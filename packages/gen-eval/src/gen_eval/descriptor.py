"""Interface descriptor models for project-agnostic service description.

The interface descriptor is the core abstraction that makes the gen-eval
framework project-agnostic. It declaratively describes a project's testable
surface: HTTP endpoints, MCP tools, CLI commands, state verifiers, and
service lifecycle configuration.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, Field

from .config import BudgetConfig


class AuthConfig(BaseModel):
    """Authentication configuration for a service."""

    type: Literal["api_key", "bearer", "basic", "none"] = "none"
    header: str = "X-API-Key"
    env_var: str | None = None
    value: str | None = None


class EndpointSpec(BaseModel):
    """Description of a single HTTP endpoint."""

    path: str
    method: str = "GET"
    auth_required: bool = False
    description: str = ""
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)


class McpToolSpec(BaseModel):
    """Description of a single MCP tool."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)


class CommandSpec(BaseModel):
    """Description of a single CLI command."""

    name: str
    subcommands: list[str] = Field(default_factory=list)
    description: str = ""
    args_schema: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)


class BindingSpec(BaseModel):
    """How a CLI argument maps onto an operation parameter.

    The binding spec named in design D1's cons: an operation's (path, query,
    body) does not map mechanically onto argv, so where a tool is a client of
    a contracted service the mapping has to be declared rather than guessed.
    """

    location: Literal["path", "query", "body", "header", "env", "stdin"]
    parameter: str


class FlagSpec(BaseModel):
    """A single contracted flag — the tool archetype's coverage unit (D3).

    Flags are why tool contracts are not OpenAPI (D5): a flag is process
    configuration rather than an operation parameter. They are also what makes
    a flat, subcommand-less CLI nameable at all — without flag-level
    identifiers gen-eval's own descriptor declares zero interfaces and its
    coverage assertion passes for free.
    """

    name: str
    short: str | None = None
    type: Literal["string", "integer", "number", "boolean", "path", "enum"] = "string"
    required: bool = False
    repeatable: bool = False
    choices: list[str] = Field(default_factory=list)
    default: Any = None
    description: str = ""
    #: Exits before required-argument enforcement (the ``--help`` /
    #: ``--version`` / ``--print-contract-version`` class).
    short_circuits: bool = False
    binds_to: BindingSpec | None = None


class PositionalSpec(BaseModel):
    """A single contracted positional argument. A coverage unit like a flag."""

    name: str
    type: Literal["string", "integer", "number", "path"] = "string"
    required: bool = True
    variadic: bool = False
    description: str = ""
    binds_to: BindingSpec | None = None


class ExitCodeSpec(BaseModel):
    """A documented process exit code.

    OpenAPI has no equivalent, which is the primary reason tool contracts get
    their own schema (D5).
    """

    code: int
    meaning: str
    sysexits_name: str | None = None


