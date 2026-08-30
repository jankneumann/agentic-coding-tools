"""Tests for the autopilot goal gate (OpenSpec D5, tasks 1.1 / 1.2).

Every refusal asserts the *reason*, not just the verdict: a gate that refuses
for the wrong condition sends the loop to ESCALATE with a misleading message,
which is a real bug even though the verdict looks right.
"""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import goal_gate

# A fixed clock so `now` injection is observable in the evidence.
FROZEN_NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)
REPORT_MTIME = datetime(2026, 8, 30, 10, 0, 0, tzinfo=timezone.utc)


@dataclass
class FakeState:
    """Duck-typed stand-in for autopilot.LoopState."""

    phase_history: list[dict[str, Any]] = field(default_factory=list)
    val_review_enabled: bool = False


def _section(heading: str, status: str) -> str:
    return f"## {heading}\n\n**Status**: {status}\n\n"


def write_change_dir(
    tmp_path: Path,
    *,
    sections: dict[str, str] | None = None,
    deployable: bool = False,
    write_report: bool = True,
    mtime: datetime = REPORT_MTIME,
) -> Path:
    """Build an OpenSpec change directory with a validation report.

    `deployable` is declared in proposal.md frontmatter so
    `resolve_required_phases` is deterministic here instead of deriving the
    surface from git.
    """
    change_dir = tmp_path / "changes" / "some-change"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(
        f"---\ndeployable: {'true' if deployable else 'false'}\n---\n\n# Proposal\n"
    )
    if write_report:
        if sections is None:
            sections = {"Spec Compliance": "pass"}
        body = "# Validation Report\n\n" + "".join(
            _section(heading, status) for heading, status in sections.items()
        )
        report = change_dir / "validation-report.md"
        report.write_text(body)
        stamp = mtime.timestamp()
        os.utime(report, (stamp, stamp))
    return change_dir


def validate_entry(offset_seconds: int, outcome: str = "passed") -> dict[str, Any]:
    """A phase_history entry `offset_seconds` after the report's mtime."""
    at = REPORT_MTIME + timedelta(seconds=offset_seconds)
    return {"phase": "VALIDATE", "outcome": outcome, "at": at.isoformat()}


def check(state: FakeState, change_dir: Path) -> goal_gate.GoalGateVerdict:
    return goal_gate.check_goal_gate(state, change_dir, now=lambda: FROZEN_NOW)


# ---------------------------------------------------------------------------
# Passing evidence
# ---------------------------------------------------------------------------

def test_passes_when_report_and_fresh_validate_record_agree(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path)
    verdict = check(FakeState(phase_history=[validate_entry(60)]), change_dir)

    assert verdict.verdict == "passed"
    assert verdict.evidence["phase_statuses"]["Spec Compliance"] == "pass"


def test_passes_when_validate_record_equals_report_mtime(tmp_path: Path) -> None:
    """`at >= mtime` — an exactly-equal timestamp is fresh, not stale."""
    change_dir = write_change_dir(tmp_path)
    verdict = check(FakeState(phase_history=[validate_entry(0)]), change_dir)

    assert verdict.verdict == "passed"


def test_passes_with_all_deployable_sections(tmp_path: Path) -> None:
    change_dir = write_change_dir(
        tmp_path,
        deployable=True,
        sections={
            "Spec Compliance": "pass",
            "Smoke Tests": "pass",
            "Security": "pass",
            "E2E Tests": "pass",
        },
    )
    verdict = check(FakeState(phase_history=[validate_entry(60)]), change_dir)

    assert verdict.verdict == "passed"
    assert set(verdict.evidence["required_sections"]) == {
        "Spec Compliance",
        "Smoke Tests",
        "Security",
        "E2E Tests",
    }


def test_latest_validate_entry_wins_over_earlier_failure(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path)
    state = FakeState(
        phase_history=[
            validate_entry(10, outcome="failed"),
            validate_entry(60, outcome="passed"),
        ]
    )

    assert check(state, change_dir).verdict == "passed"


def test_now_is_injectable(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path)
    verdict = check(FakeState(phase_history=[validate_entry(60)]), change_dir)

    assert verdict.evidence["checked_at"] == FROZEN_NOW.isoformat()


# ---------------------------------------------------------------------------
# Run-freshness refusals
# ---------------------------------------------------------------------------

def test_no_validate_record_is_refused(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path)
    verdict = check(FakeState(phase_history=[]), change_dir)

    assert verdict.verdict == "refused"
    assert verdict.reason == goal_gate.REASON_NO_VALIDATE_RECORD
    assert verdict.reason == "no VALIDATE passed record"


def test_history_without_validate_phase_is_refused(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path)
    state = FakeState(
        phase_history=[{"phase": "IMPLEMENT", "outcome": "passed", "at": "2026-08-30T11:00:00+00:00"}]
    )
    verdict = check(state, change_dir)

    assert verdict.verdict == "refused"
    assert verdict.reason == goal_gate.REASON_NO_VALIDATE_RECORD


def test_failed_validate_record_is_refused(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path)
    verdict = check(
        FakeState(phase_history=[validate_entry(60, outcome="failed")]), change_dir
    )

    assert verdict.verdict == "refused"
    assert verdict.reason == "latest VALIDATE record is failed"
    assert verdict.evidence["validate_outcome"] == "failed"


