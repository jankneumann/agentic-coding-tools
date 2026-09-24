"""Production activation boundary for configured local sandbox dispatches."""

from __future__ import annotations

import hashlib
import json
import os
import platform as platform_module
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Mapping
from uuid import uuid4
from urllib.parse import urlsplit

import yaml

from .sandbox_audit import SandboxAuditPort
from .sandbox_profile import (
    PreflightResult,
    RuntimePaths,
    SandboxLaunch,
    SandboxProfileError,
    discover_sandbox_runtime,
    preflight_runtime,
)


Isolation = Literal["none", "worktree", "sandbox"]
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENDPOINT_KINDS = {"vendor-cli", "vendor-sdk", "openrouter", "local"}
_LOCATIONS = {"local", "cloud", "unknown"}


class SandboxActivationError(RuntimeError):
    """A requested sandbox cannot be activated safely."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class SandboxActivationContext:
    agent_id: str
    vendor_type: str
    dispatch_mode: str
    model: str
    isolation: Isolation
    policy_vendor: str | None
    catalog_vendor: str | None
    assignment_location: str
    endpoint_kind: str
    base_url: str | None
    enforcement_scope: Literal["execution", "submission"]
    write_capable: bool
    source: Literal["router", "agents_yaml"]
    worktree_root: Path
    api_key_env: str
    state_env_keys: tuple[str, ...]
    routing_context_digest: str | None = None
    workspace_content_digest: str | None = None
    decision_id: str | None = None
    item_id: str | None = None
    phase: str | None = None
    attempt: int | None = None
    dispatch_work_id: str | None = None


@dataclass(frozen=True)
class SandboxActivation:
    launch: SandboxLaunch
    runtime: RuntimePaths
    audit_port: SandboxAuditPort
    audit_event: dict[str, Any]


@dataclass(frozen=True)
class SandboxDegradation:
    reason: str
    audit_port: SandboxAuditPort
    audit_event: dict[str, Any]


PolicyFetcher = Callable[[str], Mapping[str, Any]]
EventSender = Callable[[dict[str, Any]], tuple[int, dict[str, Any]]]
RuntimeDiscoverer = Callable[[Path], RuntimePaths]
RuntimePreflight = Callable[[RuntimePaths], PreflightResult]

_DISCOVERY_DEGRADATION_STATUS = {
    "runtime_lock_missing": "runtime_missing",
    "runtime_package_missing": "runtime_missing",
    "runtime_entrypoint_missing": "runtime_missing",
    "runtime_executable_missing": "runtime_missing",
    "runtime_version_or_integrity_mismatch": "runtime_incompatible",
}


def _resolve_agents_path(
    *,
    worktree_root: Path,
    agents_path: Path | None = None,
) -> Path:
    """Resolve panel config without assuming this module's installation layout."""

    if agents_path is not None:
        return agents_path.expanduser().resolve()
    configured = os.environ.get("AGENTS_YAML")
    if configured:
        return Path(configured).expanduser().resolve()
    root = worktree_root.expanduser().resolve()
    for directory in (root, *root.parents):
        for candidate in (
            directory / "agent-coordinator" / "agents.yaml",
            directory / "agents.yaml",
        ):
            if candidate.is_file():
                return candidate.resolve()
    raise SandboxActivationError("sandbox_agents_config_unavailable")


def _load_exact_lane(agent_id: str, agents_path: Path) -> dict[str, Any]:
    try:
        document = yaml.safe_load(agents_path.read_text(encoding="utf-8"))
        lane = document["agents"][agent_id]
    except (OSError, KeyError, TypeError, yaml.YAMLError) as exc:
        raise SandboxActivationError(f"sandbox_lane_unavailable:{agent_id}") from exc
    if not isinstance(lane, dict):
        raise SandboxActivationError(f"sandbox_lane_invalid:{agent_id}")
    return lane


