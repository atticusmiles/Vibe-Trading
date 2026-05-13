# 阶段 2：用户认证体系

## 1. 概述

**目标**：建立多用户认证体系，包括用户注册/登录（JWT）、API Key 加密存储、用户偏好和设置管理，前后端一起交付。

**与前后阶段的关系**：本阶段是所有业务功能的前提。后续阶段的所有 API 都需要 JWT 鉴权，所有业务数据按用户隔离。

**前置条件**：阶段 1 完成，CI/CD 流水线可用。

## 2. 数据模型

### users 表

```sql
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    api_keys        TEXT DEFAULT '{}',    -- JSON，仅密钥值加密，结构可读
    preferences     TEXT DEFAULT '{}',    -- JSON，投资偏好
    settings        TEXT DEFAULT '{}',    -- JSON，系统设置
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
```

**api_keys JSON 结构**：
```json
{
    "llm_provider": {
        "key": "enc:a3f1b2...",
        "label": "OpenRouter",
        "model": "anthropic/claude-sonnet-4-20250514",
        "base_url": "https://openrouter.ai/api/v1",
        "provider": "openrouter"
    },
    "tushare": {
        "key": "enc:9c2d4e..."
    },
    "searxng": {
        "base_url": "http://localhost:8080"
    }
}
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
        "app_secret": "enc:...",
        "push_channel": ""
    }
}
```

## 3. API 设计

### 3.1 认证端点

```
POST   /auth/register
请求：{"username": "xxx", "password": "xxx"}
响应：{"id": 1, "username": "xxx", "created_at": "..."}

POST   /auth/login
请求：{"username": "xxx", "password": "xxx"}
响应：{"access_token": "xxx", "token_type": "bearer", "expires_in": 86400}

POST   /auth/logout
头部：Authorization: Bearer <token>
响应：204 No Content

GET    /auth/me
头部：Authorization: Bearer <token>
响应：{"id": 1, "username": "xxx", "preferences": {...}, "created_at": "..."}
```

### 3.2 用户配置端点

所有端点通过 JWT 中间件自动获取 user_id，不需要在 URL 或请求体中传递。

```
GET    /api/user/preferences
响应：{"investment_style": "价值投资", ...}

PUT    /api/user/preferences
请求：{"investment_style": "成长投资", "risk_appetite": "积极型", ...}
响应：200 OK

GET    /api/user/api-keys
响应：{"llm_provider": {"label": "OpenRouter", "key": "enc:***"}, ...}
（密钥值脱敏，只显示后4位）

PUT    /api/user/api-keys
请求：{"llm_provider": {"key": "sk-xxx", "label": "OpenRouter", "model": "..."}}
响应：200 OK
（存储时自动加密 key 字段，其他字段明文）

DELETE /api/user/api-keys/{key_type}
响应：200 OK

GET    /api/user/settings
响应：{"news_archive_time": "08:00", ...}

PUT    /api/user/settings
请求：{"news_archive_time": "09:00", "proposal_limits": {"trend": 5}}
响应：200 OK
```

## 4. 业务逻辑

### 4.1 JWT 认证

- 登录成功后签发 JWT，包含 `sub`（user_id）和 `exp`（过期时间）
- Token 有效期 24 小时
- 中间件在每个请求前解析 Token，将 `user_id` 注入请求上下文
- SSE 连接通过 `?token=` 查询参数传递 Token

### 4.2 API Key 加密

- 使用 AES-256-GCM 加密，密钥从环境变量 `ENCRYPTION_KEY` 读取
- 写入时：`api_keys` JSON 中 `"key"` 字段的值加密后存储为 `"enc:base64_ciphertext"`
- 读取时：`GET /api/user/api-keys` 返回脱敏值（`"***abcd"`，显示后4位）
- 运行时使用：Agent 执行时解密实际 key 值传给 LLM Provider

### 4.3 密码安全

- 使用 bcrypt 哈希，work factor = 12
- 注册时校验用户名长度 3-32，密码长度 8-128

### 4.4 数据隔离

- 所有业务查询强制 `WHERE user_id = ?`
- 中间件层统一注入 user_id，业务代码不自行解析认证信息

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

- 登录成功后 Token 存入 localStorage，跳转到 Dashboard
- 未登录访问其他页面自动跳转到 `/login`

### 5.2 用户设置页面（`/settings`）

三个 Tab：**API Key 配置** | **投资偏好** | **系统设置**

**API Key 配置 Tab**：
```
┌─────────────────────────────────────────┐
│  LLM Provider                           │
│  标签：[OpenRouter    ]                  │
│  Key： [sk-****************abcd]         │  ← 脱敏显示，点击编辑
│  模型：[anthropic/claude-sonnet-4-20250514]              │
│  Base URL：[https://openrouter.ai/api/v1]│
│                                         │
│  tushare                                │
│  Token：[****efgh]                       │
│                                         │
│  searxng                                │
│  地址：[http://localhost:8080]           │
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

**系统设置 Tab**：
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
- [ ] 所有 /api/* 端点需要 Bearer Token 才能访问，无 Token 返回 401
- [ ] 不同用户的 API Key / 偏好 / 设置完全隔离
- [ ] API Key 存储加密，读取脱敏
- [ ] 前端登录/注册流程完整可用
- [ ] 前端设置页面可管理 API Key、偏好、系统设置
- [ ] Token 过期后前端自动跳转到登录页
