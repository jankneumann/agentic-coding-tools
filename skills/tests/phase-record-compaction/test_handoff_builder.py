"""Tests for autopilot handoff_builder.build_phase_record(state, prev, next).

Asserts that for each _HANDOFF_BOUNDARIES pair, build_phase_record produces
a valid PhaseRecord with the appropriate phase_name, summary, and structured
fields populated from LoopState.

Spec reference: skill-workflow / Coordinator Handoff Population at Autopilot
Phase Boundaries — Handoff is populated on each defined boundary.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/session-log/scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills/autopilot/scripts"))

from handoff_builder import build_phase_record  # noqa: E402
from phase_record import PhaseRecord  # noqa: E402

from autopilot import _HANDOFF_BOUNDARIES, LoopState  # noqa: E402


@pytest.fixture
def state() -> LoopState:
    return LoopState(
        change_id="test-change",
        current_phase="IMPLEMENT",
        iteration=1,
        total_iterations=4,
        findings_trend=[5, 3, 1],
        blocking_findings=[],
        packages_status={"wp-main": "complete"},
        package_authors={"wp-main": "claude_code"},
        handoff_ids=["prior-handoff-1"],
        previous_phase="PLAN_REVIEW",
    )


class TestBuilderShape:
    """build_phase_record returns a PhaseRecord with required fields."""

    def test_returns_phase_record(self, state: LoopState) -> None:
        record = build_phase_record(state, "PLAN_ITERATE", "PLAN_REVIEW")
        assert isinstance(record, PhaseRecord)

    def test_change_id_propagated(self, state: LoopState) -> None:
        record = build_phase_record(state, "PLAN_ITERATE", "PLAN_REVIEW")
        assert record.change_id == "test-change"

    def test_summary_mentions_transition(self, state: LoopState) -> None:
        record = build_phase_record(state, "IMPL_ITERATE", "IMPL_REVIEW")
        # The summary should reference the boundary so a reader can tell at
        # a glance which phase the record describes.
        assert "IMPL_ITERATE" in record.summary or "IMPL_REVIEW" in record.summary

    def test_agent_type_is_autopilot_by_default(self, state: LoopState) -> None:
        record = build_phase_record(state, "PLAN_REVIEW", "IMPLEMENT")
        # Default agent_type should identify the autopilot driver
        assert record.agent_type == "autopilot"


class TestBuilderEachBoundary:
    """For every _HANDOFF_BOUNDARIES pair, a non-empty PhaseRecord is produced."""

    @pytest.mark.parametrize("boundary", sorted(_HANDOFF_BOUNDARIES))
    def test_each_boundary_produces_record(
        self,
        boundary: tuple[str, str],
        state: LoopState,
    ) -> None:
        prev, nxt = boundary
        record = build_phase_record(state, prev, nxt)
        assert isinstance(record, PhaseRecord)
        assert record.change_id == state.change_id
        # phase_name must be non-empty and human-readable
        assert record.phase_name
        assert isinstance(record.phase_name, str)
        # summary must be non-empty
        assert record.summary


class TestPhaseNameMapping:
    """Per-boundary builders produce sensible phase_name strings."""

    def test_plan_iterate_to_review(self, state: LoopState) -> None:
        record = build_phase_record(state, "PLAN_ITERATE", "PLAN_REVIEW")
        # The just-completed phase is PLAN_ITERATE; with state.iteration=1
        # the canonical name is "Plan Iteration 1"
        assert "Plan Iteration" in record.phase_name

    def test_plan_review_to_implement(self, state: LoopState) -> None:
        record = build_phase_record(state, "PLAN_REVIEW", "IMPLEMENT")
        assert "Plan Review" in record.phase_name or "Plan" in record.phase_name

    def test_impl_iterate_to_review(self, state: LoopState) -> None:
        record = build_phase_record(state, "IMPL_ITERATE", "IMPL_REVIEW")
        assert "Implementation" in record.phase_name

    def test_validate_to_submit(self, state: LoopState) -> None:
        record = build_phase_record(state, "VALIDATE", "SUBMIT_PR")
        assert "Validation" in record.phase_name


class TestStructuredFieldsFromState:
    """Builder pulls structured fields from LoopState for the coordinator."""

    def test_findings_trend_summary(self, state: LoopState) -> None:
        """Findings trend should appear somewhere in the record (summary or
        completed_work) so the next phase has visibility into convergence."""
        record = build_phase_record(state, "PLAN_REVIEW", "IMPLEMENT")
        rendered = record.summary + " ".join(record.completed_work)
        # 5 → 3 → 1 — at least the latest count should be visible
        assert "1" in rendered or "5" in rendered or "findings" in rendered.lower()

    def test_packages_status_in_completed_work(self, state: LoopState) -> None:
        """When a package is complete, that fact should land in completed_work
        for the IMPL_ITERATE → IMPL_REVIEW boundary."""
        record = build_phase_record(state, "IMPL_ITERATE", "IMPL_REVIEW")
        # packages_status={"wp-main": "complete"} — the package id should
        # appear in the rendered record (completed_work or summary)
        rendered = record.summary + " ".join(record.completed_work)
        assert "wp-main" in rendered

    def test_no_blocking_findings_yields_empty_open_questions(
        self, state: LoopState,
    ) -> None:
        # state.blocking_findings is empty → no open questions
        record = build_phase_record(state, "VALIDATE", "SUBMIT_PR")
        assert record.open_questions == []


class TestBuilderWithBlockingFindings:
    """When blocking findings exist, they surface as open questions."""

    def test_blocking_findings_become_open_questions(self) -> None:
        state = LoopState(
            change_id="test",
            blocking_findings=[
                {"id": "F1", "severity": "high", "title": "Missing test for edge X"},
                {"id": "F2", "severity": "high", "title": "Race in worker pool"},
            ],
        )
        record = build_phase_record(state, "IMPL_REVIEW", "VALIDATE")
        assert len(record.open_questions) == 2
        joined = " ".join(record.open_questions)
        assert "edge X" in joined
        assert "worker pool" in joined
