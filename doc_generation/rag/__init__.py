#***********************************************
#      Filename: __init__.py
#   Description: RAG 向量库（Chroma）
#***********************************************

from doc_generation.rag.errors import RagConfigError
from doc_generation.rag.factory import (
    clear_rag_cache,
    get_rag_defaults,
    get_rag_store,
    is_rag_enabled,
)
from doc_generation.rag.chroma_store import ChromaRagStore
from doc_generation.rag.format import format_rag_output

__all__ = [
    "format_rag_output",
    "ChromaRagStore",
    "RagConfigError",
    "clear_rag_cache",
    "get_rag_defaults",
    "get_rag_store",
    "is_rag_enabled",
]
