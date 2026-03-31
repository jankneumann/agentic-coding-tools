"""Top-level orchestrator for generator-evaluator runs.

Manages the full gen-eval pipeline: service lifecycle, scenario generation,
budget-aware prioritization, parallel evaluation, feedback loops, and
report generation. Ensures teardown always runs, even on failure.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import time

from evaluation.gen_eval.change_detector import ChangeDetector
from evaluation.gen_eval.config import BudgetTracker, GenEvalConfig
from evaluation.gen_eval.descriptor import InterfaceDescriptor
from evaluation.gen_eval.evaluator import Evaluator
from evaluation.gen_eval.feedback import FeedbackSynthesizer
from evaluation.gen_eval.models import (
    EvalFeedback,
    Scenario,
    ScenarioGenerator,
    ScenarioVerdict,
)
from evaluation.gen_eval.reports import GenEvalReport

logger = logging.getLogger(__name__)


class HealthCheckError(Exception):
    """Raised when the service health check fails after all retries."""


class GenEvalOrchestrator:
    """Top-level orchestrator for generator-evaluator runs."""

    def __init__(
        self,
        config: GenEvalConfig,
        descriptor: InterfaceDescriptor,
        generator: ScenarioGenerator,
        evaluator: Evaluator,
        feedback_synthesizer: FeedbackSynthesizer | None = None,
        change_detector: ChangeDetector | None = None,
    ) -> None:
        self.config = config
        self.descriptor = descriptor
        self.generator = generator
        self.evaluator = evaluator
        self.feedback_synthesizer = feedback_synthesizer or FeedbackSynthesizer()
        self.change_detector = change_detector
        self.budget_tracker: BudgetTracker = config.build_budget_tracker()
        self._budget_exhausted = False

    async def run(self) -> GenEvalReport:
        """Execute the full gen-eval pipeline.

        1. Start services (docker-compose up, health check with retry+backoff)
        2. Seed data if configured
        3. Generate scenarios (template + LLM within budget)
        4. Prioritize by budget tier
        5. Evaluate scenarios (parallel via asyncio.Semaphore(N))
        6. Synthesize feedback
        7. If budget remains and iterations configured: loop to step 3
        8. Generate report
        9. Teardown services
        """
        start_time = time.monotonic()
        all_verdicts: list[ScenarioVerdict] = []
        iterations_completed = 0
        feedback: EvalFeedback | None = None

        try:
            # 1. Start services
            self._run_startup()
            await self._health_check()

            # 2. Seed data
            self._seed_data()

            # 3-7. Iteration loop
            for iteration in range(self.config.max_iterations):
                if not self.budget_tracker.can_continue():
                    self._budget_exhausted = True
                    logger.info("Budget exhausted before iteration %d", iteration + 1)
                    break

                # 3. Generate scenarios
                focus_areas: list[str] | None = None
                if feedback:
                    focus_areas = feedback.suggested_focus or None

                scenarios = await self.generator.generate(
                    focus_areas=focus_areas,
                    count=self.config.max_scenarios_per_iteration,
                )

                # 4. Prioritize
                scenarios = self._prioritize_scenarios(scenarios)

                # 5. Evaluate in parallel
                verdicts = await self._evaluate_parallel(scenarios)
                all_verdicts.extend(verdicts)

                iterations_completed += 1

                # 6. Synthesize feedback
                feedback = self.feedback_synthesizer.synthesize(verdicts, self.descriptor, feedback)

                # 7. Check budget for next iteration
                if not self.budget_tracker.can_continue():
                    self._budget_exhausted = True
                    logger.info("Budget exhausted after iteration %d", iteration + 1)
                    break

        finally:
            # 9. Always teardown
            self._run_teardown()

        # 8. Generate report
        duration = time.monotonic() - start_time
        return self._build_report(all_verdicts, duration, iterations_completed)

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def _run_startup(self) -> None:
        """Run the startup command from the descriptor.

        Security: The command is executed with ``shell=True`` and comes directly
        from the interface descriptor file.  Descriptor files must be treated as
        trusted input — never load a descriptor from an untrusted source.
        """
        cmd = self.descriptor.startup.command
        logger.info("Starting services: %s", cmd)
        subprocess.run(cmd, shell=True, check=True, capture_output=True, timeout=120)

    async def _health_check(self) -> None:
        """Poll the health check endpoint with retry and exponential backoff."""
        health_target = self.descriptor.startup.health_check
        retries = self.config.health_check_retries
        interval = self.config.health_check_interval_seconds

        for attempt in range(retries):
            try:
                result = subprocess.run(
                    ["curl", "-sf", health_target],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    logger.info("Health check passed on attempt %d", attempt + 1)
                    return
            except (subprocess.SubprocessError, OSError):
                pass

            if attempt < retries - 1:
                backoff = interval * (2**attempt)
                logger.info(
                    "Health check attempt %d/%d failed, retrying in %.1fs",
                    attempt + 1,
                    retries,
                    backoff,
                )
                await asyncio.sleep(backoff)

        raise HealthCheckError(f"Health check failed after {retries} attempts: {health_target}")

    def _seed_data(self) -> None:
        """Run seed command if configured.

        Security: The command is executed with ``shell=True`` and comes directly
        from the interface descriptor file.  Descriptor files must be treated as
        trusted input — never load a descriptor from an untrusted source.
        """
        seed_cmd = self.descriptor.startup.seed_command
        if not seed_cmd or not self.config.seed_data:
            return
        logger.info("Seeding data: %s", seed_cmd)
        subprocess.run(seed_cmd, shell=True, check=True, capture_output=True, timeout=120)

    def _run_teardown(self) -> None:
        """Run teardown command. Always called, even on failure.

        Security: The command is executed with ``shell=True`` and comes directly
        from the interface descriptor file.  Descriptor files must be treated as
        trusted input — never load a descriptor from an untrusted source.
        """
        cmd = self.descriptor.startup.teardown
        logger.info("Tearing down services: %s", cmd)
        try:
            subprocess.run(cmd, shell=True, check=False, capture_output=True, timeout=120)
        except Exception:
            logger.exception("Teardown failed")

    # ------------------------------------------------------------------
    # Scenario prioritization
    # ------------------------------------------------------------------

    def _prioritize_scenarios(self, scenarios: list[Scenario]) -> list[Scenario]:
        """Prioritize scenarios into budget tiers.

        Tier 1 (40% budget): Changed features
        Tier 2 (35% budget): Critical paths (priority <= 1)
        Tier 3 (25% budget): Full surface (everything else)

        Returns scenarios ordered by tier priority.
        """
        changed_interfaces: set[str] = set()
        if self.change_detector and self.config.changed_features_ref:
            changed_interfaces = set(
                self.change_detector.detect_from_git_diff(self.config.changed_features_ref)
            )

        tier1: list[Scenario] = []
        tier2: list[Scenario] = []
        tier3: list[Scenario] = []

        for scenario in scenarios:
            # Tier 1: scenario touches a changed interface
            if changed_interfaces and any(
                iface in changed_interfaces for iface in scenario.interfaces
            ):
                tier1.append(scenario)
            # Tier 2: critical path (priority <= 1)
            elif scenario.priority <= 1:
                tier2.append(scenario)
            # Tier 3: everything else
            else:
                tier3.append(scenario)

        # Apply budget caps per tier
        max_total = self.config.max_scenarios_per_iteration
        max_tier1 = int(max_total * 0.40)
        max_tier2 = int(max_total * 0.35)
        max_tier3 = max_total - max_tier1 - max_tier2  # gets the remainder

        result = tier1[:max_tier1] + tier2[:max_tier2] + tier3[:max_tier3]
        return result

    # ------------------------------------------------------------------
    # Parallel evaluation
    # ------------------------------------------------------------------

    async def _evaluate_parallel(self, scenarios: list[Scenario]) -> list[ScenarioVerdict]:
        """Evaluate scenarios with bounded parallelism."""
        semaphore = asyncio.Semaphore(self.config.parallel_scenarios)
        verdicts: list[ScenarioVerdict] = []

        async def _eval_one(scenario: Scenario) -> ScenarioVerdict | None:
            if self._budget_exhausted or not self.budget_tracker.can_continue():
                self._budget_exhausted = True
                return None
            async with semaphore:
                if self._budget_exhausted or not self.budget_tracker.can_continue():
                    self._budget_exhausted = True
                    return None
                verdict = await self.evaluator.evaluate(scenario)
                # Record time spent — only count as CLI call when backend is actually CLI
                if verdict.backend_used == "cli":
                    self.budget_tracker.time_budget.record_call(
                        "evaluation", verdict.duration_seconds
                    )
                return verdict

        tasks = [asyncio.create_task(_eval_one(s)) for s in scenarios]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, ScenarioVerdict):
                verdicts.append(result)
            elif isinstance(result, Exception):
                logger.error("Evaluation task failed: %s", result)

        return verdicts

    # ------------------------------------------------------------------
    # Report building
    # ------------------------------------------------------------------

    @staticmethod
    def _match_interface_coverage(
        tested: set[str], descriptor_interfaces: set[str]
    ) -> set[str]:
        """Match tested interfaces against descriptor interfaces.

        Handles parametric HTTP paths: a tested interface like
        ``"GET /locks/status/src/main.py"`` matches a descriptor template
        ``"GET /locks/status/{path}"``.

        Returns the subset of ``descriptor_interfaces`` that are covered.
        """
        # Build regex patterns for descriptor interfaces with path parameters
        templates: list[tuple[re.Pattern[str], str]] = []
        exact: set[str] = set()

        for iface in descriptor_interfaces:
            if "{" in iface:
                # Convert "GET /locks/status/{path}" → regex "GET /locks/status/.+"
                pattern_str = re.escape(iface)
                # Replace escaped template params: \{param\} → .+
                pattern_str = re.sub(r"\\{[^}]+\\}", ".+", pattern_str)
                templates.append((re.compile(f"^{pattern_str}$"), iface))
            else:
                exact.add(iface)

        covered: set[str] = set()

        for t in tested:
            # Exact match first
            if t in exact:
                covered.add(t)
                continue
            # Template match
            for pattern, template_name in templates:
                if pattern.match(t):
                    covered.add(template_name)
                    break

        return covered

    def _build_report(
        self,
        verdicts: list[ScenarioVerdict],
        duration: float,
        iterations_completed: int,
    ) -> GenEvalReport:
        """Build the final report from collected verdicts."""
        passed = sum(1 for v in verdicts if v.status == "pass")
        failed = sum(1 for v in verdicts if v.status == "fail")
        errors = sum(1 for v in verdicts if v.status == "error")
        skipped = sum(1 for v in verdicts if v.status == "skip")
        total = len(verdicts)

        # Coverage: unique interfaces tested / total interfaces
        # Uses template-aware matching so "GET /locks/status/src/main.py"
        # counts as covering "GET /locks/status/{path}".
        all_interfaces = set(self.descriptor.all_interfaces())
        tested_interfaces: set[str] = set()
        for v in verdicts:
            tested_interfaces.update(v.interfaces_tested)
        covered = self._match_interface_coverage(tested_interfaces, all_interfaces)
        coverage_pct = (
            (len(covered) / len(all_interfaces) * 100) if all_interfaces else 0.0
        )

        # Per-interface aggregation
        per_interface: dict[str, dict[str, int]] = {}
        for v in verdicts:
            for iface in v.interfaces_tested:
                if iface not in per_interface:
                    per_interface[iface] = {"pass": 0, "fail": 0, "error": 0}
                if v.status in per_interface[iface]:
                    per_interface[iface][v.status] += 1

        # Per-category aggregation
        per_category: dict[str, dict[str, int]] = {}
        for v in verdicts:
            cat = v.category or "uncategorized"
            if cat not in per_category:
                per_category[cat] = {"pass": 0, "fail": 0, "error": 0, "total": 0}
            per_category[cat]["total"] += 1
            if v.status in ("pass", "fail", "error"):
                per_category[cat][v.status] += 1

        # Unevaluated interfaces
        unevaluated = sorted(all_interfaces - covered)

        # Cost summary
        cost_summary: dict[str, float] = {
            "cli_calls": float(self.budget_tracker.time_budget.cli_calls),
            "time_minutes": self.budget_tracker.time_budget.elapsed_minutes,
            "sdk_cost_usd": (
                self.budget_tracker.sdk_budget.spent_usd if self.budget_tracker.sdk_budget else 0.0
            ),
        }

        pass_rate = passed / total if total > 0 else 0.0

        return GenEvalReport(
            total_scenarios=total,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            pass_rate=pass_rate,
            coverage_pct=coverage_pct,
            duration_seconds=duration,
            budget_exhausted=self._budget_exhausted,
            verdicts=verdicts,
            per_interface=per_interface,
            per_category=per_category,
            unevaluated_interfaces=unevaluated,
            cost_summary=cost_summary,
            iterations_completed=iterations_completed,
        )
