# 阶段 1 任务清单：CI/CD 基建

## 版本管理（bump-my-version）

- [ ] 安装 bump-my-version 依赖（加入 dev deps）
- [ ] 在 `pyproject.toml` 中添加 `[tool.bumpversion]` 配置（current_version、commit、tag）
- [ ] 配置文件列表：pyproject.toml + frontend/package.json
- [ ] 验证 `bump-my-version bump patch` 正确修改两个文件 + 创建 commit + tag
- [ ] 验证 `bump-my-version bump minor/major` 正常工作

## Git Flow 分支初始化

- [ ] 从当前 main 创建 `develop` 分支
- [ ] 从 develop 创建 `release` 分支
- [ ] 配置 GitHub 分支保护规则：main（PR + review）、release（PR + review）、develop（PR + review）

## 数据路径统一

- [ ] 在 `agent/src/core/` 新增 `config.py`，定义 `DATA_DIR` 环境变量读取逻辑，默认 `~/.vibe-trading`
- [ ] 修改 `agent/cli.py` 中 `RUNS_DIR`、`SESSIONS_DIR` 路径，改为基于 `DATA_DIR`
- [ ] 修改 `agent/api_server.py` 中的路径引用，改为基于 `DATA_DIR`
- [ ] 修改 `agent/src/core/state.py` 中 `RunStateStore` 的路径，改为基于 `DATA_DIR`
- [ ] 修改 `agent/src/session/store.py` 中 session 存储路径，改为基于 `DATA_DIR`
- [ ] 修改 `agent/src/memory/persistent.py` 中 `MEMORY_BASE`，改为基于 `DATA_DIR`
- [ ] 修改 `agent/src/session/search.py` 中 SQLite 路径，改为基于 `DATA_DIR`
- [ ] 修改 Swarm 相关路径（`agent/.swarm/`）改为基于 `DATA_DIR`
- [ ] 修改 upload 路径改为基于 `DATA_DIR`
- [ ] 全局搜索确认无遗漏的硬编码路径

## Dockerfile

- [ ] 更新 `agent/requirements.txt`：新增 chromadb、PyJWT、bcrypt、cryptography、lark-oapi、apscheduler
- [ ] 修改 `Dockerfile`：创建 `/data` 目录，设置权限给 vibe 用户
- [ ] 修改 `Dockerfile`：添加 `ENV DATA_DIR=/data`
- [ ] 验证 `docker build .` 成功

## docker-compose

- [ ] 修改 `docker-compose.yml`：合并为单一 `vibe-data` volume
- [ ] 修改 `docker-compose.yml`：默认镜像标签改为 `develop`
- [ ] 修改 `docker-compose.yml`：添加 `DATA_DIR`、`ENCRYPTION_KEY`、`JWT_SECRET` 环境变量
- [ ] 去掉 frontend dev service（生产环境不需要）
- [ ] 添加 `.env.example` 说明需要配置的环境变量
- [ ] 验证 `docker compose up -d` 成功启动，`/health` 返回 200

## GitHub Actions — CI + 自动部署 UAT

- [ ] 新建 `.github/workflows/ci.yml`
- [ ] 配置触发条件：PR/push to develop、PR/push to release、v* tag push to main
- [ ] 实现 lint + test 步骤（ruff + pytest + npm build）
- [ ] 实现 push to develop 时的 Docker build：标签 `develop-sha-{短SHA}`
- [ ] 实现 push to release 时的 Docker build：标签 `release-sha-{短SHA}`
- [ ] 实现 v* tag push 到 main 时的 crane 补标签步骤（不构建）
## GitHub Actions — Deploy UAT

- [ ] 新建 `.github/workflows/deploy-uat.yml`
- [ ] 配置 `workflow_run` 触发（ci.yml 在 release 分支完成后自动触发）
- [ ] 获取 release 构建的 `sha-{短SHA}` 镜像标签
- [ ] 实现健康检查等待（轮询 /health，最多 60s）
- [ ] 实现 E2E 测试步骤
- [ ] 实现失败回滚（记录上一版本 tag，失败时回退）
- [ ] 验证 PR 到 develop 仅 lint + test
- [ ] 验证 push 到 develop 构建 `dev` + `sha-*` 镜像
- [ ] 验证 push 到 release 构建 `sha-*` 镜像
- [ ] 验证 v* tag push 补标签成功

## GitHub Actions — Deploy Prod

- [ ] 新建 `.github/workflows/deploy-prod.yml`
- [ ] 配置 `workflow_dispatch` 触发，支持 `image_tag`（必填）和 `confirm`（boolean）
- [ ] 实现镜像 tag 存在校验
- [ ] 实现 SSH 部署步骤（docker compose pull + up -d）
- [ ] 实现健康检查等待
- [ ] 实现自动创建 GitHub Release（v* tag 时）
- [ ] 配置 GitHub Environment `Production`：Required Reviewers + Wait timer
- [ ] 验证手动触发需审批才能执行

## 验证

- [ ] 本地 `bump-my-version bump patch` 正确修改文件并创建 tag
- [ ] 本地 `docker compose up -d` 启动成功，所有现有功能正常
- [ ] Push 到 develop 触发构建（`develop-sha-*`）
- [ ] Push 到 release 触发构建（`release-sha-*`）+ 自动部署 UAT
- [ ] UAT 和 Prod 使用同一个镜像（sha 一致）
- [ ] v* tag push 触发 crane 补标签（不重新构建）
- [ ] 手动触发 Deploy Prod 需要审批
- [ ] 容器重启后 `/data` 下的数据不丢失
