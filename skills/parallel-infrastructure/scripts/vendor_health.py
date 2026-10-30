"""Vendor health check: verify all configured vendors' readiness.

Design Decisions:
  D5: Dual-use — standalone CLI script + importable module for WatchdogService.
  D6: No inference probes — uses can_dispatch() + API key resolution only.
  D7: Watchdog events on coordinator_agent channel.
  add-local-agent-probe D1: CLI presence/capability/auth come from the shared
      tiered probe (vendor_probe.py), loaded by sibling file path so the
      coordinator container's by-path load of this module keeps working.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_PROBE_MODULE = "vendor_probe"
WATCHDOG_MAX_AGE_SECONDS = 3600


def _load_vendor_probe() -> Any:
    """Load vendor_probe.py by sibling path (stdlib-only, no sys.path reliance).

    Registered in ``sys.modules`` before ``exec_module`` so ``@dataclass``
    resolves postponed annotations (#643) and every loader in the process shares
    one module instance (and one cache lock).
    """
    existing = sys.modules.get(_PROBE_MODULE)
    if existing is not None:
        return existing
    path = Path(__file__).with_name("vendor_probe.py")
    spec = importlib.util.spec_from_file_location(_PROBE_MODULE, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PROBE_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_PROBE_MODULE, None)
        raise
    return module


@dataclass
class VendorHealth:
    """Health status for a single vendor agent."""

    agent_id: str
    vendor_type: str
    cli_command: str
    cli_installed: bool = False
    api_key_available: bool = False
    dispatch_modes: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    healthy: bool = False
    error: str | None = None
    cli_version: str | None = None
    missing_flags: dict[str, list[str]] = field(default_factory=dict)
    auth_status: str = "auth_unknown"
    runtime_failure: str | None = None


@dataclass
class HealthReport:
    """Aggregate health report for all vendors."""

    vendors: list[VendorHealth] = field(default_factory=list)
    healthy_count: int = 0
    total_count: int = 0

    def to_dict(self) -> dict:
        return {
            "vendors": [asdict(v) for v in self.vendors],
            "healthy_count": self.healthy_count,
            "total_count": self.total_count,
        }


def check_vendor(
    agent_id: str, agent_config: dict, lane_probe: Any | None = None
) -> VendorHealth:
    """Check health of a single vendor from its agents.yaml config.

    ``lane_probe`` is a ``vendor_probe.LaneProbe``; when omitted the lane is
    probed live (and cached).
    """
    # `or`, not a .get default: dispatch-configs sends "cli": null for SDK-only lanes (#643).
    cli = agent_config.get("cli") or {}
    command = cli.get("command", "")
    vendor_type = agent_config.get("type", "unknown")

    health = VendorHealth(
        agent_id=agent_id,
        vendor_type=vendor_type,
        cli_command=command,
    )

    # Checks 1-2: CLI presence, per-mode capability and auth (tiered probe).
    if command:
        if lane_probe is None:
            probe_mod = _load_vendor_probe()
            lane_probe = probe_mod.probe_lanes({agent_id: cli}, reuse_fresh=False)[agent_id]
        entry = lane_probe.entry
        health.cli_installed = bool(entry["l0"].get("ok"))
        health.cli_version = entry.get("cli_version")
        health.auth_status = (entry.get("l2") or {}).get("status", "auth_unknown")
        for mode_name, tier in (entry.get("modes") or {}).items():
            if tier.get("ok"):
                health.dispatch_modes.append(mode_name)
            elif tier.get("missing_flags"):
                health.missing_flags[mode_name] = list(tier["missing_flags"])
        failure = lane_probe.runtime_failure
        if failure:
            health.runtime_failure = (
                "runtime_auth_required"
                if failure["error_class"] == "auth_required"
                else "runtime_vendor_unavailable"
            )

    # Check 3: Models configured
    model = cli.get("model")
    if model:
        health.models.append(model)
    health.models.extend(cli.get("model_fallbacks", []))

    # Check 4: API key availability (CLI-declared env var, SDK section, or
    # direct api_key). cli.api_key_env is a credential the CLI itself needs
    # to serve a request (pi: OPENROUTER_API_KEY, issue #383).
    sdk = agent_config.get("sdk") or {}
    cli_api_key_env = cli.get("api_key_env")
    api_key_env = cli_api_key_env or sdk.get("api_key_env")
    if api_key_env:
        health.api_key_available = bool(os.environ.get(api_key_env))
    else:
        # Check if api_key is configured directly
        api_key = agent_config.get("api_key")
        if api_key and not api_key.startswith("${"):
            health.api_key_available = True
        elif api_key and api_key.startswith("${"):
            # Environment variable reference
            env_var = api_key.strip("${}")
            health.api_key_available = bool(os.environ.get(env_var))

    # Determine overall health. When the CLI declares a required credential,
    # a present binary without it cannot serve requests — fail closed. D6
    # still holds: this is env-var resolution, not an inference probe.
    if cli_api_key_env:
        health.healthy = health.cli_installed and health.api_key_available
    else:
        health.healthy = health.cli_installed or health.api_key_available
    # Same predicate as --check-vendors and discover_reviewers: an expired
    # login or a remembered runtime failure is not healthy.
    if health.auth_status == "auth_failed" or health.runtime_failure:
        health.healthy = False

    has_probe_method = bool(command or api_key_env or agent_config.get("api_key"))
    if not has_probe_method:
        health.error = "no_probe_method"

    return health


def load_agents_yaml(path: Path | None = None) -> dict:
    """Load explicit config, then public HTTP config, then a local fallback."""
    explicit = path or (
        Path(os.environ["AGENTS_YAML"]).expanduser()
        if os.environ.get("AGENTS_YAML")
        else None
    )
    if explicit and explicit.exists():
        import yaml  # lazy: the HTTP path must work without PyYAML

        with open(explicit) as f:
            return yaml.safe_load(f) or {}

    base_url = os.environ.get("COORDINATION_API_URL")
    if base_url:
        request = Request(
            f"{base_url.rstrip('/')}/agents/dispatch-configs",
            headers={"User-Agent": "agentic-coding-tools/0.1"},
        )
        try:
            with urlopen(request, timeout=3.0) as response:
                payload = json.loads(response.read())
            if isinstance(payload, dict):
                agents = payload.get("agents", [])
                if isinstance(agents, list):
                    return {
                        "agents": {
                            item["agent_id"]: item
                            for item in agents
                            if isinstance(item, dict) and item.get("agent_id")
                        }
                    }
                return payload
        except (URLError, OSError, ValueError, json.JSONDecodeError):
            pass

    # Optional source-repository compatibility fallback.
    candidates = [
        Path.cwd() / "agent-coordinator" / "agents.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            import yaml

            with open(candidate) as f:
                return yaml.safe_load(f) or {}

    return {}


def check_all_vendors(
    agents_yaml_path: Path | None = None,
    *,
    reuse_fresh: bool = True,
    max_age_seconds: int | None = WATCHDOG_MAX_AGE_SECONDS,
) -> HealthReport:
    """Check health of all vendors configured in agents.yaml.

    The default (watchdog) reuses probe-cache entries younger than
    ``max_age_seconds`` without starting subprocesses; the CLI passes
    ``reuse_fresh=False`` to re-probe.
    """
    config = load_agents_yaml(agents_yaml_path)
    agents = config.get("agents", {})

    clis = {
        agent_id: (agent_config or {}).get("cli")
        for agent_id, agent_config in agents.items()
        if ((agent_config or {}).get("cli") or {}).get("command")
    }
    lane_probes = (
        _load_vendor_probe().probe_lanes(
            clis, reuse_fresh=reuse_fresh, max_age_seconds=max_age_seconds
        )
        if clis
        else {}
    )

    report = HealthReport()
    for agent_id, agent_config in agents.items():
        health = check_vendor(agent_id, agent_config, lane_probes.get(agent_id))
        report.vendors.append(health)

    report.total_count = len(report.vendors)
    report.healthy_count = sum(1 for v in report.vendors if v.healthy)
    return report


def format_table(report: HealthReport) -> str:
    """Format health report as a human-readable table."""
    lines = []
    header = f"{'Vendor':<18} {'CLI':<6} {'API Key':<9} {'Modes':<30} {'Models'}"
    lines.append(header)
    lines.append("-" * len(header))

    for v in report.vendors:
        cli_mark = "ok" if v.cli_installed else "-"
        key_mark = "ok" if v.api_key_available else "-"
        modes = ", ".join(v.dispatch_modes) if v.dispatch_modes else "-"
        models = ", ".join(v.models) if v.models else "-"
        lines.append(f"{v.agent_id:<18} {cli_mark:<6} {key_mark:<9} {modes:<30} {models}")

    lines.append("")
    lines.append(f"Healthy: {report.healthy_count}/{report.total_count}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check vendor health status.")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--agents-yaml", type=Path, default=None, help="Path to agents.yaml")
    args = parser.parse_args(argv)

    report = check_all_vendors(args.agents_yaml, reuse_fresh=False)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_table(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
