"""Content invariants for the audit-choices skill."""
from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "audit-choices"


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


def test_skill_states_read_only_contract():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "read-only" in text.lower() or "read only" in text.lower()
    assert "MUST NOT modify" in text or "must not modify" in text.lower()


def test_skill_states_never_blocks_rule():
    text = (SKILL_DIR / "SKILL.md").read_text().lower()
    assert "exit" in text and "0" in text
    assert "never block" in text or "does not block" in text or "non-blocking" in text


def test_skill_names_independent_auditor_dispatch():
    text = (SKILL_DIR / "SKILL.md").read_text().lower()
    assert "independent" in text
    assert "sub-agent" in text or "subagent" in text
