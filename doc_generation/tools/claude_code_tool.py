#***********************************************
#      Filename: claude_code_tool.py
#   Description: Claude Code CLI 工具（基于 claude-code-sdk）
#***********************************************

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional, Type

from pydantic import BaseModel, Field
from typing_extensions import Annotated
from langchain_core.tools import InjectedToolArg

from claude_code_sdk import (
    ClaudeCodeOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    query,
)

from doc_generation.utils import load_config
from doc_generation.tools.base import ResilientBaseTool

logger = logging.getLogger(__name__)


def _get_claude_code_cwd() -> str | None:
    try:
        stage = os.environ.get("STAGE") or "prod"
        cfg = load_config(stage_name=stage, config_path=os.environ.get("CONFIG_PATH", "config.yml"))
        return cfg.get("claude_code", {}).get("cwd")
    except Exception:
        return None


async def _run_claude_code(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    cwd: str | None = None,
    max_turns: int | None = None,
    allowed_tools: list[str] | None = None,
) -> str:
    options = ClaudeCodeOptions(
        system_prompt=system_prompt,
        model=model,
        cwd=cwd,
        max_turns=max_turns,
        allowed_tools=allowed_tools or ["Read", "Glob", "Grep"],
    )

    text_parts: list[str] = []

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                elif isinstance(block, ToolResultBlock):
                    if block.content and isinstance(block.content, str):
                        text_parts.append(block.content)
        elif isinstance(message, ResultMessage):
            if message.result:
                text_parts.append(message.result)

    return "\n".join(text_parts)


class ClaudeCodeInput(BaseModel):
    prompt: str = Field(description="发送给 Claude Code 的提示词/任务描述。")
    system_prompt: Annotated[Optional[str], InjectedToolArg] = Field(default=None, description="自定义系统提示词（可选）。")
    model: Annotated[Optional[str], InjectedToolArg] = Field(default=None, description="指定使用的模型（可选）。")
    max_turns: Annotated[Optional[int], InjectedToolArg] = Field(default=None, description="最大对话轮次（可选）。")
    allowed_tools: Annotated[Optional[list[str]], InjectedToolArg] = Field(default=None, description="允许使用的工具列表（可选）。")


class ClaudeCodeTool(ResilientBaseTool):
    name: str = "claude_code"
    description: str = (
        "调用 Claude Code CLI 执行编程相关任务，如代码生成、代码分析、文件操作等。"
        "Claude Code 是一个强大的 AI 编程助手，可以理解代码库上下文并执行复杂的编程任务。"
        "适用于需要深度代码理解、跨文件分析、代码重构等场景。"
    )
    args_schema: Type[BaseModel] = ClaudeCodeInput

    def _execute(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_turns: Optional[int] = None,
        allowed_tools: Optional[list[str]] = None,
        cwd: Optional[str] = None,
    ) -> str:
        cwd = cwd or _get_claude_code_cwd()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(
                    asyncio.run,
                    _run_claude_code(
                        prompt, system_prompt=system_prompt, model=model,
                        cwd=cwd, max_turns=max_turns, allowed_tools=allowed_tools,
                    ),
                ).result()
        else:
            result = asyncio.run(
                _run_claude_code(
                    prompt, system_prompt=system_prompt, model=model,
                    cwd=cwd, max_turns=max_turns, allowed_tools=allowed_tools,
                )
            )

        logger.info("claude_code completed, response length=%d", len(result))
        return result


_claude_code_tool = ClaudeCodeTool()


def claude_code(
    prompt: str,
    system_prompt: Annotated[Optional[str], InjectedToolArg] = None,
    model: Annotated[Optional[str], InjectedToolArg] = None,
    max_turns: Annotated[Optional[int], InjectedToolArg] = None,
    allowed_tools: Annotated[Optional[list[str]], InjectedToolArg] = None,
    cwd: Optional[str] = None,
) -> str:
    return _claude_code_tool._execute(
        prompt, system_prompt=system_prompt, model=model,
        max_turns=max_turns, allowed_tools=allowed_tools, cwd=cwd,
    )
