# 阶段 3 任务清单：事实表管理（趋势 + 行业 + 自选股）

## 数据库迁移

- [ ] 在 `agent/src/db/database.py` 中新增迁移版本 3：创建 trends、industries、stocks 三张表（含 CHECK 约束和 UNIQUE 约束）
- [ ] 创建 updated_at 自动更新触发器（trg_trends_updated_at、trg_industries_updated_at、trg_stocks_updated_at）
- [ ] 创建 (user_id, status) 复合索引（idx_trends_user_status、idx_industries_user_status、idx_stocks_user_status）

## Pydantic Models

- [ ] 定义 TrendCreate / TrendUpdate / TrendResponse model（title 必填，level 枚举校验，confidence 0-10）
- [ ] 定义 IndustryCreate / IndustryUpdate / IndustryResponse model（name 必填，confidence 0-10，recommended_stocks JSON 数组，recommended_count 虚拟字段）
- [ ] 定义 StockCreate / StockUpdate / StockResponse model（name + code 必填，confidence 0-10，position REAL，target_price/stop_loss 非负校验）
- [ ] 定义 DashboardResponse model（trends/industries/stocks 统计 + recently_updated 列表 + latest_runs 列表）
- [ ] TrendUpdate / IndustryUpdate / StockUpdate 的 status 字段标记 Optional，允许通过 PUT 修改（Undo 恢复场景）

## 后端 — 趋势 API

- [ ] `GET /api/trends`：列表查询，支持 `?status=` 过滤（active/proposed/adopted/rejected/removed），JWT 鉴权 + user_id 隔离
- [ ] `GET /api/trends/{id}`：详情，校验 user_id 归属
- [ ] `POST /api/trends`：新增，状态直接为 adopted，Pydantic 校验输入
- [ ] `PUT /api/trends/{id}`：更新字段（含 status），校验 user_id 归属，inline editing 单字段更新支持
- [ ] `DELETE /api/trends/{id}`：设状态为 removed，校验 user_id 归属

## 后端 — 行业 API

- [ ] `GET /api/industries`：列表查询，支持 `?status=` 过滤，JWT 鉴权 + user_id 隔离
- [ ] `GET /api/industries/{id}`：详情（含 recommended_count 虚拟字段），校验 user_id 归属
- [ ] `POST /api/industries`：新增，Pydantic 校验输入
- [ ] `PUT /api/industries/{id}`：更新字段（含 status），校验 user_id 归属
- [ ] `DELETE /api/industries/{id}`：删除，校验 user_id 归属

## 后端 — 自选股 API

- [ ] `GET /api/stocks`：列表查询，支持 `?status=` 过滤，JWT 鉴权 + user_id 隔离
- [ ] `GET /api/stocks/{id}`：详情，校验 user_id 归属
- [ ] `POST /api/stocks`：新增，Pydantic 校验输入（code 格式提示）
- [ ] `PUT /api/stocks/{id}`：更新字段（含 status），校验 user_id 归属
- [ ] `DELETE /api/stocks/{id}`：删除，校验 user_id 归属

## 后端 — Dashboard

- [ ] `GET /api/dashboard`：汇总数据（各类活跃数、待审批数）+ recently_updated（合并三张表按 updated_at 降序前 5 条，含 type 字段）+ 用户最近 runs 列表

## 后端 — 路由注册

- [ ] 在 `api_server.py` 中注册趋势、行业、自选股、Dashboard 路由，统一添加 `Depends(require_jwt_auth)`

## 前端 — 通用组件

