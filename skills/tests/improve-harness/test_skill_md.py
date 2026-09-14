"""Content invariants for the improve-harness skill."""

from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "improve-harness"


def test_frontmatter_parses():
    assert_frontmatter_parses(SKILL_DIR)


def test_required_keys_present():
    assert_required_keys_present(SKILL_DIR)


def test_references_resolve():
    assert_references_resolve(SKILL_DIR)


def test_related_resolve():
    assert_related_resolve(SKILL_DIR)


def test_candidate_work_sidecar_is_documented():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "--candidate-work-output" in text
    assert "improve-harness-candidate-work.json" in text
