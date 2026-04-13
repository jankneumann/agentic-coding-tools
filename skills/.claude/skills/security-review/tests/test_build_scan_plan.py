from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from build_scan_plan import build_plan  # noqa: E402


def _profile(*profiles: str) -> dict[str, object]:
    return {
        "primary_profile": profiles[0] if profiles else "generic",
        "profiles": list(profiles),
        "confidence": "high",
        "signals": [],
    }


def test_zap_enabled_for_dast_profile_without_target() -> None:
    plan = build_plan(
        profile=_profile("docker-api"),
        fail_on="high",
        zap_target=None,
        zap_mode="baseline",
    )
    zap = next(item for item in plan["scanners"] if item["scanner"] == "zap")
    assert zap["enabled"] is True
    assert "no --zap-target provided" in str(zap["reason"]).lower()


def test_zap_disabled_for_non_dast_profile() -> None:
    plan = build_plan(
        profile=_profile("python"),
        fail_on="high",
        zap_target=None,
        zap_mode="baseline",
    )
    zap = next(item for item in plan["scanners"] if item["scanner"] == "zap")
    assert zap["enabled"] is False


def test_dependency_check_enabled_for_ecosystem_profile() -> None:
    plan = build_plan(
        profile=_profile("node"),
        fail_on="high",
        zap_target=None,
        zap_mode="baseline",
    )
    dep = next(item for item in plan["scanners"] if item["scanner"] == "dependency-check")
    assert dep["enabled"] is True
