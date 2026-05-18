from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from doc_generation.utils import get_current_dir


def _project_root() -> Path:
    """Project root (parent of the ``doc_generation`` package directory)."""
    return get_current_dir().parent


@dataclass
class SkillsConfig:
    """Skills system configuration (from stage config or defaults)."""

    use: str = "doc_generation.skills.storage.local_skill_storage:LocalSkillStorage"
    path: str | None = None
    enabled: list[str] | None = None
    mode: str = "inline"
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SkillsConfig:
        if not raw:
            return cls()
        return cls(
            use=raw.get("use", cls.use),
            path=raw.get("path"),
            enabled=raw.get("enabled"),
            mode=raw.get("mode", "inline"),
            agents=raw.get("agents") or {},
        )

    def get_skills_path(self) -> Path:
        if self.path:
            path = Path(self.path)
            if not path.is_absolute():
                path = _project_root() / path
            return path.resolve()
        if env_path := os.getenv("DOC_GENERATION_SKILLS_PATH"):
            return Path(env_path).resolve()
        project_default = _project_root() / "skills"
        return project_default.resolve()

    def get_enabled_names(self) -> set[str] | None:
        if self.enabled is None:
            return None
        return set(self.enabled)

    def get_agent_skills(self, agent: str, step: str | None = None) -> set[str] | None:
        """Return skill whitelist for an agent/step. None means all enabled skills."""
        agent_cfg = self.agents.get(agent) or {}
        skills = None
        if step and step in agent_cfg:
            step_cfg = agent_cfg[step]
            if isinstance(step_cfg, dict):
                skills = step_cfg.get("skills")
            else:
                skills = step_cfg
        if skills is None:
            skills = agent_cfg.get("skills")
        if skills is None:
            return None
        if isinstance(skills, list):
            return set(skills)
        return set()
