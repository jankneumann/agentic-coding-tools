"""``coverage_pct`` must be denominated in operations, not elements (task 4.10).

Spec scenarios:
  - gen-eval-framework.operation-and-surface-coverage-model
      · one operation tested via one surface is not three gaps

Design decisions: D4.

Round-7 review, antigravity-001. Wave 3 built the operation model to remove the
element arithmetic, then left the headline number on the old denominator:
``len(covered) / len(all_interfaces)``. ``all_interfaces()`` returns one entry
per exposed *element*, so an operation published on three surfaces contributes
three. Exercise it once and the report says 33% — the exact number D4 exists to
stop producing. ``--min-coverage`` gates on this value, so the stale denominator
is not cosmetic: it fails builds that are fully covered.

The distinction these tests turn on is that the two denominators AGREE for a
single-surface descriptor and diverge only for a multi-surface one. Asserting on
a flat descriptor would pass under both formulas and prove nothing, so the
service fixture carries the weight and the flat cases exist to pin that nothing
regressed for them.
"""

from __future__ import annotations

from pathlib import Path

from gen_eval.descriptor import ToolDescriptor
from gen_eval.service_descriptor import ServiceDescriptor
from tests.test_coverage_model import CLI_CONTRACT, report_for
from tests.test_service_descriptor import CONTRACT_PATH


class TestOperationDenominatedCoverage:
    """A fully-exercised operation is 100%, however many surfaces expose it."""

    def test_one_operation_exercised_on_one_surface_is_fully_covered(
        self, tmp_path: Path
    ) -> None:
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        operation = descriptor.operations[0]
        http_element = operation.interface_id("http")
        assert http_element is not None, "fixture must expose an HTTP surface"

        # This operation is published on more than one surface, which is the
        # only configuration where the two denominators disagree.
        exposed = [s for s in ("http", "mcp", "cli") if operation.interface_id(s)]
        assert len(exposed) > 1, "fixture operation must be multi-surface"

        report = report_for(descriptor, [http_element], tmp_path)
        covered_ops = [op for op in report.per_operation if op.covered]
        assert len(covered_ops) == 1

        expected = 1 / len(descriptor.operations) * 100
        assert report.coverage_pct == expected, (
            f"coverage_pct {report.coverage_pct:.1f}% is element-denominated; "
            f"one of {len(descriptor.operations)} operations is covered, so it "
            f"must be {expected:.1f}%"
        )

    def test_covering_every_operation_reports_one_hundred_percent(
        self, tmp_path: Path
    ) -> None:
        """The headline case: a suite that exercises everything must read 100%.

        Under the element denominator this reports far less, because each
        operation's unexercised sibling surfaces stay in the divisor.
        """
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        one_element_each = [
            element
            for op in descriptor.operations
            if (element := op.interface_id("http")) is not None
        ]
        report = report_for(descriptor, one_element_each, tmp_path)
        assert all(op.covered for op in report.per_operation)
        assert report.coverage_pct == 100.0

    def test_an_untested_suite_is_zero(self, tmp_path: Path) -> None:
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        assert report_for(descriptor, [], tmp_path).coverage_pct == 0.0

    def test_the_percentage_tracks_the_operation_records(self, tmp_path: Path) -> None:
        """coverage_pct and per_operation must never disagree (D6).

        Two independent computations of one quantity is how they come to
        disagree; this pins them to the same source.
        """
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        operation = descriptor.operations[0]
        element = operation.interface_id("http")
        assert element is not None
        report = report_for(descriptor, [element], tmp_path)

        covered = sum(1 for op in report.per_operation if op.covered)
        assert report.coverage_pct == covered / len(report.per_operation) * 100


class TestFlatDescriptorsAreUnaffected:
    """Rule 4 — for a single-surface descriptor the two denominators agree."""

    def test_a_tool_descriptor_percentage_is_unchanged(self, tmp_path: Path) -> None:
        descriptor = ToolDescriptor.from_contract(CLI_CONTRACT)
        declared = descriptor.all_interfaces()
        assert declared, "tool contract must declare a surface"
        tested = declared[:2]
        report = report_for(descriptor, tested, tmp_path)
        assert report.coverage_pct == len(tested) / len(declared) * 100

    def test_a_tool_descriptor_fully_covered_is_one_hundred(
        self, tmp_path: Path
    ) -> None:
        descriptor = ToolDescriptor.from_contract(CLI_CONTRACT)
        report = report_for(descriptor, descriptor.all_interfaces(), tmp_path)
        assert report.coverage_pct == 100.0

    def test_an_empty_declared_surface_is_zero_not_a_crash(
        self, tmp_path: Path
    ) -> None:
        """The divisor can be zero; that must not raise (D3)."""
        from gen_eval.descriptor import InterfaceDescriptor

        descriptor = InterfaceDescriptor(project="empty", version="1.0", services=[])
        assert report_for(descriptor, [], tmp_path).coverage_pct == 0.0
