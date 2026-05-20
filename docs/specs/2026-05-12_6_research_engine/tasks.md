# 阶段 6 任务清单：投研引擎

## Phase 1: 数据库 + fetch_news 扩展 + 上下文注入

### 1.1 DB migration 10

- [ ] `agent/src/db/database.py` — `_SCHEMA_VERSION` 9→10
- [ ] 创建 `research_candidates` 表（id, target_type, name, code, source_context, initial_score, status, source_run_id, research_run_id, report, report_type, reported_at, extra_reports, conclusion, proposal_id, created_at, updated_at）
- [ ] `UNIQUE(target_type, name, date(created_at))` 按天去重
- [ ] 索引 `idx_candidates_status(target_type, status)`
- [ ] 索引 `idx_candidates_research_run(research_run_id)`

### 1.2 fetch_news 扩展

- [ ] `agent/src/tools/fetch_news.py` — 新增 `mode` 参数（"digest" 调用 `get_news_digest`）
- [ ] 新增 `days` 参数（按天数过滤）
- [ ] 支持 `fetch_news(mode="digest", days=90)` 和 `fetch_news(days=7)`

### 1.3 Worker 上下文注入

- [ ] `agent/src/swarm/worker.py` — 将 `_run_id`、`_user_id` 从 `user_vars` 注入到 tool kwargs
- [ ] Tools 通过 `kwargs.get("_run_id")` / `kwargs.get("_user_id")` 读取，无需修改 BaseTool

## Phase 2: 2 个 Agent Tool

### 2.1 `manage_candidates` — 新建 `agent/src/tools/manage_candidates_tool.py`

- [ ] `ManageCandidatesTool(BaseTool)`：name="manage_candidates", is_readonly=False, repeatable=True
- [ ] 参数：`action`（add / update）, `target_type`, `target_name`, `candidates`（add 时）, `report`, `report_type`, `extra_report`, `status`, `conclusion`, `code`, `score`, `reason`
- [ ] action="add"：批量写入候选（target_type + candidates JSON 数组），INSERT OR IGNORE 按天去重，从 `kwargs["_run_id"]` 写入 source_run_id
- [ ] action="update"：按 `(target_type, target_name)` 定位最新候选
  - 支持 `report` + `report_type` + `reported_at` 写入
  - `extra_report` 追加到 JSON 数组，不覆盖
  - `status` 仅接受 `proposed` / `passed`（`researching` 由 batch-research API 设置）
  - `conclusion` 记录决策原因
  - status 变为 `proposed` 时延迟导入调用 `check_event_triggers(target_type)`

### 2.2 `manage_proposals` — 新建 `agent/src/tools/manage_proposals_tool.py`

- [ ] `ManageProposalsTool(BaseTool)`：name="manage_proposals", is_readonly=False, repeatable=True
- [ ] 参数：`action`（create / update / cancel）, `target_type`, `target_name`, `title`, `payload`, `confidence`, `conclusion`, `summary`
- [ ] action="create"：创建 proposal + 原子更新 candidate status=proposed + 回写 proposal_id + 触发事件检查
- [ ] action="update"：保鲜时结论显著变化，更新已有 proposal 的 payload
- [ ] action="cancel"：取消已有 proposal（proposal status→cancelled，candidate status→passed）
- [ ] 直接 DB 操作（不绕 HTTP 层），从 `kwargs["_user_id"]` 读取用户 ID

### 2.3 验证

- [ ] 确认 `build_filtered_registry(["manage_candidates", "manage_proposals"])` 可发现 2 个 tool

## Phase 3: 6 个 YAML Preset

所有文件位于 `agent/src/swarm/presets/`，**所有 system_prompt 使用中文**。

### 3.1 `scan_trends.yaml`

- [ ] 单 agent `trend_scanner`，tools: `[fetch_news, fetch_kline, fetch_quote, add_candidates, load_skill]`
- [ ] system_prompt（中文）：fetch_news(days=7) 读 7 天明细 + fetch_news(mode="digest", days=90) 读 90 天摘要，识别候选趋势，宁多勿漏
- [ ] DAG：`task-scan`（单 task）
- [ ] variables: `market`, `existing_trends`（当前 proposed+adopted 趋势列表，启动时注入）

### 3.2 `research_trends.yaml`

- [ ] 4 agents：`trend_researcher`, `trend_pro`, `trend_con`, `trend_manager`
- [ ] DAG：`task-research → task-pro + task-con（并行）→ task-manager`
- [ ] input_from：pro/con 读 task-research；manager 读 task-research + task-pro + task-con
- [ ] trend_researcher system_prompt：深度调研，`update_candidate(name, type, report="...", report_type="macro_analysis")`
- [ ] trend_pro system_prompt：读取 {upstream_context}，论证趋势成立 → `extra_report`
- [ ] trend_con system_prompt：读取 {upstream_context}，论证趋势不成立或风险 → `extra_report`
- [ ] trend_manager system_prompt：综合正反意见做 proposed/passed 决策，保鲜时审慎原则
- [ ] variables: `candidate_names`, `candidate_info`, `existing_trends`

