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
- **`rejected` 状态在本阶段不会产生**，预留给阶段 4 提案拒绝场景

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
- `research_report` 为行业研究报告文本，前端详情面板中展示

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
PUT    /api/trends/{id}                更新（支持 status 字段，用于 Undo 恢复）
DELETE /api/trends/{id}                删除（状态设为 removed）
```

`active` 是虚拟过滤：`WHERE status IN ('proposed', 'adopted')`

### 3.2 行业管理

```
GET    /api/industries                 列表（?status=）
GET    /api/industries/{id}            详情
POST   /api/industries                 新增
PUT    /api/industries/{id}            更新（支持 status 字段）
DELETE /api/industries/{id}            删除
```

### 3.3 自选股管理

```
GET    /api/stocks                     列表（?status=）
GET    /api/stocks/{id}                详情
POST   /api/stocks                     新增
PUT    /api/stocks/{id}                更新（支持 status 字段）
DELETE /api/stocks/{id}                删除
```

### 3.4 Dashboard

```
GET    /api/dashboard                  总览数据
响应：{
    "trends": {"active": 5, "proposed": 2},
    "industries": {"active": 3, "proposed": 1},
    "stocks": {"active": 8, "proposed": 3},
    "recently_updated": [
        {"type": "trend", "id": 1, "title": "...", "confidence": 8, "updated_at": "..."},
        {"type": "stock", "id": 3, "title": "688981.SH", "confidence": 6, "updated_at": "..."}
    ],
    "latest_runs": [...]
}
```

- `recently_updated`：合并三张表按 updated_at 降序取前 5 条，每条含 `type`（trend/industry/stock）用于前端渲染图标
- `latest_runs` 复用现有 runs 系统数据

### 3.5 API 响应格式

- **列表**：直接返回数组 `[{...}, {...}]`
- **详情**：返回单个对象 `{...}`。industries 详情额外包含 `recommended_count` 虚拟字段（解析 recommended_stocks JSON 数组的 length）
- **创建**：返回 201 + 创建的对象
- **更新**：返回 200 + 更新后的对象。`status` 字段允许通过 PUT 修改（用于 Undo 恢复删除）
- **删除**：返回 204 No Content
- **错误**：返回 `{"detail": "error message"}`

## 4. 业务逻辑

### 4.1 手动添加

用户手动添加的趋势/行业/股票直接为 `adopted` 状态。暂时不触发自动投研（阶段 6 实现）。

### 4.2 删除与恢复

- DELETE 操作将状态设为 `removed`，不物理删除。保留历史记录用于审计
- 前端 Undo 通过 `PUT /api/{resource}/{id}` 传 `{status: "adopted"}` 恢复
- PUT 端点允许修改 `status` 字段，支持上述恢复场景

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
- `target_price`/`stop_loss`/`position`：非负数校验

## 5. 数据库迁移

本阶段新增迁移版本 3，集成到现有 `_MIGRATIONS` 机制（`agent/src/db/database.py`）：

- 版本 3：创建 trends、industries、stocks 三张表 + updated_at 触发器 + 复合索引

## 6. 前端设计

### 6.0 设计规范

**风格定位**：紧凑型 Master-Detail 布局，左侧数据列表 + 右侧详情面板。追求高信息密度与操作效率。

**技术栈**（与现有前端一致）：
- Tailwind CSS、lucide-react 图标、sonner toast、英文 UI 文案
- 暗色模式优先（已有 dark mode 支持）

**核心交互原则**：
- 状态变更仅通过删除（→ removed）操作，其他状态变更由阶段 4 提案机制完成
- 列表页不做弹窗，所有操作在右侧面板内完成
- 流畅过渡动画，选中项高亮，面板展开/收起有 slide 效果
- **Inline editing**：详情面板直接点击字段值即可编辑，无需模式切换
- **Hover 操作**：列表行 hover 显示快捷操作图标，减少操作步数

### 6.1 Master-Detail 页面结构（三个管理页面共用）

```
┌──────── 40% ────────┬────────── 60% ──────────────┐
│ 🔍 Search...        │                               │
│ [All][Active][Prop]. │  ┌─ Detail Panel ───────────┐│
│                      │  │                           ││
│ Title  Level C S  ▲  │  │  (inline editing)        ││
│ ────── ───── ── ── ──│  │                           ││
│ AI rot 🔵LT 🟢8 ● ≡  │  │  Title (editable)        ││
│ Semi r 🔴ST 🟡6 ● ≡← │  │  Level: [标签]           ││
│ Rate c 🟠MT 🟢7 ● ≡  │  │  Confidence: █8█         ││
│                      │  │  Evidence:               ││
│                      │  │  [可编辑文本]            ││
│                      │  │                           ││
│                      │  │  Created: 2026-05-14     ││
│               [+ Add]│  │  [Delete]                ││
│                      │  └───────────────────────────┘│
└──────────────────────┴──────────────────────────────┘
图标说明: ≡ = hover时显示的操作图标(编辑/删除)
          ← = 当前选中行(左侧2px竖线高亮)
