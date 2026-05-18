# 阶段 5：数据源集成层

## 1. 概述

**目标**：为 Agent 提供统一的 A 股数据获取接口，覆盖行情、估值、财报、新闻、研报 5 大数据类型。Agent 只关心"我要什么数据"，不关心数据从哪来。

**设计原则**：
- **接口优先**：先定义 Agent 需要的接口签名和返回结构，再决定实现
- **源无关**：Agent 调用 `get_kline("600519")` 不需要知道数据来自 mootdx 还是 baostock
- **自动降级**：主源失败自动切备源，Agent 无感知

**数据源**（4 个，全部零鉴权）：

| 数据源 | 协议 | 核心能力 |
|--------|------|----------|
| mootdx | TCP | K 线（8 周期）、实时盘口（46 字段）、季报快照（37 字段）、F10 九大类 |
| baostock | Socket | K 线 + 估值指标（PE/PB/PS 历史序列）、三大报表、申万行业分类 |
| 腾讯财经 | HTTP | PE/PB/市值/换手率等估值快照（88 字段 `~` 分隔，GBK） |
| akshare | HTTP/爬虫 | 新闻（财联社 + 东财）、研报、一致预期 EPS（限低频） |

**与前后阶段的关系**：
- 依赖阶段 2（用户体系）和阶段 4（提案机制）
- 本阶段产出的数据接口是阶段 6（投研引擎）的核心数据输入

**前置条件**：Python 3.11+，国内网络环境。

## 2. Agent 接口设计

### 2.1 行情接口（K 线 + 实时报价）

Agent 场景：看趋势、算技术指标、回测验证、多股对比。

```python
# 历史K线 — 最常用
async def get_kline(
    code: str,
    period: str = "daily",       # daily/weekly/monthly/1min/5min/15min/30min/60min
    start_date: str | None = None,  # YYYY-MM-DD
    end_date: str | None = None,
    count: int = 120,
) -> list[Bar]
# Bar = {date: str, open: float, high: float, low: float, close: float,
#        volume: float, amount: float}

# 实时报价 — 盘中用
async def get_quote(code: str) -> Quote
# Quote = {price, change, change_pct, volume, amount,
#          open, high, low, pre_close,
#          bid1_price, bid1_vol, ..., ask1_price, ask1_vol, ...}

# 批量报价 — 同时看多只
async def get_quotes(codes: list[str]) -> dict[str, Quote]
```

### 2.2 估值接口

Agent 场景：判断贵不贵、历史分位、同行业对比。

```python
# 当前估值快照
async def get_valuation(code: str) -> Valuation
# Valuation = {pe_ttm, pe_static, pb, ps_ttm,
#              total_mv, circ_mv, turnover,
#              limit_up, limit_down}

# 历史估值序列 — 算分位数用
async def get_valuation_history(
    code: str,
    start_date: str,
    end_date: str,
) -> list[ValuationPoint]
# ValuationPoint = {date, pe_ttm, pb, ps_ttm}
```

### 2.3 财报接口

Agent 场景：基本面分析、筛选优质股、排雷。

```python
# 最新季报摘要 — 快速扫一眼
async def get_financial_snapshot(code: str) -> FinancialSnapshot
# FinancialSnapshot = {eps, bvps, roe, net_profit, revenue,
#                      total_shares, float_shares, ...}

# 完整财务报表 — 深入分析
async def get_financial_statements(
    code: str,
    year: int,
    quarter: int,          # 1-4
    report_type: str,      # "balance" | "income" | "cashflow"
) -> dict

# F10 公司资料 — 公司概况/股东/股本
async def get_f10(code: str, category: str = "all") -> dict

# 行业分类 — 按行业筛选
async def get_industry(code: str) -> IndustryInfo
# IndustryInfo = {industry: str, classification: str}
# e.g. {industry: "银行", classification: "申万一级行业"}
```

### 2.4 新闻接口

Agent 场景：事件驱动、情绪判断、每日简报。

