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
