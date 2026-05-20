# 阶段 6：投研引擎

## 1. 概述

**目标**：基于现有 Swarm DAG + preset 机制，实现 6 个投研 YAML，采用 **扫描（生产者）→ 调研（消费者）** 两步模式：

```
scan_trends      → 趋势候选 → research_trends     → 趋势提案
scan_industries  → 行业候选 → research_industries  → 行业提案
scan_stocks      → 股票候选 → research_stocks      → 股票提案
```

**设计原则**：
- 复用 SwarmRuntime / SwarmStore / SSE 事件流
- 扫描与调研解耦：扫描只管发现候选，调研只管深度研究 + 决策
- candidates 表是天然的队列：扫描写入（生产者），调研读取（消费者）
- 每个调研 run 只处理 1 个候选，并发调度保证吞吐
- 趋势/行业采用 researcher → pro + con → manager 辩论模式
- 股票采用 9-agent 深度分析模式（多空辩论 + 风险评估 + 交易建议）

**触发方式**：
- scan_trends：定时启动（每天），也可手动触发
- scan_industries：双重触发 — 事件驱动（趋势 proposed 时）+ 定时（每天），也可手动触发
- scan_stocks：手动启动（行业 proposed 后，用户主动触发）
- 调研：半自动 — 用户在前端看到 pending 候选后，勾选并启动调研

**前置条件**：阶段 4（提案审批）、阶段 5（数据源 + 新闻）。

## 2. 数据模型

### 2.1 research_candidates 表（唯一新增表）

合并 candidates + reports，每个候选一行，内嵌主调研报告 + 多视角分析。

```sql
CREATE TABLE research_candidates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type     TEXT NOT NULL,            -- trend / industry / stock
    name            TEXT NOT NULL,            -- 趋势标题 / 行业名 / 股票名
    code            TEXT,                     -- 仅 stock 时填写股票代码
    source_context  TEXT,                     -- 为什么入选（受益来源、入选理由）
    initial_score   INTEGER DEFAULT 0,        -- scanner 给的初始评分 0-10
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending / researching / proposed / passed
    -- 溯源
    source_run_id   TEXT,                     -- 哪次 scan run 产出的
    research_run_id TEXT,                     -- 哪次 research run 在处理（防并发重复消费）
    -- 调研报告
    report          TEXT,                     -- Markdown 主调研报告（researcher 写入）
    report_type     TEXT,                     -- macro_analysis / industry_deep_dive / tech_analysis
    reported_at     TEXT,                     -- 调研完成时间
    extra_reports   TEXT DEFAULT '[]',        -- JSON array [{agent_id, title, content}]
    -- 决策
    conclusion      TEXT,                     -- proposed 原因 / passed 原因
    proposal_id     INTEGER REFERENCES proposals(id),  -- 提案 adopted 后数据落地到 trends/industries/stocks
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT,
    UNIQUE(target_type, name, date(created_at))  -- 同天同类同名去重
);

CREATE INDEX idx_candidates_status ON research_candidates(target_type, status);
CREATE INDEX idx_candidates_research_run ON research_candidates(research_run_id);
```

**`extra_reports` 用途**：
- 趋势/行业管线：通常为空（只有 researcher 主报告）
- 股票管线：存储 bull_analyst、bear_analyst、trader、risk analysts 等多视角分析
- 每个 entry：`{"agent_id": "bull_analyst", "title": "看涨论点", "content": "..."}`

**`research_run_id` 用途**：
- batch-research 启动时原子写入，标记候选已被消费
- 防止并发 run 重复处理同一候选

**状态流转**：

```
pending → researching（batch-research 启动时标记）
        → proposed（decider 决策，创建提案）
        → adopted（proposal 被 adopted 后自动更新）
        → passed（decider 决策，记录原因）
        → passed（保鲜时条件恶化，由 proposed/adopted 降级）
```

### 2.2 复用现有结构

- **SwarmRun.config / artifacts**：存 workflow 元数据、工作流级报告（多空辩论等）
- **proposals 表**（已有）：提案产出走这张表

## 3. Agent Tool 扩展（3 个）

### 3.1 `add_candidates` Tool

Scanner / Decider Agent 调用，批量写入候选。

```python
class AddCandidatesTool(BaseTool):
    name = "add_candidates"
    parameters = {
        "target_type": "str — trend / industry / stock",
        "candidates": "str — JSON array [{name, code?, score?, reason?}]",
    # UNIQUE(target_type, name, date(created_at)) 按天去重：
    #   同一天同名同类型自动跳过，次日可重新入选
```

