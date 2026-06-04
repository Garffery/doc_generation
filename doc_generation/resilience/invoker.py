#***********************************************
#      Filename: invoker.py
#   Description: ResilientModel 核心编排器
#***********************************************

from __future__ import annotations

import logging
from typing import Any, Optional, Type

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

    def __init__(
        self,
        model: Any,
        role: str,
        config: ResilienceConfig,
        expected_schema: Optional[Type] = None,
    ):
        self._model = model
        self._role = role
        self._config = config
        self._backend = config.get_backend(role)
        self._breaker = get_breaker(self._backend, config.circuit_breaker)
        self._fallback_chain = FallbackChain.from_config(role, config)
        self._timeout = config.watchdog.default_timeout
        self._expected_schema = expected_schema  # 用于验证结构化输出

    def __getattr__(self, name: str) -> Any:
        """代理所有未显式定义的属性到底层模型。"""
        return getattr(self._model, name)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ResilientModel":
        """返回新的 ResilientModel，包装 tool-bound 模型。"""
        bound = self._model.bind_tools(tools, **kwargs)
        return ResilientModel(bound, self._role, self._config, self._expected_schema)

    def with_structured_output(self, schema: Any, **kwargs: Any) -> "ResilientModel":
        """返回新的 ResilientModel，包装 structured-output 模型。"""
        structured = self._model.with_structured_output(schema, **kwargs)
        return ResilientModel(structured, self._role, self._config, expected_schema=schema)

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        """同步调用，带完整弹性保护。"""
        return self._execute_sync(messages, **kwargs)

    async def ainvoke(self, messages: Any, **kwargs: Any) -> Any:
        """异步调用，带完整弹性保护。"""
        return await self._execute_async(messages, **kwargs)

    def _validate_structured_output(self, result: Any) -> bool:
        """验证结果是否符合预期的结构化输出格式。

        如果设置了 expected_schema，检查结果是否是该类型的实例。
        如果结果是 AIMessage，说明结构化输出失败。
        """
        if self._expected_schema is None:
            return True  # 没有设置 schema，不做验证

        # 检查是否返回了 AIMessage（表示结构化输出失败）
        try:
            from langchain_core.messages import AIMessage
            if isinstance(result, AIMessage):
                logger.warning(
                    "[RESILIENT] Structured output failed for role='%s', got AIMessage instead of %s",
                    self._role,
                    self._expected_schema.__name__ if hasattr(self._expected_schema, '__name__') else str(self._expected_schema)
                )
                return False
        except ImportError:
            pass  # 如果没有安装 langchain_core，跳过检查

        # 检查结果类型是否匹配预期的 schema
        try:
            if not isinstance(result, self._expected_schema):
                logger.warning(
                    "[RESILIENT] Result type mismatch for role='%s': expected %s, got %s",
                    self._role,
                    self._expected_schema.__name__ if hasattr(self._expected_schema, '__name__') else str(self._expected_schema),
                    type(result).__name__
                )
                return False
        except TypeError:
            # 对于某些类型（如 TypedDict），isinstance 检查可能失败
            pass

        return True

    def _add_structure_prompt(self, messages: Any) -> Any:
        """在消息末尾添加提示，强调必须返回结构化输出。"""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            structure_reminder = (
                "IMPORTANT: You MUST respond with the exact structured format requested. "
                "Do not return a plain text message. Follow the schema strictly."
            )

            # 如果 messages 是列表，添加一条系统消息
            if isinstance(messages, list):
                return messages + [SystemMessage(content=structure_reminder)]
            else:
                # 如果是单个消息，转换为列表
                return [messages, SystemMessage(content=structure_reminder)]
        except ImportError:
            # 如果无法导入 langchain_core，返回原消息
            return messages

    def _execute_sync(self, messages: Any, **kwargs: Any) -> Any:
        """同步执行编排：熔断 → 超时 → 重试 → 降级。"""

        # 1. 熔断器检查(短路了去尝试一下,如果有fall-back)
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

            # 3. 验证结构化输出
            if self._expected_schema and not self._validate_structured_output(result):
                logger.info(
                    "[RESILIENT] Retrying with structure reminder for role='%s'",
                    self._role
                )
                # 添加提示后重试一次
                enhanced_messages = self._add_structure_prompt(messages)
                result = retry_sync(
                    lambda *args, **kw: invoke_with_timeout(
                        self._model.invoke, (enhanced_messages,), kwargs, self._timeout
                    ),
                    config=self._config.retry,
                    backend=self._backend,
                    role=self._role,
                )

                # 再次验证
                if not self._validate_structured_output(result):
                    logger.error(
                        "[RESILIENT] Structure validation failed after retry for role='%s'",
                        self._role
                    )
                    raise LLMRetryableError(
                        f"Model returned unexpected format after retry: {type(result)}",
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

            # 3. 验证结构化输出
            if self._expected_schema and not self._validate_structured_output(result):
                logger.info(
                    "[RESILIENT] Retrying with structure reminder for role='%s'",
                    self._role
                )
                # 添加提示后重试一次
                enhanced_messages = self._add_structure_prompt(messages)
                result = await retry_async(
                    lambda *args, **kw: ainvoke_with_timeout(
                        self._model.ainvoke(enhanced_messages, **kwargs), self._timeout
                    ),
                    config=self._config.retry,
                    backend=self._backend,
                    role=self._role,
                )

                # 再次验证
                if not self._validate_structured_output(result):
                    logger.error(
                        "[RESILIENT] Structure validation failed after retry for role='%s'",
                        self._role
                    )
                    raise LLMRetryableError(
                        f"Model returned unexpected format after retry: {type(result)}",
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
        """同步降级链执行，带结构化输出验证。"""
        from doc_generation.resilience.fallback import FallbackExhaustedError

        try:
            result = self._fallback_chain.invoke_fallback(messages, **kwargs)

            # 验证 fallback 结果的结构化输出
            if self._expected_schema and not self._validate_structured_output(result):
                logger.info(
                    "[RESILIENT] Fallback result validation failed for role='%s', retrying with structure reminder",
                    self._role
                )
                # 添加提示后重试 fallback
                enhanced_messages = self._add_structure_prompt(messages)
                result = self._fallback_chain.invoke_fallback(enhanced_messages, **kwargs)

                # 再次验证
                if not self._validate_structured_output(result):
                    logger.error(
                        "[RESILIENT] Fallback structure validation failed after retry for role='%s'",
                        self._role
                    )
                    raise LLMFatalError(
                        f"Fallback returned unexpected format after retry: {type(result)}",
                        original=None,
                        backend=self._backend,
                        role=self._role,
                    )

            return result
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
        """异步降级链执行，带结构化输出验证。"""
        from doc_generation.resilience.fallback import FallbackExhaustedError

        try:
            result = await self._fallback_chain.ainvoke_fallback(messages, **kwargs)

            # 验证 fallback 结果的结构化输出
            if self._expected_schema and not self._validate_structured_output(result):
                logger.info(
                    "[RESILIENT] Fallback result validation failed for role='%s', retrying with structure reminder",
                    self._role
                )
                # 添加提示后重试 fallback
                enhanced_messages = self._add_structure_prompt(messages)
                result = await self._fallback_chain.ainvoke_fallback(enhanced_messages, **kwargs)

                # 再次验证
                if not self._validate_structured_output(result):
                    logger.error(
                        "[RESILIENT] Fallback structure validation failed after retry for role='%s'",
                        self._role
                    )
                    raise LLMFatalError(
                        f"Fallback returned unexpected format after retry: {type(result)}",
                        original=None,
                        backend=self._backend,
                        role=self._role,
                    )

            return result
        except FallbackExhaustedError:
            raise
        except Exception as exc:
            raise LLMFatalError(
                f"Fallback chain failed for role '{self._role}': {exc}",
                original=exc,
                backend=self._backend,
                role=self._role,
            ) from exc
