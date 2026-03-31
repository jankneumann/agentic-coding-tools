"""Report generation for gen-eval runs.

Produces structured reports in markdown and JSON formats from
GenEvalReport data. Reports include pass/fail summaries, coverage
metrics, per-interface and per-category breakdowns, and cost summaries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from evaluation.gen_eval.models import ScenarioVerdict
from evaluation.metrics import GenEvalMetrics


@dataclass
class GenEvalReport:
    """Complete gen-eval run report."""

    total_scenarios: int
    passed: int
    failed: int
    errors: int
    skipped: int
    pass_rate: float
    coverage_pct: float  # unique interfaces tested / total * 100
    duration_seconds: float
    budget_exhausted: bool
    verdicts: list[ScenarioVerdict]
    per_interface: dict[str, dict]  # interface -> {pass, fail, error counts}
    per_category: dict[str, dict]  # category -> {pass, fail, error, total}
    unevaluated_interfaces: list[str]
    cost_summary: dict[str, float]  # cli_calls, time_minutes, sdk_cost_usd
    iterations_completed: int

    def to_metrics(self) -> list[GenEvalMetrics]:
        """Convert verdicts to GenEvalMetrics for integration with MetricsCollector."""
        metrics: list[GenEvalMetrics] = []
        for v in self.verdicts:
            primary_interface = v.interfaces_tested[0] if v.interfaces_tested else "unknown"
            metrics.append(
                GenEvalMetrics(
                    scenario_id=v.scenario_id,
                    interface=primary_interface,
                    verdict=v.status,
                    duration_seconds=v.duration_seconds,
                    category=v.category or "uncategorized",
                    backend_used=v.backend_used,
                )
            )
        return metrics


def generate_markdown_report(report: GenEvalReport) -> str:
    """Generate a markdown-formatted report."""
    lines: list[str] = []

    lines.append("# Gen-Eval Report")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total scenarios**: {report.total_scenarios}")
    lines.append(f"- **Passed**: {report.passed}")
    lines.append(f"- **Failed**: {report.failed}")
    lines.append(f"- **Errors**: {report.errors}")
    lines.append(f"- **Skipped**: {report.skipped}")
    lines.append(f"- **Pass rate**: {report.pass_rate:.1%}")
    lines.append(f"- **Coverage**: {report.coverage_pct:.1f}%")
    lines.append(f"- **Duration**: {report.duration_seconds:.1f}s")
    lines.append(f"- **Iterations completed**: {report.iterations_completed}")
    lines.append(f"- **Budget exhausted**: {report.budget_exhausted}")
    lines.append("")

    # Cost summary
    lines.append("## Cost Summary")
    lines.append("")
    lines.append(f"- **CLI calls**: {int(report.cost_summary.get('cli_calls', 0))}")
    lines.append(f"- **Time**: {report.cost_summary.get('time_minutes', 0):.1f} minutes")
    lines.append(f"- **SDK cost**: ${report.cost_summary.get('sdk_cost_usd', 0):.2f}")
    lines.append("")

    # Per-interface breakdown
    if report.per_interface:
        lines.append("## Per-Interface Results")
        lines.append("")
        lines.append("| Interface | Pass | Fail | Error |")
        lines.append("|-----------|------|------|-------|")
        for iface, counts in sorted(report.per_interface.items()):
            lines.append(
                f"| {iface} | {counts.get('pass', 0)} "
                f"| {counts.get('fail', 0)} "
                f"| {counts.get('error', 0)} |"
            )
        lines.append("")

    # Per-category breakdown
    if report.per_category:
        lines.append("## Per-Category Results")
        lines.append("")
        lines.append("| Category | Total | Pass | Fail | Error |")
        lines.append("|----------|-------|------|------|-------|")
        for cat, counts in sorted(report.per_category.items()):
            lines.append(
                f"| {cat} | {counts.get('total', 0)} "
                f"| {counts.get('pass', 0)} "
                f"| {counts.get('fail', 0)} "
                f"| {counts.get('error', 0)} |"
            )
        lines.append("")

    # Unevaluated interfaces
    if report.unevaluated_interfaces:
        lines.append("## Unevaluated Interfaces")
        lines.append("")
        for iface in report.unevaluated_interfaces:
            lines.append(f"- {iface}")
        lines.append("")

    # Failed scenarios
    failed_verdicts = [v for v in report.verdicts if v.status in ("fail", "error")]
    if failed_verdicts:
        lines.append("## Failed Scenarios")
        lines.append("")
        for v in failed_verdicts:
            lines.append(f"### {v.scenario_name} (`{v.scenario_id}`)")
            lines.append("")
            lines.append(f"- **Status**: {v.status}")
            lines.append(f"- **Category**: {v.category}")
            lines.append(f"- **Duration**: {v.duration_seconds:.3f}s")
            if v.failure_summary:
                lines.append(f"- **Failure**: {v.failure_summary}")
            lines.append("")

    return "\n".join(lines)


def generate_json_report(report: GenEvalReport) -> str:
    """Generate a JSON-formatted report."""
    data: dict = {
        "total_scenarios": report.total_scenarios,
        "passed": report.passed,
        "failed": report.failed,
        "errors": report.errors,
        "skipped": report.skipped,
        "pass_rate": report.pass_rate,
        "coverage_pct": report.coverage_pct,
        "duration_seconds": report.duration_seconds,
        "budget_exhausted": report.budget_exhausted,
        "iterations_completed": report.iterations_completed,
        "cost_summary": report.cost_summary,
        "per_interface": report.per_interface,
        "per_category": report.per_category,
        "unevaluated_interfaces": report.unevaluated_interfaces,
        "verdicts": [v.model_dump() for v in report.verdicts],
    }
    return json.dumps(data, indent=2, default=str)
