#***********************************************
#      Filename: supervisor_agent.py
#   Description: 监督智能体
#***********************************************

"""用于协调多个Sub-Research-Agent的监督。该模块实现了一种监督者模式，其中：
1. Supervisor Agent协调研究活动并分配任务
2. 多个Sub-Research-Agent独立地处理特定的子主题
3. 结果汇总并压缩，用于最终技术开发文档
Supervisor Agent采用Send并行派发方式来提高效率，通过hand-off实现每个研究主题的状态隔离。
"""
from langchain_core.messages import BaseMessage, filter_messages, SystemMessage, ToolMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
import logging

from langgraph.constants import END, START
from langgraph.graph import StateGraph
from typing_extensions import Literal
from langgraph.types import Command, Send

from doc_generation.agents.evaluator_agent import evaluate_draft_quality
from doc_generation.agents.red_team_agent import red_team_node
from doc_generation.agents.research_agent import researcher_agent
from doc_generation.llm import get_chat_model
from doc_generation.prompts import MULTI_STEP_DENOISE_PROMPT, CRITICAL_ADDRESS_PROMPT
from doc_generation.states import QualityMetric
from doc_generation.states.supervisor import ConductResearch, ResearchComplete, SupervisorState, ResearchTaskInfo
from doc_generation.tools import _think_tool, _refine_draft_report_tool
from doc_generation.utils import get_today_str, sanitize_tool_messages

logger = logging.getLogger(__name__)

try:
    import nest_asyncio
    try:
        from IPython import get_ipython
        if get_ipython() is not None:
            nest_asyncio.apply()
    except ImportError:
        pass  # Not Jupyter
except ImportError:
    pass

def get_notes_from_tool_calls(messages: list[BaseMessage]) -> list[str]:
    """从Supervisor agent消息历史记录中的 ToolMessage 对象提取Research Notes。
    当Supervisor通过 ConductResearch tools调用将研究任务委托给子代理时，
    每个Sub-Agent 都会返回其压缩的研究结果（以 ToolMessage 内容形式）。
    此函数提取所有此类 ToolMessage 内容，以得到合并后的最终的研究笔记。

    Args：
        messages：主管对话历史记录中的消息列表

    Return：
        从ToolMessage对象中提取的Research Notes字符串列表
    """
    return [tool_msg.content for tool_msg in filter_messages(messages, include_types="tool")]


# ===== CONFIGURATION =====

supervisor_tools_list = [ConductResearch, ResearchComplete, _think_tool, _refine_draft_report_tool]
supervisor_model = get_chat_model("supervisor")
supervisor_model_with_tools = supervisor_model.bind_tools(supervisor_tools_list)


# System constants (最大迭代次数/最大并行Sub-Agents)
max_researcher_iterations = 15 # Calls to think_tool + ConductResearch + refine_draft_report
max_concurrent_researchers = 3 # 最大并行子agent数
min_need_repair_score = 6.0    # 评估低于这个分数，就要出发agent修复提醒


# ===== SUPERVISOR NODES =====

async def supervisor(state: SupervisorState) -> Command[Literal["supervisor_tools"]]:
    """分析研究简报和当前进展
    功能：
        - 需要研究确认的功能点
        - 是否开展并行功能点确认
        - 研究何时完成

    Args：
        state：当前supervisor状态，包含messages和progress

    Returns：
        用于跳转到 supervisor_tools 节点并更新状态的命令
    """
    supervisor_messages = state.get("supervisor_messages", [])
    iteration = state.get("research_iterations", 0)
    logger.info("[SUPERVISOR] supervisor invoked (iteration=%d, messages=%d)", iteration, len(supervisor_messages))

    # 组装系统提示词
    system_message = MULTI_STEP_DENOISE_PROMPT.format(
        date=get_today_str(),
        max_concurrent_research_units=max_concurrent_researchers,
        max_researcher_iterations=max_researcher_iterations
    )
    messages = [SystemMessage(content=system_message)] + sanitize_tool_messages(supervisor_messages)

    # 动态上下文注入：检查并注入任何未处理的对抗性反馈，实现自我纠正机制。
    critiques = state.get("active_critiques", [])
    unaddressed = [c for c in critiques if not c.addressed]
    if unaddressed:
        critique_text = "\n".join([f"- {c.author} says: {c.concern}" for c in unaddressed])
        intervention = SystemMessage(content=CRITICAL_ADDRESS_PROMPT.format(critique_text=critique_text))
        messages.append(intervention)

    # 如果上一次迭代中质量得分较低，则会发出提醒
    if state.get("needs_quality_repair"):
        messages.append(SystemMessage(content="上一稿技术开发文档质量较低（得分低于7/10），请继续完善。"))

    # 决策调用哪一个工具
    response = await supervisor_model_with_tools.ainvoke(messages)
    logger.info(
        "supervisor model produced tool_calls=%s num_tool_calls=%d",
        bool(response.tool_calls),
        len(response.tool_calls or []),
    )

    # 跳转到supervisor_tools
    return Command(
        goto="supervisor_tools",
        update={
            "supervisor_messages": [response],
            "research_iterations": iteration + 1,
            "needs_quality_repair": False  # 在向supervisor发出提醒后，重置修复标志
        }
    )


