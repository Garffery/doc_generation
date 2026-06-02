import json
import logging
import traceback
import uuid
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from backend.db import create_ticket, update_ticket_status, init_report, update_report_stage, get_ticket_id_by_thread
from doc_generation.utils import load_config


def _get_recursion_limit() -> int:
    cfg = load_config(stage_name="prod", config_path="config.yml") or {}
    return int(cfg.get("graph", {}).get("recursion_limit", 25))

logger = logging.getLogger(__name__)


async def run_agent_stream(message: str) -> AsyncGenerator[str, None]:
    """调用 LangGraph agent 并通过 SSE 流式返回中间状态和最终结果"""

    from doc_generation.agent_builder import agent

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": _get_recursion_limit()}
    input_state = {"messages": [HumanMessage(content=message)]}

    try:
        ticket_id = await create_ticket(message, thread_id)
        await init_report(ticket_id, message)
        yield _sse_event("session", {"thread_id": thread_id, "ticket_id": ticket_id})
        yield _sse_event("status", {"stage": "started", "message": "开始生成文档..."})
        await update_ticket_status(ticket_id, "running")

        async for event in agent.astream_events(input_state, config=config, version="v2"):
            kind = event.get("event")
            name = event.get("name", "")

            if kind == "on_chain_error":
                err_msg = str(event.get("data", {}).get("error", "Unknown error"))
                with open("logs/agent_error.log", "a", encoding="utf-8") as f:
                    f.write(f"\non_chain_error: name={name}, event={json.dumps(event, default=str, ensure_ascii=False)[:2000]}\n")

            if kind == "on_chain_start" and name in (
                "write_research_brief",
                "question_to_user",
                "write_draft_report",
                "supervisor_subgraph",
                "final_report_generation",
            ):
                stage_labels = {
                    "write_research_brief": "正在拆解需求...",
                    "question_to_user": "正在生成澄清问题...",
                    "write_draft_report": "正在生成文档草稿...",
                    "supervisor_subgraph": "正在深度研究与优化...",
                    "final_report_generation": "正在生成最终报告...",
                }
                yield _sse_event("status", {
                    "stage": name,
                    "message": stage_labels.get(name, name),
                })

            elif kind == "on_chain_end" and name in (
                "write_research_brief",
                "write_draft_report",
            ):
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    if "research_brief" in output:
                        await update_report_stage(ticket_id, "research_brief", output["research_brief"])
                        yield _sse_event("progress", {
                            "stage": "research_brief",
                            "content": output["research_brief"],
                        })
                    if "draft_report" in output:
                        await update_report_stage(ticket_id, "draft_report", output["draft_report"])
                        yield _sse_event("progress", {
                            "stage": "draft_report",
                            "content": output["draft_report"],
                        })

            elif kind == "on_chain_end" and name == "final_report_generation":
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict) and "final_report" in output:
                    await update_report_stage(ticket_id, "final_report", output["final_report"])
                    yield _sse_event("result", {
                        "content": output["final_report"],
                    })

        # 流结束后检查是否因 interrupt 暂停
        state = await agent.aget_state(config)
        if state.tasks and any(
            hasattr(t, "interrupts") and t.interrupts for t in state.tasks
        ):
            interrupt_value = state.tasks[0].interrupts[0].value
            yield _sse_event("interrupt", {
                "thread_id": thread_id,
                "questions": json.dumps(interrupt_value.get("questions", []), ensure_ascii=False),
            })
        else:
            await update_ticket_status(ticket_id, "done")

    except Exception as e:
        logger.exception("Agent execution failed")
        tb = traceback.format_exc()
        import pathlib
        log_path = pathlib.Path(__file__).resolve().parent.parent / "logs" / "agent_error.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n{tb}\n")
        await update_ticket_status(ticket_id, "error")
        yield _sse_event("error", {"message": str(e)})


