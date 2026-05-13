# 阶段 4 任务清单：提案机制

## 数据库

- [ ] 创建 proposals 表（含 user_id、target_type、target_id、action、status、title、summary、confidence、payload、original_payload、run_id、source_agent）
- [ ] 创建 proposals 索引（user_id+status、user_id+target_type+target_id）
- [ ] 创建 audit_logs 表（含 user_id、action、target_type、target_id、details、actor_type、actor_id）
- [ ] 创建 audit_logs 索引（user_id+created_at）

## 后端 — 提案 API

- [ ] `POST /api/proposals`：创建提案
  - 根据 action 类型执行不同逻辑
  - create：同时在事实表新增 proposed 记录
  - update：保存 original_payload，更新事实表记录为 proposed
  - delete：不改变事实表状态
- [ ] `GET /api/proposals`：列表查询
  - 支持 ?type=、?status=、?target_id= 过滤
  - 按创建时间倒序
- [ ] `GET /api/proposals/{id}`：详情
  - 含关联的事实表记录当前状态
- [ ] `POST /api/proposals/{id}/adopt`：采纳
  - 提案状态 → adopted
  - 事实表状态 → adopted
  - 写入审计日志
- [ ] `POST /api/proposals/{id}/reject`：拒绝
  - 提案状态 → rejected
  - create：事实表 → rejected
  - update：事实表回滚 original_payload
  - delete：事实表不变
  - 写入审计日志

## 后端 — 置信度淘汰

- [ ] 提案创建时检查该类型 pending create 提案数量
- [ ] 超过用户配置的上限（settings.proposal_limits.{type}，默认 10）时
- [ ] 自动撤回置信度最低的 pending create 提案（状态 → rejected，事实表 → rejected）
- [ ] 撤回操作写入审计日志

## 后端 — 审计日志

- [ ] 审计日志写入函数：记录 action、target、details、actor_type、actor_id
- [ ] 所有提案变更操作（创建、采纳、拒绝、淘汰）自动记录审计日志

## 前端 — 提案区域

- [ ] 在趋势管理页顶部增加待审批提案区块
- [ ] 在行业管理页顶部增加待审批提案区块
- [ ] 在自选股管理页顶部增加待审批提案区块
- [ ] 提案卡片：显示类型标签、标题、置信度、来源 Agent、摘要
- [ ] 采纳按钮：确认弹窗 → 调用 adopt API → 刷新列表
- [ ] 拒绝按钮：确认弹窗 → 调用 reject API → 刷新列表
- [ ] 提案区块无待审批时隐藏

## 前端 — 提案详情弹窗

- [ ] 详情弹窗组件
- [ ] 显示提案基本信息（类型、操作、标题、置信度、来源）
- [ ] 显示变更摘要（Markdown 渲染）
- [ ] update 类型显示新旧值对比（左右并排或 diff 视图）
- [ ] 底部操作按钮（采纳/拒绝/关闭）

## 测试

- [ ] 后端测试：create 提案 → 事实表新增 proposed 记录
- [ ] 后端测试：update 提案 → 事实表更新 + original_payload 保存
- [ ] 后端测试：delete 提案 → 事实表不变
- [ ] 后端测试：采纳 → 事实表状态变更正确
- [ ] 后端测试：拒绝 create → 事实表记录 rejected
- [ ] 后端测试：拒绝 update → 事实表回滚
- [ ] 后端测试：置信度淘汰 → 超限时自动撤回最低置信度
- [ ] 后端测试：审计日志完整记录
- [ ] 前端测试：提案审批 E2E（查看 → 采纳/拒绝 → 列表更新）
