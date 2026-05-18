from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

from doc_generation.skills.parser import parse_skill_file
from doc_generation.skills.types import SKILL_MD_FILE, Skill, SkillCategory

logger = logging.getLogger(__name__)

_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillStorage(ABC):
    """Abstract skill storage; subclasses implement medium-specific operations."""

    @staticmethod
    def validate_skill_name(name: str) -> str:
        normalized = name.strip()
        if not _SKILL_NAME_PATTERN.fullmatch(normalized):
            raise ValueError(
                "Skill name must be hyphen-case using lowercase letters, digits, and hyphens only."
            )
        if len(normalized) > 64:
            raise ValueError("Skill name must be 64 characters or fewer.")
        return normalized

    @abstractmethod
    def get_skills_root_path(self) -> Path:
        """Absolute path to the skills root directory."""

    @abstractmethod
    def _iter_skill_files(self) -> Iterable[tuple[SkillCategory, Path, Path]]:
        """Yield (category, category_root, skill_md_path) for every SKILL.md."""

    def load_skills(self, *, enabled_names: set[str] | None = None) -> list[Skill]:
        """Discover skills, apply enabled filter, prefer custom over public on name clash."""
        skills_by_name: dict[str, Skill] = {}
        for category, category_root, md_path in self._iter_skill_files():
            skill = parse_skill_file(
                md_path,
                category=category,
                relative_path=md_path.parent.relative_to(category_root),
            )
            if not skill:
                continue
            existing = skills_by_name.get(skill.name)
            if existing is None or (
                existing.category == SkillCategory.PUBLIC and skill.category == SkillCategory.CUSTOM
            ):
                skills_by_name[skill.name] = skill

        skills = list(skills_by_name.values())
        if enabled_names is not None:
            skills = [s for s in skills if s.name in enabled_names]
            for skill in skills:
                skill.enabled = True
        else:
            for skill in skills:
                skill.enabled = True

        skills.sort(key=lambda s: s.name)
        return skills

    def read_skill_content(self, skill: Skill) -> str:
        from doc_generation.skills.parser import read_skill_body

        return read_skill_body(skill.skill_file)