```python
# 财联社快讯 — 市场级，自爬主源
async def get_flash_news(limit: int = 30) -> list[NewsItem]
# NewsItem = {title, content, time, level, source}
# 主源：自爬 cls.cn/nodeapi/telegraphList（HTTPS，零鉴权）
# 备源：akshare stock_info_global_cls

# 个股新闻 — 东财源
async def get_stock_news(code: str, limit: int = 20) -> list[NewsItem]

# 每日新闻总结 — 从库内读取已生成的总结
async def get_news_digest(
    start_date: str | None = None,   # YYYY-MM-DD，默认 7 天前
    end_date: str | None = None,     # YYYY-MM-DD，默认今天
) -> list[NewsDigest]
# NewsDigest = {date, headline, summary, items: [{title, content, source, time}]}
# 返回日期范围内的总结列表，按日期倒序
# 数据来源：flash_news_raw 持续采集 → 每日定时 job 生成总结 → news_digests 表
```

### 2.5 研报接口

Agent 场景：机构预期、目标价参考。

```python
# 一致预期 EPS
async def get_consensus_eps(code: str) -> ConsensusEPS
# ConsensusEPS = {eps_mean, eps_median, org_count, warning?}
# org_count < 3 时 warning = "机构覆盖不足，数据不可信"

# 研报列表
async def get_research_reports(code: str, limit: int = 10) -> list[ResearchReport]
# ResearchReport = {title, org, rating, target_price, date}
```

## 3. 实现策略：接口 → 数据源映射

### 3.1 接口与数据源对照

| 接口 | 主源 | 备源 | 说明 |
|------|------|------|------|
| `get_kline` | mootdx (TCP) | baostock | mootdx 速度快、周期全；baostock 日K降级 |
| `get_quote` / `get_quotes` | mootdx | — | 实时盘口只有 mootdx 提供 |
| `get_valuation` | baostock | 腾讯财经 | baostock 返回结构化估值字段，历史连续 |
| `get_valuation_history` | baostock | — | 历史估值序列只有 baostock 有 |
| `get_financial_snapshot` | mootdx | baostock | mootdx 37 字段快照；baostock 用 `query_profit_data` + `query_balance_data` 等多接口拼装 |
| `get_financial_statements` | baostock | akshare(新浪源) | baostock 三大报表完整 |
| `get_f10` | mootdx | — | F10 九大类，mootdx 独有 |
| `get_industry` | baostock | — | 申万行业分类，baostock 独有 |
| `get_flash_news` | 自爬财联社(HTTPS) | akshare(cls) | 直接爬 `cls.cn/nodeapi/telegraphList`，可控性更强 |
| `get_stock_news` | akshare(东财) | — | 个股新闻 |
| `get_news_digest` | news_digests 表 | — | 从库内读取已生成的每日总结 |
| `get_consensus_eps` | akshare(同花顺) | — | 一致预期 |
| `get_research_reports` | akshare | — | 研报列表 |

### 3.2 降级机制

统一 `fallback` 函数，所有接口内部使用，Agent 无感知：

```
调用主源 → 成功 → 返回数据
         → 失败 → 记录 data_fetch_logs → 调用备源 → 成功 → 返回（标记 fallback）
                                                  → 失败 → 抛 NoDataAvailableError
```

降级失败时抛 `NoDataAvailableError`，由调用方处理。

### 3.3 baostock 生命周期

baostock 需要 login/logout 配对，用上下文管理器封装：

```python
@asynccontextmanager
async def baostock_session():
    bs.login()
    try:
        yield bs
    finally:
        bs.logout()
```

所有 baostock 调用走此管理器。高频场景（如估值）可保持长连接复用。

## 4. 数据源已知陷阱

### mootdx

- `datetime` 同时出现在 DataFrame index 和 column → 先 `drop(columns=["datetime"])` 再 `reset_index()`
- 首次运行自动测速 37 台服务器，生成 `~/.mootdx/config.json`
- 海外 IP 不稳定，需国内网络
- `block()` 和 `minute()` 返回空数据，不可用
- K 线 category 编号：4=日 5=周 6=月 7=1分 8=5分 9=15分 10=30分 11=60分

### 腾讯财经

