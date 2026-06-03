#***********************************************
#      Filename: base.py
#   Description: 带弹性处理的 BaseTool 基类
#***********************************************

from __future__ import annotations

from typing import Any, Callable, List, Optional, Type
from pydantic import BaseModel
from langchain_core.tools import BaseTool

from doc_generation.resilience.config import load_resilience_config, ResilienceConfig
from doc_generation.resilience.tool_invoker import ResilientTool
from doc_generation.resilience.tool_errors import ToolError

import logging

logger = logging.getLogger(__name__)

_shared_resilience_config: Optional[ResilienceConfig] = None


def _get_shared_config() -> ResilienceConfig:
    global _shared_resilience_config
    if _shared_resilience_config is None:
        _shared_resilience_config = load_resilience_config()
    return _shared_resilience_config


class ResilientBaseTool(BaseTool):
    """内置弹性处理（熔断→重试→降级）的 BaseTool 基类。

    子类实现 _execute() 而非 _run()，弹性流程自动生效。
    """

    name: str = ""
    description: str = ""
    args_schema: Optional[Type[BaseModel]] = None
    fallback_message: str = "工具暂时不可用，请稍后重试。"

    # Pydantic 不追踪这些私有属性，用 model_config exclude 排除
    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, fallback_tools: Optional[List[Callable]] = None, **kwargs: Any):
        super().__init__(**kwargs)
        object.__setattr__(self, "_resilient", ResilientTool(
            tool_fn=self._execute,
            tool_name=self.name,
            config=_get_shared_config(),
            fallback_tools=fallback_tools,
        ))

    def _execute(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._resilient.invoke(*args, **kwargs)
        except ToolError as e:
            logger.error("[%s] failed after resilience handling: %s", self.name, e)
            return f"{self.fallback_message}（{type(e).__name__}）"
