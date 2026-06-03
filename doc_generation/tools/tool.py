#***********************************************
#      Filename: tool.py
#   Description: 可调用工具列表
#***********************************************

import os
from typing import Optional, Type
from typing_extensions import Annotated, List, Literal
from langchain_core.messages import HumanMessage
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel, Field
import logging
from doc_generation.utils import get_today_str
from doc_generation.llm import get_chat_model
from doc_generation.states import Summary
from doc_generation.prompts import SUMMARIZE_PROMPT, REFINE_DRAFT_REPORT_PROMPT
from doc_generation.tools.search_factory import (
    SearchConfigError,
    get_search_client,
    get_search_defaults,
    get_search_provider,
)
from doc_generation.tools.base import ResilientBaseTool

logger = logging.getLogger(__name__)

summarization_model = get_chat_model("researcher_summarizer")
writer_model = get_chat_model("writer")
MAX_CONTEXT_LENGTH = 250000
DEFAULT_MAX_CONTEXT = 1000
search_provider = None
search_client = None
search_defaults = None


def _ensure_search_runtime(raise_on_error: bool = True):
    global search_provider, search_client, search_defaults
    try:
        if search_provider is None:
            search_provider = get_search_provider()
        if search_client is None:
            search_client = get_search_client()
        if search_defaults is None:
            search_defaults = get_search_defaults()
    except SearchConfigError as exc:
        logger.error("Search runtime initialization failed: %s", exc)
        if raise_on_error:
            raise
    except Exception as exc:
        logger.error("Unexpected error during search runtime init: %s", exc)
        if raise_on_error:
            raise
    return search_provider, search_client, search_defaults


try:
    import requests
    _REQUESTS_TIMEOUT_EXC = (requests.exceptions.Timeout,)
except Exception:
    _REQUESTS_TIMEOUT_EXC = tuple()

try:
    import httpx
    _HTTPX_TIMEOUT_EXC = (httpx.TimeoutException,)
except Exception:
    _HTTPX_TIMEOUT_EXC = tuple()

_TIMEOUT_EXCEPTIONS = (TimeoutError,) + _REQUESTS_TIMEOUT_EXC + _HTTPX_TIMEOUT_EXC


def tavily_search_multiple(
    search_queries: List[str],
    max_results: Optional[int] = 3,
    topic: Optional[Literal["general", "news", "finance"]] = "general",
    include_raw_content: Optional[bool] = True,
    timeout_seconds: Optional[int] = None,
) -> List[dict]:
    _, _, defaults_obj = _ensure_search_runtime()
    if defaults_obj is None:
        raise SearchConfigError("Search runtime unavailable")

    effective_max_results = max_results if max_results is not None else defaults_obj.get("max_results", 3)
    effective_topic = topic if topic is not None else defaults_obj.get("topic", "general")
    effective_include_raw = include_raw_content if include_raw_content is not None else True
    effective_timeout = timeout_seconds if timeout_seconds is not None else defaults_obj.get("timeout_seconds")

    search_docs = []
    for query in search_queries:
        result = search_provider.search(
            search_client, query,
            max_results=effective_max_results,
            include_raw_content=effective_include_raw,
            topic=effective_topic,
            timeout_seconds=effective_timeout,
        )
        search_docs.append(result)
    return search_docs


def summarize_webpage_content(webpage_content: str) -> str:
    try:
        structured_model = summarization_model.with_structured_output(Summary)
        summary = structured_model.invoke([
            HumanMessage(content=SUMMARIZE_PROMPT.format(
                webpage_content=webpage_content,
                date=get_today_str()
            ))
        ])
        return (
            f"<summary>\n{summary.summary}\n</summary>\n\n"
            f"<key_excerpts>\n{summary.key_excerpts}\n</key_excerpts>"
        )
    except Exception as e:
        logger.error(f"Failed to summarize webpage: {str(e)}")
        return webpage_content[:DEFAULT_MAX_CONTEXT] + "..."


def deduplicate_search_results(search_results: List[dict]) -> dict:
    unique_results = {}
    for response in search_results:
        for result in response['results']:
            url = result['url']
            if url not in unique_results:
                unique_results[url] = result
    return unique_results


