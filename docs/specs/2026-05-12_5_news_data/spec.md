# 阶段 5：每日新闻存档与数据源

## 1. 概述

**目标**：建立 APScheduler 定时任务框架，实现每日新闻自动存档，同时搭建数据源适配层，为后续投研引擎提供数据基础。

**与前后阶段的关系**：依赖阶段 2 的用户体系和阶段 4 的提案机制（舆情触发的投研会产出提案）。本阶段产出的数据源适配层和新闻简报是阶段 6（投研引擎）的数据输入。

**前置条件**：阶段 2 完成，LLM 和数据源配置通过全局环境变量管理。

## 2. 数据模型

### news_digests 表

```sql
CREATE TABLE news_digests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    digest_date TEXT NOT NULL,            -- YYYY-MM-DD
    content     TEXT NOT NULL,            -- 结构化新闻简报（Markdown）
    summary     TEXT,                     -- 一句话摘要
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, digest_date)
);
```

## 3. 数据源适配层

### 3.1 设计

统一的数据源接口，支持降级回退：

```python
class DataSource(Protocol):
    async def get_market_data(self, code: str, start: str, end: str) -> pd.DataFrame: ...
    async def search_news(self, query: str, limit: int = 20) -> list[dict]: ...
```

### 3.2 数据源优先级

| 数据类型 | 主数据源 | 备用数据源 |
|---------|---------|-----------|
| A 股行情 | tushare（需 token） | akshare（免费） |
| A 股财务 | tushare | akshare |
| 宏观数据 | akshare | — |
| 新闻搜索 | searxng（需配置地址） | — |

优先使用主数据源，失败时自动降级到备用数据源。tushare token 通过环境变量 `TUSHARE_TOKEN` 配置，未配置时直接使用 akshare。

### 3.3 数据源环境变量配置

- `TUSHARE_TOKEN`：tushare token（可选，未配置时使用 akshare 备用）
- 未配置的自动跳过，使用备用数据源

## 4. 定时任务

### 4.1 APScheduler 集成

- 使用 AsyncIOScheduler，绑定 FastAPI 的 lifespan 事件
- 调度信息存储在 `vibe.db` 中（避免内存丢失）
- 每个用户独立的定时任务实例（使用各自的 API Key 和数据源配置）

### 4.2 每日新闻存档任务

- **触发时间**：用户配置 `settings.news_archive_time`（默认 `08:00`）
- **执行逻辑**：
  1. 调用每日新闻分析师 Agent（单 Agent，非投研工作流）
  2. Agent 通过 searxng 搜索前一日财经新闻
  3. Agent 产出结构化新闻简报（Markdown 格式）
  4. 存入 news_digests 表
- **失败处理**：记录错误日志，不重试，等下一个周期
- **输出格式**：包含新闻标题、摘要、影响评估、相关行业/股票

## 5. API 设计

```
GET    /api/news/digests                   新闻简报列表（?date=YYYY-MM-DD）
GET    /api/news/digests/{id}              简报详情
GET    /api/news/digests/latest             最新一期简报
POST   /api/news/digests/trigger           手动触发新闻存档（立即执行一次）
```

## 6. 前端设计

### 6.1 新闻简报页面（`/news`）

```
┌───────────────────────────────────────────────┐
│  新闻简报                                      │
│                                               │
│  ┌─ 2026-05-12 ────────────────────────────┐  │
│  │ [最新] 摘要：美联储释放降息信号，A 股... │  │
│  │ 点击展开详情                             │  │
│  └──────────────────────────────────────────┘  │
│                                               │
│  ┌─ 2026-05-11 ────────────────────────────┐  │
│  │ 摘要：新能源板块领涨，科技股...          │  │
│  └──────────────────────────────────────────┘  │
│                                               │
│  [手动触发存档]                                │
└───────────────────────────────────────────────┘
```

## 7. 验收标准

- [ ] APScheduler 正确集成到 FastAPI 生命周期
- [ ] 每日定时触发新闻存档任务
- [ ] 新闻简报存入 news_digests 表，按用户隔离
- [ ] 数据源适配层支持 tushare / akshare / searxng，降级回退正常
- [ ] 用户未配置 tushare token 时自动使用 akshare
- [ ] 可通过 API 查询历史新闻简报
- [ ] 可手动触发新闻存档
- [ ] 前端新闻简报页面可用
