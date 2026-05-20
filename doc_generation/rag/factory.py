#***********************************************
#      Filename: factory.py
#   Description: RAG 配置加载与 Chroma store 工厂
#***********************************************

from __future__ import annotations

import os
from typing import Any, Dict

import logging

from doc_generation.rag.chroma_store import ChromaRagStore
from doc_generation.rag.errors import RagConfigError
from doc_generation.utils import load_config, load_dotenv_if_present

load_dotenv_if_present()

DEFAULT_STAGE = "prod"
logger = logging.getLogger(__name__)


_RAG_STORE_CACHE: Dict[tuple[str, str, str], ChromaRagStore] = {}


def _resolve_stage(stage: str | None) -> str:
    return stage or os.environ.get("STAGE") or DEFAULT_STAGE


def _load_stage_config(stage: str | None) -> Dict[str, Any]:
    stage_name = _resolve_stage(stage)
    config_path = os.environ.get("CONFIG_PATH", "config.yml")
    cfg = load_config(stage_name=stage_name, config_path=config_path)
    if cfg is None:
        raise RagConfigError(f"No config found for stage '{stage_name}'")
    return cfg


def _get_rag_cfg(stage: str | None = None) -> Dict[str, Any]:
    cfg = _load_stage_config(stage)
    return cfg.get("rag") or {}


def is_rag_enabled(*, stage: str | None = None) -> bool:
    """当前 stage 是否启用了 RAG（config 中存在 rag 块且 enabled 不为 false）。"""
    rag_cfg = _get_rag_cfg(stage)
    if not rag_cfg:
        return False
    return bool(rag_cfg.get("enabled", True))


def get_rag_defaults(*, stage: str | None = None) -> Dict[str, Any]:
    """返回 RAG 检索默认参数（top_k 等）。"""
    rag_cfg = _get_rag_cfg(stage)
    if not is_rag_enabled(stage=stage):
        raise RagConfigError("RAG is not enabled for this stage")

    backend = (rag_cfg.get("backend") or "chroma").lower()
    backend_cfg = rag_cfg.get(backend, {}) if isinstance(rag_cfg.get(backend), dict) else {}
    if not isinstance(backend_cfg, dict):
        raise RagConfigError(f"RAG config for backend '{backend}' must be a mapping")

    defaults = {
        "top_k": 5,
        "score_threshold": None,
    }
    defaults.update({k: backend_cfg.get(k, defaults[k]) for k in defaults})
    return defaults


def get_rag_store(*, stage: str | None = None) -> ChromaRagStore:
    """根据 config.yml 获取（并缓存）Chroma RAG store。"""
    if not is_rag_enabled(stage=stage):
        raise RagConfigError("RAG is not enabled for this stage")

    stage_name = _resolve_stage(stage)
    rag_cfg = _get_rag_cfg(stage)
    backend = (rag_cfg.get("backend") or "chroma").lower()
    if backend != "chroma":
        raise RagConfigError(
            f"Unsupported RAG backend '{backend}'. Only 'chroma' is supported."
        )

    config_path = os.environ.get("CONFIG_PATH", "config.yml")
    backend_cfg = rag_cfg.get("chroma", {}) if isinstance(rag_cfg.get("chroma"), dict) else {}
    collection_name = backend_cfg.get("collection_name", "doc_generation")
    cache_key = (config_path, stage_name, collection_name)

    if cache_key in _RAG_STORE_CACHE:
        logger.debug("Using cached RAG store collection='%s'", collection_name)
        return _RAG_STORE_CACHE[cache_key]

    logger.info(
        "Building Chroma RAG store stage='%s' collection='%s'",
        stage_name,
        collection_name,
    )
    store = ChromaRagStore.from_config(rag_cfg, stage_cfg=_load_stage_config(stage))
    _RAG_STORE_CACHE[cache_key] = store
    return store


def clear_rag_cache() -> None:
    """清空 RAG store 缓存（测试或热重载配置时使用）。"""
    _RAG_STORE_CACHE.clear()
