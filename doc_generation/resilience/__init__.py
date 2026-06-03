#***********************************************
#      Filename: __init__.py
#   Description: Resilience 模块公共 API
#***********************************************

from doc_generation.resilience.errors import (
    LLMError,
    LLMRetryableError,
    LLMFatalError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMAuthError,
    LLMContentFilterError,
    LLMContextLengthError,
    LLMConnectionError,
    LLMInvalidRequestError,
    LLMModelOverloadedError,
    LLMOutputParseError,
    CircuitOpenError,
    classify_error,
)
from doc_generation.resilience.tool_errors import (
    ToolError,
    ToolRetryableError,
    ToolFatalError,
    ToolTimeoutError,
    ToolRateLimitError,
    ToolServerError,
    ToolConnectionError,
    ToolBadInputError,
    ToolAuthError,
    ToolNotFoundError,
    ToolConfigError,
    ToolCircuitOpenError,
    classify_tool_error,
)
from doc_generation.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    get_breaker,
    reset_all_breakers,
)
from doc_generation.resilience.config import (
    ResilienceConfig,
    RetryConfig,
    CircuitBreakerConfig,
    WatchdogConfig,
    FallbackEntry,
    load_resilience_config,
)
from doc_generation.resilience.fallback import FallbackChain, FallbackExhaustedError
from doc_generation.resilience.tool_fallback import (
    ToolFallbackChain,
    FallbackToolExhaustedError,
    register_tool_capability,
    get_fallback_tools,
)
from doc_generation.resilience.invoker import ResilientModel
from doc_generation.resilience.tool_invoker import ResilientTool
from doc_generation.resilience.tool_cost import (
    ToolCostTracker,
    ToolCostStats,
    ToolCallRecord,
    get_cost_tracker,
)
from doc_generation.resilience.watchdog import WatchdogTimeoutError

__all__ = [
    # LLM 错误
    "LLMError",
    "LLMRetryableError",
    "LLMFatalError",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "LLMAuthError",
    "LLMContentFilterError",
    "LLMContextLengthError",
    "LLMConnectionError",
    "LLMInvalidRequestError",
    "LLMModelOverloadedError",
    "LLMOutputParseError",
    "CircuitOpenError",
    "classify_error",
    # 工具错误
    "ToolError",
    "ToolRetryableError",
    "ToolFatalError",
    "ToolTimeoutError",
    "ToolRateLimitError",
    "ToolServerError",
    "ToolConnectionError",
    "ToolBadInputError",
    "ToolAuthError",
    "ToolNotFoundError",
    "ToolConfigError",
    "ToolCircuitOpenError",
    "classify_tool_error",
    # 熔断器
    "CircuitBreaker",
    "CircuitState",
    "get_breaker",
    "reset_all_breakers",
    # 配置
    "ResilienceConfig",
    "RetryConfig",
    "CircuitBreakerConfig",
    "WatchdogConfig",
    "FallbackEntry",
    "load_resilience_config",
    # 降级链
    "FallbackChain",
    "FallbackExhaustedError",
    "ToolFallbackChain",
    "FallbackToolExhaustedError",
    "register_tool_capability",
    "get_fallback_tools",
    # 调用器
    "ResilientModel",
    "ResilientTool",
    # 成本追踪
    "ToolCostTracker",
    "ToolCostStats",
    "ToolCallRecord",
    "get_cost_tracker",
    # 其他
    "WatchdogTimeoutError",
]
