# 阶段 6 任务清单：投研引擎

## 数据库

- [ ] 创建 research_candidates 表（id, target_type, name, code, source_context, initial_score, status, source_run_id, research_run_id, report, report_type, reported_at, extra_reports, conclusion, proposal_id, created_at, updated_at）
- [ ] UNIQUE(target_type, name, date(created_at)) 按天去重，次日可重新入选
- [ ] 创建索引 idx_candidates_status(target_type, status)
- [ ] 创建索引 idx_candidates_research_run(research_run_id)

## Agent Tool（3 个）

- [ ] `add_candidates`：批量写入候选（target_type + JSON 数组），写入 source_run_id
- [ ] `update_candidate`：按 (target_type, name) 定位，支持 report / extra_report / status / conclusion
  - [ ] extra_report 参数：追加到 extra_reports JSON 数组
  - [ ] status 仅接受 proposed / passed（researching 由 batch-research 设置）
- [ ] `create_proposal`：封装 proposals service create，创建后自动回写 candidate.proposal_id
- [ ] 验证 3 个 tool 在 build_filtered_registry 中可被正确发现

## Worker 上下文注入

- [ ] Worker 启动时将 user_id、run_id 写入 tool context
- [ ] add_candidates 从 context 注入 source_run_id
- [ ] BaseTool 子类可通过 self.context 访问

## 趋势管线

### scan_trends.yaml

- [ ] trend_scanner agent：fetch_news, fetch_kline, fetch_quote, add_candidates, load_skill
  - [ ] system_prompt：fetch_news(limit=50, days=7) 读 7 天明细 + fetch_news(mode="digest", days=90) 读 90 天摘要，识别候选趋势，宁多勿漏
- [ ] DAG：task-scan（单 task）
- [ ] variables: market

### research_trends.yaml

- [ ] trend_researcher agent：fetch_news, fetch_kline, fetch_quote, fetch_research, update_candidate, load_skill
  - [ ] system_prompt：深度调研候选趋势
  - [ ] update_candidate(name, type, report="...", report_type="macro_analysis")
- [ ] trend_pro agent：update_candidate, load_skill
  - [ ] system_prompt：论证趋势成立的理由 → extra_report
- [ ] trend_con agent：update_candidate, load_skill
  - [ ] system_prompt：论证趋势不成立或风险 → extra_report
- [ ] trend_manager agent：update_candidate, create_proposal, load_skill
  - [ ] system_prompt：综合正反意见做 proposed/passed 决策
  - [ ] 确保候选最终状态非 researching
- [ ] DAG：task-research → task-pro + task-con（并行）→ task-manager
- [ ] variables: candidate_names（JSON 数组，1 个元素）

## 行业管线

### scan_industries.yaml

- [ ] industry_scanner agent：fetch_news, fetch_financial, add_candidates, load_skill
  - [ ] system_prompt：从 {trend_context}（所有 proposed 趋势 + 60 天新闻摘要）读取活跃趋势，识别受益行业
  - [ ] source_context 记录受益趋势
- [ ] DAG：task-scan（单 task）
- [ ] 触发方式：事件驱动（趋势 proposed 时）+ 定时（每天）+ 手动
- [ ] variables: market, trend_context（自动构建）

### research_industries.yaml

- [ ] industry_researcher agent：fetch_financial, fetch_research, fetch_news, update_candidate, load_skill
  - [ ] system_prompt：深度调研候选行业
  - [ ] update_candidate(name, type, report="...", report_type="industry_deep_dive")
- [ ] industry_pro agent：update_candidate, load_skill
  - [ ] system_prompt：论证行业值得投资 → extra_report
- [ ] industry_con agent：update_candidate, load_skill
  - [ ] system_prompt：论证行业风险和不利因素 → extra_report
- [ ] industry_manager agent：update_candidate, create_proposal, load_skill
  - [ ] system_prompt：综合正反意见做 proposed/passed 决策
  - [ ] 确保候选最终状态非 researching
- [ ] DAG：task-research → task-pro + task-con（并行）→ task-manager
- [ ] variables: candidate_names（JSON 数组，1 个元素）