- 返回 `~` 分隔 88 字段，GBK 编码
- **字段 43 是振幅%，不是 PB**（全网教程写错）。PB 在字段 46
- 关键字段：39=PE(TTM) 44=总市值(亿) 45=流通市值(亿) 46=PB 47=涨停价 48=跌停价 52=PE(静态)

### akshare

- 东财源底层打向东方财富，有反爬，请求间隔 >= 5s
- `stock_balance_sheet_by_report_em` 内部 HTML 解析崩溃 → 改用 `stock_financial_report_sina`
- `stock_profit_forecast_ths` 的 indicator 必须写完整 `"预测年报每股收益"`
- 机构覆盖 < 3 家时一致预期不可信，需输出 warning

### baostock

- 必须 `bs.login()` 才能查询，用完 `bs.logout()`
- 代码格式：`sh.600000` / `sz.000001`（需从 `600000` 转换）
- 估值字段名：`peTTM`, `pbMRQ`, `psTTM`, `pcfNcfTTM`
- 服务器偶发不稳定，需处理连接超时

## 5. 实现参考

**主体逻辑**：按本文档定义的 13 个 Agent 接口 + 数据源映射 + 降级策略实现。

**技术实现**：参考 [SKILL.md](SKILL.md)，内含全部数据源的直连 HTTP 代码、字段映射、踩坑记录。关键对照：

| 本 spec 接口 | SKILL.md 参考 | 核心要点 |
|-------------|--------------|---------|
| `get_kline` / `get_quote` | Layer 1.1 mootdx | `Quotes.factory(market='std')` → `client.bars()` / `client.quotes()`；datetime 双重存在需 drop |
| `get_valuation` | Layer 1.2 腾讯财经 | `qt.gtimg.cn/q=` + GBK 解码；字段索引 46=PB（不是 43）；支持指数/ETF |
| `get_financial_snapshot` | Layer 6.1 mootdx finance | `client.finance(symbol=)` → 37 字段季报快照 |
| `get_f10` | Layer 6.2 mootdx F10 | `client.F10(symbol=, name=)` → 9 大类文本 |
| `get_financial_statements` | Layer 6.4 新浪财报三表 | `quotes.sina.cn` → fzb/lrb/llb 三表 |
| `get_flash_news` | Layer 5.2 财联社 | `cls.cn/nodeapi/telegraphList` → `roll_data` 含 title/content/ctime/level |
| `get_stock_news` | Layer 5.1 东财个股新闻 | `search-api-web.eastmoney.com` JSONP 接口 |
| `get_consensus_eps` | Layer 2.2 同花顺 EPS | `basic.10jqka.com.cn` HTML 解析；机构 < 3 不可信 |
| `get_research_reports` | Layer 2.1 东财研报 | `reportapi.eastmoney.com/report/list`；含 infoCode 可下载 PDF |

**SKILL.md 额外能力**（本 spec 未纳入，后续可扩展）：
- 同花顺热点（强势股 + 题材归因 reason tags）
- 百度 PAE（概念板块 + 分钟资金流）
- 北向资金（同花顺 hsgtApi）
- 龙虎榜 / 解禁 / 融资融券 / 大宗交易 / 股东户数 / 分红
- 百度 K 线带 MA5/MA10/MA20
- 巨潮公告全文检索
- 东财个股基础信息（行业/股本/市值/上市日期）

**实现要点**：
- SKILL.md V3.0 已移除 akshare 依赖，所有数据源改为直连 HTTP API；本 spec 保留 akshare 作为部分接口的降级备源
- SKILL.md 中的 `eastmoney_datacenter()` helper 可直接复用，统一龙虎榜/解禁/融资融券/大宗交易/股东户数/分红的查询模式
- SKILL.md 的 `get_prefix()` 函数与 `base.py` 的 `normalize_code()` 可对齐

## 6. 模块结构

```
agent/src/datasources/
├── __init__.py          # 统一公开 API（导出所有 get_* 函数）
├── base.py              # 异常类 + fallback + TTLCache + normalize_code + baostock_session
├── market.py            # get_kline, get_quote, get_quotes
├── valuation.py         # get_valuation, get_valuation_history
├── fundamental.py       # get_financial_snapshot, get_financial_statements, get_f10, get_industry
├── news.py              # get_flash_news, get_stock_news, get_global_news
└── research.py          # get_consensus_eps, get_research_reports
```

