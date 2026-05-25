#***********************************************
#      Filename: test_rag_tool.py
#   Description: RAG 工具与格式化测试
#***********************************************

from doc_generation.rag.format import format_rag_output


def test_format_rag_output_empty():
    text = format_rag_output([])
    assert "No relevant documents" in text


def test_format_rag_output_with_chunks():
    text = format_rag_output(
        [
            {
                "content": "Hello protocol",
                "metadata": {"source": "/docs/proto.md"},
                "score": 0.12,
            }
        ]
    )
    assert "Knowledge base results" in text
    assert "Hello protocol" in text
    assert "proto.md" in text
