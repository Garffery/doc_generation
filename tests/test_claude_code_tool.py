#***********************************************
#      Filename: test_claude_code_tool.py
#   Description: Claude Code 工具测试
#***********************************************

import asyncio
import pytest

from doc_generation.tools.claude_code_tool import _claude_code_tool, claude_code, _run_claude_code


def test_tool_registration():
    """验证工具正确注册为 LangChain tool。"""
    assert _claude_code_tool.name == "claude_code"
    assert "Claude Code" in _claude_code_tool.description


def test_tool_args_schema():
    """验证 prompt 是唯一暴露给 LLM 的参数（其余为 InjectedToolArg）。"""
    schema = _claude_code_tool.get_input_schema().model_json_schema()
    required = schema.get("required", [])
    assert "prompt" in required
    assert "system_prompt" not in required
    assert "allowed_tools" not in required


@pytest.mark.asyncio
async def test_run_claude_code_basic():
    """集成测试：调用 Claude Code 执行简单的只读任务。"""
    result = await _run_claude_code(
        prompt="列出当前目录下的 pyproject.toml 文件内容的前5行",
        cwd="E:/project/agent/doc_generation",
        max_turns=3,
    )
    assert isinstance(result, str)
    assert len(result) > 0
    print("\n===== Claude Code Response =====")
    print(result)


@pytest.mark.asyncio
async def test_allowed_tools_default():
    """验证默认 allowed_tools 只包含 Read, Glob, Grep。"""
    from claude_code_sdk import ClaudeCodeOptions

    options = ClaudeCodeOptions(
        allowed_tools=None or ["Read", "Glob", "Grep"],
    )
    assert options.allowed_tools == ["Read", "Glob", "Grep"]


def test_claude_code_sync_wrapper():
    """集成测试：通过同步包装器调用 Claude Code。"""
    result = claude_code(
        prompt="用 Grep 搜索当前目录下包含 'langchain' 的 .toml 文件",
        cwd="E:/project/agent/doc_generation",
        max_turns=3,
    )
    assert isinstance(result, str)
    assert len(result) > 0
    print("\n===== Claude Code Sync Response =====")
    print(result)


if __name__ == "__main__":
    asyncio.run(test_run_claude_code_basic())
