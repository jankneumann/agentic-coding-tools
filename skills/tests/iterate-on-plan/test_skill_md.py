"""Content invariants for the iterate-on-plan skill."""

from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "iterate-on-plan"


def test_frontmatter_parses():
    assert_frontmatter_parses(SKILL_DIR)


def test_required_keys_present():
    assert_required_keys_present(SKILL_DIR)


def test_references_resolve():
    assert_references_resolve(SKILL_DIR)


def test_related_resolve():
    assert_related_resolve(SKILL_DIR)


def test_plan_iteration_writes_run_in_worktree():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "worktree.py" in text
    assert "checkout_policy.py" in text
    assert "MUST NOT commit directly to local main" in text
