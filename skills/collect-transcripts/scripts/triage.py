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
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from normalize import ContentType, EventRole, NormalizedEvent  # noqa: E402
from sanitize_events import sanitize_event_stream  # noqa: E402

# Per system_one_decisions.testing's documented stubbing rule: import the
# module, never a pre-bound name, so a monkeypatched `decide` attribute is
# what this code actually calls.
system_one_decisions: ModuleType | None
try:
    import system_one_decisions
except ImportError:
    system_one_decisions = None


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
    # Judged fields (D1): None when the judgment is unavailable, never
    # guessed from the deterministic counters.
    redirected_by_user: bool | None = None
    out_of_scope_work: bool | None = None

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
# Judged classification (D1-D4)
# ---------------------------------------------------------------------------

_STRUGGLE_LEVELS = ("none", "low", "medium", "high")

DEFAULT_DEEP_ANALYSIS_PROBABILITY_FLOOR = 0.5
_TRIAGE_JUDGMENT_CONFIG_PATH = _SCRIPTS_DIR / "triage-judgment.json"


def load_deep_analysis_floor(config_path: Path | None = None) -> float:
    """Read the optional sidecar JSON, falling back to the module default.

    Mirrors gatekeeper_shadow.load_shadow_thresholds: a malformed or
    missing sidecar degrades to the default rather than raising -- a
    threshold-config error must never become a triage exception.
    """
    path = config_path or _TRIAGE_JUDGMENT_CONFIG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_DEEP_ANALYSIS_PROBABILITY_FLOOR
    if not isinstance(raw, dict):
        return DEFAULT_DEEP_ANALYSIS_PROBABILITY_FLOOR
    try:
        return float(
            raw.get("deep_analysis_floor", DEFAULT_DEEP_ANALYSIS_PROBABILITY_FLOOR)
        )
    except (TypeError, ValueError):
        return DEFAULT_DEEP_ANALYSIS_PROBABILITY_FLOOR

_STRUGGLE_LEVEL_CRITERIA = {
    "none": "No struggle signals -- the session proceeded cleanly.",
    "low": "Minor friction -- a retry or a single easily-resolved error.",
    "medium": "Moderate struggle -- repeated errors or a real correction.",
    "high": "Significant struggle -- the agent was clearly stuck or lost.",
}

_COMPACT_CONTENT_TYPES = (ContentType.TEXT, ContentType.THINKING, ContentType.TOOL_RESULT)
_COMPACT_ROLES = (EventRole.USER, EventRole.ASSISTANT, EventRole.TOOL)


