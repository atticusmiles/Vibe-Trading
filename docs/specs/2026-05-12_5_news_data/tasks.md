# 阶段 5 任务清单：每日新闻存档与数据源

## 数据库

- [ ] 创建 news_digests 表（user_id、digest_date、content、summary）
- [ ] 创建 UNIQUE 约束（user_id + digest_date）

## 数据源适配层

- [ ] 新增 `agent/src/datasources/` 模块
- [ ] 定义 DataSource Protocol（get_market_data、search_news）
- [ ] 实现 tushare 适配器（行情 + 财务数据）
- [ ] 实现 akshare 适配器（行情 + 宏观数据）
- [ ] 实现 searxng 适配器（新闻搜索）
- [ ] 实现 DataSourceManager：根据用户配置选择数据源，支持降级回退
- [ ] 数据源读取用户 api_keys JSON 中的配置（tushare token、searxng 地址）

## APScheduler 集成

- [ ] 新增 `agent/src/scheduler/` 模块
- [ ] 集成 AsyncIOScheduler 到 FastAPI lifespan
- [ ] 调度信息持久化到 vibe.db
- [ ] 实现 scheduler 启动时为每个用户注册定时任务
- [ ] 实现定时任务的用户隔离（使用各自的 API Key）

## 每日新闻存档

- [ ] 实现每日新闻分析师 Agent（单 Agent，使用现有 Swarm 单 Agent 模式）
- [ ] Agent 通过 searxng 搜索前一日财经新闻
- [ ] Agent 产出结构化新闻简报（Markdown 格式）
- [ ] 将简报存入 news_digests 表
- [ ] 失败时记录错误日志，不阻塞其他用户
- [ ] 读取用户 settings.news_archive_time 配置（默认 08:00）

## 后端 — 新闻 API

- [ ] `GET /api/news/digests`：列表查询，支持 ?date= 过滤
- [ ] `GET /api/news/digests/{id}`：详情
- [ ] `GET /api/news/digests/latest`：最新一期
- [ ] `POST /api/news/digests/trigger`：手动触发

## 前端 — 新闻简报页

- [ ] `/news` 路由和页面
- [ ] 简报列表（按日期倒序，卡片式展示）
- [ ] 最新标签标识
- [ ] 点击展开详情（Markdown 渲染）
- [ ] 手动触发按钮（调用 trigger API）
- [ ] 导航栏添加新闻入口

## 测试

- [ ] 单元测试：数据源适配器（mock 外部 API）
- [ ] 单元测试：降级回退逻辑（主数据源失败 → 备用数据源）
- [ ] 集成测试：新闻存档任务执行 → news_digests 写入
- [ ] 集成测试：手动触发新闻存档
- [ ] 集成测试：用户隔离（不同用户独立存档）
