"""Deploy assets are inert templates (tasks 5.6/5.7)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from agent_scenarios.nightly import NightlyConfig

PKG = Path(__file__).resolve().parents[1]
DEPLOY = PKG / "deploy"
SERVICE = DEPLOY / "systemd" / "agent-scenarios-nightly.service.template"
TIMER = DEPLOY / "systemd" / "agent-scenarios-nightly.timer.template"
EXAMPLE = DEPLOY / "nightly.example.yaml"


def test_templates_contain_unresolved_placeholders() -> None:
    service = SERVICE.read_text()
    assert "@UV@" in service and "@REPO@" in service
    assert "Type=oneshot" in service and "Nice=10" in service and "SuccessExitStatus=0\n" in service
    timer = TIMER.read_text()
    assert "OnCalendar=*-*-* 02:30" in timer and "Persistent=false" in timer
    assert "RandomizedDelaySec=15m" in timer


def test_example_config_parses_disabled() -> None:
    raw = yaml.safe_load(EXAMPLE.read_text())
    assert raw["enabled"] is False
    cfg = NightlyConfig.model_validate(raw)
    assert cfg.enabled is False and cfg.caps.max_pairs == 30


def test_timeout_covers_wall_clock_cap_plus_one_pair_timeout() -> None:
    cfg = NightlyConfig.model_validate(yaml.safe_load(EXAMPLE.read_text()))
    match = re.search(r"^TimeoutStartSec=(\d+)min$", SERVICE.read_text(), re.M)
    assert match, "TimeoutStartSec must be expressed in minutes"
    needed = cfg.caps.max_wall_clock_minutes + cfg.caps.per_pair_timeout_seconds / 60 + 10
    assert int(match.group(1)) >= needed


def test_no_systemctl_invocation_in_package_code_or_tests() -> None:
    offenders: list[str] = []
    needle = "systemctl"
    for base in (PKG / "src", PKG / "tests"):
        for path in base.rglob("*.py"):
            if path == Path(__file__):
                continue
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                if needle in line and not line.lstrip().startswith(("#", '"""', "*")):
                    offenders.append(f"{path.relative_to(PKG)}:{lineno}")
    assert offenders == []
