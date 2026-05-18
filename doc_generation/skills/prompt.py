from __future__ import annotations

import logging

from doc_generation.skills.config import SkillsConfig
from doc_generation.skills.registry import get_or_new_skill_storage
from doc_generation.skills.storage import SkillStorage
from doc_generation.skills.types import Skill, SkillCategory

logger = logging.getLogger(__name__)


def _skill_mutability_label(category: SkillCategory | str) -> str:
    return "[custom, editable]" if category == SkillCategory.CUSTOM else "[built-in]"


def _filter_skills(
    skills: list[Skill],
    available_skills: set[str] | None,
) -> list[Skill]:
    if available_skills is None:
        return skills
    return [s for s in skills if s.name in available_skills]


def get_skills_catalog_section(
    skills: list[Skill],
    *,
    skills_root: str,
    available_skills: set[str] | None = None,
) -> str:
    """Deer-flow style catalog: list skills and paths for progressive loading."""
    filtered = _filter_skills(skills, available_skills)
    if not filtered:
        return ""

    lines = []
    for skill in filtered:
        lines.append(
            f"  <skill>\n"
            f"    <name>{skill.name}</name>\n"
            f"    <description>{skill.description}</description>\n"
            f"    <category>{_skill_mutability_label(skill.category)}</category>\n"
            f"    <path>{skill.skill_file}</path>\n"
            f"  </skill>"
        )

    return f"""
<skills>
You have access to skills that provide optimized workflows for specific tasks.

**Progressive loading:**
1. When the task matches a skill, read that skill's SKILL.md at the path below.
2. Follow the skill instructions precisely.
3. Load references/scripts under the skill folder only when needed.

**Skills root:** {skills_root}
{chr(10).join(lines)}
</skills>
"""


def get_skills_inline_section(
    skills: list[Skill],
    storage: SkillStorage,
    *,
    available_skills: set[str] | None = None,
) -> str:
    """Inject full skill instructions into the prompt (for tool-less LLM nodes)."""
    filtered = _filter_skills(skills, available_skills)
    if not filtered:
        return ""

    blocks: list[str] = []
    for skill in filtered:
        try:
            body = storage.read_skill_content(skill)
        except OSError as exc:
            logger.warning("Failed to read skill %s: %s", skill.name, exc)
            continue
        blocks.append(
            f'<skill name="{skill.name}" category="{_skill_mutability_label(skill.category)}">\n'
            f"{body}\n"
            f"</skill>"
        )

    if not blocks:
        return ""

    return (
        "<skills>\n"
        "Apply the following skill instructions when they match the current task.\n"
        + "\n\n".join(blocks)
        + "\n</skills>\n"
    )


def build_skills_context(
    skills_config: SkillsConfig,
    *,
    agent: str,
    step: str | None = None,
    storage: SkillStorage | None = None,
) -> str:
    """Build skills prompt block for an agent workflow step."""
    storage = storage or get_or_new_skill_storage(skills_config=skills_config)
    enabled_names = skills_config.get_enabled_names()
    all_skills = storage.load_skills(enabled_names=enabled_names)

    agent_skills = skills_config.get_agent_skills(agent, step)
    if agent_skills is not None and not agent_skills:
        return ""

    if skills_config.mode == "catalog":
        return get_skills_catalog_section(
            all_skills,
            skills_root=str(storage.get_skills_root_path()),
            available_skills=agent_skills,
        )

    return get_skills_inline_section(
        all_skills,
        storage,
        available_skills=agent_skills,
    )
