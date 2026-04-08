"""Process analysis artifact generation.

Generates process-analysis.md and process-analysis.json summarizing
convergence behavior for a change: loops taken, repeated findings,
flaky scenarios, time to first pass, churn, and failure classes.

Design Decision D5: Process analysis is a first-class optional artifact
generated during validation. Cleanup and merge gates consume it
read-only. Archive mining benefits from explicit process outcomes.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IterationRecord:
    """Record of a single validation/iteration loop."""

    iteration: int
    timestamp: str = ""
    scenarios_run: int = 0
    scenarios_passed: int = 0
    scenarios_failed: int = 0
    findings_addressed: int = 0
    findings_deferred: int = 0
    new_findings: int = 0


@dataclass
class ProcessAnalysis:
    """Convergence analysis for a change's validation lifecycle."""

    change_id: str
    generated_at: str = ""
    iterations: list[IterationRecord] = field(default_factory=list)
    total_loops: int = 0
    time_to_first_pass_minutes: float | None = None
    flaky_scenarios: list[str] = field(default_factory=list)
    repeated_findings: list[str] = field(default_factory=list)
    file_churn: dict[str, int] = field(default_factory=dict)
    resolved_count: int = 0
    deferred_count: int = 0
    missing_artifacts: list[str] = field(default_factory=list)

    @property
    def convergence_rate(self) -> float:
        """Ratio of resolved to total findings."""
        total = self.resolved_count + self.deferred_count
        if total == 0:
            return 1.0
        return self.resolved_count / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "generated_at": self.generated_at,
            "total_loops": self.total_loops,
            "time_to_first_pass_minutes": self.time_to_first_pass_minutes,
            "convergence_rate": round(self.convergence_rate, 3),
            "resolved_count": self.resolved_count,
            "deferred_count": self.deferred_count,
            "flaky_scenarios": self.flaky_scenarios,
            "repeated_findings": self.repeated_findings,
            "file_churn": self.file_churn,
            "missing_artifacts": self.missing_artifacts,
            "iterations": [
                {
                    "iteration": it.iteration,
                    "timestamp": it.timestamp,
                    "scenarios_run": it.scenarios_run,
                    "scenarios_passed": it.scenarios_passed,
                    "scenarios_failed": it.scenarios_failed,
                    "findings_addressed": it.findings_addressed,
                    "findings_deferred": it.findings_deferred,
                    "new_findings": it.new_findings,
                }
                for it in self.iterations
            ],
        }


def generate_process_analysis(
    change_id: str,
    validation_report_path: Path | None = None,
    session_log_path: Path | None = None,
    impl_findings_path: Path | None = None,
    rework_report_path: Path | None = None,
) -> ProcessAnalysis:
    """Generate process analysis from available artifacts.

    Tolerates missing optional artifacts — records them as absent
    rather than failing (spec scenario: skill-workflow.2.2).

    Args:
        change_id: The OpenSpec change ID.
        validation_report_path: Path to validation-report.md.
        session_log_path: Path to session-log.md.
        impl_findings_path: Path to impl-findings.md.
        rework_report_path: Path to rework-report.json.

    Returns:
        ProcessAnalysis with available data populated.
    """
    analysis = ProcessAnalysis(
        change_id=change_id,
        generated_at=datetime.now(UTC).isoformat(),
    )

    missing: list[str] = []

    # Parse validation report for iteration data
    if validation_report_path and validation_report_path.exists():
        _parse_validation_report(analysis, validation_report_path)
    elif validation_report_path:
        missing.append("validation-report.md")

    # Parse session log for timing and loop counts
    if session_log_path and session_log_path.exists():
        _parse_session_log(analysis, session_log_path)
    elif session_log_path:
        missing.append("session-log.md")

    # Parse impl findings for resolved/deferred counts
    if impl_findings_path and impl_findings_path.exists():
        _parse_impl_findings(analysis, impl_findings_path)
    elif impl_findings_path:
        missing.append("impl-findings.md")

    # Parse rework report for failure routing
    if rework_report_path and rework_report_path.exists():
        _parse_rework_report(analysis, rework_report_path)
    elif rework_report_path:
        missing.append("rework-report.json")

    analysis.missing_artifacts = missing
    return analysis