### 3.2 `update_candidate` Tool

Researcher / Decider 调用，写入调研报告或更新决策状态。

```python
class UpdateCandidateTool(BaseTool):
    name = "update_candidate"
    parameters = {
        "target_name": "str — 候选名称",
        "target_type": "str — trend / industry / stock（与 name 组合定位，避免重名歧义）",
        "status": "str — optional, proposed / passed",
        "conclusion": "str — optional，决策原因",
        "report": "str — optional，Markdown 主调研报告",
        "report_type": "str — optional，macro_analysis / tech_analysis / ...",
        "extra_report": "str — optional，JSON {agent_id, title, content}，追加到 extra_reports",
    }
```

- status 由 dispatch 层（batch-research API）原子设置为 "researching"，agent 不负责此状态变更
- Researcher 调用 `update_candidate(name, type, report="...", report_type="...")` 只写报告
- Decider 调用 `update_candidate(name, type, status="proposed"/"passed", conclusion="...")` 做决策
- 股票管线的多视角分析师调用 `update_candidate(name, type, extra_report={...})` 追加分析

### 3.3 `create_proposal` Tool

Decider Agent 调用，创建提案。复用阶段 4 proposals service。

```python
class CreateProposalTool(BaseTool):
    name = "create_proposal"
    parameters = {
        "target_type": "str — trend | industry | stock",
        "action": "str — create | update",
        "title": "str — proposal title",
        "payload": "str — JSON string（实体表字段：trends/industries/stocks）",
        "confidence": "int — 0-10",
        "summary": "str — optional",
    }
    # 创建 proposal 记录（target_type + target_id 指向实体表）
    # proposal adopted 后数据落地到 trends/industries/stocks 表
    # 创建后自动回写 candidate.proposal_id
```

**数据流转关系**：

```
research_candidates (筛选中间态) → proposals (审批流) → trends/industries/stocks (最终实体)
```

- `research_candidates`：投研筛选过程的中间产物，存储候选、调研报告、辩论过程
- `proposals`：审批流程，target_type + target_id 指向实体表
- `trends / industries / stocks`：最终有效数据，AI **只能通过提案间接更新**，无权直接修改
- 保鲜操作：重新调研后，仅当结论显著变化时创建新提案，由人工审批后生效

## 4. 六个工作流

### 4.1 通用架构

投研分为两个阶段，通过 candidates 表衔接，调研阶段支持并发：

```
扫描阶段（生产者）                    candidates 表                    调研阶段（消费者，可并发）

┌── scanner ──┐                                                     ┌── researcher_1 ──┐  ┌── researcher_2 ──┐
│ 单 agent    │──→ add_candidates ──→ pending 候选 ──→ 调度分发 ──→ │ 候选 A,B         │  │ 候选 C,D         │
│ 发现候选    │                                                     └──────────────────┘  └──────────────────┘
└─────────────┘                                                           ↓                      ↓
                                                                    ┌── decider ──┐    ┌── decider ──┐
                                                                    │ 决策         │    │ 决策         │
                                                                    └─────────────┘    └─────────────┘
```

- 扫描 YAML：单 agent（scanner），单 task
- 调研 YAML：researcher → pro + con（并行辩论）→ manager（决策）
- 每次 research run 只处理 1 个候选，保证质量
- 调度器可同时启动多个 research run（不同候选），并发执行
- batch-research API 启动时原子标记候选为 researching + 写入 research_run_id，防止重复消费

**并发调度流程**：

```
1. 找到 N 个 pending 候选（同 target_type）
2. 对每个候选：
   a. 原子更新：status=researching, research_run_id=新run_id
   b. 启动 Swarm run，user_vars.candidate_names=[该候选名]
3. N 个 run 并发执行
```

### 4.2 趋势管线

#### scan_trends.yaml

**触发**：手动启动，指定 market
**产出**：趋势候选（写入 candidates 表）

| Agent | 角色 | Tools | 职责 |
|-------|------|-------|------|
| trend_scanner | 趋势扫描器 | fetch_news, fetch_kline, fetch_quote, add_candidates, load_skill | 从新闻+行情中识别候选趋势 |

**DAG**：`task-scan`（单 task）

