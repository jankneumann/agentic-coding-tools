"""Content invariants for the parallel-review-implementation skill."""
from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "parallel-review-implementation"


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


def test_skill_references_5_axis_schema():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "Five-Axis" in text or "5-axis" in text or "axis" in text.lower(), \
        "Skill must reference the 5-axis review schema"
    for severity in ("Critical", "Nit", "Optional", "FYI"):
        assert severity in text, f"Severity prefix {severity!r} must be documented"
