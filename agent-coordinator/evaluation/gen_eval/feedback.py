"""Feedback synthesizer for the generator-evaluator loop.

Analyzes evaluator verdicts and produces structured feedback to guide
the next generation iteration. Computes coverage summaries, identifies
failing interfaces, under-tested categories, and near-miss scenarios.
"""

from __future__ import annotations

import logging

from evaluation.gen_eval.descriptor import InterfaceDescriptor
from evaluation.gen_eval.models import EvalFeedback, ScenarioVerdict

logger = logging.getLogger(__name__)

# Thresholds
_UNDER_TESTED_THRESHOLD = 0.50  # category coverage below 50%
_NEAR_MISS_DURATION_S = 0.5  # scenarios slower than 500ms


class FeedbackSynthesizer:
    """Synthesize evaluator verdicts into generator guidance."""

    def synthesize(
        self,
        verdicts: list[ScenarioVerdict],
        descriptor: InterfaceDescriptor,
        previous_feedback: EvalFeedback | None = None,
    ) -> EvalFeedback:
        """Analyze verdicts and produce structured feedback.

        Computes:
        1. failing_interfaces: endpoint names that had fail verdicts
        2. under_tested_categories: categories with < 50% scenario coverage
        3. near_miss_scenarios: scenarios that passed but with > 500ms latency
           or had any step with a partial-match diff
        4. suggested_focus: areas to explore next (combines failing + under-tested)
        5. coverage_summary: interface -> coverage percentage
        """
        iteration = (previous_feedback.iteration + 1) if previous_feedback else 1

        failing = self._failing_interfaces(verdicts)
        under_tested = self._under_tested_categories(verdicts, descriptor)
        near_miss = self._near_miss_scenarios(verdicts)
        coverage = self._coverage_summary(verdicts, descriptor)
        se_focus = self._side_effect_failure_focus(verdicts)
        sem_focus = self._semantic_gap_focus(verdicts)
        focus = self._suggested_focus(failing, under_tested, se_focus, sem_focus)

        return EvalFeedback(
            iteration=iteration,
            failing_interfaces=failing,
            under_tested_categories=under_tested,
            near_miss_scenarios=near_miss,
            suggested_focus=focus,
            coverage_summary=coverage,
        )

    def to_prompt_text(self, feedback: EvalFeedback) -> str:
        """Format feedback as a prompt-compatible text block."""
        lines: list[str] = []
        lines.append(f"=== Evaluation Feedback (iteration {feedback.iteration}) ===")
        lines.append("")

        if feedback.failing_interfaces:
            lines.append("Failing interfaces:")
            for iface in feedback.failing_interfaces:
                lines.append(f"  - {iface}")
            lines.append("")

        if feedback.under_tested_categories:
            lines.append("Under-tested categories (< 50% coverage):")
            for cat in feedback.under_tested_categories:
                lines.append(f"  - {cat}")
            lines.append("")

        if feedback.near_miss_scenarios:
            lines.append("Near-miss scenarios (passed but risky):")
            for sc in feedback.near_miss_scenarios:
                lines.append(f"  - {sc}")
            lines.append("")

        if feedback.coverage_summary:
            lines.append("Coverage summary:")
            for iface, pct in sorted(feedback.coverage_summary.items()):
                lines.append(f"  {iface}: {pct:.1f}%")
            lines.append("")

        if feedback.suggested_focus:
            lines.append("Suggested focus for next iteration:")
            for area in feedback.suggested_focus:
                lines.append(f"  - {area}")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _failing_interfaces(verdicts: list[ScenarioVerdict]) -> list[str]:
        """Collect unique interface names from steps with status='fail'."""
        failing: set[str] = set()
        for v in verdicts:
            for step in v.steps:
                if step.status == "fail":
                    # Use the step's transport + endpoint as the interface id
                    # but also include any interfaces_tested from the verdict
                    failing.update(v.interfaces_tested)
        return sorted(failing)

    @staticmethod
    def _under_tested_categories(
        verdicts: list[ScenarioVerdict],
        descriptor: InterfaceDescriptor,
    ) -> list[str]:
        """Find categories with < 50% interface coverage.

        For each category present in verdicts, compute the ratio of
        unique interfaces exercised (from ``interfaces_tested`` on verdicts
        in that category) vs total interfaces in the descriptor.
        Categories where coverage < 50% are considered under-tested.
        """
        total_interfaces = descriptor.total_interface_count()
        if total_interfaces == 0:
            return []

        # Collect unique interfaces exercised per category
        category_interfaces: dict[str, set[str]] = {}
        for v in verdicts:
            cat = v.category
            if cat:
                category_interfaces.setdefault(cat, set()).update(v.interfaces_tested)

        under_tested: list[str] = []
        for cat, interfaces in sorted(category_interfaces.items()):
            ratio = len(interfaces) / total_interfaces
            if ratio < _UNDER_TESTED_THRESHOLD:
                under_tested.append(cat)

        return under_tested

    @staticmethod
    def _near_miss_scenarios(verdicts: list[ScenarioVerdict]) -> list[str]:
        """Find passed scenarios that are risky.

        A scenario is near-miss if it passed but:
        - duration > 500ms, OR
        - any step has a non-None diff (partial match)
        """
        near_miss: list[str] = []
        for v in verdicts:
            if v.status != "pass":
                continue
            is_near_miss = False
            # High latency (skip when duration is 0.0 — evaluator didn't set timing)
            if v.duration_seconds == 0.0:
                logger.debug(
                    "Skipping latency near-miss check for %s: duration not set",
                    v.scenario_id,
                )
            elif v.duration_seconds > _NEAR_MISS_DURATION_S:
                is_near_miss = True
            # Partial match: step passed but has diff
            for step in v.steps:
                if step.diff is not None and step.diff:
                    is_near_miss = True
                    break
            if is_near_miss:
                near_miss.append(v.scenario_id)
        return near_miss

    @staticmethod
    def _coverage_summary(
        verdicts: list[ScenarioVerdict],
        descriptor: InterfaceDescriptor,
    ) -> dict[str, float]:
        """Compute per-interface coverage percentage.

        Coverage = (1 if interface was exercised in any verdict, else 0)
        as a percentage of the total.
        """
        all_interfaces = descriptor.all_interfaces()
        if not all_interfaces:
            return {}

        exercised: set[str] = set()
        for v in verdicts:
            exercised.update(v.interfaces_tested)

        result: dict[str, float] = {}
        for iface in all_interfaces:
            result[iface] = 100.0 if iface in exercised else 0.0

        return result

    @staticmethod
    def _side_effect_failure_focus(verdicts: list[ScenarioVerdict]) -> list[str]:
        """Identify scenarios with side-effect failures as focus areas."""
        focus: list[str] = []
        for v in verdicts:
            for step in v.steps:
                if step.side_effect_verdicts:
                    for sev in step.side_effect_verdicts:
                        if sev.get("status") in ("fail", "error"):
                            focus.append(
                                f"side-effect failure in {v.scenario_id}:{step.step_id}"
                            )
                            break
        return focus

    @staticmethod
    def _semantic_gap_focus(verdicts: list[ScenarioVerdict]) -> list[str]:
        """Identify scenarios where semantic evaluation was skipped."""
        focus: list[str] = []
        for v in verdicts:
            for step in v.steps:
                if step.semantic_verdict and step.semantic_verdict.status == "skip":
                    focus.append(
                        f"semantic evaluation skipped in {v.scenario_id}:{step.step_id}"
                    )
        return focus

    @staticmethod
    def _suggested_focus(
        failing: list[str],
        under_tested: list[str],
        side_effect_focus: list[str] | None = None,
        semantic_focus: list[str] | None = None,
    ) -> list[str]:
        """Union of failing interfaces, under-tested categories, and extended focus areas."""
        seen: set[str] = set()
        focus: list[str] = []
        for item in failing + under_tested + (side_effect_focus or []) + (semantic_focus or []):
            if item not in seen:
                seen.add(item)
                focus.append(item)
        return focus
