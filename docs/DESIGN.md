# AI辅助投研系统 — 整体设计

## 1. 设计目标

基于 `docs/specs/OVERALL_SPEC.md` 定义的业务需求，在现有 Vibe-Trading 项目基础上，设计一套支持多用户、多 Agent 协同、提案驱动的 AI 投研系统。

## 2. 系统架构总览

```
┌─────────────────────────────────────────────────────────┐
│                      前端 (React)                         │
│  ┌──────┐ ┌──────────┐ ┌──────┐ ┌──────┐ ┌──────────┐  │
│  │ 对话  │ │ 趋势管理  │ │ 行业  │ │ 自选股│ │ Agent配置 │  │
│  └──────┘ └──────────┘ └──────┘ └──────┘ └──────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP / SSE
┌───────────────────────┼─────────────────────────────────┐
│                  API Server (FastAPI)                     │
│           认证 · 路由 · 飞书Webhook · 定时任务             │
└───────────┬───────────┬──────────────┬──────────────────┘
            │           │              │
┌───────────▼──┐ ┌──────▼──────┐ ┌────▼─────────────────┐
│  投研引擎     │ │  数据管理    │ │  外部集成             │
│              │ │              │ │                      │
│ · Agent团队   │ │ · 事实表CRUD │ │ · 飞书消息推送        │
│ · 工作流编排   │ │ · 提案管理   │ │ · 飞书对话接入        │
│ · 每日新闻    │ │ · 审批流转   │ │ · 数据源适配          │
│ · 舆情监控    │ │ · 审计日志   │ │                      │
└───────────┬──┘ └──────┬──────┘ └──────────────────────┘
            │           │
     ┌──────▼───────────▼──────┐
     │     SQLite 数据库        │
     │  用户 · 偏好 · 事实表    │
     │  提案 · 报告 · 审计日志   │
     └─────────────────────────┘
```

## 3. 数据库设计

系统使用单一 SQLite 数据库 `~/.vibe-trading/vibe.db`，统一存储所有业务数据和现有 session 搜索索引（替代原有 `sessions.db`）。

### 3.1 用户表

```
users
├── id              INTEGER PK
├── username        TEXT UNIQUE NOT NULL
├── password_hash   TEXT NOT NULL
├── api_keys        TEXT        -- JSON，各类型API Key（仅密钥值加密，结构可读）
│   └── {"llm_provider": {"key":"enc:xxx","label":"OpenRouter","model":"xxx","base_url":"xxx"}, "tushare": {"key":"enc:xxx"}, ...}
├── preferences     TEXT        -- JSON，投资偏好（整体读写）
│   └── {"investment_style":"价值投资", "risk_appetite":"稳健型", "focus_markets":[...], ...}
├── settings        TEXT        -- JSON，系统设置（整体读写）
│   └── {"news_archive_time":"08:00", "sentinel_interval":60, "proposal_limits":{"trend":10,...}, "feishu":{...}}
├── created_at      DATETIME
└── updated_at      DATETIME
```

### 3.2 Agent 配置

```
agent_configs
├── id              INTEGER PK
├── user_id         INTEGER FK → users.id
├── agent_id        TEXT        -- 对应 preset 中的 agent id
├── system_prompt   TEXT        -- 用户自定义提示词，NULL表示使用默认
├── enabled_skills  TEXT        -- JSON array，NULL表示使用默认
├── enabled_tools   TEXT        -- JSON array，NULL表示使用默认
├── updated_at      DATETIME
└── UNIQUE(user_id, agent_id)
```

### 3.3 事实表

三张事实表共享相同的状态流转：`proposed` | `adopted` | `rejected` | `removed`

```
trends
├── id              INTEGER PK
├── user_id         INTEGER FK → users.id
├── status          TEXT
├── title           TEXT
├── level           TEXT            -- 长期 / 中期 / 短期
├── confidence      INTEGER         -- 0~10
├── evidence        TEXT            -- 支撑依据
├── created_at      DATETIME
├── updated_at      DATETIME
└── UNIQUE(user_id, title)

industries
├── id              INTEGER PK
├── user_id         INTEGER FK → users.id
├── status          TEXT
├── name            TEXT
├── confidence      INTEGER         -- 0~10
├── reason          TEXT            -- 入选理由
├── research_report TEXT            -- 行业调研报告
├── recommended_stocks TEXT         -- JSON array
├── created_at      DATETIME
├── updated_at      DATETIME
└── UNIQUE(user_id, name)

stocks
├── id              INTEGER PK
├── user_id         INTEGER FK → users.id
├── status          TEXT
├── name            TEXT
├── code            TEXT
├── confidence      INTEGER         -- 0~10
├── industry_id     INTEGER FK → industries.id
├── position        TEXT            -- 持仓
├── advice          TEXT            -- 买入/卖出/持有
├── target_price    REAL            -- 目标价位
├── stop_loss       REAL            -- 止损位
├── reason          TEXT
├── created_at      DATETIME
├── updated_at      DATETIME
└── UNIQUE(user_id, code)
```

