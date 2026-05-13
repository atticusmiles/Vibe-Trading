# 阶段 10：记忆系统

## 1. 概述

**目标**：集成 ChromaDB 实现语义记忆，Agent 可跨投研运行存取非结构化洞察（经验教训、分析模式、历史判断），按用户隔离。

**与前后阶段的关系**：依赖阶段 2（用户隔离）和阶段 6（投研引擎）。本阶段为 Agent 提供长期记忆能力，提升分析质量。

**前置条件**：阶段 6 完成，投研引擎可运行。

## 2. 两层记忆架构

| 层级 | 存储 | 内容 | 检索方式 |
|------|------|------|---------|
| 结构化记忆 | SQLite (vibe.db) | 事实表 + 投研报告 + 审计日志 | SQL 查询 |
| 非结构化记忆 | ChromaDB | Agent 洞察、经验教训、分析模式 | 语义搜索 |

结构化记忆已在前面阶段实现（事实表 CRUD、research_reports 查询）。本阶段新增非结构化记忆层。

## 3. ChromaDB 配置

```
存储路径：$DATA_DIR/chroma/
底层存储：SQLite（ChromaDB 默认后端）
备份方式：随 DATA_DIR 整体备份
```

## 4. 业务逻辑

### 4.1 Collection 设计

每个用户一个 Collection，命名为 `user_{user_id}_memory`。

### 4.2 写入记忆

Agent 执行完成后，从输出中提取非结构化洞察写入 ChromaDB：

```
collection.add(
    ids=["memory_{uuid}"],
    documents=["新能源行业评级由中性上调至看好，理由是政策支持力度加大..."],
    metadatas=[{
        "user_id": 1,
        "memory_type": "insight",         # insight / lesson / context / summary
        "source_agent": "industry_analyst",
        "related_type": "industry",       # trend / industry / stock
        "related_id": 42,
        "run_id": "2026-0512-001",
        "created_at": "2026-05-12T14:30:00"
    }]
)
```

### 4.3 读取记忆

Agent 执行前，语义搜索相关记忆作为上下文注入：

```
collection.query(
    query_texts=["新能源行业的历史分析结论"],
    where={"user_id": user_id},
    n_results=5
)
```

支持 metadata 过滤组合：
- `where={"source_agent": "macro_analyst"}` — 某个 Agent 的历史洞察
- `where={"related_type": "industry", "related_id": 42}` — 某个行业的所有记忆
- `where={"memory_type": "lesson"}` — 经验教训

### 4.4 记忆生命周期

- 无自动过期，所有记忆永久保留
- 后续可扩展：定期清理低质量记忆、合并重复记忆

## 5. API 设计

```
GET    /api/memories                    查询记忆（?query=语义搜索&q_type=&agent=&related_type=）
DELETE /api/memories/{id}               删除指定记忆
GET    /api/memories/stats              记忆统计（数量、按类型分布）
```

## 6. 投研引擎集成

投研引擎的每个 Agent 执行前：
1. 从 ChromaDB 搜索与当前分析相关的历史记忆
2. 注入 Agent 的 system prompt 作为上下文
3. Agent 执行完成后，提取洞察写入 ChromaDB

## 7. 前端设计

### 7.1 记忆管理页面（`/memories`）

```
┌───────────────────────────────────────────────────┐
│  Agent 记忆                         [搜索...]      │
│                                                   │
│  [全部] [洞察] [教训] [摘要]                        │
│                                                   │
│  ┌─ 洞察 · 宏观分析师 · 2026-05-12 ──────────┐   │
│  │ 新能源行业评级由中性上调至看好...           │   │
│  │ 关联：新能源行业  来源：运行 #2026-0512-01 │   │
│  └─────────────────────────────────────────────┘  │
│                                                   │
│  统计：共 128 条记忆  洞察 89 | 教训 23 | 摘要 16   │
└───────────────────────────────────────────────────┘
```

## 8. 验收标准

- [ ] ChromaDB 正确初始化，数据存储在 `$DATA_DIR/chroma/`
- [ ] Agent 执行完成后自动写入非结构化记忆
- [ ] 语义搜索可按自然语言查询召回相关记忆
- [ ] metadata 过滤正确（按 Agent、类型、关联对象）
- [ ] 用户隔离：不同用户的记忆完全隔离
- [ ] 投研引擎的 Agent 可读取历史记忆作为上下文
- [ ] 前端记忆管理页面可用（列表、搜索、统计）
