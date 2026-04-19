"""Execution-environment detection shared across OpenSpec skills.

Answers a single question: does the caller already have filesystem isolation?
Used by worktree.py and merge_worktrees.py to short-circuit git-worktree
operations when the harness (e.g. a cloud ephemeral container) is the
isolation boundary rather than a local .git-worktrees/ tree.

Detection precedence (highest to lowest):
  1. Explicit env var AGENT_EXECUTION_ENV (value "cloud" or "local").
     Legacy CLAUDE_CODE_CLOUD=1 is accepted as cloud.
  2. Coordinator discovery query (only when agent_id is provided). 500ms
     timeout, falls through to heuristic on any error.
  3. Container heuristic: /.dockerenv exists OR KUBERNETES_SERVICE_HOST set
     OR CODESPACES=true.
  4. Default: isolation_provided=False (preserves legacy worktree behavior).

The helper is pure and side-effect-free apart from stderr diagnostics when
WORKTREE_DEBUG=1 is set. Callers should treat the result as a single
decision and not re-query inside tight loops.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Literal

Source = Literal["env_var", "coordinator", "heuristic", "default"]

_AGENT_EXECUTION_ENV = "AGENT_EXECUTION_ENV"
_LEGACY_CLOUD_VAR = "CLAUDE_CODE_CLOUD"

# Module-level so tests can monkeypatch without subclassing pathlib.Path.
_DOCKERENV_PATH = "/.dockerenv"

_COORDINATOR_URL_VAR = "COORDINATOR_URL"
_COORDINATOR_API_KEY_VAR = "COORDINATOR_API_KEY"
_COORDINATOR_TIMEOUT_SECONDS = 0.5


@dataclass(frozen=True)
class EnvironmentProfile:
    """Result of environment detection.

    ``isolation_provided=True`` means the caller is running inside an
    environment that already provides filesystem isolation (container,
    ephemeral VM, etc.) and skills should NOT create additional git
    worktrees. ``source`` records which precedence layer produced the
    decision so operators can debug detection. ``details`` carries
    layer-specific metadata (env var name, agent id, heuristic marker).
    """

    isolation_provided: bool
    source: Source
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Layer 1 — explicit env var
# ---------------------------------------------------------------------------


def _env_var_layer() -> EnvironmentProfile | None:
    """Return a profile if an explicit env var is set, else None."""
    primary = os.environ.get(_AGENT_EXECUTION_ENV, "").strip().lower()
    if primary:
        if primary == "cloud":
            return EnvironmentProfile(
                isolation_provided=True,
                source="env_var",
                details={"var": _AGENT_EXECUTION_ENV, "value": "cloud"},
            )
        if primary == "local":
            return EnvironmentProfile(
                isolation_provided=False,
                source="env_var",
                details={"var": _AGENT_EXECUTION_ENV, "value": "local"},
            )
        # Unrecognized value — warn and fall through so detection still
        # has a chance via coordinator/heuristic layers.
        print(
            f"environment_profile: unrecognized {_AGENT_EXECUTION_ENV}="
            f"{primary!r} — ignoring, falling through to next layer",
            file=sys.stderr,
        )
        return None

    legacy = os.environ.get(_LEGACY_CLOUD_VAR, "").strip()
    if legacy in ("1", "true", "yes"):
        return EnvironmentProfile(
            isolation_provided=True,
            source="env_var",
            details={"var": _LEGACY_CLOUD_VAR, "value": legacy},
        )
    return None


# ---------------------------------------------------------------------------
# Layer 2 — coordinator discovery query
# ---------------------------------------------------------------------------


def _query_coordinator(
    agent_id: str,
    url: str,
    api_key: str | None,
    timeout: float,
) -> dict[str, Any] | None:
    """Ask the coordinator for this agent's registration record.

    Returns the parsed JSON body on 200, or None on any non-200 status.
    Raises on network errors so ``_coordinator_layer`` can decide how
    to handle the failure (log + fall through).
    """
    endpoint = url.rstrip("/") + f"/agents/{agent_id}"
    req = urllib.request.Request(endpoint, method="GET")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        if resp.status != 200:
            return None
        parsed: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return parsed


def _coordinator_layer(agent_id: str) -> EnvironmentProfile | None:
    """Return a profile if the coordinator reports isolation_provided."""
    url = os.environ.get(_COORDINATOR_URL_VAR, "").strip()
    if not url:
        return None
    api_key = os.environ.get(_COORDINATOR_API_KEY_VAR) or None

    try:
        record = _query_coordinator(
            agent_id, url, api_key, _COORDINATOR_TIMEOUT_SECONDS
        )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print(
            f"environment_profile: coordinator query failed "
            f"(agent_id={agent_id}, error={exc!r}) — falling through",
            file=sys.stderr,
        )
        return None

    if record is None or "isolation_provided" not in record:
        return None

    return EnvironmentProfile(
        isolation_provided=bool(record["isolation_provided"]),
        source="coordinator",
        details={"agent_id": agent_id, "url": url},
    )


# ---------------------------------------------------------------------------
# Layer 3 — container heuristic
# ---------------------------------------------------------------------------


def _heuristic_layer() -> EnvironmentProfile | None:
    """Return a profile if any container marker is present, else None.

    The set is intentionally conservative. Hostname patterns and
    /proc/1/cgroup parsing are rejected because they trigger false
    positives inside local dev containers where operators DO want
    worktree isolation between concurrent agents.
    """
    # Marker 1: Docker container
    try:
        if os.path.exists(_DOCKERENV_PATH):
            return EnvironmentProfile(
                isolation_provided=True,
                source="heuristic",
                details={"marker": "dockerenv", "path": _DOCKERENV_PATH},
            )
    except OSError:
        pass

    # Marker 2: Kubernetes pod
    k8s = os.environ.get("KUBERNETES_SERVICE_HOST", "").strip()
    if k8s:
        return EnvironmentProfile(
            isolation_provided=True,
            source="heuristic",
            details={"marker": "kubernetes", "host": k8s},
        )

    # Marker 3: GitHub Codespaces
    if os.environ.get("CODESPACES", "").strip().lower() == "true":
        return EnvironmentProfile(
            isolation_provided=True,
            source="heuristic",
            details={"marker": "codespaces"},
        )

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect(
    agent_id: str | None = None,
    *,
    _skip_coordinator: bool = False,
    _skip_heuristic: bool = False,
) -> EnvironmentProfile:
    """Detect the execution environment's isolation posture.

    Args:
        agent_id: The current agent's coordinator ID. If None, the
            coordinator layer is skipped. Skills that don't know their
            agent id (e.g. plan-feature itself) can omit this.
        _skip_coordinator: Testing hook — short-circuit the coordinator
            layer. Not for production callers.
        _skip_heuristic: Testing hook — short-circuit the heuristic
            layer. Not for production callers.

    Returns:
        An EnvironmentProfile. Never raises; detection errors fall
        through to the default (``isolation_provided=False``).
    """
    layer = _env_var_layer()
    if layer is not None:
        return _emit_debug(layer)

    if not _skip_coordinator and agent_id:
        layer = _coordinator_layer(agent_id)
        if layer is not None:
            return _emit_debug(layer)

    if not _skip_heuristic:
        layer = _heuristic_layer()
        if layer is not None:
            return _emit_debug(layer)

    return _emit_debug(
        EnvironmentProfile(
            isolation_provided=False,
            source="default",
            details={},
        )
    )


def _emit_debug(profile: EnvironmentProfile) -> EnvironmentProfile:
    """Print the full profile to stderr when WORKTREE_DEBUG=1."""
    if os.environ.get("WORKTREE_DEBUG", "").strip() in ("1", "true", "yes"):
        print(
            f"environment_profile: isolation_provided={profile.isolation_provided} "
            f"source={profile.source} details={profile.details}",
            file=sys.stderr,
        )
    return profile
