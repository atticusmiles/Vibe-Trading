# 阶段 4：提案机制

## 1. 概述

**目标**：在事实表基础上实现提案（Proposal）机制，支持 AI 或用户产生趋势/行业/股票的变更提案，用户审批后更新事实表状态。

**与前后阶段的关系**：依赖阶段 3 的事实表。本阶段是阶段 6（投研引擎）产出提案的接收端，也用于飞书审批（阶段 8）。

**前置条件**：阶段 3 完成，事实表 CRUD 可用。

## 2. 数据模型

### proposals 表

```sql
CREATE TABLE proposals (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id),
    target_type       TEXT NOT NULL,          -- trend / industry / stock
    target_id         INTEGER NOT NULL,       -- 事实表记录ID（create 时为新插入记录的 ID）
    action            TEXT NOT NULL,           -- create / update / delete
    status            TEXT NOT NULL DEFAULT 'pending',
    title             TEXT NOT NULL,
    summary           TEXT,
    confidence        INTEGER DEFAULT 5,       -- 0~10
    payload           TEXT NOT NULL,           -- JSON，目标字段值
    original_payload  TEXT,                    -- JSON，仅 update 类型，记录提案创建时的事实表快照
    run_id            TEXT,                    -- 关联的投研运行ID
    source_agent      TEXT,                    -- 产出Agent
    created_at        TEXT DEFAULT (datetime('now')),
    reviewed_at       TEXT
);

CREATE INDEX idx_proposals_user_status ON proposals(user_id, status);
CREATE INDEX idx_proposals_target ON proposals(user_id, target_type, target_id);

-- 同一目标只允许一条 pending 提案（create/update/delete 均适用）
CREATE UNIQUE INDEX idx_proposals_pending_target
    ON proposals(user_id, target_type, target_id)
    WHERE status = 'pending';
```

### audit_logs 表

```sql
CREATE TABLE audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    action      TEXT NOT NULL,           -- proposal_created / proposal_adopted / proposal_rejected / proposal_evicted
    target_type TEXT,                    -- trend / industry / stock
    target_id   INTEGER,
    details     TEXT,                    -- JSON
    actor_type  TEXT NOT NULL,           -- user / agent
    actor_id    TEXT NOT NULL,           -- "user:{id}" 或 "agent:{name}"
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_audit_user ON audit_logs(user_id, created_at);
```

## 3. API 设计

```
GET    /api/proposals                      列表（?type=&status=&target_id=&page=1&per_page=20）
GET    /api/proposals/{id}                 详情
POST   /api/proposals                      创建提案（Agent 或系统内部调用）
POST   /api/proposals/{id}/adopt           采纳提案
POST   /api/proposals/{id}/reject          拒绝提案
POST   /api/proposals/{id}/cancel          取消提案（创建者主动撤回）
```

### 权限

- `POST /api/proposals`：复用用户 JWT（Agent 运行在用户会话内，继承用户身份）。`actor_type=agent`，`actor_id="agent:{source_agent}"`。
- 审批/取消操作：`actor_type=user`，`actor_id="user:{user_id}"`。

## 4. 业务逻辑

### 4.1 提案创建

创建提案时需指定 `target_type`、`action`、`payload`。

**action=create**：先插事实表，再建提案。
- 在事实表新增一条 `status=proposed` 的记录
- 提案的 `target_id` 设为该记录 ID
- 前端列表天然显示（Phase 3 已 filter `proposed`）
- reject 时事实表 `proposed → rejected`
- adopt 时事实表 `proposed → adopted`

**action=update / action=delete**：不碰事实表，adopt 时才落地。

**action=update**：
- `target_id` 指向事实表已有记录
- `original_payload` 保存事实表当前字段值快照（用于前端展示新旧对比）
- 事实表不做任何操作
- 同一 target 已有 pending 提案时：
  - 新提案置信度 **高于** 现有提案：自动撤回现有提案（`rejected`），插入新提案
  - 新提案置信度 **不高于** 现有提案：返回 409 冲突
  - 撤回的旧提案写入审计日志（`action=proposal_evicted`）

