#!/usr/bin/env python3
"""Deterministic half of the setup-coordinator skill.

Four subcommands:

* ``detect-harnesses`` — which coding-agent CLIs are present on this host.
* ``check`` — resolve the deployment profile and report every precondition.
* ``configure`` — the one mutating operation: add ``mcp__coordination__*`` to
  the Claude Code permissions allow-list.
* ``report`` — capability-flag summary for the active profile.

Two properties hold across all of them:

* **Nothing is executed.** No container is started, no vendor MCP configuration
  is written, no hook is installed, and no ``.secrets.yaml`` is created. Steps
  this entrypoint cannot perform are reported with the exact operator command
  that performs them.
* **Only the standard library and sibling skill modules are imported at module
  scope**, so the installed payload loads in a consumer repository that has no
  coordinator checkout. Sibling modules that may be absent are guarded.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Sibling-skill wiring
#
# Both siblings are imported by flat module name after a path insert rather than
# through a package facade: ``project-context-runtime``'s package __init__
# deliberately does not re-export the atomic primitives, and a facade import
# would break when the payload is installed without its parent package.
# --------------------------------------------------------------------------- #
_SKILLS_DIR = Path(__file__).resolve().parents[2]
_RUNTIME_SCRIPTS = _SKILLS_DIR / "project-context-runtime" / "scripts"
_VENDOR_SCRIPTS = _SKILLS_DIR / "parallel-infrastructure" / "scripts"
for _sibling in (_RUNTIME_SCRIPTS, _VENDOR_SCRIPTS):
    if _sibling.is_dir() and str(_sibling) not in sys.path:
        sys.path.insert(0, str(_sibling))


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of *directory* so a rename is durably recorded."""
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError:
        # Some network filesystems reject directory fsync. ``os.replace`` still
        # gives crash-atomicity for the file itself, so this is non-fatal.
        pass
    finally:
        os.close(fd)


