"""Vendor health check: verify all configured vendors' readiness.

Design Decisions:
  D5: Dual-use — standalone CLI script + importable module for WatchdogService.
  D6: No inference probes — uses can_dispatch() + API key resolution only.
  D7: Watchdog events on coordinator_agent channel.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


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


def check_vendor(agent_id: str, agent_config: dict) -> VendorHealth:
    """Check health of a single vendor from its agents.yaml config."""
    cli = agent_config.get("cli", {})
    command = cli.get("command", "")
    vendor_type = agent_config.get("type", "unknown")

    health = VendorHealth(
        agent_id=agent_id,
        vendor_type=vendor_type,
        cli_command=command,
    )

    # Check 1: CLI installed
    if command:
        health.cli_installed = shutil.which(command) is not None

    # Check 2: Available dispatch modes
    dispatch_modes = cli.get("dispatch_modes", {})
    for mode_name, mode_config in dispatch_modes.items():
        if health.cli_installed:
            health.dispatch_modes.append(mode_name)

    # Check 3: Models configured
    model = cli.get("model")
    if model:
        health.models.append(model)
    health.models.extend(cli.get("model_fallbacks", []))

    # Check 4: API key availability (check SDK section or env var)
    sdk = agent_config.get("sdk", {})
    api_key_env = sdk.get("api_key_env")
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

    # Determine overall health: CLI installed OR API key available
    health.healthy = health.cli_installed or health.api_key_available

    return health


def load_agents_yaml(path: Path | None = None) -> dict:
    """Load agents.yaml from explicit path or discovery."""
    import yaml

    if path and path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}

    # Try default locations
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "agent-coordinator" / "agents.yaml",
        Path.cwd() / "agent-coordinator" / "agents.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            with open(candidate) as f:
                return yaml.safe_load(f) or {}

    return {}


def check_all_vendors(agents_yaml_path: Path | None = None) -> HealthReport:
    """Check health of all vendors configured in agents.yaml."""
    config = load_agents_yaml(agents_yaml_path)
    agents = config.get("agents", {})

    report = HealthReport()
    for agent_id, agent_config in agents.items():
        # Only check agents with CLI sections
        if "cli" not in agent_config:
            continue
        health = check_vendor(agent_id, agent_config)
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

    report = check_all_vendors(args.agents_yaml)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_table(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