状态值：`proposed` | `adopted` | `rejected` | `removed`

### 3.4 提案表

```
proposals
├── id                INTEGER PK
├── user_id           INTEGER FK → users.id
├── target_type       TEXT        -- trend / industry / stock
├── target_id         INTEGER     -- 事实表记录ID，新增时为NULL
├── action            TEXT        -- create / update / delete
├── status            TEXT        -- pending / adopted / rejected
├── title             TEXT
├── summary           TEXT
├── payload           TEXT        -- JSON，目标字段值
├── original_payload  TEXT        -- JSON，仅update类型
├── run_id            TEXT        -- 关联的投研运行ID
├── source_agent      TEXT        -- 产出Agent
├── created_at        DATETIME
├── reviewed_at       DATETIME
```

### 3.5 投研运行与报告

```
research_runs
├── id              TEXT PK         -- UUID
├── user_id         INTEGER FK → users.id
├── trigger_type    TEXT            -- manual / auto / alert
├── start_stage     INTEGER         -- 从哪个阶段开始（1-9）
├── status          TEXT            -- running / completed / failed
├── config          TEXT            -- JSON，运行配置
├── started_at      DATETIME
├── completed_at    DATETIME
└── error           TEXT

research_reports
├── id              INTEGER PK
├── run_id          TEXT FK → research_runs.id
├── stage           INTEGER         -- 阶段编号（1-9）
├── agent_id        TEXT            -- 产出Agent
├── report_type     TEXT            -- trend_proposal / industry_report / ...
├── title           TEXT
├── content         TEXT            -- 报告正文（Markdown）
├── metadata        TEXT            -- JSON，附加数据
├── created_at      DATETIME
└── INDEX(run_id, stage)
```

### 3.6 审计日志

```
audit_logs
├── id              INTEGER PK
├── user_id         INTEGER FK → users.id
├── action          TEXT        -- proposal_created / proposal_adopted / ...
├── target_type     TEXT
├── target_id       INTEGER
├── details         TEXT        -- JSON
├── created_at      DATETIME
├── actor_type      TEXT        -- user / agent
├── actor_id        TEXT
└── INDEX(user_id, target_type, created_at)
```

### 3.7 新闻存档

```
news_digests
├── id              INTEGER PK
├── user_id         INTEGER FK → users.id
├── digest_date     DATE            -- 新闻日期
├── content         TEXT            -- 结构化新闻简报（Markdown）
├── summary         TEXT            -- 一句话摘要
├── created_at      DATETIME
└── UNIQUE(user_id, digest_date)

alert_events
├── id              INTEGER PK
├── user_id         INTEGER FK → users.id
├── event_type      TEXT            -- news / sentiment
├── title           TEXT
├── content         TEXT
├── relevance_score REAL            -- 相关性评分 0-1
├── affected_type   TEXT            -- trend / industry / stock
├── affected_ids    TEXT            -- JSON array
├── triggered_run_id TEXT FK → research_runs.id  -- 触发的投研运行
├── created_at      DATETIME
└── INDEX(user_id, created_at)
```

## 4. API 设计

### 4.1 认证（新增）

```
POST   /auth/register           注册
POST   /auth/login              登录，返回 JWT
POST   /auth/logout             登出
GET    /auth/me                 当前用户信息
```

认证方式：JWT Token，放在 `Authorization: Bearer <token>` 中。所有 API 通过中间件从 Token 解析 `user_id`，不通过 URL 或请求体传递，从根源杜绝水平越权。

### 4.2 用户配置（新增）

所有 `/api/user/*` 接口基于 Token 中的 `user_id` 自动定位当前用户，无需也不允许指定其他用户。

