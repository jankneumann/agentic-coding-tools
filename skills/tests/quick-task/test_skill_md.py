"""Content invariants for the quick-task skill."""

from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "quick-task"


def test_frontmatter_parses():
    assert_frontmatter_parses(SKILL_DIR)


def test_required_keys_present():
    assert_required_keys_present(SKILL_DIR)


def test_references_resolve():
    assert_references_resolve(SKILL_DIR)


def test_related_resolve():
    assert_related_resolve(SKILL_DIR)


def test_quick_task_default_is_read_only_unless_isolated():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "read-only by default" in text.lower()
    assert "worktree.py" in text
    assert "checkout_policy.py" in text
    assert "read-write, no worktree isolation" not in text
