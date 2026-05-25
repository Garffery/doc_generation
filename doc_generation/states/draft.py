#***********************************************
#      Filename: state_draft.py
#   Description: 报告草稿的结构化字段定义 
#***********************************************

"""用于draft State格式定义。
这定义了用于State对象和结构化模式，包括状态管理和输入输出格式。
"""

import operator
from typing_extensions import Optional, Annotated, List, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


# ===== STATE DEFINITIONS =====

class AgentInputState(MessagesState):
    """Agent的输入状态 - 仅包含来自用户输入的消息"""
    pass

class AgentState(MessagesState):
    """多Agent深度研究系统的主状态。
    扩展 MessagesState，添加用于研究协调的附加字段。
    注意：为了正确定义状态，某些字段在不同的状态类中重复出现。子图与主工作流之间的管理。
    """

    research_brief: Optional[str]                                           # 根据用户对话历史生成的需求拆解简报（功能点列表）
    clarification_questions: Optional[list[dict]]                            # LLM生成的澄清问题（含候选答案）
    clarification_answers: Optional[str]                                    # 用户对澄清问题的回答
    supervisor_messages: Annotated[Sequence[BaseMessage], add_messages]     # 与Supervisor Agent交换的协调消息
    raw_notes: Annotated[list[str], operator.add] = []                      # 研究阶段收集的原始未处理研究笔记
    notes: Annotated[list[str], operator.add] = []                          # 已处理和结构化的笔记，可用于生成报告
    draft_report: str                                                       # 后端开发技术文档草稿
    final_report: str                                                       # 最终格式化的研究报告


# ===== STRUCTURED OUTPUT SCHEMAS =====

class ResearchQuestion(BaseModel):
    """用于生成结构化需求拆解简报的字段定义"""

    research_brief: str = Field(
        description=(
            "Requirement decomposition brief (not a backend dev doc): brief summary, "
            "confirmed/open requirements, atomic functional points F-001+ with scope, "
            "rules, dependencies, acceptance hints; point relationships. Same language as user."
        ),
    )

class DraftReport(BaseModel):
    """用于生成结构化后端开发技术文档草稿的字段定义"""

    draft_report: str = Field(
        description=(
            "Backend technical development document draft in Markdown: overview, "
            "architecture sketch, per functional point F-xxx sections (API, logic, data, "
            "tests, open items), implementation order, NFRs, risks. Same language as brief."
        ),
    )


class ClarificationItem(BaseModel):
    """单个澄清问题及其候选答案"""

    question: str = Field(description="The clarification question")
    options: list[str] = Field(description="3 suggested answers for the user to choose from")


class ClarificationQuestions(BaseModel):
    """LLM生成的澄清问题列表，每个问题附带3个候选答案"""

    items: list[ClarificationItem] = Field(
        description="2-5 clarification questions with suggested answers, ordered by importance"
    )
