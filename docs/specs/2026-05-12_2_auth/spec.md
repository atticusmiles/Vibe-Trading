# 阶段 2：用户认证体系

## 1. 概述

**目标**：建立多用户认证体系，包括用户注册/登录（JWT）、用户偏好和设置管理，前后端一起交付。LLM Provider 和数据源配置通过全局环境变量管理，不存入数据库。

**与前后阶段的关系**：本阶段是所有业务功能的前提。后续阶段的所有 API 都需要 JWT 鉴权，所有业务数据按用户隔离。

**前置条件**：阶段 1 完成，CI/CD 流水线可用。

## 2. 数据模型

### users 表

```sql
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    preferences     TEXT DEFAULT '{}',    -- JSON，投资偏好
    settings        TEXT DEFAULT '{}',    -- JSON，系统设置（敏感字段加密）
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
```

**preferences JSON 结构**：
```json
{
    "investment_style": "价值投资",
    "risk_appetite": "稳健型",
    "focus_markets": ["A股"],
    "focus_industries": ["科技", "消费"],
    "holding_period": "中线",
    "capital_scale": "10~50万",
    "stock_invest_total": 50000,
    "avoid_targets": ["ST股", "次新股"],
    "custom_notes": ""
}
```

**settings JSON 结构**：
```json
{
    "news_archive_time": "08:00",
    "sentinel_interval": 60,
    "proposal_limits": {
        "trend": 10,
        "industry": 10,
        "stock": 10
    },
    "feishu": {
        "app_id": "",
        "app_secret": "enc:dGVzdA==:eW91cg==:dGhlbQ==",
        "push_channel": ""
    }
}
```

## 3. API 设计

### 3.1 认证端点

```
POST   /auth/register
请求：{"username": "xxx", "password": "xxx"}
成功：201 {"id": 1, "username": "xxx", "created_at": "..."}
失败：409 {"detail": "Username already exists"}

POST   /auth/login
请求：{"username": "xxx", "password": "xxx"}
响应：{"access_token": "xxx", "token_type": "bearer", "expires_in": 86400}

GET    /auth/me
头部：Authorization: Bearer <token>
响应：{"id": 1, "username": "xxx", "preferences": {...}, "created_at": "..."}

PUT    /auth/password
头部：Authorization: Bearer <token>
请求：{"old_password": "xxx", "new_password": "xxx"}
成功：200 OK
失败：400 {"detail": "Incorrect password"}
```

### 3.2 用户配置端点

所有端点通过 JWT 中间件自动获取 user_id，不需要在 URL 或请求体中传递。

**设计原则**：每个配置组（preferences、settings）有独立的 GET/PUT 端点，PUT 为全量替换（不支持 PATCH 部分更新）。前端读取当前值 → 用户修改 → 提交完整 JSON 替换。LLM 和数据源配置通过全局 `.env` 管理，不经过这些端点。

```
GET    /api/user/settings/preferences
响应：{"investment_style": "价值投资", ...}

PUT    /api/user/settings/preferences
请求：完整 JSON（全量替换）
响应：200 OK

GET    /api/user/settings/system
响应：{"news_archive_time": "08:00", ...}
（settings 中敏感字段如 feishu.app_secret 同样解密后返回明文）

PUT    /api/user/settings/system
请求：完整 JSON（全量替换）
响应：200 OK
```

## 4. 业务逻辑

### 4.1 JWT 认证

- 登录成功后签发 JWT，包含 `sub`（user_id）和 `exp`（过期时间）
- **JWT_SECRET 格式**：任意字符串，建议 >= 32 字符随机值
- Token 有效期 24 小时，过期后前端自动跳转登录页重新登录
- 中间件解析 Token，校验签名和过期时间，将 `user_id` 注入请求上下文（无状态，不查数据库）
- SSE 连接通过 `?token=` 查询参数传递 Token（复用现有 `require_event_stream_auth` 的模式）

### 4.2 敏感字段加密

- 使用 AES-256-GCM 加密，密钥从环境变量 `ENCRYPTION_KEY` 读取
- **ENCRYPTION_KEY 格式**：32 字节，以 hex 编码传入（64 字符）。启动时校验长度，不符合则报错退出
- 加密规则：递归遍历 JSON 树，所有以 `"key"` 或 `"secret"` 或 `"app_secret"` 命名的字段值自动加密
- 存储格式：`"enc:base64_nonce:base64_ciphertext:base64_tag"`（含 nonce 和 tag，无需单独存储）
- 写入时：自动识别并加密敏感字段
- 读取时：自动解密，返回明文（前端直接展示和编辑）
- 运行时使用：Agent 执行时解密实际密钥值传给 LLM Provider
- **启动检测**：服务启动时检查 `ENCRYPTION_KEY` 是否设置，未设置时 warn 日志提示；若用户尝试写入敏感字段但 key 缺失，返回 503 Service Unavailable

