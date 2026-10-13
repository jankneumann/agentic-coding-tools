"""Dispatchable vendor verification (dispatch-contract PI requirement, D10).

``--check-vendors`` counts a lane only after its dry invocation succeeds; with
``--json`` it reports verified and unverified lanes per mode, the sanctioned
probe command, and the per-environment quorum policy resolved from data.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import review_dispatcher as rd


class _Reviewer:
    def __init__(self, vendor: str, command: str, tier: str = "cli") -> None:
        self.vendor = vendor
        self.dispatch_tier = tier
        self.cli_config = SimpleNamespace(command=command) if tier == "cli" else None


class _Orch:
    """Roster: ``lanes`` maps vendor -> CLI command; ``dispatchable`` is the
    subset discover_reviewers returns (the existing PATH/mode check)."""

    def __init__(self, lanes: dict[str, str], dispatchable: set[str], sdk: set[str] = frozenset()) -> None:
        self.lanes = lanes
        self.dispatchable = dispatchable
        self.adapters = {
            v: SimpleNamespace(vendor=v, cli_config=SimpleNamespace(command=c)) for v, c in lanes.items()
        }
        self.sdk_adapters = {v: SimpleNamespace(vendor=v) for v in sdk}

    def discover_reviewers(self, exclude_vendor=None, dispatch_mode="review"):
        found = [
            _Reviewer(v, self.lanes[v]) for v in sorted(self.dispatchable) if v != exclude_vendor
        ]
        found += [_Reviewer(v, "", tier="sdk") for v in sorted(self.sdk_adapters)]
        return found


@pytest.fixture()
def roster(monkeypatch: pytest.MonkeyPatch):
    def install(orch: Any) -> None:
        monkeypatch.setattr(rd, "_orchestrator_for_dispatch", lambda *_a, **_k: orch)
        monkeypatch.setattr(rd, "_execution_environment", lambda: "host")

    return install


def _json(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out.strip().splitlines()
    return json.loads(out[-1])


def test_a_listed_vendor_without_its_cli_is_unverified(roster, capsys) -> None:
    roster(_Orch({"claude_code": sys.executable, "codex": "codex-not-installed-0d1e"}, {"claude_code"}))

    rc = rd._check_vendors(min_vendors=2, as_json=True)

    report = _json(capsys)
    assert rc == rd.CHECK_VENDORS_BELOW_QUORUM
    assert report["modes"]["review"]["verified"] == ["claude_code"]
    assert {"vendor": "codex", "reason": "cli_not_found"} in report["modes"]["review"]["unverified"]
    assert report["probe_command"].endswith("--check-vendors --json")


def test_a_cli_lane_whose_dry_invocation_fails_does_not_count(roster, capsys, tmp_path: Path) -> None:
    failing = tmp_path / "broken-cli"
    failing.write_text("#!/bin/sh\nexit 3\n")
    failing.chmod(0o755)
    roster(_Orch({"claude_code": sys.executable, "codex": str(failing)}, {"claude_code", "codex"}))

    assert rd._check_vendors(min_vendors=2, as_json=True) == rd.CHECK_VENDORS_BELOW_QUORUM
    assert {"vendor": "codex", "reason": "probe_failed"} in _json(capsys)["modes"]["review"]["unverified"]


def test_two_verified_lanes_meet_quorum(roster, capsys) -> None:
    roster(_Orch({"claude_code": sys.executable, "codex": sys.executable}, {"claude_code", "codex"}))
    assert rd._check_vendors(min_vendors=2, as_json=True) == 0
    assert _json(capsys)["modes"]["review"]["verified"] == ["claude_code", "codex"]


def test_sdk_lanes_without_an_authenticated_noop_are_unverified(roster, capsys) -> None:
    roster(_Orch({"claude_code": sys.executable}, {"claude_code"}, sdk={"gemini"}))
    rd._check_vendors(min_vendors=2, as_json=True)
    assert {"vendor": "gemini", "reason": "probe_unsupported"} in _json(capsys)["modes"]["review"]["unverified"]


def test_a_hanging_dry_invocation_is_unverified() -> None:
    reason = rd._dry_invoke([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.5)
    assert reason == "probe_timeout"
    assert rd.DRY_PROBE_TIMEOUT_SECONDS == 10


def test_roster_failure_prints_an_error_document(monkeypatch, capsys) -> None:
    def broken(*_a, **_k):
        raise RuntimeError("agents.yaml unreadable")

    monkeypatch.setattr(rd, "_orchestrator_for_dispatch", broken)

    assert rd._check_vendors(as_json=True) == rd.CHECK_VENDORS_BELOW_QUORUM
    report = _json(capsys)
    assert report["modes"] == {}
    assert "error" in report


def test_the_probe_never_discloses_credentials(roster, capsys, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-SENTINEL-1234567890")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-SENTINEL-0987654321")
    spawned: list[list[str]] = []
    real_run = subprocess.run

    def recording_run(argv, *args, **kwargs):
        spawned.append(list(argv))
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(rd.subprocess, "run", recording_run)
    roster(_Orch({"claude_code": sys.executable, "codex": sys.executable}, {"claude_code", "codex"}))

    rd._check_vendors(min_vendors=2, as_json=True)

    captured = capsys.readouterr()
    for sentinel in ("sk-test-SENTINEL-1234567890", "sk-test-SENTINEL-0987654321"):
        assert sentinel not in captured.out
        assert sentinel not in captured.err
    assert spawned, "the dry invocations ran"
    assert all(Path(argv[0]).name not in {"env", "printenv"} for argv in spawned)
    assert all(argv[1:] == ["--version"] for argv in spawned)


# --------------------------------------------------------------------------- #
# Per-environment quorum policy, as data
# --------------------------------------------------------------------------- #


def test_cloud_container_with_one_lane_resolves_quorum_one_with_its_sunset() -> None:
    resolved = rd.resolve_quorum_policy(environment="cloud_container", verified_review_lanes=1)
    assert resolved["min_quorum"] == {"PLAN_REVIEW": 1, "IMPL_REVIEW": 1, "VAL_REVIEW": 1}
    assert resolved["policy_id"]
    assert "GX10" in resolved["sunset"]


def test_a_host_or_a_multi_lane_container_keeps_quorum_two() -> None:
    for environment, lanes in (("host", 1), ("cloud_container", 2)):
        resolved = rd.resolve_quorum_policy(environment=environment, verified_review_lanes=lanes)
        assert resolved["min_quorum"] == {"PLAN_REVIEW": 2, "IMPL_REVIEW": 2, "VAL_REVIEW": 2}
        assert resolved["policy_id"] is None


def test_an_inactive_policy_restores_quorum_two(tmp_path: Path) -> None:
    policy = json.loads(rd._QUORUM_POLICY_PATH.read_text())
    for entry in policy["policies"]:
        entry["active"] = False
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy))
    resolved = rd.resolve_quorum_policy(
        environment="cloud_container", verified_review_lanes=1, policy_path=path
    )
    assert resolved["min_quorum"]["PLAN_REVIEW"] == 2


def test_the_json_report_carries_the_resolved_policy(roster, capsys, monkeypatch) -> None:
    roster(_Orch({"claude_code": sys.executable}, {"claude_code"}))
    monkeypatch.setattr(rd, "_execution_environment", lambda: "cloud_container")
    rd._check_vendors(min_vendors=2, as_json=True)
    assert _json(capsys)["quorum_policy"]["min_quorum"]["PLAN_REVIEW"] == 1