def _reject_routing_floats(value: Any, path: str = "routing_context") -> None:
    if isinstance(value, float):
        raise SandboxActivationError(f"sandbox_routing_float:{path}")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_routing_floats(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_routing_floats(child, f"{path}[{index}]")


def _routing_digest(routing_context: Mapping[str, Any]) -> str:
    _reject_routing_floats(routing_context)
    try:
        canonical = json.dumps(
            routing_context,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SandboxActivationError("sandbox_routing_context_invalid") from exc
    return hashlib.sha256(canonical).hexdigest()


def resolve_activation_context(
    *,
    agent_id: str,
    dispatch_mode: str,
    model: str,
    worktree_root: Path,
    execution_context: Mapping[str, Any] | None = None,
    agents_path: Path | None = None,
) -> SandboxActivationContext:
    """Resolve one exact lane; routed context remains the isolation authority."""

    lane = _load_exact_lane(
        agent_id,
        _resolve_agents_path(
            worktree_root=worktree_root,
            agents_path=agents_path,
        ),
    )
    cli = lane.get("cli")
    if not isinstance(cli, dict):
        raise SandboxActivationError(f"sandbox_cli_unavailable:{agent_id}")
    modes = cli.get("dispatch_modes")
    mode = modes.get(dispatch_mode) if isinstance(modes, dict) else None
    if not isinstance(mode, dict):
        raise SandboxActivationError(f"sandbox_mode_unavailable:{agent_id}:{dispatch_mode}")
    api_key_env = cli.get("api_key_env")
    if (
        not isinstance(api_key_env, str)
        or not api_key_env
        or _ENV_KEY_RE.fullmatch(api_key_env) is None
    ):
        raise SandboxActivationError(f"sandbox_credential_unavailable:{agent_id}")
    state_keys = cli.get("state_env_keys", [])
    if (
        not isinstance(state_keys, list)
        or not all(
            isinstance(key, str) and _ENV_KEY_RE.fullmatch(key) is not None
            for key in state_keys
        )
        or len(state_keys) != len(set(state_keys))
        or api_key_env in state_keys
    ):
        raise SandboxActivationError(f"sandbox_state_keys_invalid:{agent_id}")
    endpoint_kind = lane.get("endpoint_kind") or "vendor-cli"
    base_url = lane.get("base_url")
    if endpoint_kind not in _ENDPOINT_KINDS:
        raise SandboxActivationError(f"sandbox_endpoint_invalid:{agent_id}")
    location = lane.get("location") or "local"
    if location not in _LOCATIONS:
        raise SandboxActivationError(f"sandbox_location_invalid:{agent_id}")
    if base_url is not None:
        if not isinstance(base_url, str):
            raise SandboxActivationError(f"sandbox_endpoint_invalid:{agent_id}")
        parsed_endpoint = urlsplit(base_url)
        if (
            parsed_endpoint.scheme not in {"http", "https"}
            or not parsed_endpoint.hostname
            or parsed_endpoint.username is not None
            or parsed_endpoint.password is not None
            or parsed_endpoint.fragment
        ):
            raise SandboxActivationError(f"sandbox_endpoint_invalid:{agent_id}")
        normalized_host = (parsed_endpoint.hostname or "").lower()
        try:
            normalized_port = parsed_endpoint.port
        except ValueError as exc:
            raise SandboxActivationError(f"sandbox_endpoint_invalid:{agent_id}") from exc
        if (parsed_endpoint.scheme.lower(), normalized_port) in {
            ("http", 80), ("https", 443),
        }:
            normalized_port = None
        normalized_authority = normalized_host + (
            f":{normalized_port}" if normalized_port is not None else ""
        )
        raw_segments = parsed_endpoint.path.split("/")
        if any(segment in {".", ".."} for segment in raw_segments):
            raise SandboxActivationError(f"sandbox_endpoint_invalid:{agent_id}")
        normalized_url = parsed_endpoint._replace(
            scheme=parsed_endpoint.scheme.lower(),
            netloc=normalized_authority,
        ).geturl()
        if base_url != normalized_url:
            raise SandboxActivationError(f"sandbox_endpoint_invalid:{agent_id}")

    if execution_context is None:
        vendor_type = lane.get("type")
        if not isinstance(vendor_type, str) or not vendor_type.strip():
            raise SandboxActivationError(
                f"sandbox_vendor_type_invalid:{agent_id}"
            )
        vendor_projection: dict[str, str | None] = {}
        for field in ("policy_vendor", "catalog_vendor"):
            value = lane.get(field)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise SandboxActivationError(
                    f"sandbox_{field}_invalid:{agent_id}"
                )
            vendor_projection[field] = value
        isolation = mode.get("isolation", lane.get("isolation", "none"))
        if isolation not in {"none", "worktree", "sandbox"}:
            raise SandboxActivationError(f"sandbox_isolation_invalid:{agent_id}")
        enforcement_scope = mode.get("enforcement_scope")
        write_capable = mode.get("write_capable")
        if enforcement_scope not in {"execution", "submission"} or type(write_capable) is not bool:
            raise SandboxActivationError(f"sandbox_mode_projection_invalid:{agent_id}")
        return SandboxActivationContext(
            agent_id=agent_id,
            vendor_type=vendor_type,
            dispatch_mode=dispatch_mode,
            model=model,
            isolation=isolation,
            policy_vendor=vendor_projection["policy_vendor"],
            catalog_vendor=vendor_projection["catalog_vendor"],
            assignment_location=location,
            endpoint_kind=endpoint_kind,
            base_url=base_url,
            enforcement_scope=enforcement_scope,
            write_capable=write_capable,
            source="agents_yaml",
            worktree_root=worktree_root.resolve(),
            api_key_env=api_key_env,
            state_env_keys=tuple(state_keys),
        )

    required = {
        "schema_version", "routing_context", "agent_id", "vendor_type",
        "dispatch_mode", "model", "isolation",
        "policy_vendor", "catalog_vendor", "assignment_location", "endpoint_kind",
        "execution_location", "base_url", "enforcement_scope", "write_capable",
        "source", "worktree_root",
        "routing_context_digest", "workspace_content_digest", "decision_id", "item_id",
        "phase", "attempt", "dispatch_work_id",
    }
    missing = sorted(required - execution_context.keys())
    if missing:
        raise SandboxActivationError(
            "sandbox_execution_context_missing:" + ",".join(missing)
        )
    if execution_context.get("source") != "router":
        raise SandboxActivationError("sandbox_execution_context_source_invalid")
    if execution_context.get("schema_version") != 1:
        raise SandboxActivationError("sandbox_execution_context_schema_invalid")
    if execution_context.get("execution_location") != "local":
        raise SandboxActivationError("sandbox_execution_location_invalid")
    routing_context = execution_context.get("routing_context")
    if not isinstance(routing_context, dict):
        raise SandboxActivationError("sandbox_routing_context_invalid")
    if execution_context.get("routing_context_digest") != _routing_digest(routing_context):
        raise SandboxActivationError("sandbox_routing_context_digest_mismatch")
    if Path(str(execution_context["worktree_root"])).resolve() != worktree_root.resolve():
        raise SandboxActivationError("sandbox_execution_context_worktree_root_mismatch")
    duplicates = {
        "agent_id": agent_id,
        "dispatch_mode": dispatch_mode,
        "model": model,
    }
    for field, expected in duplicates.items():
        if execution_context.get(field) != expected:
            raise SandboxActivationError(f"sandbox_execution_context_{field}_mismatch")
    routing_fields = {
        "decision_id": "decision_id",
        "item_id": "item_id",
        "phase": "phase",
        "attempt": "attempt",
        "dispatch_work_id": "dispatch_work_id",
    }
    for context_field, routing_field in routing_fields.items():
        if execution_context.get(context_field) != routing_context.get(routing_field):
            raise SandboxActivationError(
                f"sandbox_execution_context_{context_field}_mismatch"
            )
    assignment = routing_context.get("assignment")
    if not isinstance(assignment, dict):
        raise SandboxActivationError("sandbox_routing_assignment_invalid")
    assignment_fields = {
        "agent_id": "agent_id",
        "vendor_type": "vendor_type",
        "policy_vendor": "policy_vendor",
        "catalog_vendor": "catalog_vendor",
        "assignment_location": "location",
        "dispatch_mode": "dispatch_mode",
        "isolation": "isolation",
        "model": "model",
        "base_url": "base_url",
        "endpoint_kind": "endpoint_kind",
        "enforcement_scope": "enforcement_scope",
        "write_capable": "write_capable",
    }
    for context_field, assignment_field in assignment_fields.items():
        if execution_context.get(context_field) != assignment.get(assignment_field):
            raise SandboxActivationError(
                f"sandbox_execution_context_{context_field}_mismatch"
            )
    isolation = execution_context.get("isolation")
    enforcement_scope = execution_context.get("enforcement_scope")
    write_capable = execution_context.get("write_capable")
    if isolation not in {"none", "worktree", "sandbox"}:
        raise SandboxActivationError("sandbox_execution_context_isolation_invalid")
    if enforcement_scope not in {"execution", "submission"} or type(write_capable) is not bool:
        raise SandboxActivationError("sandbox_execution_context_projection_invalid")
    return SandboxActivationContext(
        agent_id=agent_id,
        vendor_type=str(execution_context["vendor_type"]),
        dispatch_mode=dispatch_mode,
        model=model,
        isolation=isolation,
        policy_vendor=execution_context["policy_vendor"],
        catalog_vendor=execution_context["catalog_vendor"],
        assignment_location=str(execution_context["assignment_location"]),
        endpoint_kind=str(execution_context["endpoint_kind"]),
        base_url=execution_context["base_url"],
        enforcement_scope=enforcement_scope,
        write_capable=write_capable,
        source="router",
        worktree_root=Path(str(execution_context["worktree_root"])).resolve(),
        api_key_env=api_key_env,
        state_env_keys=tuple(state_keys),
        routing_context_digest=execution_context["routing_context_digest"],
        workspace_content_digest=execution_context["workspace_content_digest"],
        decision_id=execution_context["decision_id"],
        item_id=execution_context["item_id"],
        phase=execution_context["phase"],
        attempt=execution_context["attempt"],
        dispatch_work_id=execution_context["dispatch_work_id"],
    )


def resolve_requested_isolation(
    agent_id: str,
    dispatch_mode: str,
    *,
    worktree_root: Path,
    agents_path: Path | None = None,
) -> Isolation:
    """Resolve exact standalone mode isolation for callers outside the panel."""

    lane = _load_exact_lane(
        agent_id,
        _resolve_agents_path(
            worktree_root=worktree_root,
            agents_path=agents_path,
        ),
    )
    cli = lane.get("cli")
    modes = cli.get("dispatch_modes") if isinstance(cli, dict) else None
    mode = modes.get(dispatch_mode) if isinstance(modes, dict) else None
    if not isinstance(mode, dict):
        raise SandboxActivationError(f"sandbox_mode_unavailable:{agent_id}:{dispatch_mode}")
    value = mode.get("isolation", lane.get("isolation", "none"))
    if value not in {"none", "worktree", "sandbox"}:
        raise SandboxActivationError(f"sandbox_isolation_invalid:{agent_id}")
    return value


def _bridge_module() -> Any:
    scripts = Path(__file__).resolve().parents[1] / "coordination-bridge" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import coordination_bridge  # type: ignore[import-not-found]

    return coordination_bridge


def _default_policy_fetcher(agent_id: str) -> Mapping[str, Any]:
    return _bridge_module().export_network_policy(agent_id)


def _default_event_sender(event: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    result = _bridge_module().record_sandbox_event(event)
    status = result.get("status_code")
    if status is None:
        raise OSError(str(result.get("error") or "sandbox audit unavailable"))
    payload = result.get("data")
    return int(status), payload if isinstance(payload, dict) else result


def _git_path(cwd: Path, flag: str) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", flag], cwd=str(cwd), check=True,
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SandboxActivationError("sandbox_git_identity_unavailable") from exc
    value = Path(result.stdout.strip())
    return (cwd / value).resolve() if not value.is_absolute() else value.resolve()


def _endpoint_digest(endpoint_kind: str, base_url: str | None) -> str:
    if not endpoint_kind:
        raise SandboxActivationError("sandbox_endpoint_invalid")
    if base_url is not None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise SandboxActivationError("sandbox_endpoint_invalid")
    document = {"base_url": base_url, "endpoint_kind": endpoint_kind}
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _audit_state_root(env: Mapping[str, str]) -> Path:
    configured = env.get("XDG_STATE_HOME") or os.environ.get("XDG_STATE_HOME")
    base = Path(configured) if configured else Path.home() / ".local" / "state"
    return (base / "agentic-coding-tools" / "sandbox-events").resolve()


def _vendor_install_root(executable: Path) -> Path:
    return executable.parents[1] if executable.parent.name == "bin" else executable.parent


def _platform() -> Literal["linux", "darwin", "unsupported"]:
    system = platform_module.system()
    if system == "Linux":
        return "linux"
    if system == "Darwin":
        return "darwin"
    return "unsupported"


def _base_event(
    context: SandboxActivationContext,
    executable: Path,
    *,
    preflight_status: str,
    degradation_reason: str | None,
    runtime: RuntimePaths | None,
    policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    paths = [str(executable)]
    if runtime is not None:
        paths.extend((str(runtime.node), str(runtime.entrypoint)))
    return {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "context_source": context.source,
        "decision_id": context.decision_id,
        "item_id": context.item_id,
        "phase": context.phase,
        "attempt": context.attempt,
        "dispatch_work_id": context.dispatch_work_id,
        "routing_context_digest": context.routing_context_digest,
        "workspace_content_digest": context.workspace_content_digest,
        "agent_id": context.agent_id,
        "vendor_type": context.vendor_type,
        "policy_vendor": context.policy_vendor,
        "catalog_vendor": context.catalog_vendor,
        "assignment_location": context.assignment_location,
        "execution_location": "local",
        "enforcement_scope": context.enforcement_scope,
        "write_capable": context.write_capable,
        "dispatch_mode": context.dispatch_mode,
        "model": context.model,
        "endpoint_kind": context.endpoint_kind,
        "endpoint_digest": _endpoint_digest(context.endpoint_kind, context.base_url),
        "requested_isolation": "sandbox",
        "sandbox_applied": False,
        "backend": "srt" if degradation_reason is None else "local-process",
        "runtime_version": runtime.version if runtime is not None else None,
        "platform": _platform(),
        "preflight_status": preflight_status,
        "policy_revision": policy.get("policy_revision") if policy else None,
        "policy_digest": policy.get("policy_digest") if policy else None,
        "settings_digest": None,
        "worktree_root": str(context.worktree_root),
        "executable_paths": sorted(set(paths)),
        "environment_keys": sorted({context.api_key_env, *context.state_env_keys}),
        "degradation_reason": degradation_reason,
        "cleanup_status": "not_started",
        "cleanup_residual_paths": [],
    }


def activate_sandbox(
    *,
    context: SandboxActivationContext,
    vendor_executable: Path,
    env: Mapping[str, str],
    policy_fetcher: PolicyFetcher = _default_policy_fetcher,
    event_sender: EventSender = _default_event_sender,
    runtime_discoverer: RuntimeDiscoverer = discover_sandbox_runtime,
    runtime_preflight: RuntimePreflight = preflight_runtime,
    audit_state_root: Path | None = None,
) -> SandboxActivation | SandboxDegradation:
    """Construct all runtime inputs, or one auditable permitted degradation."""

    if context.isolation != "sandbox":
        raise SandboxActivationError("sandbox_activation_not_requested")
    if not context.api_key_env or not env.get(context.api_key_env):
        raise SandboxActivationError("authorization_failed")
    executable = vendor_executable.resolve(strict=True)
    common_git = _git_path(context.worktree_root, "--git-common-dir")
    git_toplevel = _git_path(context.worktree_root, "--show-toplevel")
    common_repo = common_git.parent
    try:
        runtime = runtime_discoverer(context.worktree_root)
    except SandboxProfileError as exc:
        preflight_status = _DISCOVERY_DEGRADATION_STATUS.get(exc.reason)
        if not exc.fail_open or preflight_status is None:
            raise SandboxActivationError(exc.reason) from exc
        audit = SandboxAuditPort(
            state_root=audit_state_root or _audit_state_root(env),
            checkout_roots=[common_repo],
            sender=event_sender,
        )
        event = _base_event(
            context, executable, preflight_status=preflight_status,
            degradation_reason=preflight_status, runtime=None, policy=None,
        )
        return SandboxDegradation(preflight_status, audit, event)
    preflight = runtime_preflight(runtime)
    if not preflight.ok:
        audit = SandboxAuditPort(
            state_root=audit_state_root or _audit_state_root(env),
            checkout_roots=[common_repo],
            sender=event_sender,
        )
        event = _base_event(
            context, executable, preflight_status=preflight.status,
            degradation_reason=preflight.status, runtime=runtime, policy=None,
        )
        return SandboxDegradation(preflight.status, audit, event)
    policy = policy_fetcher(context.agent_id)
    if policy.get("schema_version") != 1 or policy.get("agent_id") != context.agent_id:
        raise SandboxActivationError("policy_unavailable")
    audit = SandboxAuditPort(
        state_root=audit_state_root or _audit_state_root(env),
        checkout_roots=[common_repo],
        sender=event_sender,
    )
    launch = SandboxLaunch(
        agent_id=context.agent_id,
        worktree_root=context.worktree_root,
        common_repo=common_repo,
        common_git_dir=common_git,
        git_toplevel=git_toplevel,
        git_common_dir=common_git,
        vendor_executable=executable,
        vendor_install_root=_vendor_install_root(executable),
        policy=policy,
        write_capable=context.write_capable,
        credential_env_key=context.api_key_env,
        state_env_keys=context.state_env_keys,
        read_only_snapshot=(
            ".review-snapshots" in context.worktree_root.parts
        ),
    )
    event = _base_event(
        context, executable, preflight_status="passed", degradation_reason=None,
        runtime=runtime, policy=policy,
    )
    return SandboxActivation(launch, runtime, audit, event)
