#***********************************************
#      Filename: config.py
#   Description: Resilience 配置解析
#***********************************************

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from doc_generation.utils import load_config

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: bool = True


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2


@dataclass
class WatchdogConfig:
    """超时看门狗配置"""
    default_timeout: float = 120.0


@dataclass
class FallbackEntry:
    """降级链中的一个条目"""
    backend: Optional[str] = None
    handle: Optional[str] = None
    static: Optional[str] = None

    @property
    def is_static(self) -> bool:
        return self.static is not None


@dataclass
class ResilienceConfig:
    """完整的 Resilience 配置"""
    retry: RetryConfig = field(default_factory=RetryConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)
    static_response: str = "系统暂时无法处理您的请求，请稍后重试。"
    role_fallbacks: Dict[str, List[FallbackEntry]] = field(default_factory=dict)
    role_backends: Dict[str, str] = field(default_factory=dict)

    def get_fallback_chain(self, role: str) -> List[FallbackEntry]:
        return self.role_fallbacks.get(role, [])

    def get_backend(self, role: str) -> str:
        return self.role_backends.get(role, "unknown")


def _parse_retry_config(raw: Dict[str, Any]) -> RetryConfig:
    return RetryConfig(
        max_attempts=raw.get("max_attempts", 3),
        base_delay=raw.get("base_delay", 1.0),
        max_delay=raw.get("max_delay", 30.0),
        jitter=raw.get("jitter", True),
    )


def _parse_circuit_breaker_config(raw: Dict[str, Any]) -> CircuitBreakerConfig:
    return CircuitBreakerConfig(
        failure_threshold=raw.get("failure_threshold", 5),
        recovery_timeout=raw.get("recovery_timeout", 60.0),
        success_threshold=raw.get("success_threshold", 2),
    )


def _parse_watchdog_config(raw: Dict[str, Any]) -> WatchdogConfig:
    return WatchdogConfig(
        default_timeout=raw.get("default_timeout", 120.0),
    )


def _parse_fallback_chain(raw_list: List[Dict[str, Any]]) -> List[FallbackEntry]:
    entries = []
    for item in raw_list:
        entries.append(FallbackEntry(
            backend=item.get("backend"),
            handle=item.get("handle"),
            static=item.get("static"),
        ))
    return entries


def load_resilience_config(stage: str | None = None, config_path: str | None = None) -> ResilienceConfig:
    """从 config.yml 加载 resilience 配置。

    Args:
        stage: 环境阶段名（prod/dev/test）
        config_path: 配置文件路径

    Returns:
        解析后的 ResilienceConfig 实例
    """
    resolved_path = config_path or os.environ.get("CONFIG_PATH", "config.yml")
    resolved_stage = stage or os.environ.get("STAGE") or "prod"

    try:
        cfg = load_config(stage_name=resolved_stage, config_path=resolved_path)
    except Exception as e:
        logger.warning("Failed to load config for resilience (using defaults): %s", e)
        return ResilienceConfig()

    if cfg is None:
        return ResilienceConfig()

    # 解析 resilience 顶层配置
    resilience_raw = cfg.get("resilience", {})
    retry = _parse_retry_config(resilience_raw.get("retry", {}))
    circuit_breaker = _parse_circuit_breaker_config(resilience_raw.get("circuit_breaker", {}))
    watchdog = _parse_watchdog_config(resilience_raw.get("watchdog", {}))
    static_response = resilience_raw.get("fallback", {}).get(
        "static_response", "系统暂时无法处理您的请求，请稍后重试。"
    )

    # 解析各 role 的 fallback_chain 和 backend
    roles_cfg = cfg.get("roles", {})
    role_fallbacks: Dict[str, List[FallbackEntry]] = {}
    role_backends: Dict[str, str] = {}

    for role_name, role_cfg in roles_cfg.items():
        if isinstance(role_cfg, dict):
            role_backends[role_name] = role_cfg.get("backend", "unknown")
            fallback_raw = role_cfg.get("fallback_chain", [])
            if fallback_raw:
                role_fallbacks[role_name] = _parse_fallback_chain(fallback_raw)

    return ResilienceConfig(
        retry=retry,
        circuit_breaker=circuit_breaker,
        watchdog=watchdog,
        static_response=static_response,
        role_fallbacks=role_fallbacks,
        role_backends=role_backends,
    )
