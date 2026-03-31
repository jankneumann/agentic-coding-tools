"""Interface descriptor models for project-agnostic service description.

The interface descriptor is the core abstraction that makes the gen-eval
framework project-agnostic. It declaratively describes a project's testable
surface: HTTP endpoints, MCP tools, CLI commands, state verifiers, and
service lifecycle configuration.
"""

from __future__ import annotations

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


class EndpointDescriptor(BaseModel):
    """Description of a single HTTP endpoint."""

    path: str
    method: str = "GET"
    auth_required: bool = False
    description: str = ""
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)


class ToolDescriptor(BaseModel):
    """Description of a single MCP tool."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)


class CommandDescriptor(BaseModel):
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


class ServiceDescriptor(BaseModel):
    """A single testable service within a project."""

    name: str
    type: Literal["http", "mcp", "cli", "browser"]
    # HTTP-specific
    base_url: str | None = None
    openapi_spec: Path | None = None
    auth: AuthConfig | None = None
    endpoints: list[EndpointDescriptor] = Field(default_factory=list)
    # MCP-specific
    transport: Literal["stdio", "sse"] | None = None
    mcp_url: str | None = None
    tools_manifest: Path | None = None
    tools: list[ToolDescriptor] = Field(default_factory=list)
    # CLI-specific
    command: str | None = None
    cli_schema: Path | None = None
    json_flag: str | None = None
    commands: list[CommandDescriptor] = Field(default_factory=list)
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
    services: list[ServiceDescriptor]
    state_verifiers: list[StateVerifier] = Field(default_factory=list)
    startup: StartupConfig
    scenario_dirs: list[Path] = Field(default_factory=list)
    budget_defaults: BudgetConfig | None = None
    file_interface_map: list[FileInterfaceMapping] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> InterfaceDescriptor:
        """Load descriptor from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected YAML mapping in {path}, got {type(data).__name__}")
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
