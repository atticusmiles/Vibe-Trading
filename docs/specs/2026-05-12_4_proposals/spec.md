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
    target_id         INTEGER,                -- 事实表记录ID，新增时为 NULL
    action            TEXT NOT NULL,           -- create / update / delete
    status            TEXT NOT NULL DEFAULT 'pending',
    title             TEXT NOT NULL,
    summary           TEXT,
    confidence        INTEGER DEFAULT 5,       -- 0~10
    payload           TEXT NOT NULL,           -- JSON，目标字段值
    original_payload  TEXT,                    -- JSON，仅 update 类型
    run_id            TEXT,                    -- 关联的投研运行ID
    source_agent      TEXT,                    -- 产出Agent
    created_at        TEXT DEFAULT (datetime('now')),
    reviewed_at       TEXT
);

CREATE INDEX idx_proposals_user_status ON proposals(user_id, status);
CREATE INDEX idx_proposals_target ON proposals(user_id, target_type, target_id);
```

### audit_logs 表

```sql
CREATE TABLE audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    action      TEXT NOT NULL,           -- proposal_created / proposal_adopted / proposal_rejected
    target_type TEXT,                    -- trend / industry / stock
    target_id   INTEGER,
    details     TEXT,                    -- JSON
    actor_type  TEXT NOT NULL,           -- user / agent
    actor_id    TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_audit_user ON audit_logs(user_id, created_at);
```

## 3. API 设计

```
GET    /api/proposals                      列表（?type=trend|industry|stock&status=pending|adopted|rejected&target_id=）
GET    /api/proposals/{id}                 详情
POST   /api/proposals                      创建提案（Agent 或系统内部调用）
POST   /api/proposals/{id}/adopt           采纳提案
POST   /api/proposals/{id}/reject          拒绝提案
```

## 4. 业务逻辑

### 4.1 提案创建

创建提案时需指定 `target_type`、`action`、`payload`：

**action=create**：
- `target_id` 为 NULL
- 同时在事实表新增一条 `status=proposed` 的记录
- `target_id` 设为该新记录的 ID
- 提案立即生效（事实表有 proposed 记录）

**action=update**：
- `target_id` 指向事实表已有记录
- `original_payload` 保存当前字段值（用于拒绝时回滚）
- 事实表记录更新为 payload 中的值，状态变为 `proposed`

**action=delete**：
- `target_id` 指向事实表已有记录
- 事实表状态不变
- 用户确认后状态更新为 `removed`

### 4.2 提案审批

**采纳（adopt）**：
- 提案状态变为 `adopted`
- 事实表记录状态变为 `adopted`
- 记录审计日志

**拒绝（reject）**：
- 提案状态变为 `rejected`
- 如果是 `action=create`：事实表记录状态变为 `rejected`
- 如果是 `action=update`：事实表记录回滚为 `original_payload` 中的值，状态恢复原状态
- 如果是 `action=delete`：事实表不变，提案关闭
- 记录审计日志

### 4.3 置信度淘汰

- 读取用户 settings 中 `proposal_limits.{type}` 配置（默认 10）
- 仅限制 `action=create` 类型的 `pending` 提案数量
- 超过上限时，自动撤回当前置信度最低的 `pending` `create` 提案（事实表记录变为 `rejected`）
- `action=update` 和 `action=delete` 不受数量限制

### 4.4 提案列表过滤

- `?type=trend`：按 target_type 过滤
- `?status=pending`：按状态过滤
- `?target_id=42`：查看某条事实表记录关联的所有提案
- 无参数：返回所有提案，按创建时间倒序

## 5. 前端设计

### 5.1 管理页面增加提案区域

在趋势/行业/股票管理页面的顶部增加**待审批区块**：

```
┌─────────────────────────────────────────┐
│  ┌─ 待审批提案 ──────────────────────┐   │
│  │                                   │   │
│  │  📋 [新增] 人民币走强             │   │
│  │  置信度：8/10 · 来源：宏观分析师   │   │
│  │  摘要：基于XXX数据，判断...        │   │
│  │  [采纳] [拒绝] [查看详情 →]       │   │
│  │                                   │   │
│  │  📋 [更新] 美元降息预期           │   │
│  │  置信度：7/10 · 来源：宏观分析师   │   │
│  │  [采纳] [拒绝] [查看详情 →]       │   │
│  │                                   │   │
│  └───────────────────────────────────┘   │
│                                         │
│  [全部] [活跃] [已采纳] [已拒绝] [已移除] │  ← 原有列表
│  ...                                    │
└─────────────────────────────────────────┘
```

### 5.2 提案详情弹窗

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
│  （如果是 update 类型，显示新旧值对比）   │
│  ┌─ 原始值 ──┐  ┌─ 新值 ─────┐         │
│  │ 置信度：7  │  │ 置信度：9   │         │
│  │ 依据：... │  │ 依据：...  │         │
│  └───────────┘  └────────────┘         │
│                                         │
│  [采纳] [拒绝] [关闭]                   │
└─────────────────────────────────────────┘
```

## 6. 验收标准

- [ ] 可通过 API 创建三种类型的提案（create/update/delete）
- [ ] create 提案同时在事实表新增 proposed 记录
- [ ] update 提案更新事实表记录，保留原始值
- [ ] delete 提案不改变事实表状态
- [ ] 采纳提案后事实表状态正确变更
- [ ] 拒绝提案后事实表正确回滚
- [ ] 置信度淘汰机制生效：超限时自动撤回最低置信度的 create 提案
- [ ] 审计日志完整记录所有变更操作
- [ ] 前端管理页面展示待审批提案，支持采纳/拒绝交互
- [ ] 提案详情弹窗展示变更摘要和新旧值对比
