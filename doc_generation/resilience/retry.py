#***********************************************
#      Filename: retry.py
#   Description: 指数退避重试（带 Full Jitter）
#***********************************************

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Callable, Coroutine, TypeVar

from doc_generation.resilience.errors import (
    LLMError,
    LLMFatalError,
    LLMRateLimitError,
    LLMRetryableError,
    classify_error,
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


def retry_sync(
    fn: Callable[..., T],
    args: tuple = (),
    kwargs: dict[str, Any] | None = None,
    *,
    config: RetryConfig,
    backend: str = "",
    role: str = "",
) -> T:
    """同步重试执行器。

    Args:
        fn: 要执行的函数
        args: 位置参数
        kwargs: 关键字参数
        config: 重试配置
        backend: 后端名称（用于错误分类）
        role: 角色名称（用于错误分类）

    Returns:
        函数执行结果

    Raises:
        LLMError: 重试耗尽后抛出最后一次的分类错误
    """
    if kwargs is None:
        kwargs = {}

    last_error: LLMError | None = None

    for attempt in range(config.max_attempts):
        try:
            result = fn(*args, **kwargs)
            return result
        except LLMError:
            raise
        except Exception as exc:
            classified = classify_error(exc, backend=backend, role=role)
            last_error = classified

            if isinstance(classified, LLMFatalError):
                logger.warning(
                    "[RETRY] Fatal error on attempt %d/%d for role='%s': %s",
                    attempt + 1, config.max_attempts, role, classified
                )
                raise classified from exc

            if attempt < config.max_attempts - 1:
                retry_after = getattr(classified, "retry_after", None)
                delay = _compute_delay(attempt, config, retry_after)
                logger.info(
                    "[RETRY] Retryable error on attempt %d/%d for role='%s', sleeping %.2fs: %s",
                    attempt + 1, config.max_attempts, role, delay, type(exc).__name__
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "[RETRY] Exhausted %d attempts for role='%s': %s",
                    config.max_attempts, role, classified
                )

    raise last_error  # type: ignore[misc]


async def retry_async(
    fn: Callable[..., Coroutine[Any, Any, T]],
    args: tuple = (),
    kwargs: dict[str, Any] | None = None,
    *,
    config: RetryConfig,
    backend: str = "",
    role: str = "",
) -> T:
    """异步重试执行器。

    Args:
        fn: 要执行的异步函数
        args: 位置参数
        kwargs: 关键字参数
        config: 重试配置
        backend: 后端名称
        role: 角色名称

    Returns:
        函数执行结果

    Raises:
        LLMError: 重试耗尽后抛出最后一次的分类错误
    """
    if kwargs is None:
        kwargs = {}

    last_error: LLMError | None = None

    for attempt in range(config.max_attempts):
        try:
            result = await fn(*args, **kwargs)
            return result
        except LLMError:
            raise
        except Exception as exc:
            classified = classify_error(exc, backend=backend, role=role)
            last_error = classified

            if isinstance(classified, LLMFatalError):
                logger.warning(
                    "[RETRY] Fatal error on attempt %d/%d for role='%s': %s",
                    attempt + 1, config.max_attempts, role, classified
                )
                raise classified from exc

            if attempt < config.max_attempts - 1:
                retry_after = getattr(classified, "retry_after", None)
                delay = _compute_delay(attempt, config, retry_after)
                logger.info(
                    "[RETRY] Retryable error on attempt %d/%d for role='%s', sleeping %.2fs: %s",
                    attempt + 1, config.max_attempts, role, delay, type(exc).__name__
                )
                await asyncio.sleep(delay)
            else:
                logger.warning(
                    "[RETRY] Exhausted %d attempts for role='%s': %s",
                    config.max_attempts, role, classified
                )

    raise last_error  # type: ignore[misc]
