#***********************************************
#      Filename: tool_retry.py
#   Description: 工具调用重试策略（指数退避、固定延迟、立即修正）
#***********************************************

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Callable, Coroutine, TypeVar

from doc_generation.resilience.tool_errors import (
    ToolError,
    ToolFatalError,
    ToolRateLimitError,
    ToolRetryableError,
    ToolBadInputError,
    classify_tool_error,
)
from doc_generation.resilience.config import RetryConfig

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _compute_delay(attempt: int, config: RetryConfig, rate_limit_retry_after: float | None = None) -> float:
    """计算第 N 次重试的等待时间。

    Args:
        attempt: 当前重试次数（从 0 开始）
        config: 重试配置
        rate_limit_retry_after: 429 响应中的 Retry-After 值

    Returns:
        等待秒数
    """
    if rate_limit_retry_after is not None and rate_limit_retry_after > 0:
        return min(rate_limit_retry_after, config.max_delay)

    exponential = config.base_delay * (2 ** attempt)
    capped = min(exponential, config.max_delay)

    if config.jitter:
        return random.uniform(0, capped)
    return capped


def retry_tool_sync(
    fn: Callable[..., T],
    args: tuple = (),
    kwargs: dict[str, Any] | None = None,
    *,
    config: RetryConfig,
    tool_name: str = "",
) -> T:
    """同步工具调用重试执行器。

    Args:
        fn: 要执行的函数
        args: 位置参数
        kwargs: 关键字参数
        config: 重试配置
        tool_name: 工具名称（用于错误分类）

    Returns:
        函数执行结果

    Raises:
        ToolError: 重试耗尽后抛出最后一次的分类错误
    """
    if kwargs is None:
        kwargs = {}

    last_error: ToolError | None = None

    for attempt in range(config.max_attempts):
        try:
            result = fn(*args, **kwargs)
            return result
        except ToolError:
            raise
        except Exception as exc:
            classified = classify_tool_error(exc, tool_name=tool_name)
            last_error = classified

            # 认证错误和配置错误：不重试
            if isinstance(classified, ToolFatalError) and not isinstance(classified, ToolBadInputError):
                logger.warning(
                    "[TOOL_RETRY] Fatal error on attempt %d/%d for tool='%s': %s",
                    attempt + 1, config.max_attempts, tool_name, classified
                )
                raise classified from exc

            # 400 错误输入：记录错误详情，但不在这里自动修正（由上层 LLM 处理）
            if isinstance(classified, ToolBadInputError):
                logger.warning(
                    "[TOOL_RETRY] Bad input error on attempt %d/%d for tool='%s': %s",
                    attempt + 1, config.max_attempts, tool_name, classified
                )
                raise classified from exc

            if attempt < config.max_attempts - 1:
                retry_after = getattr(classified, "retry_after", None)
                delay = _compute_delay(attempt, config, retry_after)
                logger.info(
                    "[TOOL_RETRY] Retryable error on attempt %d/%d for tool='%s', sleeping %.2fs: %s",
                    attempt + 1, config.max_attempts, tool_name, delay, type(exc).__name__
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "[TOOL_RETRY] Exhausted %d attempts for tool='%s': %s",
                    config.max_attempts, tool_name, classified
                )

    raise last_error  # type: ignore[misc]


async def retry_tool_async(
    fn: Callable[..., Coroutine[Any, Any, T]],
    args: tuple = (),
    kwargs: dict[str, Any] | None = None,
    *,
    config: RetryConfig,
    tool_name: str = "",
) -> T:
    """异步工具调用重试执行器。

    Args:
        fn: 要执行的异步函数
        args: 位置参数
        kwargs: 关键字参数
        config: 重试配置
        tool_name: 工具名称

    Returns:
        函数执行结果

    Raises:
        ToolError: 重试耗尽后抛出最后一次的分类错误
    """
    if kwargs is None:
        kwargs = {}

    last_error: ToolError | None = None

    for attempt in range(config.max_attempts):
        try:
            result = await fn(*args, **kwargs)
            return result
        except ToolError:
            raise
        except Exception as exc:
            classified = classify_tool_error(exc, tool_name=tool_name)
            last_error = classified

            # 认证错误和配置错误：不重试
            if isinstance(classified, ToolFatalError) and not isinstance(classified, ToolBadInputError):
                logger.warning(
                    "[TOOL_RETRY] Fatal error on attempt %d/%d for tool='%s': %s",
                    attempt + 1, config.max_attempts, tool_name, classified
                )
                raise classified from exc

            # 400 错误输入：记录错误详情
            if isinstance(classified, ToolBadInputError):
                logger.warning(
                    "[TOOL_RETRY] Bad input error on attempt %d/%d for tool='%s': %s",
                    attempt + 1, config.max_attempts, tool_name, classified
                )
                raise classified from exc

            if attempt < config.max_attempts - 1:
                retry_after = getattr(classified, "retry_after", None)
                delay = _compute_delay(attempt, config, retry_after)
                logger.info(
                    "[TOOL_RETRY] Retryable error on attempt %d/%d for tool='%s', sleeping %.2fs: %s",
                    attempt + 1, config.max_attempts, tool_name, delay, type(exc).__name__
                )
                await asyncio.sleep(delay)
            else:
                logger.warning(
                    "[TOOL_RETRY] Exhausted %d attempts for tool='%s': %s",
                    config.max_attempts, tool_name, classified
                )

    raise last_error  # type: ignore[misc]
