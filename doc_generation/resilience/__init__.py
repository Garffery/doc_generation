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
from doc_generation.resilience.invoker import ResilientModel
from doc_generation.resilience.watchdog import WatchdogTimeoutError

__all__ = [
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
    "CircuitBreaker",
    "CircuitState",
    "get_breaker",
    "reset_all_breakers",
    "ResilienceConfig",
    "RetryConfig",
    "CircuitBreakerConfig",
    "WatchdogConfig",
    "FallbackEntry",
    "load_resilience_config",
    "FallbackChain",
    "FallbackExhaustedError",
    "ResilientModel",
    "WatchdogTimeoutError",
]
