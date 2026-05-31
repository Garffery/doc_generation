#***********************************************
#      Filename: research_agent.py
#   Description:  研究智能体
#***********************************************

"""Research Agent核心实现
该文件实现了一个 Research Agent，通过本地知识库检索与反思循环收集信息并综合回答研究问题。
支持 _claude_code_tool 的异步执行：通过 ARQ 派发任务并使用 interrupt/resume 模式等待结果。
"""

import uuid
from typing_extensions import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, filter_messages

from doc_generation.llm import get_chat_model
from doc_generation.states import ResearcherState, ResearcherOutputState
from doc_generation.utils import get_today_str
from doc_generation.tools import _think_tool, _rag_search_tool, _claude_code_tool
from doc_generation.rag import is_rag_enabled
from doc_generation.prompts import RESEARCH_AGENT_PROMPT, COMPRESS_RESEARCH_SYSTEM_PROMPT, COMPRESS_RESEARCH_HUMAN_PROMPT
import logging

logger = logging.getLogger(__name__)


# ===== CONFIGURATION =====

# 初始化 tools：知识库检索 + 反思（不使用网络搜索）
tools = [_think_tool]
if is_rag_enabled():
    tools.insert(0, _rag_search_tool)
tools_by_name = {tool.name: tool for tool in tools}

# 初始化模型
model = get_chat_model("researcher_main")
model_with_tools = model.bind_tools(tools)
compress_model = get_chat_model("researcher_compressor")


# ===== AGENT NODES =====

MAX_TOOL_CALL_ITERATIONS = 5

def llm_call(state: ResearcherState):
    """根据当前状态决策下一步的动作"""

    msg_count = len(state.get("researcher_messages", []))
    iterations = state.get("tool_call_iterations", 0)
    logger.debug("llm_call invoked with %d messages, iteration=%d", msg_count, iterations)

    # 调用大模型
    response = model_with_tools.invoke(
        [SystemMessage(content=RESEARCH_AGENT_PROMPT)] + state["researcher_messages"]
    )

    logger.info(
        "llm_call produced response tool_calls=%s num_tool_calls=%d iteration=%d",
        bool(response.tool_calls),
        len(response.tool_calls or []),
        iterations,
    )
    return {
        "researcher_messages": [response],
        "tool_call_iterations": iterations + 1,
    }


async def dispatch_claude_code_tool(tool_args: dict, job_id: str, thread_id: str) -> None:
    """将 _claude_code_tool 任务派发到 ARQ 队列"""
    import os
    from arq import create_pool
    from arq.connections import RedisSettings

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    redis_settings = RedisSettings.from_dsn(redis_url)
    pool = await create_pool(redis_settings)
    await pool.enqueue_job(
        "run_claude_code_tool",
        job_id,
        thread_id,
        tool_args,
        _job_id=job_id,
    )
    await pool.aclose()
    logger.info("[DISPATCH] Enqueued claude_code_tool job_id=%s thread_id=%s", job_id, thread_id)


def tool_node(state: ResearcherState) -> Command:
    """根据前一次大模型结果执行所有工具调用。
    _claude_code_tool 会被异步派发到 ARQ，其他工具同步执行。
    始终返回 Command 以支持动态路由。
    """

    tool_calls = state["researcher_messages"][-1].tool_calls
    logger.info("tool_node executing %d tool calls", len(tool_calls or []))

    tool_outputs = []
    claude_code_call = None

    for tool_call in tool_calls:
        if tool_call["name"] == "claude_code":
            claude_code_call = tool_call
        else:
            tool = tools_by_name[tool_call["name"]]
            logger.info("Invoking tool %s with args=%s", tool_call["name"], tool_call["args"])
            observation = tool.invoke(tool_call["args"])
            tool_outputs.append(
                ToolMessage(
                    content=observation,
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"]
                )
            )

    if claude_code_call is not None:
        dispatched = state.get("_claude_code_dispatched", False)
        if dispatched:
            logger.info("[TOOL_NODE] claude_code already dispatched, skipping")
            return Command(goto="llm_call", update={"researcher_messages": tool_outputs})

        job_id = str(uuid.uuid4())
        thread_id = state.get("_parent_thread_id", "")

        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(
                    asyncio.run,
                    dispatch_claude_code_tool(claude_code_call["args"], job_id, thread_id)
                ).result()
        else:
            asyncio.run(dispatch_claude_code_tool(claude_code_call["args"], job_id, thread_id))

        logger.info("[TOOL_NODE] Dispatched claude_code job_id=%s, transitioning to wait_for_claude_code", job_id)

        return Command(
            goto="wait_for_claude_code",
            update={
                "researcher_messages": tool_outputs,
                "claude_code_job_id": job_id,
                "claude_code_tool_call_id": claude_code_call["id"],
                "_claude_code_dispatched": True,
            }
        )

    return Command(goto="llm_call", update={"researcher_messages": tool_outputs})