```
GET    /api/user/preferences           获取投资偏好
PUT    /api/user/preferences           更新投资偏好（整体替换）
GET    /api/user/api-keys              获取全部API Key（密钥值脱敏）
PUT    /api/user/api-keys              整体替换（删除某个key_type传null或不传即可）
GET    /api/user/settings              获取用户设置
PUT    /api/user/settings              更新用户设置（整体替换）
```

### 4.3 趋势管理（新增）

```
GET    /api/trends                     获取趋势列表（支持 ?status= 过滤）
GET    /api/trends/{id}                趋势详情
POST   /api/trends                     手动添加趋势（直接adopted，触发评估）
PUT    /api/trends/{id}                手动更新趋势
DELETE /api/trends/{id}                手动删除趋势
GET    /api/trends/{id}/reports        查看关联的投研报告
```

### 4.4 行业管理（新增）

```
GET    /api/industries                 获取行业列表
GET    /api/industries/{id}            行业详情
POST   /api/industries                 手动添加行业
PUT    /api/industries/{id}            手动更新行业
DELETE /api/industries/{id}            手动删除行业
GET    /api/industries/{id}/reports    查看关联的投研报告
```

### 4.5 自选股管理（新增）

```
GET    /api/stocks                     获取自选股列表
GET    /api/stocks/{id}                股票详情
POST   /api/stocks                     手动添加股票
PUT    /api/stocks/{id}                手动更新股票
DELETE /api/stocks/{id}                手动删除自选股
GET    /api/stocks/{id}/reports        查看关联的投研报告
```

### 4.6 提案管理（新增）

```
GET    /api/proposals                  获取提案列表（支持 ?type=&status=&target_id= 过滤）
GET    /api/proposals/{id}             提案详情（含关联报告）
POST   /api/proposals/{id}/adopt       采纳提案
POST   /api/proposals/{id}/reject      拒绝提案
GET    /api/proposals/{id}/reports     查看提案关联的中间报告
```

### 4.7 投研引擎（新增）

投研运行复用现有 Swarm 基建，不单独建 `/api/research/runs`。启动投研时在 `POST /swarm/runs` 传入投研 preset + 额外参数（start_stage、trigger_type），运行态（详情、SSE、取消）直接用现有 Swarm 端点。仅新增投研特有的报告查询接口。

```
POST   /swarm/runs                     启动投研（现有端点，扩展投研参数）
GET    /swarm/runs                     列出投研运行（现有端点，支持 ?preset=research 过滤）
GET    /swarm/runs/{run_id}            运行详情（现有端点）
GET    /swarm/runs/{run_id}/events     SSE事件流（现有端点）
POST   /swarm/runs/{run_id}/cancel     取消运行（现有端点）
GET    /api/research/runs/{run_id}/reports  查看投研运行的所有中间报告（新增）
```

### 4.8 Agent 配置（新增）

```
GET    /api/agents                     获取Agent列表及默认配置
GET    /api/agents/{agent_id}          单个Agent配置详情
PUT    /api/agents/{agent_id}          更新用户自定义配置
DELETE /api/agents/{agent_id}          恢复默认配置
GET    /api/agents/{agent_id}/skills   获取Agent可用技能列表
GET    /api/agents/{agent_id}/tools    获取Agent可用工具列表
```

### 4.9 飞书集成（新增）

```
POST   /api/feishu/webhook            飞书事件回调（消息、卡片操作）
POST   /api/feishu/bind               绑定飞书账号
DELETE /api/feishu/bind               解绑飞书账号
GET    /api/feishu/config             获取飞书配置
PUT    /api/feishu/config             更新飞书配置
```

### 4.10 现有接口（保持不动）