async def supervisor_tools(state: SupervisorState):
    """
    执行Supervisor决策——继续下一轮研究或者是结束流程。

    功能：
        - 执行 think_tool 调用以进行思考
        - 通过 Send 并行派发研究任务到 research 子图节点（hand-off 状态隔离）
        - 确定研究何时完成

    参数：
        state：包含supervisor messages和迭代次数
        config：RunnableConfig，包含 thread_id 等配置信息

    返回值：
        Command 或 list[Send] 用于并行派发
    """
    supervisor_messages = state.get("supervisor_messages", [])
    research_iterations = state.get("research_iterations", 0)
    most_recent_message = supervisor_messages[-1]

    # 检查是否达到了最大迭代次数或者supervisor是否输出工具调用
    exceeded_iterations = research_iterations >= max_researcher_iterations
    no_tool_calls = not most_recent_message.tool_calls
    research_complete = any(
        tool_call["name"] == "ResearchComplete"
        for tool_call in most_recent_message.tool_calls
    )

    # 如果超过则退出
    if exceeded_iterations or no_tool_calls or research_complete:
        final_notes = get_notes_from_tool_calls(state.get("supervisor_messages", []))
        logger.info("[REPORT] The research is complete, writing the final report.")

        return Command(
            goto=END,
            update={
                "notes": final_notes,
                "research_brief": state.get("research_brief", "")
            })

    # 分类工具调用
    think_tool_calls = [
        tool_call for tool_call in most_recent_message.tool_calls
        if tool_call["name"] == "think_tool"
    ]

    conduct_research_calls = [
        tool_call for tool_call in most_recent_message.tool_calls
        if tool_call["name"] == "ConductResearch"
    ]

    refine_report_calls = [
        tool_call for tool_call in most_recent_message.tool_calls
        if tool_call["name"] == "refine_draft_report"
    ]

    logger.info(
        "[SUPERVISOR] supervisor_tools executing think=%d conduct=%d refine=%d",
        len(think_tool_calls),
        len(conduct_research_calls),
        len(refine_report_calls),
    )

    try:
        tool_messages = []
        updates = {}
        next_step = "supervisor"

        # 调用 think 工具
        for tool_call in think_tool_calls:
            observation = _think_tool.invoke(tool_call["args"])
            logger.info(f"========>[thinking tool] thinking process {observation}")
            tool_messages.append(
                ToolMessage(
                    content=observation,
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"]
                )
            )

        # 使用 Send 并行派发 ConductResearch 到 research 子图节点（hand-off 状态隔离）
        if conduct_research_calls:
            pending_tasks = [
                ResearchTaskInfo(
                    tool_call_id=tc["id"],
                    tool_call_name=tc["name"],
                    research_topic=tc["args"]["research_topic"],
                )
                for tc in conduct_research_calls
            ]

            # 为每个 ConductResearch 写入占位 ToolMessage，保证消息序列完整
            # 使用固定 id 格式，后续 collect_research 会用相同 id 替换内容
            for tc in conduct_research_calls:
                tool_messages.append(
                    ToolMessage(
                        content="[Research in progress...]",
                        name=tc["name"],
                        tool_call_id=tc["id"],
                        id=f"research_placeholder_{tc['id']}"
                    )
                )

            # 通过 Command 跳转到 prepare_research 节点，同时保存状态
            updates["supervisor_messages"] = tool_messages
            updates["pending_research_tasks"] = pending_tasks

            return Command(goto="prepare_research", update=updates)

        # 开始调用大模型结合已有信息修正技术开发文档
        for tool_call in refine_report_calls:
            findings = "\n".join(get_notes_from_tool_calls(state.get("supervisor_messages", [])))

            new_draft = _refine_draft_report_tool.invoke({
                "research_brief": state.get("research_brief", ""),
                "findings": findings,
                "draft_report": state.get("draft_report", "")
            })

            eval_result = evaluate_draft_quality(
                research_brief=state.get("research_brief", ""),
                draft_report=new_draft
            )
            logger.info(
                "[EVALUATOR] comprehensive score=%f, accuracy score=%f, coherence score=%f",
                eval_result.comprehensiveness_score,
                eval_result.accuracy_score,
                eval_result.coherence_score
            )
            logger.info(f"[EVALUATOR] scoing reason: {eval_result.reason}")

            avg_score = (
                eval_result.comprehensiveness_score + eval_result.accuracy_score + eval_result.coherence_score) / 3

            tool_messages.append(ToolMessage(
                content=f"Draft Updated.\nQuality Score: {avg_score}/10.\nJudge Feedback: {eval_result.reason}",
                name=tool_call["name"],
                tool_call_id=tool_call["id"]
            ))

            updates["draft_report"] = new_draft
            updates["quality_history"] = [QualityMetric(
                score=avg_score,
                feedback=eval_result.reason,
                iteration=state.get("research_iterations", 0))
            ]

            if avg_score < min_need_repair_score:
                updates["needs_quality_repair"] = True

            next_step = "red_team"

        updates["supervisor_messages"] = tool_messages
        updates["raw_notes"] = []

        return Command(goto=next_step, update=updates)

    except Exception as e:
        from langgraph.errors import GraphBubbleUp
        from doc_generation.resilience import LLMFatalError, FallbackExhaustedError
        if isinstance(e, GraphBubbleUp):
            raise
        if isinstance(e, (LLMFatalError, FallbackExhaustedError)):
            logger.error("[SUPERVISOR] LLM call failed after all retries and fallbacks: %s", e)
        else:
            logger.exception("[SUPERVISOR] supervisor_tools failed: %s", e)
        return Command(
            goto=END,
            update={
                "notes": get_notes_from_tool_calls(supervisor_messages),
                "research_brief": state.get("research_brief", "")
            }
        )