- [ ] MasterDetailLayout 组件：左右分栏（左 40% 列表 + 右 60% 详情），右侧面板支持收起/展开动画
- [ ] CompactList 组件：紧凑行列表（~40px 行高），支持列头点击排序（升序/降序箭头）、选中行高亮（左侧 2px 竖线）、hover 背景变化 + 操作图标显示
- [ ] StatusFilterBar 组件：Pill tabs（All / Active / Proposed / Rejected / Removed），选中高亮
- [ ] StatusDot 组件：状态圆点（adopted=绿, proposed=蓝, rejected=灰, removed=暗灰虚线圆）
- [ ] ConfidenceDot 组件：0-10 色点（0-3红, 4-6黄, 7-10绿）+ 数字
- [ ] ConfidenceSlider 组件：0-10 滑块，带数字显示和色带，用于 inline editing
- [ ] SearchInput 组件：搜索框，debounce 300ms，传入 onSearch 回调，放置于左侧面板顶部
- [ ] DetailPanel 组件：右侧面板，三种状态切换（收起窄条 / 详情 / 添加表单），支持 inline editing，内容切换 slide/fade 动画
- [ ] InlineEditableField 组件：展示态点击变为编辑控件（文本→input，枚举→select，数字→slider，多行→textarea），失焦/Enter 自动 Save
- [ ] DeleteWithUndo 组件：点击删除 → sonner toast "Removed" + Undo 按钮（5 秒内可撤销，Undo 调用 PUT 恢复 status）
- [ ] EmptyState 组件：图示 + 引导文案 + CTA 按钮
- [ ] TagInput 组件：回车添加 tag，点击 × 删除，用于 recommended_stocks 等

## 前端 — 趋势管理页

- [ ] `/trends` 路由和页面框架（MasterDetailLayout）
- [ ] CompactList 列表：列 Title(flex) / Level(80px) / Conf(40px) / Status(30px) / Updated(70px)，默认 Updated 降序
- [ ] Level 标签颜色：long-term=蓝, mid-term=紫, short-term=橙（冷色=长期，暖色=短期）
- [ ] 左侧搜索栏 + StatusFilterBar
- [ ] 列表行 hover 显示编辑/删除操作图标
- [ ] 选中状态记入 URL hash（`/trends#3`），页面刷新恢复
- [ ] DetailPanel 详情态（分组）：概览（Title/Level/Confidence，inline editing）+ 分析（Evidence，inline editing）+ 元数据（Status/时间戳）
- [ ] DetailPanel 添加态：Title 文本输入、Level 下拉、Confidence 滑块、Evidence 多行文本、[Save] 按钮
- [ ] 面板收起态：未选中时显示窄条 "Select an item or + Add"
- [ ] 删除操作：DeleteWithUndo（列表 hover 图标或面板内 Delete 按钮，Undo 调用 PUT 恢复 status=adopted）
- [ ] 空状态：图示 + "Add your first trend" + CTA

## 前端 — 行业管理页

- [ ] `/industries` 路由和页面框架（MasterDetailLayout）
- [ ] CompactList 列表：列 Name(flex) / Conf(40px) / Stocks(50px) / Status(30px) / Updated(70px)
- [ ] 左侧搜索栏 + StatusFilterBar
- [ ] 列表行 hover 显示编辑/删除操作图标
- [ ] DetailPanel 详情态（分组）：概览（Name/Confidence）+ 分析（Reason/Research Report/Recommended Stocks Tag 列表）+ 元数据（Status/时间戳），全部支持 inline editing
- [ ] DetailPanel 添加态：Name 文本输入、Confidence 滑块、Reason 多行文本、Research Report 多行文本、Recommended Stocks TagInput、[Save]
- [ ] 面板收起态
- [ ] 删除操作：DeleteWithUndo
- [ ] 空状态引导

## 前端 — 自选股管理页

