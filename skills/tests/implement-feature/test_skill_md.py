"""Content invariants for the implement-feature skill."""
from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "implement-feature"


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


def test_implement_feature_has_scope_discipline_template():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "NOTICED BUT NOT TOUCHING:" in text, \
        "implement-feature must contain the scope-discipline template"
    assert "Implementation Rules" in text or "Rules 0" in text, \
        "implement-feature must contain Rules 0-5 framing"
