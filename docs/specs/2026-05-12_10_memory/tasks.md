# 阶段 10 任务清单：记忆系统

## ChromaDB 集成

- [ ] 安装 chromadb 依赖（已在阶段 1 加入 requirements.txt）
- [ ] 新增 `agent/src/memory/vector.py` 模块
- [ ] 实现 ChromaDB 客户端初始化（PersistentClient，路径 $DATA_DIR/chroma）
- [ ] 实现按用户创建/获取 Collection（`user_{user_id}_memory`）
- [ ] 实现记忆写入函数（documents + metadatas）
- [ ] 实现语义搜索函数（query_texts + where 过滤 + n_results）
- [ ] 实现记忆删除函数
- [ ] 实现记忆统计函数

## 后端 — 记忆 API

- [ ] `GET /api/memories`：查询记忆（支持语义搜索 + metadata 过滤）
- [ ] `DELETE /api/memories/{id}`：删除指定记忆
- [ ] `GET /api/memories/stats`：记忆统计

## 投研引擎集成

- [ ] Agent 执行前：搜索相关历史记忆
- [ ] 将搜索结果注入 Agent system prompt 作为上下文
- [ ] Agent 执行后：从输出中提取洞察
- [ ] 将洞察写入 ChromaDB（含 metadata）
- [ ] 在投研 preset YAML 中配置哪些 Agent 需要读写记忆

## 前端

- [ ] `/memories` 路由和页面
- [ ] 搜索框（语义搜索）
- [ ] 记忆列表（卡片式，显示内容摘要、来源 Agent、时间、关联对象）
- [ ] 类型筛选 Tab（全部/洞察/教训/摘要）
- [ ] 记忆删除操作
- [ ] 统计区域（总数、按类型分布）
- [ ] 导航栏添加记忆入口

## 测试

- [ ] 单元测试：ChromaDB 写入和语义搜索
- [ ] 单元测试：metadata 过滤
- [ ] 单元测试：用户隔离（不同 Collection）
- [ ] 集成测试：投研运行 → Agent 写入记忆 → 下次运行读取记忆
- [ ] 集成测试：语义搜索召回相关性
- [ ] 前端测试：记忆搜索和列表展示