- [ ] `/stocks` 路由和页面框架（MasterDetailLayout）
- [ ] CompactList 列表：列 Name+Code(flex) / Industry(90px, 链接跳转 /industries?search=) / Advice(50px, 颜色标签) / Conf(40px) / Price(100px, T:¥98 / S:¥72) / Status(30px) / Updated(70px)
- [ ] Advice 颜色：`advice.toLowerCase()` 精确匹配 — buy=绿, sell=红, hold=灰, 其他=默认
- [ ] 左侧搜索栏 + StatusFilterBar
- [ ] 列表行 hover 显示编辑/删除操作图标
- [ ] DetailPanel 详情态（分组）：基本信息（Name+Code/Industry Name）+ 交易参数（Advice/Target/Stop/Position）+ 分析（Confidence/Reason）+ 元数据（Status/时间戳），全部支持 inline editing
- [ ] DetailPanel 添加态：Name、Code（placeholder: 600000.SH）、Industry Name（带自动补全）、Advice、Target Price、Stop Loss、Position、Confidence 滑块、Reason 多行、[Save]
- [ ] Industry Name 自动补全：从已有 industries 列表搜索建议，允许自由输入
- [ ] 面板收起态
- [ ] 删除操作：DeleteWithUndo
- [ ] 空状态引导

## 前端 — Dashboard

- [ ] 替换现有 Home 页面为动态 Dashboard（Bento Grid 布局）
- [ ] 统计卡片行（4 列等宽）：Active Trends / Active Industries / Active Stocks / Pending Proposals，text-3xl 数字 + proposed 副标题（warning 色），**点击跳转携带 status 参数**（如 `/trends?status=active`）
- [ ] Pending Proposals 卡片：预留位置，Phase 4 实现
- [ ] Recently Updated 区（左 60%）：展示 Dashboard API 的 recently_updated 数据，每行：类型图标 + 标题 + 置信度 + 相对时间，**点击行跳转并选中条目**（如 `/trends#5`），[All] 跳转 `/trends?sort=updated`
- [ ] Recent Runs 区（右 40%）：表格展示最近 runs（复用现有数据，前 5 条），[All] 跳转 Agent 页

## 前端 — 导航与路由

- [ ] 侧边栏 NAV 更新：添加 Trends(TrendingUp) / Industries(Factory) / Stocks(CandlestickChart)，Home 改名 Dashboard(LayoutDashboard)
- [ ] 路由注册：`/trends`、`/industries`、`/stocks`，支持 `?status=` 查询参数和 `#id` hash
- [ ] i18n 添加新页面翻译 key（dashboard, trends, industries, stocks）

## 测试

- [ ] 数据库迁移测试：版本 3 正确创建三张表 + 触发器 + 索引
- [ ] 后端测试：三张表 CRUD 全覆盖（创建、读取、更新、软删除）
- [ ] 后端测试：PUT 支持 status 字段修改（Undo 恢复场景）
- [ ] 后端测试：状态过滤（active = proposed + adopted）
- [ ] 后端测试：删除不物理删除，状态变为 removed
- [ ] 后端测试：用户隔离（用户 A 看不到用户 B 的数据）
- [ ] 后端测试：输入校验（confidence 越界返回 422、level 枚举校验、title 非空）
- [ ] 后端测试：updated_at 触发器自动更新
- [ ] 后端测试：industries 详情返回 recommended_count 虚拟字段
- [ ] 后端测试：Dashboard API 返回 recently_updated（合并三张表，按 updated_at 排序，前 5 条）
- [ ] 前端测试：Master-Detail 布局（选中列表项 → 右侧面板展开 → 显示详情）
- [ ] 前端测试：Inline editing（点击字段 → 编辑 → 失焦 Save → 列表同步更新）
- [ ] 前端测试：添加 → 列表更新 → 选中查看详情 → 删除 + Undo 恢复
- [ ] 前端测试：排序（点击列头切换升序/降序）
- [ ] 前端测试：搜索过滤 + 状态筛选叠加
- [ ] 前端测试：URL hash 记忆（选中条目后刷新页面，恢复选中状态）
- [ ] 前端测试：Dashboard 统计卡片跳转携带 status 参数
- [ ] 前端测试：Dashboard Recently Updated 点击跳转并选中条目