### 4.3 密码安全

- 使用 bcrypt 哈希，work factor = 12，salt 由 bcrypt 自动生成（无需单独处理）
- 注册时校验用户名长度 3-32，密码长度 8-128

### 4.4 数据隔离

- 所有业务查询强制 `WHERE user_id = ?`
- 中间件层统一注入 user_id，业务代码不自行解析认证信息

### 4.5 迁移策略

- **一刀切**：本阶段上线后，移除现有的 `API_AUTH_KEY` 静态 Token 认证机制
- 所有端点统一使用 JWT 鉴权（通过 `Depends(require_jwt_auth)` 替换现有的 `Depends(require_auth)`）
- 前端移除 `apiAuth.ts` 中旧的静态 key 逻辑，改用 JWT Token
- `API_AUTH_KEY` 环境变量标记为废弃，不再读取

### 4.6 数据库配置

- SQLite WAL 模式（`PRAGMA journal_mode=WAL`），busy timeout 5 秒
- 数据库文件路径：`{DATA_DIR}/vibe.db`
- 服务启动时在 FastAPI `lifespan` 中自动初始化建表和迁移

## 5. 前端设计

### 5.1 登录/注册页面（`/login`）

```
┌─────────────────────────────────┐
│         Vibe Trading AI         │
│                                 │
│  [登录]  [注册]                 │  ← Tab 切换
│                                 │
│  用户名：[______________]        │
│  密  码：[______________]        │
│                                 │
│       [ 登 录 ]                 │
│                                 │
└─────────────────────────────────┘
```

- 登录成功后 Token 存入 localStorage（复用现有 `apiAuth.ts` 的 `setApiAuthKey`），跳转到 Dashboard
- 未登录访问其他页面自动跳转到 `/login`
- 所有 API 请求通过现有 `api.ts` 的 `request()` 封装自动附带 `Authorization: Bearer <token>`（原生 fetch，不使用 Axios）

### 5.2 用户设置页面（`/settings`）

三个 Tab：**投资偏好** | **系统设置** | **安全**

**安全 Tab**：
```
┌─────────────────────────────────────────┐
│  修改密码                               │
│  当前密码：[______________]              │
│  新密码：  [______________]              │
│  确认密码：[______________]              │
│                                         │
│  [保存]                                 │
└─────────────────────────────────────────┘
```

**投资偏好 Tab**：
```
┌─────────────────────────────────────────┐
│  投资风格：[价值投资 ▼]                  │
│  风险偏好：[稳健型   ▼]                  │
│  关注市场：[☑ A股] [☐ 港股] [☐ 美股]    │
│  关注行业：[☑ 科技] [☑ 消费] [☐ 医药]   │
│  持仓周期：[中线     ▼]                  │
│  资金规模：[10~50万 ▼]                   │
│  股票投资总额：[50000        ]           │
│  避险标的：[ST股, 次新股         ]       │  ← Tag 输入
│  自定义备注：[                    ]       │
│                                         │
│  [保存]                                 │
└─────────────────────────────────────────┘
```

**系统设置 Tab**（飞书配置区域在阶段 8 实现，本阶段不渲染）：
```
┌─────────────────────────────────────────┐
│  新闻存档时间：[08:00]                   │
│  舆情监控频率：[每小时 ▼]                │
│                                         │
│  提案数量上限                            │
│  趋势：[10]  行业：[10]  股票：[10]      │
│                                         │
│  [保存]                                 │
└─────────────────────────────────────────┘
```

## 6. 验收标准

- [ ] 可通过 API 注册新用户、登录获取 JWT
- [ ] 注册重复用户名返回 409
- [ ] 所有 /api/* 端点需要 Bearer Token 才能访问，无 Token 返回 401
- [ ] 不同用户的偏好 / 设置完全隔离
- [ ] 敏感字段（secret/app_secret）存储加密，读取返回明文
- [ ] ENCRYPTION_KEY 缺失时写入敏感字段返回 503
- [ ] 前端登录/注册流程完整可用
- [ ] 前端设置页面可管理偏好、系统设置、密码修改
- [ ] Token 过期后前端自动跳转到登录页