**system_prompt 要点**：
- 广度优先：fetch_news(limit=50, days=7) 读取近 7 天新闻明细 + fetch_news(mode="digest", days=90) 读取近 90 天新闻摘要，结合主要指数行情
- 识别正在形成的趋势信号（政策方向、资金异动、产业变化）
- 对每个信号调用 add_candidates（target_type: trend），给出 initial_score 和 source_context
- 宁多勿漏，后续由 researcher 深度过滤

**上下文需求**：
| 来源 | 内容 | 获取方式 |
|------|------|----------|
| {existing_trends} | 当前 trends 表中 proposed + adopted 的趋势列表（title, status, confidence） | user_vars 启动时注入 |
| 7 天新闻明细 | 近期市场动态 | fetch_news(limit=50, days=7) |
| 90 天新闻摘要 | 长周期趋势背景 | fetch_news(mode="digest", days=90) |
| 指数行情 | 上证/深证/创业板等主要指数 | fetch_kline, fetch_quote |

#### research_trends.yaml

**触发**：用户在候选列表中勾选 pending 趋势候选后启动（每个候选一个 run）
**输入**：user_vars 包含 `candidate_names`（JSON 数组，1 个元素，如 `["人民币走强"]`）
**产出**：趋势提案

| Agent | 角色 | Tools | 职责 |
|-------|------|-------|------|
| trend_researcher | 趋势调研员 | fetch_news, fetch_kline, fetch_quote, fetch_research, update_candidate, load_skill | 深度调研候选趋势 |
| trend_pro | 趋势支持方 | update_candidate, load_skill | 论证该趋势成立的理由 |
| trend_con | 趋势反对方 | update_candidate, load_skill | 论证该趋势不成立或风险 |
| trend_manager | 趋势决策者 | update_candidate, create_proposal, load_skill | 综合正反意见做 proposed/passed 决策 |

**DAG**：`task-research → task-pro + task-con（并行）→ task-manager`

**trend_researcher system_prompt 要点**：
- 调研 {candidate_names} 中的候选（状态已为 researching）
- update_candidate(name, type, report="...", report_type="macro_analysis")
- 多维度验证：宏观指标、政策连贯性、历史类似趋势、当前所处阶段

**trend_researcher 上下文需求**：
| 来源 | 内容 | 获取方式 |
|------|------|----------|
| {candidate_names} | 待调研候选名称 | user_vars |
| {candidate_info} | 候选的 source_context、initial_score | user_vars（启动时从 candidates 表读取） |
| {existing_trends} | 当前 trends 表已有趋势（避免重复、参考历史） | user_vars 注入 |
| 新闻 + 行情 | 趋势相关最新数据和新闻 | fetch_news, fetch_kline, fetch_quote, fetch_research |

**trend_pro system_prompt 要点**：
- 读取 {upstream_context} 中 researcher 的调研报告
- update_candidate(name, type, extra_report={agent_id: "trend_pro", title: "趋势成立论点", content: "..."})
- 从数据中找到支持该趋势成立的证据

**trend_con system_prompt 要点**：
- 读取 {upstream_context} 中 researcher 的调研报告
- update_candidate(name, type, extra_report={agent_id: "trend_con", title: "趋势风险论点", content: "..."})
- 从数据中找到该趋势不成立或有风险的证据

**trend_pro / trend_con 上下文需求**：
| 来源 | 内容 | 获取方式 |
|------|------|----------|
| {upstream_context} | researcher 调研报告 | Swarm upstream summaries |
| {candidate_names} | 候选名称 | user_vars |

**trend_manager system_prompt 要点**：
- 读取 {upstream_context} 中 researcher 调研报告 + pro/con 辩论
- 权衡正反意见：proposed → create_proposal + update_candidate(name, type, "proposed")；passed → update_candidate(name, type, "passed", conclusion="原因")
- 确保候选最终状态非 researching
- 保鲜时：结论无显著变化则仅更新报告，不创建新提案

**trend_manager 上下文需求**：
| 来源 | 内容 | 获取方式 |
|------|------|----------|
| {upstream_context} | researcher 报告 + pro/con 辩论 | Swarm upstream summaries |
| {candidate_names} | 候选名称 | user_vars |
| {existing_trend} | 如果是保鲜：该趋势在 trends 表的当前状态和上次报告 | user_vars 注入 |

### 4.3 行业管线

#### scan_industries.yaml

