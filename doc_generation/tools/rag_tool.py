#***********************************************
#      Filename: rag_tool.py
#   Description: RAG 检索 LangChain / LangGraph 工具
#***********************************************

from __future__ import annotations

from typing import Optional

import logging
from typing_extensions import Annotated

from langchain_core.tools import InjectedToolArg, tool

from doc_generation.rag import get_rag_defaults, get_rag_store, is_rag_enabled
from doc_generation.rag.errors import RagConfigError
from doc_generation.rag.format import format_rag_output

logger = logging.getLogger(__name__)


def rag_search(
    query: str,
    top_k: Annotated[Optional[int], InjectedToolArg] = None,
) -> str:
    """在本地 Chroma 知识库中做语义检索，返回与 query 最相关的文档片段。

    适用于项目内已入库的协议说明、设计文档、历史报告等静态资料；
    需要实时网络信息时请使用 tavily_search。

    Args:
        query: 检索问题或关键词。
        top_k: 返回的最大片段数（可选，默认来自 config.yml）。

    Returns:
        格式化后的知识库检索结果。
    """
    if not is_rag_enabled():
        raise RagConfigError("RAG is not enabled; add a 'rag' block to config.yml")

    defaults = get_rag_defaults()
    resolved_top_k = top_k if top_k is not None else defaults.get("top_k", 5)

    logger.info("rag_search query=%r top_k=%s", query, resolved_top_k)
    store = get_rag_store()
    results = store.search(query, top_k=resolved_top_k)
    return format_rag_output(results)


_rag_search_tool = tool(parse_docstring=True)(rag_search)