## 股票管线

### scan_stocks.yaml

- [ ] stock_scanner agent：fetch_financial, fetch_news, add_candidates, load_skill
  - [ ] system_prompt：从 {industry_names} 读取已提案行业，每个行业筛选 3-5 只候选股票
  - [ ] 调用 add_candidates 时 code 填股票代码，source_context 记录所属行业
- [ ] DAG：task-scan（单 task）
- [ ] 触发方式：事件驱动（行业 proposed 时）+ 定时（每天）+ 手动
- [ ] variables: market, industry_names（JSON 数组）

### research_stocks.yaml

- [ ] stock_researcher agent：fetch_kline, fetch_quote, fetch_financial, fetch_news, fetch_research, update_candidate, load_skill
  - [ ] system_prompt：深度调研候选股票（技术+基本面+新闻）
  - [ ] update_candidate(name, type, report="...", report_type="tech_analysis")
- [ ] bull_analyst：update_candidate, load_skill — 看涨论点 → extra_report
- [ ] bear_analyst：update_candidate, load_skill — 看跌论点 → extra_report
- [ ] research_manager：update_candidate, load_skill — 投资结论 → extra_report
- [ ] trader：fetch_kline, fetch_quote, update_candidate, load_skill — 交易建议 → extra_report
- [ ] aggressive_analyst：update_candidate, load_skill — 激进风险观点 → extra_report
- [ ] conservative_analyst：update_candidate, load_skill — 保守风险观点 → extra_report
- [ ] neutral_analyst：update_candidate, load_skill — 中立风险观点 → extra_report
- [ ] risk_manager：update_candidate, create_proposal, load_skill
  - [ ] system_prompt：综合所有分析做最终决策
  - [ ] proposed → create_proposal + update_candidate(name, type, "proposed")
  - [ ] passed → update_candidate(name, type, "passed", conclusion="原因")
  - [ ] 确保候选最终状态非 researching
- [ ] DAG：task-research → task-bull + task-bear（并行）→ task-manager → task-trader → task-aggressive + task-conservative + task-neutral（并行）→ task-risk-manager
- [ ] variables: candidate_names（JSON 数组，1 个元素）

## 每个 Agent 的 system_prompt 规范

- [ ] Scanner：广度扫描 → add_candidates（宁多勿漏），写入 source_context 和 initial_score
- [ ] Researcher：深度调研 → update_candidate(name, type, report="...")
- [ ] Pro（趋势/行业）：读取 {upstream_context} → update_candidate(name, type, extra_report={agent_id, title, "支持论点"})
- [ ] Con（趋势/行业）：读取 {upstream_context} → update_candidate(name, type, extra_report={agent_id, title, "反对论点"})
- [ ] Manager（趋势/行业）：综合调研报告 + 正反辩论 → create_proposal + update_candidate(status="proposed"/"passed")
- [ ] 股票多视角分析师：update_candidate(name, type, extra_report={agent_id, title, content})
- [ ] risk_manager（股票）：综合所有分析 → create_proposal + update_candidate(status="proposed"/"passed")
- [ ] 所有 Manager/risk_manager 明确指示：确保候选最终状态非 researching

## 后端 — 调度器

- [ ] 定时调度：scan_trends（每天）、scan_industries（每天）、scan_stocks（每天）
- [ ] 事件驱动：跟踪 research_candidates 表 status 变化
  - [ ] 趋势 proposed → 自动构建 trend_context → 启动 scan_industries
  - [ ] 行业 proposed → 启动 scan_stocks，industry_names 取所有 proposed 行业
- [ ] 保鲜调度：对 trends/industries/stocks 实体表中 proposed + adopted 记录定期重新调研
  - [ ] 趋势：每天，筛选 trends 表 updated_at > 1 天 → research_trends
  - [ ] 行业：每天，筛选 industries 表 updated_at > 1 天 → research_industries
  - [ ] 股票：每天，筛选 stocks 表 updated_at > 1 天 → research_stocks
  - [ ] 保鲜 run 与首次调研一致，researcher 读取旧报告作为上下文
  - [ ] manager 可将 proposed/adopted 改为 passed（条件恶化时）
  - [ ] 保鲜审慎原则：结论无显著差异时仅更新报告，不创建新提案、不改变状态
  - [ ] adopted 降级需充分理由，不能仅因小幅波动

