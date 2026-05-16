# 阶段 3：事实表管理（趋势 + 行业 + 自选股）

## 1. 概述

**目标**：实现趋势、行业、自选股三张事实表的完整 CRUD，包括后端 API 和前端管理页面，附带 Dashboard 总览页。

**与前后阶段的关系**：依赖阶段 2 的用户认证体系。本阶段产出的三张事实表是阶段 4（提案机制）的基础。

**前置条件**：阶段 2 完成，用户可注册登录。

## 2. 数据模型

### trends 表

```sql
CREATE TABLE trends (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    status      TEXT NOT NULL DEFAULT 'adopted' CHECK(status IN ('proposed','adopted','rejected','removed')),
    title       TEXT NOT NULL,
    level       TEXT CHECK(level IN ('long-term','mid-term','short-term')),
    confidence  INTEGER DEFAULT 5 CHECK(confidence BETWEEN 0 AND 10),
    evidence    TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, title)
);
```

- 状态值：`proposed` | `adopted` | `rejected` | `removed`
- `proposed` 和 `adopted` 为活跃状态
- 活跃趋势判定：`WHERE status IN ('proposed', 'adopted')`
- `level` 枚举：`long-term`（长期）、`mid-term`（中期）、`short-term`（短期）
- `confidence` 范围：0-10，0 表示未评估

### industries 表

```sql
CREATE TABLE industries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    status              TEXT NOT NULL DEFAULT 'adopted' CHECK(status IN ('proposed','adopted','rejected','removed')),
    name                TEXT NOT NULL,
    confidence          INTEGER DEFAULT 5 CHECK(confidence BETWEEN 0 AND 10),
    reason              TEXT,
    research_report     TEXT,
    recommended_stocks  TEXT DEFAULT '[]',
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, name)
);
```

- `recommended_stocks` 为自由文本 JSON 数组，存储推荐股票代码，与 `stocks` 表无外键关联

### stocks 表

```sql
CREATE TABLE stocks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    status          TEXT NOT NULL DEFAULT 'adopted' CHECK(status IN ('proposed','adopted','rejected','removed')),
    name            TEXT NOT NULL,
    code            TEXT NOT NULL,
    confidence      INTEGER DEFAULT 5 CHECK(confidence BETWEEN 0 AND 10),
    industry_name   TEXT,
    position        REAL,
    advice          TEXT,
    target_price    REAL,
    stop_loss       REAL,
    reason          TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, code)
);
```

- `code` 使用 tushare 格式：`600000.SH`（沪市）、`000001.SZ`（深市）、`BTC-USDT`（加密货币）等
- `industry_name` 为行业名称文本，无外键约束，不与 `industries` 表强关联
- `position` 为仓位金额（REAL 类型），如 `50000.0`
- `advice` 为操作建议自由文本（如"买入"、"持有"、"减仓"等）

### updated_at 自动更新触发器

为每张表创建触发器，UPDATE 时自动刷新 `updated_at`：

```sql
CREATE TRIGGER IF NOT EXISTS trg_trends_updated_at
AFTER UPDATE ON trends FOR EACH ROW
BEGIN
    UPDATE trends SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_industries_updated_at
AFTER UPDATE ON industries FOR EACH ROW
BEGIN
    UPDATE industries SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_stocks_updated_at
AFTER UPDATE ON stocks FOR EACH ROW
BEGIN
    UPDATE stocks SET updated_at = datetime('now') WHERE id = NEW.id;
END;
```

### 索引

```sql
CREATE INDEX IF NOT EXISTS idx_trends_user_status ON trends(user_id, status);
CREATE INDEX IF NOT EXISTS idx_industries_user_status ON industries(user_id, status);
CREATE INDEX IF NOT EXISTS idx_stocks_user_status ON stocks(user_id, status);
```

使用 `(user_id, status)` 复合索引，覆盖典型查询 `WHERE user_id = ? AND status IN (...)`。

## 3. API 设计

三张表共享统一的 API 模式。列表接口暂不分页，全量返回数组。

### 3.1 趋势管理

```
GET    /api/trends                     列表（?status=active|proposed|adopted|rejected|removed）
GET    /api/trends/{id}                详情
POST   /api/trends                     新增（手动添加，直接 adopted）
PUT    /api/trends/{id}                更新
DELETE /api/trends/{id}                删除（状态设为 removed）
```

`active` 是虚拟过滤：`WHERE status IN ('proposed', 'adopted')`

### 3.2 行业管理

```
GET    /api/industries                 列表（?status=）
GET    /api/industries/{id}            详情
POST   /api/industries                 新增
PUT    /api/industries/{id}            更新
DELETE /api/industries/{id}            删除
```

