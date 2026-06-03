#***********************************************
#      Filename: tool_errors.py
#   Description: 工具调用错误分类体系
#***********************************************

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """工具调用错误基类"""

    def __init__(self, message: str, *, original: Exception | None = None, tool_name: str = ""):
        super().__init__(message)
        self.original = original
        self.tool_name = tool_name


# --- 可重试错误（瞬态） ---

class ToolRetryableError(ToolError):
    """可通过重试恢复的瞬态错误基类"""
    pass


class ToolRateLimitError(ToolRetryableError):
    """429 速率限制"""

    def __init__(self, message: str, *, retry_after: float | None = None, **kwargs: Any):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ToolTimeoutError(ToolRetryableError):
    """请求超时（408/504/连接超时）"""
    pass


class ToolServerError(ToolRetryableError):
    """服务器错误（500/502/503）"""
    pass


class ToolConnectionError(ToolRetryableError):
    """网络连接失败"""
    pass


# --- 致命错误（不可重试，触发降级或直接失败） ---

class ToolFatalError(ToolError):
    """不可重试的致命错误基类"""
    pass


class ToolBadInputError(ToolFatalError):
    """错误输入（400）- 可以尝试让 LLM 修正参数后重试一次"""

    def __init__(self, message: str, *, error_details: str = "", **kwargs):
        super().__init__(message, **kwargs)
        self.error_details = error_details


class ToolAuthError(ToolFatalError):
    """认证/授权失败（401/403）"""
    pass


class ToolNotFoundError(ToolFatalError):
    """资源不存在（404）"""
    pass


class ToolConfigError(ToolFatalError):
    """工具配置错误（如缺少 API key）"""
    pass


class ToolCircuitOpenError(ToolError):
    """熔断器处于 Open 状态，拒绝请求"""
    pass


# --- 错误分类器 ---

def _get_status_code(exc: Exception) -> int | None:
    """从异常中提取 HTTP 状态码"""
    if hasattr(exc, "status_code"):
        return exc.status_code
    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        return exc.response.status_code
    if hasattr(exc, "http_status"):
        return exc.http_status
    if hasattr(exc, "code"):
        code = exc.code
        if isinstance(code, int) and 100 <= code <= 599:
            return code
    return None


def _get_error_body(exc: Exception) -> str:
    """从异常中提取错误消息体"""
    if hasattr(exc, "body") and isinstance(exc.body, dict):
        return str(exc.body.get("message", ""))
    if hasattr(exc, "response"):
        resp = exc.response
        if hasattr(resp, "text"):
            return resp.text[:500] if resp.text else ""
        if hasattr(resp, "json"):
            try:
                return str(resp.json())[:500]
            except Exception:
                pass
    return str(exc)


def _extract_retry_after(exc: Exception) -> float | None:
    """从异常中提取 Retry-After 值"""
    if hasattr(exc, "response") and hasattr(exc.response, "headers"):
        headers = exc.response.headers
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except (ValueError, TypeError):
                pass
    return None


def classify_tool_error(exc: Exception, *, tool_name: str = "") -> ToolError:
    """将原始异常分类为具体的 ToolError 子类型。

    Args:
        exc: 原始异常
        tool_name: 工具名称

    Returns:
        分类后的 ToolError 实例
    """
    common_kwargs = {"original": exc, "tool_name": tool_name}
    exc_type_name = type(exc).__name__.lower()
    exc_msg = str(exc).lower()

    # 超时类异常（按类型名匹配）
    timeout_keywords = ("timeout", "timed out", "timedout")
    if any(kw in exc_type_name for kw in timeout_keywords) or any(kw in exc_msg for kw in timeout_keywords):
        return ToolTimeoutError(str(exc), **common_kwargs)

    # 连接类异常
    connection_keywords = ("connection", "connect", "network", "dns", "resolve")
    if any(kw in exc_type_name for kw in connection_keywords):
        return ToolConnectionError(str(exc), **common_kwargs)

    # 基于 HTTP 状态码分类
    status_code = _get_status_code(exc)
    if status_code is not None:
        if status_code == 429:
            retry_after = _extract_retry_after(exc)
            return ToolRateLimitError(str(exc), retry_after=retry_after, **common_kwargs)

        if status_code in (408, 504):
            return ToolTimeoutError(str(exc), **common_kwargs)

        if status_code in (500, 502, 503):
            return ToolServerError(str(exc), **common_kwargs)

        if status_code in (401, 403):
            return ToolAuthError(str(exc), **common_kwargs)

        if status_code == 404:
            return ToolNotFoundError(str(exc), **common_kwargs)

        if status_code == 400:
            body = _get_error_body(exc)
            return ToolBadInputError(str(exc), error_details=body, **common_kwargs)

    # 基于异常类型名的模式匹配
    if "ratelimit" in exc_type_name:
        retry_after = _extract_retry_after(exc)
        return ToolRateLimitError(str(exc), retry_after=retry_after, **common_kwargs)

    if "authentication" in exc_type_name or "permission" in exc_type_name or "unauthorized" in exc_type_name:
        return ToolAuthError(str(exc), **common_kwargs)

    if "notfound" in exc_type_name or "404" in exc_msg:
        return ToolNotFoundError(str(exc), **common_kwargs)

    if "badrequest" in exc_type_name or "invalidrequest" in exc_type_name or "validation" in exc_type_name:
        body = _get_error_body(exc)
        return ToolBadInputError(str(exc), error_details=body, **common_kwargs)

    if "config" in exc_type_name or "configuration" in exc_type_name:
        return ToolConfigError(str(exc), **common_kwargs)

    # 基于错误消息内容的模式匹配
    if "rate limit" in exc_msg or "rate_limit" in exc_msg or "too many requests" in exc_msg:
        return ToolRateLimitError(str(exc), **common_kwargs)

    if "server error" in exc_msg or "internal error" in exc_msg:
        return ToolServerError(str(exc), **common_kwargs)

    if "api key" in exc_msg or "api_key" in exc_msg or "missing credentials" in exc_msg:
        return ToolConfigError(str(exc), **common_kwargs)

    # 默认：视为可重试错误（保守策略）
    logger.warning("Unclassified tool error (treating as retryable): %s: %s", type(exc).__name__, exc)
    return ToolRetryableError(str(exc), **common_kwargs)