`__init__.py` 导出全部接口，调用方只需：

```python
from src.datasources import get_kline, get_valuation, get_stock_news
```

## 7. 与 Backtest Loaders 的关系

`backtest/loaders/` 服务回测系统（OHLCV），`src/datasources/` 服务 Agent/投研系统。两者独立但共享底层库：

- `backtest/loaders/mootdx.py` — 新增 mootdx OHLCV loader
- `backtest/loaders/baostock_loader.py` — 新增 baostock OHLCV loader
- `src/datasources/market.py` — Agent 用 K 线 + 实时盘口

backtest A 股 fallback chain 调整为：`mootdx → baostock → akshare`。

## 8. Agent Tools

`src/tools/` 下新增工具，注册到 `ToolRegistry` 供 Agent 自动发现：

| 工具 | 调用接口 | 参数 |
|------|---------|------|
| `fetch_kline` | `get_kline` | code, period, count |
| `fetch_quote` | `get_valuation` + `get_quote` | code |
| `fetch_financial` | `get_financial_snapshot` / `get_financial_statements` | code, report_type? |
| `fetch_news` | `get_flash_news` + `get_stock_news` | code?, limit |
| `fetch_research` | `get_consensus_eps` | code |

每个 tool 返回格式化文本给 Agent 上下文。

## 9. 定时任务

### 8.1 APScheduler 集成

- AsyncIOScheduler，绑定 FastAPI lifespan
- 调度信息持久化到 vibe.db

### 8.2 财联社电报持续采集

- **触发频率**：每分钟 1 次
- **执行逻辑**：
  1. 自爬 `https://www.cls.cn/nodeapi/telegraphList`（HTTPS，零鉴权）
  2. 解析 `roll_data`，按 `title + ctime` 去重，新条目写入 `flash_news_raw` 表
  3. akshare `stock_info_global_cls` 作为降级备源
- **数据清理**：每天凌晨自动删除 7 天前的记录
- **用途**：为 `get_news_digest` 提供完整的当日新闻素材

### 8.3 每日新闻总结

- **触发时间**：用户配置 `settings.news_archive_time`（默认 `08:00`）
- **执行逻辑**：
  1. 从 `flash_news_raw` 表读取前一日全量电报
  2. 调用 LLM 产出结构化总结（headline + summary + 分类）
  3. 存入 `news_digests` 表
- **失败处理**：记录日志，不重试

## 10. 数据库

```sql
CREATE TABLE flash_news_raw (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    content     TEXT,
    level       TEXT,                 -- A/B/C 等级
    source      TEXT NOT NULL DEFAULT 'cls',
    published_at TEXT NOT NULL,        -- 原始发布时间
    fetched_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(title, published_at)
);

CREATE TABLE news_digests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    digest_date TEXT NOT NULL,
    content     TEXT NOT NULL,
    summary     TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, digest_date)
);
```

## 11. 后端 API

```
GET    /api/news/digests                   新闻简报列表（?date=YYYY-MM-DD）
GET    /api/news/digests/{id}              简报详情
GET    /api/news/digests/latest            最新一期
POST   /api/news/digests/trigger          手动触发新闻存档
GET    /api/datasources/status             各数据源可用性检查
```

## 12. 验收标准

- [ ] `src/datasources/` 可 import，13 个 `get_*` 接口全部可用
- [ ] mootdx K 线 8 种周期正确，datetime 列处理无误
- [ ] baostock 估值历史序列 + 三大报表 + 行业分类正确
- [ ] 腾讯财经估值字段索引正确（PB 在 46）
- [ ] 新闻三源可用（财联社 + 东财个股 + 全球资讯）
- [ ] 降级回退：主源失败自动切备源，Agent 无感知
- [ ] backtest fallback chain 包含 mootdx + baostock
- [ ] 5 个 Agent tools 注册成功
- [ ] 每日新闻存档正常触发
- [ ] 性能：K 线 < 2s，估值 < 1s，新闻 < 5s