```
# 系统
GET    /health                         健康检查
GET    /api                             API 信息
GET    /correlation                     相关性矩阵
POST   /system/shutdown                 关闭服务

# Settings（现有，投研系统上线后由 /api/user 替代）
GET    /settings/llm                    获取 LLM 配置
PUT    /settings/llm                    更新 LLM 配置
GET    /settings/data-sources           获取数据源配置
PUT    /settings/data-sources           更新数据源配置

# Runs（现有）
GET    /runs                            列出运行
GET    /runs/{run_id}                   运行详情
GET    /runs/{run_id}/code              获取策略代码
GET    /runs/{run_id}/pine              获取 Pine Script

# Sessions（现有）
POST   /sessions                        创建会话
GET    /sessions                        列出会话
GET    /sessions/{session_id}           会话详情
PATCH  /sessions/{session_id}           更新会话
DELETE /sessions/{session_id}           删除会话
POST   /sessions/{session_id}/messages  发送消息
GET    /sessions/{session_id}/messages  获取消息列表
GET    /sessions/{session_id}/events    SSE 事件流
POST   /sessions/{session_id}/cancel    取消会话

# Swarm（现有）
GET    /swarm/presets                   列出 Swarm 预设
POST   /swarm/runs                      启动 Swarm 运行
GET    /swarm/runs                      列出 Swarm 运行
GET    /swarm/runs/{run_id}             运行详情
GET    /swarm/runs/{run_id}/events      SSE 事件流
POST   /swarm/runs/{run_id}/cancel      取消运行

# 其他（现有）
GET    /skills                          列出技能
GET    /shadow-reports/{shadow_id}      获取影子报告
POST   /upload                          上传文件
```

## 5. 投研引擎设计

### 5.1 基于现有 Swarm 的扩展

现有 Swarm 系统已具备 DAG 编排、并行执行、文件存储、SSE 事件流等能力。投研引擎在其基础上扩展：

```
投研 Preset YAML（新增）
    │
    ▼
SwarmRuntime（现有）
    │
    ▼
投研引擎层（新增）
    ├── ProposalGenerator     从Agent输出提取提案，写入proposals表
    ├── ReportCollector        收集各阶段报告，写入research_reports表
    ├── StageController        控制从哪个阶段开始执行（支持部分启动）
    └── ProposalLimiter        检查提案上限，执行置信度淘汰
```

### 5.2 工作流 Preset

新增投研专用的 preset YAML，定义 18 个 Agent 和 9 个阶段的 DAG。每个阶段的 Agent 完成后，`ProposalGenerator` 从产出中提取结构化提案数据。

### 5.3 部分启动机制

舆情监控和手动添加触发的投研不需要从头运行，支持从指定阶段开始：

| 触发场景 | 起始阶段 | 输入来源 |
|---------|---------|---------|
| 完整投研 | 阶段一 | 新闻流 + 行情数据 |
| 新增行业 | 阶段二 | 现有趋势 + 新闻 |
| 新增股票 | 阶段四 | 现有行业调研报告 |
| 舆情影响趋势 | 阶段一 | 舆情事件 + 现有趋势 |
| 舆情影响行业 | 阶段二 | 舆情事件 + 现有行业 |
| 舆情影响股票 | 阶段四 | 舆情事件 + 现有股票 |

### 5.4 提案产出流程

```
Agent 执行完成 → 产出 summary.md
        │
        ▼
ProposalGenerator 解析 summary
        │
        ├── 提取趋势提案 → ProposalLimiter 检查上限
        │                     │
        │              未超限 ──→ 写入 proposals + trends 表
        │              超限 ────→ 淘汰最低置信度 → 写入新提案
        │
        ├── 提取行业提案 → 同上流程
        ├── 提取股票提案 → 同上流程
        └── 提取分析报告 → 写入 research_reports 表
```

## 6. 后台任务设计

### 6.1 定时任务调度

使用 APScheduler（轻量，与 FastAPI 集成简单）管理定时任务：

| 任务 | 默认频率 | 可配置 | 触发内容 |
|------|---------|--------|---------|
| 每日新闻存档 | 每日 8:00 | 是 | 每日新闻分析师 Agent |
| 舆情监控 | 每小时 | 是 | 舆情监控分析师 Agent |

### 6.2 舆情监控流程

```
定时触发 → 舆情监控分析师 Agent 执行
    │
    ├── 获取最新新闻/舆情
    ├── 对比用户关注列表（趋势、行业、股票）
    ├── 评估相关性评分
    │
    ├── 低相关性 → 记录到 alert_events，不触发
    └── 高相关性 → 记录到 alert_events
                      │
                      └── 根据 affected_type 决定起始阶段
                              │
                              └── 启动投研运行（部分启动）
                                      │
                                      └── 推送飞书通知
```

## 7. 飞书集成设计

### 7.1 架构

```
飞书开放平台
    │
    │  Webhook (事件订阅)
    ▼
API Server /api/feishu/webhook
    │
    ├── 消息事件 → 转发到 Session 对话系统
    ├── 卡片操作 → 提案采纳/拒绝
    │
    ▼
飞书消息发送 API
    ├── 提案推送（消息卡片）
    └── 对话回复（文本/卡片）
```

