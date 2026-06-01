#***********************************************
#      Filename: utils.py
#   Description: 工具函数库
#***********************************************

import os
import yaml
from pathlib import Path
from datetime import datetime


# ===== UTILITY FUNCTIONS =====

def get_today_str() -> str:
    """获取今天的日期并返回格式化的字符串"""
    now = datetime.now()
    return now.strftime(f"%a %b {now.day}, %Y")

def get_current_dir() -> Path:
    """获取当前的目录"""
    try:
        return Path(__file__).resolve().parent
    except NameError:
        return Path.cwd()


def load_dotenv_if_present(path: str | os.PathLike[str] | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file without overriding existing env vars."""
    env_path = Path(path) if path is not None else Path.cwd() / ".env"
    if not env_path.is_file():
        return

    with open(env_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


# ===== CONFIG LOADER =====

def get_config_yml(path, section_name, subsection_name=None):
    """读取yaml文件"""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")

    with open(path, encoding="utf8") as f:
        data = yaml.safe_load(f)
        try:
            return (
                data[section_name]
                if subsection_name is None
                else data[section_name][subsection_name]
            )
        except KeyError as e:
            raise KeyError(
                f"No such section or subsection in config file: {section_name}, {subsection_name}. Config file: {path}"
            ) from e


def load_config(stage_name=None, config_path=None):
    """加载配置"""
    return get_config_yml(
        path=config_path, section_name="stages", subsection_name=stage_name
    )


def sanitize_tool_messages(messages: list) -> list:
    """确保每条带 tool_calls 的 assistant message 都有对应的 ToolMessage。
    对于缺少部分 tool response 的 assistant message，移除未应答的 tool_calls；
    如果全部 tool_calls 都缺少应答，则移除整条 AI message。"""
    from langchain_core.messages import ToolMessage, AIMessage

    if not messages:
        return messages

    all_tool_msg_ids = {
        msg.tool_call_id for msg in messages if isinstance(msg, ToolMessage)
    }

    orphan_ids: set[str] = set()
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            continue
        required_ids = {tc["id"] for tc in tool_calls}
        missing = required_ids - all_tool_msg_ids
        if missing:
            orphan_ids.update(missing)

    if not orphan_ids:
        return messages

    result = []
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            kept_calls = [tc for tc in msg.tool_calls if tc["id"] not in orphan_ids]
            if not kept_calls:
                continue
            msg = msg.model_copy(update={"tool_calls": kept_calls})
        if isinstance(msg, ToolMessage) and msg.tool_call_id in orphan_ids:
            continue
        result.append(msg)

    return result
