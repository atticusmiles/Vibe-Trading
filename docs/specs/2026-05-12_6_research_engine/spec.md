# 阶段 6：投研引擎

## 1. 概述

**目标**：基于现有 Swarm 系统扩展投研引擎，实现 18 Agent、9 阶段的自动投研工作流，产出提案和中间报告。

**与前后阶段的关系**：依赖阶段 4（提案机制）和阶段 5（数据源 + 新闻）。本阶段是系统的核心功能，将前几个阶段的基础设施串联起来。

**前置条件**：阶段 4（提案审批可用）、阶段 5（数据源和新闻可用）。

## 2. 数据模型

### research_runs 表

```sql
CREATE TABLE research_runs (
    id              TEXT PRIMARY KEY,         -- UUID
    user_id         INTEGER NOT NULL REFERENCES users(id),
    trigger_type    TEXT NOT NULL,            -- manual / alert / manual_trend / manual_industry / manual_stock
    start_stage     INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'running',
    config          TEXT DEFAULT '{}',        -- JSON，运行配置
    started_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT,
    error           TEXT
);
```

### research_reports 表

```sql
CREATE TABLE research_reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES research_runs(id),
    stage           INTEGER NOT NULL,
    agent_id        TEXT NOT NULL,
    report_type     TEXT NOT NULL,            -- trend_proposal / industry_report / tech_analysis / ...
    title           TEXT,
    content         TEXT NOT NULL,            -- Markdown
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_reports_run ON research_reports(run_id, stage);
```

## 3. 投研 Preset 定义

### 3.1 Agent 列表（18 个）

| 阶段 | Agent | 产出 |
|------|-------|------|
| 1 | macro_analyst（宏观分析师） | 趋势提案 |
| 2 | industry_opportunity（行业机会分析师） | 行业提案 |
| 3a | industry_analyst（行业分析师） | 行业调研报告 |
| 3b | industry_stock_analyst（行业股票分析师） | 股票提案 |
| 4a | technical_analyst（技术分析师） | 技术分析报告 |
| 4b | sentiment_analyst（社交媒体情绪分析师） | 情绪分析报告 |
| 4c | news_analyst（新闻分析师） | 新闻分析报告 |
| 4d | fundamental_analyst（基本面分析师） | 基本面分析报告 |
| 5 | bull_analyst（看涨分析师） | 辩论记录 |
| 5 | bear_analyst（看跌分析师） | 辩论记录 |
| 6 | research_manager（研究经理） | 投资结论 |
| 7 | trader（交易员） | 交易建议 |
| 8a | aggressive_analyst（激进分析师） | 风险观点 |
| 8b | conservative_analyst（保守分析师） | 风险观点 |
| 8c | neutral_analyst（中立分析师） | 风险观点 |
| 9 | risk_manager（风控经理） | 最终提案 |

### 3.2 DAG 定义

```
阶段1 → 阶段2 → 阶段3a → 阶段3b → 阶段4{a,b,c,d}(并行) → 阶段5{bull,bear} → 阶段6 → 阶段7 → 阶段8{a,b,c}(并行) → 阶段9
```

每个阶段完成后的产出写入 research_reports，涉及提案的写入 proposals。

### 3.3 部分启动机制

| 触发场景 | start_stage | 输入 |
|---------|-------------|------|
| 完整投研 | 1 | 新闻流 + 行情 |
| 手动新增趋势 | 1 | 现有趋势 + 新闻 |
| 手动新增行业 | 2 | 现有趋势 + 新闻 |
| 手动新增股票 | 4 | 现有行业调研 |
| 舆情影响趋势 | 1 | 舆情 + 现有趋势 |
| 舆情影响行业 | 2 | 舆情 + 现有行业 |
| 舆情影响股票 | 4 | 舆情 + 现有股票 |

跳过的阶段直接复用已有的 reports 作为上下文输入。

## 4. Swarm 扩展组件

### 4.1 StageController

- 接收 `start_stage` 参数，控制从指定阶段开始执行
- 跳过的阶段：从 research_reports 读取已有报告注入上下文
- 每个阶段完成后通过 EventBus 发送 SSE 事件

### 4.2 ReportCollector

