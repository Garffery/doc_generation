#***********************************************
#      Filename: invoker.py
#   Description: ResilientModel 核心编排器
#***********************************************

from __future__ import annotations

import logging
from typing import Any

from doc_generation.resilience.circuit_breaker import CircuitBreaker, get_breaker
from doc_generation.resilience.config import ResilienceConfig
from doc_generation.resilience.errors import (
    CircuitOpenError,
    LLMError,
    LLMFatalError,
    LLMRetryableError,
    classify_error,
)
from doc_generation.resilience.fallback import FallbackChain
from doc_generation.resilience.retry import retry_async, retry_sync
from doc_generation.resilience.watchdog import ainvoke_with_timeout, invoke_with_timeout

logger = logging.getLogger(__name__)


class ResilientModel:
    """LangChain 模型的弹性代理包装器。

    拦截 invoke/ainvoke 调用，自动执行完整的错误处理流程：
    熔断器检查 → Watchdog 超时保护 → 指数退避重试 → 备用模型降级 → 静态兜底

    同时正确代理 bind_tools() 和 with_structured_output()，使链式调用保持弹性。
    """

    def __init__(self, model: Any, role: str, config: ResilienceConfig):
        self._model = model
        self._role = role
        self._config = config
        self._backend = config.get_backend(role)
        self._breaker = get_breaker(self._backend, config.circuit_breaker)
        self._fallback_chain = FallbackChain.from_config(role, config)
        self._timeout = config.watchdog.default_timeout

    def __getattr__(self, name: str) -> Any:
        """代理所有未显式定义的属性到底层模型。"""
        return getattr(self._model, name)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ResilientModel":
        """返回新的 ResilientModel，包装 tool-bound 模型。"""
        bound = self._model.bind_tools(tools, **kwargs)
        return ResilientModel(bound, self._role, self._config)

    def with_structured_output(self, schema: Any, **kwargs: Any) -> "ResilientModel":
        """返回新的 ResilientModel，包装 structured-output 模型。"""
        structured = self._model.with_structured_output(schema, **kwargs)
        return ResilientModel(structured, self._role, self._config)

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        """同步调用，带完整弹性保护。"""
        return self._execute_sync(messages, **kwargs)

    async def ainvoke(self, messages: Any, **kwargs: Any) -> Any:
        """异步调用，带完整弹性保护。"""
        return await self._execute_async(messages, **kwargs)

    def _execute_sync(self, messages: Any, **kwargs: Any) -> Any:
        """同步执行编排：熔断 → 超时 → 重试 → 降级。"""

        # 1. 熔断器检查
        if not self._breaker.allow_request():
            logger.warning("[RESILIENT] Circuit OPEN for backend='%s', skipping to fallback", self._backend)
            return self._fallback_sync(messages, **kwargs)

        # 2. 带超时和重试的主模型调用
        def _guarded_invoke(*args: Any, **kw: Any) -> Any:
            return invoke_with_timeout(
                self._model.invoke, (messages,), kwargs, self._timeout
            )

        try:
            result = retry_sync(
                _guarded_invoke,
                config=self._config.retry,
                backend=self._backend,
                role=self._role,
            )
            self._breaker.record_success()
            return result
        except LLMFatalError as e:
            self._breaker.record_failure()
            logger.warning("[RESILIENT] Fatal error for role='%s', entering fallback: %s", self._role, e)
            return self._fallback_sync(messages, **kwargs)
        except LLMRetryableError as e:
            self._breaker.record_failure()
            logger.warning("[RESILIENT] Retries exhausted for role='%s', entering fallback: %s", self._role, e)
            return self._fallback_sync(messages, **kwargs)
        except LLMError as e:
            self._breaker.record_failure()
            logger.warning("[RESILIENT] LLM error for role='%s', entering fallback: %s", self._role, e)
            return self._fallback_sync(messages, **kwargs)

    async def _execute_async(self, messages: Any, **kwargs: Any) -> Any:
        """异步执行编排：熔断 → 超时 → 重试 → 降级。"""

        # 1. 熔断器检查
        if not self._breaker.allow_request():
            logger.warning("[RESILIENT] Circuit OPEN for backend='%s', skipping to fallback", self._backend)
            return await self._fallback_async(messages, **kwargs)

        # 2. 带超时和重试的主模型调用
        async def _guarded_ainvoke(*args: Any, **kw: Any) -> Any:
            return await ainvoke_with_timeout(
                self._model.ainvoke(messages, **kwargs), self._timeout
            )

        try:
            result = await retry_async(
                _guarded_ainvoke,
                config=self._config.retry,
                backend=self._backend,
                role=self._role,
            )
            self._breaker.record_success()
            return result
        except LLMFatalError as e:
            self._breaker.record_failure()
            logger.warning("[RESILIENT] Fatal error for role='%s', entering fallback: %s", self._role, e)
            return await self._fallback_async(messages, **kwargs)
        except LLMRetryableError as e:
            self._breaker.record_failure()
            logger.warning("[RESILIENT] Retries exhausted for role='%s', entering fallback: %s", self._role, e)
            return await self._fallback_async(messages, **kwargs)
        except LLMError as e:
            self._breaker.record_failure()
            logger.warning("[RESILIENT] LLM error for role='%s', entering fallback: %s", self._role, e)
            return await self._fallback_async(messages, **kwargs)

    def _fallback_sync(self, messages: Any, **kwargs: Any) -> Any:
        """同步降级链执行。"""
        from doc_generation.resilience.fallback import FallbackExhaustedError

        try:
            return self._fallback_chain.invoke_fallback(messages, **kwargs)
        except FallbackExhaustedError:
            raise
        except Exception as exc:
            raise LLMFatalError(
                f"Fallback chain failed for role '{self._role}': {exc}",
                original=exc,
                backend=self._backend,
                role=self._role,
            ) from exc

    async def _fallback_async(self, messages: Any, **kwargs: Any) -> Any:
        """异步降级链执行。"""
        from doc_generation.resilience.fallback import FallbackExhaustedError

        try:
            return await self._fallback_chain.ainvoke_fallback(messages, **kwargs)
        except FallbackExhaustedError:
            raise
        except Exception as exc:
            raise LLMFatalError(
                f"Fallback chain failed for role '{self._role}': {exc}",
                original=exc,
                backend=self._backend,
                role=self._role,
            ) from exc
