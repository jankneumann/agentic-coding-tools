"""vendor_health delegation to the tiered probe (task 3.1)."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

import vendor_health
import vendor_probe as vp

SCRIPTS = Path(__file__).resolve().parents[2] / "parallel-infrastructure" / "scripts"


def make_cli(tmp: Path, name="fakecli", help_text="-p --model", auth_rc=0) -> None:
    bindir = tmp / "bin"
    bindir.mkdir(exist_ok=True)
    log = tmp / f"{name}.log"
    path = bindir / name
    path.write_text(
        f"""#!/bin/sh
echo "$*" >> "{log}"
case "$*" in
  "--version") echo 'fake 9.9';;
  "--help") echo '{help_text}';;
  *) exit {auth_rc};;
esac
"""
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def calls(tmp: Path, name="fakecli") -> list[str]:
    log = tmp / f"{name}.log"
    return log.read_text().splitlines() if log.exists() else []


def lane(**cli_over):
    cli = {
        "command": "fakecli",
        "dispatch_modes": {"review": {"args": ["-p", "--secret-dispatch-flag"]}, "quick": {"args": ["-p"]}},
        "model_flag": "--model",
        "probe": {},
    }
    cli.update(cli_over)
    return {"type": "fake", "cli": cli}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    monkeypatch.setenv("AGENTIC_PROBE_CACHE", str(tmp_path / "cache.json"))


def test_preserved_and_new_fields(tmp_path):
    make_cli(tmp_path)
    h = vendor_health.check_vendor("fake-local", lane())
    assert h.cli_installed is True
    assert h.cli_version == "fake 9.9"
    # review passes --secret-dispatch-flag which help lacks -> narrowed
    assert h.dispatch_modes == ["quick"]
    assert h.missing_flags == {"review": ["--secret-dispatch-flag"]}
    assert h.auth_status == "auth_unknown"
    assert h.runtime_failure is None
    assert h.healthy is True
    d = h.__dict__
    for key in ("cli_installed", "api_key_available", "dispatch_modes", "models", "healthy", "error"):
        assert key in d


def test_no_probe_block_equals_todays_mode_list(tmp_path):
    make_cli(tmp_path, help_text="nothing")
    cfg = lane()
    del cfg["cli"]["probe"]
    assert vendor_health.check_vendor("a", cfg).dispatch_modes == ["review", "quick"]


def test_expired_login_makes_lane_unhealthy(tmp_path):
    make_cli(tmp_path, help_text="-p --model --secret-dispatch-flag", auth_rc=1)
    cfg = lane(probe={"auth_status_args": ["auth", "status"]})
    h = vendor_health.check_vendor("a", cfg)
    assert h.auth_status == "auth_failed"
    assert h.healthy is False
    assert h.error == "auth_failed"


def test_remembered_billing_failure_unhealthy(tmp_path):
    make_cli(tmp_path, help_text="-p --model --secret-dispatch-flag")
    vp.record_runtime_failure("a", "vendor_unavailable")
    h = vendor_health.check_vendor("a", lane())
    assert h.runtime_failure == "runtime_vendor_unavailable"
    assert h.healthy is False
    assert h.error == "runtime_vendor_unavailable"


def test_remembered_auth_required_sets_error(tmp_path):
    make_cli(tmp_path, help_text="-p --model --secret-dispatch-flag")
    vp.record_runtime_failure("a", "auth_required")
    h = vendor_health.check_vendor("a", lane())
    assert h.error == "runtime_auth_required"


def test_healthy_lane_has_no_error_and_no_probe_method_wins(tmp_path):
    make_cli(tmp_path, help_text="-p --model --secret-dispatch-flag")
    assert vendor_health.check_vendor("a", lane()).error is None
    assert vendor_health.check_vendor("sdk", {"type": "x"}).error == "no_probe_method"


def test_entry_without_l0_does_not_raise(tmp_path):
    probe = vp.LaneProbe("a", {"modes": {}, "l2": {"status": "auth_unknown", "method": "none"}})
    h = vendor_health.check_vendor("a", lane(), probe)
    assert h.cli_installed is False


def test_health_and_check_vendors_agree_on_missing_flag(tmp_path):
    make_cli(tmp_path)
    cfg = lane()
    h = vendor_health.check_vendor("a", cfg)
    assert "review" not in h.dispatch_modes
    entry = vp.read_cache()["lanes"]["a"]
    assert vp.mode_verdict(entry, None, "review")[0] == "missing_flags"
    assert vp.mode_verdict(entry, None, "quick") is None


def test_health_probes_are_token_free(tmp_path):
    make_cli(tmp_path)
    vendor_health.check_vendor("a", lane(probe={"auth_status_args": ["auth", "status"]}))
    for line in calls(tmp_path):
        assert "--secret-dispatch-flag" not in line


def test_cli_reprobes_but_check_all_reuses_fresh(tmp_path, monkeypatch):
    make_cli(tmp_path, help_text="-p --model --secret-dispatch-flag")
    agents = {"agents": {"a": lane()}}
    monkeypatch.setattr(vendor_health, "load_agents_yaml", lambda _p=None: agents)
    vendor_health.check_all_vendors(reuse_fresh=False)
    n1 = len(calls(tmp_path))
    assert n1 > 0
    first = vendor_health.check_all_vendors()  # watchdog default
    assert len(calls(tmp_path)) == n1
    second = vendor_health.check_all_vendors()
    assert len(calls(tmp_path)) == n1
    assert [v.healthy for v in first.vendors] == [v.healthy for v in second.vendors]
    # entries older than max_age are re-probed
    monkeypatch.setattr(time, "time", lambda: time.monotonic() * 0 + 4e9)
    vendor_health.check_all_vendors()
    assert len(calls(tmp_path)) > n1


def test_cli_main_reprobes_against_fresh_cache(tmp_path):
    make_cli(tmp_path)
    agents = tmp_path / "agents.yaml"
    agents.write_text(
        "agents:\n  a:\n    type: fake\n    cli:\n      command: fakecli\n"
        "      dispatch_modes:\n        quick: {args: ['-p']}\n      model_flag: --model\n"
    )
    env = {**os.environ}
    for _ in range(2):
        before = len(calls(tmp_path))
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "vendor_health.py"), "--agents-yaml", str(agents), "--json"],
            env=env, capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert len(calls(tmp_path)) > before
        assert "fake 9.9" in proc.stdout


def test_watchdog_style_by_path_load_without_yaml(tmp_path):
    """Load vendor_health by path (as watchdog.py does) with yaml unimportable."""
    make_cli(tmp_path)
    code = f"""
import importlib.util, sys
sys.modules['yaml'] = None  # make `import yaml` fail
spec = importlib.util.spec_from_file_location('_coordinator_vendor_health', {str(SCRIPTS / 'vendor_health.py')!r})
mod = importlib.util.module_from_spec(spec)
sys.modules['_coordinator_vendor_health'] = mod
spec.loader.exec_module(mod)
mod.load_agents_yaml = lambda p=None: {{'agents': {{'a': {{'type': 'fake', 'cli': {{'command': 'fakecli', 'dispatch_modes': {{'quick': {{'args': ['-p']}}}}, 'model_flag': '--model', 'probe': {{}}}}}}}}}}
report = mod.check_all_vendors()
assert 'vendor_probe' in sys.modules
print(report.vendors[0].cli_version)
"""
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
        cwd=tmp_path, env={**os.environ, "PYTHONPATH": ""},
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "fake 9.9"
