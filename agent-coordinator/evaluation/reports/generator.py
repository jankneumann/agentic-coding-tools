"""Report generator for evaluation results.

Produces structured reports in markdown and JSON format with
per-task results, per-config summaries, ablation comparisons,
and statistical significance indicators.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..ablation import interpret_effect_size
from ..metrics import (
    TaskMetrics,
    TrialMetrics,
    compute_effect_size,
)


class ReportGenerator:
    """Generates evaluation reports from collected metrics."""

    def __init__(self, output_dir: str | Path) -> None:
        self._output_dir = Path(output_dir)

    def generate(
        self,
        task_metrics: list[TaskMetrics],
        trial_metrics: list[TrialMetrics],
        run_id: str,
        config_summary: dict[str, Any] | None = None,
        consensus_results: list[dict[str, Any]] | None = None,
    ) -> tuple[Path, Path]:
        """Generate both markdown and JSON reports.

        Returns:
            Tuple of (markdown_path, json_path).
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)

        md_path = self._output_dir / f"{run_id}.md"
        json_path = self._output_dir / f"{run_id}.json"

        md_content = self._generate_markdown(
            task_metrics, trial_metrics, run_id, config_summary, consensus_results
        )
        md_path.write_text(md_content)

        json_content = self._generate_json(
            task_metrics, trial_metrics, run_id, config_summary, consensus_results
        )
        json_path.write_text(json.dumps(json_content, indent=2))

        return md_path, json_path

    def _generate_markdown(
        self,
        task_metrics: list[TaskMetrics],
        trial_metrics: list[TrialMetrics],
        run_id: str,
        config_summary: dict[str, Any] | None = None,
        consensus_results: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate a markdown evaluation report."""
        lines: list[str] = []
        now = datetime.now(UTC).isoformat()

        lines.append(f"# Evaluation Report: {run_id}")
        lines.append(f"\nGenerated: {now}\n")

        if config_summary:
            lines.append("## Configuration\n")
            for key, val in config_summary.items():
                lines.append(f"- **{key}**: {val}")
            lines.append("")

        # Summary table
        lines.append("## Summary\n")
        lines.append(
            "| Task | Backend | Config | Trials | Success Rate "
            "| Wall Clock (s) | Tokens | Cost ($) |"
        )
        lines.append(
            "|------|---------|--------|--------|-------------|"
            "----------------|--------|----------|"
        )
        for tm in trial_metrics:
            lines.append(
                f"| {tm.task_id} | {tm.backend_name} | {tm.ablation_label} "
                f"| {tm.num_trials} | {tm.success_rate:.0%} "
                f"| {tm.wall_clock.mean:.1f} "
                f"({tm.wall_clock.ci_lower:.1f}-{tm.wall_clock.ci_upper:.1f}) "
                f"| {tm.total_tokens.mean:.0f} "
                f"| {tm.cost_usd.mean:.4f} |"
            )
        lines.append("")

        # Ablation comparison
        ablation_labels = sorted(set(tm.ablation_label for tm in trial_metrics))
        if len(ablation_labels) > 1:
            lines.append("## Ablation Comparison\n")
            lines.append(self._ablation_comparison_table(trial_metrics, ablation_labels))
            lines.append("")

        # Per-task breakdown
        lines.append("## Per-Task Results\n")
        for tm in trial_metrics:
            lines.append(f"### {tm.task_id} ({tm.backend_name}, {tm.ablation_label})\n")
            lines.append(f"- **Trials**: {tm.num_trials}")
            lines.append(f"- **Success rate**: {tm.success_rate:.0%}")
            lines.append(f"- **Wall clock**: {tm.wall_clock.mean:.1f}s "
                         f"(CI: {tm.wall_clock.ci_lower:.1f}-{tm.wall_clock.ci_upper:.1f})")
            lines.append(f"- **Test pass rate**: {tm.test_pass_rate.mean:.0%}")
            lines.append(f"- **Coordination overhead**: {tm.coordination_overhead.mean:.1f}%")
            lines.append(f"- **Speedup factor**: {tm.speedup_factor.mean:.2f}")
            # Safety metrics from raw data
            matching_raw = [
                m for m in task_metrics
                if m.task_id == tm.task_id
                and m.backend_name == tm.backend_name
                and m.ablation_label == tm.ablation_label
            ]
            if matching_raw:
                total_guardrail = sum(
                    m.safety.guardrail_checks for m in matching_raw
                )
                total_blocks = sum(
                    m.safety.guardrail_blocks for m in matching_raw
                )
                total_audit = sum(
                    m.safety.audit_entries_written for m in matching_raw
                )
                if total_guardrail > 0 or total_audit > 0:
                    lines.append(
                        f"- **Guardrail checks**: {total_guardrail} "
                        f"({total_blocks} blocked)"
                    )
                    lines.append(f"- **Audit entries**: {total_audit}")
            lines.append("")

        # Consensus evaluation results
        if consensus_results:
            lines.append("## Consensus Evaluation\n")
            for cr in consensus_results:
                lines.append(f"### {cr.get('task_id', 'unknown')}\n")
                for judge, score in cr.get("scores", {}).items():
                    lines.append(f"- **{judge}**: {score}")
                agreement = cr.get("agreement_rate", 0)
                lines.append(f"- **Agreement rate**: {agreement:.0%}")
                if cr.get("disagreement"):
                    lines.append(f"- **Disagreement flagged**: {cr['disagreement']}")
                lines.append("")

        return "\n".join(lines)

    def _ablation_comparison_table(
        self,
        trial_metrics: list[TrialMetrics],
        ablation_labels: list[str],
    ) -> str:
        """Generate ablation comparison with effect sizes."""
        lines: list[str] = []

        # Group by task for cross-config comparison
        tasks = sorted(set(tm.task_id for tm in trial_metrics))

        lines.append("| Task | Config A | Config B | Metric | Effect Size | Interpretation |")
        lines.append("|------|----------|----------|--------|-------------|----------------|")

        baseline_label = "all-on" if "all-on" in ablation_labels else ablation_labels[0]

        for task_id in tasks:
            task_trials = [tm for tm in trial_metrics if tm.task_id == task_id]
            baseline = next(
                (tm for tm in task_trials if tm.ablation_label == baseline_label), None
            )
            if not baseline:
                continue

            for other in task_trials:
                if other.ablation_label == baseline_label:
                    continue
                # Compare wall clock times
                d = compute_effect_size(
                    [baseline.wall_clock.mean], [other.wall_clock.mean]
                )
                interp = interpret_effect_size(d)
                lines.append(
                    f"| {task_id} | {baseline_label} | {other.ablation_label} "
                    f"| wall_clock | {d:.2f} | {interp} |"
                )

        return "\n".join(lines)

    def _generate_json(
        self,
        task_metrics: list[TaskMetrics],
        trial_metrics: list[TrialMetrics],
        run_id: str,
        config_summary: dict[str, Any] | None = None,
        consensus_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate a JSON evaluation report."""
        return {
            "metadata": {
                "run_id": run_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "config": config_summary or {},
            },
            "raw_metrics": [tm.to_dict() for tm in task_metrics],
            "trial_summaries": [tm.to_dict() for tm in trial_metrics],
            "consensus_results": consensus_results or [],
        }
