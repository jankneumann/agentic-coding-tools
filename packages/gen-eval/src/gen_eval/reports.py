"""Report generation for gen-eval runs.

Produces structured reports in markdown and JSON formats from
GenEvalReport data. Reports include pass/fail summaries, coverage
metrics, per-interface and per-category breakdowns, cost summaries,
and visibility-grouped results when a manifest is available.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from gen_eval.descriptor import InterfaceDescriptor
from gen_eval.metrics import GenEvalMetrics
from gen_eval.models import ScenarioVerdict

#: The surfaces an operation may be published on (D4). Kept in step with
#: ``service_descriptor.SURFACES``; spelled out here because the report model
#: must describe descriptors that carry no operations at all.
SURFACES = ("http", "mcp", "cli")

#: Element-identifier prefixes that name their own surface. Anything else —
#: ``"POST /locks/acquire"`` — is HTTP, which has no prefix.
_PREFIXED_SURFACES = ("mcp", "cli", "browser")


class SurfaceCoverage(BaseModel):
    """Whether one surface publishes an operation, and whether it was exercised.

    ``exposed`` and ``covered`` are deliberately independent booleans. A
    surface that does not publish the operation is ``exposed=False`` and is
    **not** a coverage gap — no run could ever cover it. A surface that
    publishes it and was not exercised is ``exposed=True, covered=False``, and
    is. The flat model could not tell those apart: both were simply absent
    from the covered set.
    """

    exposed: bool = False
    #: The surface-local element serving the operation — an HTTP
    #: ``"METHOD /path"``, an ``"mcp:<tool>"``, a ``"cli:<command>"``. ``None``
    #: exactly when the surface does not expose the operation.
    element: str | None = None
    covered: bool = False


class OperationCoverage(BaseModel):
    """Coverage for one operation across every surface (D4).

    The operation is the unit. An operation published on three surfaces and
    exercised through one is *covered*, with two exposed-but-uncovered
    surfaces — not two gaps.
    """

    operation_id: str
    surfaces: dict[str, SurfaceCoverage] = Field(default_factory=dict)

    # ``computed_field`` so the derived flag is emitted by model_dump_json and
    # documented in the published report schema, rather than being a Python-only
    # convenience a JSON consumer has to reimplement.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def covered(self) -> bool:
        return any(surface.covered for surface in self.surfaces.values())

    def exposed_elements(self) -> list[str]:
        """Declared elements serving this operation, in surface order."""
        return [s.element for s in self.surfaces.values() if s.exposed and s.element]

    def uncovered_elements(self) -> list[str]:
        """Exposed elements no scenario exercised. Unexposed surfaces excluded."""
        return [
            s.element
            for s in self.surfaces.values()
            if s.exposed and s.element and not s.covered
        ]


def _surface_of(element: str) -> str:
    """Infer the surface an element identifier belongs to."""
    prefix = element.split(":", 1)[0]
    return prefix if prefix in _PREFIXED_SURFACES else "http"


def build_operation_coverage(
    descriptor: InterfaceDescriptor, covered_elements: set[str]
) -> list[OperationCoverage]:
    """Build the operation × surface coverage model for any descriptor archetype.

    A service descriptor carries operations with surface bindings, so the model
    is read straight off it. A tool descriptor and a hand-authored
    :class:`InterfaceDescriptor` carry none — there each declared coverage unit
    becomes its own single-surface operation, so every archetype produces the
    same report structure and a consumer needs no branch (D6).

    ``covered_elements`` is the set of *declared* element identifiers that
    scenarios exercised, already resolved through template matching by the
    orchestrator. Passing raw tested identifiers here would silently miss
    parametric HTTP paths.
    """
    operations = getattr(descriptor, "operations", None)
    if operations:
        return [_from_operation(operation, covered_elements) for operation in operations]
    return [_from_element(element, covered_elements) for element in descriptor.all_interfaces()]


def _from_operation(operation: object, covered_elements: set[str]) -> OperationCoverage:
    surfaces: dict[str, SurfaceCoverage] = {}
    for surface in SURFACES:
        # ``interface_id`` returns None when the surface does not expose the
        # operation, which is the same condition as ``exposed=False``. Deriving
        # both from one call keeps them from disagreeing.
        element = operation.interface_id(surface)  # type: ignore[attr-defined]
        surfaces[surface] = SurfaceCoverage(
            exposed=element is not None,
            element=element,
            covered=element is not None and element in covered_elements,
        )
    return OperationCoverage(
        operation_id=operation.operation_id,  # type: ignore[attr-defined]
        surfaces=surfaces,
    )


def _from_element(element: str, covered_elements: set[str]) -> OperationCoverage:
    surface = _surface_of(element)
    return OperationCoverage(
        operation_id=element,
        surfaces={
            name: SurfaceCoverage(
                exposed=name == surface,
                element=element if name == surface else None,
                covered=name == surface and element in covered_elements,
            )
            for name in (*SURFACES, surface)
        },
    )


class VisibilityBreakdown(BaseModel):
    """Pass/fail/error/skip counts for a single visibility bucket."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0

    # ``computed_field`` (rather than a bare ``@property``) so ``pass_rate``
    # is emitted by model_dump_json *and* documented in the published
    # serialization JSON Schema. The type: ignore is the documented pydantic
    # idiom for stacking computed_field on top of property under mypy.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0