### 3.3 `scan_industries.yaml`

- [ ] 单 agent `industry_scanner`，tools: `[fetch_news, fetch_financial, add_candidates, load_skill]`
- [ ] system_prompt（中文）：从 {trend_context}（所有 proposed 趋势 + 60 天新闻摘要）读取活跃趋势，识别受益行业，source_context 记录受益趋势
- [ ] DAG：`task-scan`（单 task）
- [ ] 触发方式：事件驱动（趋势 proposed 时）+ 定时（每天）+ 手动
- [ ] variables: `market`, `trend_context`（自动构建）, `existing_industries`

### 3.4 `research_industries.yaml`

- [ ] 4 agents：`industry_researcher`, `industry_pro`, `industry_con`, `industry_manager`
- [ ] DAG：同 research_trends
- [ ] industry_researcher system_prompt：深度调研，景气度/产业链/竞争格局，`update_candidate(name, type, report="...", report_type="industry_deep_dive")`
- [ ] industry_pro / industry_con：同趋势管线模式，输出 extra_report
- [ ] industry_manager system_prompt：综合正反意见做决策，保鲜时审慎原则
- [ ] variables: `candidate_names`, `candidate_info`, `related_trends`, `existing_industries`

### 3.5 `scan_stocks.yaml`

- [ ] 单 agent `stock_scanner`，tools: `[fetch_financial, fetch_news, add_candidates, load_skill]`
- [ ] system_prompt（中文）：从 {industry_names} 读取已提案行业，每个行业筛选 3-5 只候选股票，code 填股票代码，source_context 记录所属行业
- [ ] DAG：`task-scan`（单 task）
- [ ] 触发方式：事件驱动（行业 proposed 时）+ 定时（每天）+ 手动
- [ ] variables: `market`, `industry_names`, `industry_details`, `existing_stocks`, `current_portfolio`

### 3.6 `research_stocks.yaml`

- [ ] 9 agents：`stock_researcher`, `bull_analyst`, `bear_analyst`, `research_manager`, `trader`, `aggressive_analyst`, `conservative_analyst`, `neutral_analyst`, `risk_manager`
- [ ] DAG：`task-research → task-bull + task-bear（并行）→ task-manager → task-trader → task-aggressive + task-conservative + task-neutral（并行）→ task-risk-manager`
- [ ] stock_researcher：tools `[fetch_kline, fetch_quote, fetch_financial, fetch_news, fetch_research, update_candidate, load_skill]`，深度调研，`update_candidate(name, type, report="...", report_type="tech_analysis")`
- [ ] bull_analyst / bear_analyst：`[update_candidate, load_skill]`，看涨/看跌论点 → extra_report
- [ ] research_manager：`[update_candidate, load_skill]`，投资结论 → extra_report
- [ ] trader：`[fetch_kline, fetch_quote, update_candidate, load_skill]`，交易建议（入场/止损/止盈位）→ extra_report
- [ ] aggressive / conservative / neutral_analyst：`[update_candidate, load_skill]`，三视角风险观点 → extra_report
- [ ] risk_manager：`[update_candidate, create_proposal, load_skill]`，综合所有分析做最终决策，保鲜时审慎原则
- [ ] variables: `candidate_names`, `candidate_info`, `related_industry`, `existing_stocks`, `current_portfolio`, `existing_stock`（保鲜时）

## Phase 4: API 端点

### 4.1 candidates API — 新建 `agent/src/research/candidates.py`

- [ ] `GET /api/research/candidates` — 按 target_type / status 过滤，返回列表
- [ ] `GET /api/research/candidates/{id}` — 完整候选详情含 report + extra_reports
- [ ] `POST /api/research/candidates/batch-research`
  - [ ] 校验：所有候选 target_type 一致 + status = pending
  - [ ] target_type → preset 映射：trend → research_trends, industry → research_industries, stock → research_stocks
  - [ ] 对每个候选：原子更新 `status=researching, research_run_id=新 ID` → 启动独立 Swarm run
  - [ ] user_vars 注入 `_run_id`, `_user_id`, `candidate_names`, `candidate_info`, `existing_*` 等上下文
  - [ ] 按 `max_concurrent` 控制并发数（默认 3）
  - [ ] 返回所有 run_id 列表

### 4.2 路由注册

- [ ] `agent/src/research/__init__.py` — 注册 candidates 模块路由

## Phase 5: 调度器 + 事件驱动