### 7.2 提案推送卡片

新提案产生时，构造飞书交互卡片：

```
┌─────────────────────────────────┐
│  📋 新提案：新增趋势"人民币走强"   │
│  类型：趋势 · 置信度：8/10        │
│  摘要：基于XXX数据，判断...        │
├─────────────────────────────────┤
│  [  采纳  ]      [  拒绝  ]      │
└─────────────────────────────────┘
```

用户点击按钮 → 飞书回调 webhook → 系统更新提案状态。

### 7.3 飞书对话

用户在飞书中@机器人发消息 → 飞书推送消息事件 → 系统创建/复用 Session → 执行 Agent → 返回结果消息。

## 8. 前端页面设计

### 8.1 页面路由

在现有路由基础上新增：

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | Dashboard | 总览面板 |
| `/chat` | Chat | 对话模式（复用现有Agent页面） |
| `/trends` | Trends | 趋势管理 + 提案审批 |
| `/industries` | Industries | 行业管理 + 提案审批 |
| `/stocks` | Stocks | 自选股管理 + 提案审批 |
| `/research` | Research | 投研运行列表 + 运行详情 |
| `/agents` | AgentConfig | Agent 配置页面 |
| `/settings` | Settings | 用户偏好 + API Key + 系统设置 |
| `/login` | Login | 登录/注册 |

### 8.2 关键交互

**趋势/行业/股票管理页面**（统一布局）：

```
┌─────────────────────────────────────────┐
│  [全部] [活跃] [待审批] [已拒绝] [已移除]  │  ← 状态筛选
├─────────────────────────────────────────┤
│                                         │
│  ┌─ 📋 待审批 ──────────────────────┐   │
│  │ 新增趋势：人民币走强    置信度 8   │   │  ← proposed 状态
│  │ [采纳] [拒绝] [查看报告 →]        │   │
│  └──────────────────────────────────┘   │
│                                         │
│  ┌─ ✅ 已采纳 ──────────────────────┐   │
│  │ 美元降息预期    长期    置信度 7   │   │  ← adopted 状态
│  │ [更新] [删除] [查看报告 →]        │   │
│  └──────────────────────────────────┘   │
│                                         │
│  [+ 手动添加]                            │  ← 直接创建 adopted
└─────────────────────────────────────────┘
```

**投研运行详情页**：

```
┌─────────────────────────────────────────┐
│  投研运行 #2026-0512-001                │
│  触发：手动 · 状态：运行中 · 耗时：3m22s │
├─────────────────────────────────────────┤
│                                         │
│  ✅ 阶段一：趋势发现      2m10s         │
│     → 产出：2条趋势提案                  │
│                                         │
│  ✅ 阶段二：行业筛选      1m05s         │
│     → 产出：1条行业提案                  │
│                                         │
│  🔄 阶段三：行业调研与选股  运行中...     │
│                                         │
│  ⏳ 阶段四：多维分析                     │
│  ⏳ 阶段五~九：...                       │
│                                         │
└─────────────────────────────────────────┘
```

## 9. 记忆系统设计

### 9.1 两层记忆架构

| 层级 | 存储 | 内容 | 检索方式 |
|------|------|------|---------|
| 结构化记忆 | SQLite (vibe.db) | 趋势、行业、股票事实表 + 投研报告 + 审计日志 | SQL 查询 |
| 非结构化记忆 | ChromaDB | Agent 经验教训、分析洞察、对话要点 | 语义搜索 |

### 9.2 ChromaDB 配置

```
存储路径：~/.vibe-trading/chroma/
底层存储：SQLite（ChromaDB 默认后端）
备份方式：整个目录拷贝
```

### 9.3 记忆读写流程

```
Agent 执行时：
    │
    ├── 读取结构化记忆
    │   └── SELECT * FROM trends WHERE user_id=? AND status IN ('proposed','adopted')
    │   └── SELECT * FROM research_reports WHERE run_id=?
    │
    ├── 读取非结构化记忆（语义搜索）
    │   └── collection.query(query_texts=["新能源行业结论"], where={"user_id": user_id}, n_results=5)
    │
    └── 写入新记忆
        └── 结构化 → INSERT INTO proposals / research_reports
        └── 非结构化 → collection.add(documents=[insight], metadatas=[{user_id, type, agent_id}])
```

