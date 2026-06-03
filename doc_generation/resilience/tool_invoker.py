#***********************************************
#      Filename: tool_invoker.py
#   Description: ResilientTool 核心编排器（工具调用弹性包装器）
#***********************************************

from __future__ import annotations

import logging
from typing import Any, Callable, List

from doc_generation.resilience.circuit_breaker import CircuitBreaker, get_breaker
from doc_generation.resilience.config import ResilienceConfig
from doc_generation.resilience.tool_errors import (
    ToolCircuitOpenError,
    ToolError,
    ToolFatalError,
    ToolRetryableError,
    ToolBadInputError,
)
from doc_generation.resilience.tool_fallback import ToolFallbackChain
from doc_generation.resilience.tool_retry import retry_tool_sync, retry_tool_async
from doc_generation.resilience.tool_cost import get_cost_tracker
from doc_generation.resilience.watchdog import invoke_with_timeout, ainvoke_with_timeout

logger = logging.getLogger(__name__)


class ResilientTool:
    """工具调用的弹性包装器。

    执行完整的错误处理流程：
    熔断器检查 → Watchdog 超时保护 → 指数退避重试 → 备用工具降级 → 成本记录

    Example:
        ```python
        # 包装现有工具函数
        resilient_search = ResilientTool(
            tool_fn=tavily_search,
            tool_name="tavily_search",
            config=resilience_config,
            fallback_tools=[bing_search, duckduckgo_search]
        )

        # 调用工具
        result = resilient_search.invoke(query="AI agents", max_results=5)
        ```
    """

    def __init__(
        self,
        tool_fn: Callable,
        tool_name: str,
        config: ResilienceConfig,
        fallback_tools: List[Callable] | None = None,
        timeout: float | None = None,
    ):
        """初始化弹性工具包装器。

        Args:
            tool_fn: 原始工具函数
            tool_name: 工具名称（用于日志、熔断器、成本追踪）
            config: 弹性配置
            fallback_tools: 备用工具函数列表（可选）
            timeout: 超时时间（秒），如果为 None 则使用配置中的默认值
        """
        self._tool_fn = tool_fn
        self._tool_name = tool_name
        self._config = config
        self._breaker = get_breaker(tool_name, config.circuit_breaker)
        self._fallback_chain = ToolFallbackChain(tool_name, fallback_tools or []) if fallback_tools else None
        self._timeout = timeout or config.watchdog.default_timeout
        self._cost_tracker = get_cost_tracker()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """使工具可以像普通函数一样调用。"""
        return self.invoke(*args, **kwargs)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """同步调用，带完整弹性保护。"""
        return self._execute_sync(*args, **kwargs)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        """异步调用，带完整弹性保护。"""
        return await self._execute_async(*args, **kwargs)

    def _execute_sync(self, *args: Any, **kwargs: Any) -> Any:
        """同步执行编排：熔断 → 超时 → 重试 → 降级 → 成本记录。"""

        # 1. 熔断器检查
        if not self._breaker.allow_request():
            logger.warning("[RESILIENT_TOOL] Circuit OPEN for tool='%s', skipping to fallback", self._tool_name)
            self._cost_tracker.record_call(self._tool_name, success=False, error_type="circuit_open")
            if self._fallback_chain:
                return self._fallback_chain.invoke_fallback(*args, **kwargs)
            raise ToolCircuitOpenError(
                f"Circuit breaker is OPEN for tool '{self._tool_name}'",
                tool_name=self._tool_name,
            )

        # 2. 带超时和重试的主工具调用
        def _guarded_invoke(*a: Any, **kw: Any) -> Any:
            return invoke_with_timeout(
                self._tool_fn, args, kwargs, self._timeout
            )

        try:
            result = retry_tool_sync(
                _guarded_invoke,
                config=self._config.retry,
                tool_name=self._tool_name,
            )
            self._breaker.record_success()
            self._cost_tracker.record_call(self._tool_name, success=True)
            return result
        except ToolBadInputError as e:
            # 400 错误：记录后直接抛出，由上层 LLM 修正参数
            self._breaker.record_failure()
            refund = self._cost_tracker.record_call(self._tool_name, success=False, error_type="4xx")
            logger.warning(
                "[RESILIENT_TOOL] Bad input error for tool='%s' (refund=%.2f): %s",
                self._tool_name, refund, e
            )
            raise
        except ToolFatalError as e:
            # 认证错误等致命错误：记录后直接抛出
            self._breaker.record_failure()
            error_type = "auth" if "auth" in type(e).__name__.lower() else "fatal"
            refund = self._cost_tracker.record_call(self._tool_name, success=False, error_type=error_type)
            logger.warning(
                "[RESILIENT_TOOL] Fatal error for tool='%s' (refund=%.2f): %s",
                self._tool_name, refund, e
            )
            raise
        except ToolRetryableError as e:
            # 瞬态错误重试耗尽：进入降级链
            self._breaker.record_failure()
            error_type = self._classify_error_type(e)
            refund = self._cost_tracker.record_call(self._tool_name, success=False, error_type=error_type)
            logger.warning(
                "[RESILIENT_TOOL] Retries exhausted for tool='%s' (refund=%.2f), entering fallback: %s",
                self._tool_name, refund, e
            )
            if self._fallback_chain:
                return self._fallback_chain.invoke_fallback(*args, **kwargs)
            raise
        except ToolError as e:
            self._breaker.record_failure()
            refund = self._cost_tracker.record_call(self._tool_name, success=False, error_type="unknown")
            logger.warning(
                "[RESILIENT_TOOL] Tool error for tool='%s' (refund=%.2f): %s",
                self._tool_name, refund, e
            )
            raise

    async def _execute_async(self, *args: Any, **kwargs: Any) -> Any:
        """异步执行编排：熔断 → 超时 → 重试 → 降级 → 成本记录。"""

        # 1. 熔断器检查
        if not self._breaker.allow_request():
            logger.warning("[RESILIENT_TOOL] Circuit OPEN for tool='%s', skipping to fallback", self._tool_name)
            self._cost_tracker.record_call(self._tool_name, success=False, error_type="circuit_open")
            if self._fallback_chain:
                return await self._fallback_chain.ainvoke_fallback(*args, **kwargs)
            raise ToolCircuitOpenError(
                f"Circuit breaker is OPEN for tool '{self._tool_name}'",
                tool_name=self._tool_name,
            )

        # 2. 带超时和重试的主工具调用
        async def _guarded_ainvoke(*a: Any, **kw: Any) -> Any:
            return await ainvoke_with_timeout(
                self._tool_fn(*args, **kwargs), self._timeout
            )

        try:
            result = await retry_tool_async(
                _guarded_ainvoke,
                config=self._config.retry,
                tool_name=self._tool_name,
            )
            self._breaker.record_success()
            self._cost_tracker.record_call(self._tool_name, success=True)
            return result
        except ToolBadInputError as e:
            self._breaker.record_failure()
            refund = self._cost_tracker.record_call(self._tool_name, success=False, error_type="4xx")
            logger.warning(
                "[RESILIENT_TOOL] Bad input error for tool='%s' (refund=%.2f): %s",
                self._tool_name, refund, e
            )
            raise
        except ToolFatalError as e:
            self._breaker.record_failure()
            error_type = "auth" if "auth" in type(e).__name__.lower() else "fatal"
            refund = self._cost_tracker.record_call(self._tool_name, success=False, error_type=error_type)
            logger.warning(
                "[RESILIENT_TOOL] Fatal error for tool='%s' (refund=%.2f): %s",
                self._tool_name, refund, e
            )
            raise
        except ToolRetryableError as e:
            self._breaker.record_failure()
            error_type = self._classify_error_type(e)
            refund = self._cost_tracker.record_call(self._tool_name, success=False, error_type=error_type)
            logger.warning(
                "[RESILIENT_TOOL] Retries exhausted for tool='%s' (refund=%.2f), entering fallback: %s",
                self._tool_name, refund, e
            )
            if self._fallback_chain:
                return await self._fallback_chain.ainvoke_fallback(*args, **kwargs)
            raise
        except ToolError as e:
            self._breaker.record_failure()
            refund = self._cost_tracker.record_call(self._tool_name, success=False, error_type="unknown")
            logger.warning(
                "[RESILIENT_TOOL] Tool error for tool='%s' (refund=%.2f): %s",
                self._tool_name, refund, e
            )
            raise

    def _classify_error_type(self, error: ToolError) -> str:
        """将错误分类为成本追踪类型。"""
        error_class_name = type(error).__name__.lower()
        if "timeout" in error_class_name:
            return "timeout"
        if "ratelimit" in error_class_name:
            return "429"
        if "server" in error_class_name or "5xx" in error_class_name:
            return "5xx"
        if "connection" in error_class_name:
            return "connection"
        return "retryable"
