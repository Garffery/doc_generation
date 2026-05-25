# 初始化模型

import os

from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.types import interrupt
from doc_generation.llm import get_chat_model
from doc_generation import AgentState
from doc_generation.prompts import RESEARCH_BRIEF_PROMPT, DRAFT_REPORT_PROMPT, QUESTION_TO_USER_PROMPT
from langchain_core.messages import AIMessage, HumanMessage, get_buffer_string
from rich.markdown import Markdown
from rich.console import Console
import logging

from doc_generation.states.draft import DraftReport, ResearchQuestion, ClarificationQuestions, ClarificationItem, AgentInputState
from doc_generation.utils import get_today_str, load_config
from doc_generation.logging_config import configure_logging
from doc_generation.skills import build_skills_context
from doc_generation.skills.config import SkillsConfig
from doc_generation.skills.registry import get_or_new_skill_storage, load_skills_config_from_stage

logger = logging.getLogger(__name__)
draft_model = get_chat_model("draft")


def _load_skills_config() -> SkillsConfig:
    config_path = os.environ.get("CONFIG_PATH", "config.yml")
    stage = os.environ.get("STAGE") or "prod"
    stage_cfg = load_config(stage_name=stage, config_path=config_path)
    return load_skills_config_from_stage(stage_cfg or {})


def _skills_section(step: str) -> str:
    skills_cfg = _load_skills_config()
    storage = get_or_new_skill_storage(skills_config=skills_cfg)
    return build_skills_context(skills_cfg, agent="draft", step=step, storage=storage)


def write_research_brief(state: AgentState):
    """根据用户对话生成需求拆解简报（功能点列表），供后续生成开发文档草稿"""

    logger.debug(
        "write research_brief invoked with %d messages", len(state.get("messages", []))
    )

    # 组装prompt
    prompt = RESEARCH_BRIEF_PROMPT.format(
        messages=get_buffer_string(state.get("messages", [])),
        date=get_today_str(),
        skills_section=_skills_section("write_research_brief"),
    )
    logger.debug("write_research_brief invoking structured_output_model with prompt_length=%d", len(prompt))

    # 结构化输出
    structured_output_model = draft_model.with_structured_output(ResearchQuestion)
    response = structured_output_model.invoke([HumanMessage(content=prompt)])
    logger.debug("write_research_brief produced research_brief length=%d", len(response.research_brief))

    return {"research_brief": response.research_brief}


def question_to_user(state: AgentState):
    """根据 research_brief 生成澄清问题（含候选答案），通过 interrupt 暂停等待用户回答"""

    research_brief = state.get("research_brief", "")

    prompt = QUESTION_TO_USER_PROMPT.format(
        research_brief=research_brief,
        date=get_today_str(),
    )

    structured_model = draft_model.with_structured_output(ClarificationQuestions)
    response = structured_model.invoke([HumanMessage(content=prompt)])
    items = [{"question": item.question, "options": item.options} for item in response.items]

    logger.info("question_to_user generated %d questions, interrupting for user input", len(items))

    # interrupt 暂停图执行，将问题及候选答案发送给用户；resume 时返回用户的回答
    answer = interrupt({"questions": items})

    return {
        "clarification_questions": items,
        "clarification_answers": answer,
    }

def write_draft_report(state: AgentState):
    """根据需求拆解简报生成后端开发技术文档草稿"""

    logger.debug(
        "write_draft_report invoked with research_brief present=%s",
        bool(state.get("research_brief")),
    )

    # 组装prompt
    research_brief = state.get("research_brief", "")
    draft_report_prompt = DRAFT_REPORT_PROMPT.format(
        research_brief=research_brief,
        date=get_today_str(),
        skills_section=_skills_section("write_draft_report"),
    )

    # 如果有用户澄清回答，追加到 prompt 上下文
    clarification_answers = state.get("clarification_answers", "")
    if clarification_answers:
        draft_report_prompt += f"\n\n<用户补充说明>\n{clarification_answers}\n</用户补充说明>\n"

    # 结构化输出
    structured_output_model = draft_model.with_structured_output(DraftReport)
    response = structured_output_model.invoke([HumanMessage(content=draft_report_prompt)])
    logger.debug("write_draft_report produced draft_report length=%d", len(response.draft_report))

    return {
        "research_brief": research_brief,
        "draft_report": response.draft_report,
        "supervisor_messages": ["Here is the backend dev doc draft: " + response.draft_report, research_brief]
    }


if __name__  == "__main__":
    configure_logging(level=os.environ.get("LOG_LEVEL", "DEBUG"))

    # 构建Graph
    deep_researcher_builder = StateGraph(AgentState, input_schema=AgentInputState)

    # 增加节点
    deep_researcher_builder.add_node("write_research_brief", write_research_brief)
    deep_researcher_builder.add_node("write_draft_report", write_draft_report)
    deep_researcher_builder.add_node("question_to_user", question_to_user)

    # 增加边
    deep_researcher_builder.add_edge(START, "write_research_brief")
    deep_researcher_builder.add_edge("write_research_brief", "question_to_user")
    deep_researcher_builder.add_edge("question_to_user", "write_draft_report")
    deep_researcher_builder.add_edge("write_draft_report", END)

    # 编译graph
    draft_agent = deep_researcher_builder.compile()

    # 打印graph
    print(draft_agent.get_graph().draw_ascii())

    # 测试问题
    thread = {"configurable": {"thread_id": "1", "recursion_limit": 50}}
    result = draft_agent.invoke({"messages": [HumanMessage(content="""
游戏中需要开发一个战令活动,这个战令总共有三档,一档免费战令,"进阶福利","天降豪礼"这两档付费直购战令。
活动逻辑: 1.点击战令入口，弹出战令界面，显示战令的奖励,能领取的奖励高亮,未达到领取条件的奖励置灰。
         2. 点击战令界面上的物品，如果有满足战令等级的奖励，会一次性全部领取
         3.如果没有购买"进阶福利"和"天降豪礼",则只能领取免费战令对应的奖励
战令等级:
		战令一共有15个等级，玩家没累计1000积分可以提升一个等级

积分:
	在游戏中完成相应的任务，能够获得对应任务的积分。

活动结算:
	如果活动结束的时候,玩家存在满足领取条件的奖励，但是未领取，需要通过邮件补发的方式进行奖励补发。
    """)]},
                                config=thread)

    # 输出
    console = Console()
    print("=====  Research Brief ====")
    # console.print(Markdown(result["research_brief"]))
    # print("====Research Brief end====")

    print("=====  Draft Report ====")
    console.print(Markdown(result["draft_report"]))