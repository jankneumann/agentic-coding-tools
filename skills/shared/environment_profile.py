"""Execution-environment detection shared across OpenSpec skills.

Reports filesystem workspace isolation and network restriction independently.
Used by worktree.py and merge_worktrees.py to short-circuit git-worktree
operations when the harness (e.g. a cloud ephemeral container) is the
isolation boundary rather than a local .git-worktrees/ tree.

Detection precedence (highest to lowest):
  1. Explicit env var AGENT_EXECUTION_ENV (value "cloud" or "local").
     Legacy CLAUDE_CODE_CLOUD=1 is accepted as cloud.
  2. Coordinator discovery query (only when agent_id is provided). 500ms
     timeout, falls through to heuristic on any error.
  3. Conservative container and cloud-harness heuristics.
  4. Default: neither dimension is provided.

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
class IsolationPosture:
    """Factual isolation supplied by the current execution environment."""

    filesystem: bool
    network: bool


@dataclass(frozen=True, init=False)
class EnvironmentProfile:
    """Result of environment detection.

    ``posture`` reports filesystem workspace and network isolation as
    independent facts. ``isolation_provided`` remains the compatibility
    alias for the filesystem dimension. ``source`` records the filesystem
    source, or the network source when filesystem falls through to default.
    """

    posture: IsolationPosture
    source: Source
    details: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        posture: IsolationPosture | bool | None = None,
        source: Source = "default",
        details: dict[str, Any] | None = None,
        *,
        isolation_provided: bool | None = None,
    ) -> None:
        """Build a profile, accepting the legacy filesystem-only keyword."""
        if isinstance(posture, bool):
            if isolation_provided is not None:
                raise TypeError("pass positional legacy value or isolation_provided, not both")
            isolation_provided = posture
            posture = None
        if posture is not None and isolation_provided is not None:
            raise TypeError("pass posture or isolation_provided, not both")
        if posture is None:
            posture = IsolationPosture(
                filesystem=False if isolation_provided is None else isolation_provided,
                network=False,
            )
        object.__setattr__(self, "posture", posture)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "details", {} if details is None else details)

    @property
    def isolation_provided(self) -> bool:
        """Compatibility alias for filesystem workspace isolation."""
        return self.posture.filesystem


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
                details={
                    "var": _AGENT_EXECUTION_ENV,
                    "value": "cloud",
                    "dimension_sources": {"filesystem": _AGENT_EXECUTION_ENV},
                },
            )
        if primary == "local":
            return EnvironmentProfile(
                isolation_provided=False,
                source="env_var",
                details={
                    "var": _AGENT_EXECUTION_ENV,
                    "value": "local",
                    "dimension_sources": {"filesystem": _AGENT_EXECUTION_ENV},
                },
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
            details={
                "var": _LEGACY_CLOUD_VAR,
                "value": legacy,
                "dimension_sources": {"filesystem": _LEGACY_CLOUD_VAR},
            },
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

    if not isinstance(record, dict):
        return None

    if "isolation_posture" in record:
        posture_record = record["isolation_posture"]
        if not isinstance(posture_record, dict):
            print(
                "environment_profile: coordinator returned malformed "
                "isolation_posture — ignoring, falling through",
                file=sys.stderr,
            )
            return None
        filesystem = posture_record.get("filesystem")
        network = posture_record.get("network")
        if isinstance(filesystem, bool) and isinstance(network, bool):
            return EnvironmentProfile(
                posture=IsolationPosture(filesystem=filesystem, network=network),
                source="coordinator",
                details={
                    "agent_id": agent_id,
                    "url": url,
                    "dimension_sources": {
                        "filesystem": "coordinator",
                        "network": "coordinator",
                    },
                },
            )
        print(
            "environment_profile: coordinator returned malformed "
            "isolation_posture — ignoring, falling through",
            file=sys.stderr,
        )
        return None

    if "isolation_provided" not in record:
        return None
    isolation_provided = record["isolation_provided"]
    if not isinstance(isolation_provided, bool):
        print(
            "environment_profile: coordinator returned non-boolean "
            "isolation_provided — ignoring, falling through",
            file=sys.stderr,
        )
        return None

    return EnvironmentProfile(
        isolation_provided=isolation_provided,
        source="coordinator",
        details={
            "agent_id": agent_id,
            "url": url,
            "dimension_sources": {"filesystem": "coordinator"},
        },
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
                posture=IsolationPosture(
                    filesystem=True,
                    network=_network_heuristic_provided(),
                ),
                source="heuristic",
                details=_heuristic_details("dockerenv", path=_DOCKERENV_PATH),
            )
    except OSError:
        pass

    # Marker 2: Kubernetes pod
    k8s = os.environ.get("KUBERNETES_SERVICE_HOST", "").strip()
    if k8s:
        return EnvironmentProfile(
            posture=IsolationPosture(
                filesystem=True,
                network=_network_heuristic_provided(),
            ),
            source="heuristic",
            details=_heuristic_details("kubernetes", host=k8s),
        )

    # Marker 3: GitHub Codespaces
    if os.environ.get("CODESPACES", "").strip().lower() == "true":
        return EnvironmentProfile(
            posture=IsolationPosture(
                filesystem=True,
                network=_network_heuristic_provided(),
            ),
            source="heuristic",
            details=_heuristic_details("codespaces"),
        )

    if _exact_env("CLAUDE_CODE_REMOTE", "true"):
        return EnvironmentProfile(
            posture=IsolationPosture(
                filesystem=True,
                network=_network_heuristic_provided(),
            ),
            source="heuristic",
            details=_heuristic_details("claude_code_remote"),
        )

    if _exact_env("CODEX_CI", "1") and (
        os.environ.get("CODEX_PERMISSION_PROFILE", "") == ":workspace"
    ):
        return EnvironmentProfile(
            posture=IsolationPosture(
                filesystem=True,
                network=_network_heuristic_provided(),
            ),
            source="heuristic",
            details=_heuristic_details("codex_workspace"),
        )

    if _network_heuristic_provided():
        return EnvironmentProfile(
            posture=IsolationPosture(filesystem=False, network=True),
            source="heuristic",
            details={
                "marker": "codex_network_disabled",
                "dimension_sources": {"network": "codex_network_disabled"},
            },
        )

    return None


def _exact_env(name: str, value: str) -> bool:
    return os.environ.get(name, "") == value


def _network_heuristic_provided() -> bool:
    return _exact_env("CODEX_SANDBOX_NETWORK_DISABLED", "1")


def _heuristic_details(marker: str, **extra: Any) -> dict[str, Any]:
    details: dict[str, Any] = {
        "marker": marker,
        "dimension_sources": {"filesystem": marker},
    }
    details.update(extra)
    if _network_heuristic_provided():
        details["dimension_sources"]["network"] = "codex_network_disabled"
    return details


def _combine_layers(layers: list[EnvironmentProfile]) -> EnvironmentProfile:
    """Resolve each dimension from its first definitive layer."""
    values = {"filesystem": False, "network": False}
    dimension_sources: dict[str, str] = {}
    layer_sources: dict[str, Source] = {}
    details: dict[str, Any] = {}

    for layer in layers:
        reported = layer.details.get("dimension_sources", {})
        if not isinstance(reported, dict):
            continue
        selected = False
        for dimension in ("filesystem", "network"):
            if dimension in dimension_sources or dimension not in reported:
                continue
            values[dimension] = getattr(layer.posture, dimension)
            dimension_sources[dimension] = str(reported[dimension])
            layer_sources[dimension] = layer.source
            selected = True
        if selected:
            for key, value in layer.details.items():
                if key != "dimension_sources":
                    details.setdefault(key, value)

    for dimension in ("filesystem", "network"):
        if dimension not in dimension_sources:
            dimension_sources[dimension] = "default"
            layer_sources[dimension] = "default"
    details["dimension_sources"] = dimension_sources

    source = layer_sources["filesystem"]
    if source == "default":
        source = layer_sources["network"]
    return EnvironmentProfile(
        posture=IsolationPosture(
            filesystem=values["filesystem"],
            network=values["network"],
        ),
        source=source,
        details=details,
    )


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
        through to ``IsolationPosture(filesystem=False, network=False)``.
    """
    layers: list[EnvironmentProfile] = []
    layer = _env_var_layer()
    if layer is not None:
        layers.append(layer)

    if not _skip_coordinator and agent_id:
        layer = _coordinator_layer(agent_id)
        if layer is not None:
            layers.append(layer)

    if not _skip_heuristic:
        layer = _heuristic_layer()
        if layer is not None:
            layers.append(layer)

    return _emit_debug(_combine_layers(layers))


def _emit_debug(profile: EnvironmentProfile) -> EnvironmentProfile:
    """Print the full profile to stderr when WORKTREE_DEBUG=1."""
    if os.environ.get("WORKTREE_DEBUG", "").strip() in ("1", "true", "yes"):
        print(
            f"environment_profile: isolation_provided={profile.isolation_provided} "
            f"filesystem={profile.posture.filesystem} "
            f"network={profile.posture.network} "
            f"source={profile.source} details={profile.details}",
            file=sys.stderr,
        )
    return profile
