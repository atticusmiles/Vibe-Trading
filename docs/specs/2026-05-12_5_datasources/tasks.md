# 阶段 5 任务清单：数据源集成层

## 1. 基础设施（base.py）

- [ ] 安装依赖：`pip install mootdx baostock`，添加到 pyproject.toml
- [ ] 新建 `agent/src/datasources/__init__.py`（空占位）
- [ ] 新建 `agent/src/datasources/base.py`
  - [ ] `DataSourceError` 异常类
  - [ ] `NoDataAvailableError` 异常类（主备源全部失败时抛出）
  - [ ] `fallback(primary_fn, fallback_fn)` 通用降级函数
  - [ ] `TTLCache` 内存缓存（行情数据默认 30s TTL）
  - [ ] `normalize_code(code)` → 转换为 mootdx/腾讯/akshare/baostock 各格式
  - [ ] `baostock_session()` 上下文管理器（login/logout）
- [ ] 数据库 migration：flash_news_raw + news_digests

## 2. 行情层（market.py）

- [ ] `get_kline(code, period, start_date, end_date, count)` → `list[Bar]`
  - [ ] period 字符串映射到 mootdx category 编号（daily→4, weekly→5, ...）
  - [ ] mootdx 返回处理：`drop(columns=["datetime"])` → `reset_index()`
  - [ ] DataFrame → `list[Bar]` 标准化
  - [ ] 降级：mootdx → baostock（日K）
- [ ] `get_quote(code)` → `Quote`
  - [ ] mootdx 实时盘口 46 字段解析
- [ ] `get_quotes(codes)` → `dict[str, Quote]`
  - [ ] 批量获取，单次请求

## 3. 估值层（valuation.py）

- [ ] `get_valuation(code)` → `Valuation`
  - [ ] 主源 baostock：`query_history_k_data_plus` 取最新一行估值字段
  - [ ] 备源腾讯财经：HTTP `~` 分隔 88 字段，GBK 解码
  - [ ] 字段校准：46=PB（不是 43）
- [ ] `get_valuation_history(code, start_date, end_date)` → `list[ValuationPoint]`
  - [ ] baostock `query_history_k_data_plus` peTTM/pbMRQ/psTTM 字段

## 4. 财报层（fundamental.py）

- [ ] `get_financial_snapshot(code)` → `FinancialSnapshot`
  - [ ] 主源 mootdx 季报快照 37 字段（EPS/ROE/净利润/营收等）
  - [ ] 备源 baostock：`query_profit_data` + `query_balance_data` + `query_growth_data` 等多接口拼装
- [ ] `get_financial_statements(code, year, quarter, report_type)` → `dict`
  - [ ] report_type="balance" → baostock `query_balance_data()`
  - [ ] report_type="income" → baostock `query_profit_data()`
  - [ ] report_type="cashflow" → baostock `query_cash_flow_data()`
  - [ ] 降级：baostock → akshare `stock_financial_report_sina`
- [ ] `get_f10(code, category)` → `dict`
  - [ ] mootdx F10 九大类
- [ ] `get_industry(code)` → `IndustryInfo`
  - [ ] baostock `query_stock_industry()` → 申万行业分类

## 5. 新闻层（news.py）

- [ ] `get_flash_news(limit)` → `list[NewsItem]`
  - [ ] 主源：自爬 `cls.cn/nodeapi/telegraphList`（HTTPS，零鉴权）
  - [ ] 解析 `roll_data`：title, content, ctime→上海时区, level(A/B/C)
  - [ ] 备源：akshare `stock_info_global_cls`
- [ ] `get_stock_news(code, limit)` → `list[NewsItem]`
  - [ ] akshare `stock_news_em`（东财源）
- [ ] `get_news_digest(start_date, end_date)` → `list[NewsDigest]`
  - [ ] 从 `news_digests` 表按日期范围查询
  - [ ] start_date 默认 7 天前，end_date 默认今天
  - [ ] 按日期倒序返回
- [ ] 简易缓存：同一 code 5 分钟内不重复请求

## 6. 研报层（research.py）

- [ ] `get_consensus_eps(code)` → `ConsensusEPS`
  - [ ] akshare `stock_profit_forecast_ths`，indicator = `"预测年报每股收益"`
  - [ ] org_count < 3 时附加 warning