async def wait_for_claude_code(state: ResearcherState) -> Command:
    """检查 Redis 中 claude_code 任务是否完成，未完成则 interrupt 挂起子图。"""
    import os
    import redis.asyncio as aioredis

    job_id = state.get("claude_code_job_id", "")
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    r = aioredis.from_url(redis_url, decode_responses=True)

    try:
        result_key = f"claude_code_job:{job_id}"
        error_key = f"claude_code_job:{job_id}:error"

        result = await r.get(result_key)
        error = await r.get(error_key)

        if result is not None:
            logger.info("[WAIT] claude_code job %s completed successfully", job_id)
            return Command(
                goto="collect_claude_code_result",
                update={"claude_code_result": result}
            )

        if error is not None:
            logger.warning("[WAIT] claude_code job %s failed: %s", job_id, error)
            return Command(
                goto="collect_claude_code_result",
                update={"claude_code_result": f"Error: {error}"}
            )

        logger.info("[WAIT] claude_code job %s not yet complete, interrupting", job_id)
        interrupt({"job_id": job_id, "status": "pending"})
        return Command(goto="wait_for_claude_code")
    finally:
        await r.aclose()


def collect_claude_code_result(state: ResearcherState) -> dict:
    """将 claude_code 异步执行结果封装为 ToolMessage 并重置派发标志。"""

    result = state.get("claude_code_result", "")
    tool_call_id = state.get("claude_code_tool_call_id", "")

    tool_message = ToolMessage(
        content=result,
        name="claude_code",
        tool_call_id=tool_call_id,
    )

    logger.info("[COLLECT] Collected claude_code result, tool_call_id=%s, length=%d", tool_call_id, len(result))

    return {
        "researcher_messages": [tool_message],
        "claude_code_job_id": "",
        "claude_code_result": "",
        "claude_code_tool_call_id": "",
        "_claude_code_dispatched": False,
    }


def compress_research(state: ResearcherState) -> dict:
    """把研究发现压缩为高价值摘要，只保留有用信息."""

    # 组装prompt
    system_message = COMPRESS_RESEARCH_SYSTEM_PROMPT.format(date=get_today_str())
    messages = [SystemMessage(content=system_message)] + state.get("researcher_messages", []) +\
            [HumanMessage(content=COMPRESS_RESEARCH_HUMAN_PROMPT.format(research_topic=state.get("research_topic", "")))]
    logger.info("compress_research invoked with %d messages", len(messages))

    # 调用summary模型
    response = compress_model.invoke(messages)

    # 从messages和tools抽取raw notes
    raw_notes = [
        str(m.content) for m in filter_messages(
            state["researcher_messages"],
            include_types=["tool", "ai"]
        )
    ]

    logger.debug("compress_research produced raw_notes_count=%d", len(raw_notes))
    return {
        "compressed_research": [str(response.content)],
        "raw_notes": ["\n".join(raw_notes)]
    }

# ===== ROUTING LOGIC =====

def should_continue(state: ResearcherState) -> Literal["tool_node", "compress_research"]:
    """Determine whether to continue research or provide final answer."""
    messages = state["researcher_messages"]
    last_message = messages[-1]
    iterations = state.get("tool_call_iterations", 0)

    if iterations >= MAX_TOOL_CALL_ITERATIONS:
        logger.info("should_continue: max iterations reached (%d), forcing compress_research", iterations)
        return "compress_research"

    decision = "tool_node" if last_message.tool_calls else "compress_research"
    logger.info("should_continue decision=%s (has_tool_calls=%s, iteration=%d)", decision, bool(last_message.tool_calls), iterations)
    return decision


# ===== GRAPH CONSTRUCTION =====

# Build the agent
agent_builder = StateGraph(ResearcherState, output_schema=ResearcherOutputState)

# Add nodes to the graph
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)
agent_builder.add_node("wait_for_claude_code", wait_for_claude_code)
agent_builder.add_node("collect_claude_code_result", collect_claude_code_result)
agent_builder.add_node("compress_research", compress_research)

# Add edges to connect nodes
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    {
        "tool_node": "tool_node", # Continue research loop
        "compress_research": "compress_research", # 返回 final answer
    },
)
agent_builder.add_edge("wait_for_claude_code", "collect_claude_code_result")
agent_builder.add_edge("collect_claude_code_result", "llm_call")  # 异步结果回收后继续
agent_builder.add_edge("compress_research", END)

# Compile the agent (with checkpointer to support interrupt/resume)
import os
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient

_researcher_mongo_client = MongoClient(os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
_researcher_checkpointer = MongoDBSaver(_researcher_mongo_client, db_name="doc_generation_researcher")
researcher_agent = agent_builder.compile(checkpointer=_researcher_checkpointer)

if __name__ == "__main__":
    print(researcher_agent.get_graph().draw_ascii())
