"""Frontend-descriptor loading and detection.

Loads ``evaluation/descriptors/<name>.yaml`` (or any YAML path) and
validates it against ``contracts/frontend-descriptor.schema.json`` from the
``factory-missions-architecture-alignment`` change.

The :func:`is_frontend_descriptor` helper is the public API used by
``validate-feature --phase gen-eval`` to route YAMLs to the Playwright
validator vs. the existing HTTP/MCP gen-eval path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml


_DEFAULT_SCHEMA_REL = (
    "openspec/changes/factory-missions-architecture-alignment/contracts/"
    "frontend-descriptor.schema.json"
)


class DescriptorError(ValueError):
    """Raised when a descriptor cannot be loaded or fails schema validation."""


def _repo_root() -> Path:
    """Best-effort repo-root resolution.

    The validator runs from a worktree or the repo checkout; walk up from
    this file looking for ``openspec/`` as a marker.
    """
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "openspec").is_dir():
            return parent
    return here.parent


def load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    """Load the frontend-descriptor JSON schema.

    Args:
        schema_path: Optional override path to a schema file. Defaults to
            ``<repo-root>/openspec/changes/factory-missions-architecture-alignment/contracts/frontend-descriptor.schema.json``.
    """
    if schema_path is None:
        schema_path = _repo_root() / _DEFAULT_SCHEMA_REL
    return json.loads(Path(schema_path).read_text(encoding="utf-8"))


def load_descriptor(
    path: Path,
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Load a frontend descriptor and validate it against the schema.

    Args:
        path: Path to a YAML file.
        schema_path: Optional override; see :func:`load_schema`.

    Returns:
        The parsed descriptor dict.

    Raises:
        DescriptorError: On YAML parse error or schema-validation failure.
            The wrapped message names the failing field for operator clarity.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise DescriptorError(f"cannot read descriptor {path}: {exc}") from exc

    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise DescriptorError(f"invalid YAML in {path}: {exc}") from exc

    if not isinstance(doc, dict):
        raise DescriptorError(
            f"descriptor {path} must be a YAML mapping at top level"
        )

    schema = load_schema(schema_path)
    try:
        jsonschema.validate(instance=doc, schema=schema)
    except jsonschema.ValidationError as exc:
        # Surface the failing field via the JSON pointer in exc.absolute_path.
        path_str = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise DescriptorError(
            f"frontend descriptor {path} failed validation at {path_str}: {exc.message}"
        ) from exc
    return doc


def is_frontend_descriptor(
    path: Path,
    *,
    schema_path: Path | None = None,
) -> bool:
    """Return ``True`` if ``path`` is a valid frontend descriptor.

    Used by ``validate-feature --phase gen-eval`` to decide whether to
    dispatch to the Playwright validator or the existing HTTP/MCP gen-eval
    path. Returns ``False`` on any load/parse/validation error rather than
    raising -- this is a routing predicate, not a verifier.
    """
    try:
        load_descriptor(path, schema_path=schema_path)
        return True
    except (DescriptorError, FileNotFoundError):
        return False


def normalize_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    """Apply schema defaults that aren't auto-applied by jsonschema validate.

    jsonschema's ``validate`` does not mutate the instance to insert defaults.
    The runner needs ``bind_address``, ``browsers``, and ``viewport`` in their
    canonical defaulted form -- this helper shallow-copies the dict and fills
    those in.
    """
    out = dict(descriptor)
    out.setdefault("schema_version", "1")
    out.setdefault("auth_flow", [])
    out.setdefault("env_vars_required", [])
    out.setdefault("browsers", ["chromium"])
    out.setdefault("test_isolation", "per_scenario")
    lifecycle = dict(out.get("lifecycle") or {})
    if lifecycle:
        lifecycle.setdefault("bind_address", "127.0.0.1")
        out["lifecycle"] = lifecycle
    viewport = dict(out.get("viewport") or {})
    viewport.setdefault("width", 1280)
    viewport.setdefault("height", 720)
    out["viewport"] = viewport
    return out


__all__ = [
    "DescriptorError",
    "is_frontend_descriptor",
    "load_descriptor",
    "load_schema",
    "normalize_descriptor",
]