```

**左侧面板**（40%，列表区）：

**搜索栏**（左侧顶部）：
- 搜索框：debounce 300ms，匹配标题/名称/代码/理由

**状态 Pill tabs**（搜索栏下方）：
- All | Active | Proposed | Rejected | Removed

**Compact List**（列表主体）：
- 每行一个条目，高度固定（~40px），紧凑排列
- 可点击的列头排序（升序/降序切换，箭头指示方向）
- 选中行左侧有 2px primary 色竖线高亮
- 行 hover 有背景色变化 + 显示操作图标（编辑/删除）
- **Status 列**：固定 30px，显示状态圆点（adopted=绿, proposed=蓝, rejected=灰, removed=暗灰虚线圆）
- 底部固定 [+ Add] 按钮
- 选中状态通过 URL hash 记忆（如 `/trends#3`），页面刷新后恢复

**右侧面板**（60%，详情区，三种状态）：
1. **收起态**：未选中任何条目时，面板收起为窄条，显示 "Select an item or + Add"
2. **详情态**：选中条目后展开，字段分组展示，**支持 inline editing**（点击字段值即变为输入控件，失焦或 Enter 自动 Save）
3. **添加态**：点击 [+ Add] 后面板展开为空白表单，提交后自动选中新条目

**Inline Editing 规则**：
- 文本字段：点击后变为文本输入框，失焦自动 Save
- 枚举字段（Level）：点击后变为下拉选择
- 数字字段（Confidence）：点击后变为滑块
- 多行文本（Evidence/Reason）：点击后展开为多行编辑区
- 每次编辑后列表行数据同步更新，无需手动刷新

### 6.2 趋势管理页（`/trends`）

**列表列**：
| 列 | 宽度 | 内容 |
|----|------|------|
| Title | flex | 标题文本，溢出省略 |
| Level | 80px | 标签：long-term=蓝 / mid-term=紫 / short-term=橙（暖色=短，冷色=长） |
| Conf | 40px | 数字 + 色点（0-3红, 4-6黄, 7-10绿） |
| Status | 30px | 状态圆点（adopted=绿, proposed=蓝, rejected=灰, removed=暗灰） |
| Updated | 70px | 相对时间（2h ago），可点击列头排序 |

**默认排序**：Updated 降序

**右侧详情面板字段**（分组展示）：

**概览组**：
| 字段 | 展示 | Inline edit |
|------|------|------------|
| Title | 大号文本 | 文本输入 |
| Level | 彩色标签 | 下拉选择 |
| Confidence | 色点 + 数字 | 滑块 (0-10) |

**分析组**：
| 字段 | 展示 | Inline edit |
|------|------|------------|
| Evidence | 完整文本（可滚动） | 多行文本 |

**元数据组**：
| 字段 | 展示 |
|------|------|
| Status | 状态标签 |
| Created / Updated | 时间戳 |

### 6.3 行业管理页（`/industries`）

**列表列**：
| 列 | 宽度 | 内容 |
|----|------|------|
| Name | flex | 行业名称 |
| Conf | 40px | 数字 + 色点 |
| Stocks | 50px | 推荐股票数 badge |
| Status | 30px | 状态圆点 |
| Updated | 70px | 相对时间 |

