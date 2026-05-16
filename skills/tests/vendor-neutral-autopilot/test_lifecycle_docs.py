from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

LIFECYCLE_SKILLS = [
    "autopilot",
    "plan-feature",
    "implement-feature",
    "iterate-on-plan",
    "iterate-on-implementation",
    "parallel-review-plan",
    "parallel-review-implementation",
    "validate-feature",
]


def test_lifecycle_skills_name_provider_neutral_dispatch() -> None:
    for skill in LIFECYCLE_SKILLS:
        text = (ROOT / "skills" / skill / "SKILL.md").read_text()
        assert "provider-neutral" in text.lower(), skill
        assert "dispatch adapter" in text.lower(), skill


def test_agent_tool_references_are_labeled_as_provider_specific_examples() -> None:
    for skill in LIFECYCLE_SKILLS:
        text = (ROOT / "skills" / skill / "SKILL.md").read_text()
        if "Agent(...)" not in text and "Agent tool" not in text:
            continue
        lowered = text.lower()
        assert "claude" in lowered or "provider-specific" in lowered, skill
