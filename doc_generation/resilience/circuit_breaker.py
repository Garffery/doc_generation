#***********************************************
#      Filename: circuit_breaker.py
#   Description: Per-Backend 熔断器
#***********************************************

from __future__ import annotations

import logging
import threading
import time
from enum import Enum

from doc_generation.resilience.config import CircuitBreakerConfig
from doc_generation.resilience.errors import CircuitOpenError

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-backend 熔断器，线程安全。

    三态转换：
    - CLOSED: 正常通行，记录失败次数
    - OPEN: 达到失败阈值后，拒绝所有请求，直到冷却期结束
    - HALF_OPEN: 冷却期后允许一个探测请求通过，成功则关闭，失败则重新打开
    """

    def __init__(self, backend: str, config: CircuitBreakerConfig | None = None):
        self.backend = backend
        cfg = config or CircuitBreakerConfig()
        self._failure_threshold = cfg.failure_threshold
        self._recovery_timeout = cfg.recovery_timeout
        self._success_threshold = cfg.success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._get_state_unlocked()

    def _get_state_unlocked(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info("[CIRCUIT] Backend '%s' transitioning OPEN -> HALF_OPEN", self.backend)
        return self._state

    def allow_request(self) -> bool:
        """检查是否允许请求通过。"""
        with self._lock:
            state = self._get_state_unlocked()
            if state == CircuitState.CLOSED:
                return True
            if state == CircuitState.HALF_OPEN:
                return True
            return False

    def record_success(self) -> None:
        """记录一次成功调用。"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info("[CIRCUIT] Backend '%s' recovered: HALF_OPEN -> CLOSED", self.backend)
            else:
                self._failure_count = 0

    def record_failure(self) -> None:
        """记录一次失败调用。"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("[CIRCUIT] Backend '%s' probe failed: HALF_OPEN -> OPEN", self.backend)
            elif self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "[CIRCUIT] Backend '%s' tripped: CLOSED -> OPEN (failures=%d)",
                    self.backend, self._failure_count
                )

    def reset(self) -> None:
        """手动重置熔断器（用于测试或运维操作）。"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            logger.info("[CIRCUIT] Backend '%s' manually reset to CLOSED", self.backend)


# --- 全局注册表 ---

_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_breaker(backend: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
    """获取或创建指定 backend 的熔断器实例。"""
    with _breakers_lock:
        if backend not in _breakers:
            _breakers[backend] = CircuitBreaker(backend=backend, config=config)
        return _breakers[backend]


def reset_all_breakers() -> None:
    """重置所有熔断器（用于测试）。"""
    with _breakers_lock:
        for breaker in _breakers.values():
            breaker.reset()