- 每个 Agent 完成后，解析其输出
- 提取结构化报告内容，写入 research_reports
- 关联 run_id 和 stage 编号

### 4.3 ProposalGenerator

- 从特定阶段 Agent 的输出中提取提案数据
- 构造 proposal payload，调用阶段 4 的提案创建 API
- 处理置信度淘汰

### 4.4 ProposalLimiter

- 在 ProposalGenerator 写入前检查上限
- 超限时执行淘汰，再写入新提案

## 5. API 设计

```
POST   /swarm/runs                     启动投研（现有端点，扩展参数）
      请求：{
          "preset": "research",
          "start_stage": 1,
          "trigger_type": "manual",
          "context": {"trend_ids": [1,2], "industry_ids": [3]}
      }

GET    /swarm/runs                     列出投研运行（支持 ?preset=research 过滤）
GET    /swarm/runs/{run_id}            运行详情（含各阶段状态）
GET    /swarm/runs/{run_id}/events     SSE 事件流（实时进度）
POST   /swarm/runs/{run_id}/cancel     取消运行

GET    /api/research/runs/{run_id}/reports  查看投研运行的所有报告
```

## 6. 前端设计

### 6.1 投研运行列表页（`/research`）

```
┌───────────────────────────────────────────────────┐
│  投研运行                    [启动新投研]          │
│                                                   │
│  ┌─ #2026-0512-001 ────────────────────────────┐  │
│  │ 完整投研 · 手动触发 · 运行中 · 3m22s        │  │
│  │ 阶段进度：✅✅🔄⏳⏳⏳⏳⏳⏳                    │  │
│  │ [查看详情 →]                                 │  │
│  └──────────────────────────────────────────────┘  │
│                                                   │
│  ┌─ #2026-0511-003 ────────────────────────────┐  │
│  │ 行业投研 · 舆情触发 · 已完成 · 12m05s       │  │
│  │ 产出：2条提案                                │  │
│  │ [查看详情 →]                                 │  │
│  └──────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
```

### 6.2 投研运行详情页

```
┌───────────────────────────────────────────────┐
│  投研运行 #2026-0512-001                      │
│  触发：手动 · 状态：运行中 · 耗时：3m22s       │
│                                               │
│  ✅ 阶段一：趋势发现      2m10s               │
│     → 产出：2条趋势提案  [查看报告 →]         │
│                                               │
│  ✅ 阶段二：行业筛选      1m05s               │
│     → 产出：1条行业提案  [查看报告 →]         │
│                                               │
│  🔄 阶段三：行业调研与选股  运行中...          │
│                                               │
│  ⏳ 阶段四：多维分析                          │
│  ⏳ 阶段五：投资辩论                          │
│  ⏳ 阶段六：投资决策                          │
│  ⏳ 阶段七：交易计划                          │
│  ⏳ 阶段八：风险辩论                          │
│  ⏳ 阶段九：风控决策                          │
│                                               │
│  [取消运行]                                   │
└───────────────────────────────────────────────┘
```

### 6.3 启动投研弹窗

```
┌─────────────────────────────────────────┐
│  启动自动投研                            │
│                                         │
│  投研类型：[完整投研 ▼]                 │
│                                         │
│  选择趋势：（可选，默认全部活跃趋势）     │
│  [☑ 人民币走强] [☑ 美元降息预期]        │
│                                         │
│  选择行业：（可选）                      │
│  [☑ 新能源] [☐ 半导体]                  │
│                                         │
│  [启动] [取消]                          │
└─────────────────────────────────────────┘
```

## 7. 验收标准

- [ ] 可通过 API 启动完整投研（9 阶段 DAG 按序执行）
- [ ] 并行阶段（4a-d、8a-c）同时执行
- [ ] 各阶段产出写入 research_reports
- [ ] 提案产出正确写入 proposals 表
- [ ] SSE 事件流实时推送阶段进度
- [ ] 可从指定阶段启动（部分启动）
- [ ] 可取消运行中的投研
- [ ] 前端投研列表页展示运行历史
- [ ] 前端运行详情页实时展示阶段进度
- [ ] 前端报告查看页展示中间报告（Markdown 渲染）
