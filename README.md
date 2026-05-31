# doc_generation

Python project for document generation.

## 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Frontend (React + Vite)                      │
│                         http://localhost:5173                         │
├─────────────────────────────────────────────────────────────────────┤
│  InputForm ──► ProgressBar ──► ClarificationPanel ──► ReportView    │
│                                                                      │
│  SSE Events: session / status / progress / interrupt / result        │
└────────────────────────────┬────────────────────────────────────────┘
                             │ POST /api/generate (SSE)
                             │ POST /api/resume   (SSE)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI + Uvicorn)                       │
│                      http://localhost:8000                            │
├─────────────────────────────────────────────────────────────────────┤
│  routes.py ──► service.py ──► agent_builder.py (LangGraph)           │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   LangGraph Workflow (StateGraph)                     │
│                                                                      │
│  ┌──────────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │ write_research   │    │ question_to_user │    │ write_draft   │  │
│  │ _brief           │───►│ (interrupt)      │───►│ _report       │  │
│  └──────────────────┘    └──────────────────┘    └───────┬───────┘  │
│                                                          │          │
│                                                          ▼          │
│  ┌──────────────────┐    ┌──────────────────────────────────────┐   │
│  │ final_report     │◄───│ supervisor_subgraph                  │   │
│  │ _generation      │    │ (research_agent + evaluator + ...)   │   │
│  └──────────────────┘    └──────────────────────────────────────┘   │
│                                                                      │
│  Checkpointer: MemorySaver (支持 interrupt/resume)                   │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        External Services                             │
├─────────────────────────────────────────────────────────────────────┤
│  • LLM (OpenAI API / langchain-openai)                              │
│  • ChromaDB (RAG 向量检索)                                           │
│  • Claude Code SDK (代码工具调用)                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 核心流程

```
用户输入需求
    │
    ▼
write_research_brief ── 需求拆解，生成功能点列表 (F-001, F-002...)
    │
    ▼
question_to_user ────── LLM 生成澄清问题（含候选答案），interrupt 暂停等待用户选择
    │
    ▼
write_draft_report ──── 结合用户回答，生成后端技术文档草稿
    │
    ▼
supervisor_subgraph ─── 多轮深度研究与优化（research_agent / evaluator / red_team）
    │
    ▼
final_report_generation ── 汇总生成最终技术文档
```

### 目录结构

```
doc_generation/
├── agent_builder.py        # LangGraph 主图构建
├── agents/                 # 各节点实现
│   ├── draft_agent.py      # write_research_brief / question_to_user / write_draft_report
│   ├── supervisor.py       # supervisor 子图
│   ├── research_agent.py   # 研究 agent
│   └── evaluator_agent.py  # 评估 agent
├── states/                 # State 定义 (Pydantic models)
├── prompts/                # 各环节 Prompt
├── tools/                  # LangGraph 工具 (RAG, Claude Code)
├── rag/                    # ChromaDB 向量存储
├── skills/                 # 技能系统 (SKILL.md 加载)
└── llm.py                  # LLM 模型配置

backend/
├── app.py                  # FastAPI 应用入口
├── api/routes.py           # API 路由 (/generate, /resume)
├── service.py              # SSE 流式服务
└── schemas.py              # 请求/响应模型

frontend/src/
├── App.tsx                 # 主应用 (状态管理)
├── api.ts                  # SSE 流式 API 客户端
└── components/
    ├── InputForm.tsx       # 需求输入
    ├── ProgressBar.tsx     # 进度条 (5阶段)
    ├── ClarificationPanel.tsx  # 澄清问答 (选择题+其他)
    └── ReportView.tsx      # Markdown 文档渲染
```

## 新增功能：Claude Code 异步执行架构

本次更新将 `claude_code_tool` 从同步调用改为基于 ARQ + Redis 的异步执行模式，避免长时间运行的 Claude Code 任务阻塞 LangGraph 主流程。

### 架构概览

```
research_agent (LangGraph 子图)
    │
    ├── tool_node 检测到 claude_code 调用
    │       │
    │       ▼
    │   dispatch_claude_code_tool ──► ARQ Redis 队列
    │       │
    │       ▼
    │   wait_for_claude_code ──► interrupt 挂起子图
    │
    │                               ARQ Worker (独立进程)
    │                                   │
    │                                   ▼
    │                           执行 _run_claude_code
    │                                   │
    │                                   ▼
    │                           结果写入 Redis
    │                                   │
    │                                   ▼
    │                           POST /api/internal/resume/researcher/{thread_id}
    │                                   │
    │       ┌───────────────────────────┘
    │       ▼
    │   collect_claude_code_result ──► 封装 ToolMessage
    │       │
    │       ▼
    │   llm_call (继续推理)
    │
    ▼
supervisor 轮询等待 interrupt 恢复
```

### 关键组件

| 组件 | 文件 | 说明 |
|------|------|------|
| ARQ Worker | `doc_generation/worker.py` | 独立进程，监听 Redis 队列执行 claude_code_tool，结果存入 Redis |
| 异步派发 | `doc_generation/agents/research_agent.py` | tool_node 将 claude_code 调用派发到 ARQ 队列 |
| Interrupt/Resume | `doc_generation/agents/research_agent.py` | wait_for_claude_code 节点通过 interrupt 挂起，等待 Worker 完成后恢复 |
| 回调端点 | `backend/api/routes.py` | `POST /api/internal/resume/researcher/{thread_id}` 恢复子图执行 |
| Supervisor 适配 | `doc_generation/agents/supervisor.py` | 为每个 researcher 分配独立 thread_id，轮询等待 interrupt 恢复 |
| MongoDB Checkpointer | `doc_generation/agents/research_agent.py` | researcher 子图使用 MongoDBSaver 支持 interrupt/resume 持久化 |

### 新增依赖

- `arq` — 基于 Redis 的异步任务队列
- `redis` / `redis.asyncio` — Redis 客户端
- `pymongo` + `langgraph-checkpoint-mongodb` — researcher 子图的 checkpoint 持久化
- `httpx` — Worker 回调通知

### 配置变更

`config.yml` 新增 `claude_code.cwd` 字段，指定 Claude Code 工具的工作目录：

```yaml
stages:
  prod:
    claude_code:
      cwd: D:\project\project_data
```

环境变量：
- `REDIS_URL` — Redis 连接地址（默认 `redis://localhost:6379`）
- `MONGODB_URI` — MongoDB 连接地址（默认 `mongodb://localhost:27017`）
- `RESUME_CALLBACK_URL` — Worker 回调地址（默认 `http://localhost:8000/api/internal/resume/researcher`）

### 启动方式

`start.bat` / `stop.bat` 已更新，自动管理 ARQ Worker 进程：

```bash
# 手动启动 Worker
python -m arq doc_generation.worker.WorkerSettings
```

## Setup

```bash
cd doc_generation
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Run

```bash
# 后端
uvicorn backend.app:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev
```

## Test

```bash
pytest
```

## RAG（Chroma）

在 `config.yml` 的 `stages.<stage>.rag` 中配置 Chroma 持久化目录与集合名。启用后，`research_agent` 会自动绑定 `rag_search` 工具，供 LangGraph 的 `tool_node` 调用。

将文档写入知识库：

```bash
doc-generation-rag-ingest skills/public/erlang-socket-protocol-doc/SKILL.md
# 或
python -m doc_generation.rag.ingest path/to/docs/
```

在自定义图中使用：

```python
from doc_generation.tools import _rag_search_tool

tools = [_rag_search_tool]
tools_by_name = {t.name: t for t in tools}
model_with_tools = model.bind_tools(tools)
```
