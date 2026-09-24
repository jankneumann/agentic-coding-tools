"""Deterministic behavioural checks for explain-code (design D7)."""

from __future__ import annotations

from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2] / "explain-code"
SKILL_MD = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
GROUNDING = (SKILL_DIR / "references" / "grounding.md").read_text(encoding="utf-8")


def test_disclosure_forms_and_ungrounded_reasons():
    """Grounding reference encodes both D5 forms, closed reasons, footer mapping, exemptions."""
    assert "Grounding: graph @ " in GROUNDING
    assert "Grounding: source read, unverified (" in GROUNDING

    for reason in (
        "graph absent",
        "graph check failed",
        "graph stale",
        "symbol not in graph",
        "form not graph-backed",
    ):
        assert reason in GROUNDING, f"missing ungrounded reason token: {reason}"

    # Footer → disclosure mapping (D5)
    assert "after" in GROUNDING.lower() and "·" in GROUNDING
    assert "covered" in GROUNDING
    assert "; " in GROUNDING  # sha separator in disclosure form

    # Clarification / redirect exemptions
    assert "Ambiguous-symbol clarification" in GROUNDING or "exit `3`" in GROUNDING
    assert "Whole-repository redirect" in GROUNDING or "/codebase-atlas" in GROUNDING
    assert "MUST NOT carry" in GROUNDING or "no `Grounding:`" in GROUNDING.lower() or "No `Grounding:`" in GROUNDING

    # Non-call-tree source-read requirement
    assert "read the relevant source" in GROUNDING.lower() or "read those files" in GROUNDING.lower() or "before sketching" in GROUNDING

    # Tree tool failure → graph check failed
    assert "could not be spawned" in GROUNDING or "spawn" in GROUNDING
    assert "graph check failed" in GROUNDING


def test_whole_repository_redirect_to_codebase_atlas():
    assert "/codebase-atlas" in SKILL_MD
    assert "Whole-repository" in SKILL_MD or "whole-repository" in SKILL_MD.lower() or "whole-repository" in SKILL_MD
    # related includes atlas (also checked in test_skill_md)
    assert "codebase-atlas" in SKILL_MD


def test_forbids_ensure_and_analysis_pipeline():
    combined = SKILL_MD + "\n" + GROUNDING
    assert "--ensure" in combined
    assert "analysis pipeline" in combined.lower()
    assert "Never run `--ensure`" in combined or "never** runs `--ensure`" in combined
