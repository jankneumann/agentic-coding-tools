"""Seed-suite taxonomy: which skill belongs to which family (design D6)."""

from __future__ import annotations

#: Skill families counted by the seed-suite coverage floor. Unknown skills map to
#: ``other``, which does not count toward coverage.
SKILL_FAMILIES: dict[str, tuple[str, ...]] = {
    "plan": ("plan-feature", "iterate-on-plan"),
    "implement": ("implement-feature", "iterate-on-implementation"),
    "validate": ("validate-feature",),
    "merge": ("merge-pull-requests", "cleanup-feature"),
}

#: Families that must each be covered by at least two scenarios.
REQUIRED_FAMILIES: tuple[str, ...] = tuple(SKILL_FAMILIES)

_SKILL_TO_FAMILY = {
    skill: family for family, skills in SKILL_FAMILIES.items() for skill in skills
}


def skill_family(skill: str) -> str:
    """Return the family of ``skill`` (``other`` when unknown)."""
    return _SKILL_TO_FAMILY.get(skill, "other")


__all__ = ["REQUIRED_FAMILIES", "SKILL_FAMILIES", "skill_family"]
