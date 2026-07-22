"""Regression tests for executable commands and sequencing in autopilot SKILL.md."""

from __future__ import annotations

from pathlib import Path


_SKILL = Path(__file__).resolve().parents[2] / "autopilot" / "SKILL.md"


def test_gatekeeper_documents_record_before_transition_contract() -> None:
    text = _SKILL.read_text()
    section = text.split("### 1.5. GATEKEEPER Phase (Judge)", 1)[1].split(
        "### 2. PLAN Phase",
        1,
    )[0]
    normalized = " ".join(section.split())

    assert "Apply `apply-outcome` while `current_phase` is still `GATEKEEPER`" in normalized
    assert "does not set `gate_verdict`, `val_review_enabled`, or `current_phase`" in normalized
    assert "Only after `apply-outcome` exits zero" in normalized