class ToolCommandSpec(BaseModel):
    """An invocation unit of a contracted tool, with its arguments.

    Distinct from :class:`CommandSpec`, which describes a command inside a
    hand-authored :class:`ServiceSpec` and cannot express flags. Unifying the
    two would change the published ``interface-descriptor`` schema, which this
    change deliberately leaves alone — the contract-derived surface lives on
    :class:`ToolDescriptor`, not inside the legacy service model.

    A command with an empty ``name`` is the flat, subcommand-less form. It
    contributes no coverage unit of its own (D3): only its flags and
    positionals do.
    """

    name: str = ""
    description: str = ""
    flags: list[FlagSpec] = Field(default_factory=list)
    positionals: list[PositionalSpec] = Field(default_factory=list)
    #: Operations this command serves, when the tool is a client of a
    #: contracted service. A list because one surface element may serve
    #: several operations (D4/D7).
    operation_ids: list[str] = Field(default_factory=list)

    def coverage_units(self) -> list[str]:
        """Identifiers this command contributes to the declared surface.

        The vocabulary is shared with what a scenario records as tested, so a
        tested element matches its declared counterpart rather than comparing
        two disjoint string sets.
        """
        units: list[str] = []
        if self.name:
            units.append(_cli_unit(self.name))
        for flag in self.flags:
            units.append(_cli_unit(self.name, flag.name))
        for positional in self.positionals:
            units.append(_cli_unit(self.name, f"<{positional.name}>"))
        return units

    def coverage_aliases(self) -> dict[str, str]:
        """Alternate spellings of this command's units → the declared unit.

        A flag with a ``short`` form is one coverage unit invocable two ways.
        ``coverage_units`` emits only the long name, so without this map a step
        using ``-v`` records ``cli:-v``, fails the declared-membership filter,
        and leaves ``cli:--verbose`` uncovered despite a real exercise — the
        same vocabulary split D10 closes at the command level, reappearing one
        level down.

        Keyed by the full unit rather than the bare flag, because ``-t`` may
        mean different things under different subcommands.
        """
        return {
            _cli_unit(self.name, flag.short): _cli_unit(self.name, flag.name)
            for flag in self.flags
            if flag.short
        }


def _cli_unit(command_name: str, leaf: str = "") -> str:
    """Render one coverage-unit identifier, e.g. ``cli:lock acquire --ttl``."""
    return "cli:" + " ".join(part for part in (command_name, leaf) if part)


class FileInterfaceMapping(BaseModel):
    """Maps source files to interface endpoints for change detection."""

    file_pattern: str  # glob pattern, e.g. "src/locks.py"
    interfaces: list[str]  # endpoint/tool names affected


class ServiceSpec(BaseModel):
    """A single testable service within a project.

    A container of element specs describing one *surface* of a project, not the
    project itself — the document describing the project is
    :class:`InterfaceDescriptor`. Hence the ``Spec`` suffix (see design D1).
    """

    name: str
    type: Literal["http", "mcp", "cli", "browser"]
    # HTTP-specific
    base_url: str | None = None
    openapi_spec: Path | None = None
    auth: AuthConfig | None = None
    endpoints: list[EndpointSpec] = Field(default_factory=list)
    # MCP-specific
    transport: Literal["stdio", "sse"] | None = None
    mcp_url: str | None = None
    tools_manifest: Path | None = None
    tools: list[McpToolSpec] = Field(default_factory=list)
    # CLI-specific
    command: str | None = None
    cli_schema: Path | None = None
    json_flag: str | None = None
    commands: list[CommandSpec] = Field(default_factory=list)
    # Browser-specific
    launch_url: str | None = None


class StateVerifier(BaseModel):
    """A state backend for verification (not interaction)."""

    name: str
    type: Literal["postgres", "sqlite", "filesystem", "redis"]
    dsn_env: str | None = None
    tables: list[str] = Field(default_factory=list)


class StartupConfig(BaseModel):
    """How to start/stop services for evaluation.

    Optional on :class:`InterfaceDescriptor` — omit the whole block for
    projects with nothing to start (a CLI-only surface, or services managed
    entirely out-of-band). See ``InterfaceDescriptor.startup``.

    Security: ``command``, ``teardown``, and ``seed_command`` are executed via
    ``subprocess.run(..., shell=True)`` in the orchestrator.  Descriptor files
    must come from trusted sources — never load an untrusted descriptor.
    """

    command: str  # e.g., "docker-compose up -d"
    health_check: str  # URL or command to verify readiness
    health_timeout_seconds: int = 60
    health_retry_count: int = 5
    teardown: str  # e.g., "docker-compose down -v"
    seed_command: str | None = None


