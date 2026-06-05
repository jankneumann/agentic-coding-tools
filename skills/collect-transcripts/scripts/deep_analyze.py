"""Deep analysis for flagged session transcripts.

Runs on sessions flagged by the triage pass.  Produces structured findings
under the D4 tag schema with ``source:transcript-mined``.

The deep-analysis model is resolved via the archetype system (default
archetype: reviewer, default provider: claude_code).  In ``--dry-run``
mode, no API calls are made.

The analysis extracts:
- Failure patterns (retry storms, tool-error sequences)
- Capability gaps (what the harness was missing)
- Affected skills
- Severity assessment
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
from triage import TriageScore  # noqa: E402


# ---------------------------------------------------------------------------
# Finding schema (matches D4 tag schema)
# ---------------------------------------------------------------------------

VALID_FAILURE_TYPES = {
    "scope_violation",
    "verification_failed",
    "lock_unavailable",
    "timeout",
    "convergence_failed",
    "context_exhaustion",
    "tool_error",
    "retry_storm",
    "user_correction",
}

VALID_SEVERITIES = {"low", "medium", "high", "critical"}


@dataclass
class TranscriptFinding:
    """A structured finding from deep analysis of a session transcript.

    Fields match the D4 tag schema so findings can be written to episodic
    memory via the ``remember`` MCP tool.
    """
    session_id: str = ""
    failure_type: str = ""  # from VALID_FAILURE_TYPES
    capability_gap: str = ""
    affected_skill: str = ""
    severity: str = "low"  # from VALID_SEVERITIES
    source: str = "transcript-mined"
    description: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_memory_tags(self) -> list[str]:
        """Convert to the D4 episodic memory tag format."""
        tags = [
            f"failure_type:{self.failure_type}",
            f"capability_gap:{self.capability_gap}",
            f"affected_skill:{self.affected_skill}",
            f"severity:{self.severity}",
            f"source:{self.source}",
        ]
        return tags

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TranscriptFinding:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Heuristic deep analysis (no LLM — pattern matching)
# ---------------------------------------------------------------------------

def analyze_session_heuristic(
    events: list[NormalizedEvent],
    triage_score: TriageScore,
) -> list[TranscriptFinding]:
    """Extract findings from a session using heuristic pattern matching.

    This is the offline-capable analysis path that does not require an LLM.
    For full LLM-powered analysis, use ``analyze_session_llm()`` (which
    requires an archetype-resolved model).
    """
    findings: list[TranscriptFinding] = []
    session_id = triage_score.session_id

    # --- Retry storm detection ---
    if triage_score.retry_count >= 3:
        # Identify the most retried tool
        tool_counts: dict[str, int] = {}
        for event in events:
            if event.role == EventRole.ASSISTANT:
                for block in event.content:
                    if block.type == ContentType.TOOL_USE:
                        tool_counts[block.tool_name] = (
                            tool_counts.get(block.tool_name, 0) + 1
                        )
        if tool_counts:
            most_retried = max(tool_counts, key=tool_counts.get)  # type: ignore[arg-type]
            findings.append(
                TranscriptFinding(
                    session_id=session_id,
                    failure_type="retry_storm",
                    capability_gap=f"Agent retried {most_retried} {tool_counts[most_retried]} times",
                    affected_skill=_infer_skill(events),
                    severity="high" if triage_score.retry_count >= 5 else "medium",
                    description=(
                        f"Detected retry storm: tool {most_retried} was called "
                        f"{tool_counts[most_retried]} times (consecutive retries: "
                        f"{triage_score.retry_count})"
                    ),
                    evidence=[
                        f"retry_count={triage_score.retry_count}",
                        f"most_retried_tool={most_retried}",
                    ],
                )
            )

    # --- Tool error pattern ---
    if triage_score.tool_error_count >= 2:
        error_tools: list[str] = []
        for event in events:
            if event.role == EventRole.TOOL:
                for block in event.content:
                    if block.type == ContentType.TOOL_RESULT and block.is_error:
                        error_tools.append(block.text[:100])
        findings.append(
            TranscriptFinding(
                session_id=session_id,
                failure_type="tool_error",
                capability_gap="Multiple tool errors during session",
                affected_skill=_infer_skill(events),
                severity="high" if triage_score.tool_error_count >= 4 else "medium",
                description=(
                    f"Session had {triage_score.tool_error_count} tool errors"
                ),
                evidence=error_tools[:5],  # cap evidence
            )
        )

    # --- Scope violation pattern ---
    if triage_score.scope_violation_count >= 1:
        findings.append(
            TranscriptFinding(
                session_id=session_id,
                failure_type="scope_violation",
                capability_gap="Agent attempted out-of-scope operations",
                affected_skill=_infer_skill(events),
                severity="medium",
                description=(
                    f"Detected {triage_score.scope_violation_count} scope violation(s)"
                ),
                evidence=[
                    f"scope_violation_count={triage_score.scope_violation_count}"
                ],
            )
        )

    # --- User correction pattern ---
    if triage_score.user_correction_count >= 2:
        findings.append(
            TranscriptFinding(
                session_id=session_id,
                failure_type="user_correction",
                capability_gap="Agent required multiple user corrections",
                affected_skill=_infer_skill(events),
                severity="medium",
                description=(
                    f"User corrected the agent {triage_score.user_correction_count} time(s)"
                ),
                evidence=[
                    f"user_correction_count={triage_score.user_correction_count}"
                ],
            )
        )

    return findings


def _infer_skill(events: list[NormalizedEvent]) -> str:
    """Attempt to infer the skill being used from event content.

    Returns "unknown" if unable to determine.
    """
    # Look for skill references in user messages or metadata
    for event in events:
        if event.role == EventRole.USER:
            for block in event.content:
                text = block.text.lower()
                # Common skill name patterns
                for skill_name in [
                    "implement-feature",
                    "plan-feature",
                    "validate-feature",
                    "cleanup-feature",
                    "collect-transcripts",
                    "improve-harness",
                    "agent-metrics",
                ]:
                    if skill_name in text:
                        return skill_name
        # Check metadata
        if "skill" in event.metadata:
            return str(event.metadata["skill"])
    return "unknown"


# ---------------------------------------------------------------------------
# Dry-run report
# ---------------------------------------------------------------------------

def dry_run_findings_report(findings: list[TranscriptFinding]) -> str:
    """Generate a dry-run report of findings.

    Prints what WOULD be written to episodic memory without actually writing.
    """
    lines: list[str] = []
    lines.append("# Deep Analysis — Dry Run Report")
    lines.append("")
    lines.append(f"Findings: {len(findings)}")
    lines.append("")

    if findings:
        lines.append("## Findings (would be written to episodic memory)")
        lines.append("")
        for i, f in enumerate(findings, 1):
            lines.append(f"### {i}. [{f.severity.upper()}] {f.failure_type}")
            lines.append(f"- **Session**: {f.session_id}")
            lines.append(f"- **Gap**: {f.capability_gap}")
            lines.append(f"- **Skill**: {f.affected_skill}")
            lines.append(f"- **Source**: {f.source}")
            lines.append(f"- **Description**: {f.description}")
            if f.evidence:
                lines.append(f"- **Evidence**: {'; '.join(f.evidence[:3])}")
            lines.append(f"- **Tags**: {', '.join(f.to_memory_tags())}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deep analysis of flagged session transcripts"
    )
    parser.add_argument(
        "--events-file",
        type=str,
        help="Path to a JSONL events file",
    )
    parser.add_argument(
        "--triage-file",
        type=str,
        help="Path to triage scores JSON file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Print findings without writing to memory (default: True)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output findings as JSON",
    )
    args = parser.parse_args()

    if not args.events_file:
        print("Error: --events-file is required", file=sys.stderr)
        return 1

    events = _load_events_file(Path(args.events_file))
    if not events:
        print("No events loaded.", file=sys.stderr)
        return 0

    # Load or create triage score
    triage_score = TriageScore(
        session_id=events[0].session_id,
        event_count=len(events),
    )
    if args.triage_file:
        try:
            data = json.loads(Path(args.triage_file).read_text())
            triage_score = TriageScore.from_dict(data)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Warning: failed to load triage: {exc}", file=sys.stderr)

    # Run heuristic analysis
    findings = analyze_session_heuristic(events, triage_score)

    if args.json:
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        report = dry_run_findings_report(findings)
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
