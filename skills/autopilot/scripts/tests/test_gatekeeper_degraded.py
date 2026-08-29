"""Tests for DEGRADED reporting from the GATEKEEPER fail-open path.

TDD tests written before implementation (task 2.7, OpenSpec change
introduce-fitness-function-gates, design decision D6).

When no dispatch adapter is available the GATEKEEPER judge falls back to a
permissive signal-only verdict. That fallback is a documented behavior, but it
currently fails open *silently* — the run looks identical to one where a judge
actually weighed the risk. It must now record an explicit DEGRADED entry naming
what was not checked and why.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the scripts directory is importable
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from autopilot import DEGRADED_STATUS, LoopState, _phase_gatekeeper  # noqa: E402


def _degraded_entries(state: LoopState) -> list[dict]:
    return [e for e in state.phase_history if e.get("outcome") == DEGRADED_STATUS]


class TestGatekeeperFallbackIsDegraded:
    """No judge available -> permissive verdict, but recorded as DEGRADED."""

    def test_fallback_records_degraded_entry(self) -> None:
        state = LoopState(current_phase="GATEKEEPER")

        outcome = _phase_gatekeeper(state, None)

        assert outcome == "proceed"  # still permissive — the loop continues
        entries = _degraded_entries(state)
        assert len(entries) == 1
        assert entries[0]["phase"] == "GATEKEEPER"

    def test_degraded_note_says_what_was_not_checked_and_why(self) -> None:
        state = LoopState(current_phase="GATEKEEPER")

        _phase_gatekeeper(state, None)

        note = _degraded_entries(state)[0]["note"]
        assert "NOT CHECKED" in note
        assert "adapter" in note.lower()

    def test_unrecognised_verdict_also_degrades(self) -> None:
        """A judge that answers gibberish is no more checked than no judge."""
        state = LoopState(current_phase="GATEKEEPER")

        _phase_gatekeeper(state, lambda _s: "banana")

        assert len(_degraded_entries(state)) == 1

    def test_risk_signals_still_enable_validation_review(self) -> None:
        """Degradation reporting must not change the fallback's behavior."""
        state = LoopState(
            current_phase="GATEKEEPER",
            gate_signals={"has_db_migration": True},
        )

        outcome = _phase_gatekeeper(state, None)

        assert outcome == "proceed_with_review"
        assert state.val_review_enabled is True
        assert len(_degraded_entries(state)) == 1

    def test_real_judge_verdict_is_not_degraded(self) -> None:
        state = LoopState(current_phase="GATEKEEPER")

        outcome = _phase_gatekeeper(state, lambda _s: "proceed")

        assert outcome == "proceed"
        assert _degraded_entries(state) == []
