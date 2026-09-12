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


def _assert_names_all_three_effects(passage: str, label: str) -> None:
    """D6's whole argument for enumerating effects rather than loosening to a
    rule is that the enumeration stays literal and checkable. Three effects
    are permitted on a range run — the run directory's pair, the latest.*
    copies, and retention's archive move — so all three must be named.

    impl-round-2 found the first version asserted only `openspec/choices/`
    and `openspec/choices/archive/`; the first is a substring of the second,
    so it added nothing, and neither mentioned latest.* at all.
    """
    assert "openspec/choices/archive/" in passage, f"{label} omits the archive move"
    assert "latest.json" in passage and "latest.md" in passage, (
        f"{label} omits the latest.* pointers"
    )
    # The run directory itself, distinct from the archive path. Matched on
    # the stem so "run directories" and "that run's ..." both count; an
    # exact "run directory" is too brittle for prose that legitimately
    # pluralises or uses the possessive.
    assert (
        "run director" in passage
        or "run's" in passage
        or "-HHMMSS-" in passage
    ), f"{label} omits the run directory"


def test_read_only_contract_names_the_range_form_destinations():
    text = (SKILL_DIR / "SKILL.md").read_text()
    contract_paragraph = _paragraph_containing(text, "MUST NOT modify any file outside")
    # D6 enumerates three effects, so assert three. Note that
    # `"openspec/choices/" in x` is subsumed by the archive assertion — the
    # archive path contains it — so the run directory is pinned via the
    # `<run-id>` wording instead, and the latest.* pointers by name.
    _assert_names_all_three_effects(contract_paragraph, "Read-Only Contract")


def test_red_flags_bullet_names_the_range_form_destinations():
    text = (SKILL_DIR / "SKILL.md").read_text()
    red_flags = _section(text, "Red Flags")
    bullet = _paragraph_containing(red_flags, "the read-only contract has been violated")
    _assert_names_all_three_effects(bullet, "Red Flags bullet")


def test_output_section_lists_the_range_form_destination():
    text = (SKILL_DIR / "SKILL.md").read_text()
    output_section = _section(text, "Output")
    _assert_names_all_three_effects(output_section, "Output section")
