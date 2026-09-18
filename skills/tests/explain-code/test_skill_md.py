"""Content invariants for the explain-code skill (add-visual-code-explainer)."""

from __future__ import annotations

from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "explain-code"


def test_frontmatter_parses():
    assert_frontmatter_parses(SKILL_DIR)


def test_required_keys_explicit_without_triggers():
    """Assert keys directly — do not call assert_required_keys_present (still requires triggers)."""
    fm = assert_frontmatter_parses(SKILL_DIR)
    for key in ("name", "description", "category", "tags", "user_invocable", "related"):
        assert fm.get(key) not in (None, "", []), f"missing or empty frontmatter key: {key}"
    assert fm["name"] == "explain-code"
    assert fm["category"] == "Architecture"
    assert fm["user_invocable"] is True
    related = fm["related"]
    assert isinstance(related, list)
    assert "codebase-atlas" in related
    assert "refresh-architecture" in related
    assert "triggers" not in fm


def test_description_mentions_codebase_atlas():
    fm = assert_frontmatter_parses(SKILL_DIR)
    assert "codebase-atlas" in fm["description"]


def test_references_resolve():
    assert_references_resolve(SKILL_DIR)


def test_related_resolve():
    assert_related_resolve(SKILL_DIR)


def test_tail_block_present():
    assert_tail_block_present(SKILL_DIR)


def test_skill_md_line_budget():
    lines = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 150, f"SKILL.md has {len(lines)} lines (cap 150)"


def test_references_do_not_link_to_other_references():
    refs = SKILL_DIR / "references"
    for path in sorted(refs.glob("*.md")):
        body = path.read_text(encoding="utf-8")
        # Allow mentioning grounding.md from SKILL only; form refs must not nest.
        assert "references/" not in body, f"{path.name} must not link to another reference"
