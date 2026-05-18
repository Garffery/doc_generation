from __future__ import annotations

import importlib
from typing import Type

from doc_generation.skills.config import SkillsConfig
from doc_generation.skills.storage import SkillStorage

_default_skill_storage: SkillStorage | None = None
_default_skills_config: SkillsConfig | None = None


def resolve_class(class_path: str, base_class: type) -> Type:
    module_path, class_name = class_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    if not isinstance(cls, type) or not issubclass(cls, base_class):
        raise TypeError(f"{class_path} is not a subclass of {base_class.__name__}")
    return cls


def _make_storage(skills_config: SkillsConfig, *, host_path: str | Path | None = None) -> SkillStorage:
    cls = resolve_class(skills_config.use, SkillStorage)
    resolved_path = host_path if host_path is not None else skills_config.get_skills_path()
    return cls(host_path=str(resolved_path))


def get_or_new_skill_storage(
    *,
    skills_config: SkillsConfig | None = None,
    skills_path: str | Path | None = None,
) -> SkillStorage:
    """Return skill storage — singleton by default, or a fresh instance when overridden."""
    global _default_skill_storage, _default_skills_config

    if skills_path is not None:
        config = skills_config or SkillsConfig()
        return _make_storage(config, host_path=skills_path)

    if skills_config is not None:
        return _make_storage(skills_config)

    config = SkillsConfig()
    if _default_skill_storage is None or _default_skills_config != config:
        _default_skill_storage = _make_storage(config)
        _default_skills_config = config
    return _default_skill_storage


def reset_skill_storage() -> None:
    global _default_skill_storage, _default_skills_config
    _default_skill_storage = None
    _default_skills_config = None


def load_skills_config_from_stage(stage_cfg: dict) -> SkillsConfig:
    return SkillsConfig.from_dict(stage_cfg.get("skills"))