### 5.1 定时调度 — 修改 `agent/src/scheduler/__init__.py`

- [ ] 辅助函数 `_run_preset(name, vars)` — 懒加载 SwarmRuntime，启动 Swarm run
- [ ] 每天 08:30 — `scan_trends`（market="A-shares"）
- [ ] 每天 09:00 — `scan_industries`（自动构建 trend_context：所有 proposed 趋势 + 60 天新闻摘要）
- [ ] 每天 09:30 — `scan_stocks`（industry_names 取所有 proposed 行业）

### 5.2 保鲜调度

- [ ] 每天 10:00 — 保鲜趋势：筛选 trends 表 `updated_at > 1 天` 且 `status IN (proposed, adopted)` → 为每条创建临时候选 → research_trends
- [ ] 每天 10:30 — 保鲜行业：筛选 industries 表 → research_industries
- [ ] 每天 11:00 — 保鲜股票：筛选 stocks 表 → research_stocks
- [ ] 保鲜 run 与首次调研一致，researcher 读取旧报告作为上下文
- [ ] 保鲜审慎原则：结论无显著差异时仅更新报告，不创建新提案、不改变状态
- [ ] adopted 降级需充分理由，不能仅因小幅波动

### 5.3 事件驱动 — 新建 `agent/src/scheduler/events.py`

- [ ] `check_event_triggers(target_type)` — 由 update_candidate_tool 延迟导入调用
- [ ] 趋势 proposed → 自动构建 trend_context → 启动 scan_industries
- [ ] 行业 proposed → 启动 scan_stocks，industry_names 取所有 proposed 行业

## Phase 6: 测试

### 6.1 Tool 单元测试 — `agent/tests/test_candidates_tools.py`

- [ ] `test_add_candidates_batch_insert` — 批量写入
- [ ] `test_add_candidates_daily_dedup` — 同天跳过，次日可新增
- [ ] `test_add_candidates_source_run_id` — _run_id 注入
- [ ] `test_update_candidate_report` — 按 (type, name) 定位，写入 report
- [ ] `test_update_candidate_extra_report_append` — 追加不覆盖
- [ ] `test_update_candidate_status_change` — status 变为 proposed/passed
- [ ] `test_update_candidate_rejects_researching` — agent 不能设置 researching
- [ ] `test_create_proposal_creates_and_backlinks` — 创建 proposal + 回写 proposal_id

### 6.2 YAML 验证 — `agent/tests/test_research_presets.py`

- [ ] `test_all_presets_loadable` — 6 个 preset 可加载
- [ ] `test_scan_trends_dag` — 单 task，无依赖
- [ ] `test_research_trends_dag` — 4 task，正确依赖链
- [ ] `test_scan_industries_dag` — 单 task
- [ ] `test_research_industries_dag` — 同 research_trends 模式
- [ ] `test_scan_stocks_dag` — 单 task
- [ ] `test_research_stocks_dag` — 9 agent，7 层 DAG 拓扑
- [ ] `test_all_presets_variables_declared` — variables 声明与 prompt 模板匹配

### 6.3 API 测试 — `agent/tests/test_candidates_api.py`

- [ ] `test_list_candidates_filter` — 按 target_type / status 过滤
- [ ] `test_get_candidate_detail` — 返回 report + extra_reports
- [ ] `test_batch_research_validates_type_consistency` — 拒绝混合类型
- [ ] `test_batch_research_validates_pending_status` — 拒绝非 pending
- [ ] `test_batch_research_maps_preset` — target_type → preset 映射正确
- [ ] `test_batch_research_marks_researching` — 原子设置 status=researching

### 6.4 fetch_news 扩展测试

- [ ] `test_fetch_news_digest_mode` — mode="digest" 返回摘要
- [ ] `test_fetch_news_with_days_filter` — days=7 过滤原始新闻日期

## 前端（后续阶段）

### 投研中心页 `/research`

- [ ] 路由和页面
- [ ] 管线 Tab（趋势 / 行业 / 股票）
- [ ] 待调研候选区：pending 候选列表，支持勾选 + 启动调研
- [ ] 运行历史：按 preset_name 过滤 swarm runs
- [ ] 扫描启动按钮 → 扫描弹窗

### 运行详情页 `/research/{run_id}`

- [ ] 扫描 run：展示发现的候选列表 + 评分 + 入选理由
- [ ] 调研 run：展示 researcher 报告 + pro/con 辩论 + manager 结论
- [ ] 展开查看调研报告（ReactMarkdown）+ extra_reports
- [ ] SSE 实时更新 + 取消按钮

### 启动弹窗

- [ ] 扫描弹窗：选择扫描类型 + 参数
- [ ] 调研弹窗：展示勾选候选列表 → 确认启动，校验同类型