class InterfaceDescriptor(BaseModel):
    """Top-level project descriptor.

    Describes an entire project's testable surface: services (HTTP, MCP, CLI),
    state verifiers (databases), lifecycle configuration, and file-to-interface
    mappings for change detection.
    """

    project: str
    version: str
    services: list[ServiceSpec]
    state_verifiers: list[StateVerifier] = Field(default_factory=list)
    # Optional: a project with nothing to start (CLI-only surfaces, or
    # services managed entirely out-of-band) omits this block entirely. When
    # absent the orchestrator skips startup, health check, seeding and
    # teardown — there is nothing to do, so there is nothing to describe.
    # Requiring it forced such projects to invent no-op commands and a
    # health check URL that had to genuinely succeed; those placeholders read
    # as meaningful configuration to the next person to open the file.
    startup: StartupConfig | None = None
    scenario_dirs: list[Path] = Field(default_factory=list)
    budget_defaults: BudgetConfig | None = None
    file_interface_map: list[FileInterfaceMapping] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        """Load descriptor from a YAML file.

        Resolves any relative ``scenario_dirs`` entries against the descriptor's
        parent directory — matching the convention used by npm/pip/docker
        (paths in a config file are relative to the file's location, not the
        invoking process's CWD). Absolute entries are left untouched.
        """
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected YAML mapping in {path}, got {type(data).__name__}")
        cls._resolve_relative_paths(data, Path(path).resolve().parent)
        return cls(**data)

    @classmethod
    def _resolve_relative_paths(cls, data: dict[str, Any], descriptor_dir: Path) -> None:
        """Rewrite file-relative path entries in ``data`` to absolute paths.

        A hook rather than inline code so an archetype can resolve its own
        path-valued fields on the same terms, without restating the loader.
        """
        raw_dirs = data.get("scenario_dirs") or []
        resolved: list[Path] = []
        for entry in raw_dirs:
            p = Path(entry)
            resolved.append(p if p.is_absolute() else (descriptor_dir / p).resolve())
        if resolved:
            data["scenario_dirs"] = resolved

    def all_interfaces(self) -> list[str]:
        """Return all interface identifiers across all services."""
        interfaces: list[str] = []
        for svc in self.services:
            if svc.type == "http":
                for ep in svc.endpoints:
                    interfaces.append(f"{ep.method} {ep.path}")
            elif svc.type == "mcp":
                for tool in svc.tools:
                    interfaces.append(f"mcp:{tool.name}")
            elif svc.type == "cli":
                for cmd in svc.commands:
                    interfaces.append(f"cli:{cmd.name}")
            elif svc.type == "browser":
                if svc.launch_url:
                    interfaces.append(f"browser:{svc.launch_url}")
        return interfaces

    def coverage_aliases(self) -> dict[str, str]:
        """Alternate spellings of declared units → the unit they name.

        Empty for every archetype but the tool: only a CLI contract declares a
        second spelling for one element. Defined here rather than only on
        :class:`ToolDescriptor` so the evaluator can ask any descriptor without
        first discovering which archetype it holds.
        """
        return {}

    def total_interface_count(self) -> int:
        """Return total number of testable interfaces."""
        return len(self.all_interfaces())