class GenEvalReport(BaseModel):
    """Complete gen-eval run report.

    This is a pydantic model rather than a plain dataclass so that
    ``eval-report.schema.json`` can be *generated* from it (see
    ``scripts/generate_contract_schemas.py``) instead of hand-authored and
    left to drift away from the emitter.
    """

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
    per_interface: dict[str, dict[str, int]]  # interface -> {pass, fail, error counts}
    per_category: dict[str, dict[str, int]]  # category -> {pass, fail, error, total}
    unevaluated_interfaces: list[str]
    cost_summary: dict[str, float]  # cli_calls, time_minutes, sdk_cost_usd
    # Operation × surface coverage (D4). Additive: both fields default, so
    # every existing constructor call keeps working and the published schema
    # change is a new optional field rather than a contract bump.
    per_operation: list[OperationCoverage] = Field(default_factory=list)
    #: Operations no exposing surface exercised. Distinct from
    #: ``unevaluated_interfaces``, which is per-element: an operation covered
    #: on HTTP still leaves its untested MCP element in the flat list.
    unevaluated_operations: list[str] = Field(default_factory=list)
    iterations_completed: int
    # Visibility-grouped results (populated when manifest is available)
    per_visibility: dict[str, VisibilityBreakdown] = Field(default_factory=dict)

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

    # Visibility breakdown
    if report.per_visibility:
        lines.append("## Visibility Breakdown")
        lines.append("")
        lines.append("| Visibility | Total | Pass | Fail | Error | Skip | Pass Rate |")
        lines.append("|------------|-------|------|------|-------|------|-----------|")
        for vis, breakdown in sorted(report.per_visibility.items()):
            lines.append(
                f"| {vis} | {breakdown.total} "
                f"| {breakdown.passed} "
                f"| {breakdown.failed} "
                f"| {breakdown.errors} "
                f"| {breakdown.skipped} "
                f"| {breakdown.pass_rate:.1%} |"
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
    """Generate a JSON-formatted report.

    Delegates to pydantic's serializer so the emitted document is, by
    construction, an instance of the published
    ``contracts/eval-report.schema.json`` (generated from this same model in
    ``serialization`` mode). Hand-building the dict here is what would let the
    two drift apart.

    Contract note: ``per_visibility`` is now always present, emitted as ``{}``
    when no manifest supplied visibility data. The previous hand-built dict
    omitted the key entirely in that case. This is additive for readers that
    use ``data.get("per_visibility", {})``.
    """
    return report.model_dump_json(indent=2)
