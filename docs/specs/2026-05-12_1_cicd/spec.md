# 阶段 1：CI/CD 基建

## 1. 概述

**目标**：在现有代码基础上建立完整的容器化构建与部署流水线，确保后续每个阶段的交付物都能自动构建、测试、部署。

**与前后阶段的关系**：本阶段不引入任何新功能代码，仅改造构建和部署基础设施。所有后续阶段依赖本阶段产出的 CI/CD 流水线。

**前置条件**：现有代码可正常运行（`pytest` 通过、`npm run build` 通过）。

## 2. 版本管理

采用 **bump-my-version** 管理版本号，一次命令同步修改 pyproject.toml + package.json 并创建 git tag。

### 2.1 配置（pyproject.toml）

```toml
[tool.bumpversion]
current_version = "0.1.7"
commit = true
tag = true
tag_name = "v{new_version}"

[[tool.bumpversion.files]]
filename = "pyproject.toml"
search = 'version = "{current_version}"'
replace = 'version = "{new_version}"'

[[tool.bumpversion.files]]
filename = "frontend/package.json"
search = '"version": "{current_version}"'
replace = '"version": "{new_version}"'
```

### 2.2 使用方式

```
bump-my-version bump patch   # 0.1.7 → 0.1.8，自动改文件 + commit + tag v0.1.8
bump-my-version bump minor   # 0.1.7 → 0.2.0
bump-my-version bump major   # 0.1.7 → 1.0.0
```

## 3. Git Flow

### 3.1 分支模型

```
feature/* ──→ develop ──→ release ──→ main
  (开发)       (集成)      (UAT)     (生产)
```

| 分支 | 用途 | 保护规则 |
|------|------|---------|
| `main` | 生产分支 | PR + review，仅接受 release 的 PR |
| `release` | UAT 测试分支 | PR + review，仅接受 develop 的 PR |
| `develop` | 开发集成分支 | PR + review |
| `feature/*` `fix/*` | 具体功能开发 | 无限制 |

### 3.2 核心原则：镜像只构建一次

镜像在 **merge 到 release 时构建一次**，UAT 和生产使用同一个镜像：

- merge 到 release → 构建镜像 `sha-*` + 自动部署 UAT
- merge 到 main → 不构建，仅用 crane 给已有镜像补打 `v*` 标签
- 生产部署使用 UAT 验证过的同一镜像

### 3.3 完整流程

```
1. feat/* → PR → develop        CI: lint + test（不构建）
2. develop → PR → release       CI: lint + test + build(sha-*) + 自动部署UAT
3. 人工 UAT 验证
   不通过 → 在 feat 修 → 回到步骤 1
   通过   → 继续
4. release → PR → main          代码落地，不构建
5. main 上 bump + push tag      CI: crane 补标签 sha-* → v*（不重新构建）
6. 手动 Deploy Prod             image_tag: v* → 审批 → 部署 → GitHub Release
```

## 4. 现有基础设施

| 组件 | 现状 |
|------|------|
| Dockerfile | 已有，多阶段构建（前端 build → Python 运行时） |
| docker-compose.yml | 已有，两个 volume（vibe-runs、vibe-sessions），前端用 dev 模式 |
| GitHub Actions | 已有 `test.yml`（lint + pytest + frontend build） |

## 5. 改造设计

### 5.1 Dockerfile 改造

```
改动点：
1. requirements.txt 新增依赖：chromadb、PyJWT、bcrypt、cryptography、lark-oapi、apscheduler
   （投研系统全部依赖一次性加入，后续阶段无需改 Dockerfile）
2. 创建 /data 目录，USER vibe 拥有写权限
3. 环境变量 DATA_DIR 默认 /data
4. 入口点保持不变：vibe-trading serve --host 0.0.0.0 --port 8899
```

### 5.2 docker-compose 改造

```yaml
services:
  vibe-trading:
    build: .
    image: ghcr.io/hkuds/vibe-trading:${TAG:-develop}
    ports:
      - "127.0.0.1:8899:8899"
    environment:
      - DATA_DIR=/data
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
      - JWT_SECRET=${JWT_SECRET}
    volumes:
      - vibe-data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8899/health')"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  vibe-data:
```

关键改动：
- 多个 volume 合并为单一 `vibe-data`，挂载到 `/data`
- 默认标签改为 `develop`（develop 分支构建）
- 新增 `ENCRYPTION_KEY` 和 `JWT_SECRET` 环境变量（后续阶段使用）
- 去掉 frontend dev service（生产环境由 FastAPI 托管静态文件）

### 5.3 数据路径统一

现有代码中分散的路径统一由 `DATA_DIR` 环境变量控制：

| 数据 | 现有路径 | 统一后路径 |
|------|---------|-----------|
| 业务数据库 | 无（新增） | `$DATA_DIR/vibe.db` |
| ChromaDB | 无（新增） | `$DATA_DIR/chroma/` |
| 文件记忆 | `~/.vibe-trading/memory/` | `$DATA_DIR/memory/` |
| FTS5 索引 | `~/.vibe-trading/sessions.db` | `$DATA_DIR/sessions.db` |
| Runs | `agent/runs/` | `$DATA_DIR/runs/` |
| Sessions | `agent/sessions/` | `$DATA_DIR/sessions/` |
| Swarm | `agent/.swarm/runs/` | `$DATA_DIR/swarm/` |
| Uploads | `agent/uploads/` | `$DATA_DIR/uploads/` |