**触发**：双重触发 — 事件驱动（趋势 proposed 时自动触发）+ 定时（每天），也可手动触发
**输入变量**：
- `trend_context`：自动构建 — 读取所有 proposed 趋势候选 + fetch_news(mode="digest", days=60) 60 天新闻摘要
**产出**：行业候选（写入 candidates 表）

| Agent | 角色 | Tools | 职责 |
|-------|------|-------|------|
| industry_scanner | 行业扫描器 | fetch_news, fetch_financial, add_candidates, load_skill | 从活跃趋势中识别受益行业 |

**DAG**：`task-scan`（单 task）

**system_prompt 要点**：
- 从 {trend_context} 读取活跃趋势和近期新闻摘要
- 识别每个趋势下的受益行业
- 调用 add_candidates（target_type: industry），source_context 记录受益趋势
- 每个行业给出受益逻辑和 initial_score

**上下文需求**：
| 来源 | 内容 | 获取方式 |
|------|------|----------|
| {trend_context} | 所有 proposed/adopted 趋势（title, status, confidence, evidence）+ 60 天新闻摘要 | user_vars 启动时自动构建 |
| {existing_industries} | 当前 industries 表已有行业（避免重复） | user_vars 注入 |
| {existing_trends} | trends 表活跃趋势详情（用于判断受益逻辑） | user_vars 注入 |
| 行业财务数据 | 行业指数、板块资金流向 | fetch_financial |
| 新闻 | 行业相关新闻 | fetch_news |

#### research_industries.yaml

**触发**：用户勾选 pending 行业候选后启动（每个候选一个 run）
**输入**：user_vars 包含 `candidate_names`（1 个元素）
**产出**：行业提案

| Agent | 角色 | Tools | 职责 |
|-------|------|-------|------|
| industry_researcher | 行业调研员 | fetch_financial, fetch_research, fetch_news, update_candidate, load_skill | 深度调研 |
| industry_pro | 行业支持方 | update_candidate, load_skill | 论证该行业值得投资 |
| industry_con | 行业反对方 | update_candidate, load_skill | 论证该行业的风险和不利因素 |
| industry_manager | 行业决策者 | update_candidate, create_proposal, load_skill | 综合正反意见做 proposed/passed 决策 |

**DAG**：`task-research → task-pro + task-con（并行）→ task-manager`

**industry_researcher system_prompt 要点**：
- 调研 {candidate_names} 中的候选（状态已为 researching）
- 调研：景气度、产业链分析、竞争格局、龙头股初筛
- update_candidate(name, type, report="...", report_type="industry_deep_dive")

**industry_researcher 上下文需求**：
| 来源 | 内容 | 获取方式 |
|------|------|----------|
| {candidate_names} | 待调研候选名称 | user_vars |
| {candidate_info} | 候选的 source_context（受益趋势）、initial_score | user_vars |
| {related_trends} | 该行业受益的活跃趋势详情（从 source_context 解析） | user_vars 注入 |
| {existing_industries} | industries 表已有行业（参考同行） | user_vars 注入 |
| 行业财务数据 + 研报 | 景气度、产业链、竞争格局 | fetch_financial, fetch_research, fetch_news |

**industry_pro / industry_con**：同趋势管线模式，输出 extra_report

**industry_manager system_prompt 要点**：
- 综合正反意见做决策
- 确保候选最终状态非 researching
- 保鲜时：结论无显著变化则仅更新报告，不创建新提案

**industry_manager 上下文需求**：
| 来源 | 内容 | 获取方式 |
|------|------|----------|
| {upstream_context} | researcher 报告 + pro/con 辩论 | Swarm upstream summaries |
| {candidate_names} | 候选名称 | user_vars |
| {existing_industry} | 如果是保鲜：该行业在 industries 表的当前状态 | user_vars 注入 |

### 4.4 股票管线

#### scan_stocks.yaml

**触发**：双重触发 — 事件驱动（行业 proposed 时自动触发）+ 定时（每天），也可手动触发
**产出**：股票候选（写入 candidates 表）

| Agent | 角色 | Tools | 职责 |
|-------|------|-------|------|
| stock_scanner | 股票扫描器 | fetch_financial, fetch_news, add_candidates, load_skill | 从已提案行业中识别候选股票 |

**DAG**：`task-scan`（单 task）