### 9.4 非结构化记忆的 metadata 过滤

ChromaDB 支持 metadata 过滤，投研场景按以下维度组织：

```
metadata:
  user_id: 1                    # 用户隔离
  memory_type: insight          # insight / lesson / context / summary
  source_agent: macro_analyst   # 来源 Agent
  related_type: industry        # trend / industry / stock
  related_id: 42                # 关联的事实表记录 ID
```

### 9.5 与现有文件记忆的关系

现有 `~/.vibe-trading/memory/` 文件记忆系统保留不动（单 Agent 跨 session 上下文）。投研系统的 ChromaDB 记忆是新增层，服务于多 Agent 协同场景的结构化/语义化召回。两者并存，互不干扰。

## 10. 安全设计

### 9.1 认证与授权

- JWT Token 认证，Token 有效期 24 小时，支持 Refresh Token
- 所有 API 请求携带 `Authorization: Bearer <token>`
- SSE 连接支持 `?token=` 查询参数

### 9.2 数据隔离

- 所有业务查询强制带 `user_id` 条件，中间件层注入当前用户 ID
- 数据库层面不依赖应用层过滤，关键查询使用参数化 SQL

### 9.3 敏感数据

- API Key 使用 AES-256 加密存储，密钥从环境变量读取
- 前端展示 API Key 时只显示后 4 位
- 密码使用 bcrypt 哈希存储

## 10. 技术选型

| 层面 | 选型 | 说明 |
|------|------|------|
| 后端框架 | FastAPI（现有） | 保持一致 |
| 数据库 | SQLite + FTS5（单文件） | `~/.vibe-trading/vibe.db`，业务数据 + session 搜索统一存储 |
| 定时任务 | APScheduler | 轻量，与 FastAPI 集成简单 |
| 认证 | JWT (PyJWT) | 无状态，适合多端（Web+飞书） |
| 加密 | cryptography (AES-256) | API Key 加密存储 |
| 前端框架 | React 19 + Vite（现有） | 保持一致 |
| 状态管理 | Zustand（现有） | 保持一致 |
| 飞书SDK | lark-oapi | 飞书开放平台官方 SDK |
| 投研编排 | 现有 Swarm 系统 | 扩展而非重写 |
| 向量记忆 | ChromaDB | 语义搜索，底层 SQLite，本地部署 |

## 11. 与现有系统的关系

```
现有系统（保持不变）           新增系统
─────────────────           ──────────
api_server.py ────────────── 扩展新 API 端点
sessions/ ────────────────── 复用对话体系
src/swarm/ ───────────────── 扩展投研 preset + ProposalGenerator
src/tools/ ───────────────── 复用全部 21 个工具
src/skills/ ──────────────── 复用全部 74 个技能
src/providers/ ───────────── 复用 LLM 抽象层
src/session/search.py ────── 复用 SQLite FTS5 模式
frontend/ ────────────────── 扩展新页面和路由
```

核心原则：**扩展现有系统，不重写**。投研引擎复用 Swarm 编排能力，对话复用 Session 体系，前端复用组件库。

## 12. 容器部署设计

### 12.1 数据目录统一

现有系统使用分散的相对路径，投研系统新增后需统一管理。通过环境变量 `DATA_DIR` 控制，默认为 `~/.vibe-trading`（本地开发），容器内为 `/data`。

```
$DATA_DIR/
├── vibe.db                 # SQLite 业务数据库
├── chroma/                 # ChromaDB 向量记忆
├── memory/                 # 现有文件记忆（保留）
├── sessions.db             # 现有 FTS5 搜索索引（保留，后续迁入 vibe.db）
├── runs/                   # 现有 Run 产物（从 agent/runs 迁出）
├── sessions/               # 现有 Session 文件（从 agent/sessions 迁出）
└── uploads/                # 上传文件（从 agent/uploads 迁出）
```

### 12.2 Dockerfile 改造

在现有 Dockerfile 基础上调整：

```
改动点：
1. 新增依赖：chromadb、PyJWT、bcrypt、cryptography、lark-oapi、apscheduler
2. 数据目录：创建 /data，USER vibe 拥有写权限
3. 环境变量：DATA_DIR=/data，ENCRYPTION_KEY（运行时注入）
4. Volume 挂载点：/data
```

构建流程不变：前端 npm build → Python 安装 → FastAPI 启动。

### 12.3 docker-compose 改造

