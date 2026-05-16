# 阶段 3 任务清单：事实表管理（趋势 + 行业 + 自选股）

## 数据库迁移

- [ ] 在 `agent/src/db/database.py` 中新增迁移版本 3：创建 trends、industries、stocks 三张表（含 CHECK 约束和 UNIQUE 约束）
- [ ] 创建 updated_at 自动更新触发器（trg_trends_updated_at、trg_industries_updated_at、trg_stocks_updated_at）
- [ ] 创建 (user_id, status) 复合索引（idx_trends_user_status、idx_industries_user_status、idx_stocks_user_status）

## Pydantic Models

- [ ] 定义 TrendCreate / TrendUpdate / TrendResponse model（title 必填，level 枚举校验，confidence 0-10）
- [ ] 定义 IndustryCreate / IndustryUpdate / IndustryResponse model（name 必填，confidence 0-10，recommended_stocks JSON 数组）
- [ ] 定义 StockCreate / StockUpdate / StockResponse model（name + code 必填，confidence 0-10，position REAL，target_price/stop_loss 正数校验）
- [ ] 定义 DashboardResponse model（trends/industries/stocks 统计 + latest_runs 列表）

## 后端 — 趋势 API

- [ ] `GET /api/trends`：列表查询，支持 `?status=` 过滤（active/proposed/adopted/rejected/removed），JWT 鉴权 + user_id 隔离
- [ ] `GET /api/trends/{id}`：详情，校验 user_id 归属
- [ ] `POST /api/trends`：新增，状态直接为 adopted，Pydantic 校验输入
- [ ] `PUT /api/trends/{id}`：更新字段，校验 user_id 归属
- [ ] `DELETE /api/trends/{id}`：设状态为 removed，校验 user_id 归属

## 后端 — 行业 API

- [ ] `GET /api/industries`：列表查询，支持 `?status=` 过滤，JWT 鉴权 + user_id 隔离
- [ ] `GET /api/industries/{id}`：详情，校验 user_id 归属
- [ ] `POST /api/industries`：新增，Pydantic 校验输入
- [ ] `PUT /api/industries/{id}`：更新，校验 user_id 归属
- [ ] `DELETE /api/industries/{id}`：删除，校验 user_id 归属

## 后端 — 自选股 API

- [ ] `GET /api/stocks`：列表查询，支持 `?status=` 过滤，JWT 鉴权 + user_id 隔离
- [ ] `GET /api/stocks/{id}`：详情，校验 user_id 归属
- [ ] `POST /api/stocks`：新增，Pydantic 校验输入（code 格式提示）
- [ ] `PUT /api/stocks/{id}`：更新，校验 user_id 归属
- [ ] `DELETE /api/stocks/{id}`：删除，校验 user_id 归属

## 后端 — Dashboard

- [ ] `GET /api/dashboard`：汇总数据（各类活跃数、待审批数）+ 用户最近 runs 列表

## 后端 — 路由注册

- [ ] 在 `api_server.py` 中注册趋势、行业、自选股、Dashboard 路由，统一添加 `Depends(require_jwt_auth)`

## 前端 — 通用组件

- [ ] 状态筛选 Tab 组件（All / Active / Proposed / Rejected / Removed）
- [ ] 状态标签组件（颜色区分各状态）
- [ ] 置信度显示组件（0-10 进度条或数字）
- [ ] 确认弹窗组件（删除确认）

## 前端 — 趋势管理页

- [ ] `/trends` 路由和页面
- [ ] 列表渲染（卡片式，含标题、级别标签、置信度、依据摘要）
- [ ] 状态筛选 Tab
- [ ] 手动添加弹窗（表单：标题、级别下拉、置信度滑块、依据）
- [ ] 编辑弹窗
- [ ] 删除操作（确认弹窗 → DELETE → 刷新列表）

## 前端 — 行业管理页

- [ ] `/industries` 路由和页面
- [ ] 列表渲染（行业名、置信度、理由摘要、推荐股票数）
- [ ] 状态筛选 Tab
- [ ] 手动添加弹窗（表单：名称、置信度、理由、推荐股票代码列表）
- [ ] 编辑弹窗
- [ ] 删除操作

## 前端 — 自选股管理页

- [ ] `/stocks` 路由和页面
- [ ] 列表渲染（名称+代码、行业名、置信度、操作建议、目标价、止损位、仓位金额）
- [ ] 状态筛选 Tab
- [ ] 手动添加弹窗（表单：名称、代码 tushare 格式、行业名文本输入、置信度、仓位金额、建议、目标价、止损位、理由）
- [ ] 编辑弹窗
- [ ] 删除操作

## 前端 — Dashboard

- [ ] `/` 路由和 Dashboard 页面
- [ ] 统计卡片（活跃趋势数、活跃行业数、活跃自选股数、待审批数）
- [ ] 最近投研运行列表（复用现有 runs 数据）

## 测试

- [ ] 数据库迁移测试：版本 3 正确创建三张表 + 触发器 + 索引
- [ ] 后端测试：三张表 CRUD 全覆盖（创建、读取、更新、软删除）
- [ ] 后端测试：状态过滤（active = proposed + adopted）
- [ ] 后端测试：删除不物理删除，状态变为 removed
- [ ] 后端测试：用户隔离（用户 A 看不到用户 B 的数据）
- [ ] 后端测试：输入校验（confidence 越界返回 422、level 枚举校验、title 非空）
- [ ] 后端测试：updated_at 触发器自动更新
- [ ] 前端测试：三个管理页面 E2E（添加 → 列表展示 → 编辑 → 删除）
