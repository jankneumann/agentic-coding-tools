"""An empty declared surface fails rather than reporting coverage (task 5.4).

Spec scenarios:
  - gen-eval-framework.dogfood
      · an empty declared surface fails rather than reporting coverage

Design decisions: D3 (the coverage unit is the archetype's own unit), D10.

``coverage_pct`` is ``covered / declared``. When ``declared`` is zero the
framework reports ``0.0`` and every threshold at or below zero is satisfied, so
a descriptor that declares nothing exits 0 — the same outcome as a suite that
exercised everything. The two states are indistinguishable from the outside,
which is what makes this worth a separate gate rather than a lower threshold:
no threshold can separate them, because the numerator and denominator are both
empty.

This is not hypothetical. Until task 5.3, gen-eval's own dogfood descriptor
declared ``commands: []`` and its coverage assertion passed for free on every
run, while ri-06 downstream asserted ``unevaluated_interfaces == []`` and got
the same free pass from the same emptiness.

``declared_interface_count`` is what makes the distinction expressible at all.
Without it the report carries no field that differs between "covered
everything" and "declared nothing" — ``per_interface`` and
``unevaluated_interfaces`` are both empty in both cases.
"""

from __future__ import annotations

import pytest

from gen_eval.__main__ import exit_decision
from gen_eval.reports import GenEvalReport


def report(*, declared: int, covered_pct: float = 0.0) -> GenEvalReport:
    """A report that passed every scenario it ran, differing only in surface."""
    return GenEvalReport(
        total_scenarios=3,
        passed=3,
        failed=0,
        errors=0,
        skipped=0,
        pass_rate=1.0,
        coverage_pct=covered_pct,
        duration_seconds=0.1,
        budget_exhausted=False,
        verdicts=[],
        per_interface={},
        per_category={},
        unevaluated_interfaces=[],
        cost_summary={},
        iterations_completed=1,
        declared_interface_count=declared,
    )


class TestAnEmptyDeclaredSurfaceFails:
    """Zero declared units is not zero gaps."""

    def test_it_exits_nonzero(self) -> None:
        code, _ = exit_decision(
            report(declared=0), fail_threshold=1.0, min_coverage=0.0
        )
        assert code == 1

    def test_the_message_names_the_empty_surface(self) -> None:
        _, message = exit_decision(
            report(declared=0), fail_threshold=1.0, min_coverage=0.0
        )
        assert "declare" in message.lower()

    def test_a_zero_coverage_floor_does_not_rescue_it(self) -> None:
        """No threshold can separate 'covered all' from 'declared none'."""
        code, _ = exit_decision(
            report(declared=0), fail_threshold=0.0, min_coverage=0.0
        )
        assert code == 1

    def test_a_perfect_pass_rate_does_not_rescue_it(self) -> None:
        """The gates are independent — scenarios passing says nothing here."""
        code, message = exit_decision(
            report(declared=0), fail_threshold=1.0, min_coverage=0.0
        )
        assert code == 1, message


class TestANonEmptySurfaceIsUnaffected:
    """Rule 4 — a descriptor that declares something behaves as before."""

    def test_a_covered_run_still_passes(self) -> None:
        code, _ = exit_decision(
            report(declared=17, covered_pct=100.0),
            fail_threshold=1.0,
            min_coverage=80.0,
        )
        assert code == 0

    def test_a_partially_covered_run_still_reports_the_percentage(self) -> None:
        code, message = exit_decision(
            report(declared=17, covered_pct=29.4),
            fail_threshold=1.0,
            min_coverage=80.0,
        )
        assert code == 1
        assert "29.4" in message

    def test_a_partially_covered_run_under_no_floor_passes(self) -> None:
        code, _ = exit_decision(
            report(declared=17, covered_pct=29.4),
            fail_threshold=1.0,
            min_coverage=0.0,
        )
        assert code == 0

    @pytest.mark.parametrize("declared", [1, 17, 200])
    def test_any_non_zero_surface_clears_this_gate(self, declared: int) -> None:
        code, _ = exit_decision(
            report(declared=declared, covered_pct=100.0),
            fail_threshold=1.0,
            min_coverage=0.0,
        )
        assert code == 0


class TestTheZeroScenarioGuardStillFiresFirst:
    """Rule 4 — the existing vacuous-run guard is untouched."""

    def test_a_run_with_no_scenarios_still_fails(self) -> None:
        empty = report(declared=17, covered_pct=100.0)
        empty.total_scenarios = 0
        code, message = exit_decision(empty, fail_threshold=0.0, min_coverage=0.0)
        assert code == 1
        assert "no scenarios" in message