**action=delete**：
- `target_id` 指向事实表已有记录
- 事实表不做任何操作
- 同一 target 不允许第二条 pending 的 update/delete 提案

### 4.2 提案审批

**采纳（adopt）**：
- 提案状态变为 `adopted`
- 根据 action 类型落地事实表变更：
  - `create`：事实表记录 `proposed → adopted`
  - `update`：将 payload 中的值写入事实表记录，状态设为 `adopted`
  - `delete`：事实表记录状态设为 `removed`
- 记录审计日志

**拒绝（reject）**：
- 提案状态变为 `rejected`
- 根据 action 类型处理事实表：
  - `create`：事实表记录 `proposed → rejected`
  - `update`/`delete`：事实表不做任何操作
- 记录审计日志

**取消（cancel）**：
- 仅 `pending` 状态可取消
- 提案状态变为 `rejected`（与 reject 共用最终状态，审计日志区分 action）
- 根据 action 类型处理事实表：
  - `create`：事实表记录 `proposed → rejected`
  - `update`/`delete`：事实表不做任何操作
- 记录审计日志

### 4.3 提案淘汰

两种淘汰场景，统一处理：

**场景 A — 同目标替换（update/delete）**：
- 同一 `(target_type, target_id)` 已有 pending 提案，新提案置信度更高时自动替换
- 被替换提案：`rejected`，审计日志 `action=proposal_evicted`，details 记录替换原因和被替换提案 ID
- 置信度不高于现有提案时返回 409

**场景 B — create 数量淘汰**：
- 仅限制 `action=create` 类型的 `pending` 提案数量
- 默认上限 10（硬编码常量 `DEFAULT_PROPOSAL_LIMIT = 10`，后续阶段 7 接入 settings）
- 超过上限时，自动撤回当前置信度最低的 `pending` `create` 提案
  - 多条同置信度时，按 `created_at ASC` 取最早的一条
- 撤回操作：提案状态 → `rejected`，事实表 `proposed → rejected`
- 写入审计日志（`action=proposal_evicted`）

**淘汰通用规则**：
- 被淘汰的 create 提案对应的事实表 `proposed` 记录变为 `rejected`
- 被淘汰的 update/delete 提案不影响事实表
- 所有淘汰写入审计日志

### 4.4 提案列表过滤

- `?type=trend`：按 target_type 过滤
- `?status=pending`：按状态过滤
- `?target_id=42`：查看某条事实表记录关联的所有提案
- `?page=1&per_page=20`：分页，默认每页 20 条
- 无参数：返回所有提案，按创建时间倒序

## 5. 前端设计

### 5.1 管理页面 — 列表内嵌提案标记 + 详情面板审批

趋势/行业/股票管理页面加载时，额外请求 `GET /api/proposals?type={type}&status=pending`，按 `target_id` 与事实表列表交叉匹配，标记有待审批提案的条目：

```
┌─────────────────────────────────────────┐
│  [搜索...]                    [筛选 ▼]  │
│─────────────────────────────────────────│
│  ● 人民币走强                 长期  ●8  │  ← 正常条目
│  ⚠ 美元降息预期          中期  ●7  [审] │  ← 有 pending update 提案，高亮 + 审批按钮
│  ● AI 基础设施轮动           短期  ●6  │  ← 正常条目
│  ⚠ 茅台                 买入  ●9  [审] │  ← 有 pending update 提案
│  ⚠ 【新】新能源补贴政策    长期  ●5  [审] │  ← proposed + pending create 提案
└─────────────────────────────────────────┘
```

