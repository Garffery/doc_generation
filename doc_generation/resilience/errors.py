#***********************************************
#      Filename: errors.py
#   Description: LLM 调用错误分类体系
#***********************************************

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """LLM 调用错误基类"""

    def __init__(self, message: str, *, original: Exception | None = None, backend: str = "", role: str = ""):
        super().__init__(message)
        self.original = original
        self.backend = backend
        self.role = role


# --- 可重试错误（瞬态） ---

class LLMRetryableError(LLMError):
    """可通过重试恢复的瞬态错误基类"""
    pass


class LLMRateLimitError(LLMRetryableError):
    """429 速率限制"""

    def __init__(self, message: str, *, retry_after: float | None = None, **kwargs: Any):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class LLMTimeoutError(LLMRetryableError):
    """请求超时（408/504/连接超时/Watchdog 超时）"""
    pass


class LLMModelOverloadedError(LLMRetryableError):
    """模型过载（500/502/503）"""
    pass


class LLMConnectionError(LLMRetryableError):
    """网络连接失败"""
    pass


# --- 致命错误（不可重试，触发降级或直接失败） ---

class LLMFatalError(LLMError):
    """不可重试的致命错误基类"""
    pass


class LLMOutputParseError(LLMFatalError):
    """结构化输出解析失败（Pydantic ValidationError、JSON 解析错误等）。
    不可重试 — 相同 prompt 大概率产生相同的非法输出，直接走降级链。
    """

    def __init__(self, message: str, *, raw_output: str = "", **kwargs):
        super().__init__(message, **kwargs)
        self.raw_output = raw_output


class LLMAuthError(LLMFatalError):
    """认证/授权失败（401/403）"""
    pass


class LLMContentFilterError(LLMFatalError):
    """内容安全过滤"""
    pass


class LLMContextLengthError(LLMFatalError):
    """上下文长度超限"""
    pass


class LLMInvalidRequestError(LLMFatalError):
    """无效请求（400，非上述特定类型）"""
    pass


class CircuitOpenError(LLMError):
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


def classify_error(exc: Exception, *, backend: str = "", role: str = "") -> LLMError:
    """将原始异常分类为具体的 LLMError 子类型。

    Args:
        exc: 原始异常
        backend: 后端名称（openai/deepseek）
        role: 角色名称

    Returns:
        分类后的 LLMError 实例
    """
    common_kwargs = {"original": exc, "backend": backend, "role": role}
    exc_type_name = type(exc).__name__.lower()
    exc_msg = str(exc).lower()

    # 超时类异常（按类型名匹配）
    timeout_keywords = ("timeout", "timed out", "timedout")
    if any(kw in exc_type_name for kw in timeout_keywords) or any(kw in exc_msg for kw in timeout_keywords):
        return LLMTimeoutError(str(exc), **common_kwargs)

    # 连接类异常
    connection_keywords = ("connection", "connect", "network", "dns", "resolve")
    if any(kw in exc_type_name for kw in connection_keywords):
        return LLMConnectionError(str(exc), **common_kwargs)

    # 基于 HTTP 状态码分类
    status_code = _get_status_code(exc)
    if status_code is not None:
        # 429: 速率限制 —— 请求频率超出 API 配额，需等待后重试
        if status_code == 429:
            retry_after = _extract_retry_after(exc)
            return LLMRateLimitError(str(exc), retry_after=retry_after, **common_kwargs)

        # 408: 请求超时；504: 网关超时 —— 服务端未在规定时间内响应
        if status_code in (408, 504):
            return LLMTimeoutError(str(exc), **common_kwargs)

        # 500: 服务器内部错误；502: 网关错误；503: 服务不可用 —— 模型服务过载或暂时故障
        if status_code in (500, 502, 503):
            return LLMModelOverloadedError(str(exc), **common_kwargs)

        # 401: 未认证（API Key 无效/缺失）；403: 无权限（Key 有效但无权访问该资源）
        if status_code in (401, 403):
            return LLMAuthError(str(exc), **common_kwargs)

        # 400: 错误请求 —— 根据响应体内容进一步细分错误类型
        if status_code == 400:
            body = _get_error_body(exc)
            body_lower = body.lower()
            # 响应体提及认证/授权关键词，归为认证错误
            if "authentication" in body_lower or "authorization" in body_lower:
                return LLMAuthError(str(exc), **common_kwargs)
            # 响应体提及内容过滤/安全策略，归为内容审核拦截
            if "content_filter" in body_lower or "content_policy" in body_lower or "safety" in body_lower:
                return LLMContentFilterError(str(exc), **common_kwargs)
            # 响应体提及上下文长度/token 超限，归为上下文超长错误
            if "context_length" in body_lower or "max_tokens" in body_lower or "too long" in body_lower:
                return LLMContextLengthError(str(exc), **common_kwargs)
            return LLMInvalidRequestError(str(exc), **common_kwargs)

    # 基于异常类型名的模式匹配（兼容 openai SDK 的异常类）
    if "ratelimit" in exc_type_name:
        retry_after = _extract_retry_after(exc)
        return LLMRateLimitError(str(exc), retry_after=retry_after, **common_kwargs)

    if "authentication" in exc_type_name or "permission" in exc_type_name:
        return LLMAuthError(str(exc), **common_kwargs)

    if "badrequest" in exc_type_name or "invalidrequest" in exc_type_name:
        body = _get_error_body(exc)
        body_lower = body.lower()
        if "context_length" in body_lower or "max_tokens" in body_lower:
            return LLMContextLengthError(str(exc), **common_kwargs)
        return LLMInvalidRequestError(str(exc), **common_kwargs)

    if "overloaded" in exc_type_name or "serviceunavailable" in exc_type_name:
        return LLMModelOverloadedError(str(exc), **common_kwargs)

    # 基于错误消息内容的模式匹配
    if "rate limit" in exc_msg or "rate_limit" in exc_msg or "too many requests" in exc_msg:
        return LLMRateLimitError(str(exc), **common_kwargs)

    if "overloaded" in exc_msg or "capacity" in exc_msg:
        return LLMModelOverloadedError(str(exc), **common_kwargs)

    # 结构化输出解析失败（Pydantic ValidationError, OutputParserException, JSON解析错误）
    parse_keywords = ("validationerror", "outputparser", "jsondecodeerror", "json_parse", "parsing")
    if any(kw in exc_type_name for kw in parse_keywords):
        raw_output = str(exc)[:1000]
        return LLMOutputParseError(str(exc), raw_output=raw_output, **common_kwargs)

    if "output_parser" in exc_msg or "failed to parse" in exc_msg or "json" in exc_type_name:
        raw_output = str(exc)[:1000]
        return LLMOutputParseError(str(exc), raw_output=raw_output, **common_kwargs)

    # 默认：视为可重试错误（保守策略）
    logger.warning("Unclassified LLM error (treating as retryable): %s: %s", type(exc).__name__, exc)
    return LLMRetryableError(str(exc), **common_kwargs)