**右侧详情面板字段**（分组展示）：

**概览组**：
| 字段 | 展示 | Inline edit |
|------|------|------------|
| Name | 大号文本 | 文本输入 |
| Confidence | 色点 + 数字 | 滑块 (0-10) |

**分析组**：
| 字段 | 展示 | Inline edit |
|------|------|------------|
| Reason | 完整文本 | 多行文本 |
| Research Report | 完整文本（可折叠） | 多行文本 |
| Recommended Stocks | Tag 列表 | Tag 输入（回车添加） |

**元数据组**：
| 字段 | 展示 |
|------|------|
| Status | 状态标签 |
| Created / Updated | 时间戳 |

### 6.4 自选股管理页（`/stocks`）

**列表列**：
| 列 | 宽度 | 内容 |
|----|------|------|
| Name | flex | 股票名称 + 代码 |
| Industry | 90px | 行业名（链接样式，点击跳转 `/industries?search=<name>`） |
| Advice | 50px | 颜色标签（匹配规则见下） |
| Conf | 40px | 数字 + 色点 |
| Price | 100px | T:¥98 / S:¥72 紧凑一行 |
| Status | 30px | 状态圆点 |
| Updated | 70px | 相对时间 |

**Advice 颜色匹配规则**：`advice.toLowerCase()` 精确匹配预设值，不匹配时用默认灰色。
- `buy` → 绿, `sell` → 红, `hold` → 灰, 其他 → 默认

**右侧详情面板字段**（分组展示）：

**基本信息组**：
| 字段 | 展示 | Inline edit |
|------|------|------------|
| Name | 大号文本 | 文本输入 |
| Code | 代码文本（副标题） | 文本输入（placeholder: 600000.SH） |
| Industry Name | 链接文本 | 带自动补全的文本输入（从已有 industries 建议） |

**交易参数组**：
| 字段 | 展示 | Inline edit |
|------|------|------------|
| Advice | 颜色标签 | 文本输入 |
| Target Price | 数字 | 数字输入 |
| Stop Loss | 数字 | 数字输入 |
| Position | 金额 | 数字输入 |

**分析组**：
| 字段 | 展示 | Inline edit |
|------|------|------------|
| Confidence | 色点 + 数字 | 滑块 (0-10) |
| Reason | 完整文本 | 多行文本 |

**元数据组**：
| 字段 | 展示 |
|------|------|
| Status | 状态标签 |
| Created / Updated | 时间戳 |

### 6.5 Dashboard（`/`）

替换现有 Home 静态页面为动态 Dashboard，采用 Bento Grid 布局：

```
┌──────────────────────────────────────────────────────────┐
│  Dashboard                                               │
│                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ Trends   │ │Industries│ │ Stocks   │ │ Pending  │   │
│  │    5     │ │    3     │ │    8     │ │    6     │   │
│  │ +2 prop  │ │ +1 prop  │ │ +3 prop  │ │ proposals│   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│    → /trends?status=active  (深链接，带 status 参数)     │
│                                                          │
│  ┌─────────────────────────┐ ┌────────────────────────┐  │
│  │ Recently Updated        │ │ Recent Runs            │  │
│  │                         │ │                        │  │
│  │ 📈 AI infra rot.  8 2h │ │ run-abc  strategy  +5% │  │
│  │ 💹 688981.SH     6 1d  │ │ run-def  backtest -2% │  │
│  │ 🏭 Semi          7 2d  │ │ run-ghi  screen   +8% │  │
│  │ ...              [All] │ │ ...              [All] │  │
│  └─────────────────────────┘ └────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**统计卡片行**（4 列等宽）：
- Active Trends / Active Industries / Active Stocks / Pending Proposals
- 数字大号（text-3xl font-bold），"+X proposed" 用 warning 色
- **深链接**：点击卡片跳转并携带 status 参数，如 `/trends?status=active`
- Pending Proposals 卡片预留位置，Phase 4 实现

**Recently Updated**（占左 60%）：
- 数据来源：Dashboard API 的 `recently_updated` 字段
- 每行：类型图标（📈趋势/🏭行业/💹股票）+ 标题 + 置信度 + 相对时间
- 点击行跳转到对应管理页并选中该条目（如 `/trends#5`）
- [All] 跳转到 `/trends?sort=updated`

