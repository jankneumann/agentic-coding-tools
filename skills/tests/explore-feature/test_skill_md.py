"""Content invariants for the explore-feature skill."""
from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "explore-feature"


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


def test_explore_feature_has_how_might_we():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "How Might We" in text or "how might we" in text.lower()
    assert "NOT DOING" in text, "explore-feature must reference NOT DOING list"
