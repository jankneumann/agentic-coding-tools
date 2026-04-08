"""DTU-lite scaffold generation from public SDK/API documentation.

Generates a Digital Twin Under test (DTU) scaffold from public docs,
examples, auth guidance, and error-mode descriptions. The scaffold
includes a descriptor seed, fixture placeholders, unsupported-surface
list, and fidelity report.

DTUs bootstrapped from docs alone are eligible for public scenarios.
Holdout eligibility requires live probe confirmation or explicit
operator approval (Design Decision D3).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class EndpointDoc:
    """Documentation for a single API endpoint."""

    path: str
    method: str = "GET"
    description: str = ""
    auth_required: bool = False
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    error_codes: list[int] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AuthDoc:
    """Documentation for API authentication."""

    type: str = "none"  # api_key, bearer, basic, oauth2, none
    header: str = ""
    description: str = ""


@dataclass
class ErrorMode:
    """Documentation for an error scenario."""

    code: int
    name: str = ""
    description: str = ""
    retry_eligible: bool = False


@dataclass
class PublicDocInput:
    """Structured input from public SDK/API documentation.

    This is what users provide to the scaffold generator — a structured
    summary of the external system's public documentation.
    """

    system_name: str
    base_url: str = ""
    version: str = ""
    auth: AuthDoc | None = None
    endpoints: list[EndpointDoc] = field(default_factory=list)
    error_modes: list[ErrorMode] = field(default_factory=list)
    rate_limits: dict[str, Any] | None = None
    notes: str = ""


@dataclass
class DTUScaffold:
    """Output of the DTU scaffold generation process."""

    system_name: str
    descriptor_seed: dict[str, Any]
    fixture_paths: list[str]
    unsupported_surfaces: list[str]
    error_catalog: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


def generate_scaffold(doc_input: PublicDocInput) -> DTUScaffold:
    """Generate a DTU scaffold from public documentation.

    Produces a gen-eval descriptor seed, fixture placeholders,
    and an unsupported-surface list from structured doc input.

    Args:
        doc_input: Structured representation of public SDK/API docs.

    Returns:
        DTUScaffold with descriptor seed, fixture paths, and
        unsupported surface catalog.
    """
    descriptor_seed = _build_descriptor_seed(doc_input)
    fixture_paths = _build_fixture_paths(doc_input)
    unsupported = _detect_unsupported_surfaces(doc_input)
    error_catalog = _build_error_catalog(doc_input)

    return DTUScaffold(
        system_name=doc_input.system_name,
        descriptor_seed=descriptor_seed,
        fixture_paths=fixture_paths,
        unsupported_surfaces=unsupported,
        error_catalog=error_catalog,
        metadata={
            "version": doc_input.version,
            "endpoint_count": len(doc_input.endpoints),
            "error_mode_count": len(doc_input.error_modes),
            "has_auth": doc_input.auth is not None and doc_input.auth.type != "none",
        },
    )


def write_scaffold(scaffold: DTUScaffold, output_dir: Path) -> list[Path]:
    """Write scaffold artifacts to disk.

    Creates:
    - descriptor.seed.yaml — gen-eval descriptor template
    - fixtures/ — placeholder fixture directory
    - error-catalog.json — error mode documentation
    - unsupported-surfaces.json — list of unsupported API surfaces

    Args:
        scaffold: Generated DTU scaffold.
        output_dir: Target directory for scaffold output.

    Returns:
        List of created file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    # Descriptor seed
    desc_path = output_dir / "descriptor.seed.yaml"
    with open(desc_path, "w") as f:
        yaml.dump(scaffold.descriptor_seed, f, default_flow_style=False, sort_keys=False)
    created.append(desc_path)

    # Fixture directory and placeholders
    fixtures_dir = output_dir / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    for fixture_path in scaffold.fixture_paths:
        fixture_file = fixtures_dir / fixture_path
        fixture_file.parent.mkdir(parents=True, exist_ok=True)
        if not fixture_file.exists():
            fixture_file.write_text(
                f"# Placeholder fixture for {fixture_path}\n"
                f"# Replace with actual response data from {scaffold.system_name}\n"
            )
    created.append(fixtures_dir)

    # Error catalog
    if scaffold.error_catalog:
        catalog_path = output_dir / "error-catalog.json"
        with open(catalog_path, "w") as f:
            json.dump(scaffold.error_catalog, f, indent=2)
        created.append(catalog_path)

    # Unsupported surfaces
    if scaffold.unsupported_surfaces:
        unsupported_path = output_dir / "unsupported-surfaces.json"
        with open(unsupported_path, "w") as f:
            json.dump(scaffold.unsupported_surfaces, f, indent=2)
        created.append(unsupported_path)

    return created


def _build_descriptor_seed(doc_input: PublicDocInput) -> dict[str, Any]:
    """Build a gen-eval descriptor YAML seed from public docs."""
    endpoints = []
    for ep in doc_input.endpoints:
        endpoint: dict[str, Any] = {
            "path": ep.path,
            "method": ep.method,
            "auth_required": ep.auth_required,
            "description": ep.description,
        }
        if ep.request_schema:
            endpoint["request_schema"] = ep.request_schema
        if ep.response_schema:
            endpoint["response_schema"] = ep.response_schema
        endpoints.append(endpoint)

    auth_config: dict[str, Any] = {"type": "none"}
    if doc_input.auth and doc_input.auth.type != "none":
        auth_config = {
            "type": doc_input.auth.type,
            "header": doc_input.auth.header,
        }

    service: dict[str, Any] = {
        "name": doc_input.system_name,
        "type": "http",
        "base_url": doc_input.base_url or "http://localhost:8080",
        "auth": auth_config,
        "endpoints": endpoints,
    }

    return {
        "project": f"dtu-{doc_input.system_name}",
        "version": doc_input.version or "0.1.0",
        "services": [service],
        "scenario_dirs": [f"scenarios/{doc_input.system_name}"],
    }


def _build_fixture_paths(doc_input: PublicDocInput) -> list[str]:
    """Generate fixture file paths based on endpoints."""
    paths: list[str] = []
    for ep in doc_input.endpoints:
        slug = ep.path.strip("/").replace("/", "_")
        method = ep.method.lower()
        paths.append(f"{method}_{slug}_success.json")
        for code in ep.error_codes:
            paths.append(f"{method}_{slug}_error_{code}.json")
    return paths


def _detect_unsupported_surfaces(doc_input: PublicDocInput) -> list[str]:
    """Identify API surfaces that cannot be simulated from docs alone."""
    unsupported: list[str] = []

    # Endpoints without schemas are harder to simulate
    for ep in doc_input.endpoints:
        if not ep.response_schema and not ep.examples:
            unsupported.append(
                f"{ep.method} {ep.path}: no response schema or examples documented"
            )

    # Auth flows requiring live tokens
    if doc_input.auth and doc_input.auth.type == "oauth2":
        unsupported.append("OAuth2 token exchange: requires live identity provider")

    # Rate limiting behavior
    if doc_input.rate_limits:
        unsupported.append("Rate limiting: timing-dependent behavior, needs live probes")

    return unsupported


def _build_error_catalog(doc_input: PublicDocInput) -> list[dict[str, Any]]:
    """Build a structured error mode catalog."""
    return [
        {
            "code": em.code,
            "name": em.name,
            "description": em.description,
            "retry_eligible": em.retry_eligible,
        }
        for em in doc_input.error_modes
    ]
