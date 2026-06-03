#***********************************************
#      Filename: tool_fallback.py
#   Description: 工具备用链（按能力分组，主工具失败时切换）
#***********************************************

from __future__ import annotations

import logging
from typing import Any, Callable, List

from doc_generation.resilience.tool_errors import ToolError, ToolFatalError

logger = logging.getLogger(__name__)


class FallbackToolExhaustedError(ToolFatalError):
    """所有备用工具均已耗尽"""
    pass


class ToolFallbackChain:
    """工具备用链：按顺序尝试备用工具。

    备用流程：
    1. 主工具重试失败后进入备用链
    2. 按配置顺序尝试每个备用工具（单次调用，不重试）
    3. 如果所有备用工具都失败，抛出 FallbackToolExhaustedError
    """

    def __init__(self, tool_name: str, fallback_tools: List[Callable]):
        """初始化备用链。

        Args:
            tool_name: 主工具名称
            fallback_tools: 备用工具函数列表
        """
        self.tool_name = tool_name
        self.fallback_tools = fallback_tools

    def invoke_fallback(self, *args: Any, **kwargs: Any) -> Any:
        """同步执行备用链。

        Args:
            *args: 传递给工具的位置参数
            **kwargs: 传递给工具的关键字参数

        Returns:
            备用工具的响应

        Raises:
            FallbackToolExhaustedError: 所有备用工具均失败
        """
        for i, fallback_fn in enumerate(self.fallback_tools):
            try:
                fallback_name = getattr(fallback_fn, "__name__", f"fallback_{i}")
                logger.info(
                    "[TOOL_FALLBACK] tool='%s' trying fallback '%s' (position %d)",
                    self.tool_name, fallback_name, i
                )
                return fallback_fn(*args, **kwargs)
            except Exception as exc:
                fallback_name = getattr(fallback_fn, "__name__", f"fallback_{i}")
                logger.warning(
                    "[TOOL_FALLBACK] tool='%s' fallback '%s' failed: %s",
                    self.tool_name, fallback_name, exc
                )
                continue

        raise FallbackToolExhaustedError(
            f"All fallback tools exhausted for '{self.tool_name}'",
            tool_name=self.tool_name,
        )

    async def ainvoke_fallback(self, *args: Any, **kwargs: Any) -> Any:
        """异步执行备用链。

        Args:
            *args: 传递给工具的位置参数
            **kwargs: 传递给工具的关键字参数

        Returns:
            备用工具的响应

        Raises:
            FallbackToolExhaustedError: 所有备用工具均失败
        """
        for i, fallback_fn in enumerate(self.fallback_tools):
            try:
                fallback_name = getattr(fallback_fn, "__name__", f"fallback_{i}")
                logger.info(
                    "[TOOL_FALLBACK] tool='%s' trying fallback '%s' (position %d)",
                    self.tool_name, fallback_name, i
                )

                # 检查是否是异步函数
                import asyncio
                if asyncio.iscoroutinefunction(fallback_fn):
                    return await fallback_fn(*args, **kwargs)
                else:
                    return fallback_fn(*args, **kwargs)
            except Exception as exc:
                fallback_name = getattr(fallback_fn, "__name__", f"fallback_{i}")
                logger.warning(
                    "[TOOL_FALLBACK] tool='%s' fallback '%s' failed: %s",
                    self.tool_name, fallback_name, exc
                )
                continue

        raise FallbackToolExhaustedError(
            f"All fallback tools exhausted for '{self.tool_name}'",
            tool_name=self.tool_name,
        )


# --- 工具能力分组注册表 ---

_tool_capabilities: dict[str, List[str]] = {}


def register_tool_capability(capability: str, tool_name: str) -> None:
    """将工具注册到能力组。

    Args:
        capability: 能力名称（如 "web_search", "news_search"）
        tool_name: 工具名称
    """
    if capability not in _tool_capabilities:
        _tool_capabilities[capability] = []
    if tool_name not in _tool_capabilities[capability]:
        _tool_capabilities[capability].append(tool_name)
        logger.debug("[TOOL_CAPABILITY] Registered tool='%s' for capability='%s'", tool_name, capability)


def get_fallback_tools(capability: str, primary_tool: str) -> List[str]:
    """获取指定能力的备用工具列表（排除主工具）。

    Args:
        capability: 能力名称
        primary_tool: 主工具名称

    Returns:
        备用工具名称列表
    """
    all_tools = _tool_capabilities.get(capability, [])
    return [t for t in all_tools if t != primary_tool]
