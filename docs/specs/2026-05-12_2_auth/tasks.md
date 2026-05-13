# 阶段 2 任务清单：用户认证体系

## 数据库

- [ ] 新增 `agent/src/db/` 模块：数据库初始化、连接管理、schema 迁移
- [ ] 实现 `vibe.db` 初始化逻辑（首次启动自动建表）
- [ ] 创建 users 表（含 api_keys / preferences / settings JSON 字段）
- [ ] 实现 schema 版本管理（简单的版本号 + 迁移脚本列表）

## 后端 — 认证

- [ ] 新增 `agent/src/auth/` 模块
- [ ] 实现 bcrypt 密码哈希（注册时 hash，登录时 verify）
- [ ] 实现 JWT 签发（PyJWT，payload 含 sub/user_id + exp）
- [ ] 实现 JWT 中间件：解析 Authorization 头，注入 user_id 到请求上下文
- [ ] 实现 SSE Token 认证（支持 `?token=` 查询参数）
- [ ] 实现 `POST /auth/register`：校验用户名/密码格式，创建用户
- [ ] 实现 `POST /auth/login`：校验凭证，返回 JWT
- [ ] 实现 `POST /auth/logout`：客户端清除 Token 即可（JWT 无状态）
- [ ] 实现 `GET /auth/me`：返回当前用户信息

## 后端 — API Key 加密

- [ ] 新增 `agent/src/crypto/` 模块
- [ ] 实现 AES-256-GCM 加密/解密函数（密钥从 ENCRYPTION_KEY 环境变量读取）
- [ ] 实现 API Key 写入加密：PUT /api/user/api-keys 时自动加密 key 字段
- [ ] 实现 API Key 读取脱敏：GET /api/user/api-keys 时只显示后 4 位
- [ ] 实现 API Key 运行时解密：Agent 执行时获取实际密钥值

## 后端 — 用户配置 API

- [ ] 实现 `GET /api/user/preferences`：读取当前用户 preferences JSON
- [ ] 实现 `PUT /api/user/preferences`：整体替换 preferences JSON
- [ ] 实现 `GET /api/user/api-keys`：读取并脱敏
- [ ] 实现 `PUT /api/user/api-keys`：整体替换，自动加密 key 字段
- [ ] 实现 `DELETE /api/user/api-keys/{key_type}`：删除指定类型
- [ ] 实现 `GET /api/user/settings`：读取 settings JSON
- [ ] 实现 `PUT /api/user/settings`：整体替换 settings JSON

## 后端 — 数据隔离

- [ ] 确保所有新增 API 端点注册 JWT 中间件依赖
- [ ] 现有 API 端点保持兼容（保留 `require_local_or_auth` 逻辑，投研 API 用新 JWT 鉴权）

## 前端 — 登录注册

- [ ] 新增 `/login` 路由和页面组件
- [ ] 实现登录/注册表单（Tab 切换）
- [ ] 实现 JWT Token 存储（localStorage）
- [ ] 实现路由守卫：未登录自动跳转 `/login`
- [ ] 实现 Axios 拦截器：自动添加 `Authorization: Bearer <token>` 头
- [ ] 实现 Token 过期处理：401 响应自动跳转登录页

## 前端 — 用户设置页

- [ ] 新增 `/settings` 路由和页面组件
- [ ] 实现 API Key 配置 Tab：表单 + 脱敏显示 + 编辑模式
- [ ] 实现投资偏好 Tab：下拉选择 + 多选标签 + 数字输入
- [ ] 实现系统设置 Tab：时间选择 + 频率选择 + 数字输入
- [ ] 实现保存交互：PUT 请求 + 成功提示

## 测试

- [ ] 后端测试：注册/登录/JWT 签发验证
- [ ] 后端测试：API Key 加密/脱敏/解密
- [ ] 后端测试：数据隔离（用户 A 不能访问用户 B 的数据）
- [ ] 后端测试：未认证请求返回 401
- [ ] 前端测试：登录流程 E2E
