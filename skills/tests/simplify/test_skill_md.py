"""Content invariants for the simplify skill."""
from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "simplify"


def test_frontmatter_parses():
    assert_frontmatter_parses(SKILL_DIR)


def test_required_keys_present():
    assert_required_keys_present(SKILL_DIR)


def test_references_resolve():
    assert_references_resolve(SKILL_DIR)


def test_related_resolve():
    assert_related_resolve(SKILL_DIR)


def test_tail_block_present():
    assert_tail_block_present(SKILL_DIR)


def test_simplify_has_chestertons_fence_and_rule_of_500():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "Chesterton" in text, "simplify must reference Chesterton's Fence"
    assert "Rule of 500" in text, "simplify must reference Rule of 500"
