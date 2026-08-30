"""Goal gate for the autopilot loop — the evidence check guarding DONE.

A pure function over two independent evidence sources (OpenSpec design D5):

1. ``validation-report.md`` — the durable artifact ``/cleanup-feature`` already
   gates on. Required sections come from ``gate_logic.resolve_required_phases``,
   the same call ``gate_logic.pre_merge_gate`` makes, so the goal gate and
   ``/cleanup-feature`` can never disagree about what "validated" means.
2. ``LoopState.phase_history`` — written by ``apply_phase_outcome`` during *this*
   run.

Neither alone is sufficient. The report can be a leftover from an earlier run of
the same change; the history entry alone is only the sub-agent's self-report with
no artifact behind it. Requiring the history entry to postdate the report is what
binds the artifact to this run.

The module deliberately imports nothing from ``autopilot.py``: ``state`` is used
structurally (``.phase_history``, ``.val_review_enabled``) so that ``autopilot``
can import this module without a cycle.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal

_SKILLS_DIR = Path(__file__).resolve().parents[2]
_GATE_LOGIC_DIR = _SKILLS_DIR / "validate-feature" / "scripts"
if str(_GATE_LOGIC_DIR) not in sys.path:
    sys.path.insert(0, str(_GATE_LOGIC_DIR))

import gate_logic  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from autopilot import LoopState

REPORT_FILENAME = "validation-report.md"

# The VAL_REVIEW phase's report heading (mirrors handoff_builder's phase labels).
VAL_REVIEW_HEADING = "Validation Review"
VAL_REVIEW_LABEL = "Validation review"

# Named refusal reasons. Each names exactly one failing condition so an ESCALATE
# raised from here says which piece of evidence was missing.
REASON_NO_VALIDATE_RECORD = "no VALIDATE passed record"
REASON_STALE_REPORT = "validate record predates report"
REASON_REPORT_MISSING = "validation report missing"
REASON_UNREADABLE_TIMESTAMP = "VALIDATE record has an unreadable timestamp"


@dataclass(frozen=True)
class GoalGateVerdict:
    verdict: Literal["passed", "refused", "abandoned"]
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _latest_validate_entry(history: Any) -> dict[str, Any] | None:
    """The last VALIDATE entry in the append-only ``phase_history`` log.

    List order is chronological because the log is only ever appended to, so the
    last match is the latest one; sorting by ``at`` would additionally trust a
    field this function is about to validate.
    """
    if not isinstance(history, list):
        return None
    for entry in reversed(history):
        if isinstance(entry, dict) and entry.get("phase") == "VALIDATE":
            return entry
    return None


def _parse_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    # Older records were written without an offset; they came from
    # `datetime.now(timezone.utc)` so UTC is the right assumption, and it keeps
    # the comparison against the report's mtime from raising on mixed awareness.
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _required_sections(state: Any, change_dir: Path) -> dict[str, str]:
    sections = gate_logic.resolve_required_phases(None, change_dir=change_dir)
    if getattr(state, "val_review_enabled", False):
        sections[VAL_REVIEW_HEADING] = VAL_REVIEW_LABEL
    return sections


def check_goal_gate(
    state: "LoopState",
    change_dir: Path,
    *,
    now: Callable[[], datetime] = _utc_now,
) -> GoalGateVerdict:
    """Decide whether the loop has earned DONE.

    Returns ``passed`` only when every required report section reads ``pass``
    AND the latest VALIDATE history entry is ``passed`` and not older than the
    report file. Any other outcome is ``refused`` with a reason naming the one
    condition that failed. ``now`` is injectable so the recorded ``checked_at``
    is deterministic under test.
    """
    change_dir = Path(change_dir)
    report_path = change_dir / REPORT_FILENAME
    evidence: dict[str, Any] = {
        "report_path": str(report_path),
        "checked_at": now().isoformat(),
    }

    entry = _latest_validate_entry(getattr(state, "phase_history", None))
    if entry is None:
        return GoalGateVerdict("refused", REASON_NO_VALIDATE_RECORD, evidence)

    outcome = entry.get("outcome")
    evidence["validate_outcome"] = outcome
    evidence["validate_at"] = entry.get("at")
    if outcome != "passed":
        return GoalGateVerdict(
            "refused", f"latest VALIDATE record is {outcome}", evidence
        )

    validated_at = _parse_timestamp(entry.get("at"))
    if validated_at is None:
        return GoalGateVerdict("refused", REASON_UNREADABLE_TIMESTAMP, evidence)

    if not report_path.is_file():
        return GoalGateVerdict("refused", REASON_REPORT_MISSING, evidence)

    # mtime, not a git timestamp: validate-feature writes the report inside an
    # ephemeral worktree and copies it back, so mtime is the moment the report
    # became visible to this loop — the comparison that proves the report is
    # this run's, and one that does not require the report to be committed.
    report_mtime = datetime.fromtimestamp(report_path.stat().st_mtime, tz=timezone.utc)
    evidence["report_mtime"] = report_mtime.isoformat()
    if validated_at < report_mtime:
        return GoalGateVerdict("refused", REASON_STALE_REPORT, evidence)

    required = _required_sections(state, change_dir)
    evidence["required_sections"] = list(required)
    statuses = {
        heading: gate_logic.check_phase_status(str(report_path), heading)
        for heading in required
    }
    evidence["phase_statuses"] = statuses

    for heading in required:
        status = statuses[heading]
        if status == "pass":
            continue
        if status == "fail":
            reason = f"required section failed: {heading}"
        elif status == "skipped":
            reason = f"required section skipped: {heading}"
        else:
            reason = f"required section not passed: {heading} ({status})"
        return GoalGateVerdict("refused", reason, evidence)

    return GoalGateVerdict("passed", "all required evidence present", evidence)
