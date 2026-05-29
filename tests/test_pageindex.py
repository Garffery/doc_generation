"""
PageIndex 包集成测试
测试 Markdown 文档的解析、树结构构建、以及 Client 基本功能
"""
import os
import sys
import json
import asyncio
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from doc_generation.pageindex.page_index_md import (
    extract_nodes_from_markdown,
    extract_node_text_content,
    build_tree_from_nodes,
    clean_tree_for_output,
    update_node_list_with_text_token_count,
    tree_thinning_for_index,
    md_to_tree,
)
from doc_generation.pageindex.utils import (
    ConfigLoader,
    count_tokens,
    extract_json,
    write_node_id,
    list_to_tree,
    post_processing,
    format_structure,
    remove_fields,
    structure_to_list,
    get_nodes,
)
from doc_generation.pageindex.retrieve import (
    get_document,
    get_document_structure,
    get_page_content,
)

TEST_MD = os.path.join(
    os.path.dirname(__file__),
    "..",
    "skills",
    "public",
    "erlang-player-data-storage",
    "SKILL.md",
)


# ─── utils 模块测试 ───────────────────────────────────────────────────────────


class TestConfigLoader:
    def test_load_default(self):
        loader = ConfigLoader()
        opt = loader.load()
        assert hasattr(opt, "model")
        assert hasattr(opt, "toc_check_page_num")
        assert hasattr(opt, "max_page_num_each_node")
        assert hasattr(opt, "max_token_num_each_node")

    def test_load_with_overrides(self):
        loader = ConfigLoader()
        opt = loader.load({"model": "gpt-4o"})
        assert opt.model == "gpt-4o"

    def test_load_rejects_unknown_keys(self):
        loader = ConfigLoader()
        with pytest.raises(ValueError, match="Unknown config keys"):
            loader.load({"nonexistent_key": "value"})


class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0
        assert count_tokens(None) == 0

    def test_nonempty_string(self):
        tokens = count_tokens("Hello, world!")
        assert tokens > 0


class TestExtractJson:
    def test_plain_json(self):
        result = extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_code_block(self):
        text = '```json\n{"answer": "yes"}\n```'
        result = extract_json(text)
        assert result == {"answer": "yes"}

    def test_invalid_json(self):
        result = extract_json("not json at all")
        assert result == {}


class TestWriteNodeId:
    def test_assigns_ids(self):
        tree = [
            {"title": "A", "nodes": [{"title": "A1", "nodes": []}]},
            {"title": "B", "nodes": []},
        ]
        write_node_id(tree)
        assert tree[0]["node_id"] == "0000"
        assert tree[0]["nodes"][0]["node_id"] == "0001"
        assert tree[1]["node_id"] == "0002"


class TestListToTree:
    def test_flat_list(self):
        data = [
            {"structure": "1", "title": "Intro", "start_index": 1, "end_index": 5},
            {"structure": "2", "title": "Body", "start_index": 6, "end_index": 10},
        ]
        tree = list_to_tree(data)
        assert len(tree) == 2
        assert tree[0]["title"] == "Intro"

    def test_nested_list(self):
        data = [
            {"structure": "1", "title": "Chapter 1", "start_index": 1, "end_index": 10},
            {"structure": "1.1", "title": "Section 1.1", "start_index": 2, "end_index": 5},
            {"structure": "1.2", "title": "Section 1.2", "start_index": 6, "end_index": 10},
            {"structure": "2", "title": "Chapter 2", "start_index": 11, "end_index": 20},
        ]
        tree = list_to_tree(data)
        assert len(tree) == 2
        assert len(tree[0]["nodes"]) == 2
        assert tree[0]["nodes"][0]["title"] == "Section 1.1"


class TestFormatStructure:
    def test_reorders_keys(self):
        data = {"start_index": 1, "title": "Test", "end_index": 5, "node_id": "0001"}
        result = format_structure(data, order=["title", "node_id", "start_index", "end_index"])
        keys = list(result.keys())
        assert keys == ["title", "node_id", "start_index", "end_index"]


class TestRemoveFields:
    def test_removes_text(self):
        data = [{"title": "A", "text": "long content", "nodes": [{"title": "B", "text": "more"}]}]
        result = remove_fields(data, fields=["text"])
        assert "text" not in result[0]
        assert "text" not in result[0]["nodes"][0]


# ─── page_index_md 模块测试 ───────────────────────────────────────────────────


class TestExtractNodesFromMarkdown:
    def test_basic_extraction(self):
        md = "# Title\n\nSome text\n\n## Section 1\n\nContent\n\n## Section 2\n\nMore"
        nodes, lines = extract_nodes_from_markdown(md)
        assert len(nodes) == 3
        assert nodes[0]["node_title"] == "Title"
        assert nodes[1]["node_title"] == "Section 1"
        assert nodes[2]["node_title"] == "Section 2"

    def test_ignores_headers_in_code_blocks(self):
        md = "# Real Title\n\n```\n# Not a title\n```\n\n## Real Section\n"
        nodes, lines = extract_nodes_from_markdown(md)
        titles = [n["node_title"] for n in nodes]
        assert "Not a title" not in titles
        assert "Real Title" in titles
        assert "Real Section" in titles

    def test_with_real_file(self):
        if not os.path.exists(TEST_MD):
            pytest.skip("Test MD file not found")
        with open(TEST_MD, "r", encoding="utf-8") as f:
            content = f.read()
        nodes, lines = extract_nodes_from_markdown(content)
        assert len(nodes) > 0
        assert all("node_title" in n and "line_num" in n for n in nodes)