def load_descriptor(path: Path) -> InterfaceDescriptor:
    """Load a descriptor file as the archetype it actually is.

    The runtime previously loaded every descriptor with
    ``InterfaceDescriptor.from_yaml()``. Pydantic drops fields the model does
    not declare, so a derived descriptor arrived at the evaluator stripped of
    exactly what made it derived: ``ServiceDescriptor.operations`` and
    ``ToolDescriptor.commands`` / ``executable`` / ``contract``. The same
    generated file yielded 17 interfaces as a tool descriptor and 0 as the base
    model, and the coverage model silently fell back to its element path — so
    D4's operation keying never engaged outside the tests that construct the
    derived class by hand.

    Dispatch reads the document's own shape rather than a ``kind`` discriminator
    so that already-generated files load correctly without reissuing them:

    - ``operations``           → :class:`~gen_eval.service_descriptor.ServiceDescriptor`
    - ``executable``           → :class:`ToolDescriptor`
    - neither                  → :class:`InterfaceDescriptor`

    Both markers are structural, not incidental. ``executable`` is required on
    the tool archetype, and only the service archetype carries ``operations``,
    so neither can appear on a hand-authored file by accident.

    Rule 4: a descriptor carrying neither marker loads exactly as it did
    before — same class, same fields, same behaviour.

    A file that declares no ``contract`` warns (D6). It still loads, and the
    flat fields it produces stay populated — ACA and the coordinator read that
    shape and a hard cutover would block on a coordinator OpenAPI contract that
    does not exist yet. What it stops doing is doing so silently: without a
    contract there is no source of truth behind the declared surface, so drift
    between it and the implementation is undetectable by construction.
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {path}, got {type(data).__name__}")

    if not data.get("contract"):
        warnings.warn(
            f"{path} declares no `contract:`, so its interface list is whatever "
            f"was typed rather than what a contract declares — drift between it "
            f"and the implementation cannot be detected. Derive it instead: "
            f"scripts/generate_tool_descriptor.py or "
            f"scripts/generate_service_descriptor.py. Hand-authored descriptors "
            f"still load and still emit the flat fields (D6); this path is "
            f"deprecated, not removed.",
            DeprecationWarning,
            stacklevel=2,
        )

    if data.get("operations"):
        # Imported here, not at module scope: service_descriptor imports this
        # module for InterfaceDescriptor, so a top-level import would cycle.
        from gen_eval.service_descriptor import ServiceDescriptor

        return ServiceDescriptor.from_yaml(path)
    if data.get("executable"):
        return ToolDescriptor.from_yaml(path)
    return InterfaceDescriptor.from_yaml(path)


class ToolDescriptor(InterfaceDescriptor):
    """A program's own invocation surface, derived from a CLI contract.

    The tool archetype (spec: Service And Tool Descriptor Archetypes). Where
    :class:`InterfaceDescriptor` describes a project whose services are started
    and probed, a tool descriptor describes an executable that is simply
    invoked — so it carries no lifecycle at all, and its coverage unit is the
    flag, positional or named subcommand rather than the operation.

    **The name is reclaimed, not renamed.** For one release
    ``descriptor.ToolDescriptor`` was a deprecation alias for
    :class:`McpToolSpec`, a single MCP tool. It now denotes this document-level
    archetype. Both resolve successfully while meaning different things, which
    is why the spec requires a contract-version increment and a downstream
    notice rather than a deprecation warning.

    **Lifecycle is structurally absent, not merely unset.** ``startup`` is
    typed ``None``, so a caller cannot hand one to a tool descriptor and have
    the orchestrator run it. The orchestrator's existing ``startup is None``
    branches then skip startup, health check, seeding and teardown.
    """

    #: Narrowed from the parent: a tool has nothing to start (spec: "A tool
    #: descriptor SHALL NOT require service lifecycle configuration").
    startup: None = None

    #: The CLI contract this descriptor was derived from. Relative entries in
    #: a descriptor file resolve against the file's own directory.
    contract: Path | None = None

    #: Console-script name resolved from PATH — the published artifact, not a
    #: source module path.
    executable: str

    commands: list[ToolCommandSpec] = Field(default_factory=list)
    exit_codes: list[ExitCodeSpec] = Field(default_factory=list)

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
        scenario_dirs: list[Path] | None = None,
    ) -> Self:
        """Derive a tool descriptor from a CLI contract document.

        This is the *generation-time* path (D2). Nothing here consults the
        implementation: no ``--help`` probe, no PATH lookup, no subprocess.
        That direction is the whole design (D1) — if introspection populated
        the declared surface, an uninstalled or broken tool would derive an
        empty one and then report full coverage of nothing.

        Loading a checked-in descriptor deliberately does NOT re-derive. The
        declared surface must not depend on generator success at run time;
        detecting drift between contract and artifact is the drift guard's job.
        """
        contract_path = Path(path).resolve()
        with open(contract_path) as f:
            document = yaml.safe_load(f)
        if not isinstance(document, dict):
            raise ValueError(
                f"Expected YAML mapping in {contract_path}, got {type(document).__name__}"
            )

        tool = document.get("tool") or {}
        name = tool.get("name")
        executable = tool.get("executable")
        if not name or not executable:
            raise ValueError(f"{contract_path} declares no tool.name / tool.executable")

        return cls(
            project=project or name,
            version=version or str(document.get("contract_version", "1")),
            executable=executable,
            contract=contract_path,
            commands=[ToolCommandSpec(**c) for c in document.get("commands") or []],
            exit_codes=[ExitCodeSpec(**e) for e in document.get("exit_codes") or []],
            # The tool under test, so the evaluator has something to invoke.
            # The declared surface lives on ``commands`` above, not here.
            services=[ServiceSpec(name=f"{name}-cli", type="cli", command=executable)],
            scenario_dirs=scenario_dirs or [],
        )

    def all_interfaces(self) -> list[str]:
        """Return the contracted coverage units (D3).

        Overrides the parent's command-level vocabulary. Commands are not
        coverage units for this archetype: a flat CLI declares exactly one
        command with an empty name, so counting commands reports a surface of
        1 for a tool that declares nothing testable.
        """
        return [unit for command in self.commands for unit in command.coverage_units()]

    def coverage_aliases(self) -> dict[str, str]:
        """Short flag spellings → the long unit they name, across all commands."""
        aliases: dict[str, str] = {}
        for command in self.commands:
            aliases.update(command.coverage_aliases())
        return aliases


#: Pre-rename name -> its replacement (design D1 of the prerequisite rename).
#: Each entry is a plain deprecation — the alias resolves and warns.
#:
#: ``ToolDescriptor`` is deliberately absent. It was an alias for
#: ``McpToolSpec``; it is now the tool archetype defined above, and a name that
#: denotes a different type cannot be described by a warning that points
#: somewhere else. That reclamation is announced by a contract-version
#: increment and a downstream notice instead.
_DEPRECATED_ALIASES: dict[str, str] = {
    "EndpointDescriptor": "EndpointSpec",
    "CommandDescriptor": "CommandSpec",
}

#: Reclaimed here rather than aliased. ``ServiceDescriptor`` was an alias for
#: ``ServiceSpec`` — *one testable service* — and is now the document-level
#: service archetype in ``service_descriptor``. Leaving it in the table above
#: would warn "use ServiceSpec instead" while the name's actual replacement is
#: a different type entirely.
#:
#: Resolved lazily rather than imported at module scope: ``service_descriptor``
#: imports this module, so a top-level import would cycle. Same technique as
#: :func:`load_descriptor`.
_RECLAIMED_NAMES: frozenset[str] = frozenset({"ServiceDescriptor"})


def __getattr__(name: str) -> Any:
    """Resolve a pre-rename name, warning that it moved (PEP 562).

    The alias is deliberately *not* cached into ``globals()``. Caching would
    make the module dict answer every access after the first, so only the
    first consumer to touch the name would ever see the warning — which is the
    opposite of what a deprecation is for.

    Unknown names still raise ``AttributeError`` so a typo stays a typo rather
    than becoming a warning about a name that was never real.
    """
    if name in _RECLAIMED_NAMES:
        # A live name for a current type, so no warning: one here would say
        # "this is going away" when the truth is "this stayed and changed
        # meaning" — the opposite claim.
        from gen_eval import service_descriptor

        return getattr(service_descriptor, name)

    replacement = _DEPRECATED_ALIASES.get(name)
    if replacement is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    warnings.warn(
        f"{__name__}.{name} is deprecated and will be removed after one "
        f"release; use {__name__}.{replacement} instead. Note that {name} may "
        f"later be reclaimed for a different type — see the change's "
        f"DOWNSTREAM notice.",
        DeprecationWarning,
        stacklevel=2,
    )
    return globals()[replacement]
