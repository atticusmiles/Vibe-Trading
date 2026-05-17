# 阶段 4 任务清单：提案机制

## 数据库（Migration v5）

- [ ] `_SCHEMA_VERSION` 4 → 5
- [ ] 创建 `proposals` 表（含 user_id、target_type、target_id、action、status、title、summary、confidence、payload、original_payload、run_id、source_agent、created_at、reviewed_at）
- [ ] 创建 `idx_proposals_user_status` 索引
- [ ] 创建 `idx_proposals_target` 索引
- [ ] 创建 `idx_proposals_pending_target` 唯一索引（WHERE status='pending'，覆盖 create/update/delete）
- [ ] 创建 `audit_logs` 表（含 user_id、action、target_type、target_id、details、actor_type、actor_id、created_at）
- [ ] 创建 `idx_audit_user` 索引

## 后端 — 提案 API

**新建文件：** `agent/src/proposals.py`（~400 行）

### Pydantic 模型

- [ ] `ProposalCreate`：target_type、action、payload、title、summary、confidence、run_id、source_agent（create 时后端自动生成 target_id，update/delete 需传 target_id）
- [ ] `ProposalResponse`：所有字段 + 审计信息
- [ ] `ProposalListResponse`：分页响应（items、total、page、per_page）

### CRUD 端点

- [ ] `POST /api/proposals`：创建提案
  - 验证 target_type 合法（trend/industry/stock）
  - action=create：先在事实表新增 proposed 记录，获取 target_id
  - action=update/delete：target_id 必填，验证事实表记录存在
  - action=update：保存 original_payload（当前事实表记录快照）
  - 同一 target 已有 pending 提案时：新置信度更高 → 自动撤回旧提案再插入；不高于 → 409
  - 触发 create 数量淘汰检查
  - 写入审计日志
- [ ] `GET /api/proposals`：列表查询
  - 支持 ?type=、?status=、?target_id= 过滤
  - 支持 ?page=1&per_page=20 分页
  - 按创建时间倒序
- [ ] `GET /api/proposals/{id}`：详情
  - 含关联的事实表记录当前状态（用于 update 类型的新旧对比）
- [ ] `POST /api/proposals/{id}/adopt`：采纳
  - 提案状态 → adopted，设置 reviewed_at
  - action=create：事实表记录 proposed → adopted
  - action=update：事实表记录更新为 payload 值，状态 → adopted
  - action=delete：事实表记录状态 → removed
  - 写入审计日志（actor_type=user）
- [ ] `POST /api/proposals/{id}/reject`：拒绝
  - 提案状态 → rejected，设置 reviewed_at
  - action=create：事实表记录 proposed → rejected
  - action=update/delete：事实表不做任何操作
  - 写入审计日志（actor_type=user）
- [ ] `POST /api/proposals/{id}/cancel`：取消
  - 仅 pending 状态可取消
  - 提案状态 → rejected，设置 reviewed_at
  - action=create：事实表记录 proposed → rejected
  - action=update/delete：事实表不做任何操作
  - 写入审计日志（action=proposal_cancelled）

### 注册路由

- [ ] `agent/api_server.py` 添加 `from src.proposals import register_proposal_routes` + `register_proposal_routes(app)`

## 后端 — 提案淘汰

- [ ] 常量 `DEFAULT_PROPOSAL_LIMIT = 10`
- [ ] `_evict_if_lower_confidence()` 辅助函数 — 同目标替换
  - 查询同一 (target_type, target_id) 的 pending 提案
  - 如果存在且新置信度更高：旧提案 rejected + create 类型的事实表 proposed → rejected
  - 如果存在但置信度不高于：抛出 409
  - 写入审计日志
- [ ] `_evict_if_over_limit()` 辅助函数 — create 数量淘汰
  - 查询当前 user + target_type 的 pending create 提案数量
  - 超限时：`UPDATE proposals SET status='rejected' WHERE status='pending' AND action='create' ORDER BY confidence ASC, created_at ASC LIMIT (overflow)`
  - 被淘汰的提案状态 → rejected
  - 每条淘汰写入审计日志（action=proposal_evicted）
- [ ] 在 `POST /api/proposals` 创建成功后调用

## 后端 — 审计日志

- [ ] `_write_audit_log()` 辅助函数
  - 参数：user_id、action、target_type、target_id、details、actor_type、actor_id
  - INSERT 到 audit_logs
- [ ] 所有提案变更操作自动调用：create、adopt、reject、cancel、evict

## 后端 — Dashboard 扩展

- [ ] `GET /api/dashboard` 响应增加 `pending_proposals` 计数字段
  - 按 target_type 分组统计 pending 提案数量
