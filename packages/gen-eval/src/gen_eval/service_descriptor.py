"""Service descriptors derived from an OpenAPI contract.

The service archetype (spec: Service And Tool Descriptor Archetypes). A
service descriptor describes a system whose one operation set is projected
across HTTP, MCP and CLI bindings; its contract is OpenAPI and its coverage
unit is the *operation*, not the interface.

Two things separate this from the descriptor it supersedes:

**The contract populates the surface; the implementation never does** (D1).
Nothing here opens a socket, runs a subprocess, or calls ``list_tools()``. An
implementation that is broken, half-deployed or absent therefore yields the
same declared surface as a healthy one — which is the point. Introspection
that populates a declared set turns an outage into a coverage report of
``unevaluated_interfaces == []``.

**Coverage is keyed on operation × surface** (D4). One operation exposed on
three bindings is one unit with three surface entries, not three units; a
surface that does not expose an operation is recorded as such and never
counts as a gap; and one element may serve several operations, in which case
the binding is declared in the contract rather than derived (D7).

The ``ServiceDescriptor`` name is **reclaimed**: for one release it aliased
``descriptor.ServiceSpec``, the container for a single testable service. It
now denotes this document. ``descriptor.ServiceSpec`` keeps the container
role, so the two are deliberately different classes in different modules —
comparing them by identity will fail a correct implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, Field

from .descriptor import (
    CommandSpec,
    EndpointSpec,
    InterfaceDescriptor,
    McpToolSpec,
    ServiceSpec,
)

#: OpenAPI path-item keys that denote an operation. Everything else in a path
#: item (``parameters``, ``summary``, ``$ref``) is not one.
_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

#: Surfaces in the order they are declared, so the derived surface list is
#: stable across runs — an unstable order is permanent drift under ``--check``.
SURFACES = ("http", "mcp", "cli")

#: Contract-level extension carrying the MCP carve-outs (D7). Resources and
#: prompts are not operations and stay out of operation × surface coverage.
MCP_EXTENSION = "x-gen-eval-mcp"

#: Operation-level extension carrying the surface bindings (D4).
SURFACE_EXTENSION = "x-gen-eval-surface"


class SurfaceBinding(BaseModel):
    """How one surface exposes one operation.

    ``exposed: False`` is a first-class statement, not an omission: without it
    every operation missing from a binding becomes a permanent, unfixable
    coverage gap. ``reason`` is what makes that statement reviewable.
    """

    exposed: bool = True
    #: The surface-local element serving this operation — an HTTP route, an
    #: MCP tool name, a CLI command. May be shared by several operations.
    element: str | None = None
    reason: str | None = None


class OperationSpec(BaseModel):
    """One contracted operation, with its per-surface exposure."""

    operation_id: str
    method: str
    path: str
    summary: str = ""
    description: str = ""
    #: Raw OpenAPI parameter objects, kept for the MCP projection's flattening.
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    #: Raw JSON Schema of the request body, if any.
    request_body: dict[str, Any] | None = None
    surfaces: dict[str, SurfaceBinding] = Field(default_factory=dict)

    def interface_id(self, surface: str) -> str | None:
        """The declared identifier for this operation on ``surface``.

        ``None`` when the surface does not expose it — an unexposed surface
        contributes nothing to the declared set, so it can never be reported
        as uncovered.
        """
        binding = self.surfaces.get(surface)
        if binding is None or not binding.exposed:
            return None
        element = binding.element
        if surface == "http":
            return element or f"{self.method} {self.path}"
        return f"{surface}:{element or self.operation_id}"


class McpToolProjection(BaseModel):
    """An MCP tool derived from one or more operations (D7).

    Carries ``operation_ids`` because the projection is not injective: one
    tool may serve several operations, and coverage has to credit all of them
    when that tool is exercised. A projection that forgot the fan-in would
    report the unnamed operations as never tested.
    """

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    operation_ids: list[str] = Field(default_factory=list)


class ServiceDescriptor(InterfaceDescriptor):
    """A project's testable surface, derived from its OpenAPI contract."""

    #: The contract this descriptor was derived from. Relative entries in a
    #: descriptor file resolve against the file's own directory.
    contract: Path | None = None

    operations: list[OperationSpec] = Field(default_factory=list)

    #: Declared but excluded from coverage (D7): resources and prompts are
    #: not operations, so counting them as uncovered interfaces would be a
    #: permanent false gap.
    mcp_resources: list[str] = Field(default_factory=list)
    mcp_prompts: list[str] = Field(default_factory=list)

    # -- loading ---------------------------------------------------------

    @classmethod
    def _resolve_relative_paths(cls, data: dict[str, Any], descriptor_dir: Path) -> None:
        super()._resolve_relative_paths(data, descriptor_dir)
        raw = data.get("contract")
        if raw:
            p = Path(raw)
            data["contract"] = p if p.is_absolute() else (descriptor_dir / p).resolve()

    @classmethod
    def from_contract(
        cls,
        path: Path,
        *,
        project: str | None = None,
        version: str | None = None,
        base_url: str | None = None,
        scenario_dirs: list[Path] | None = None,
    ) -> Self:
        """Derive a service descriptor from an OpenAPI document.

        ``base_url`` is recorded so the evaluator knows where to send traffic.
        It is never contacted here: the declared surface must be identical
        whether or not anything is listening.
        """
        contract_path = Path(path).resolve()
        with open(contract_path) as f:
            document = yaml.safe_load(f)
        if not isinstance(document, dict):
            raise ValueError(
                f"Expected YAML mapping in {contract_path}, got {type(document).__name__}"
            )

        operations = _extract_operations(document, contract_path)
        info = document.get("info") or {}
        mcp_extension = document.get(MCP_EXTENSION) or {}

        return cls(
            project=project or info.get("title") or contract_path.stem,
            version=version or str(info.get("version") or "1"),
            contract=contract_path,
            operations=operations,
            mcp_resources=list(mcp_extension.get("resources") or []),
            mcp_prompts=list(mcp_extension.get("prompts") or []),
            services=_build_services(
                project or info.get("title") or contract_path.stem, operations, base_url
            ),
            scenario_dirs=scenario_dirs or [],
        )

    # -- surface ---------------------------------------------------------

    def operation(self, operation_id: str) -> OperationSpec:
        for op in self.operations:
            if op.operation_id == operation_id:
                return op
        raise KeyError(f"no operation {operation_id!r} in {self.project}")

    def all_interfaces(self) -> list[str]:
        """Declared identifiers across every exposed surface, de-duplicated.

        De-duplication is the many-to-one case (D7): one MCP tool serving two
        operations is one element. Emitting it twice would make the surface
        larger than it is and make subset verification report the second
        occurrence as an omitted tool.
        """
        surface: list[str] = []
        for operation in self.operations:
            for name in SURFACES:
                identifier = operation.interface_id(name)
                if identifier is not None and identifier not in surface:
                    surface.append(identifier)
        return surface

    def coverage_unit_count(self) -> int:
        """The service archetype's coverage unit is the operation (D3)."""
        return len(self.operations)

    def mcp_tools(self) -> list[McpToolProjection]:
        """Project the MCP surface from the contract (D7).

        Mechanical, but not total. Derivation is the default — one tool per
        operation, named for the operation, with (path, query, body)
        parameters flattened into one input object — and an explicit
        ``mcp.element`` binding overrides it: the bound name is emitted once
        and every operation behind it is recorded.

        Resources and prompts are not projected. They are not operations.
        """
        return project_mcp_tools(self.operations)

    def operations_for_element(self, surface: str, element: str) -> list[str]:
        """Operation ids served by one surface element — the fan-in record."""
        return [
            op.operation_id
            for op in self.operations
            if op.interface_id(surface) == f"{surface}:{element}"
        ]


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def project_mcp_tools(operations: list[OperationSpec]) -> list[McpToolProjection]:
    """Derive the MCP tool set from a contract's operations (D7)."""
    projections: list[McpToolProjection] = []
    by_name: dict[str, McpToolProjection] = {}

    for operation in operations:
        identifier = operation.interface_id("mcp")
        if identifier is None:
            continue
        name = identifier.removeprefix("mcp:")
        existing = by_name.get(name)
        if existing is None:
            projection = McpToolProjection(
                name=name,
                description=operation.summary or operation.description,
                input_schema=_flatten_parameters(operation),
                operation_ids=[operation.operation_id],
            )
            by_name[name] = projection
            projections.append(projection)
            continue

        # Fan-in: one element, several operations. The bound name is emitted
        # once; every operation behind it is recorded so exercising the tool
        # can credit all of them.
        existing.operation_ids.append(operation.operation_id)
        addition = operation.summary or operation.description
        if addition and addition not in existing.description:
            existing.description = (
                f"{existing.description}\n{addition}" if existing.description else addition
            )
        existing.input_schema = _merge_schemas(
            existing.input_schema, _flatten_parameters(operation)
        )

    return projections


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _extract_operations(document: dict[str, Any], source: Path) -> list[OperationSpec]:
    operations: list[OperationSpec] = []
    for path, item in (document.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, raw in item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(raw, dict):
                continue
            operation_id = raw.get("operationId")
            if not operation_id:
                # Fail closed. A nameless operation has no coverage key, and
                # dropping it would shrink the declared surface — the exact
                # failure this design exists to prevent, arriving through the
                # contract instead of through introspection.
                raise ValueError(
                    f"{source}: {method.upper()} {path} declares no operationId; "
                    "an operation without one cannot be a coverage key"
                )
            operations.append(
                OperationSpec(
                    operation_id=operation_id,
                    method=method.upper(),
                    path=path,
                    summary=raw.get("summary") or "",
                    description=raw.get("description") or "",
                    parameters=list(raw.get("parameters") or []),
                    request_body=_request_body_schema(raw),
                    surfaces=_surface_bindings(raw, method, path),
                )
            )
    return operations


def _request_body_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    content = ((operation.get("requestBody") or {}).get("content") or {}).get(
        "application/json"
    ) or {}
    schema = content.get("schema")
    return schema if isinstance(schema, dict) else None


def _surface_bindings(
    operation: dict[str, Any], method: str, path: str
) -> dict[str, SurfaceBinding]:
    declared = operation.get(SURFACE_EXTENSION)
    if not isinstance(declared, dict):
        # No binding block: the operation exists on the HTTP surface it was
        # written on, and makes no claim about the others. Inventing MCP and
        # CLI exposure here would manufacture gaps that no contract declared.
        return {"http": SurfaceBinding(exposed=True, element=f"{method.upper()} {path}")}
    return {
        surface: SurfaceBinding(**config)
        for surface, config in declared.items()
        if isinstance(config, dict)
    }


#: Parameter locations that become tool arguments (D7). Headers and cookies
#: are transport concerns, not things an agent decides to pass.
_ARGUMENT_LOCATIONS = ("path", "query")


def _flatten_parameters(operation: OperationSpec) -> dict[str, Any]:
    """Flatten (path, query, body) into one JSON Schema object."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    for parameter in operation.parameters:
        if parameter.get("in") not in _ARGUMENT_LOCATIONS:
            continue
        name = parameter.get("name")
        if not name:
            continue
        properties[name] = parameter.get("schema") or {}
        if parameter.get("required"):
            required.append(name)

    body = operation.request_body or {}
    for name, schema in (body.get("properties") or {}).items():
        properties[name] = schema
    required.extend(name for name in body.get("required") or [] if name not in required)

    flattened: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        flattened["required"] = required
    return flattened


def _merge_schemas(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Union two flattened schemas for a tool that serves both operations.

    Properties union; ``required`` **intersects**. A parameter required by
    only one of the bound operations cannot be required by the shared tool —
    marking it so would make the tool unable to express the other call at all.
    The real ``check_locks`` is exactly this shape: it branches on
    ``file_paths`` being None to serve both a listing and a single lookup.
    """
    properties = {**(left.get("properties") or {}), **(right.get("properties") or {})}
    left_required = set(left.get("required") or [])
    right_required = set(right.get("required") or [])

    merged: dict[str, Any] = {"type": "object", "properties": properties}
    shared = sorted(left_required & right_required)
    if shared:
        merged["required"] = shared
    return merged


def _build_services(
    project: str, operations: list[OperationSpec], base_url: str | None
) -> list[ServiceSpec]:
    """Build the evaluator-facing services from the declared surface.

    Only surfaces the contract actually exposes get a service: a project with
    no CLI must not acquire an empty CLI service that later reads as an
    untested one.
    """
    services: list[ServiceSpec] = []

    endpoints = [
        EndpointSpec(path=op.path, method=op.method, description=op.summary)
        for op in operations
        if op.interface_id("http") is not None
    ]
    if endpoints:
        services.append(
            ServiceSpec(name=f"{project}-http", type="http", base_url=base_url, endpoints=endpoints)
        )

    # The projection already collapses many-to-one and flattens arguments, so
    # the service's tool list is exactly it — deriving a second, simpler list
    # here would let the two disagree.
    tools = [
        McpToolSpec(
            name=projection.name,
            description=projection.description,
            input_schema=projection.input_schema,
        )
        for projection in project_mcp_tools(operations)
    ]
    if tools:
        services.append(ServiceSpec(name=f"{project}-mcp", type="mcp", tools=tools))

    commands: list[CommandSpec] = []
    for op in operations:
        identifier = op.interface_id("cli")
        if identifier is None:
            continue
        name = identifier.removeprefix("cli:")
        if any(command.name == name for command in commands):
            continue
        commands.append(CommandSpec(name=name, description=op.summary or op.description))
    if commands:
        services.append(ServiceSpec(name=f"{project}-cli", type="cli", commands=commands))

    return services
