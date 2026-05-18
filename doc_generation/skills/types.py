from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

SKILL_MD_FILE = "SKILL.md"


class SkillCategory(StrEnum):
    """Skill source category."""

    PUBLIC = "public"
    CUSTOM = "custom"


@dataclass
class Skill:
    """Metadata for a discovered skill."""

    name: str
    description: str
    license: str | None
    skill_dir: Path
    skill_file: Path
    relative_path: Path
    category: SkillCategory
    allowed_tools: list[str] | None = None
    enabled: bool = True

    @property
    def skill_path(self) -> str:
        path = self.relative_path.as_posix()
        return "" if path == "." else path

    def get_skill_file_path(self, skills_root: Path) -> str:
        """Absolute path to this skill's SKILL.md."""
        return str(self.skill_file if self.skill_file.is_absolute() else skills_root / self.category / self.skill_path / SKILL_MD_FILE)

    def __repr__(self) -> str:
        return f"Skill(name={self.name!r}, category={self.category!r})"
