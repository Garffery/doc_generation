import logging
import re
from pathlib import Path

import yaml

from doc_generation.skills.types import SKILL_MD_FILE, Skill, SkillCategory

logger = logging.getLogger(__name__)


def parse_allowed_tools(raw: object, skill_file: Path) -> list[str] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError(f"allowed-tools in {skill_file} must be a list of strings")
    allowed_tools: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError(f"allowed-tools in {skill_file} must contain only strings")
        tool_name = item.strip()
        if not tool_name:
            raise ValueError(f"allowed-tools in {skill_file} cannot contain empty tool names")
        allowed_tools.append(tool_name)
    return allowed_tools


def parse_skill_file(
    skill_file: Path,
    category: SkillCategory,
    relative_path: Path | None = None,
) -> Skill | None:
    if not skill_file.exists() or skill_file.name != SKILL_MD_FILE:
        return None

    try:
        content = skill_file.read_text(encoding="utf-8")
        front_matter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not front_matter_match:
            return None

        metadata = yaml.safe_load(front_matter_match.group(1))
        if not isinstance(metadata, dict):
            logger.error("Front-matter in %s is not a YAML mapping", skill_file)
            return None

        name = metadata.get("name")
        description = metadata.get("description")
        if not name or not isinstance(name, str):
            return None
        if not description or not isinstance(description, str):
            return None

        name = name.strip()
        description = description.strip()
        if not name or not description:
            return None

        license_text = metadata.get("license")
        if license_text is not None:
            license_text = str(license_text).strip() or None

        allowed_tools = parse_allowed_tools(metadata.get("allowed-tools"), skill_file)

        return Skill(
            name=name,
            description=description,
            license=license_text,
            skill_dir=skill_file.parent,
            skill_file=skill_file,
            relative_path=relative_path or Path(skill_file.parent.name),
            category=category,
            allowed_tools=allowed_tools,
            enabled=True,
        )
    except Exception:
        logger.exception("Unexpected error parsing skill file %s", skill_file)
        return None


def read_skill_body(skill_file: Path) -> str:
    """Return SKILL.md content without YAML frontmatter."""
    content = skill_file.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n.*?\n---\s*\n", content, re.DOTALL)
    if match:
        return content[match.end() :].strip()
    return content.strip()
