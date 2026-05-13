"""Content invariants for the cleanup-feature skill."""
from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "cleanup-feature"


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


def test_cleanup_feature_has_staged_rollout():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "Staged Rollout" in text or "staged rollout" in text.lower()
    for marker in ("5%", "25%", "50%", "100%"):
        assert marker in text, f"Staged rollout sequence missing {marker}"
