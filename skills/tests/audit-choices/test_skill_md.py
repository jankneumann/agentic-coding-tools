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


def _section(text: str, heading: str) -> str:
    """Return the body of one `## <heading>` section, up to the next `##`."""
    start = text.index(f"## {heading}")
    rest = text[start:]
    next_heading = rest.find("\n## ", 1)
    return rest if next_heading == -1 else rest[:next_heading]


def _paragraph_containing(text: str, needle: str) -> str:
    """Return the blank-line-delimited paragraph containing `needle`."""
    idx = text.index(needle)
    start = text.rfind("\n\n", 0, idx)
    end = text.find("\n\n", idx)
    return text[start:] if end == -1 else text[start:end]


def test_read_only_contract_names_the_range_form_destinations():
    text = (SKILL_DIR / "SKILL.md").read_text()
    contract_paragraph = _paragraph_containing(text, "MUST NOT modify any file outside")
    assert "openspec/choices/" in contract_paragraph
    assert "openspec/choices/archive/" in contract_paragraph


def test_red_flags_bullet_names_the_range_form_destinations():
    text = (SKILL_DIR / "SKILL.md").read_text()
    red_flags = _section(text, "Red Flags")
    bullet = _paragraph_containing(red_flags, "the read-only contract has been violated")
    assert "openspec/choices/" in bullet
    assert "openspec/choices/archive/" in bullet


def test_output_section_lists_the_range_form_destination():
    text = (SKILL_DIR / "SKILL.md").read_text()
    output_section = _section(text, "Output")
    assert "openspec/choices/" in output_section
    assert "openspec/choices/archive/" in output_section