def _compact_transcript(
    events: list[NormalizedEvent],
    *,
    max_chars: int = 8000,
) -> str:
    """Reduce a session's events to text a struggle judgment can read.

    Keeps only user/assistant/tool-result text content -- never a
    ``tool_use`` block's ``tool_input`` payload dict (that's the "tool
    payload" this helper must exclude). Truncates to *max_chars* from the
    end: the most recent turns are likeliest to explain a struggle.
    """
    lines: list[str] = []
    for event in events:
        if event.role not in _COMPACT_ROLES:
            continue
        for block in event.content:
            if block.type not in _COMPACT_CONTENT_TYPES:
                continue
            if not block.text:
                continue
            lines.append(f"[{event.role.value}] {block.text}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = "...(truncated)\n" + text[-max_chars:]
    return text


def _answer_field(answer: Any, name: str, default: Any = None) -> Any:
    """Read a field off a real SDK answer object or a plain dict/mapping."""
    if isinstance(answer, dict):
        return answer.get(name, default)
    return getattr(answer, name, default)


def _classify_session(
    counters: dict[str, int],
    transcript: str,
    *,
    session_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Ask one calibrated judgment for this session's classification.

    Returns ``{}`` on any unavailability (module missing, ``decide()``
    returns no usable answer) -- never raises, never guesses. Callers read
    individual fields with ``.get(name, default)``.

    ``dry_run`` (default ``True``, matching the CLI's own default) is
    threaded straight into ``decide()``'s own ``dry_run`` short-circuit:
    the CLI's documented "no API calls in dry-run mode" promise must hold
    for this call exactly as it does for every other one in this repo.
    """
    if system_one_decisions is None:
        return {}

    state = {"counters": dict(counters), "transcript": transcript}
    questions = {
        "struggle_level": {
            "type": "choice",
            "instructions": (
                "Given the signal counts and transcript excerpt, how much "
                "did the agent struggle in this session?"
            ),
            "criteria": _STRUGGLE_LEVEL_CRITERIA,
        },
        "deep_analysis": {
            "type": "noul",
            "instructions": "Does this session warrant deep analysis?",
        },
        "user_redirected": {
            "type": "noul",
            "instructions": "Did the user have to redirect the agent?",
        },
        "out_of_scope": {
            "type": "noul",
            "instructions": "Did the agent do out-of-scope work?",
        },
    }

    answers = system_one_decisions.decide(
        state, questions, site="collect-transcripts.triage", dry_run=dry_run,
    )
    if not answers:
        return {}

    result: dict[str, Any] = {}

    struggle_answer = answers.get("struggle_level") if hasattr(answers, "get") else None
    if struggle_answer is not None:
        level = _answer_field(struggle_answer, "choice")
        if level in _STRUGGLE_LEVELS:
            result["struggle_level"] = level

    deep_analysis_answer = answers.get("deep_analysis") if hasattr(answers, "get") else None
    if deep_analysis_answer is not None:
        p = _answer_field(deep_analysis_answer, "noul")
        if isinstance(p, (int, float)):
            result["flagged_for_deep_analysis"] = bool(p >= load_deep_analysis_floor())

    redirected_answer = answers.get("user_redirected") if hasattr(answers, "get") else None
    if redirected_answer is not None:
        p = _answer_field(redirected_answer, "noul")
        if isinstance(p, (int, float)):
            result["redirected_by_user"] = bool(p >= 0.5)

    out_of_scope_answer = answers.get("out_of_scope") if hasattr(answers, "get") else None
    if out_of_scope_answer is not None:
        p = _answer_field(out_of_scope_answer, "noul")
        if isinstance(p, (int, float)):
            result["out_of_scope_work"] = bool(p >= 0.5)

    return result


# ---------------------------------------------------------------------------
# Triage engine
# ---------------------------------------------------------------------------

def triage_session(
    events: list[NormalizedEvent],
    *,
    session_id: str = "",
    threshold: float = 5.0,
    dry_run: bool = True,
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
    dry_run:
        Forwarded to the judged classification call's own ``dry_run``
        short-circuit (default ``True``, matching the CLI's own default:
        no API calls unless explicitly disabled).

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
    flagged_for_deep_analysis = composite_score >= threshold

    # Sanitize before any text leaves the process (capability spec:
    # "Sanitization precedes any LLM analysis"). Only the compacted text
    # sent to the judgment is sanitized -- the counters above already ran
    # against the raw events and are unaffected by redaction either way
    # (tool_name/is_error/type are never touched by the sanitizer).
    sanitized_events, _redactions = sanitize_event_stream(events)

    # D1/D4: ask the judgment; unavailable/partial answers leave the
    # deterministic values above untouched field by field.
    judged = _classify_session(
        {
            "retry_count": retry_count,
            "tool_error_count": tool_error_count,
            "scope_violation_count": scope_violation_count,
            "user_correction_count": user_correction_count,
        },
        _compact_transcript(sanitized_events),
        session_id=session_id,
        dry_run=dry_run,
    )
    struggle_level = judged.get("struggle_level", struggle_level)
    flagged_for_deep_analysis = judged.get(
        "flagged_for_deep_analysis", flagged_for_deep_analysis
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
        flagged_for_deep_analysis=flagged_for_deep_analysis,
        redirected_by_user=judged.get("redirected_by_user"),
        out_of_scope_work=judged.get("out_of_scope_work"),
    )


def triage_sessions(
    sessions: dict[str, list[NormalizedEvent]],
    *,
    threshold: float = 5.0,
    dry_run: bool = True,
) -> list[TriageScore]:
    """Score multiple sessions.

    Parameters
    ----------
    sessions:
        Mapping of session_id -> events.
    threshold:
        Composite score threshold for flagging.
    dry_run:
        Forwarded to each session's judged classification call.

    Returns
    -------
    List of TriageScore, one per session.
    """
    return [
        triage_session(events, session_id=sid, threshold=threshold, dry_run=dry_run)
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
    lines.append("- Triage model calls: 0 (heuristic scoring, no LLM needed)")
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

    scores = triage_sessions(sessions, threshold=args.threshold, dry_run=args.dry_run)

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