**system_prompt 要点**：
- 从 {industry_names} 读取已提案行业
- 对每个行业筛选 3-5 只候选股票（基本面 + 技术面初筛）
- 调用 add_candidates（target_type: stock, code=股票代码），source_context 记录所属行业
- 给出初步评分和入选理由

**上下文需求**：
| 来源 | 内容 | 获取方式 |
|------|------|----------|
| {industry_names} | 已 proposed/adopted 的行业列表 | user_vars 注入 |
| {industry_details} | 行业详情（reason, confidence, research_report） | user_vars 注入 |
| {existing_stocks} | 当前 stocks 表已有股票（避免重复、参考持仓） | user_vars 注入 |
| {current_portfolio} | 当前持仓信息（已持有的股票及仓位） | user_vars 注入 |
| 财务数据 + 新闻 | 基本面初筛 | fetch_financial, fetch_news |

#### research_stocks.yaml

**触发**：用户勾选 pending 股票候选后启动（每个候选一个 run）
**输入**：user_vars 包含 `candidate_names`（1 个元素）
**产出**：股票提案（带交易建议和风控参数）

| Agent | 角色 | Tools | 职责 |
|-------|------|-------|------|
| stock_researcher | 股票调研员 | fetch_kline, fetch_quote, fetch_financial, fetch_news, fetch_research, update_candidate, load_skill | 深度调研（技术+基本面+新闻） |
| bull_analyst | 看涨分析师 | update_candidate, load_skill | 看涨论点 |
| bear_analyst | 看跌分析师 | update_candidate, load_skill | 看跌论点 |
| research_manager | 研究经理 | update_candidate, load_skill | 投资结论 |
| trader | 交易员 | fetch_kline, fetch_quote, update_candidate, load_skill | 交易建议 |
| aggressive_analyst | 激进分析师 | update_candidate, load_skill | 风险观点 |
| conservative_analyst | 保守分析师 | update_candidate, load_skill | 风险观点 |
| neutral_analyst | 中立分析师 | update_candidate, load_skill | 风险观点 |
| risk_manager | 风控经理 | update_candidate, create_proposal, load_skill | 最终决策 |

**DAG**：

```
task-research ──┬── task-bull  ─┐
                └── task-bear  ─┤ 并行 → task-manager → task-trader ──┐
                                                        ┌── task-aggressive ─┐ │
                                                        ├── task-conservative┤ │
                                                        └── task-neutral ────┘ │
                                                                        │      │
                                                                        └──────┘
                                                                             │
                                                                     task-risk-manager
```

- stock_researcher 深度调研候选，写入 report
- 多视角分析师通过 update_candidate(name, type, extra_report={...}) 追加分析到 extra_reports
- 后续多空辩论、风险评估基于调研报告展开（通过 {upstream_context}）
- risk_manager 做最终决策：create_proposal + "proposed" 或 "passed"
- 确保候选最终状态非 researching
- 保鲜时：结论无显著变化则仅更新报告，不创建新提案

**各 Agent 上下文需求**：

| Agent | 上下文 | 来源 |
|-------|--------|------|
| **stock_researcher** | {candidate_names}、{candidate_info}（source_context 所属行业、initial_score） | user_vars |
| | {related_industry} | 所属行业详情（name, confidence, research_report） | user_vars 注入 |
| | {existing_stocks} | stocks 表已有股票（参考同行、避免重复） | user_vars 注入 |
| | K线 + 行情 + 财务 + 新闻 + 研报 | 技术面+基本面+消息面 | fetch_* tools |
| **bull_analyst** | {upstream_context} | researcher 调研报告 | Swarm upstream |
| | {candidate_names} | 候选名称 | user_vars |
| **bear_analyst** | {upstream_context} | researcher 调研报告 | Swarm upstream |
| | {candidate_names} | 候选名称 | user_vars |
| **research_manager** | {upstream_context} | researcher 报告 + bull/bear 辩论 | Swarm upstream |
| | {candidate_names} | 候选名称 | user_vars |
| **trader** | {upstream_context} | research_manager 投资结论 | Swarm upstream |
| | {candidate_names} + code | 候选名称和代码 | user_vars |
| | K线 + 行情 | 量价分析，计算入场/止损/止盈位 | fetch_kline, fetch_quote |
| | {current_portfolio} | 当前持仓（已有仓位的相关股票） | user_vars 注入 |
| **aggressive_analyst** | {upstream_context} | research_manager 结论 + trader 交易建议 | Swarm upstream |
| | {candidate_names} | 候选名称 | user_vars |
| **conservative_analyst** | 同 aggressive | 同上 | 同上 |
| **neutral_analyst** | 同 aggressive | 同上 | 同上 |
| **risk_manager** | {upstream_context} | research_manager + trader + 三视角风险分析 | Swarm upstream |
| | {candidate_names} | 候选名称 | user_vars |
| | {current_portfolio} | 当前完整持仓（仓位占比、行业集中度、相关性） | user_vars 注入 |
| | {existing_stock} | 如果是保鲜：该股票在 stocks 表的当前状态和上次报告 | user_vars 注入 |