- [ ] `DashboardResponse` 模型增加 `pending_proposals: Dict[str, int]`

## 前端 — API Client + Types

**修改文件：** `frontend/src/lib/api.ts`

- [ ] 新增 `ProposalItem` 接口
- [ ] 新增 `ProposalListResponse` 接口（含分页信息）
- [ ] 新增 API 函数：`listProposals`、`getProposal`、`createProposal`、`adoptProposal`、`rejectProposal`、`cancelProposal`

**修改文件：** `frontend/src/lib/i18n.tsx`

- [ ] 添加翻译 key：proposals/待审批/采纳/拒绝/取消/evicted/提案详情/变更摘要/提议值/当前值 等

## 前端 — 提案组件

**新建目录：** `frontend/src/components/proposals/`

| 文件 | 用途 |
|------|------|
| `ProposalBanner.tsx` | 可折叠待审批区块（收起显示计数，展开显示卡片列表） |
| `ProposalCard.tsx` | 单条提案卡片（类型标签、标题、置信度、来源、摘要、操作按钮） |
| `ProposalDetailModal.tsx` | 提案详情弹窗（基本信息 + update 类型新旧对比 + 操作按钮） |
| `ProposalList.tsx` | 全局提案页列表组件（分页、过滤、批量操作） |

## 前端 — 管理页面集成

**修改文件：** `frontend/src/pages/Trends.tsx`

- [ ] 页面加载时额外请求 `GET /api/proposals?type=trend&status=pending`，建立 `Map<targetId, ProposalItem>` 索引
- [ ] CompactList renderRow 中检查：`item.status === 'proposed'` 或 proposals 索引命中 `item.id`
- [ ] 有 pending 提案的行：加 ⚠ 图标 + `bg-warning/5` 背景高亮 + 右侧"审批"按钮
- [ ] 点击"审批"→ 打开 ProposalDetailModal
- [ ] 引入 `ProposalBanner` 组件，页面顶部可折叠待审批汇总
- [ ] 采纳/拒绝后同时刷新事实表列表和 proposals 索引

**修改文件：** `frontend/src/pages/Industries.tsx`

- [ ] 同上

**修改文件：** `frontend/src/pages/Stocks.tsx`

- [ ] 同上

## 前端 — 全局提案页

**新建文件：** `frontend/src/pages/Proposals.tsx`（~250 行）

- [ ] 按 target_type tab 切换（全部 / 趋势 / 行业 / 自选股）
- [ ] 提案列表（分页、状态过滤）
- [ ] 批量选择 + 批量采纳/拒绝
- [ ] 点击打开 ProposalDetailModal

## 前端 — Dashboard + 导航

**修改文件：** `frontend/src/pages/Home.tsx`

- [ ] 第四张卡片改为真实 pending proposal 计数
- [ ] 点击跳转 `/proposals`

**修改文件：** `frontend/src/router.tsx`

- [ ] 添加 `/proposals` 路由

**修改文件：** `frontend/src/components/layout/Layout.tsx`

- [ ] 导航数组添加 "提案"（DocumentCheck icon）
- [ ] 显示 pending 数量 badge

## 测试

### 后端单元测试

- [ ] create 提案 → 事实表新增 proposed 记录，提案 target_id 关联该记录
- [ ] update 提案 → 事实表不变，original_payload 保存快照
- [ ] delete 提案 → 事实表不变
- [ ] 同一 target 已有 pending 提案，新提案置信度更高 → 旧提案自动 evicted，新提案创建成功
- [ ] 同一 target 已有 pending 提案，新提案置信度不高于 → 409 冲突
- [ ] 同目标替换时 create 类型的旧提案事实表 proposed → rejected
- [ ] 采纳 create → 事实表记录 proposed → adopted
- [ ] 采纳 update → 事实表记录更新为 payload 值
- [ ] 采纳 delete → 事实表记录状态 removed
- [ ] 拒绝 create → 事实表记录 proposed → rejected
- [ ] 拒绝 update/delete → 事实表无变化
- [ ] 取消 create 提案 → 事实表记录 proposed → rejected
- [ ] 取消 update/delete 提案 → 事实表不变
- [ ] 已 adopted/rejected 的提案不能再次操作
- [ ] 置信度淘汰 → 超限时自动撤回最低置信度
- [ ] 置信度相同时淘汰最早创建的
- [ ] 审计日志完整记录所有操作
- [ ] 分页查询正常
- [ ] 未登录访问 → 401
- [ ] 跨用户访问 → 404

### 前端测试

- [ ] 提案审批 E2E（查看 → 采纳/拒绝 → 列表更新）
- [ ] 全局提案页 tab 切换和分页
