# 阶段 9：舆情监控

## 1. 概述

**目标**：实现定时舆情监控，自动检测突发新闻和舆情事件，判断与用户关注的相关性，高相关时自动触发部分投研流程。

**与前后阶段的关系**：依赖阶段 5（APScheduler + 数据源 + 新闻搜索）和阶段 6（投研引擎）。本阶段为投研系统增加自动响应能力。

**前置条件**：阶段 5 完成（定时任务框架可用），阶段 6 完成（投研引擎可启动）。

## 2. 数据模型

### alert_events 表

```sql
CREATE TABLE alert_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id),
    event_type        TEXT NOT NULL,             -- news / sentiment
    title             TEXT NOT NULL,
    content           TEXT,
    relevance_score   REAL,                      -- 0~1
    affected_type     TEXT,                      -- trend / industry / stock
    affected_ids      TEXT DEFAULT '[]',         -- JSON array
    triggered_run_id  TEXT REFERENCES research_runs(id),
    created_at        TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_alerts_user ON alert_events(user_id, created_at);
```

## 3. 业务逻辑

### 3.1 定时监控任务

- **频率**：用户配置 `settings.sentinel_interval`（默认 60 分钟）
- **执行 Agent**：舆情监控分析师（单 Agent）
- **输入**：最新新闻/舆情（通过 searxng 搜索）、用户关注列表（活跃趋势 + 活跃行业 + 活跃股票）
- **输出**：事件列表，每条包含相关性评分

### 3.2 相关性判断

舆情监控分析师对每个事件评估相关性：
- **低相关性**（score < 0.5）：记录到 alert_events，不触发投研
- **高相关性**（score >= 0.5）：记录到 alert_events，触发部分投研

### 3.3 自动触发投研

根据影响的对象类型决定起始阶段：

| affected_type | start_stage | 输入 |
|--------------|-------------|------|
| trend | 1 | 舆情事件 + 现有趋势 |
| industry | 2 | 舆情事件 + 现有行业 |
| stock | 4 | 舆情事件 + 现有股票 |

触发的投研运行 `trigger_type` 设为 `alert`，产出的提案正常推送（含飞书通知）。

### 3.4 去重

- 同一事件不重复触发：检查最近 24h 内是否有相同 `title` + `affected_type` 的 alert_event
- 避免短时间内对同一标的重复投研

## 4. API 设计

```
GET    /api/alerts                     舆情事件列表（?relevance=high&affected_type=trend）
GET    /api/alerts/{id}                事件详情
```

## 5. 前端设计

### 5.1 舆情事件页面（`/alerts`）

```
┌───────────────────────────────────────────────────┐
│  舆情监控                                          │
│                                                   │
│  [全部] [高相关] [低相关]                           │
│                                                   │
│  ┌─ 🔴 美联储意外加息 ────────────────────────┐  │
│  │ 相关性：0.92 · 影响趋势：美元降息预期        │  │
│  │ 时间：2026-05-12 14:30                      │  │
│  │ 已触发投研运行 #2026-0512-002  [查看 →]     │  │
│  └─────────────────────────────────────────────┘  │
│                                                   │
│  ┌─ 🟢 某公司财报超预期 ──────────────────────┐  │
│  │ 相关性：0.35 · 未触发                        │  │
│  │ 时间：2026-05-12 13:15                      │  │
│  └─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
```

## 6. 验收标准

- [ ] APScheduler 按用户配置的频率定时运行舆情监控
- [ ] 舆情事件记录到 alert_events 表
- [ ] 高相关性事件自动触发部分投研
- [ ] 触发的投研运行正确选择起始阶段
- [ ] 产出的提案正常推送
- [ ] 去重机制生效（24h 内不重复触发）
- [ ] 前端舆情事件列表页可用
- [ ] 用户可配置监控频率