def test_latest_validate_failure_beats_earlier_pass(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path)
    state = FakeState(
        phase_history=[
            validate_entry(10, outcome="passed"),
            validate_entry(60, outcome="failed"),
        ]
    )
    verdict = check(state, change_dir)

    assert verdict.verdict == "refused"
    assert verdict.reason == "latest VALIDATE record is failed"


def test_stale_report_is_refused(tmp_path: Path) -> None:
    """Report written after the VALIDATE record — evidence from another run."""
    change_dir = write_change_dir(tmp_path)
    verdict = check(FakeState(phase_history=[validate_entry(-60)]), change_dir)

    assert verdict.verdict == "refused"
    assert verdict.reason == goal_gate.REASON_STALE_REPORT
    assert verdict.reason == "validate record predates report"


def test_unparseable_validate_timestamp_is_refused(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path)
    state = FakeState(
        phase_history=[{"phase": "VALIDATE", "outcome": "passed", "at": "not-a-time"}]
    )
    verdict = check(state, change_dir)

    assert verdict.verdict == "refused"
    assert verdict.reason == goal_gate.REASON_UNREADABLE_TIMESTAMP


# ---------------------------------------------------------------------------
# Report-evidence refusals
# ---------------------------------------------------------------------------

def test_missing_report_is_refused(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path, write_report=False)
    verdict = check(FakeState(phase_history=[validate_entry(60)]), change_dir)

    assert verdict.verdict == "refused"
    assert verdict.reason == goal_gate.REASON_REPORT_MISSING


def test_no_validate_record_outranks_missing_report(tmp_path: Path) -> None:
    """A hand-edited state with no history is refused for the history, per spec."""
    change_dir = write_change_dir(tmp_path, write_report=False)
    verdict = check(FakeState(phase_history=[]), change_dir)

    assert verdict.reason == goal_gate.REASON_NO_VALIDATE_RECORD


def test_failed_section_is_refused_by_name(tmp_path: Path) -> None:
    change_dir = write_change_dir(
        tmp_path,
        deployable=True,
        sections={
            "Spec Compliance": "pass",
            "Smoke Tests": "fail",
            "Security": "pass",
            "E2E Tests": "pass",
        },
    )
    verdict = check(FakeState(phase_history=[validate_entry(60)]), change_dir)

    assert verdict.verdict == "refused"
    assert verdict.reason == "required section failed: Smoke Tests"
    assert verdict.evidence["phase_statuses"]["Smoke Tests"] == "fail"


def test_skipped_section_is_refused_by_name(tmp_path: Path) -> None:
    change_dir = write_change_dir(
        tmp_path, sections={"Spec Compliance": "skipped"}
    )
    verdict = check(FakeState(phase_history=[validate_entry(60)]), change_dir)

    assert verdict.verdict == "refused"
    assert verdict.reason == "required section skipped: Spec Compliance"


def test_missing_section_is_refused_by_name(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path, sections={"Notes": "pass"})
    verdict = check(FakeState(phase_history=[validate_entry(60)]), change_dir)

    assert verdict.verdict == "refused"
    assert verdict.reason == "required section not passed: Spec Compliance (missing)"


def test_degraded_section_is_refused(tmp_path: Path) -> None:
    change_dir = write_change_dir(
        tmp_path, sections={"Spec Compliance": "degraded"}
    )
    verdict = check(FakeState(phase_history=[validate_entry(60)]), change_dir)

    assert verdict.verdict == "refused"
    assert verdict.reason == "required section not passed: Spec Compliance (degraded)"


# ---------------------------------------------------------------------------
# Task 1.2 — Validation Review section follows val_review_enabled
# ---------------------------------------------------------------------------

def test_validation_review_required_when_enabled(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path, sections={"Spec Compliance": "pass"})
    state = FakeState(phase_history=[validate_entry(60)], val_review_enabled=True)
    verdict = check(state, change_dir)

    assert verdict.verdict == "refused"
    assert verdict.reason == "required section not passed: Validation Review (missing)"
    assert "Validation Review" in verdict.evidence["required_sections"]


def test_validation_review_ignored_when_disabled(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path, sections={"Spec Compliance": "pass"})
    state = FakeState(phase_history=[validate_entry(60)], val_review_enabled=False)
    verdict = check(state, change_dir)

    assert verdict.verdict == "passed"
    assert "Validation Review" not in verdict.evidence["required_sections"]


def test_validation_review_passes_when_present_and_enabled(tmp_path: Path) -> None:
    change_dir = write_change_dir(
        tmp_path,
        sections={"Spec Compliance": "pass", "Validation Review": "pass"},
    )
    state = FakeState(phase_history=[validate_entry(60)], val_review_enabled=True)

    assert check(state, change_dir).verdict == "passed"


def test_failing_validation_review_is_refused_when_enabled(tmp_path: Path) -> None:
    change_dir = write_change_dir(
        tmp_path,
        sections={"Spec Compliance": "pass", "Validation Review": "fail"},
    )
    state = FakeState(phase_history=[validate_entry(60)], val_review_enabled=True)
    verdict = check(state, change_dir)

    assert verdict.verdict == "refused"
    assert verdict.reason == "required section failed: Validation Review"


# ---------------------------------------------------------------------------
# Verdict shape
# ---------------------------------------------------------------------------

def test_verdict_is_frozen(tmp_path: Path) -> None:
    change_dir = write_change_dir(tmp_path)
    verdict = check(FakeState(phase_history=[validate_entry(60)]), change_dir)

    with pytest.raises(FrozenInstanceError):
        verdict.verdict = "refused"  # type: ignore[misc]
