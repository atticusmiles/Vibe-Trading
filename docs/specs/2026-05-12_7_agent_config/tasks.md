# 阶段 7 任务清单：Agent 配置

## 数据库

- [ ] 创建 agent_configs 表（user_id、agent_id、system_prompt、enabled_skills、enabled_tools）
- [ ] 创建 UNIQUE 约束（user_id + agent_id）

## 后端 — Agent 配置 API

- [ ] `GET /api/agents`：列表，从 preset YAML 读取 18 个 Agent 的基本信息
- [ ] `GET /api/agents/{agent_id}`：详情，合并默认值和用户自定义值，返回 effective_* 字段
- [ ] `PUT /api/agents/{agent_id}`：更新自定义配置（仅存储非 NULL 字段）
- [ ] `DELETE /api/agents/{agent_id}`：删除用户自定义记录（恢复默认）
- [ ] `GET /api/agents/{agent_id}/skills`：从 `src/skills/` 自动发现技能列表
- [ ] `GET /api/agents/{agent_id}/tools`：从 `src/tools/` 自动发现工具列表

## 后端 — 投研运行集成

- [ ] 投研引擎启动时为每个 Agent 查询 agent_configs
- [ ] 合并逻辑：有自定义用自定义，无自定义用 YAML 默认值
- [ ] 注入 effective 配置到 SwarmRuntime

## 前端 — Agent 列表页

- [ ] `/agents` 路由和页面
- [ ] Agent 列表卡片（名称、角色描述、配置状态标签：默认/已自定义）
- [ ] 点击进入编辑页或弹窗

## 前端 — Agent 编辑页

- [ ] Agent 编辑表单组件
- [ ] 系统提示词编辑（大文本框，显示默认值，可覆盖）
- [ ] 技能勾选列表（从 API 加载可用技能，checkbox）
- [ ] 工具勾选列表（从 API 加载可用工具，checkbox）
- [ ] 保存按钮（PUT 请求）
- [ ] 恢复默认按钮（DELETE 请求 + 确认弹窗）

## 测试

- [ ] 后端测试：查看默认配置
- [ ] 后端测试：自定义配置保存和读取
- [ ] 后端测试：effective 配置合并逻辑
- [ ] 后端测试：恢复默认（DELETE）
- [ ] 集成测试：投研运行使用自定义配置
- [ ] 前端测试：Agent 配置编辑 E2E