## 5. API 设计

```
# Swarm 运行（已有）
POST   /swarm/runs                     启动扫描或调研
GET    /swarm/runs                     列出运行
GET    /swarm/runs/{run_id}            运行详情
GET    /swarm/runs/{run_id}/events     SSE 事件流
POST   /swarm/runs/{run_id}/cancel     取消运行

# 候选管理（新增）
GET    /api/research/candidates                     查询候选列表
      参数：?target_type=stock&status=pending
GET    /api/research/candidates/{id}                 单个候选详情（含 report + extra_reports）
POST   /api/research/candidates/batch-research       批量启动调研（每个候选一个 run，并发执行）
      请求：{
          "candidate_ids": [1, 2, 3],
          "max_concurrent": 3        // 可选，最大并发 run 数
      }
      校验：
        - 所有候选 target_type 一致
        - 所有候选 status = pending
        - 根据 target_type 自动选择 preset_name
      流程：
        - 对每个候选：原子更新 status=researching, research_run_id=新ID → 启动 run
        - 按 max_concurrent 控制并发数
        - 返回所有 run_id 列表
```

## 6. 调度器

### 6.1 定时调度

| 预设 | 周期 | 说明 |
|------|------|------|
| scan_trends | 每天 | 扫描最新趋势 |
| scan_industries | 每天 | 基于活跃趋势扫描受益行业 |
| scan_stocks | 每天 | 基于已提案行业扫描候选股票 |

### 6.2 事件驱动调度

跟踪 `research_candidates` 表变化：

| 事件 | 触发条件 | 动作 |
|------|----------|------|
| 趋势 proposed | candidate.status 变为 `proposed` 且 target_type=`trend` | 自动构建 trend_context（所有 proposed 趋势 + 60 天新闻摘要），启动 scan_industries |
| 行业 proposed | candidate.status 变为 `proposed` 且 target_type=`industry` | 启动 scan_stocks，industry_names 取所有 proposed 行业 |

事件来源：`update_candidate` tool 写入 status 变更时，检查是否满足触发条件。

### 6.3 保鲜调度

对 `trends`、`industries`、`stocks` 实体表中 `proposed` 和 `adopted` 状态的记录定期重新调研。AI 只能通过提案间接更新实体表，保鲜流程：

1. 筛选待保鲜记录 → 创建临时 candidate → 启动 research YAML
2. researcher 用最新数据重新调研，参考旧报告作为上下文
3. 结论显著变化 → `create_proposal` 创建新提案（人工审批后才更新实体表）
4. 结论无显著变化 → 仅更新 candidate 报告，不创建提案

| target_type | 频率 | 执行逻辑 |
|-------------|------|----------|
| trend | 每天 | 筛选 trends 表 updated_at > 1 天的 proposed + adopted 记录，逐个启动 research_trends |
| industry | 每天 | 筛选 industries 表 updated_at > 1 天的 proposed + adopted 记录，逐个启动 research_industries |
| stock | 每天 | 筛选 stocks 表 updated_at > 1 天的 proposed + adopted 记录，逐个启动 research_stocks |

保鲜 run 与首次调研 run 流程完全一致，区别在于：
- 候选已有旧 report 和 extra_reports，researcher 读取旧报告作为上下文，结合最新数据生成新报告
- manager 可将 proposed/adopted 改为 `passed`（如果条件恶化）
- 保鲜后 updated_at 更新，避免短期内重复刷新

**保鲜审慎原则**：
- 只有结论与上次**显著不同**时（如评分变化 ≥ 2 分、基本面重大变化、新的重大风险），才创建新提案
- 结论无显著差异时，仅更新报告内容，不创建新提案，不改变状态
- adopted 候选降级为 passed 需要充分理由（明确的风险信号），不能仅因小幅波动降级

