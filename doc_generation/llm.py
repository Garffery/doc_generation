#***********************************************
#      Filename: llm.py
#   Description: 大模型客户端 
#***********************************************


from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
from langchain.chat_models import init_chat_model

from doc_generation.utils import load_config, load_dotenv_if_present

load_dotenv_if_present()


logger = logging.getLogger(__name__)

# 缓存CONFIG，避免重复导入(config_path, stage, loader_id) 
_CONFIG_CACHE: Dict[tuple[str, str, int], Dict[str, Any]] = {}

_PLACEHOLDER_API_KEYS = frozenset(
    {"", "your-openai-api-key-here", "your-deepseek-api-key-here", "CHANGE_ME", "sk-your-api-key-here"}
)
_PLACEHOLDER_BASE_URLS = frozenset({"", "https://your-api-base-url.example/v1"})


def _resolve_openai_credential(
    config_value: str | None,
    env_key: str,
    placeholders: frozenset[str],
) -> str | None:
    env_value = os.environ.get(env_key)
    if env_value:
        return env_value
    if config_value and config_value not in placeholders:
        return config_value
    return None

# 默认的stage
DEFAULT_STAGE = "prod"


class LLMConfigError(ValueError):
    """当LLM配置错误或者不合法时抛出该异常"""


def _resolve_stage(stage: str | None) -> str:
    return stage or os.environ.get("STAGE") or DEFAULT_STAGE


def _load_stage_config(stage_name: str | None, config_path: str | None) -> Dict[str, Any]:
    """加载config.yml"""

    # Key作为config loader的唯一标识
    cache_key = (os.environ.get("CONFIG_PATH", "config.yml"), stage_name, id(load_config))

    if cache_key in _CONFIG_CACHE:
        return _CONFIG_CACHE[cache_key]

    cfg = load_config(stage_name=stage_name, config_path=config_path)
    if cfg is None:
        raise LLMConfigError(f"No config found for stage '{stage_name}'")

    _CONFIG_CACHE[cache_key] = cfg
    return cfg


def _build_openai_kwargs(
    handle: str,
    api_cfg: Dict[str, Any],
    max_tokens: int | None,
    timeout_seconds: Optional[int],
) -> Dict[str, Any]:
    """初始化llm client参数，例如api_key, base_url"""

    model = handle or api_cfg.get("default_model")
    if not model:
        raise LLMConfigError("OpenAI config requires a model name!")

    kwargs: Dict[str, Any] = {
        "model": model,
    }

    api_key = _resolve_openai_credential(
        api_cfg.get("api_key"),
        "OPENAI_API_KEY",
        _PLACEHOLDER_API_KEYS,
    )
    if not api_key:
        raise LLMConfigError(
            "OpenAI api_key is missing. Set OPENAI_API_KEY or cognition.openai.api_key in config."
        )
    kwargs["api_key"] = api_key

    base_url = _resolve_openai_credential(
        api_cfg.get("base_url"),
        "OPENAI_BASE_URL",
        _PLACEHOLDER_BASE_URLS,
    )
    if base_url:
        kwargs["base_url"] = base_url

    organization = api_cfg.get("organization")
    if organization:
        kwargs["organization"] = organization

    # 温度系数
    if api_cfg.get("temperature") is not None:
        kwargs["temperature"] = api_cfg["temperature"]

    # # 最大token数（新模型使用 max_completion_tokens）
    # if max_tokens is not None:
    #     kwargs["max_completion_tokens"] = max_tokens

    # 请求超时
    if timeout_seconds is not None:
        # OpenAI兼容接口可用接收timeout/request_timeout
        kwargs["timeout"] = timeout_seconds
        kwargs["request_timeout"] = timeout_seconds

    # 模型参数（可选）
    model_kwargs: Dict[str, Any] = {}
    if model_kwargs:
        kwargs["model_kwargs"] = model_kwargs

    return kwargs


def _resolve_config_max_tokens(api_cfg: Dict[str, Any], handle: str) -> int | None:
    """解析最大token数"""
    models_cfg = api_cfg.get("models") or {}
    model_cfg = models_cfg.get(handle) or {}
    return model_cfg.get("max_tokens")


def _resolve_timeout_seconds(api_cfg: Dict[str, Any], role_cfg: Dict[str, Any]) -> Optional[int]:
    """解析timeout/request_timeout/timeout_seconds参数"""
    for cfg in (role_cfg, api_cfg):
        for key in ("timeout", "request_timeout", "timeout_seconds"):
            if cfg.get(key) is not None:
                return cfg.get(key)
    return None


