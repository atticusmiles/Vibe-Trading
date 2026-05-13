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
    status      TEXT NOT NULL DEFAULT 'adopted',
    title       TEXT NOT NULL,
    level       TEXT,
    confidence  INTEGER DEFAULT 5,
    evidence    TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, title)
);
```

状态值：`proposed` | `adopted` | `rejected` | `removed`
- `proposed` 和 `adopted` 为活跃状态
- 活跃趋势判定：`WHERE status IN ('proposed', 'adopted')`

### industries 表

```sql
CREATE TABLE industries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    status              TEXT NOT NULL DEFAULT 'adopted',
    name                TEXT NOT NULL,
    confidence          INTEGER DEFAULT 5,
    reason              TEXT,
    research_report     TEXT,
    recommended_stocks  TEXT DEFAULT '[]',
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, name)
);
```

### stocks 表

```sql
CREATE TABLE stocks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    status          TEXT NOT NULL DEFAULT 'adopted',
    name            TEXT NOT NULL,
    code            TEXT NOT NULL,
    confidence      INTEGER DEFAULT 5,
    industry_id     INTEGER REFERENCES industries(id),
    position        TEXT,
    advice          TEXT,
    target_price    REAL,
    stop_loss       REAL,
    reason          TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, code)
);
```

## 3. API 设计

三张表共享统一的 API 模式：

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

## 5. 前端设计

### 5.1 统一布局（三个管理页面共用）

```
┌─────────────────────────────────────────────┐
│  [全部] [活跃] [待审批] [已拒绝] [已移除]    │  ← 状态筛选 Tab
├─────────────────────────────────────────────┤
│                                             │
│  ┌─ 趋势/行业/股票卡片 ──────────────────┐  │
│  │ 标题/名称          置信度 8/10         │  │
│  │ 级别/所属行业      状态标签            │  │
│  │ 依据/理由摘要                          │  │
│  │ [编辑] [删除]                          │  │
│  └────────────────────────────────────────┘  │
│                                             │
│  [+ 手动添加]                                │
└─────────────────────────────────────────────┘
```

### 5.2 趋势管理页（`/trends`）

卡片字段：标题、级别（长/中/短期标签）、置信度、依据摘要

### 5.3 行业管理页（`/industries`）

卡片字段：行业名称、置信度、入选理由摘要、推荐股票数量

### 5.4 自选股管理页（`/stocks`）

卡片字段：股票名称+代码、所属行业、置信度、操作建议（买入/卖出/持有标签）、目标价位、止损位

### 5.5 Dashboard（`/`）

```
┌───────────────────────────────────────────────┐
│  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │ 活跃趋势 │  │ 活跃行业 │  │ 活跃自选股│      │
│  │    5     │  │    3     │  │    8     │       │
│  └─────────┘  └─────────┘  └─────────┘       │
│                                               │
│  ┌─────────┐  ┌─────────┐                    │
│  │ 待审批   │  │ 最近投研 │                    │
│  │   6     │  │   ...   │                    │
│  └─────────┘  └─────────┘                    │
└───────────────────────────────────────────────┘
```

## 6. 验收标准

- [ ] 可通过 API 对三类事实数据进行完整 CRUD
- [ ] 列表支持按状态过滤，`active` 返回 proposed + adopted
- [ ] 删除操作设状态为 removed，数据保留
- [ ] 不同用户数据完全隔离
- [ ] 前端三个管理页面可正常使用，含状态筛选和手动添加
- [ ] Dashboard 展示正确的汇总数据