## 7. 前端设计

### 7.1 投研中心页（`/research`）

```
┌───────────────────────────────────────────────────┐
│  投研中心                                          │
│                                                   │
│  [趋势管线]  [行业管线]  [股票管线]                │
│                                                   │
│  ┌─ 待调研候选 ───────────────────────────────┐   │
│  │ ☐ 人民币走强 (趋势)  评分:8                │   │
│  │ ☐ AI算力增长 (趋势)  评分:7                │   │
│  │ ☐ 新能源 (行业)      评分:6  受益:人民币走强│   │
│  │            [勾选后启动调研 →]               │   │
│  └────────────────────────────────────────────┘   │
│                                                   │
│  运行历史：                                       │
│  ┌─ #swarm-xxx ───────────────────────────────┐   │
│  │ 趋势扫描 · 已完成 · 产出 8 个候选          │   │
│  └────────────────────────────────────────────┘   │
│  ┌─ #swarm-yyy ───────────────────────────────┐   │
│  │ 趋势调研 · 已完成 · 3 proposed / 2 passed  │   │
│  └────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────┘
```

### 7.2 运行详情页（`/research/{run_id}`）

根据 preset_name 区分扫描/调研，展示不同内容：

**扫描 run**：展示发现的候选列表 + 评分 + 入选理由
**调研 run**：展示候选进度

```
┌───────────────────────────────────────────────┐
│  趋势调研 #swarm-yyy                          │
│  状态：运行中 · 耗时：3m10s                    │
│                                               │
│  候选进度：                                   │
│  ┌─ 人民币走强 ──────── 🔄 调研中 ────────┐   │
│  │  [查看调研报告 →]                      │   │
│  └────────────────────────────────────────┘   │
│  ┌─ AI 算力需求增长 ─── ✅ 已提案 (7分) ──┐   │
│  │  [查看调研报告 →] [查看提案 →]         │   │
│  └────────────────────────────────────────┘   │
│  ┌─ 房地产放松 ──────── ❌ 已放弃 ────────┐   │
│  │  原因：政策信号不连贯，历史类似趋势短   │   │
│  │  [查看调研报告 →]                      │   │
│  └────────────────────────────────────────┘   │
└───────────────────────────────────────────────┘
```

### 7.3 启动弹窗

**扫描弹窗**：

```
┌─────────────────────────────────────────┐
│  启动扫描                               │
│                                         │
│  扫描类型：[趋势扫描 ▼]                 │
│                                         │
│  目标市场：[A股        ]                 │
│                                         │
│  [启动] [取消]                          │
└─────────────────────────────────────────┘

行业扫描额外字段：
  趋势来源：[自动读取活跃趋势 ▼]

股票扫描额外字段：
  行业来源：[选择已提案行业 ▼]
```

**调研弹窗**（从候选列表勾选后触发）：

```
┌─────────────────────────────────────────┐
│  启动调研                               │
│                                         │
│  候选数量：3 个                          │
│  - 人民币走强 (趋势)                    │
│  - AI算力增长 (趋势)                    │
│  - 房地产放松 (趋势)                    │
│                                         │
│  [启动] [取消]                          │
└─────────────────────────────────────────┘
```

## 8. 验收标准

- [ ] 6 个 YAML：3 scan + 3 research，scan 单 task，趋势/行业 researcher → pro + con → manager，股票 9-agent 复杂 DAG
- [ ] `add_candidates` 批量写入候选（pending），写入 source_run_id 和 source_context
- [ ] `update_candidate` 按 (target_type, name) 定位，写入 report / extra_report / 决策状态
- [ ] `create_proposal` 仅对最优候选创建提案，自动回写 proposal_id
- [ ] batch-research 启动时原子标记 researching + research_run_id，防止并发重复消费
- [ ] 每次 research run 只处理 1 个候选
- [ ] 并发调度：可同时启动多个 research run（每个候选独立 run），互不干扰
- [ ] 三层衔接：scan_trends → research_trends → scan_industries → research_industries → scan_stocks → research_stocks
- [ ] SSE 实时推送各阶段进度
- [ ] candidates API 支持按 type/status 过滤 + extra_reports 展示
- [ ] batch-research API 校验候选一致性 + 自动选择 preset + 并发启动
- [ ] 前端候选列表支持勾选 + 启动调研
- [ ] 集成测试：mock LLM 验证 scan → research 全流程（含并发调度）