## 后端 — batch-research API + 并发调度

- [ ] `POST /api/research/candidates/batch-research`
  - [ ] 校验：所有候选 target_type 一致 + status = pending
  - [ ] 根据 target_type 自动映射 preset：trend → research_trends, industry → research_industries, stock → research_stocks
  - [ ] 对每个候选：原子更新 status=researching, research_run_id=新 run ID → 启动独立 Swarm run
  - [ ] 按 max_concurrent 控制并发数（默认 3）
  - [ ] 返回所有 run_id 列表

## 后端 — 候选查询 API

- [ ] `GET /api/research/candidates`
  - [ ] 参数：target_type, status
  - [ ] 返回 name, target_type, status, initial_score, conclusion, proposal_id, report, extra_reports
- [ ] `GET /api/research/candidates/{id}`
  - [ ] 返回完整候选信息含 report + extra_reports

## 前端 — 投研中心页

- [ ] `/research` 路由和页面
- [ ] 管线 Tab（趋势 / 行业 / 股票）
- [ ] 待调研候选区：pending 候选列表，支持勾选 + 启动调研
- [ ] 运行历史：按 preset_name 过滤 swarm runs（区分 scan / research）
- [ ] 运行卡片：名称、状态、耗时、候选名
- [ ] 扫描启动按钮 → 扫描弹窗

## 前端 — 运行详情页

- [ ] `/research/{run_id}` 路由
- [ ] 扫描 run：展示发现的候选列表 + 评分 + 入选理由
- [ ] 调研 run：候选进度（单候选），展示 researcher 报告 + pro/con 辩论 + manager 结论
  - [ ] pending：待调研
  - [ ] researching：调研中
  - [ ] proposed：已提案（链接 proposals）
  - [ ] passed：已放弃（显示 conclusion）
- [ ] 展开查看调研报告（ReactMarkdown 渲染）+ extra_reports pro/con 展示
- [ ] SSE 实时更新
- [ ] 取消按钮

## 前端 — 启动弹窗

- [ ] 扫描弹窗：选择扫描类型（趋势/行业/股票）+ 参数
  - [ ] 趋势扫描：market
  - [ ] 行业扫描：market, trend_context（自动读取活跃趋势）
  - [ ] 股票扫描：market, industry_names（选择已提案行业）
- [ ] 调研弹窗：展示勾选的候选列表 → 确认启动
  - [ ] 校验：同类型才能一起调研
- [ ] 启动后跳转详情页（批量启动时跳转到投研中心，可看到多个 run 并行）

## 测试

- [ ] 单元测试：add_candidates 批量写入 + 按天去重（同天跳过，次日可新增）+ source_run_id 写入
- [ ] 单元测试：update_candidate 按 (type, name) 定位，写入 report + extra_report
- [ ] 单元测试：update_candidate extra_report 追加不覆盖
- [ ] 单元测试：create_proposal 调用 proposals service + 回写 proposal_id
- [ ] 单元测试：6 个 YAML DAG 验证（scan 单 task，research: research → pro+con → manager）
- [ ] 单元测试：batch-research 校验（类型不一致拒绝、非 pending 拒绝）
- [ ] 集成测试：mock LLM scan_trends → batch-research → research_trends（researcher → pro/con → manager）
- [ ] 集成测试：并发 batch-research（多个候选同时启动独立 run，互不干扰）
- [ ] 集成测试：mock LLM scan_industries → research_industries（含 parent_id 关联 + pro/con 辩论）
- [ ] 集成测试：mock LLM scan_stocks → research_stocks（9-agent 复杂 DAG + extra_reports 多视角写入）
- [ ] 集成测试：candidates API 过滤 + 详情 + extra_reports + 子候选
- [ ] 集成测试：SSE 事件推送
