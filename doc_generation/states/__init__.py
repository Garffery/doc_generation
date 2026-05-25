#***********************************************
#      Filename: __init__.py
#   Description: 大模型格式化字段定义
#***********************************************

from doc_generation.states.critique import Critique
from doc_generation.states.quality import QualityMetric
from doc_generation.states.eval_result import EvaluationResult
from doc_generation.states.draft import AgentInputState, AgentState, ResearchQuestion, DraftReport
from doc_generation.states.research import ResearcherState, ResearcherOutputState, Summary
from doc_generation.states.supervisor import SupervisorState, ConductResearch, ResearchComplete
