# 阶段 6 任务清单：投研引擎

## 数据库

- [ ] 创建 research_runs 表（id、user_id、trigger_type、start_stage、status、config、started_at、completed_at、error）
- [ ] 创建 research_reports 表（run_id、stage、agent_id、report_type、title、content、metadata）
- [ ] 创建 research_reports 索引（run_id + stage）

## 投研 Preset YAML

- [ ] 创建 `agent/swarm/presets/research.yaml`
- [ ] 定义 18 个 Agent（name、role、system_prompt 默认值、skills、tools）
- [ ] 定义 9 个阶段的 DAG 边（dependencies）
- [ ] 阶段 4 内部 4 个 Agent 并行
- [ ] 阶段 8 内部 3 个 Agent 并行

## Swarm 扩展

- [ ] StageController：接收 start_stage 参数，控制从指定阶段开始
- [ ] StageController：跳过阶段时从 research_reports 读取已有报告注入上下文
- [ ] ReportCollector：Agent 完成后解析输出，写入 research_reports
- [ ] ProposalGenerator：从特定阶段 Agent 输出提取提案数据
- [ ] ProposalGenerator：调用提案创建逻辑（复用阶段 4 的 Service）
- [ ] ProposalLimiter：提案写入前检查上限，超限执行淘汰
- [ ] 投研运行创建时写入 research_runs 表
- [ ] 投研运行完成时更新 status 和 completed_at
- [ ] 投研运行失败时记录 error

## Swarm 端点扩展

- [ ] `POST /swarm/runs`：支持 preset=research 参数，传递 start_stage、trigger_type、context
- [ ] `GET /swarm/runs`：支持 ?preset=research 过滤
- [ ] `GET /swarm/runs/{run_id}`：返回运行详情含各阶段状态
- [ ] SSE 事件：阶段开始/完成事件推送（含 stage、agent_id、耗时）

## 后端 — 报告 API

- [ ] `GET /api/research/runs/{run_id}/reports`：查询运行的所有报告（按 stage 排序）

## 后端 — 手动触发关联

- [ ] 趋势手动添加（`POST /api/trends`）触发投研（start_stage=1）
- [ ] 行业手动添加（`POST /api/industries`）触发投研（start_stage=2）
- [ ] 股票手动添加（`POST /api/stocks`）触发投研（start_stage=4）

## 前端 — 投研运行列表页

- [ ] `/research` 路由和页面
- [ ] 运行列表卡片（运行 ID、触发类型、状态、耗时、阶段进度条）
- [ ] 状态标签（运行中/已完成/失败）
- [ ] 启动新投研按钮 → 弹窗

## 前端 — 投研运行详情页

- [ ] `/research/{run_id}` 路由和页面
- [ ] 基本信息区（运行 ID、触发类型、状态、耗时）
- [ ] 阶段进度区（9 个阶段，各阶段状态图标 + 耗时）
- [ ] 展开查看报告（点击阶段 → 加载报告 → Markdown 渲染）
- [ ] SSE 实时更新（阶段状态变化自动刷新）
- [ ] 取消运行按钮

## 前端 — 启动投研弹窗

- [ ] 投研类型选择（完整/趋势/行业/股票）
- [ ] 趋势选择（多选，从活跃趋势列表加载）
- [ ] 行业选择（多选）
- [ ] 启动确认

## 前端 — 报告查看

- [ ] 报告 Markdown 渲染组件
- [ ] 报告元数据展示（阶段、Agent、产出时间）

## 测试

- [ ] 单元测试：StageController 部分启动逻辑
- [ ] 单元测试：ReportCollector 解析 Agent 输出
- [ ] 单元测试：ProposalGenerator 提取提案
- [ ] 单元测试：ProposalLimiter 淘汰逻辑
- [ ] 集成测试：完整 9 阶段投研运行（mock LLM）
- [ ] 集成测试：部分启动（从阶段 4 开始）
- [ ] 集成测试：SSE 事件推送
- [ ] 前端测试：投研启动 → 运行详情 → 报告查看 E2E
