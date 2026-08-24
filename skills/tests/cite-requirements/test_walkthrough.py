"""Tests for the deterministic half of skills/cite-requirements.

Scope: the text-manipulation core (block location, insertion, exclusions
file, journal, annotation shape) — everything that runs without the
gen-eval venv. Functions needing `gen_eval` (resolution, cards) accept a
`known_ids` injection or import lazily; the thin glue that resolves for
real is exercised by using the skill, not by this suite.

Counts are derived from the real contract file, never hardcoded — the
suite must not fail because a flag was legitimately added.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

SKILL_SCRIPTS = Path(__file__).resolve().parents[2] / "cite-requirements" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

import walkthrough as w  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_CONTRACT = REPO_ROOT / "openspec" / "contracts" / "gen-eval-framework" / "cli" / (
    "gen-eval.yaml"
)

# A miniature contract with the same indentation grammar as the real one.
MINI = """\
contract_version: "1"
tool:
  name: mini
commands:
  - name: ""
    flags:
      - name: --alpha
        type: string
        description: >-
          First flag, multi-line
          description body.
      - name: --beta
        type: number
        default: 3

exit_codes:
  - code: 0
"""


def mini_lines() -> list[str]:
    return MINI.splitlines(keepends=True)


# ---------------------------------------------------------------------------
# Block location
# ---------------------------------------------------------------------------


def test_locate_flag_block_spans_to_next_flag() -> None:
    lines = mini_lines()
    start, end = w.locate_flag_block(lines, "--alpha")
    assert lines[start].rstrip() == "      - name: --alpha"
    assert lines[end].rstrip() == "      - name: --beta"
    # multi-line description stays inside the block
    assert any("description body." in ln for ln in lines[start:end])


def test_locate_flag_block_last_flag_stops_at_dedent_excluding_blanks() -> None:
    lines = mini_lines()
    start, end = w.locate_flag_block(lines, "--beta")
    assert lines[start].rstrip() == "      - name: --beta"
    # ends before the blank line separating it from exit_codes
    assert lines[end - 1].rstrip() == "        default: 3"


def test_locate_flag_block_unknown_flag_fails() -> None:
    with pytest.raises(w.WalkthroughError, match="--gamma"):
        w.locate_flag_block(mini_lines(), "--gamma")


# ---------------------------------------------------------------------------
# Insertion — citation
# ---------------------------------------------------------------------------


def test_apply_citation_roundtrips_and_touches_nothing_else() -> None:
    lines = mini_lines()
    block = w.render_citation_block(["mini.first-requirement", "other.cross-capability"])
    new_lines = w.insert_traceability(lines, "--alpha", block)
    new_text = "".join(new_lines)

    # everything outside the inserted block is byte-identical
    assert "".join(lines) == new_text.replace("".join(block), "", 1)

    parsed = w.parse_contract_traceability(new_text)
    assert parsed["--alpha"]["requirements"] == [
        "mini.first-requirement",
        "other.cross-capability",
    ]
    assert parsed["--beta"] == {}
    w.validate_contract_text(new_text, "--alpha")


def test_double_decision_fails_without_replace_and_succeeds_with_it() -> None:
    lines = w.insert_traceability(
        mini_lines(), "--alpha", w.render_citation_block(["mini.first-requirement"])
    )
    with pytest.raises(w.WalkthroughError, match="--replace"):
        w.insert_traceability(lines, "--alpha", w.render_citation_block(["mini.other"]))

    replaced = w.insert_traceability(
        lines, "--alpha", w.render_citation_block(["mini.other"]), replace=True
    )
    parsed = w.parse_contract_traceability("".join(replaced))
    assert parsed["--alpha"]["requirements"] == ["mini.other"]
    # the old block is gone, not shadowed
    assert "first-requirement" not in "".join(replaced)


# ---------------------------------------------------------------------------
# Insertion — exclusion
# ---------------------------------------------------------------------------


def test_apply_exclusion_folds_reason_and_parses_back() -> None:
    reason = (
        "Served by the framework API, no CLI surface. This sentence is long "
        "enough to force the folded scalar onto several wrapped lines."
    )
    new_text = "".join(
        w.insert_traceability(mini_lines(), "--beta", w.render_exclusion_block(reason))
    )
    parsed = w.parse_contract_traceability(new_text)
    # folded scalar joins with single spaces — reason survives verbatim
    assert parsed["--beta"]["excluded"]["reason"] == reason
    w.validate_contract_text(new_text, "--beta")


def test_empty_reason_fails_closed() -> None:
    with pytest.raises(w.WalkthroughError, match="empty"):
        w.render_exclusion_block("   ")


def test_validate_contract_text_rejects_both_and_neither() -> None:
    both = "".join(
        w.insert_traceability(
            mini_lines(),
            "--alpha",
            w.render_citation_block(["mini.x"]) + w.render_exclusion_block("r")[1:],
        )
    )
    with pytest.raises(w.WalkthroughError, match="exactly one"):
        w.validate_contract_text(both, "--alpha")
    with pytest.raises(w.WalkthroughError, match="no traceability"):
        w.validate_contract_text(MINI, "--alpha")


# ---------------------------------------------------------------------------
# Requirement-id validation (injected universe — no gen_eval needed)
# ---------------------------------------------------------------------------


def test_validate_requirement_ids_shape_and_membership() -> None:
    known = {"mini.alpha-does-a-thing"}
    w.validate_requirement_ids(["mini.alpha-does-a-thing"], REPO_ROOT, None, known_ids=known)
    with pytest.raises(w.WalkthroughError, match="does not resolve"):
        w.validate_requirement_ids(["mini.unknown"], REPO_ROOT, None, known_ids=known)
    with pytest.raises(w.WalkthroughError, match="not a"):
        w.validate_requirement_ids(["NotAnId"], REPO_ROOT, None, known_ids=known)


# ---------------------------------------------------------------------------
# Exclusions file
# ---------------------------------------------------------------------------


def test_exclusions_file_matches_gate_loader_shape(tmp_path: Path) -> None:
    path = tmp_path / "traceability-exclusions.yaml"
    w.write_exclusions(
        path,
        "mini",
        [
            {"requirement": "mini.zeta", "reason": "later entry, sorts last"},
            {"requirement": "mini.alpha", "reason": "Served by the API; no CLI surface."},
        ],
    )
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    # exactly the shape check_traceability.load_exclusions_file requires
    assert isinstance(doc, dict) and isinstance(doc["exclusions"], list)
    for entry in doc["exclusions"]:
        assert set(entry) == {"requirement", "reason"}
    assert [e["requirement"] for e in doc["exclusions"]] == ["mini.alpha", "mini.zeta"]


def test_read_exclusions_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "traceability-exclusions.yaml"
    entries = [{"requirement": "mini.a", "reason": "why not"}]
    w.write_exclusions(path, "mini", entries)
    assert w.read_exclusions(path) == entries
    assert w.read_exclusions(tmp_path / "absent.yaml") == []


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


def test_journal_appends_and_never_rewrites(tmp_path: Path) -> None:
    first = w.journal_append(tmp_path, {"kind": "cite", "flag": "--a", "requirements": ["x.y"]})
    w.journal_append(tmp_path, {"kind": "exclude-flag", "flag": "--b", "reason": "r"})
    doc = yaml.safe_load(first.read_text(encoding="utf-8"))
    assert [d["kind"] for d in doc["decisions"]] == ["cite", "exclude-flag"]
    assert all("at" in d for d in doc["decisions"])


# ---------------------------------------------------------------------------
# Annotations shape (interpretation layer)
# ---------------------------------------------------------------------------


def test_annotations_validation_accepts_good_and_names_problems() -> None:
    good = {
        "models": [{"label": "m1", "vendor": "v1"}],
        "flags": {"--a": [{"model": "m1", "requirement": "c.x", "note": "related"}], "--b": []},
    }
    assert w.validate_annotations(good) == []

    bad = {
        "models": [{"label": "m1", "vendor": "v1"}],
        "flags": {"--a": [{"model": "ghost", "requirement": "c.x", "note": "n"}]},
    }
    problems = w.validate_annotations(bad)
    assert any("undeclared model" in p for p in problems)
    assert w.validate_annotations({"models": [], "flags": {}})


# ---------------------------------------------------------------------------
# Against the real contract (counts derived, not hardcoded)
# ---------------------------------------------------------------------------


def test_real_contract_flags_all_located() -> None:
    text = REAL_CONTRACT.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    names = w.contract_flag_names(lines)
    # derive the expected set from the parsed YAML, not a literal count
    parsed_names = list(w.parse_contract_traceability(text))
    assert names == parsed_names
    assert len(names) >= 1
    for name in names:
        start, end = w.locate_flag_block(lines, name)
        assert w.FLAG_ITEM_RE.match(lines[start])["name"] == name
        assert end > start


def test_real_contract_insertion_is_reversible_for_every_flag(tmp_path: Path) -> None:
    """Insert + parse for each real flag on a throwaway copy; the original
    file is never touched, and every insertion yields valid YAML.

    Whether a flag already carries a traceability block depends on branch
    state (all 17 do since tasks 4.1/4.2 landed), so derive `replace` from
    the artifact instead of assuming either state."""
    text = REAL_CONTRACT.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    for name in w.contract_flag_names(lines):
        start, end = w.locate_flag_block(lines, name)
        has_block = w.flag_traceability_span(lines, start, end) is not None
        new_text = "".join(
            w.insert_traceability(
                lines,
                name,
                w.render_citation_block(["gen-eval-framework.evaluation"]),
                replace=has_block,
            )
        )
        w.validate_contract_text(new_text, name)
    assert REAL_CONTRACT.read_text(encoding="utf-8") == text
