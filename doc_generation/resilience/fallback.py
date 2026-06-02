#***********************************************
#      Filename: fallback.py
#   Description: 降级链（备用模型 + 静态兜底）
#***********************************************

from __future__ import annotations

import logging
from typing import Any, List

from langchain_core.messages import AIMessage

from doc_generation.resilience.config import FallbackEntry, ResilienceConfig
from doc_generation.resilience.errors import LLMFatalError, classify_error

logger = logging.getLogger(__name__)


class FallbackExhaustedError(LLMFatalError):
    """所有降级选项均已耗尽"""
    pass


class FallbackChain:
    """降级链：按顺序尝试备用模型，最后返回静态兜底响应。

    降级流程：
    1. 主模型重试失败后进入降级链
    2. 按配置顺序尝试每个备用模型（单次调用，不重试）
    3. 如果所有备用模型都失败，返回静态兜底响应
    4. 如果没有配置任何降级选项，抛出 FallbackExhaustedError
    """

    def __init__(self, role: str, entries: List[FallbackEntry], global_static: str):
        self.role = role
        self.entries = entries
        self.global_static = global_static

    @classmethod
    def from_config(cls, role: str, config: ResilienceConfig) -> "FallbackChain":
        entries = config.get_fallback_chain(role)
        return cls(role=role, entries=entries, global_static=config.static_response)

    def _create_fallback_model(self, entry: FallbackEntry) -> Any:
        """根据 FallbackEntry 创建备用模型实例。"""
        from langchain.chat_models import init_chat_model
        from doc_generation.llm import _load_stage_config, _build_kwargs, _resolve_stage, _resolve_timeout_seconds
        import os

        config_path = os.environ.get("CONFIG_PATH", "config.yml")
        stage = _resolve_stage(None)
        cfg = _load_stage_config(stage, config_path)

        api_cfg = cfg.get("cognition", {}).get(entry.backend)
        if api_cfg is None:
            raise ValueError(f"No cognition config for fallback backend '{entry.backend}'")

        role_cfg = {}
        timeout = _resolve_timeout_seconds(api_cfg, role_cfg)

        kwargs = _build_kwargs(
            backend=entry.backend,
            handle=entry.handle or "",
            api_cfg=api_cfg,
            role_cfg=role_cfg,
            max_tokens=None,
            timeout_seconds=timeout,
        )
        return init_chat_model(**kwargs)

    def invoke_fallback(self, messages: Any, **kwargs: Any) -> Any:
        """同步执行降级链。

        Args:
            messages: 原始消息列表
            **kwargs: 传递给模型的额外参数

        Returns:
            备用模型的响应或静态兜底 AIMessage

        Raises:
            FallbackExhaustedError: 所有降级选项均失败
        """
        for i, entry in enumerate(self.entries):
            if entry.is_static:
                logger.info("[FALLBACK] role='%s' using static fallback at position %d", self.role, i)
                return AIMessage(content=entry.static)

            try:
                logger.info(
                    "[FALLBACK] role='%s' trying fallback model %s/%s (position %d)",
                    self.role, entry.backend, entry.handle, i
                )
                model = self._create_fallback_model(entry)
                return model.invoke(messages, **kwargs)
            except Exception as exc:
                logger.warning(
                    "[FALLBACK] role='%s' fallback %s/%s failed: %s",
                    self.role, entry.backend, entry.handle, exc
                )
                continue

        # 所有配置的降级都失败了，使用全局静态兜底
        if self.global_static:
            logger.warning("[FALLBACK] role='%s' all fallbacks exhausted, using global static response", self.role)
            return AIMessage(content=self.global_static)

        raise FallbackExhaustedError(
            f"All fallback options exhausted for role '{self.role}'",
            role=self.role,
        )

    async def ainvoke_fallback(self, messages: Any, **kwargs: Any) -> Any:
        """异步执行降级链。

        Args:
            messages: 原始消息列表
            **kwargs: 传递给模型的额外参数

        Returns:
            备用模型的响应或静态兜底 AIMessage

        Raises:
            FallbackExhaustedError: 所有降级选项均失败
        """
        for i, entry in enumerate(self.entries):
            if entry.is_static:
                logger.info("[FALLBACK] role='%s' using static fallback at position %d", self.role, i)
                return AIMessage(content=entry.static)

            try:
                logger.info(
                    "[FALLBACK] role='%s' trying fallback model %s/%s (position %d)",
                    self.role, entry.backend, entry.handle, i
                )
                model = self._create_fallback_model(entry)
                return await model.ainvoke(messages, **kwargs)
            except Exception as exc:
                logger.warning(
                    "[FALLBACK] role='%s' fallback %s/%s failed: %s",
                    self.role, entry.backend, entry.handle, exc
                )
                continue

        if self.global_static:
            logger.warning("[FALLBACK] role='%s' all fallbacks exhausted, using global static response", self.role)
            return AIMessage(content=self.global_static)

        raise FallbackExhaustedError(
            f"All fallback options exhausted for role '{self.role}'",
            role=self.role,
        )
