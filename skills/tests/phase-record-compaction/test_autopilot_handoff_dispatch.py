"""Tests for autopilot._maybe_handoff PhaseRecord dispatch.

Asserts:
- _maybe_handoff calls handoff_fn(state, PhaseRecord) — not (state, str).
- The PhaseRecord passed in is built by build_phase_record(state, prev, next).
- handoff_fn's return value (handoff_id or None) is appended to state.handoff_ids
  and stored as state.last_handoff_id.
- handoff_fn=None is a no-op (no exception, no state mutation).
- Non-boundary transitions are skipped (no call to handoff_fn).

Spec reference: skill-workflow / Coordinator Handoff Population at Autopilot
Phase Boundaries — Handoff is populated on each defined boundary.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/session-log/scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills/autopilot/scripts"))

from phase_record import PhaseRecord  # noqa: E402

from autopilot import LoopState, _maybe_handoff  # noqa: E402


class _CapturingHandoffFn:
    """Records every (state, phase_record) call and returns canned handoff_ids."""

    def __init__(self, ids: list[str | None] | None = None) -> None:
        self.calls: list[tuple[LoopState, PhaseRecord]] = []
        self._ids = list(ids) if ids is not None else ["h-1"]

    def __call__(self, state: LoopState, record: PhaseRecord) -> str | None:
        self.calls.append((state, record))
        if not self._ids:
            return None
        return self._ids.pop(0)


@pytest.fixture
def state() -> LoopState:
    return LoopState(
        change_id="dispatch-test",
        current_phase="IMPLEMENT",
        iteration=1,
        findings_trend=[3, 1],
        packages_status={"wp-main": "complete"},
    )


class TestBoundaryDispatch:
    """At a known boundary, _maybe_handoff calls handoff_fn with a PhaseRecord."""

    def test_calls_handoff_fn_with_phase_record(self, state: LoopState) -> None:
        fn = _CapturingHandoffFn(ids=["h-42"])
        _maybe_handoff("PLAN_REVIEW", "IMPLEMENT", state, fn)
        assert len(fn.calls) == 1
        captured_state, record = fn.calls[0]
        assert captured_state is state
        assert isinstance(record, PhaseRecord)
        assert record.change_id == state.change_id

    def test_phase_record_phase_name_reflects_prev(self, state: LoopState) -> None:
        fn = _CapturingHandoffFn()
        _maybe_handoff("IMPL_ITERATE", "IMPL_REVIEW", state, fn)
        record = fn.calls[0][1]
        # IMPL_ITERATE → "Implementation Iteration <iteration>"
        assert "Implementation Iteration" in record.phase_name

    def test_handoff_id_appended_to_state(self, state: LoopState) -> None:
        fn = _CapturingHandoffFn(ids=["h-99"])
        _maybe_handoff("VALIDATE", "SUBMIT_PR", state, fn)
        assert state.handoff_ids == ["h-99"]
        assert state.last_handoff_id == "h-99"

    def test_multiple_boundaries_accumulate_ids(self, state: LoopState) -> None:
        fn = _CapturingHandoffFn(ids=["h-1", "h-2", "h-3"])
        _maybe_handoff("PLAN_ITERATE", "PLAN_REVIEW", state, fn)
        _maybe_handoff("PLAN_REVIEW", "IMPLEMENT", state, fn)
        _maybe_handoff("IMPL_ITERATE", "IMPL_REVIEW", state, fn)
        assert state.handoff_ids == ["h-1", "h-2", "h-3"]
        assert state.last_handoff_id == "h-3"

    def test_none_return_does_not_pollute_state(self, state: LoopState) -> None:
        # When handoff_fn returns None (e.g., write failed end-to-end), the
        # state should not gain an entry — the failure has no id to record.
        fn = _CapturingHandoffFn(ids=[None])
        _maybe_handoff("VAL_REVIEW", "SUBMIT_PR", state, fn)
        assert state.handoff_ids == []
        assert state.last_handoff_id is None


class TestNonBoundary:
    """Non-boundary transitions skip the handoff callback entirely."""

    def test_unknown_pair_skips(self, state: LoopState) -> None:
        fn = _CapturingHandoffFn()
        _maybe_handoff("INIT", "PLAN", state, fn)  # not in _HANDOFF_BOUNDARIES
        assert fn.calls == []
        assert state.handoff_ids == []
        assert state.last_handoff_id is None

    def test_none_handoff_fn_is_noop(self, state: LoopState) -> None:
        # No handoff_fn provided → no exception, no state mutation.
        _maybe_handoff("PLAN_REVIEW", "IMPLEMENT", state, None)
        assert state.handoff_ids == []
        assert state.last_handoff_id is None


class TestHandoffFnCallableContract:
    """handoff_fn signature: (LoopState, PhaseRecord) -> str | None."""

    def test_handoff_fn_with_old_signature_breaks_clearly(
        self, state: LoopState,
    ) -> None:
        # If a caller passes an old-style fn(state, str), the dispatcher
        # passes a PhaseRecord instead — the fn either accepts it (Any-typed)
        # or raises TypeError. We assert the dispatcher does not silently
        # convert PhaseRecord to a string.
        captured: list[Any] = []

        def fn(state: LoopState, arg: Any) -> Any:
            captured.append(arg)
            return None

        _maybe_handoff("PLAN_REVIEW", "IMPLEMENT", state, fn)
        assert len(captured) == 1
        assert isinstance(captured[0], PhaseRecord)
