#***********************************************
#      Filename: agent_builder.py
#   Description: 多智能体深度研究Builder 
#***********************************************


from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.mongodb import MongoDBSaver

from doc_generation.utils import get_today_str
from doc_generation.states import AgentState, AgentInputState
from doc_generation.prompts import FINAL_REPORT_PROMPT
from doc_generation.agents import write_research_brief, write_draft_report, question_to_user
from doc_generation.agents import supervisor_agent
from doc_generation.llm import get_chat_model


# ===== Config =====

writer_model = get_chat_model("writer")


# ===== FINAL REPORT GENERATION =====

async def final_report_generation(state: AgentState):
    """最终报告的生成: 用户query，研究简报，findings, 报告初稿 => 报告
    """

    # 取出所有的notes
    notes = state.get("notes", [])
    findings = "\n".join(notes)

    # 组装prompt
    final_report_prompt = FINAL_REPORT_PROMPT.format(
        research_brief=state.get("research_brief", ""),
        findings=findings,
        date=get_today_str(),
        draft_report=state.get("draft_report", "")
    )

    # 生成最后的报告
    final_report = await writer_model.ainvoke([HumanMessage(content=final_report_prompt)])

    return {
        "final_report": final_report.content,
        "messages": ["最终的报告: " + final_report.content],
    }


# ===== 图的构建 =====

# 构建深度研究的workflow
deep_researcher_builder = StateGraph(AgentState, input_schema=AgentInputState)

# 添加节点
deep_researcher_builder.add_node("write_research_brief", write_research_brief)
deep_researcher_builder.add_node("question_to_user", question_to_user)
deep_researcher_builder.add_node("write_draft_report", write_draft_report)
deep_researcher_builder.add_node("supervisor_subgraph", supervisor_agent)
deep_researcher_builder.add_node("final_report_generation", final_report_generation)

# 添加边
deep_researcher_builder.add_edge(START, "write_research_brief")
deep_researcher_builder.add_edge("write_research_brief", "question_to_user")
deep_researcher_builder.add_edge("question_to_user", "write_draft_report")
deep_researcher_builder.add_edge("write_draft_report", "supervisor_subgraph")
deep_researcher_builder.add_edge("supervisor_subgraph", "final_report_generation")
deep_researcher_builder.add_edge("final_report_generation", END)

# 编译graph（使用 MongoDB 持久化 checkpoint，支持 interrupt/resume 跨重启恢复）
import os
from pymongo import MongoClient

_mongo_client = MongoClient(os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
checkpointer = MongoDBSaver(_mongo_client, db_name="doc_generation")
agent = deep_researcher_builder.compile(checkpointer=checkpointer)
