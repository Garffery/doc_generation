# doc_generation

基于 LangGraph 的多智能体技术文档自动生成系统，支持 RAG 检索增强、人机交互式澄清问答、异步 Claude Code 代码执行，以及生产级容错机制。

## 架构

```
用户输入 (React 前端 :5173)
    ↓  POST /api/generate (SSE)
FastAPI 后端 (:8000)
    ↓
LangGraph StateGraph
    ├─ write_research_brief    需求分解，生成功能点列表
    ├─ question_to_user        生成澄清问题，interrupt 暂停等待用户
    ├─ write_draft_report      结合用户回答生成初稿
    ├─ supervisor_subgraph     多轮精炼（researcher + evaluator + red_team）
    └─ final_report_generation 汇总输出最终文档
```

**技术栈**

| 组件 | 技术 |
|------|------|
| 前端 | React + Vite (TypeScript) |
| 后端 | FastAPI + Uvicorn |
| 工作流 | LangGraph StateGraph |
| LLM | OpenAI / DeepSeek（备用链） |
| 向量库 | ChromaDB + BGE-M3 |
| 任务队列 | ARQ + Redis（异步 Claude Code） |
| 检查点 | MongoDB（interrupt/resume 持久化） |
| 网络搜索 | Tavily |

## 快速开始

**前置条件**：Python 3.10+、Node.js 18+、MongoDB、Redis

```bash
# 安装
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
cd frontend && npm install

# 配置
cp .env.example .env  # 填写 API Key 等

# 启动（Windows 一键）
start.bat

# 或手动分别启动
uvicorn backend.app:app --reload --port 8000
cd frontend && npm run dev
python -m arq doc_generation.worker.WorkerSettings
```

访问 `http://localhost:5173`。

## 配置

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB 连接串 |
| `REDIS_URL` | `redis://localhost:6379` | Redis 连接串 |
| `RESUME_CALLBACK_URL` | `http://localhost:8000/api/internal/resume/researcher` | ARQ 完成回调地址 |
| `CONFIG_PATH` | `config.yml` | 配置文件路径 |

### config.yml 主要配置项

```yaml
stages:
  prod:
    claude_code:
      cwd: D:\project\project_data   # Claude Code 工具工作目录
    resilience:
      retry:
        max_attempts: 3
        base_delay: 1.0
        max_delay: 30.0
      circuit_breaker:
        failure_threshold: 5         # 失败 5 次后熔断
        recovery_timeout: 60
    rag:
      persist_directory: ./chroma_db
    skills:
      enabled: [erlang-player-data-storage, erlang-socket-protocol-doc]
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/generate` | 发起文档生成（SSE 流式） |
| POST | `/api/resume` | 回答澄清问题后恢复 |
| POST | `/api/retry` | 从 MongoDB 检查点重试 |
| GET | `/api/tickets` | 查看任务列表 |

SSE 事件类型：`session` / `status` / `progress` / `interrupt` / `result` / `error`

## RAG 知识库

```bash
# 导入文档
doc-generation-rag-ingest skills/public/erlang-socket-protocol-doc/SKILL.md

# 批量导入
python -m doc_generation.rag.ingest path/to/docs/
```

领域知识文档放在 `skills/public/<name>/SKILL.md`，在 `config.yml` 的 `skills.enabled` 中启用后自动注入对应 Agent 的提示词。

## 容错机制

- **重试**：指数退避（5xx/超时），固定延迟（429），不重试（401/403）
- **熔断器**：短期高频失败后自动停止调用，60s 后半开恢复
- **LLM 备用链**：OpenAI → DeepSeek → 静态响应，每个角色独立配置
- **成本追踪**：记录调用次数与成本，支持渐进式退款

详见 [docs/tool_error_handling.md](docs/tool_error_handling.md)。

## Claude Code 异步执行

`claude_code_tool` 通过 ARQ + Redis 异步执行，避免阻塞 LangGraph 主流程：

```
research_agent
  └─ dispatch_claude_code_tool ──► ARQ Redis 队列
  └─ wait_for_claude_code      ──► interrupt 挂起

ARQ Worker（独立进程）
  └─ 执行 claude_code
  └─ 结果写入 Redis
  └─ POST /api/internal/resume/researcher/{thread_id} ──► 恢复子图
```

## 目录结构

```
doc_generation/
├── agents/             # draft_agent, research_agent, supervisor, evaluator, red_team
├── tools/              # rag_search, think, claude_code
├── rag/                # ChromaDB 向量存储
├── skills/             # 可插拔知识注入
├── states/             # LangGraph State 定义
├── prompts/            # 各阶段提示词
├── agent_builder.py    # StateGraph 编译入口
├── llm.py              # LLM 工厂（含 fallback 链）
└── worker.py           # ARQ Worker
backend/
├── app.py
├── api/routes.py
├── service.py          # SSE 流式逻辑
└── db.py               # MongoDB 操作
frontend/src/
├── App.tsx
├── api.ts
└── components/         # InputForm, ProgressBar, ClarificationPanel, ReportView
skills/public/          # 领域知识文档（SKILL.md）
config.yml
```

## 测试

```bash
pytest
```
