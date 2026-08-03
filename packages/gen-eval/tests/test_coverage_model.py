"""Operation-keyed coverage: exposure recorded separately from coverage (task 3.1).

Spec scenarios:
  - gen-eval-framework.operation-and-surface-coverage-model
      · one operation tested via one surface is not three gaps
      · a surface that does not expose an operation is not a gap
      · one surface element serving two operations is covered once
      · report continues to emit the flat interface list

Design decisions: D4 (coverage keyed on operation × surface), D6 (additive
migration — the flat fields keep being emitted).

The defect this replaces is arithmetic, not cosmetic. Under the flat model an
operation exposed on HTTP, MCP and CLI contributes **three** declared
interfaces. Exercising it once via HTTP therefore reports 1/3 covered and two
gaps — for an operation that is fully tested. Push that across a real service
and the coverage number a threshold gates on is dominated by how many surfaces
each operation happens to be published on, which is not a property of the test
suite at all.

Two distinctions carry the model, and both are asserted here rather than
assumed:

*exposed vs covered*
    ``release_lock`` is not on the CLI. That surface is recorded ``exposed:
    False`` and contributes nothing to any gap. ``acquire_lock``'s MCP surface
    is exposed and untested — a real gap. Collapsing the two into "absent from
    the covered set" is exactly the bug.
*element vs operation*
    ``check_locks`` serves two operations. Exercising the element covers both,
    and the element is counted once. An operation-keyed model that forgot the
    element would double-count; an element-keyed one would report a covered
    operation as a gap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gen_eval.config import GenEvalConfig
from gen_eval.descriptor import InterfaceDescriptor, ToolDescriptor
from gen_eval.models import ScenarioVerdict
from gen_eval.orchestrator import GenEvalOrchestrator
from gen_eval.reports import GenEvalReport, OperationCoverage
from gen_eval.service_descriptor import ServiceDescriptor
from tests.test_service_descriptor import CONTRACT_PATH

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI_CONTRACT = REPO_ROOT / "openspec" / "contracts" / "gen-eval-framework" / "cli" / "gen-eval.yaml"


def verdict(scenario_id: str, status: str, interfaces: list[str]) -> ScenarioVerdict:
    return ScenarioVerdict(
        scenario_id=scenario_id,
        scenario_name=f"Scenario {scenario_id}",
        status=status,  # type: ignore[arg-type]
        steps=[],
        duration_seconds=0.1,
        interfaces_tested=interfaces,
        category="coverage",
    )


def build(descriptor: InterfaceDescriptor, tmp_path: Path) -> GenEvalOrchestrator:
    """An orchestrator wired for report building only.

    ``_build_report`` is pure with respect to the generator and evaluator, so
    the report is produced from real descriptor and verdict objects rather than
    from a hand-assembled ``GenEvalReport``. A test that constructed the report
    directly would assert the shape of its own fixture.
    """
    descriptor_path = tmp_path / "descriptor.yaml"
    descriptor_path.write_text("project: test\nversion: '0.1'\n")
    return GenEvalOrchestrator(
        config=GenEvalConfig(descriptor_path=descriptor_path, max_iterations=1),
        descriptor=descriptor,
        generator=None,  # type: ignore[arg-type]
        evaluator=None,  # type: ignore[arg-type]
    )


def report_for(
    descriptor: InterfaceDescriptor, tested: list[str], tmp_path: Path
) -> GenEvalReport:
    orchestrator = build(descriptor, tmp_path)
    verdicts = [verdict("s1", "pass", tested)] if tested else []
    return orchestrator._build_report(verdicts, duration=1.0, iterations_completed=1)


def coverage_for(report: GenEvalReport, operation_id: str) -> OperationCoverage:
    for entry in report.per_operation:
        if entry.operation_id == operation_id:
            return entry
    raise AssertionError(
        f"no coverage entry for {operation_id!r} in "
        f"{[e.operation_id for e in report.per_operation]}"
    )


@pytest.fixture(scope="module")
def service() -> ServiceDescriptor:
    return ServiceDescriptor.from_contract(CONTRACT_PATH)


@pytest.fixture(scope="module")
def tool() -> ToolDescriptor:
    return ToolDescriptor.from_contract(CLI_CONTRACT)


# ---------------------------------------------------------------------------
# One operation, one surface, one coverage — not three gaps
# ---------------------------------------------------------------------------


class TestExposureIsSeparateFromCoverage:
    @pytest.fixture
    def report(self, service: ServiceDescriptor, tmp_path: Path) -> GenEvalReport:
        """``acquire_lock`` exercised over HTTP only. It is on all three surfaces."""
        return report_for(service, ["POST /locks/acquire"], tmp_path)

    def test_the_operation_is_reported_as_covered(self, report: GenEvalReport) -> None:
        assert coverage_for(report, "acquire_lock").covered is True

    def test_the_exercised_surface_is_covered(self, report: GenEvalReport) -> None:
        assert coverage_for(report, "acquire_lock").surfaces["http"].covered is True

    @pytest.mark.parametrize("surface", ["mcp", "cli"])
    def test_the_other_surfaces_are_exposed_but_not_covered(
        self, report: GenEvalReport, surface: str
    ) -> None:
        entry = coverage_for(report, "acquire_lock").surfaces[surface]
        assert entry.exposed is True
        assert entry.covered is False

    def test_a_covered_operation_is_not_in_the_unevaluated_operations(
        self, report: GenEvalReport
    ) -> None:
        """The headline claim: one surface exercised, zero operation-level gaps."""
        assert "acquire_lock" not in report.unevaluated_operations

    def test_every_surface_is_named_by_its_element(self, report: GenEvalReport) -> None:
        """Coverage is only auditable if each surface says what serves it."""
        surfaces = coverage_for(report, "acquire_lock").surfaces
        assert surfaces["http"].element == "POST /locks/acquire"
        assert surfaces["mcp"].element == "mcp:acquire_lock"
        assert surfaces["cli"].element == "cli:lock acquire"


# ---------------------------------------------------------------------------
# An unexposed surface is not a gap
# ---------------------------------------------------------------------------


class TestUnexposedSurfacesAreNotGaps:
    @pytest.fixture
    def report(self, service: ServiceDescriptor, tmp_path: Path) -> GenEvalReport:
        return report_for(service, [], tmp_path)

    def test_a_surface_that_does_not_expose_the_operation_is_recorded_not_exposed(
        self, report: GenEvalReport
    ) -> None:
        """``release_lock`` has no CLI form. Recorded, not silently absent."""
        assert coverage_for(report, "release_lock").surfaces["cli"].exposed is False

    def test_an_unexposed_surface_names_no_element(self, report: GenEvalReport) -> None:
        assert coverage_for(report, "release_lock").surfaces["cli"].element is None

    def test_an_unexposed_surface_is_never_covered(self, report: GenEvalReport) -> None:
        assert coverage_for(report, "release_lock").surfaces["cli"].covered is False

    def test_an_unexposed_surface_contributes_nothing_to_the_flat_gap_list(
        self, report: GenEvalReport
    ) -> None:
        """``reap_expired_locks`` is HTTP-only. Nothing may fabricate the other two.

        This is the permanent-false-gap case: no run, however exhaustive, could
        ever cover an interface that does not exist.
        """
        for absent in ("mcp:reap_expired_locks", "cli:reap_expired_locks"):
            assert absent not in report.unevaluated_interfaces

    def test_an_operation_exposed_only_on_http_still_has_the_other_surfaces_recorded(
        self, report: GenEvalReport
    ) -> None:
        """Not-exposed is a recorded fact, not a missing key."""
        surfaces = coverage_for(report, "reap_expired_locks").surfaces
        assert set(surfaces) == {"http", "mcp", "cli"}
        assert surfaces["http"].exposed is True
        assert surfaces["mcp"].exposed is False
        assert surfaces["cli"].exposed is False


# ---------------------------------------------------------------------------
# One element, two operations
# ---------------------------------------------------------------------------


class TestOneElementServingTwoOperations:
    @pytest.fixture
    def report(self, service: ServiceDescriptor, tmp_path: Path) -> GenEvalReport:
        """Only the shared MCP tool is exercised — neither HTTP path is."""
        return report_for(service, ["mcp:check_locks"], tmp_path)

    @pytest.mark.parametrize("operation_id", ["list_active_locks", "get_lock_status"])
    def test_exercising_the_bound_element_covers_every_bound_operation(
        self, report: GenEvalReport, operation_id: str
    ) -> None:
        assert coverage_for(report, operation_id).surfaces["mcp"].covered is True

    @pytest.mark.parametrize("operation_id", ["list_active_locks", "get_lock_status"])
    def test_both_operations_name_the_same_element(
        self, report: GenEvalReport, operation_id: str
    ) -> None:
        assert coverage_for(report, operation_id).surfaces["mcp"].element == "mcp:check_locks"

    @pytest.mark.parametrize("operation_id", ["list_active_locks", "get_lock_status"])
    def test_neither_bound_operation_is_unevaluated(
        self, report: GenEvalReport, operation_id: str
    ) -> None:
        assert operation_id not in report.unevaluated_operations

    def test_the_shared_element_is_counted_once_in_the_flat_surface(
        self, report: GenEvalReport
    ) -> None:
        """Two operations, one element — the flat list must not double-count."""
        flat = report.unevaluated_interfaces + list(report.per_interface)
        assert flat.count("mcp:check_locks") <= 1

    def test_the_untested_surfaces_of_a_bound_operation_remain_gaps(
        self, report: GenEvalReport
    ) -> None:
        """Negative control. Covering one surface must not blanket-cover the rest."""
        assert coverage_for(report, "get_lock_status").surfaces["http"].covered is False
        assert "GET /locks/status/{path}" in report.unevaluated_interfaces


# ---------------------------------------------------------------------------
# Operations nothing exercised
# ---------------------------------------------------------------------------


class TestUnevaluatedOperations:
    def test_an_operation_no_surface_exercised_is_unevaluated(
        self, service: ServiceDescriptor, tmp_path: Path
    ) -> None:
        report = report_for(service, ["POST /locks/acquire"], tmp_path)
        assert "release_lock" in report.unevaluated_operations

    def test_a_run_that_exercised_nothing_leaves_every_operation_unevaluated(
        self, service: ServiceDescriptor, tmp_path: Path
    ) -> None:
        report = report_for(service, [], tmp_path)
        assert set(report.unevaluated_operations) == {
            operation.operation_id for operation in service.operations
        }

    def test_coverage_is_reported_per_operation_not_per_interface(
        self, service: ServiceDescriptor, tmp_path: Path
    ) -> None:
        """Five operations, thirteen exposed interfaces. The unit is the operation."""
        report = report_for(service, [], tmp_path)
        assert len(report.per_operation) == len(service.operations)


# ---------------------------------------------------------------------------
# The archetypes that have no operations
# ---------------------------------------------------------------------------


class TestArchetypesWithoutOperations:
    """A tool or hand-authored descriptor has no operations. It still reports.

    D4's model is the report's model, not the service descriptor's. Each
    declared coverage unit becomes its own single-surface operation, so the
    coverage structures are populated identically for every archetype and a
    consumer needs no branch.
    """

    def test_a_tool_descriptor_reports_one_operation_per_coverage_unit(
        self, tool: ToolDescriptor, tmp_path: Path
    ) -> None:
        report = report_for(tool, [], tmp_path)
        assert {e.operation_id for e in report.per_operation} == set(tool.all_interfaces())

    def test_a_tool_coverage_unit_lives_on_the_cli_surface(
        self, tool: ToolDescriptor, tmp_path: Path
    ) -> None:
        report = report_for(tool, [], tmp_path)
        entry = coverage_for(report, "cli:--descriptor")
        assert entry.surfaces["cli"].exposed is True
        assert entry.surfaces["cli"].element == "cli:--descriptor"

    def test_exercising_a_tool_coverage_unit_covers_exactly_that_unit(
        self, tool: ToolDescriptor, tmp_path: Path
    ) -> None:
        report = report_for(tool, ["cli:--descriptor"], tmp_path)
        assert coverage_for(report, "cli:--descriptor").covered is True
        assert coverage_for(report, "cli:--mode").covered is False

    def test_a_hand_authored_descriptor_still_reports_operations(
        self, sample_descriptor: InterfaceDescriptor, tmp_path: Path
    ) -> None:
        """D6 — the legacy shape keeps working through the deprecation window."""
        report = report_for(sample_descriptor, [], tmp_path)
        assert {e.operation_id for e in report.per_operation} == set(
            sample_descriptor.all_interfaces()
        )

    def test_a_hand_authored_http_interface_is_recorded_on_the_http_surface(
        self, sample_descriptor: InterfaceDescriptor, tmp_path: Path
    ) -> None:
        report = report_for(sample_descriptor, [], tmp_path)
        http = [i for i in sample_descriptor.all_interfaces() if i.startswith("POST ")]
        assert http, "fixture must declare an HTTP interface"
        assert coverage_for(report, http[0]).surfaces["http"].exposed is True


# ---------------------------------------------------------------------------
# The flat fields keep working, computed from the operation model (task 3.3)
# ---------------------------------------------------------------------------


class TestLegacyFlatFieldsBackCompat:
    """D6 — the flat vocabulary survives the deprecation window.

    ``unevaluated_interfaces`` and ``per_interface`` predate the operation
    model and downstream consumers assert on both (DOWNSTREAM.md points ACA at
    ``per_interface`` by name). The spec requires them to keep being emitted
    *and* to be computed from the operation model rather than maintained
    alongside it — two independently-maintained coverage computations is how
    they disagree.

    The flat fields stay **element**-keyed, which is not the same claim as the
    operation model. An operation covered on HTTP and untested on MCP is one
    covered operation and one uncovered element; both statements are true and
    the report makes both.
    """

    def test_the_flat_gap_list_is_still_emitted(
        self, service: ServiceDescriptor, tmp_path: Path
    ) -> None:
        report = report_for(service, [], tmp_path)
        assert set(report.unevaluated_interfaces) == set(service.all_interfaces())

    def test_the_flat_gap_list_stays_element_keyed_not_operation_keyed(
        self, service: ServiceDescriptor, tmp_path: Path
    ) -> None:
        """One operation covered on HTTP still leaves its other elements listed."""
        report = report_for(service, ["POST /locks/acquire"], tmp_path)
        assert "acquire_lock" not in report.unevaluated_operations
        assert "mcp:acquire_lock" in report.unevaluated_interfaces
        assert "cli:lock acquire" in report.unevaluated_interfaces
        assert "POST /locks/acquire" not in report.unevaluated_interfaces

    def test_the_per_interface_map_is_still_emitted(
        self, service: ServiceDescriptor, tmp_path: Path
    ) -> None:
        report = report_for(service, ["POST /locks/acquire"], tmp_path)
        assert report.per_interface["POST /locks/acquire"] == {
            "pass": 1,
            "fail": 0,
            "error": 0,
        }

    def test_per_interface_counts_failures_separately(
        self, service: ServiceDescriptor, tmp_path: Path
    ) -> None:
        orchestrator = build(service, tmp_path)
        report = orchestrator._build_report(
            [
                verdict("s1", "pass", ["POST /locks/acquire"]),
                verdict("s2", "fail", ["POST /locks/acquire"]),
            ],
            duration=1.0,
            iterations_completed=1,
        )
        assert report.per_interface["POST /locks/acquire"] == {
            "pass": 1,
            "fail": 1,
            "error": 0,
        }

    def test_a_parametric_path_is_attributed_to_its_declared_template(
        self, service: ServiceDescriptor, tmp_path: Path
    ) -> None:
        """The vocabulary requirement, applied to the legacy map.

        A scenario tests a concrete path; the contract declares a template.
        Keying ``per_interface`` on the raw tested string splits one declared
        interface across as many keys as the suite used path values, and none
        of them match the declared surface — so the two maps in the same
        report speak different languages.
        """
        report = report_for(service, ["GET /locks/status/src/main.py"], tmp_path)
        assert "GET /locks/status/{path}" in report.per_interface
        assert "GET /locks/status/src/main.py" not in report.per_interface

    def test_the_two_flat_fields_partition_the_declared_surface(
        self, service: ServiceDescriptor, tmp_path: Path
    ) -> None:
        """Covered and uncovered are complements, not overlapping views."""
        report = report_for(service, ["GET /locks/status/src/main.py"], tmp_path)
        declared = set(service.all_interfaces())
        covered = declared & set(report.per_interface)
        assert covered == {"GET /locks/status/{path}"}
        assert set(report.unevaluated_interfaces) == declared - covered

    def test_a_tested_identifier_matching_nothing_declared_is_still_reported(
        self, service: ServiceDescriptor, tmp_path: Path
    ) -> None:
        """Negative control against over-normalising.

        Attributing tested identifiers to declared elements must not silently
        drop the ones that match nothing — that is a scenario exercising an
        undocumented surface, which is a finding, not noise.
        """
        report = report_for(service, ["GET /undocumented"], tmp_path)
        assert "GET /undocumented" in report.per_interface

    def test_a_shared_element_appears_once_in_the_flat_map(
        self, service: ServiceDescriptor, tmp_path: Path
    ) -> None:
        report = report_for(service, ["mcp:check_locks"], tmp_path)
        assert list(report.per_interface).count("mcp:check_locks") == 1

    def test_the_flat_fields_are_populated_for_a_tool_descriptor(
        self, tool: ToolDescriptor, tmp_path: Path
    ) -> None:
        """The archetype with no operations reports the same two fields."""
        report = report_for(tool, ["cli:--descriptor"], tmp_path)
        assert "cli:--descriptor" in report.per_interface
        assert "cli:--descriptor" not in report.unevaluated_interfaces
        assert "cli:--mode" in report.unevaluated_interfaces
