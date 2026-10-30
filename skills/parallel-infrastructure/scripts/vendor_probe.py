"""Tiered, token-free local probe for vendor CLI lanes.

Design (openspec/changes/add-local-agent-probe):
  D1  Stdlib-only; loaded by file path from the coordinator container.
  D2  Required flags are derived from ``dispatch_modes.<mode>.args`` + ``*_flag`` keys.
  D3  Auth is exit-code-only; credential files are checked for existence only.
  D4  Per-user cache, fingerprinted over a normalized projection of the cli block.
  D6  Runtime failures live in a separate, account-scoped map.
  D10 Bounded concurrency: 10 s per subprocess, 25 s per lane.
  D11 ``probe_lanes(reuse_fresh=...)`` decides who re-probes.

Tiers: L0 presence (``shutil.which``), L1 capability (version + help flags per
mode), L2 auth (status command exit code, or credential file existence).
The probe never executes a dispatch-mode argument vector.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:  # pragma: no cover - platform dependent
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

logger = logging.getLogger("vendor_probe")

SCHEMA_VERSION = 1
SUBPROCESS_TIMEOUT = 10.0
LANE_DEADLINE = 25.0
MAX_WORKERS = 8
REPORT_TIMEOUT = 60.0
DEFAULT_LANE_TTL = 24 * 3600
DEFAULT_FAILURE_TTL = 3600
VERSION_MAX_CHARS = 200
DEFAULT_VERSION_ARGS = ["--version"]
DEFAULT_MODEL_FLAG = "-m"
HELP_TOKENS = {"--help", "-h", "help"}

# Reasons that exclude a lane from dispatch. ``probe_timeout`` never does.
EXCLUDING_REASONS = frozenset(
    {
        "cli_not_found",
        "missing_flags",
        "probe_failed",
        "auth_failed",
        "runtime_auth_required",
        "runtime_vendor_unavailable",
    }
)

_RUNTIME_REASON = {
    "auth_required": "runtime_auth_required",
    "vendor_unavailable": "runtime_vendor_unavailable",
}

_cache_lock = threading.Lock()


# --------------------------------------------------------------------- helpers


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: float | None = None) -> str:
    dt = datetime.fromtimestamp(ts, timezone.utc) if ts is not None else _utcnow()
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _is_probe_declared(cli: dict[str, Any]) -> bool:
    return cli.get("probe") is not None


def _modes(cli: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, cfg in (cli.get("dispatch_modes") or {}).items():
        args = cfg.get("args") if isinstance(cfg, dict) else getattr(cfg, "args", None)
        out[name] = [str(a) for a in (args or [])]
    return out


# ----------------------------------------------------------- flags and fingerprint


def injected_flags(cli: dict[str, Any]) -> dict[str, str]:
    """``*_flag`` keys of the normalized projection (model_flag defaults to -m)."""
    flags: dict[str, str] = {}
    for key, value in cli.items():
        if not key.endswith("_flag") or key == "model_flag":
            continue
        if value is not None:
            flags[key] = str(value)
    model_flag = cli.get("model_flag")
    flags["model_flag"] = DEFAULT_MODEL_FLAG if model_flag is None else str(model_flag)
    return flags


def _normalize_probe(probe: dict[str, Any] | None) -> dict[str, Any] | None:
    if probe is None:
        return None
    norm: dict[str, Any] = {}
    for key, value in probe.items():
        if value is None:
            continue
        if key == "version_args" and list(value) == DEFAULT_VERSION_ARGS:
            continue
        norm[key] = value
    return norm


def lane_fingerprint(cli: dict[str, Any]) -> str:
    """sha256 over the normalized probe-relevant projection of a cli block."""
    projection = {
        "command": cli.get("command"),
        "modes": _modes(cli),
        "flags": injected_flags(cli),
        "probe": _normalize_probe(cli.get("probe")),
    }
    blob = json.dumps(projection, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()


def mode_required_flags(cli: dict[str, Any], mode: str) -> list[str]:
    """Flags the mode passes plus the injected ``*_flag`` values, minus ignores."""
    flags: list[str] = []
    for token in _modes(cli).get(mode, []):
        if not token.startswith("-") or token in ("-", "--"):
            continue
        flag = token.split("=", 1)[0]
        if flag not in flags:
            flags.append(flag)
    for value in injected_flags(cli).values():
        if value.startswith("-") and value not in flags:
            flags.append(value)
    ignored = set((cli.get("probe") or {}).get("ignore_flags") or [])
    return [f for f in flags if f not in ignored]


def mode_help_argv(cli: dict[str, Any], mode: str) -> list[str]:
    """Help argv (after the command) for a mode: override or generated."""
    override = ((cli.get("probe") or {}).get("help_args") or {}).get(mode)
    if override:
        return [str(a) for a in override]
    path: list[str] = []
    for token in _modes(cli).get(mode, []):
        if token.startswith("-"):
            break
        path.append(token)
    return [*path, "--help"]


def flag_in_help(flag: str, help_text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", help_text) is not None


# ------------------------------------------------------------------ subprocesses


def _run(argv: list[str], timeout: float, capture: bool) -> tuple[str, int | None, str]:
    """Run argv; return (status, returncode, output).

    status is ``ok`` | ``timeout`` | ``launch_error``. stdin is always DEVNULL.
    With capture=False output is never read (stdout/stderr go to DEVNULL).
    """
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.STDOUT if capture else subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return "launch_error", None, ""
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            proc.kill()
        try:
            proc.communicate(timeout=2)
        except Exception:  # noqa: BLE001 - best effort reap
            pass
        return "timeout", None, ""
    text = out.decode("utf-8", "replace") if capture and out else ""
    return "ok", proc.returncode, text


class _Budget:
    def __init__(self, seconds: float) -> None:
        self._end = time.monotonic() + seconds

    def remaining(self) -> float:
        return self._end - time.monotonic()

    def timeout(self) -> float:
        return min(SUBPROCESS_TIMEOUT, self.remaining())


# ------------------------------------------------------------------- lane probe


@dataclass
class LaneProbe:
    """Result of probing one lane."""

    agent_id: str
    entry: dict[str, Any]
    auth_started_at: float | None = None
    runtime_failure: dict[str, Any] | None = None
    reused: bool = False


def _tier_ok() -> dict[str, Any]:
    return {"ok": True}


def _tier_fail(reason: str, missing: list[str] | None = None) -> dict[str, Any]:
    tier: dict[str, Any] = {"ok": False, "reason": reason}
    if missing is not None:
        tier["missing_flags"] = missing
    return tier


def _l2_method(probe: dict[str, Any]) -> str:
    if probe.get("auth_status_args"):
        return "status_command"
    if probe.get("credential_files"):
        return "credential_files"
    return "none"


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:VERSION_MAX_CHARS]
    return None


def probe_lane(
    agent_id: str, cli: dict[str, Any], *, lane_deadline: float = LANE_DEADLINE
) -> LaneProbe:
    """Run L0, L1 and L2 for one lane. Never executes a dispatch-mode argv."""
    command = cli.get("command") or ""
    probe = cli.get("probe") or {}
    declared = _is_probe_declared(cli)
    budget = _Budget(lane_deadline)
    mode_names = list(_modes(cli))
    found = shutil.which(command) if command else None
    realpath = os.path.realpath(found) if found else None
    method = _l2_method(probe)
    version: str | None = None
    auth_started: float | None = None

    if not found:
        l0 = _tier_fail("cli_not_found")
        modes = {m: _tier_fail("cli_not_found") for m in mode_names}
    else:
        l0 = _tier_ok()
        modes = {}
        v_status, v_rc, v_out = _run_budgeted(
            [command, *(probe.get("version_args") or DEFAULT_VERSION_ARGS)],
            budget,
            capture=True,
        )
        if v_status == "ok" and v_rc == 0:
            version = _first_line(v_out)
            helps: dict[tuple[str, ...], tuple[str, int | None, str]] = {}
            for mode in mode_names:
                if not declared:
                    modes[mode] = _tier_ok()
                    continue
                argv = tuple(mode_help_argv(cli, mode))
                if argv not in helps:
                    helps[argv] = _run_budgeted([command, *argv], budget, capture=True)
                h_status, h_rc, h_out = helps[argv]
                if h_status != "ok":
                    modes[mode] = _tier_fail(
                        "probe_timeout" if h_status == "timeout" else "probe_failed"
                    )
                elif h_rc != 0:
                    modes[mode] = _tier_fail("probe_failed")
                else:
                    missing = [
                        f
                        for f in mode_required_flags(cli, mode)
                        if not flag_in_help(f, h_out)
                    ]
                    modes[mode] = (
                        _tier_fail("missing_flags", missing) if missing else _tier_ok()
                    )
        else:
            reason = (
                "probe_timeout"
                if v_status == "timeout"
                else "probe_failed"
            )
            modes = {m: _tier_fail(reason) for m in mode_names}

    # L2
    if method == "status_command":
        if not found:
            l2 = {"status": "auth_unknown", "method": method}
        elif budget.remaining() <= 0:
            l2 = {"status": "probe_timeout", "method": method}
        else:
            auth_started = time.time()
            a_status, a_rc, _ = _run(
                [command, *probe["auth_status_args"]], budget.timeout(), capture=False
            )
            if a_status == "timeout":
                l2 = {"status": "probe_timeout", "method": method}
            elif a_status == "launch_error":
                l2 = {"status": "auth_unknown", "method": method}
                auth_started = None
            else:
                l2 = {
                    "status": "auth_ok" if a_rc == 0 else "auth_failed",
                    "method": method,
                }
    elif method == "credential_files":
        ok = all(Path(p).expanduser().exists() for p in probe["credential_files"])
        l2 = {"status": "auth_ok" if ok else "auth_failed", "method": method}
    else:
        l2 = {"status": "auth_unknown", "method": "none"}

    entry = {
        "agent_id": agent_id,
        "command": command,
        "cli_realpath": realpath,
        "cli_version": version,
        "config_fingerprint": lane_fingerprint(cli),
        "probed_at": _iso(),
        "ttl_seconds": DEFAULT_LANE_TTL,
        "l0": l0,
        "modes": modes,
        "l2": l2,
    }
    return LaneProbe(agent_id=agent_id, entry=entry, auth_started_at=auth_started)


def _run_budgeted(
    argv: list[str], budget: _Budget, capture: bool
) -> tuple[str, int | None, str]:
    if budget.remaining() <= 0:
        return "timeout", None, ""
    return _run(argv, budget.timeout(), capture)


# ------------------------------------------------------------------------- cache


def cache_path() -> Path:
    explicit = os.environ.get("AGENTIC_PROBE_CACHE")
    if explicit:
        return Path(explicit).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "agentic-coding-tools" / "vendor-probe.json"


def _empty_doc() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "lanes": {}, "runtime_failures": {}}


def _valid_doc(doc: Any) -> bool:
    return (
        isinstance(doc, dict)
        and doc.get("schema_version") == SCHEMA_VERSION
        and isinstance(doc.get("lanes"), dict)
        and isinstance(doc.get("runtime_failures", {}), dict)
    )


def read_cache(path: Path | None = None) -> dict[str, Any]:
    """Read the cache; a missing, unparseable or invalid file is empty. No lock."""
    target = path or cache_path()
    try:
        doc = json.loads(target.read_text())
    except (OSError, ValueError):
        return _empty_doc()
    if not _valid_doc(doc):
        return _empty_doc()
    doc.setdefault("runtime_failures", {})
    return doc


def update_cache(
    mutate: Callable[[dict[str, Any]], None], path: Path | None = None
) -> bool:
    """Locked read-modify-write with an atomic 0600 replace. Best-effort."""
    target = path or cache_path()
    lock_file = None
    try:
        with _cache_lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            if fcntl is not None:
                lock_file = open(str(target) + ".lock", "a")  # noqa: SIM115
                fcntl.flock(lock_file, fcntl.LOCK_EX)
            doc = read_cache(target)
            mutate(doc)
            fd, tmp = tempfile.mkstemp(
                dir=str(target.parent), prefix=".vendor-probe-", suffix=".tmp"
            )
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "w") as fh:
                    json.dump(doc, fh, indent=2, sort_keys=True)
                os.replace(tmp, target)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        return True
    except OSError as exc:
        logger.warning("vendor probe cache not written (%s): %s", target, exc)
        return False
    finally:
        if lock_file is not None:
            try:
                lock_file.close()
            except OSError:
                pass


def _clear_auth_failure(doc: dict[str, Any], probe: LaneProbe) -> None:
    """Drop an auth_required failure disproved by a later status-command probe."""
    l2 = probe.entry.get("l2") or {}
    if l2.get("status") != "auth_ok" or l2.get("method") != "status_command":
        return
    if probe.auth_started_at is None:
        return
    failures = doc.setdefault("runtime_failures", {})
    record = failures.get(probe.agent_id)
    if not record or record.get("error_class") != "auth_required":
        return
    observed = _parse_ts(record.get("observed_at"))
    if observed is not None and observed < probe.auth_started_at:
        del failures[probe.agent_id]


def store_probes(probes: list[LaneProbe], path: Path | None = None) -> bool:
    def mutate(doc: dict[str, Any]) -> None:
        for probe in probes:
            doc["lanes"][probe.agent_id] = probe.entry
            _clear_auth_failure(doc, probe)

    return update_cache(mutate, path)


def record_runtime_failure(
    agent_id: str,
    error_class: str,
    ttl_seconds: int = DEFAULT_FAILURE_TTL,
    path: Path | None = None,
    now: float | None = None,
) -> bool:
    """Record an account-scoped dispatch failure. Best-effort; never raises."""
    if error_class not in _RUNTIME_REASON:
        raise ValueError(f"unsupported runtime error class: {error_class}")

    def mutate(doc: dict[str, Any]) -> None:
        doc.setdefault("runtime_failures", {})[agent_id] = {
            "error_class": error_class,
            "observed_at": _iso(now),
            "ttl_seconds": ttl_seconds,
        }

    return update_cache(mutate, path)


def fresh_runtime_failure(
    doc: dict[str, Any], agent_id: str, now: float | None = None
) -> dict[str, Any] | None:
    record = (doc.get("runtime_failures") or {}).get(agent_id)
    if not isinstance(record, dict):
        return None
    observed = _parse_ts(record.get("observed_at"))
    ttl = record.get("ttl_seconds")
    if observed is None or not isinstance(ttl, int):
        return None
    current = time.time() if now is None else now
    if current - observed >= ttl or record.get("error_class") not in _RUNTIME_REASON:
        return None
    return record


def current_realpath(command: str) -> str | None:
    found = shutil.which(command) if command else None
    return os.path.realpath(found) if found else None


def fresh_entry(
    doc: dict[str, Any],
    agent_id: str,
    cli: dict[str, Any],
    now: float | None = None,
    max_age_seconds: int | None = None,
) -> dict[str, Any] | None:
    """Cached lane entry if TTL, realpath and fingerprint all still match."""
    entry = (doc.get("lanes") or {}).get(agent_id)
    if not isinstance(entry, dict):
        return None
    probed = _parse_ts(entry.get("probed_at"))
    ttl = entry.get("ttl_seconds")
    if probed is None or not isinstance(ttl, int):
        return None
    current = time.time() if now is None else now
    age = current - probed
    if age >= ttl or (max_age_seconds is not None and age >= max_age_seconds):
        return None
    if entry.get("config_fingerprint") != lane_fingerprint(cli):
        return None
    if entry.get("cli_realpath") != current_realpath(cli.get("command") or ""):
        return None
    return entry


def mode_verdict(
    entry: dict[str, Any] | None,
    runtime_failure: dict[str, Any] | None,
    mode: str,
) -> tuple[str, str | None] | None:
    """Why a (lane, mode) is not verified: ``(reason, since)`` or None if verified.

    Includes non-excluding reasons (``probe_timeout``); callers that gate
    dispatch filter with ``EXCLUDING_REASONS``.
    """
    if entry is not None:
        since = entry.get("probed_at")
        l0 = entry.get("l0") or {}
        if not l0.get("ok", True):
            return l0.get("reason", "cli_not_found"), since
        tier = (entry.get("modes") or {}).get(mode)
        if tier is not None and not tier.get("ok", True):
            return tier.get("reason", "probe_failed"), since
        if (entry.get("l2") or {}).get("status") == "auth_failed":
            return "auth_failed", since
    if runtime_failure is not None:
        return _RUNTIME_REASON[runtime_failure["error_class"]], runtime_failure.get(
            "observed_at"
        )
    return None


def cache_exclusion(
    agent_id: str,
    cli: dict[str, Any],
    mode: str,
    doc: dict[str, Any] | None = None,
    now: float | None = None,
) -> tuple[str, str | None] | None:
    """Dispatch-time exclusion from the cache; never starts a subprocess."""
    doc = doc if doc is not None else read_cache()
    entry = fresh_entry(doc, agent_id, cli, now)
    verdict = mode_verdict(entry, fresh_runtime_failure(doc, agent_id, now), mode)
    if verdict is not None and verdict[0] in EXCLUDING_REASONS:
        return verdict
    return None


# --------------------------------------------------------------------- probe_lanes


def probe_lanes(
    configs: dict[str, dict[str, Any]],
    reuse_fresh: bool,
    max_age_seconds: int | None = None,
    path: Path | None = None,
) -> dict[str, LaneProbe]:
    """Probe every lane in ``configs`` (agent_id -> cli block).

    With ``reuse_fresh`` a fresh cache entry (optionally younger than
    ``max_age_seconds``) is returned without starting any subprocess.
    Cache write failures are logged and never fail the caller.
    """
    doc = read_cache(path)
    results: dict[str, LaneProbe] = {}
    todo: dict[str, dict[str, Any]] = {}
    for agent_id, cli in configs.items():
        if not cli or not cli.get("command"):
            continue
        entry = (
            fresh_entry(doc, agent_id, cli, max_age_seconds=max_age_seconds)
            if reuse_fresh
            else None
        )
        if entry is not None:
            results[agent_id] = LaneProbe(agent_id, entry, reused=True)
        else:
            todo[agent_id] = cli

    if todo:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(todo))) as pool:
            futures = {a: pool.submit(probe_lane, a, c) for a, c in todo.items()}
            fresh = [f.result() for f in futures.values()]
        store_probes(fresh, path)
        for probe in fresh:
            results[probe.agent_id] = probe

    doc = read_cache(path)
    for probe in results.values():
        if not probe.reused:
            _clear_auth_failure(doc, probe)
        probe.runtime_failure = fresh_runtime_failure(doc, probe.agent_id)
    return {a: results[a] for a in configs if a in results}


# ------------------------------------------------------------------------ report

_HINTS = {
    "cli_not_found": "install the CLI and put it on PATH",
    "probe_timeout": "CLI too slow; re-run /vendor-status",
    "probe_failed": "CLI version/help command failed; reinstall or update it",
    "missing_flags": "CLI is older than agents.yaml expects; update it",
    "auth_failed": "log in to the CLI, then run /vendor-status to refresh",
    "runtime_auth_required": "log in to the CLI, then run /vendor-status to refresh",
    "runtime_vendor_unavailable": "billing/credits problem; clears after 1 h",
}


def _tier_cell(tier: dict[str, Any]) -> str:
    return "ok" if tier.get("ok") else tier.get("reason", "fail")


def format_report(
    probes: dict[str, LaneProbe],
) -> str:
    header = f"{'Lane':<22} {'Version':<26} {'L0':<14} {'L1':<22} {'L2':<14} Hint"
    lines = [header, "-" * len(header)]
    for agent_id, probe in probes.items():
        entry = probe.entry
        modes = entry.get("modes") or {}
        bad = [m for m, t in modes.items() if not t.get("ok")]
        l1 = "ok" if not bad else ",".join(f"{m}:{_tier_cell(modes[m])}" for m in bad)
        l2 = (entry.get("l2") or {}).get("status", "-")
        if probe.runtime_failure:
            l2 += "+" + _RUNTIME_REASON[probe.runtime_failure["error_class"]]
        hint = ""
        if not entry["l0"].get("ok"):
            hint = _HINTS["cli_not_found"]
        else:
            for tier in modes.values():
                if not tier.get("ok"):
                    hint = _HINTS.get(tier.get("reason", ""), "")
                    if tier.get("missing_flags"):
                        hint += " (missing " + " ".join(tier["missing_flags"]) + ")"
                    break
            else:
                if l2.startswith("auth_failed"):
                    hint = _HINTS["auth_failed"]
                elif probe.runtime_failure:
                    hint = _HINTS[_RUNTIME_REASON[probe.runtime_failure["error_class"]]]
        lines.append(
            f"{agent_id:<22} {str(entry.get('cli_version') or '-'):<26} "
            f"{_tier_cell(entry['l0']):<14} {l1:<22} {l2:<14} {hint}"
        )
    if not probes:
        lines.append("(no CLI lanes configured)")
    return "\n".join(lines)


def _resolve_cli_configs() -> dict[str, dict[str, Any]]:
    """Resolve lanes from AGENTS_YAML, the coordinator API, or a local agents.yaml.

    The one non-stdlib step; lives only in the ``report`` entry point (design D8).
    """
    scripts = str(Path(__file__).resolve().parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        import yaml
        import review_dispatcher as rd
    except ImportError as exc:
        raise _Unavailable(
            "config resolver needs PyYAML (run skills/.venv)"
            if "yaml" in str(exc).lower()
            else f"config resolver import failed: {exc}"
        ) from exc
    orch = rd.ReviewOrchestrator

    def _from_yaml(path: Path) -> dict[str, Any] | None:
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except (OSError, yaml.YAMLError):
            return None
        agents = raw.get("agents") if isinstance(raw, dict) else None
        if not isinstance(agents, dict):
            return None
        return {
            "agents": [
                {"agent_id": aid, "cli": (cfg or {}).get("cli")} for aid, cfg in agents.items()
            ]
        }

    data: dict[str, Any] | None = None
    explicit = orch._explicit_agents_yaml_path()
    if explicit and explicit.is_file():
        data = _from_yaml(explicit)
    if data is None and os.environ.get("COORDINATION_API_URL"):
        data = orch._load_from_http()
    if data is None:
        local = orch._find_local_agents_yaml()
        if local:
            data = _from_yaml(local)
    if not data:
        raise _Unavailable("no agents configuration resolved")
    configs: dict[str, dict[str, Any]] = {}
    for agent in data.get("agents", []):
        cli = agent.get("cli")
        if isinstance(cli, dict) and cli.get("command"):
            configs[agent["agent_id"]] = cli
    return configs


class _Unavailable(Exception):
    pass


def cmd_report(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="vendor_probe.py report")
    parser.add_argument("--timeout", type=float, default=REPORT_TIMEOUT)
    args = parser.parse_args(argv)
    try:
        configs = _resolve_cli_configs()
    except _Unavailable as exc:
        print(f"probe report unavailable: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001 - report must degrade, not crash
        print(f"probe report unavailable: {exc}")
        return 2
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(probe_lanes, configs, False)
    try:
        probes = future.result(timeout=args.timeout)
    except TimeoutError:
        print("probe report unavailable: timeout", flush=True)
        # Worker threads are joined at interpreter exit; leave immediately so the
        # overall bound holds even when a lane's CLI never returns.
        os._exit(2)
    except Exception as exc:  # noqa: BLE001
        print(f"probe report unavailable: {exc}")
        pool.shutdown(wait=False, cancel_futures=True)
        return 2
    pool.shutdown(wait=False)
    print(format_report(probes))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "report":
        print("usage: vendor_probe.py report [--timeout SECONDS]", file=sys.stderr)
        return 2
    return cmd_report(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