```yaml
services:
  vibe-trading:
    image: ghcr.io/${OWNER}/vibe-trading:${TAG}
    ports:
      - "127.0.0.1:8899:8899"
    environment:
      - DATA_DIR=/data
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}   # 从宿主机 .env 注入
    volumes:
      - vibe-data:/data                    # 单一 volume 覆盖全部持久化数据
    restart: unless-stopped

volumes:
  vibe-data:
```

关键改动：原来分散的 `vibe-runs`、`vibe-sessions` 多个 volume 合并为一个 `vibe-data`，与 `DATA_DIR` 统一对应。

### 12.4 环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `DATA_DIR` | 数据目录路径 | 否（默认 `~/.vibe-trading`） |
| `ENCRYPTION_KEY` | API Key 加密密钥 | 是（生产环境） |
| `JWT_SECRET` | JWT 签名密钥 | 是（生产环境） |

其余配置（LLM Provider、tushare token 等）由用户在 Web 界面配置，存储在数据库中，不再依赖 `.env` 文件。

## 13. CI/CD 设计

### 13.1 流水线总览

```
push/PR ──→ [test & build] ──→ 镜像推送 (SHA tag)
                                      │
main 分支合并后 ──────────────────────→ [deploy UAT] ──→ E2E 测试
                                                                │
手动触发 ─────────────────────────────────────────────────────→ [deploy Prod]
```

### 13.2 Workflow 1：Test & Build

```
触发：push to */pull_request to main
步骤：
  1. Python 3.11 环境
  2. pip install -e ".[dev]"
  3. ruff check agent/ — Lint
  4. pytest — 后端测试
  5. Node 20 环境
  6. npm ci && npm run build — 前端构建检查
  7.（仅 main 分支）Docker build + push to ghcr.io，标签为 commit SHA
```

仅 main 分支触发镜像构建，PR 分支只做检查不推送镜像。

### 13.3 Workflow 2：Deploy UAT & E2E

```
触发：
  - 自动：workflow 1 完成后（main 分支）
  - 手动：workflow_dispatch，可选镜像 tag

参数（workflow_dispatch）：
  - image_tag: 镜像标签（默认 latest）

步骤：
  1. 拉取指定版本镜像
  2. SSH 部署到 UAT 服务器（docker compose up -d）
  3. 等待健康检查通过（/health）
  4. 运行 E2E 测试
  5. 测试通过后通知（可选：飞书/Slack webhook）
  6. 测试失败则回滚到上一版本镜像
```

UAT 环境配置通过 GitHub Environments 管理（secrets: UAT_SSH_KEY、UAT_HOST、UAT_ENCRYPTION_KEY 等）。

### 13.4 Workflow 3：Deploy Prod

```
触发：workflow_dispatch（手动）

参数：
  - image_tag: 镜像标签（必填，如 v1.2.3 或 commit SHA）
  - confirm: 确认部署（type: boolean，必勾选）

步骤：
  1. 校验镜像 tag 存在
  2. SSH 部署到生产服务器
  3. 等待健康检查通过
  4. 创建 GitHub Release（如果 tag 是 v* 格式）
  5. 部署完成后通知
```

生产环境通过 GitHub Environments 配置 **审批保护**（Required Reviewers），手动触发后需指定人员批准才执行。

### 13.5 镜像标签策略

| 触发场景 | 标签 | 示例 |
|---------|------|------|
| main 分支每次合并 | `sha-<短SHA>` | `sha-a3f1b2c` |
| UAT 部署 | 使用上述 SHA tag 或 `latest` | `latest` |
| 生产部署 | 打正式版本 tag | `v1.2.3` |

### 13.6 GitHub Environments 配置

```
UAT:
  - secrets: UAT_SSH_KEY, UAT_HOST, UAT_ENCRYPTION_KEY, UAT_JWT_SECRET
  - 无审批要求

Production:
  - secrets: PROD_SSH_KEY, PROD_HOST, PROD_ENCRYPTION_KEY, PROD_JWT_SECRET
  - Required Reviewers: 指定审批人
  - Wait timer: 5 分钟（给审批人反悔时间）
```

### 13.7 部署与升级

```bash
# UAT/Prod 服务器上的 docker-compose.yml
# image tag 由 CI/CD 自动替换，无需手动改文件

# 升级流程
docker compose pull && docker compose up -d
# volume 数据不丢失，schema 变更由应用启动时自动迁移
```