class TestExtractNodeTextContent:
    def test_text_assignment(self):
        md = "# Title\n\nParagraph 1\n\n## Section\n\nParagraph 2\n"
        nodes, lines = extract_nodes_from_markdown(md)
        nodes_with_text = extract_node_text_content(nodes, lines)
        assert len(nodes_with_text) == 2
        assert "Paragraph 1" in nodes_with_text[0]["text"]
        assert "Paragraph 2" in nodes_with_text[1]["text"]


class TestBuildTreeFromNodes:
    def test_builds_hierarchy(self):
        nodes = [
            {"title": "Chapter", "level": 1, "text": "ch text", "line_num": 1},
            {"title": "Section", "level": 2, "text": "sec text", "line_num": 5},
            {"title": "Sub", "level": 3, "text": "sub text", "line_num": 10},
            {"title": "Chapter 2", "level": 1, "text": "ch2 text", "line_num": 15},
        ]
        tree = build_tree_from_nodes(nodes)
        assert len(tree) == 2
        assert tree[0]["title"] == "Chapter"
        assert len(tree[0]["nodes"]) == 1
        assert tree[0]["nodes"][0]["title"] == "Section"
        assert len(tree[0]["nodes"][0]["nodes"]) == 1

    def test_empty_input(self):
        assert build_tree_from_nodes([]) == []


class TestCleanTreeForOutput:
    def test_removes_empty_nodes_key(self):
        tree = [{"title": "A", "node_id": "0001", "text": "t", "line_num": 1, "nodes": []}]
        cleaned = clean_tree_for_output(tree)
        assert "nodes" not in cleaned[0]


# ─── retrieve 模块测试 ────────────────────────────────────────────────────────


class TestRetrieve:
    def setup_method(self):
        self.documents = {
            "doc-1": {
                "doc_name": "Test Doc",
                "doc_description": "A test document",
                "type": "md",
                "line_count": 50,
                "structure": [
                    {"title": "Intro", "node_id": "0001", "line_num": 1, "text": "Hello world", "nodes": [
                        {"title": "Sub", "node_id": "0002", "line_num": 10, "text": "Sub content"}
                    ]},
                ],
            }
        }

    def test_get_document(self):
        result = json.loads(get_document(self.documents, "doc-1"))
        assert result["doc_name"] == "Test Doc"
        assert result["status"] == "completed"
        assert result["line_count"] == 50

    def test_get_document_not_found(self):
        result = json.loads(get_document(self.documents, "nonexistent"))
        assert "error" in result

    def test_get_document_structure(self):
        result = json.loads(get_document_structure(self.documents, "doc-1"))
        assert isinstance(result, list)
        assert "text" not in json.dumps(result)

    def test_get_page_content_md(self):
        result = json.loads(get_page_content(self.documents, "doc-1", "1-10"))
        assert isinstance(result, list)
        assert any(item["content"] == "Hello world" for item in result)

    def test_get_page_content_invalid_format(self):
        result = json.loads(get_page_content(self.documents, "doc-1", "abc"))
        assert "error" in result


# ─── md_to_tree 端到端测试（不调用 LLM）─────────────────────────────────────────


class TestMdToTreeNoLLM:
    """测试 md_to_tree 在不需要 LLM 的模式下能正常执行"""

    def test_basic_md_to_tree(self):
        if not os.path.exists(TEST_MD):
            pytest.skip("Test MD file not found")
        result = asyncio.run(
            md_to_tree(
                md_path=TEST_MD,
                if_thinning=False,
                if_add_node_summary="no",
                if_add_node_text="yes",
                if_add_node_id="yes",
                model=None,
            )
        )
        assert "doc_name" in result
        assert "structure" in result
        assert isinstance(result["structure"], list)
        assert len(result["structure"]) > 0

    def test_md_to_tree_structure_has_node_ids(self):
        if not os.path.exists(TEST_MD):
            pytest.skip("Test MD file not found")
        result = asyncio.run(
            md_to_tree(
                md_path=TEST_MD,
                if_thinning=False,
                if_add_node_summary="no",
                if_add_node_text="no",
                if_add_node_id="yes",
                model=None,
            )
        )
        nodes = structure_to_list(result["structure"])
        assert all("node_id" in n for n in nodes)

    def test_md_to_tree_with_text(self):
        if not os.path.exists(TEST_MD):
            pytest.skip("Test MD file not found")
        result = asyncio.run(
            md_to_tree(
                md_path=TEST_MD,
                if_thinning=False,
                if_add_node_summary="no",
                if_add_node_text="yes",
                if_add_node_id="yes",
                model=None,
            )
        )
        nodes = structure_to_list(result["structure"])
        assert all("text" in n for n in nodes)
        assert any(len(n["text"]) > 0 for n in nodes)


# ─── PageIndexClient 基本初始化测试 ──────────────────────────────────────────


class TestPageIndexClientInit:
    def test_import(self):
        from doc_generation.pageindex.client import PageIndexClient
        assert PageIndexClient is not None

    def test_init_without_workspace(self):
        from doc_generation.pageindex.client import PageIndexClient
        client = PageIndexClient(api_key="test-key", model="gpt-4o")
        assert client.model == "gpt-4o"
        assert client.documents == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
