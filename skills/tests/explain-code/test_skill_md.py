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


# ── Why mode (add-why-mode-to-explain-code-with-epistemic-tiers) ────

TIERS = ("Direct", "Supported", "Inferred", "Speculative", "Unknown")
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "openspec" / "schemas" / "review-findings.schema.json"


def _skill_md() -> str:
    return (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


def _why_md() -> str:
    return (SKILL_DIR / "references" / "why.md").read_text(encoding="utf-8")


def test_why_chain_catalogue_row_links_reference():
    rows = [ln for ln in _skill_md().splitlines() if ln.startswith("| Why chain |")]
    assert len(rows) == 1
    assert "`references/why.md`" in rows[0]


def test_skill_md_names_tiers_rules_and_script():
    body = _skill_md()
    for tier in TIERS:
        assert tier in body, f"SKILL.md must name tier {tier}"
    assert "Null-result rule" in body
    assert "Embedded-hypothesis rule" in body
    assert 'python3 "<skill-base-dir>/scripts/why_trace.py"' in body
    assert "Grounding: source read, unverified (form not graph-backed)" in body


def test_related_includes_explore_feature():
    fm = assert_frontmatter_parses(SKILL_DIR)
    assert "explore-feature" in fm["related"]


def test_why_reference_documents_rules_and_disclosure():
    body = _why_md()
    for heading in ("## Tiers", "## Null-result rule", "## Embedded-hypothesis rule",
                    "## Worked example"):
        assert heading in body
    for verdict in ("confirmed", "contradicted", "untested"):
        assert verdict in body
    assert "mentions_target" in body
    assert "Grounding: source read, unverified (form not graph-backed)" in body


def _why_tiers() -> list[str]:
    section = _why_md().split("## Tiers", 1)[1].split("\n## ", 1)[0]
    tiers = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells[0] not in ("Tier", "") and not set(cells[0]) <= {"-"}:
            tiers.append(cells[0])
    return tiers


def test_why_tier_vocabulary_matches_schema_enum():
    import json

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    props = schema["properties"]["findings"]["items"]["properties"]
    assert [t.lower() for t in _why_tiers()] == props["evidence_level"]["enum"]
    assert _why_tiers() == list(TIERS)


def test_worked_example_tags_follow_the_tier_rules():
    """Every claim sentence in the worked example ends in a tier tag, and its
    Direct decision-to-line claim is backed by a reported mentions_target."""
    import re

    example = _why_md().split("## Worked example", 1)[1].split("\n## ", 1)[0]
    prose = example.split("```text", 1)[1].split("```", 1)[1].split("Grounding:", 1)[0]
    claims = re.findall(r"[^.\]]+?\.\s*\[(\w+)[^\]]*\]", prose.replace("\n", " "))
    assert claims and len(claims) <= 3
    assert set(claims) <= set(TIERS)
    for tag in re.findall(r"\[(?:Direct|Supported)([^\]]*)\]", prose):
        assert tag.strip(), "Direct and Supported tags must cite a pointer"
    assert "mentions_target: true" in example


def test_worked_example_supersession_claim_cites_the_superseding_reference():
    """The superseded decision's own pointer does not record its supersession, so
    the history claim must cite the reported ``superseded_by`` reference."""
    import re

    example = _why_md().split("## Worked example", 1)[1].split("\n## ", 1)[0]
    ref = re.search(r"superseded_by: ([^`\s]+)`", example).group(1)
    prose = example.split("```text", 1)[1].split("```", 1)[1].split("Grounding:", 1)[0]
    flat = prose.replace("\n", " ")
    history = [m for m in re.finditer(r"([^.\]]+?\.)\s*\[(\w+)([^\]]*)\]", flat)
               if "history" in m.group(1) or "supersed" in m.group(1)]
    assert history, "the worked example must show the supersession claim"
    for m in history:
        assert ref in m.group(3).split()
        assert "demo-change/session-log.md#plan/D1" not in m.group(3)


def test_null_result_rule_lists_every_trace_status():
    section = _why_md().split("## Null-result rule", 1)[1].split("\n## ", 1)[0]
    for status in ("uncommitted", "history_truncated", "no_change_id",
                   "no_decision_record"):
        assert f"`{status}`" in section
