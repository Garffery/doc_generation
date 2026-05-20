#***********************************************
#      Filename: format.py
#   Description: RAG 检索结果格式化
#***********************************************

from __future__ import annotations

from typing import List


def format_rag_output(results: List[dict]) -> str:
    """将检索结果格式化为 agent 可读的文本。"""
    if not results:
        return (
            "No relevant documents found in the knowledge base. "
            "Try a different query or ingest more source documents."
        )

    formatted = "Knowledge base results:\n\n"
    for index, item in enumerate(results, 1):
        metadata = item.get("metadata") or {}
        source = metadata.get("source") or metadata.get("filename") or "unknown"
        score = item.get("score")
        formatted += f"--- CHUNK {index} (source: {source}"
        if score is not None:
            formatted += f", score: {score:.4f}"
        formatted += ") ---\n"
        formatted += f"{item.get('content', '')}\n\n"
        formatted += "-" * 80 + "\n"
    return formatted
