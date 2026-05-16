# 阶段 2 任务清单：用户认证体系

## 数据库

- [ ] 新增 `agent/src/db/` 模块：数据库初始化、连接管理、schema 迁移
- [ ] 实现 SQLite WAL 模式 + busy timeout 5s
- [ ] 实现 `vibe.db` 初始化逻辑（首次启动自动建表）
- [ ] 创建 users 表（含 preferences / settings JSON 字段）
- [ ] 实现 schema 版本管理（简单的版本号 + 迁移脚本列表）
- [ ] 在 FastAPI lifespan 中注册 DB 初始化调用

## 后端 — 认证

- [ ] 新增 `agent/src/auth/` 模块
- [ ] 实现 bcrypt 密码哈希（work factor=12，salt 由 bcrypt 自动生成）
- [ ] 实现 JWT 签发（PyJWT，payload 含 sub/user_id + exp，有效期 24h）
- [ ] 实现 JWT 中间件：解析 Authorization 头，校验签名和过期时间，注入 user_id（无状态，不查 DB）
- [ ] 实现 SSE Token 认证（支持 `?token=` 查询参数，复用现有 event_stream_auth 模式）
- [ ] 实现 `POST /auth/register`：校验用户名 3-32 / 密码 8-128，重复用户名返回 409
- [ ] 实现 `POST /auth/login`：校验凭证，返回 JWT
- [ ] 实现 `GET /auth/me`：返回当前用户信息
- [ ] 实现 `PUT /auth/password`：校验旧密码，更新密码哈希，旧密码错误返回 400

## 后端 — 敏感字段加密

- [ ] 新增 `agent/src/crypto/` 模块（通用加密服务，不限于 API Key）
- [ ] 实现 AES-256-GCM 加密/解密函数（密钥从 ENCRYPTION_KEY 环境变量读取，32 字节 hex，64 字符）
- [ ] 实现敏感字段自动识别：JSON 中 `"key"` / `"secret"` / `"app_secret"` 字段自动加密
- [ ] 存储格式：`enc:base64_nonce:base64_ciphertext:base64_tag`
- [ ] 写入时自动加密敏感字段（api-keys / settings 均适用）
- [ ] 读取时自动解密，返回明文
- [ ] 运行时解密：Agent 执行时获取实际密钥值
- [ ] 实现启动检测：ENCRYPTION_KEY 未设置时 warn，写入敏感字段时返回 503
- [ ] 实现密钥格式校验：启动时检查 ENCRYPTION_KEY 长度为 64 字符 hex

## 后端 — 用户配置 API

- [ ] 实现 `GET /api/user/settings/preferences`：读取当前用户 preferences JSON
- [ ] 实现 `PUT /api/user/settings/preferences`：全量替换 preferences JSON
- [ ] 实现 `GET /api/user/settings/system`：读取 settings JSON，敏感字段解密返回明文
- [ ] 实现 `PUT /api/user/settings/system`：全量替换，自动加密敏感字段

## 后端 — 迁移（一刀切）

- [ ] 移除现有 `API_AUTH_KEY` 静态 Token 认证逻辑
- [ ] 所有端点替换为 `Depends(require_jwt_auth)`
- [ ] 保留 loopback 检测用于开发模式（无 JWT 时仅允许 localhost）
- [ ] 前端 `apiAuth.ts` 移除静态 key 逻辑，改用 JWT Token

## 前端 — 登录注册

- [ ] 新增 `/login` 路由和页面组件
- [ ] 实现登录/注册表单（Tab 切换）
- [ ] 实现 JWT Token 存储（复用现有 apiAuth.ts 的 setApiAuthKey / localStorage）
- [ ] 实现路由守卫：未登录自动跳转 `/login`
- [ ] 改造现有 `api.ts` 的 `request()` 封装，自动附带 JWT Token（原生 fetch，不使用 Axios）
- [ ] 实现 Token 过期处理：401 响应自动跳转登录页

## 前端 — 用户设置页

- [ ] 新增 `/settings` 路由和页面组件
- [ ] 实现投资偏好 Tab：下拉选择 + 多选标签 + 数字输入
- [ ] 实现系统设置 Tab：时间选择 + 频率选择 + 数字输入（飞书配置区域阶段 8 实现，不渲染）
- [ ] 实现安全 Tab：密码修改表单
- [ ] 实现保存交互：PUT 全量替换 + 成功提示

## 依赖同步

- [ ] pyproject.toml 添加 `PyJWT>=2.8.0`、`bcrypt>=4.0.0`、`cryptography>=41.0.0`

## 测试

- [ ] 后端测试：注册/登录/JWT 签发验证
- [ ] 后端测试：重复用户名注册返回 409
- [ ] 后端测试：敏感字段加密/解密
- [ ] 后端测试：ENCRYPTION_KEY 缺失时返回 503
- [ ] 后端测试：ENCRYPTION_KEY 格式错误时启动报错
- [ ] 后端测试：数据隔离（用户 A 不能访问用户 B 的数据）
- [ ] 后端测试：未认证请求返回 401
- [ ] 前端测试：登录流程 E2E