- 前端用 `Map<number, ProposalItem>` 按 target_id 建立 pending 提案索引
- 列表行中 `item.status === 'proposed'` 或 proposals 索引中命中 `item.id` → 加 ⚠ 图标 + `bg-warning/5` 背景高亮 + 右侧"审批"按钮
- 点击"审批"按钮 → 打开提案详情弹窗
- 点击行本身 → 正常显示事实表记录详情
- 采纳/拒绝后重新请求 proposals 刷新索引

### 5.2 可折叠待审批汇总（可选）

页面顶部可折叠汇总区块（与 5.1 互补）：

```
┌─────────────────────────────────────────┐
│  ⚠ 3 条待审批提案              [展开 ▼] │   ← 默认收起，只显示计数
│─────────────────────────────────────────│
│  (展开后显示提案卡片列表)                │
│  📋 [更新] 美元降息预期 · ●7 · 宏观分析师 │
│  [采纳] [拒绝] [查看详情 →]             │
│─────────────────────────────────────────│
│  ... 原有事实表列表 ...                  │
└─────────────────────────────────────────┘
```

- 无待审批提案时区块完全隐藏
- 列表内嵌标记（5.1）始终可见，汇总区块为辅助功能

### 5.3 提案详情弹窗

```
┌─────────────────────────────────────────┐
│  提案详情                                │
│                                         │
│  类型：趋势 · 操作：新增                 │
│  标题：人民币走强                        │
│  置信度：8/10                           │
│  来源：宏观分析师 · 运行：#2026-0512-01 │
│                                         │
│  变更摘要：                              │
│  基于XXX数据，判断人民币将持续走强...     │
│                                         │
│  （update 类型显示新旧值对比）            │
│  ┌─ 当前值 ──┐  ┌─ 提议值 ───┐         │
│  │ 置信度：7  │  │ 置信度：9   │         │
│  │ 依据：... │  │ 依据：...  │         │
│  └───────────┘  └────────────┘         │
│                                         │
│  [采纳] [拒绝] [关闭]                   │
└─────────────────────────────────────────┘
```

### 5.4 全局提案页

新增 `/proposals` 页面，汇总所有类型的待审批提案：
- 按类型 tab 切换（全部 / 趋势 / 行业 / 自选股）
- 支持批量操作（全选 → 批量采纳/拒绝）
- 审批历史记录（adopted/rejected 状态）

### 5.5 Dashboard 集成

- Home 页第四张卡片从占位符改为真实的 pending proposal 计数
- 点击跳转到 `/proposals`
- 侧边栏 "提案" 导航项显示未读 badge

## 6. 验收标准

- [ ] 可通过 API 创建三种类型的提案（create/update/delete）
- [ ] create 提案同时在事实表新增 proposed 记录，target_id 关联
- [ ] update/delete 提案不立即修改事实表
- [ ] 同一目标已有 pending 提案时，高置信度新提案自动替换旧提案
- [ ] 置信度不高于时返回 409
- [ ] 采纳 create 提案后事实表记录 proposed → adopted
- [ ] 采纳 update 提案后事实表记录更新为 payload 值
- [ ] 采纳 delete 提案后事实表记录状态变为 removed
- [ ] 拒绝 create 提案后事实表记录 proposed → rejected
- [ ] 拒绝 update/delete 提案后事实表无变化
- [ ] 取消提案功能正常
- [ ] 置信度淘汰机制生效：超限时自动撤回最低置信度的 create 提案
- [ ] 置信度相同时淘汰最早创建的提案
- [ ] 审计日志完整记录所有变更操作（含 evicted）
- [ ] 前端管理页面通过 proposals 关联查询标记有 pending 提案的条目
- [ ] 事实表列表中有 pending 提案的条目显示 ⚠ 标记和审批按钮
- [ ] 点击审批按钮打开提案详情弹窗，支持采纳/拒绝
- [ ] 提案详情弹窗展示变更摘要和新旧值对比
- [ ] 全局提案页正常展示和审批
- [ ] Dashboard 提案卡片接入真实数据
- [ ] 侧边栏提案导航显示 badge
- [ ] API 分页正常