def _build_deepseek_kwargs(
    handle: str,
    api_cfg: Dict[str, Any],
    max_tokens: int | None,
    timeout_seconds: Optional[int],
) -> Dict[str, Any]:
    """构建 DeepSeek 模型参数，DeepSeek API 兼容 OpenAI 格式。"""

    model = handle or api_cfg.get("default_model")
    if not model:
        raise LLMConfigError("DeepSeek config requires a model name!")

    kwargs: Dict[str, Any] = {
        "model": model,
        "model_provider": "deepseek",
    }

    api_key = _resolve_openai_credential(
        api_cfg.get("api_key"),
        "DEEPSEEK_API_KEY",
        _PLACEHOLDER_API_KEYS,
    )
    if not api_key:
        raise LLMConfigError(
            "DeepSeek api_key is missing. Set DEEPSEEK_API_KEY or cognition.deepseek.api_key in config."
        )
    kwargs["api_key"] = api_key

    base_url = _resolve_openai_credential(
        api_cfg.get("base_url"),
        "DEEPSEEK_BASE_URL",
        _PLACEHOLDER_BASE_URLS,
    )
    if base_url:
        kwargs["api_base"] = base_url

    if api_cfg.get("temperature") is not None:
        kwargs["temperature"] = api_cfg["temperature"]

    if timeout_seconds is not None:
        kwargs["timeout"] = timeout_seconds
        kwargs["request_timeout"] = timeout_seconds

    # 关闭 thinking 模式，避免与 tool_choice 冲突
    thinking_cfg = api_cfg.get("thinking", {"type": "disabled"})
    kwargs["model_kwargs"] = {"extra_body": {"thinking": thinking_cfg}}

    return kwargs


def _build_kwargs(
    backend: str,
    handle: str,
    api_cfg: Dict[str, Any],
    role_cfg: Dict[str, Any],
    max_tokens: int | None,
    timeout_seconds: int | None,
) -> Dict[str, Any]:

    if backend == "openai":
        return _build_openai_kwargs(handle, api_cfg, max_tokens, timeout_seconds)
    elif backend == "deepseek":
        return _build_deepseek_kwargs(handle, api_cfg, max_tokens, timeout_seconds)
    else:
        raise LLMConfigError(f"Unsupported backend '{backend}'")


def get_chat_model(role: str, *, stage: str | None = None, max_tokens: int | None = None):
    """根据config和role返回LLM client.

    Args:
        role: 角色名，例如supervisor, writer
        stage: stage name 
        max_tokens: 最大tokens 
    """

    # 获取config路径
    config_path = os.environ.get("CONFIG_PATH", "config.yml")
    resolved_stage = _resolve_stage(stage)               ## 获取开发阶段，如开发，测试,生产等

    # 加载config.yam
    cfg = _load_stage_config(resolved_stage, config_path)

    # 获取role配置 
    roles_cfg = cfg.get("roles", {})
    if role not in roles_cfg:
        # 清除cache重新加载一次
        _CONFIG_CACHE.clear()
        cfg = _load_stage_config(resolved_stage, config_path)
        roles_cfg = cfg.get("roles", {})

    # 如果role配置错误
    if role not in roles_cfg:
        available = ", ".join(sorted(roles_cfg.keys())) or "<none>"
        raise LLMConfigError(
            f"Role '{role}' not found for stage '{resolved_stage}' using config '{config_path}'. Available: {available}"
        )

    # 解析backend和handle
    role_cfg = roles_cfg[role]
    backend = role_cfg.get("backend")
    handle = role_cfg.get("handle")
    if not backend or not handle:
        raise LLMConfigError(f"Role '{role}' is missing backend or handle")

    # 解析llm api config
    api_cfg = cfg.get("cognition", {}).get(backend)
    if api_cfg is None:
        raise LLMConfigError(f"No cognition config for backend '{backend}'")

    # 获取超时时间
    resolved_timeout = _resolve_timeout_seconds(api_cfg, role_cfg)
    logger.info(
        "Selected cognition backend '%s' for role '%s' with handle '%s' (timeout=%s)",
        backend,
        role,
        handle,
        resolved_timeout,
    )

    # 获取输出最大token数
    resolved_max_tokens = max_tokens
    if resolved_max_tokens is None:
        resolved_max_tokens = _resolve_config_max_tokens(api_cfg, handle)

    # 新建llm client
    kwargs = _build_kwargs(
        backend=backend,
        handle=handle,
        api_cfg=api_cfg,
        role_cfg=role_cfg,
        max_tokens=resolved_max_tokens,
        timeout_seconds=resolved_timeout
    )
    return init_chat_model(**kwargs)
