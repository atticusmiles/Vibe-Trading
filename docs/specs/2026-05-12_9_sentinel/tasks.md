# 阶段 9 任务清单：舆情监控

## 数据库

- [ ] 创建 alert_events 表（user_id、event_type、title、content、relevance_score、affected_type、affected_ids、triggered_run_id）
- [ ] 创建索引（user_id + created_at）

## 后端 — 舆情监控任务

- [ ] 在 APScheduler 中注册舆情监控定时任务
- [ ] 按用户隔离运行（读取各自的关注列表和 API Key）
- [ ] 读取用户 settings.sentinel_interval 配置（默认 60 分钟）
- [ ] 调用舆情监控分析师 Agent
- [ ] Agent 输入：最新新闻 + 用户关注列表（活跃趋势/行业/股票）
- [ ] Agent 输出：事件列表（标题、内容、相关性评分、影响类型）

## 后端 — 事件处理

- [ ] 事件写入 alert_events 表
- [ ] 去重检查：24h 内相同 title + affected_type 不重复记录
- [ ] 低相关性事件（score < 0.5）：仅记录
- [ ] 高相关性事件（score >= 0.5）：记录 + 触发投研

## 后端 — 自动触发投研

- [ ] 根据 affected_type 决定 start_stage
- [ ] 创建投研运行（trigger_type=alert）
- [ ] 去重：同一标的 24h 内不重复触发
- [ ] 触发飞书通知（如已集成）

## 后端 — API

- [ ] `GET /api/alerts`：事件列表（支持 ?relevance=high&affected_type= 过滤）
- [ ] `GET /api/alerts/{id}`：事件详情

## 前端

- [ ] `/alerts` 路由和页面
- [ ] 事件列表（卡片式，按时间倒序）
- [ ] 相关性标签（高/低，颜色区分）
- [ ] 已触发投研的显示运行链接
- [ ] 影响对象标签（趋势/行业/股票 + 名称）
- [ ] 筛选 Tab（全部/高相关/低相关）
- [ ] 导航栏添加舆情入口

## 测试

- [ ] 单元测试：相关性判断逻辑
- [ ] 单元测试：去重逻辑
- [ ] 单元测试：affected_type → start_stage 映射
- [ ] 集成测试：舆情事件 → 自动触发投研 → 产出提案
- [ ] 集成测试：低相关事件不触发投研
