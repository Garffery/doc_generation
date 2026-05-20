#***********************************************
#      Filename: chroma_store.py
#   Description: 基于 Chroma 的向量存储与检索
#***********************************************

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import logging

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from doc_generation.rag.errors import RagConfigError

logger = logging.getLogger(__name__)

_PLACEHOLDER_API_KEYS = frozenset(
    {"", "your-openai-api-key-here", "CHANGE_ME", "sk-your-api-key-here"}
)
_PLACEHOLDER_BASE_URLS = frozenset({"", "https://your-api-base-url.example/v1"})


def _resolve_openai_api_key(config_value: str | None) -> str:
    env_value = os.environ.get("OPENAI_API_KEY")
    if env_value:
        return env_value
    if config_value and config_value not in _PLACEHOLDER_API_KEYS:
        return config_value
    raise RagConfigError(
        "OpenAI api_key is missing for embeddings. Set OPENAI_API_KEY or cognition.openai.api_key."
    )


def _resolve_openai_base_url(config_value: str | None) -> str | None:
    env_value = os.environ.get("OPENAI_BASE_URL")
    if env_value:
        return env_value
    if config_value and config_value not in _PLACEHOLDER_BASE_URLS:
        return config_value
    return None


class ChromaRagStore:
    """Chroma 持久化向量库：写入文档与相似度检索。"""

    def __init__(
        self,
        vectorstore: Chroma,
        *,
        top_k: int = 5,
        score_threshold: float | None = None,
    ) -> None:
        self.vectorstore = vectorstore
        self.top_k = top_k
        self.score_threshold = score_threshold

    @classmethod
    def from_config(
        cls,
        rag_cfg: Dict[str, Any],
        *,
        stage_cfg: Dict[str, Any],
    ) -> "ChromaRagStore":
        backend_cfg = rag_cfg.get("chroma", {})
        if not isinstance(backend_cfg, dict):
            raise RagConfigError("rag.chroma must be a mapping")

        persist_directory = backend_cfg.get("persist_directory", "data/chroma")
        collection_name = backend_cfg.get("collection_name", "doc_generation")
        top_k = int(backend_cfg.get("top_k", 5))
        score_threshold = backend_cfg.get("score_threshold")
        if score_threshold is not None:
            score_threshold = float(score_threshold)

        embedding_model = backend_cfg.get("embedding_model", "text-embedding-3-small")
        openai_cfg = (stage_cfg.get("cognition") or {}).get("openai") or {}
        api_key = _resolve_openai_api_key(openai_cfg.get("api_key"))
        base_url = _resolve_openai_base_url(openai_cfg.get("base_url"))
        embedding_kwargs: Dict[str, Any] = {
            "model": embedding_model,
            "api_key": api_key,
        }
        if base_url:
            embedding_kwargs["base_url"] = base_url

        embeddings = OpenAIEmbeddings(**embedding_kwargs)
        persist_path = Path(persist_directory)
        persist_path.mkdir(parents=True, exist_ok=True)

        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=str(persist_path),
        )
        return cls(
            vectorstore,
            top_k=top_k,
            score_threshold=score_threshold,
        )

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filter: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """相似度检索，返回带 score 的片段列表。"""
        k = top_k if top_k is not None else self.top_k
        pairs = self.vectorstore.similarity_search_with_score(
            query,
            k=k,
            filter=filter,
        )

        results: List[Dict[str, Any]] = []
        for doc, score in pairs:
            if self.score_threshold is not None and score > self.score_threshold:
                continue
            results.append(
                {
                    "content": doc.page_content,
                    "metadata": dict(doc.metadata or {}),
                    "score": float(score),
                }
            )
        return results

    def add_texts(
        self,
        texts: Sequence[str],
        *,
        metadatas: Sequence[Dict[str, Any]] | None = None,
        ids: Sequence[str] | None = None,
    ) -> List[str]:
        """向向量库追加纯文本。"""
        return self.vectorstore.add_texts(list(texts), metadatas=metadatas, ids=ids)

    def add_documents(self, documents: Iterable[Document]) -> List[str]:
        """向向量库追加 LangChain Document。"""
        return self.vectorstore.add_documents(list(documents))

    def ingest_paths(
        self,
        paths: Sequence[str | os.PathLike[str]],
        *,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        encoding: str = "utf-8",
    ) -> int:
        """从文件路径读取、分块并写入向量库。返回写入的 chunk 数量。"""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        documents: List[Document] = []

        for raw_path in paths:
            path = Path(raw_path)
            if not path.is_file():
                logger.warning("Skipping non-file path: %s", path)
                continue
            text = path.read_text(encoding=encoding)
            source = str(path.resolve())
            for chunk in splitter.split_text(text):
                documents.append(
                    Document(
                        page_content=chunk,
                        metadata={"source": source, "filename": path.name},
                    )
                )

        if not documents:
            return 0

        self.add_documents(documents)
        logger.info("Ingested %d chunks from %d paths", len(documents), len(paths))
        return len(documents)