def process_search_results(unique_results: dict) -> dict:
    summarized_results = {}
    for url, result in unique_results.items():
        if not result.get("raw_content"):
            content = result['content']
        else:
            content = summarize_webpage_content(result['raw_content'][:MAX_CONTEXT_LENGTH])
        summarized_results[url] = {'title': result['title'], 'content': content}
    return summarized_results


def format_search_output(summarized_results: dict) -> str:
    if not summarized_results:
        return "No valid search results found. Please try different search queries or use a different search API."
    formatted_output = "Search results: \n\n"
    for i, (url, result) in enumerate(summarized_results.items(), 1):
        formatted_output += f"\n\n--- SOURCE {i}: {result['title']} ---\n"
        formatted_output += f"URL: {url}\n\n"
        formatted_output += f"SUMMARY:\n{result['content']}\n\n"
        formatted_output += "-" * 80 + "\n"
    return formatted_output


# ===== BaseTool 实现 =====

class TavilySearchInput(BaseModel):
    query: str = Field(description="搜索关键词(query).")
    max_results: Annotated[Optional[int], InjectedToolArg] = Field(default=None, description="返回的最大结果数量(可选参数)，默认是3")
    topic: Annotated[Optional[Literal["general", "news", "finance"]], InjectedToolArg] = Field(default=None, description="搜索主题，参数可以为：general, news, finance，默认是\"general\"")


class TavilySearchTool(ResilientBaseTool):
    name: str = "tavily_search"
    description: str = "根据配置好的tavily API去web上搜索结果，并返回做完网页内容摘要后的结果"
    args_schema: Type[BaseModel] = TavilySearchInput
    fallback_message: str = "抱歉，搜索服务暂时不可用"

    def _execute(self, query: str, max_results: Optional[int] = None,
                 topic: Optional[Literal["general", "news", "finance"]] = None) -> str:
        _, _, defaults = _ensure_search_runtime()
        if defaults is None:
            raise SearchConfigError("Search defaults unavailable; search runtime not initialized")

        resolved_max_results = max_results if max_results is not None else defaults.get("max_results", 3)
        resolved_topic = topic if topic is not None else defaults.get("topic", "general")
        include_raw_content = defaults.get("include_raw_content") or True

        search_results = tavily_search_multiple(
            [query],
            max_results=resolved_max_results,
            topic=resolved_topic,
            include_raw_content=include_raw_content,
        )
        unique_results = deduplicate_search_results(search_results)
        summarized_results = process_search_results(unique_results)
        return format_search_output(summarized_results)


class ThinkToolInput(BaseModel):
    reflection: str = Field(description="您对研究进展、发现、存在的差距以及下一步行动的详细反思。")


class ThinkTool(ResilientBaseTool):
    name: str = "think_tool"
    description: str = (
        "用于对研究进展和决策进行策略反思的工具。"
        "每次搜索后，使用此工具分析结果并系统地规划下一步行动。"
    )
    args_schema: Type[BaseModel] = ThinkToolInput

    def _execute(self, reflection: str) -> str:
        return f"Reflection recorded: {reflection}"


class RefineDraftReportInput(BaseModel):
    research_brief: Annotated[str, InjectedToolArg] = Field(description="研究简报")
    findings: Annotated[str, InjectedToolArg] = Field(description="研究发现")
    draft_report: Annotated[str, InjectedToolArg] = Field(description="当前报告草稿")


class RefineDraftReportTool(ResilientBaseTool):
    name: str = "refine_draft_report"
    description: str = "根据最新研究发现自动完善当前报告草稿，无需手动传入参数。"
    args_schema: Type[BaseModel] = RefineDraftReportInput

    def _execute(self, research_brief: str, findings: str, draft_report: str) -> str:
        draft_report_prompt = REFINE_DRAFT_REPORT_PROMPT.format(
            research_brief=research_brief,
            findings=findings,
            draft_report=draft_report,
            date=get_today_str()
        )
        draft_report_obj = writer_model.invoke([HumanMessage(content=draft_report_prompt)])
        return getattr(draft_report_obj, "content", draft_report_obj)


_tavily_search_tool = TavilySearchTool()
_think_tool = ThinkTool()
_refine_draft_report_tool = RefineDraftReportTool()
