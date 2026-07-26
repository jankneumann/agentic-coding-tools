"""Framework-level guarantees consumers build report validators on (UP-3).

These were previously true only by construction, with nothing pinning them.
ri-06 asserts against them directly, so they are promoted to tested contract:

1. ``per_category`` / ``per_interface`` are populated on every run that
   evaluated at least one scenario — *including* runs where everything passed.
   An empty breakdown must mean "nothing ran", never "nothing failed".
2. ``unevaluated_interfaces`` lists descriptor-declared interfaces that no
   scenario touched, so a consumer can assert emptiness instead of
   recomputing coverage itself.
3. A zero-scenario run cannot report success. ``pass_rate`` is 0.0 and the CLI
   exits non-zero regardless of ``--fail-threshold``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gen_eval.config import GenEvalConfig
from gen_eval.descriptor import InterfaceDescriptor
from gen_eval.evaluator import Evaluator
from gen_eval.models import ScenarioVerdict
from gen_eval.orchestrator import GenEvalOrchestrator
from gen_eval.reports import GenEvalReport


def _verdict(
    scenario_id: str,
    status: str,
    interfaces: list[str],
    category: str,
) -> ScenarioVerdict:
    return ScenarioVerdict(
        scenario_id=scenario_id,
        scenario_name=f"Scenario {scenario_id}",
        status=status,  # type: ignore[arg-type]
        steps=[],
        duration_seconds=0.1,
        interfaces_tested=interfaces,
        category=category,
    )


@pytest.fixture
def orchestrator(
    tmp_path: Path,
    sample_descriptor: InterfaceDescriptor,
) -> GenEvalOrchestrator:
    descriptor_path = tmp_path / "descriptor.yaml"
    descriptor_path.write_text("project: test\nversion: '0.1'\n")
    return GenEvalOrchestrator(
        config=GenEvalConfig(descriptor_path=descriptor_path, max_iterations=1),
        descriptor=sample_descriptor,
        generator=AsyncMock(),
        evaluator=AsyncMock(spec=Evaluator),
    )


class TestBreakdownsPopulatedOnEveryRun:
    """Guarantee 1 — an all-pass run still reports its breakdowns."""

    def test_all_pass_run_populates_per_category(
        self, orchestrator: GenEvalOrchestrator, sample_descriptor: InterfaceDescriptor
    ) -> None:
        iface = sample_descriptor.all_interfaces()[0]
        verdicts = [
            _verdict("s1", "pass", [iface], "lock-lifecycle"),
            _verdict("s2", "pass", [iface], "work-queue"),
        ]
        report = orchestrator._build_report(verdicts, duration=1.0, iterations_completed=1)

        assert report.per_category, "per_category must be populated on an all-pass run"
        assert set(report.per_category) == {"lock-lifecycle", "work-queue"}
        assert report.per_category["lock-lifecycle"] == {
            "pass": 1,
            "fail": 0,
            "error": 0,
            "total": 1,
        }

    def test_all_pass_run_populates_per_interface(
        self, orchestrator: GenEvalOrchestrator, sample_descriptor: InterfaceDescriptor
    ) -> None:
        iface = sample_descriptor.all_interfaces()[0]
        report = orchestrator._build_report(
            [_verdict("s1", "pass", [iface], "lock-lifecycle")],
            duration=1.0,
            iterations_completed=1,
        )
        assert report.per_interface, "per_interface must be populated on an all-pass run"
        assert report.per_interface[iface]["pass"] == 1

    def test_uncategorized_verdicts_still_get_a_bucket(
        self, orchestrator: GenEvalOrchestrator, sample_descriptor: InterfaceDescriptor
    ) -> None:
        """A verdict with no category must not vanish from the breakdown."""
        iface = sample_descriptor.all_interfaces()[0]
        report = orchestrator._build_report(
            [_verdict("s1", "pass", [iface], "")], duration=1.0, iterations_completed=1
        )
        assert "uncategorized" in report.per_category
        assert report.per_category["uncategorized"]["total"] == 1

    def test_per_category_totals_match_verdict_count(
        self, orchestrator: GenEvalOrchestrator, sample_descriptor: InterfaceDescriptor
    ) -> None:
        iface = sample_descriptor.all_interfaces()[0]
        verdicts = [
            _verdict("s1", "pass", [iface], "a"),
            _verdict("s2", "fail", [iface], "a"),
            _verdict("s3", "error", [iface], "b"),
            _verdict("s4", "skip", [iface], "b"),
        ]
        report = orchestrator._build_report(verdicts, duration=1.0, iterations_completed=1)
        assert sum(c["total"] for c in report.per_category.values()) == len(verdicts)


class TestUnevaluatedInterfaces:
    """Guarantee 2 — descriptor-declared interfaces no scenario touched."""

    def test_lists_interfaces_no_scenario_touched(
        self, orchestrator: GenEvalOrchestrator, sample_descriptor: InterfaceDescriptor
    ) -> None:
        all_interfaces = sample_descriptor.all_interfaces()
        assert len(all_interfaces) > 1, "fixture must declare several interfaces"
        tested = all_interfaces[0]

        report = orchestrator._build_report(
            [_verdict("s1", "pass", [tested], "cat")], duration=1.0, iterations_completed=1
        )
        assert tested not in report.unevaluated_interfaces
        for iface in all_interfaces[1:]:
            assert iface in report.unevaluated_interfaces

    def test_empty_when_every_interface_is_covered(
        self, orchestrator: GenEvalOrchestrator, sample_descriptor: InterfaceDescriptor
    ) -> None:
        """The assertion ri-06 makes: empty means full coverage."""
        all_interfaces = sample_descriptor.all_interfaces()
        report = orchestrator._build_report(
            [_verdict("s1", "pass", all_interfaces, "cat")],
            duration=1.0,
            iterations_completed=1,
        )
        assert report.unevaluated_interfaces == []
        assert report.coverage_pct == pytest.approx(100.0)

    def test_a_failing_scenario_still_counts_as_evaluated(
        self, orchestrator: GenEvalOrchestrator, sample_descriptor: InterfaceDescriptor
    ) -> None:
        """"Unevaluated" means untouched, not unsuccessful."""
        all_interfaces = sample_descriptor.all_interfaces()
        report = orchestrator._build_report(
            [_verdict("s1", "fail", all_interfaces, "cat")],
            duration=1.0,
            iterations_completed=1,
        )
        assert report.unevaluated_interfaces == []

    def test_every_interface_unevaluated_when_nothing_ran(
        self, orchestrator: GenEvalOrchestrator, sample_descriptor: InterfaceDescriptor
    ) -> None:
        report = orchestrator._build_report([], duration=0.0, iterations_completed=1)
        assert sorted(report.unevaluated_interfaces) == sorted(sample_descriptor.all_interfaces())


class TestZeroScenarioRunCannotPass:
    """Guarantee 3 — a run that evaluated nothing is never green."""

    def test_pass_rate_is_zero_not_one(self, orchestrator: GenEvalOrchestrator) -> None:
        report = orchestrator._build_report([], duration=0.0, iterations_completed=1)
        assert report.total_scenarios == 0
        assert report.pass_rate == 0.0

    @pytest.mark.parametrize("threshold", [0.0, 0.5, 0.95, 1.0])
    async def test_cli_exits_nonzero_at_any_threshold(
        self, tmp_path: Path, threshold: float
    ) -> None:
        """The framework-level guard.

        ``pass_rate`` of 0.0 already fails a positive threshold, but
        ``--fail-threshold 0`` would otherwise let an empty run exit 0 and read
        as green. That vacuous pass is exactly what a coverage gate exists to
        catch, so ``run()`` guards ``total_scenarios == 0`` explicitly.
        """
        from gen_eval.__main__ import run

        empty_report = GenEvalReport(
            total_scenarios=0,
            passed=0,
            failed=0,
            errors=0,
            skipped=0,
            pass_rate=0.0,
            coverage_pct=0.0,
            duration_seconds=0.0,
            budget_exhausted=False,
            verdicts=[],
            per_interface={},
            per_category={},
            unevaluated_interfaces=[],
            cost_summary={},
            iterations_completed=1,
        )

        descriptor_path = tmp_path / "descriptor.yaml"
        descriptor_path.write_text("project: test\nversion: '0.1'\n")

        args = argparse.Namespace(
            descriptor=descriptor_path,
            mode="template-only",
            cli_command="claude",
            time_budget=60.0,
            sdk_budget=None,
            max_iterations=1,
            parallel=5,
            changed_features_ref=None,
            categories=None,
            report_format="markdown",
            output_dir=tmp_path / "out",
            verbose=False,
            no_services=True,
            fail_threshold=threshold,
            openspec_change=None,
        )

        mock_orchestrator = MagicMock()
        mock_orchestrator.run = AsyncMock(return_value=empty_report)

        with (
            patch("gen_eval.descriptor.InterfaceDescriptor.from_yaml") as from_yaml,
            patch("gen_eval.orchestrator.GenEvalOrchestrator", return_value=mock_orchestrator),
        ):
            from_yaml.return_value = MagicMock(services=[], total_interface_count=lambda: 0)
            exit_code = await run(args)

        assert exit_code == 1, (
            f"a zero-scenario run exited {exit_code} at --fail-threshold {threshold}; "
            "an empty run must never report success"
        )