### 3.3 自选股管理

```
GET    /api/stocks                     列表（?status=）
GET    /api/stocks/{id}                详情
POST   /api/stocks                     新增
PUT    /api/stocks/{id}                更新
DELETE /api/stocks/{id}                删除
```

### 3.4 Dashboard

```
GET    /api/dashboard                  总览数据
响应：{
    "trends": {"active": 5, "proposed": 2},
    "industries": {"active": 3, "proposed": 1},
    "stocks": {"active": 8, "proposed": 3},
    "latest_runs": [...]
}
```

`latest_runs` 复用现有 runs 系统数据，展示用户最近的投研运行记录。

### 3.5 API 响应格式

- **列表**：直接返回数组 `[{...}, {...}]`
- **详情**：返回单个对象 `{...}`
- **创建**：返回 201 + 创建的对象
- **更新**：返回 200 + 更新后的对象
- **删除**：返回 204 No Content
- **错误**：返回 `{"detail": "error message"}`

## 4. 业务逻辑

### 4.1 手动添加

用户手动添加的趋势/行业/股票直接为 `adopted` 状态。暂时不触发自动投研（阶段 6 实现）。

### 4.2 删除

DELETE 操作将状态设为 `removed`，不物理删除。保留历史记录用于审计。

### 4.3 列表过滤

- 无 status 参数：返回所有非 removed 记录
- `status=active`：返回 proposed + adopted
- `status=proposed`、`status=adopted`、`status=rejected`、`status=removed`：精确匹配

### 4.4 数据隔离

所有查询自动带 `WHERE user_id = ?`，通过 JWT 中间件注入。

### 4.5 输入校验

- `confidence`：0-10 整数，超出范围返回 422
- `level`：仅允许 `long-term`、`mid-term`、`short-term`，其他值返回 422
- `code`：非空字符串，符合 tushare 格式（前端展示时做格式说明）
- `title`/`name`：非空，长度上限 200
- `target_price`/`stop_loss`/`position`：正数校验

## 5. 数据库迁移

本阶段新增迁移版本 3，集成到现有 `_MIGRATIONS` 机制（`agent/src/db/database.py`）：

- 版本 3：创建 trends、industries、stocks 三张表 + updated_at 触发器 + 复合索引

## 6. 前端设计

### 6.1 统一布局（三个管理页面共用）

```
┌─────────────────────────────────────────────┐
│  [All] [Active] [Proposed] [Rejected] [Removed] │  ← Status filter tabs
├─────────────────────────────────────────────┤
│                                             │
│  ┌─ Trend/Industry/Stock card ────────────┐ │
│  │ Title/Name         Confidence 8/10     │ │
│  │ Level/Industry     Status badge        │ │
│  │ Evidence/Reason summary                │ │
│  │ [Edit] [Delete]                        │ │
│  └────────────────────────────────────────┘ │
│                                             │
│  [+ Add manually]                           │
└─────────────────────────────────────────────┘
```

### 6.2 趋势管理页（`/trends`）

卡片字段：标题、级别（Long-term / Mid-term / Short-term 标签）、置信度、依据摘要

### 6.3 行业管理页（`/industries`）

卡片字段：行业名称、置信度、入选理由摘要、推荐股票数量

### 6.4 自选股管理页（`/stocks`）

卡片字段：股票名称+代码、所属行业、置信度、操作建议、目标价位、止损位、仓位金额

### 6.5 Dashboard（`/`）

```
┌───────────────────────────────────────────────┐
│  ┌───────────┐  ┌───────────┐  ┌───────────┐ │
│  │ Active     │  │ Active     │  │ Active     │ │
│  │ Trends: 5 │  │ Industries │  │ Stocks: 8  │ │
│  └───────────┘  └───────────┘  └───────────┘ │
│                                               │
│  ┌───────────┐  ┌───────────────────────────┐ │
│  │ Proposed  │  │ Recent Runs               │ │
│  │    6      │  │   ...                     │ │
│  └───────────┘  └───────────────────────────┘ │
└───────────────────────────────────────────────┘
```

## 7. 验收标准

- [ ] 可通过 API 对三类事实数据进行完整 CRUD
- [ ] 列表支持按状态过滤，`active` 返回 proposed + adopted
- [ ] 删除操作设状态为 removed，数据保留
- [ ] 不同用户数据完全隔离
- [ ] 输入校验生效（confidence 范围、level 枚举、字段非空等）
- [ ] updated_at 通过触发器自动更新
- [ ] 前端三个管理页面可正常使用，含状态筛选和手动添加
- [ ] Dashboard 展示正确的汇总数据
