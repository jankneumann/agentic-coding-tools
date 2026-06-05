"""Triage pass for session transcript mining.

Scores every ingested session on struggle signals:
  - retry_count: number of repeated tool calls with the same name
  - tool_error_count: number of tool results with is_error=True
  - scope_violation_count: heuristic count of out-of-scope attempts
  - user_correction_count: number of user messages following assistant errors
  - struggle_classification: composite struggle level (none/low/medium/high)

The triage model is resolved via the archetype system (default archetype:
analyst, default provider: claude_code).  In ``--dry-run`` mode (the
default in CI), the triage prints planned operations without making any
API calls.

Usage:
    python3 triage.py --events-dir docs/transcripts/2026-06-01/ --dry-run
    python3 triage.py --events-file session.jsonl --threshold 0.5
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from normalize import ContentType, EventRole, NormalizedEvent  # noqa: E402


# ---------------------------------------------------------------------------
# Triage score
# ---------------------------------------------------------------------------

@dataclass
class TriageScore:
    """Struggle score for a single session."""
    session_id: str = ""
    harness: str = ""
    event_count: int = 0
    retry_count: int = 0
    tool_error_count: int = 0
    scope_violation_count: int = 0
    user_correction_count: int = 0
    struggle_level: str = "none"  # none | low | medium | high
    composite_score: float = 0.0
    flagged_for_deep_analysis: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TriageScore:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

# Keywords that suggest scope violations in tool arguments or text
_SCOPE_VIOLATION_KEYWORDS = [
    "out of scope",
    "outside scope",
    "scope violation",
    "not in allowed",
    "permission denied",
    "access denied",
]


def _count_retries(events: list[NormalizedEvent]) -> int:
    """Count consecutive tool calls with the same tool name (retry pattern)."""
    retries = 0
    last_tool_name = ""
    for event in events:
        if event.role == EventRole.ASSISTANT:
            for block in event.content:
                if block.type == ContentType.TOOL_USE:
                    if block.tool_name == last_tool_name:
                        retries += 1
                    last_tool_name = block.tool_name

    return retries


def _count_tool_errors(events: list[NormalizedEvent]) -> int:
    """Count tool results that indicate errors."""
    errors = 0
    for event in events:
        if event.role == EventRole.TOOL:
            for block in event.content:
                if block.type == ContentType.TOOL_RESULT and block.is_error:
                    errors += 1
    return errors


def _count_scope_violations(events: list[NormalizedEvent]) -> int:
    """Heuristic count of scope violation signals in event text."""
    count = 0
    for event in events:
        for block in event.content:
            text_lower = block.text.lower()
            for keyword in _SCOPE_VIOLATION_KEYWORDS:
                if keyword in text_lower:
                    count += 1
                    break  # one match per block
    return count


def _count_user_corrections(events: list[NormalizedEvent]) -> int:
    """Count user messages that follow tool errors (correction pattern).

    A user message immediately after a tool error or after an assistant
    message that contains an error signal is likely a correction.
    """
    corrections = 0
    saw_error = False
    for event in events:
        if event.role == EventRole.TOOL:
            for block in event.content:
                if block.type == ContentType.TOOL_RESULT and block.is_error:
                    saw_error = True
        elif event.role == EventRole.USER and saw_error:
            corrections += 1
            saw_error = False
        elif event.role == EventRole.ASSISTANT:
            saw_error = False  # reset if assistant replies normally
    return corrections


def _classify_struggle(
    retry_count: int,
    tool_error_count: int,
    scope_violation_count: int,
    user_correction_count: int,
) -> tuple[str, float]:
    """Classify struggle level based on signal counts.

    Returns (level, composite_score).
    """
    # Weighted composite score
    score = (
        retry_count * 1.0
        + tool_error_count * 2.0
        + scope_violation_count * 3.0
        + user_correction_count * 2.5
    )

    if score >= 10.0:
        return "high", score
    elif score >= 5.0:
        return "medium", score
    elif score > 0:
        return "low", score
    else:
        return "none", 0.0


# ---------------------------------------------------------------------------
# Triage engine
# ---------------------------------------------------------------------------

def triage_session(
    events: list[NormalizedEvent],
    *,
    session_id: str = "",
    threshold: float = 5.0,
) -> TriageScore:
    """Score a single session's events for struggle signals.

    Parameters
    ----------
    events:
        Normalized events for a single session.
    session_id:
        Session identifier (if not extractable from events).
    threshold:
        Composite score threshold for flagging deep analysis.

    Returns
    -------
    TriageScore with all signal counts and classification.
    """
    if not events:
        return TriageScore(session_id=session_id)

    # Derive session_id and harness from events if not provided
    if not session_id:
        session_id = events[0].session_id
    harness = events[0].harness if events else ""

    retry_count = _count_retries(events)
    tool_error_count = _count_tool_errors(events)
    scope_violation_count = _count_scope_violations(events)
    user_correction_count = _count_user_corrections(events)

    struggle_level, composite_score = _classify_struggle(
        retry_count, tool_error_count, scope_violation_count, user_correction_count
    )

    return TriageScore(
        session_id=session_id,
        harness=harness,
        event_count=len(events),
        retry_count=retry_count,
        tool_error_count=tool_error_count,
        scope_violation_count=scope_violation_count,
        user_correction_count=user_correction_count,
        struggle_level=struggle_level,
        composite_score=composite_score,
        flagged_for_deep_analysis=composite_score >= threshold,
    )


def triage_sessions(
    sessions: dict[str, list[NormalizedEvent]],
    *,
    threshold: float = 5.0,
) -> list[TriageScore]:
    """Score multiple sessions.

    Parameters
    ----------
    sessions:
        Mapping of session_id -> events.
    threshold:
        Composite score threshold for flagging.

    Returns
    -------
    List of TriageScore, one per session.
    """
    return [
        triage_session(events, session_id=sid, threshold=threshold)
        for sid, events in sessions.items()
    ]


# ---------------------------------------------------------------------------
# Dry-run report
# ---------------------------------------------------------------------------

def dry_run_report(scores: list[TriageScore]) -> str:
    """Generate a dry-run report showing planned operations.

    Prints per-session stats and estimated deep-analysis count.
    No API calls are made.
    """
    lines: list[str] = []
    lines.append("# Transcript Triage — Dry Run Report")
    lines.append("")
    lines.append(f"Sessions analyzed: {len(scores)}")

    flagged = [s for s in scores if s.flagged_for_deep_analysis]
    lines.append(f"Sessions flagged for deep analysis: {len(flagged)}")
    lines.append("")

    if scores:
        lines.append("## Per-Session Scores")
        lines.append("")
        lines.append(
            "| Session | Harness | Events | Retries | Errors "
            "| Scope | Corrections | Score | Level | Flagged |"
        )
        lines.append(
            "|---------|---------|--------|---------|--------"
            "|-------|-------------|-------|-------|---------| "
        )
        for s in sorted(scores, key=lambda x: x.composite_score, reverse=True):
            lines.append(
                f"| {s.session_id[:20]} | {s.harness} | {s.event_count} "
                f"| {s.retry_count} | {s.tool_error_count} "
                f"| {s.scope_violation_count} | {s.user_correction_count} "
                f"| {s.composite_score:.1f} | {s.struggle_level} "
                f"| {'YES' if s.flagged_for_deep_analysis else 'no'} |"
            )
        lines.append("")

    lines.append("## Estimated Operations (dry-run — no API calls made)")
    lines.append("")
    lines.append(f"- Triage model calls: 0 (heuristic scoring, no LLM needed)")
    lines.append(f"- Deep analysis model calls: {len(flagged)} (if enabled)")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Triage session transcripts for struggle signals"
    )
    parser.add_argument(
        "--events-file",
        type=str,
        help="Path to a single JSONL events file",
    )
    parser.add_argument(
        "--events-dir",
        type=str,
        help="Path to a directory of JSONL events files",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=5.0,
        help="Composite score threshold for flagging (default: 5.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Print planned operations without API calls (default: True)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output scores as JSON",
    )
    args = parser.parse_args()

    # Load events
    sessions: dict[str, list[NormalizedEvent]] = {}

    if args.events_file:
        events = _load_events_file(Path(args.events_file))
        if events:
            sid = events[0].session_id or Path(args.events_file).stem
            sessions[sid] = events

    if args.events_dir:
        events_dir = Path(args.events_dir)
        if events_dir.is_dir():
            for f in events_dir.glob("*.jsonl"):
                events = _load_events_file(f)
                if events:
                    sid = events[0].session_id or f.stem
                    sessions[sid] = events

    if not sessions:
        print("No sessions found to triage.", file=sys.stderr)
        return 0

    scores = triage_sessions(sessions, threshold=args.threshold)

    if args.json:
        print(json.dumps([s.to_dict() for s in scores], indent=2))
    else:
        report = dry_run_report(scores)
        print(report)

    return 0


def _load_events_file(path: Path) -> list[NormalizedEvent]:
    """Load NormalizedEvents from a JSONL file."""
    events: list[NormalizedEvent] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(NormalizedEvent.from_jsonl_line(line))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    except OSError:
        pass
    return events


if __name__ == "__main__":
    sys.exit(main())
