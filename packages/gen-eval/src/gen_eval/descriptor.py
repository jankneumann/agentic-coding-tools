"""Interface descriptor models for project-agnostic service description.

The interface descriptor is the core abstraction that makes the gen-eval
framework project-agnostic. It declaratively describes a project's testable
surface: HTTP endpoints, MCP tools, CLI commands, state verifiers, and
service lifecycle configuration.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Literal

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
    def from_yaml(cls, path: Path) -> InterfaceDescriptor:
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
        descriptor_dir = Path(path).resolve().parent
        raw_dirs = data.get("scenario_dirs") or []
        resolved: list[Path] = []
        for entry in raw_dirs:
            p = Path(entry)
            resolved.append(p if p.is_absolute() else (descriptor_dir / p).resolve())
        if resolved:
            data["scenario_dirs"] = resolved
        return cls(**data)

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

    def total_interface_count(self) -> int:
        """Return total number of testable interfaces."""
        return len(self.all_interfaces())


#: Pre-rename name -> its replacement (design D1). Every entry here is a plain
#: deprecation: this change frees these names but reuses none of them (D2), so
#: each has exactly one meaning throughout — "alias for the renamed type".
_DEPRECATED_ALIASES: dict[str, str] = {
    "EndpointDescriptor": "EndpointSpec",
    "ToolDescriptor": "McpToolSpec",
    "CommandDescriptor": "CommandSpec",
    "ServiceDescriptor": "ServiceSpec",
}


def __getattr__(name: str) -> Any:
    """Resolve a pre-rename name, warning that it moved (PEP 562).

    The alias is deliberately *not* cached into ``globals()``. Caching would
    make the module dict answer every access after the first, so only the
    first consumer to touch the name would ever see the warning — which is the
    opposite of what a deprecation is for.

    Unknown names still raise ``AttributeError`` so a typo stays a typo rather
    than becoming a warning about a name that was never real.
    """
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