async def resume_agent_stream(thread_id: str, answers: str) -> AsyncGenerator[str, None]:
    """用户回答澄清问题后恢复 graph 执行"""

    from doc_generation.agent_builder import agent

    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": _get_recursion_limit()}
    ticket_id = await get_ticket_id_by_thread(thread_id)

    try:
        yield _sse_event("status", {"stage": "question_to_user", "message": "正在处理您的回答..."})

        async for event in agent.astream_events(
            Command(resume=answers), config=config, version="v2"
        ):
            kind = event.get("event")
            name = event.get("name", "")

            if kind == "on_chain_start" and name in (
                "question_to_user",
                "write_draft_report",
                "supervisor_subgraph",
                "final_report_generation",
            ):
                stage_labels = {
                    "question_to_user": "正在处理您的回答...",
                    "write_draft_report": "正在生成文档草稿...",
                    "supervisor_subgraph": "正在深度研究与优化...",
                    "final_report_generation": "正在生成最终报告...",
                }
                yield _sse_event("status", {
                    "stage": name,
                    "message": stage_labels.get(name, name),
                })

            elif kind == "on_chain_end" and name == "write_draft_report":
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict) and "draft_report" in output:
                    if ticket_id:
                        await update_report_stage(ticket_id, "draft_report", output["draft_report"])
                    yield _sse_event("progress", {
                        "stage": "draft_report",
                        "content": output["draft_report"],
                    })

            elif kind == "on_chain_end" and name == "final_report_generation":
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict) and "final_report" in output:
                    if ticket_id:
                        await update_report_stage(ticket_id, "final_report", output["final_report"])
                        await update_ticket_status(ticket_id, "done")
                    yield _sse_event("result", {
                        "content": output["final_report"],
                    })

    except Exception as e:
        logger.exception("Agent resume failed")
        if ticket_id:
            await update_ticket_status(ticket_id, "error")
        yield _sse_event("error", {"message": str(e)})


async def retry_agent_stream(ticket_id: str, thread_id: str) -> AsyncGenerator[str, None]:
    """进程崩溃后，从 MongoDB checkpoint 恢复执行"""

    from doc_generation.agent_builder import agent

    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": _get_recursion_limit()}

    try:
        await update_ticket_status(ticket_id, "running")
        yield _sse_event("session", {"thread_id": thread_id, "ticket_id": ticket_id})

        # 先检查 checkpoint 中是否有 interrupt（上次停在 question_to_user）
        state = await agent.aget_state(config)
        if state.tasks and any(
            hasattr(t, "interrupts") and t.interrupts for t in state.tasks
        ):
            interrupt_value = state.tasks[0].interrupts[0].value
            yield _sse_event("interrupt", {
                "thread_id": thread_id,
                "questions": json.dumps(interrupt_value.get("questions", []), ensure_ascii=False),
            })
            return

        # 从 checkpoint 恢复执行：传 None 让 LangGraph 从上次完成的节点继续
        yield _sse_event("status", {"stage": "retry", "message": "正在从断点恢复..."})

        async for event in agent.astream_events(None, config=config, version="v2"):
            kind = event.get("event")
            name = event.get("name", "")

            if kind == "on_chain_start" and name in (
                "write_research_brief",
                "question_to_user",
                "write_draft_report",
                "supervisor_subgraph",
                "final_report_generation",
            ):
                stage_labels = {
                    "write_research_brief": "正在拆解需求...",
                    "question_to_user": "正在生成澄清问题...",
                    "write_draft_report": "正在生成文档草稿...",
                    "supervisor_subgraph": "正在深度研究与优化...",
                    "final_report_generation": "正在生成最终报告...",
                }
                yield _sse_event("status", {
                    "stage": name,
                    "message": stage_labels.get(name, name),
                })

            elif kind == "on_chain_end" and name in (
                "write_research_brief",
                "write_draft_report",
            ):
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    if "research_brief" in output:
                        await update_report_stage(ticket_id, "research_brief", output["research_brief"])
                        yield _sse_event("progress", {
                            "stage": "research_brief",
                            "content": output["research_brief"],
                        })
                    if "draft_report" in output:
                        await update_report_stage(ticket_id, "draft_report", output["draft_report"])
                        yield _sse_event("progress", {
                            "stage": "draft_report",
                            "content": output["draft_report"],
                        })

            elif kind == "on_chain_end" and name == "final_report_generation":
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict) and "final_report" in output:
                    await update_report_stage(ticket_id, "final_report", output["final_report"])
                    yield _sse_event("result", {
                        "content": output["final_report"],
                    })

        # 流结束后检查是否因 interrupt 暂停
        state = await agent.aget_state(config)
        if state.tasks and any(
            hasattr(t, "interrupts") and t.interrupts for t in state.tasks
        ):
            interrupt_value = state.tasks[0].interrupts[0].value
            yield _sse_event("interrupt", {
                "thread_id": thread_id,
                "questions": json.dumps(interrupt_value.get("questions", []), ensure_ascii=False),
            })
        else:
            await update_ticket_status(ticket_id, "done")

    except Exception as e:
        logger.exception("Agent retry failed")
        tb = traceback.format_exc()
        import pathlib
        log_path = pathlib.Path(__file__).resolve().parent.parent / "logs" / "agent_error.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n{tb}\n")
        await update_ticket_status(ticket_id, "error")
        yield _sse_event("error", {"message": str(e)})


def _sse_event(event_type: str, data: dict) -> str:
    """格式化 SSE 事件"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