- [ ] `get_research_reports(code, limit)` → `list[ResearchReport]`

## 7. 统一入口（__init__.py）

- [ ] 导出全部 13 个 `get_*` 函数
- [ ] `__all__` 列表
- [ ] 验证 `from src.datasources import get_kline, ...` 正常

## 8. Backtest Loader 扩展

- [ ] `agent/backtest/loaders/mootdx.py`
  - [ ] `MootdxLoader(DataLoaderProtocol)` — name="mootdx", markets={"a_share"}
  - [ ] `is_available()` → 检查 mootdx 可 import + 网络可达
  - [ ] `fetch()` → 标准化 OHLCV DataFrame
  - [ ] `@register` 注册
- [ ] `agent/backtest/loaders/baostock_loader.py`
  - [ ] `BaostockLoader(DataLoaderProtocol)` — name="baostock", markets={"a_share"}
  - [ ] `is_available()` → 检查 baostock 可 import
  - [ ] `fetch()` → baostock K 线 + login/logout 生命周期
  - [ ] `@register` 注册
- [ ] 更新 `registry.py`：`a_share: ["mootdx", "baostock", "akshare"]`

## 9. Agent Tools

- [ ] `src/tools/fetch_kline.py` — FetchKLineTool(code, period, count) → get_kline
- [ ] `src/tools/fetch_quote.py` — FetchQuoteTool(code) → get_valuation + get_quote
- [ ] `src/tools/fetch_financial.py` — FetchFinancialTool(code, report_type?) → get_financial_snapshot / get_financial_statements
- [ ] `src/tools/fetch_news.py` — FetchNewsTool(code?, limit) → get_flash_news + get_stock_news
- [ ] `src/tools/fetch_research.py` — FetchResearchTool(code) → get_consensus_eps
- [ ] 验证 ToolRegistry 自动注册

## 10. APScheduler + 新闻管道

- [ ] `src/scheduler/__init__.py` — AsyncIOScheduler 集成到 FastAPI lifespan
- [ ] 调度持久化到 vibe.db

### 10.1 财联社电报持续采集（每分钟）

- [ ] 定时任务：每分钟自爬 `cls.cn/nodeapi/telegraphList`
- [ ] 解析 `roll_data`，按 `title + ctime` 去重写入 `flash_news_raw`
- [ ] 每天凌晨清理 7 天前的记录

### 10.2 每日新闻总结（定时 job）

- [ ] 从 `flash_news_raw` 读取前一日全量电报
- [ ] 调用 LLM 产出结构化总结（headline + summary + 分类 items）
- [ ] 写入 `news_digests` 表
- [ ] 读取 `settings.news_archive_time`（默认 08:00）

## 11. 后端 API

- [ ] `GET /api/news/digests` — 列表（?date= 过滤）
- [ ] `GET /api/news/digests/{id}` — 详情
- [ ] `GET /api/news/digests/latest` — 最新一期
- [ ] `POST /api/news/digests/trigger` — 手动触发
- [ ] `GET /api/datasources/status` — 数据源可用性检查

## 12. 前端

- [ ] `/news` 路由和页面
- [ ] 简报列表（日期倒序，卡片式）
- [ ] 最新标签 + 点击展开详情（Markdown）
- [ ] 手动触发按钮
- [ ] 导航栏新闻入口

## 13. 测试

### 单元测试

- [ ] mootdx K 线 + datetime 处理（mock TCP）
- [ ] mootdx 盘口 46 字段解析
- [ ] baostock 代码格式转换（600000 → sh.600000）
- [ ] baostock login/logout 上下文管理器
- [ ] baostock 估值历史序列解析
- [ ] baostock 三大报表解析
- [ ] 腾讯财经估值解析（字段 46=PB，GBK 解码）
- [ ] akshare 新闻三源解析
- [ ] akshare 一致预期（org_count < 3 warning）
- [ ] fallback 降级逻辑（主源失败 → 备源成功）
- [ ] normalize_code 4 种格式
- [ ] TTLCache 过期清理

### 集成测试

- [ ] datasources 模块 import，13 个接口可调用
- [ ] backtest mootdx + baostock loader 注册
- [ ] fallback chain：mootdx → baostock → akshare
- [ ] Agent tools 自动注册
- [ ] 新闻存档 → news_digests 写入
- [ ] 手动触发新闻存档
