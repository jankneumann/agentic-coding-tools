"""Content invariants for the refine-roadmap workflow skill."""

from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

SKILL = Path(__file__).resolve().parents[2] / "refine-roadmap"


def test_frontmatter_and_references_are_valid():
    assert_frontmatter_parses(SKILL)
    assert_required_keys_present(SKILL)
    assert_references_resolve(SKILL)
    assert_related_resolve(SKILL)


def test_user_invocable_tail_contract_is_present():
    assert_tail_block_present(SKILL)


def test_skill_requires_preview_before_apply_and_atomic_commit():
    body = (SKILL / "SKILL.md").read_text()
    assert "preview" in body.lower()
    assert "strict OpenSpec" in body
    assert "single atomic commit" in body
    assert "checkpoint" in body.lower()
    assert "learning" in body.lower()
