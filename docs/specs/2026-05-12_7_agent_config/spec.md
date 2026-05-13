# 阶段 7：Agent 配置

## 1. 概述

**目标**：实现 Agent 配置管理，用户可查看系统默认配置，自定义系统提示词、选择启用的技能和工具。投研运行时使用用户自定义配置，未自定义的回退使用默认值。

**与前后阶段的关系**：依赖阶段 2 的用户体系。投研引擎（阶段 6）在运行时读取 Agent 配置，本阶段为投研引擎提供可定制能力。

**前置条件**：阶段 2 完成，阶段 6 的 preset YAML 已定义 Agent 列表。

## 2. 数据模型

### agent_configs 表

```sql
CREATE TABLE agent_configs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    agent_id        TEXT NOT NULL,            -- 对应 preset 中的 agent id
    system_prompt   TEXT,                     -- 用户自定义提示词，NULL 表示使用默认
    enabled_skills  TEXT,                     -- JSON array，NULL 表示使用默认
    enabled_tools   TEXT,                     -- JSON array，NULL 表示使用默认
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, agent_id)
);
```

## 3. API 设计

```
GET    /api/agents                         获取 Agent 列表及配置概览
GET    /api/agents/{agent_id}              单个 Agent 配置详情（含默认值 + 用户自定义）
PUT    /api/agents/{agent_id}              更新用户自定义配置
DELETE /api/agents/{agent_id}              恢复默认配置（删除用户自定义记录）
GET    /api/agents/{agent_id}/skills       获取该 Agent 可用的系统内置技能列表
GET    /api/agents/{agent_id}/tools        获取该 Agent 可用的系统内置工具列表
```

### GET /api/agents/{agent_id} 响应

```json
{
    "agent_id": "macro_analyst",
    "name": "宏观分析师",
    "default_system_prompt": "你是一位宏观分析师...",
    "default_skills": ["data_source.tushare", "analysis.macro"],
    "default_tools": ["search_web", "read_file"],
    "custom_system_prompt": null,
    "custom_skills": null,
    "custom_tools": null,
    "effective_system_prompt": "你是一位宏观分析师...",
    "effective_skills": ["data_source.tushare", "analysis.macro"],
    "effective_tools": ["search_web", "read_file"]
}
```

`effective_*` 字段：有自定义值用自定义，否则用默认值。

## 4. 业务逻辑

### 4.1 默认配置

- 默认值硬编码在投研 preset YAML 中
- 系统内置技能和工具列表从 `src/skills/` 和 `src/tools/` 自动发现
- 每个 Agent 默认关联一组技能和工具（在 YAML 中定义）

### 4.2 自定义配置

- 用户通过 PUT 接口修改某个 Agent 的配置
- 仅存储用户修改的字段，NULL 字段表示"使用默认"
- 投研运行时读取 effective 配置

### 4.3 恢复默认

- DELETE 请求删除用户自定义记录
- 下次读取时回退到默认值

### 4.4 投研运行时读取

- 投研引擎启动时，为每个 Agent 查询 agent_configs
- 有自定义用自定义，无自定义用 YAML 默认值
- 注入到 SwarmRuntime 的 Agent 配置中

## 5. 前端设计

### 5.1 Agent 列表页（`/agents`）

```
┌───────────────────────────────────────────────┐
│  Agent 配置                                    │
│                                               │
│  ┌─ 宏观分析师 ────────────────────────────┐  │
│  │ 提示词：默认 ☑  技能：默认 ☑  工具：默认 ☑│  │
│  │ [自定义]                                 │  │
│  └──────────────────────────────────────────┘  │
│                                               │
│  ┌─ 行业分析师 ────────────────────────────┐  │
│  │ 提示词：已自定义  技能：默认 ☑  工具：默认 ☑│  │
│  │ [编辑] [恢复默认]                        │  │
│  └──────────────────────────────────────────┘  │
│  ...                                          │
└───────────────────────────────────────────────┘
```

### 5.2 Agent 配置编辑页

```
┌───────────────────────────────────────────────┐
│  宏观分析师 — 配置                             │
│                                               │
│  系统提示词                                    │
│  ┌───────────────────────────────────────┐    │
│  │ [使用默认 ☐]                           │    │
│  │ 你是一位宏观分析师，负责...（可编辑）   │    │
│  └───────────────────────────────────────┘    │
│                                               │
│  启用技能                                      │
│  ☑ data_source.tushare                        │
│  ☑ analysis.macro                             │
│  ☐ data_source.akshare                        │
│                                               │
│  启用工具                                      │
│  ☑ search_web                                 │
│  ☑ read_file                                  │
│  ☐ write_file                                 │
│                                               │
│  [保存] [恢复默认] [取消]                      │
└───────────────────────────────────────────────┘
```

## 6. 验收标准

- [ ] 可查看所有 Agent 的默认配置
- [ ] 可自定义系统提示词
- [ ] 可选择启用的技能和工具（从系统内置列表中勾选）
- [ ] 可恢复默认配置
- [ ] 投研运行时使用 effective 配置
- [ ] 前端 Agent 列表页展示所有 Agent 及其配置状态
- [ ] 前端编辑页可修改提示词、勾选技能和工具
