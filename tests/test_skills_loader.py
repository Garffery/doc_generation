from pathlib import Path

from doc_generation.skills.config import SkillsConfig
from doc_generation.skills.prompt import build_skills_context
from doc_generation.skills.registry import get_or_new_skill_storage, reset_skill_storage


def _write_skill(skill_dir: Path, name: str, description: str, body: str = "# Body") -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def test_load_skills_discovers_nested_skills(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(skills_root / "public" / "root-skill", "root-skill", "Root skill")
    _write_skill(skills_root / "public" / "parent" / "child-skill", "child-skill", "Child skill")
    _write_skill(skills_root / "custom" / "team" / "helper", "team-helper", "Team helper")

    skills = get_or_new_skill_storage(skills_path=skills_root).load_skills()
    names = {s.name for s in skills}
    assert {"root-skill", "child-skill", "team-helper"} <= names


def test_load_skills_prefers_custom_over_public(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(skills_root / "public" / "shared-skill", "shared-skill", "Public version")
    _write_skill(skills_root / "custom" / "shared-skill", "shared-skill", "Custom version")

    skills = get_or_new_skill_storage(skills_path=skills_root).load_skills()
    shared = next(s for s in skills if s.name == "shared-skill")
    assert shared.description == "Custom version"


def test_build_skills_context_inline(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(
        skills_root / "public" / "demo-skill",
        "demo-skill",
        "Demo",
        body="## Do this",
    )
    config = SkillsConfig(
        path=str(skills_root),
        mode="inline",
        enabled=["demo-skill"],
        agents={"draft": {"skills": ["demo-skill"]}},
    )
    storage = get_or_new_skill_storage(skills_config=config)
    section = build_skills_context(config, agent="draft", step=None, storage=storage)
    assert "demo-skill" in section
    assert "Do this" in section


def test_pluggable_storage_class(tmp_path: Path) -> None:
    reset_skill_storage()
    skills_root = tmp_path / "skills"
    _write_skill(skills_root / "public" / "x", "x", "X")
    config = SkillsConfig(
        path=str(skills_root),
        use="doc_generation.skills.storage.local_skill_storage:LocalSkillStorage",
    )
    storage = get_or_new_skill_storage(skills_config=config)
    assert storage.get_skills_root_path() == skills_root.resolve()
    assert [s.name for s in storage.load_skills()] == ["x"]
