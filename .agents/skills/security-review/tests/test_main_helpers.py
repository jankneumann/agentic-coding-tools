from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from main import _bootstrap_components_from_missing, _required_prereqs_from_plan  # noqa: E402


def test_required_prereqs_from_plan() -> None:
    plan = {
        "scanners": [
            {"scanner": "dependency-check", "enabled": True},
            {"scanner": "zap", "enabled": True},
            {"scanner": "other", "enabled": True},
            {"scanner": "zap", "enabled": False},
        ]
    }
    assert _required_prereqs_from_plan(plan) == ["dependency-check", "zap"]


def test_bootstrap_components_from_missing() -> None:
    missing = ["zap", "dependency-check", "unknown", "docker", "container"]
    assert _bootstrap_components_from_missing(missing) == ["dependency-check", "podman"]
