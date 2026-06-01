#***********************************************
#      Filename: watchdog.py
#   Description: Windows 兼容的超时看门狗
#***********************************************

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable, Coroutine, TypeVar

from doc_generation.resilience.errors import LLMTimeoutError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class WatchdogTimeoutError(LLMTimeoutError):
    """Watchdog 超时触发的错误"""
    pass


def invoke_with_timeout(fn: Callable[..., T], args: tuple, kwargs: dict[str, Any], timeout_seconds: float) -> T:
    """同步调用的超时保护。

    使用 ThreadPoolExecutor 在独立线程中执行函数，通过 future.result(timeout) 实现超时控制。
    注意：超时后线程无法被强制终止，但异常会立即传播给调用方。

    Args:
        fn: 要执行的函数
        args: 位置参数
        kwargs: 关键字参数
        timeout_seconds: 超时秒数

    Returns:
        函数执行结果

    Raises:
        WatchdogTimeoutError: 超时
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError:
            raise WatchdogTimeoutError(
                f"LLM call exceeded watchdog timeout of {timeout_seconds}s"
            )


async def ainvoke_with_timeout(coro: Coroutine[Any, Any, T], timeout_seconds: float) -> T:
    """异步调用的超时保护。

    使用 asyncio.wait_for 实现超时控制，原生跨平台。

    Args:
        coro: 要执行的协程
        timeout_seconds: 超时秒数

    Returns:
        协程执行结果

    Raises:
        WatchdogTimeoutError: 超时
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise WatchdogTimeoutError(
            f"Async LLM call exceeded watchdog timeout of {timeout_seconds}s"
        )