**Recent Runs**（占右 40%）：
- 复用现有 runs 数据，表格展示前 5 条
- [All] 跳转到 Agent 页

**分析图表**：延后到阶段 6 投研引擎完成后实现。

### 6.6 交互规范

| 交互 | 方式 |
|------|------|
| **选中条目** | 点击列表行 → 右侧面板展开显示详情，行高亮。选中状态记入 URL hash（如 `/trends#3`） |
| **Inline edit** | 在详情面板中，点击任意字段值 → 变为编辑控件 → 失焦/Enter 自动 Save → 列表同步更新 |
| **添加** | 点击 [+ Add] → 右侧面板展开为空白表单，提交后自动选中新条目并滚动到对应位置 |
| **快捷删除** | 列表行 hover 显示删除图标 → 点击直接标记 removed → toast "Removed" + Undo 按钮（5 秒内可撤销） |
| **面板内删除** | 详情面板底部 [Delete] → 同上效果 |
| **Undo 机制** | toast 中 Undo 按钮调用 `PUT /api/{resource}/{id}` 传 `{status: "adopted"}` 恢复 |
| **排序** | 点击列头 → 切换升序/降序，箭头指示方向 |
| **搜索** | 顶部全宽搜索框，debounce 300ms 实时过滤 |
| **状态筛选** | Pill tabs 切换，筛选 + 搜索可叠加 |
| **空状态** | 列表区显示图示 + "Add your first X" + CTA 按钮 |
| **面板动画** | 面板收起/展开 slide 过渡，字段编辑 fade 过渡 |
| **页面返回** | 从其他页面返回时恢复上次选中的条目（URL hash） |

### 6.7 导航更新

侧边栏 `Layout.tsx` 的 NAV 数组更新：

```
NAV = [
  { to: "/",           icon: LayoutDashboard, key: "dashboard" },
  { to: "/trends",     icon: TrendingUp,      key: "trends" },
  { to: "/industries", icon: Factory,         key: "industries" },
  { to: "/stocks",     icon: CandlestickChart, key: "stocks" },
  { to: "/agent",      icon: Bot,             key: "agent" },
  { to: "/tools",      icon: Wrench,          key: "tools" },
  { to: "/settings",   icon: Settings,        key: "settings" },
];
```

### 6.8 Level 颜色语义

Level 标签颜色使用有语义的冷暖色映射：
- `long-term` → 蓝色（冷色=长期，稳定感）
- `mid-term` → 紫色（中性色调）
- `short-term` → 橙色（暖色=短期，紧迫感）

## 7. 验收标准

- [ ] 可通过 API 对三类事实数据进行完整 CRUD
- [ ] 列表支持按状态过滤，`active` 返回 proposed + adopted
- [ ] 列表支持列头点击排序（升序/降序）
- [ ] 列表支持搜索框实时过滤
- [ ] 列表每行显示 Status 圆点，一眼区分状态
- [ ] 列表行 hover 显示快捷操作图标（编辑/删除）
- [ ] 删除操作设状态为 removed，toast 提供 Undo 按钮（调用 PUT 恢复）
- [ ] 详情面板支持 inline editing（点击字段即编辑，失焦自动保存）
- [ ] 不同用户数据完全隔离
- [ ] 输入校验生效（confidence 范围、level 枚举、字段非空等）
- [ ] updated_at 通过触发器自动更新
- [ ] 前端三个管理页面采用 Master-Detail 布局（左 40% 列表 + 右 60% 详情）
- [ ] 未选中条目时右侧面板收起为窄条
- [ ] Dashboard 统计卡片点击跳转携带 status 参数
- [ ] Dashboard Recently Updated 区展示合并数据
- [ ] 空状态显示引导文案和 CTA 按钮
- [ ] 选中状态通过 URL hash 记忆，页面刷新后恢复