def prepare_research(state: SupervisorState):
    """Passthrough 节点，仅用于触发条件边派发 Send。"""
    return {}


def route_research(state: SupervisorState, config: RunnableConfig):
    """条件边函数：通过 Send 并行派发研究任务到 research 子图。"""
    pending_tasks = state.get("pending_research_tasks", [])
    parent_thread_id = config.get("configurable", {}).get("thread_id", "")

    sends = [
        Send("research", {
            "researcher_messages": [
                HumanMessage(content=task["research_topic"])
            ],
            "research_topic": task["research_topic"],
            "_parent_thread_id": parent_thread_id,
        })
        for task in pending_tasks
    ]

    logger.info("[DISPATCH] Sending %d research tasks via Send (hand-off)", len(sends))
    return sends


def collect_research(state: SupervisorState) -> Command[Literal["supervisor"]]:
    """收集并行 research 子图结果，用真正内容替换占位 ToolMessage。"""
    pending_tasks = state.get("pending_research_tasks", [])
    compressed_list = state.get("compressed_research", [])
    raw = state.get("raw_notes", [])

    # 用相同 id 替换占位 ToolMessage 的内容
    replacement_messages = []
    for i, task_info in enumerate(pending_tasks):
        content = compressed_list[i] if i < len(compressed_list) else "Error synthesizing research report"
        replacement_messages.append(
            ToolMessage(
                content=content,
                name=task_info["tool_call_name"],
                tool_call_id=task_info["tool_call_id"],
                id=f"research_placeholder_{task_info['tool_call_id']}"
            )
        )

    logger.info("[COLLECT] Collected %d research results", len(replacement_messages))

    return Command(
        goto="supervisor",
        update={
            "supervisor_messages": replacement_messages,
            "raw_notes": raw,
            "pending_research_tasks": [],
        }
    )


# ===== GRAPH CONSTRUCTION =====

supervisor_builder = StateGraph(SupervisorState)
supervisor_builder.add_node("supervisor", supervisor)
supervisor_builder.add_node("supervisor_tools", supervisor_tools)
supervisor_builder.add_node("prepare_research", prepare_research)
supervisor_builder.add_node("research", researcher_agent)
supervisor_builder.add_node("collect_research", collect_research)
supervisor_builder.add_node("red_team", red_team_node)

supervisor_builder.add_edge(START, "supervisor")
supervisor_builder.add_edge("supervisor", "supervisor_tools")
supervisor_builder.add_conditional_edges("prepare_research", route_research, ["research"])
supervisor_builder.add_edge("research", "collect_research")
supervisor_builder.add_edge("red_team", "supervisor")

supervisor_agent = supervisor_builder.compile()


if __name__ == "__main__":
    print(supervisor_agent.get_graph().draw_ascii())
