from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from doc_generation.skills.storage.skill_storage import SkillStorage
from doc_generation.skills.types import SKILL_MD_FILE, SkillCategory


class LocalSkillStorage(SkillStorage):
    """Filesystem-backed skill storage.

    Layout::

        skills/
          public/<skill-name>/SKILL.md
          custom/<skill-name>/SKILL.md
    """

    def __init__(self, host_path: str | Path) -> None:
        self._host_root = Path(host_path).resolve()

    def get_skills_root_path(self) -> Path:
        return self._host_root

    def _iter_skill_files(self) -> Iterable[tuple[SkillCategory, Path, Path]]:
        if not self._host_root.exists():
            return
        for category in SkillCategory:
            category_path = self._host_root / category.value
            if not category_path.exists() or not category_path.is_dir():
                continue
            for current_root, dir_names, file_names in os.walk(category_path, followlinks=True):
                dir_names[:] = sorted(name for name in dir_names if not name.startswith("."))
                if SKILL_MD_FILE not in file_names:
                    continue
                yield category, category_path, Path(current_root) / SKILL_MD_FILE