def write_process_analysis(analysis: ProcessAnalysis, output_dir: Path) -> tuple[Path, Path]:
    """Write process analysis as both markdown and JSON.

    Returns:
        Tuple of (markdown_path, json_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / "process-analysis.md"
    md_path.write_text(_render_markdown(analysis))

    json_path = output_dir / "process-analysis.json"
    with open(json_path, "w") as f:
        json.dump(analysis.to_dict(), f, indent=2)

    return md_path, json_path


def _parse_validation_report(analysis: ProcessAnalysis, path: Path) -> None:
    """Extract iteration and pass/fail data from validation report."""
    content = path.read_text()
    # Count iteration sections
    iterations = re.findall(r"## (?:Iteration|Run)\s+(\d+)", content)
    if iterations:
        analysis.total_loops = len(iterations)

    # Count pass/fail mentions
    passes = len(re.findall(r"\*\*Status\*\*:\s*pass", content))
    fails = len(re.findall(r"\*\*Status\*\*:\s*fail", content))
    if passes + fails > 0:
        analysis.iterations.append(
            IterationRecord(
                iteration=1,
                scenarios_passed=passes,
                scenarios_failed=fails,
                scenarios_run=passes + fails,
            )
        )


def _parse_session_log(analysis: ProcessAnalysis, path: Path) -> None:
    """Extract timing and phase data from session log."""
    # Session logs vary in format; extract what we can
    content = path.read_text()

    # Count phase entries
    phases = re.findall(r"## Phase:", content)
    if phases and analysis.total_loops == 0:
        analysis.total_loops = len(phases)


def _parse_impl_findings(analysis: ProcessAnalysis, path: Path) -> None:
    """Extract resolved/deferred finding counts from impl findings."""
    content = path.read_text()

    resolved = len(re.findall(r"- \[x\]", content))
    deferred = len(re.findall(r"- \[ \]", content))
    analysis.resolved_count = resolved
    analysis.deferred_count = deferred

    # Repeated findings
    findings = re.findall(r"- \[.\]\s+(.+)", content)
    seen: dict[str, int] = {}
    for finding in findings:
        key = finding.strip()[:50]  # Normalize
        seen[key] = seen.get(key, 0) + 1
    analysis.repeated_findings = [k for k, v in seen.items() if v > 1]


def _parse_rework_report(analysis: ProcessAnalysis, path: Path) -> None:
    """Extract failure routing from rework report JSON."""
    try:
        with open(path) as f:
            data = json.load(f)
        failures = data.get("failures", [])
        # Track which scenarios appear multiple times (flaky)
        ids = [f.get("scenario_id", "") for f in failures]
        seen: dict[str, int] = {}
        for sid in ids:
            seen[sid] = seen.get(sid, 0) + 1
        analysis.flaky_scenarios = [k for k, v in seen.items() if v > 1]
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to parse rework report %s: %s", path, e)


def _render_markdown(analysis: ProcessAnalysis) -> str:
    """Render process analysis as markdown."""
    lines: list[str] = []
    lines.append(f"# Process Analysis: {analysis.change_id}")
    lines.append("")
    lines.append(f"**Generated**: {analysis.generated_at}")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total loops**: {analysis.total_loops}")
    if analysis.time_to_first_pass_minutes is not None:
        lines.append(f"- **Time to first pass**: {analysis.time_to_first_pass_minutes:.1f} min")
    lines.append(f"- **Convergence rate**: {analysis.convergence_rate:.1%}")
    lines.append(f"- **Resolved findings**: {analysis.resolved_count}")
    lines.append(f"- **Deferred findings**: {analysis.deferred_count}")
    lines.append("")

    if analysis.flaky_scenarios:
        lines.append("## Flaky Scenarios")
        lines.append("")
        for s in analysis.flaky_scenarios:
            lines.append(f"- `{s}`")
        lines.append("")

    if analysis.repeated_findings:
        lines.append("## Repeated Findings")
        lines.append("")
        for f in analysis.repeated_findings:
            lines.append(f"- {f}")
        lines.append("")

    if analysis.file_churn:
        lines.append("## File Churn")
        lines.append("")
        lines.append("| File | Changes |")
        lines.append("|------|---------|")
        for f, count in sorted(analysis.file_churn.items(), key=lambda x: -x[1]):
            lines.append(f"| {f} | {count} |")
        lines.append("")

    if analysis.missing_artifacts:
        lines.append("## Missing Artifacts")
        lines.append("")
        for a in analysis.missing_artifacts:
            lines.append(f"- {a} (absent)")
        lines.append("")

    if analysis.iterations:
        lines.append("## Iteration Details")
        lines.append("")
        lines.append("| # | Run | Pass | Fail | Addressed | Deferred | New |")
        lines.append("|---|-----|------|------|-----------|----------|-----|")
        for it in analysis.iterations:
            lines.append(
                f"| {it.iteration} | {it.scenarios_run} | {it.scenarios_passed} "
                f"| {it.scenarios_failed} | {it.findings_addressed} "
                f"| {it.findings_deferred} | {it.new_findings} |"
            )
        lines.append("")

    return "\n".join(lines)
