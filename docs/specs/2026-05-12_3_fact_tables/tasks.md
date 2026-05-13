# 阶段 3 任务清单：事实表管理（趋势 + 行业 + 自选股）

## 数据库

- [ ] 创建 trends 表（含 user_id、status、title、level、confidence、evidence）
- [ ] 创建 industries 表（含 user_id、status、name、confidence、reason、research_report、recommended_stocks）
- [ ] 创建 stocks 表（含 user_id、status、name、code、confidence、industry_id、position、advice、target_price、stop_loss、reason）
- [ ] 为三张表创建 `user_id` 索引
- [ ] 为三张表创建 `status` 索引

## 后端 — 趋势 API

- [ ] `GET /api/trends`：列表查询，支持 `?status=` 过滤（active/proposed/adopted/rejected/removed）
- [ ] `GET /api/trends/{id}`：详情
- [ ] `POST /api/trends`：新增，状态直接为 adopted
- [ ] `PUT /api/trends/{id}`：更新字段
- [ ] `DELETE /api/trends/{id}`：设状态为 removed

## 后端 — 行业 API

- [ ] `GET /api/industries`：列表查询，支持 `?status=` 过滤
- [ ] `GET /api/industries/{id}`：详情
- [ ] `POST /api/industries`：新增
- [ ] `PUT /api/industries/{id}`：更新
- [ ] `DELETE /api/industries/{id}`：删除

## 后端 — 自选股 API

- [ ] `GET /api/stocks`：列表查询，支持 `?status=` 过滤
- [ ] `GET /api/stocks/{id}`：详情
- [ ] `POST /api/stocks`：新增
- [ ] `PUT /api/stocks/{id}`：更新
- [ ] `DELETE /api/stocks/{id}`：删除

## 后端 — Dashboard

- [ ] `GET /api/dashboard`：汇总数据（各类活跃数、待审批数、最近投研列表）

## 前端 — 通用组件

- [ ] 状态筛选 Tab 组件（全部/活跃/待审批/已拒绝/已移除）
- [ ] 状态标签组件（颜色区分各状态）
- [ ] 置信度显示组件（0-10 进度条或数字）
- [ ] 确认弹窗组件（删除确认）

## 前端 — 趋势管理页

- [ ] `/trends` 路由和页面
- [ ] 列表渲染（卡片式，含标题、级别标签、置信度、依据摘要）
- [ ] 状态筛选 Tab
- [ ] 手动添加弹窗（表单：标题、级别、置信度、依据）
- [ ] 编辑弹窗
- [ ] 删除操作（确认弹窗 → DELETE → 刷新列表）

## 前端 — 行业管理页

- [ ] `/industries` 路由和页面
- [ ] 列表渲染（行业名、置信度、理由摘要、推荐股票数）
- [ ] 状态筛选 Tab
- [ ] 手动添加弹窗（表单：名称、置信度、理由）
- [ ] 编辑弹窗
- [ ] 删除操作

## 前端 — 自选股管理页

- [ ] `/stocks` 路由和页面
- [ ] 列表渲染（名称+代码、行业、置信度、建议标签、目标价、止损位）
- [ ] 状态筛选 Tab
- [ ] 手动添加弹窗（表单：名称、代码、行业选择、置信度、持仓、建议、目标价、止损位、理由）
- [ ] 编辑弹窗
- [ ] 删除操作

## 前端 — Dashboard

- [ ] `/` 路由和 Dashboard 页面
- [ ] 统计卡片（活跃趋势数、活跃行业数、活跃自选股数、待审批数）
- [ ] 最近投研运行列表（预留位置，阶段 6 实现）

## 测试

- [ ] 后端测试：三张表 CRUD 全覆盖
- [ ] 后端测试：状态过滤（active = proposed + adopted）
- [ ] 后端测试：删除不物理删除，状态变为 removed
- [ ] 后端测试：用户隔离（用户 A 看不到用户 B 的数据）
- [ ] 前端测试：三个管理页面 E2E（添加 → 列表 → 编辑 → 删除）