def _inline_atomic_write_bytes(target: Path, payload: bytes) -> bool:
    """Atomic write used when ``project-context-runtime`` is not installed.

    This is a real temp-write → fsync → ``os.replace`` sequence, not an
    in-place write. A fallback is a degradation in dependency availability,
    never in the guarantees the caller was promised: atomicity is required on
    every path, not only when the sibling skill happens to be present.
    """
    target = Path(target)
    if target.exists():
        try:
            if target.read_bytes() == payload:
                return False
        except OSError:
            pass

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    handle_fd, tmp_name = tempfile.mkstemp(
        dir=str(parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle_fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    _fsync_dir(parent)
    return True


try:  # pragma: no cover - import wiring, exercised by the fallback reload test
    from atomic import atomic_write_bytes as _atomic_write_bytes
except Exception:  # pragma: no cover - consumer payload without the sibling
    _atomic_write_bytes = _inline_atomic_write_bytes

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

SCHEMA_VERSION = 1

#: Directory name of the coordinator checkout, used only to build the default
#: roster location. Deliberately kept on its own line and away from any path
#: constructor: the dependency-direction linter matches co-occurrence on a
#: single line rather than parsing imports, so a default embedded in a
#: constructor call would trip it without a single import existing.
COORDINATOR_DIRNAME = "agent-coordinator"

AGENTS_FILENAME = "agents.yaml"
SECRETS_FILENAME = ".secrets.yaml"
SECRETS_TEMPLATE = ".secrets.yaml.example"

LOCAL_SUFFIX = "-local"
WILDCARD = "mcp__coordination__*"
COORDINATION_PREFIX = "mcp__coordination__"
SETTINGS_RELATIVE = Path(".claude") / "settings.local.json"

PROFILES = ("local", "railway")
DEFAULT_PROFILE = "local"

CAPABILITY_FLAGS = (
    "CAN_LOCK",
    "CAN_QUEUE_WORK",
    "CAN_HANDOFF",
    "CAN_MEMORY",
    "CAN_GUARDRAILS",
)

#: Steps that prove a coordinator is actually usable, per transport. Presence of
#: an MCP registration or a resolved URL says the host is *configured*; only
#: these say it *works*. Every one of them is reported ``satisfied is None`` by
#: this entrypoint, which probes nothing on purpose -- which is exactly why the
#: capability flags derived from them fail closed.
VERIFYING_STEPS: dict[str, tuple[str, ...]] = {
    # Local: the coordinator runs against ParadeDB, so a container that is not
    # up is as disqualifying as tools that cannot be discovered. `bridge_detect`
    # is deliberately absent -- `collect_preconditions` only emits it on the
    # remote branch, and naming a step that is never emitted would pin the
    # flags to false forever instead of gating them.
    "local": ("database_container", "mcp_tools_discoverable"),
    "remote": ("api_health", "api_key_accepted", "bridge_detect"),
}

#: Home-relative configuration artifact per vendor. Data, not code: adding a
#: vendor is an edit here. ``None`` means the vendor declares no detectable
#: configuration location, which is reported as ``unknown`` — never as
#: ``config_missing``, because there is no login command to recommend.
HOME_CONFIG_ARTIFACTS: dict[str, str | None] = {
    "claude": ".claude.json",
    "codex": ".codex/auth.json",
    "grok": ".grok/auth.json",
    "pi": ".pi/agent/auth.json",
    "antigravity": None,
}

#: Authentication command per vendor, used only to build the ``config_missing``
#: remediation. A vendor with no entry gets a generic instruction rather than a
#: fabricated login command.
LOGIN_COMMANDS: dict[str, str] = {
    "claude": "claude",
    "codex": "codex login",
    "grok": "grok login",
    "pi": "pi auth login",
}

VALIDITY_DISCLAIMER = (
    "Presence only: credential validity and expiry were NOT checked. "
    "A vendor reported as ready may still hold an expired credential."
)


class RosterNotFoundError(Exception):
    """No readable ``agents.yaml`` at any configured location.

    Carries every path that was tried so the operator is told where to look
    instead of silently receiving a default agent set.
    """

    def __init__(self, tried: list[str]) -> None:
        self.tried = list(tried)
        super().__init__(
            "no readable agents.yaml; tried: " + ", ".join(self.tried)
        )


# --------------------------------------------------------------------------- #
# Roster resolution
# --------------------------------------------------------------------------- #


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def coordinator_dir(env: Mapping[str, str] | None = None) -> Path | None:
    """The configured coordinator checkout, or ``None`` when unset."""
    raw = _env(env).get("COORDINATOR_DIR")
    return Path(raw).expanduser() if raw else None


def resolve_agents_yaml(
    env: Mapping[str, str] | None = None,
) -> tuple[Path | None, list[str]]:
    """Resolve the agent roster locally and report every path tried.

    ``AGENTS_YAML`` wins over ``$COORDINATOR_DIR/agents.yaml``. Resolution is
    owned here rather than delegated: the shared loader falls through to an
    HTTP fetch and then to a working-directory-relative file when the explicit
    path does not exist, and returns an empty roster instead of failing. All
    three are forbidden, so the path handed to the loader is one this function
    has already confirmed exists.
    """
    environ = _env(env)
    tried: list[str] = []

    explicit = environ.get("AGENTS_YAML")
    if explicit:
        candidate = Path(explicit).expanduser().absolute()
        tried.append(str(candidate))
        if candidate.is_file():
            return candidate, tried
    else:
        tried.append("$AGENTS_YAML (unset)")

    # No cwd-relative last resort. Defaulting the base to a bare
    # Path(COORDINATOR_DIRNAME) would resolve against the process working
    # directory, which the spec forbids by name -- and it fails *silently*, in
    # the sense that the command succeeds from the repository root and fails
    # from anywhere else with identical environment. That is the same
    # cwd-dependence chain D1a exists to eliminate, and no test can catch it
    # while a fallback makes the vulnerable branch unreachable.
    base = coordinator_dir(environ)
    if base is None:
        tried.append("$COORDINATOR_DIR (unset)")
        return None, tried

    fallback = (base / AGENTS_FILENAME).absolute()
    tried.append(str(fallback))
    if fallback.is_file():
        return fallback, tried

    return None, tried


def _check_all_vendors(agents_yaml: Path) -> Any:
    """Call the shared vendor-health layer with an already-verified path.

    Imported at call time, not module scope, so the entrypoint still loads in a
    payload that does not ship ``parallel-infrastructure`` or does not have
    PyYAML installed. Every failure here degrades the report rather than
    aborting it.
    """
    from vendor_health import check_all_vendors

    return check_all_vendors(agents_yaml)


# --------------------------------------------------------------------------- #
# Harness detection
# --------------------------------------------------------------------------- #


def _classify(vendor: str, cli_on_path: bool, home: Path) -> tuple[str, str | None, bool | None]:
    """Return ``(state, config_artifact, config_present)``.

    Precedence is fixed: ``cli_missing`` first (decidable without the artifact
    table at all), then ``unknown`` when no artifact is declared, then
    ``ready``/``config_missing`` from the artifact check.
    """
    artifact = HOME_CONFIG_ARTIFACTS.get(vendor)
    if not cli_on_path:
        present = (home / artifact).exists() if artifact else None
        return "cli_missing", artifact, present
    if artifact is None:
        return "unknown", None, None
    if (home / artifact).exists():
        return "ready", artifact, True
    return "config_missing", artifact, False


def _remediation(vendor: str, command: str, state: str, artifact: str | None) -> str | None:
    if state == "cli_missing":
        return f"Install the {vendor} CLI so that `{command}` is on PATH."
    if state == "config_missing":
        login = LOGIN_COMMANDS.get(vendor)
        if login:
            return f"Authenticate the {vendor} CLI: run `{login}`."
        return f"Configure {vendor}; expected ~/{artifact} to exist."
    # `ready` needs nothing, and `unknown` must stay null: recommending a login
    # command for a vendor that has none is the failure this field avoids.
    return None


def build_harness_report(
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> dict:
    """Detect harness presence and return the report document.

    Raises ``RosterNotFoundError`` when no roster could be resolved — that is
    the only condition under which no report can be produced. Everything else
    (an unparseable roster, an unavailable sibling module) yields a report with
    ``degraded`` set and at least one warning, so a caller can tell an
    incomplete run from one that genuinely found nothing.
    """
    home = Path.home() if home is None else Path(home)
    warnings: list[str] = []

    resolved, tried = resolve_agents_yaml(env)
    if resolved is None:
        raise RosterNotFoundError(tried)

    health: Any = None
    try:
        health = _check_all_vendors(resolved)
    except Exception as exc:  # noqa: BLE001 - any failure degrades, none aborts
        warnings.append(
            f"vendor_health detection layer unavailable ({type(exc).__name__}: {exc}); "
            f"roster {resolved} was resolved but could not be read"
        )

    vendors: list[dict] = []
    seen: set[str] = set()
    if health is not None:
        for entry in health.vendors:
            agent_id = str(entry.agent_id)
            if not agent_id.endswith(LOCAL_SUFFIX):
                continue
            command = str(entry.cli_command or "").strip()
            if not command:
                continue
            vendor = agent_id[: -len(LOCAL_SUFFIX)]
            if vendor in seen:
                continue
            seen.add(vendor)

            cli_on_path = bool(entry.cli_installed)
            state, artifact, present = _classify(vendor, cli_on_path, home)
            vendors.append(
                {
                    "vendor": vendor,
                    "agent_id": agent_id,
                    "agent_type": str(entry.vendor_type or "unknown"),
                    "cli_command": command,
                    "cli_on_path": cli_on_path,
                    "config_artifact": artifact,
                    "config_present": present,
                    "state": state,
                    "remediation": _remediation(vendor, command, state, artifact),
                }
            )

    vendors.sort(key=lambda item: item["vendor"])
    summary = {name: 0 for name in ("ready", "cli_missing", "config_missing", "unknown")}
    for entry in vendors:
        summary[entry["state"]] += 1
    summary["total"] = len(vendors)

    return {
        "schema_version": SCHEMA_VERSION,
        "checked_validity": False,
        "degraded": bool(warnings),
        "warnings": warnings,
        "host": {"platform": sys.platform, "home": str(home)},
        "vendors": vendors,
        "summary": summary,
    }


def render_harness_report(report: dict) -> str:
    """Human-readable rendering. Never emitted alongside ``--json`` output."""
    lines: list[str] = []
    header = f"{'Vendor':<14} {'CLI':<6} {'Config':<8} {'State':<15} Remediation"
    lines.append(header)
    lines.append("-" * len(header))
    for entry in report["vendors"]:
        cli = "ok" if entry["cli_on_path"] else "-"
        if entry["config_present"] is None:
            cfg = "n/a"
        else:
            cfg = "ok" if entry["config_present"] else "-"
        lines.append(
            f"{entry['vendor']:<14} {cli:<6} {cfg:<8} {entry['state']:<15} "
            f"{entry['remediation'] or ''}"
        )
    summary = report["summary"]
    lines.append("")
    lines.append(
        "ready={ready} cli_missing={cli_missing} config_missing={config_missing} "
        "unknown={unknown} total={total}".format(**summary)
    )
    if report["degraded"]:
        lines.append("")
        lines.append("DEGRADED — this report is incomplete:")
        lines.extend(f"  - {warning}" for warning in report["warnings"])
    lines.append("")
    lines.append(VALIDITY_DISCLAIMER)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Settings allow-list
# --------------------------------------------------------------------------- #


def settings_path_for_root(root: Path | str) -> Path:
    """Resolve the settings file absolutely from an explicit root.

    Never derived from the process working directory: an operator invoking this
    from a subdirectory must still write the repository's settings file rather
    than create a new one where they happen to stand.
    """
    return Path(root).expanduser().resolve() / SETTINGS_RELATIVE


_INDENT_RE = re.compile(r"^([ \t]+)\S", re.MULTILINE)


def _detect_indent(text: str) -> int | str:
    """Infer the input's indentation so re-serialization preserves it."""
    match = _INDENT_RE.search(text)
    if not match:
        return 2
    whitespace = match.group(1)
    if whitespace.startswith("\t"):
        return "\t"
    return len(whitespace)


def _serialize(data: Any, *, indent: int | str, trailing_newline: bool) -> bytes:
    text = json.dumps(data, indent=indent, ensure_ascii=False)
    if trailing_newline:
        text += "\n"
    return text.encode("utf-8")


def add_coordination_permission(root: Path | str) -> dict:
    """Add ``mcp__coordination__*`` to the permissions allow-list.

    The membership test is scoped to the allow-list specifically: a textual scan
    of the file would be satisfied by the wildcard appearing in a ``deny`` list
    and would then report success while doing nothing.

    Only ``permissions.allow`` is mutated. Key order is the order read from the
    input and indentation is inherited from it, so the only textual difference
    between input and output falls inside the allow-list. When nothing needs to
    change the file is not touched at all — not even rewritten to identical
    bytes — which keeps a re-run a no-op against a file that is not in
    canonical JSON form.
    """
    path = settings_path_for_root(root)
    existed = path.is_file()
    raw = path.read_text(encoding="utf-8") if existed else ""

    if raw.strip():
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: settings file must contain a JSON object")
    else:
        data = {}

    permissions = data.get("permissions")
    if not isinstance(permissions, dict):
        permissions = {}
    allow = permissions.get("allow")
    if not isinstance(allow, list):
        allow = []

    kept = [
        item
        for item in allow
        if not (isinstance(item, str) and item.startswith(COORDINATION_PREFIX))
    ]
    already = WILDCARD in allow
    collapsed = [item for item in allow if item not in kept and item != WILDCARD]
    desired = [*kept, WILDCARD]

    # "Already configured" is about membership, not position. Comparing against
    # `desired` (which appends the wildcard last) would rewrite a file whose
    # allow-list already carries the wildcard somewhere other than the end --
    # reordering an operator's list to satisfy an internal preference, and
    # breaking "SHALL make no modification" for a file that needs none. Only an
    # entry that actually has to be collapsed justifies a write.
    if already and not collapsed:
        return {
            "changed": False,
            "path": str(path),
            "reason": "already-configured",
            "collapsed": [],
        }

    permissions["allow"] = desired
    data["permissions"] = permissions

    payload = _serialize(
        data,
        indent=_detect_indent(raw) if existed else 2,
        trailing_newline=raw.endswith("\n") if raw else True,
    )
    changed = _atomic_write_bytes(path, payload)
    return {
        "changed": bool(changed),
        "path": str(path),
        "reason": "wildcard-added" if not already else "allow-list-collapsed",
        "collapsed": collapsed,
    }


def allowlist_has_wildcard(root: Path | str) -> bool:
    """Whether the wildcard is present in ``permissions.allow`` specifically."""
    path = settings_path_for_root(root)
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    permissions = data.get("permissions")
    allow = permissions.get("allow") if isinstance(permissions, dict) else None
    return isinstance(allow, list) and WILDCARD in allow


# --------------------------------------------------------------------------- #
# Profile resolution and preconditions
# --------------------------------------------------------------------------- #


def resolve_profile(
    explicit: str | None = None, env: Mapping[str, str] | None = None
) -> str:
    """``--profile`` beats ``COORDINATOR_PROFILE`` beats ``local``."""
    candidate = explicit or _env(env).get("COORDINATOR_PROFILE") or DEFAULT_PROFILE
    if candidate not in PROFILES:
        raise ValueError(
            f"unknown profile {candidate!r}; expected one of {', '.join(PROFILES)}"
        )
    return candidate


def load_profile_yaml(
    profile: str, env: Mapping[str, str] | None = None
) -> tuple[dict, list[str]]:
    """Read the deployment profile YAML directly. Returns ``(data, warnings)``.

    Implemented against the YAML rather than by importing coordinator source,
    which a sibling clause of the same requirement forbids.
    """
    base = coordinator_dir(env)
    if base is None:
        return {}, []
    target = base / "profiles" / f"{profile}.yaml"
    if not target.is_file():
        return {}, [f"profile file not found: {target}"]
    try:
        import yaml

        loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - a missing parser degrades, not aborts
        return {}, [f"profile {target} could not be read ({type(exc).__name__}: {exc})"]
    return (loaded if isinstance(loaded, dict) else {}), []


def _step(
    step_id: str, label: str, satisfied: bool | None, detail: str, command: str | None
) -> dict:
    """One precondition. ``command`` is present exactly when not satisfied."""
    return {
        "id": step_id,
        "label": label,
        "satisfied": satisfied,
        "detail": detail,
        "command": None if satisfied is True else command,
    }


def _mcp_registered(home: Path) -> bool:
    """Whether the coordination MCP server is registered in Claude Code's own
    configuration. Read-only: this entrypoint never writes vendor MCP config."""
    config = home / ".claude.json"
    if not config.is_file():
        return False
    try:
        data = json.loads(config.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return False
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    return isinstance(servers, dict) and "coordination" in servers


def _secrets_step(base: Path | None) -> dict:
    if base is None:
        return _step(
            "secrets_file",
            "Coordinator secrets file present",
            False,
            "COORDINATOR_DIR is unset, so the secrets file location is unknown.",
            f'cp "$COORDINATOR_DIR/{SECRETS_TEMPLATE}" "$COORDINATOR_DIR/{SECRETS_FILENAME}"'
            " and fill in real values before continuing",
        )
    secrets = base / SECRETS_FILENAME
    return _step(
        "secrets_file",
        "Coordinator secrets file present",
        secrets.is_file(),
        f"Looked for {secrets}.",
        f'cp "{base / SECRETS_TEMPLATE}" "{secrets}"'
        " and fill in real values before continuing",
    )


def _permissions_step(root: Path) -> dict:
    return _step(
        "permissions_allowlist",
        "Coordination tools allow-listed in Claude Code permissions",
        allowlist_has_wildcard(root),
        f"Looked for {WILDCARD} in {settings_path_for_root(root)}.",
        f"scripts/setup_coordinator.py configure --root {root}",
    )


def collect_preconditions(
    profile: str,
    *,
    root: Path,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> tuple[list[dict], list[str]]:
    """Report every precondition for *profile*. Returns ``(steps, warnings)``.

    Nothing here executes anything. Steps whose truth cannot be established
    without starting a process are reported with ``satisfied: None`` and the
    exact operator command, rather than guessed or performed.
    """
    home = Path.home() if home is None else Path(home)
    base = coordinator_dir(env)
    profile_data, warnings = load_profile_yaml(profile, env)
    steps: list[dict] = [_secrets_step(base), _permissions_step(root)]

    if profile == "local":
        runtime = shutil.which("docker") or shutil.which("podman")
        steps.append(
            _step(
                "container_runtime",
                "Container runtime present (Docker / Podman)",
                runtime is not None,
                f"Found {runtime}." if runtime else "Neither docker nor podman is on PATH.",
                "Install Docker Desktop or Podman and ensure `docker` is on PATH",
            )
        )
        steps.append(
            _step(
                "database_container",
                "ParadeDB container running and healthy",
                None,
                "Not verifiable without starting a process; this entrypoint starts none.",
                'docker compose --project-directory "$COORDINATOR_DIR"'
                ' -f "$COORDINATOR_DIR/docker-compose.yml" up -d',
            )
        )
        steps.append(
            _step(
                "mcp_registered",
                "MCP server registered in the vendor's own configuration",
                _mcp_registered(home),
                f"Looked for an `mcpServers.coordination` entry in {home / '.claude.json'}.",
                'make -C "$COORDINATOR_DIR" mcp-setup',
            )
        )
        steps.append(
            _step(
                "mcp_tools_discoverable",
                "Coordination tools discoverable through the registered MCP server",
                None,
                "Requires a live MCP session; this entrypoint opens none.",
                "claude mcp list",
            )
        )
    else:
        api_url = _env(env).get("COORDINATION_API_URL") or str(
            profile_data.get("coordination_api_url") or ""
        )
        steps.append(
            _step(
                "api_url",
                "COORDINATION_API_URL resolved (from profile + secrets)",
                bool(api_url),
                f"Resolved {api_url}." if api_url else "Not set in the environment or profile.",
                "export COORDINATION_API_URL=https://<your-app>.railway.app",
            )
        )
        steps.append(
            _step(
                "api_health",
                "Coordination API health endpoint reachable",
                None,
                "Not verifiable without issuing a request; this entrypoint issues none.",
                'curl -s "$COORDINATION_API_URL/health"',
            )
        )
        steps.append(
            _step(
                "api_key_accepted",
                "API key accepted on a write endpoint",
                None,
                "Not verifiable without issuing a request; this entrypoint issues none.",
                'curl -s -X POST -H "X-API-Key: $COORDINATION_API_KEY"'
                ' "$COORDINATION_API_URL/agents/register"',
            )
        )
        steps.append(
            _step(
                "bridge_detect",
                "Bridge-level capability detection",
                None,
                "Delegated to the coordination-bridge sibling skill.",
                'python3 "<skill-base-dir>/../coordination-bridge/scripts/'
                'coordination_bridge.py" detect',
            )
        )

    return steps, warnings


def capability_flags(profile: str, steps: list[dict]) -> dict:
    """Capability summary derived from the reported preconditions.

    Two different questions are answered separately, because conflating them is
    a safety bug rather than a cosmetic one.

    ``COORDINATOR_CONFIGURED`` -- this host has the transport wired up: an MCP
    registration for the local profile, a resolved API URL otherwise. That is
    what `configure` can establish without running anything.

    ``COORDINATOR_AVAILABLE`` and the ``CAN_*`` flags -- the coordinator has
    been *verified* to work. Integrated skills auto-select coordinated
    execution from these, so they fail closed: a precondition this entrypoint
    cannot verify counts against availability, never for it. Because the
    entrypoint deliberately probes nothing, the verifying steps are always
    UNKNOWN here and the flags stay false until something that does probe --
    the coordination-bridge skill -- reports otherwise. That is the intended
    outcome: an unreachable or half-configured coordinator must trigger
    standalone fallback rather than be advertised as fully capable.

    Previously every ``CAN_*`` was set to the *configured* value, so an empty
    ``mcpServers.coordination`` entry, or merely exporting
    ``COORDINATION_API_URL``, advertised all five capabilities while health,
    authentication, discovery and bridge detection were all still UNKNOWN.
    """
    by_id = {step["id"]: step for step in steps}
    if profile == "local":
        configured = by_id.get("mcp_registered", {}).get("satisfied") is True
        transport = "mcp" if configured else "none"
        verifiers = VERIFYING_STEPS["local"]
    else:
        configured = by_id.get("api_url", {}).get("satisfied") is True
        transport = "http" if configured else "none"
        verifiers = VERIFYING_STEPS["remote"]

    # A verifier that is not among the emitted steps would silently make every
    # capability false forever -- indistinguishable from a genuinely
    # unverified host. Fail loudly instead; this is a wiring error, not a
    # host condition.
    missing = [step_id for step_id in verifiers if step_id not in by_id]
    if missing:
        raise KeyError(
            f"VERIFYING_STEPS[{profile!r}] names steps that collect_preconditions "
            f"never emits: {missing}"
        )

    # Kept per step rather than as a bare boolean so the caller can see which
    # check is missing and the command that would settle it.
    unverified = [
        {
            "id": step_id,
            "label": by_id.get(step_id, {}).get("label", step_id),
            "command": by_id.get(step_id, {}).get("command"),
        }
        for step_id in verifiers
        if by_id.get(step_id, {}).get("satisfied") is not True
    ]

    available = configured and not unverified
    flags = {name: available for name in CAPABILITY_FLAGS}
    return {
        "profile": profile,
        "COORDINATION_TRANSPORT": transport,
        "COORDINATOR_CONFIGURED": configured,
        "COORDINATOR_AVAILABLE": available,
        "capabilities": flags,
        "unverified_preconditions": unverified,
        "hook_activation_rule": "A hook runs only when its CAN_* flag is true.",
    }


# --------------------------------------------------------------------------- #
# Subcommand handlers
# --------------------------------------------------------------------------- #


def _emit(payload: dict, rendered: str, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)


def cmd_detect_harnesses(args: argparse.Namespace) -> int:
    try:
        report = build_harness_report()
    except RosterNotFoundError as exc:
        print("Could not resolve an agent roster. Tried:", file=sys.stderr)
        for candidate in exc.tried:
            print(f"  - {candidate}", file=sys.stderr)
        print(
            "Set AGENTS_YAML or COORDINATOR_DIR; refusing to assume a default agent set.",
            file=sys.stderr,
        )
        return 1
    _emit(report, render_harness_report(report), as_json=args.json_output)
    # Vendor states are data, not failures: a host with one CLI absent is an
    # ordinary host. Exit non-zero only when no report could be produced.
    return 0


def _resolve_or_fail(args: argparse.Namespace) -> str | None:
    try:
        return resolve_profile(getattr(args, "profile", None))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return None


def cmd_check(args: argparse.Namespace) -> int:
    profile = _resolve_or_fail(args)
    if profile is None:
        return 2
    root = Path(args.root).expanduser().resolve()
    steps, warnings = collect_preconditions(profile, root=root, env=os.environ)
    unsatisfied = [step for step in steps if step["satisfied"] is not True]
    payload = {
        "profile": profile,
        "root": str(root),
        "preconditions": steps,
        "warnings": warnings,
        "satisfied": not unsatisfied,
    }

    lines = [f"Profile: {profile}", f"Root: {root}", ""]
    for step in steps:
        mark = {True: "ok", False: "MISSING"}.get(step["satisfied"], "UNKNOWN")
        lines.append(f"[{mark:>7}] {step['label']}")
        lines.append(f"          {step['detail']}")
        if step["command"]:
            lines.append(f"          run: {step['command']}")
    if warnings:
        lines.append("")
        lines.extend(f"warning: {warning}" for warning in warnings)
    lines.append("")
    lines.append(
        "This command reports only. It starts no container, writes no vendor MCP "
        f"configuration, installs no hooks, and never creates {SECRETS_FILENAME}."
    )

    _emit(payload, "\n".join(lines), as_json=args.json_output)
    return 0 if not unsatisfied else 1


def cmd_report(args: argparse.Namespace) -> int:
    profile = _resolve_or_fail(args)
    if profile is None:
        return 2
    root = Path(args.root).expanduser().resolve()
    steps, warnings = collect_preconditions(profile, root=root, env=os.environ)
    payload = capability_flags(profile, steps)
    payload["warnings"] = warnings

    lines = [
        f"Profile: {payload['profile']}",
        f"COORDINATION_TRANSPORT={payload['COORDINATION_TRANSPORT']}",
        f"COORDINATOR_CONFIGURED={str(payload['COORDINATOR_CONFIGURED']).lower()}",
        f"COORDINATOR_AVAILABLE={str(payload['COORDINATOR_AVAILABLE']).lower()}",
        "",
    ]
    lines.extend(
        f"{name}={str(value).lower()}" for name, value in payload["capabilities"].items()
    )
    lines.append("")
    lines.append(payload["hook_activation_rule"])
    if payload["unverified_preconditions"]:
        lines.append("")
        lines.append(
            "Capabilities are false because these preconditions are unverified "
            "(this entrypoint probes nothing):"
        )
        lines.extend(
            f"  - {item['label']}" + (f" -> {item['command']}" if item["command"] else "")
            for item in payload["unverified_preconditions"]
        )
    if warnings:
        lines.extend(f"warning: {warning}" for warning in warnings)

    _emit(payload, "\n".join(lines), as_json=args.json_output)
    # Keyed to CONFIGURED, not AVAILABLE: this command reports whether setup
    # succeeded, and setup is configuration. Verification is delegated to the
    # coordination-bridge skill, so keying the exit code to AVAILABLE would make
    # `report` fail on every correctly configured host.
    return 0 if payload["COORDINATOR_CONFIGURED"] else 1


def cmd_configure(args: argparse.Namespace) -> int:
    try:
        result = add_coordination_permission(args.root)
    except (OSError, ValueError) as exc:
        print(f"Could not update the permissions allow-list: {exc}", file=sys.stderr)
        return 1

    next_steps = [
        'make -C "$COORDINATOR_DIR" mcp-setup',
        'make -C "$COORDINATOR_DIR" hooks-setup',
    ]
    result["next_steps"] = next_steps

    lines = [
        f"{'updated' if result['changed'] else 'unchanged'}: {result['path']}",
        f"reason: {result['reason']}",
    ]
    if result["collapsed"]:
        lines.append("collapsed into the wildcard: " + ", ".join(result["collapsed"]))
    lines.append("")
    lines.append("Operator-owned next steps (this entrypoint does not run them):")
    lines.extend(f"  {step}" for step in next_steps)

    _emit(result, "\n".join(lines), as_json=args.json_output)
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    # Bound to `json_output`, not `json`: a `json` destination would shadow the
    # module inside any handler that touches the namespace.
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit a single JSON document on stdout instead of a table.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="setup_coordinator.py",
        description="Configure and verify coordinator access.",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    detect = subparsers.add_parser(
        "detect-harnesses", help="Report which coding-agent CLIs are present."
    )
    _add_json_flag(detect)
    detect.set_defaults(handler=cmd_detect_harnesses)

    check = subparsers.add_parser(
        "check", help="Resolve the profile and report every precondition."
    )
    check.add_argument("--profile", choices=list(PROFILES), default=None)
    check.add_argument("--root", default=".", help="Repository root to inspect.")
    _add_json_flag(check)
    check.set_defaults(handler=cmd_check)

    report = subparsers.add_parser("report", help="Capability-flag summary.")
    report.add_argument("--profile", choices=list(PROFILES), default=None)
    report.add_argument("--root", default=".", help="Repository root to inspect.")
    _add_json_flag(report)
    report.set_defaults(handler=cmd_report)

    configure = subparsers.add_parser(
        "configure", help="Add the coordination wildcard to the permissions allow-list."
    )
    configure.add_argument(
        "--root",
        required=True,
        help="Repository root whose settings file is updated. Required so the "
        "target never depends on the current working directory.",
    )
    _add_json_flag(configure)
    configure.set_defaults(handler=cmd_configure)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_usage(sys.stderr)
        return 2
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