本地开发默认 `DATA_DIR=~/.vibe-trading`，容器内 `DATA_DIR=/data`，行为一致。

### 5.4 GitHub Actions 工作流

#### Workflow 1：CI（ci.yml）

```
文件：.github/workflows/ci.yml
触发：
  - pull_request → develop        lint + test
  - push → develop                lint + test + build
  - pull_request → release        lint + test
  - push → release                lint + test + build
  - push tag v* → main            lint + test + crane 补标签
```

| 触发场景 | Lint+Test | Docker Build | 镜像标签 |
|---------|-----------|-------------|---------|
| PR 到 develop | 执行 | — | — |
| Push 到 develop | 执行 | 执行 | `develop-sha-xxxx` |
| PR 到 release | 执行 | — | — |
| Push 到 release | 执行 | 执行 | `release-sha-xxx` |
| v* tag push 到 main | 执行 | 补标签 | 给 `release-sha-xxx` 补打 `v*` |

Push 到 develop 的步骤：
1. actions/checkout
2. actions/setup-python (3.11) + pip install -e ".[dev]"
3. ruff check agent/
4. pytest --ignore=agent/tests/e2e_backtest
5. actions/setup-node (20) + npm ci + npm run build
6. docker/login-action → docker/build-push-action
   - 多架构：linux/amd64 + linux/arm64
   - 推送到 ghcr.io
   - 标签：`develop-sha-{短SHA}`

Push 到 release 的步骤：
1. 同上 1-5
6. docker/login-action → docker/build-push-action
   - 多架构：linux/amd64 + linux/arm64
   - 推送到 ghcr.io
   - 标签：`release-sha-{短SHA}`

v* tag push 到 main 的步骤：
1. actions/checkout（fetch-tags: true）
2. lint + test
3. 用 crane 给 release 构建的 `sha-{短SHA}` 镜像补打 `v{version}` 标签（纯 registry 操作，不构建）

#### Workflow 2：Deploy UAT（deploy-uat.yml）

```
文件：.github/workflows/deploy-uat.yml
触发：workflow_run（ci.yml 在 release 分支完成后自动触发）
```

步骤：
1. 获取 release 构建的 `sha-{短SHA}` 镜像标签
2. SSH 到 UAT 服务器执行部署（docker compose pull + up -d）
3. 轮询 `/health` 最多 60s
4. 运行 E2E 测试
5. 失败时回滚到上一版本

GitHub Environment：`UAT`
- Secrets：UAT_SSH_KEY、UAT_HOST、UAT_ENCRYPTION_KEY、UAT_JWT_SECRET

#### Workflow 3：Deploy Prod（deploy-prod.yml）

```
文件：.github/workflows/deploy-prod.yml
触发：workflow_dispatch
参数：
  - image_tag（必填，如 v0.1.8）
  - confirm（boolean，必勾选）
```

步骤：
1. 校验镜像 tag 在 ghcr.io 存在
2. SSH 到生产服务器执行部署（docker compose pull + up -d）
3. 等待 `/health` 返回 200
4. 创建 GitHub Release（标题和 tag 为 v*）
5. 部署完成通知

GitHub Environment：`Production`
- Required Reviewers：指定审批人
- Wait timer：5 分钟
- Secrets：PROD_SSH_KEY、PROD_HOST、PROD_ENCRYPTION_KEY、PROD_JWT_SECRET

### 5.5 镜像标签策略

| 场景 | 标签 | 示例 |
|------|------|------|
| develop 每次 merge | `develop-sha-{7位SHA}` | `develop-sha-a3f1b2c` |
| release 每次 merge | `release-sha-{7位SHA}` | `release-sha-f2e4d6a` |
| 版本 tag push 到 main | `vX.Y.Z`（补打） | `v0.1.8`（指向 release 的同一镜像） |

每个镜像只有一个标签，通过前缀区分来源分支。

## 6. 验收标准

- [ ] `bump-my-version bump patch` 正确修改 pyproject.toml + package.json + 创建 tag
- [ ] `docker build .` 成功构建镜像
- [ ] `docker compose up -d` 启动服务，`/health` 返回 200
- [ ] PR 到 develop 触发 lint + test
- [ ] Push 到 develop 触发 lint + test + build（`dev` + `sha-*`）
- [ ] Push 到 release 触发 lint + test + build（`sha-*`）+ 自动部署 UAT
- [ ] v* tag push 到 main 触发 crane 补标签（不重新构建）
- [ ] 手动触发 Deploy Prod 需要审批才能执行
- [ ] UAT 和生产部署使用同一个镜像
- [ ] 所有持久化数据在 `/data` 目录下，容器重启后数据不丢失
