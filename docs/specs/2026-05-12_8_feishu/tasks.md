# 阶段 8 任务清单：飞书集成

## 后端 — 飞书 SDK 集成

- [ ] 安装 lark-oapi 依赖
- [ ] 新增 `agent/src/feishu/` 模块
- [ ] 实现 FeishuClient 封装（消息发送、卡片发送、事件处理）
- [ ] 从用户 settings.feishu 读取配置（app_id、app_secret）
- [ ] 实现 Access Token 管理（自动刷新）

## 后端 — Webhook

- [ ] `POST /api/feishu/webhook`：飞书事件回调入口
- [ ] 事件分发：根据事件类型分发到不同处理器
- [ ] URL 验证：处理飞书的 challenge 验证请求
- [ ] 签名验证：校验请求来自飞书（避免伪造）

## 后端 — 提案推送

- [ ] 提案创建时触发飞书推送（在阶段 4 的创建逻辑中 hook）
- [ ] 检查用户是否绑定飞书
- [ ] 构造飞书交互卡片（标题、类型、置信度、摘要、采纳/拒绝按钮）
- [ ] 发送到用户配置的推送渠道
- [ ] 卡片操作回调处理：解析 action → 调用提案审批 API → 更新卡片状态

## 后端 — 飞书对话

- [ ] 消息事件处理：接收飞书消息 → 查找绑定用户 → 获取/创建 Session
- [ ] 消息转发：将飞书消息内容发送到 Session（复用现有 Session API）
- [ ] 回复推送：Agent 回复完成后，构造飞书消息发送回用户
- [ ] 支持文本和简单卡片格式的回复

## 后端 — 配置 API

- [ ] `POST /api/feishu/bind`：绑定飞书账号（存储飞书 user_id ↔ 系统用户映射）
- [ ] `DELETE /api/feishu/bind`：解绑
- [ ] `GET /api/feishu/config`：获取配置（脱敏）
- [ ] `PUT /api/feishu/config`：更新配置（app_secret 加密存储）

## 前端

- [ ] 设置页面增加飞书配置 Tab（或放在系统设置 Tab 内）
- [ ] 飞书 App ID / Secret 配置表单
- [ ] 推送渠道配置
- [ ] 绑定/解绑操作
- [ ] 绑定状态显示

## 测试

- [ ] 单元测试：飞书卡片构造
- [ ] 单元测试：卡片操作回调解析
- [ ] 集成测试：提案推送 → 飞书卡片发送（mock 飞书 API）
- [ ] 集成测试：卡片操作 → 提案审批
- [ ] 集成测试：飞书消息 → Session 对话 → 回复
