"""Cache-filtered discovery, tiered --check-vendors and runtime write-back (task 3.3)."""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

import pytest

import checkpoint_findings as cf
import review_dispatcher as rd
import vendor_probe as vp

HELP = "-p --model --json-schema"


def make_cli(tmp: Path, name: str, *, version_rc=0, help_text=HELP, auth_rc=0,
             run_stderr: str = "", run_rc: int = 0, run_stdout: str = "") -> None:
    bindir = tmp / "bin"
    bindir.mkdir(exist_ok=True)
    log = tmp / f"{name}.log"
    path = bindir / name
    path.write_text(
        f"""#!/bin/sh
echo "$*" >> "{log}"
case "$*" in
  "--version") echo '{name} 1.0'; exit {version_rc};;
  "--help") echo '{help_text}';;
  "auth status") exit {auth_rc};;
  *) printf '%s' '{run_stdout}'; printf '%s' '{run_stderr}' >&2; exit {run_rc};;
esac
"""
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def agent(agent_id: str, vendor: str, command: str, **probe):
    return {
        "agent_id": agent_id,
        "type": vendor,
        "transport": "mcp",
        "cli": {
            "command": command,
            "dispatch_modes": {"review": {"args": ["-p"]}},
            "model_flag": "--model",
            "probe": probe,
        },
    }


def orch_for(*agents) -> rd.ReviewOrchestrator:
    return rd.ReviewOrchestrator.from_config_dict({"agents": list(agents)})


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    monkeypatch.setenv("AGENTIC_PROBE_CACHE", str(tmp_path / "cache.json"))
    monkeypatch.delenv("AGENTIC_PROBE_IGNORE_CACHE", raising=False)


def reviewers(orch):
    return {r.agent_id for r in orch.discover_reviewers()}


# ------------------------------------------------------------------ mirror


def test_mirror_cliconfig_keeps_probe_block_including_empty():
    orch = orch_for(
        agent("a-local", "va", "tool-a", auth_status_args=["auth", "status"]),
        agent("b-local", "vb", "tool-b"),
    )
    assert orch.adapters["a-local"].cli_config.probe == {"auth_status_args": ["auth", "status"]}
    assert orch.adapters["b-local"].cli_config.probe == {}


# --------------------------------------------------------------- discovery


def test_missing_cache_never_narrows(tmp_path):
    make_cli(tmp_path, "tool-a")
    orch = orch_for(agent("a-local", "va", "tool-a"))
    assert reviewers(orch) == {"a-local"}


def test_discover_starts_no_subprocess(tmp_path):
    make_cli(tmp_path, "tool-a")
    orch = orch_for(agent("a-local", "va", "tool-a"))
    reviewers(orch)
    assert not (tmp_path / "tool-a.log").exists()


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"version_rc": 1}, "probe_failed"),
        ({"help_text": "-p --model"}, "missing_flags"),
    ],
)
def test_known_broken_cli_not_dispatched(tmp_path, kwargs, reason):
    make_cli(tmp_path, "tool-a", **{"help_text": HELP, **kwargs})
    orch = orch_for(agent("a-local", "va", "tool-a"))
    # review mode needs only -p/--model; force a json-schema requirement
    orch.adapters["a-local"].cli_config.dispatch_modes["review"].args = ["-p", "--json-schema"]
    vp.probe_lanes({"a-local": rd._cli_probe_view(orch.adapters["a-local"].cli_config)}, reuse_fresh=False)
    if reason == "missing_flags":
        make_cli(tmp_path, "tool-a", help_text="-p --model")
        vp.probe_lanes({"a-local": rd._cli_probe_view(orch.adapters["a-local"].cli_config)}, reuse_fresh=False)
    assert reviewers(orch) == set()
    assert orch.last_exclusions[0]["reason"] == reason
    assert orch.last_exclusions[0]["vendor"] == "a-local"
    assert orch.last_exclusions[0]["mode"] == "review"


def test_auth_failed_excludes_and_status_pass_restores(tmp_path):
    make_cli(tmp_path, "tool-a", auth_rc=1)
    orch = orch_for(agent("a-local", "va", "tool-a", auth_status_args=["auth", "status"]))
    view = rd._cli_probe_view(orch.adapters["a-local"].cli_config)
    vp.probe_lanes({"a-local": view}, reuse_fresh=False)
    assert reviewers(orch) == set()
    assert orch.last_exclusions[0]["reason"] == "auth_failed"
    make_cli(tmp_path, "tool-a", auth_rc=0)
    vp.probe_lanes({"a-local": view}, reuse_fresh=False)
    assert reviewers(orch) == {"a-local"}


def test_probe_timeout_never_excludes(tmp_path):
    make_cli(tmp_path, "tool-a")
    orch = orch_for(agent("a-local", "va", "tool-a"))
    view = rd._cli_probe_view(orch.adapters["a-local"].cli_config)
    probe = vp.probe_lane("a-local", view)
    probe.entry["modes"]["review"] = {"ok": False, "reason": "probe_timeout"}
    vp.store_probes([probe])
    assert reviewers(orch) == {"a-local"}


def test_stale_entry_does_not_exclude_and_ignore_switch(tmp_path, monkeypatch):
    make_cli(tmp_path, "tool-a", auth_rc=1)
    orch = orch_for(agent("a-local", "va", "tool-a", auth_status_args=["auth", "status"]))
    vp.probe_lanes({"a-local": rd._cli_probe_view(orch.adapters["a-local"].cli_config)}, reuse_fresh=False)
    assert reviewers(orch) == set()
    monkeypatch.setenv("AGENTIC_PROBE_IGNORE_CACHE", "1")
    assert reviewers(orch) == {"a-local"}
    assert orch.last_exclusions == []
    monkeypatch.delenv("AGENTIC_PROBE_IGNORE_CACHE")
    # config edit -> fingerprint mismatch -> stale
    orch.adapters["a-local"].cli_config.dispatch_modes["review"].args = ["-p", "-x"]
    assert reviewers(orch) == {"a-local"}


def test_runtime_failure_excludes_then_expires(tmp_path, monkeypatch):
    make_cli(tmp_path, "tool-a")
    orch = orch_for(agent("a-local", "va", "tool-a"))
    vp.record_runtime_failure("a-local", "auth_required")
    assert reviewers(orch) == set()
    assert orch.last_exclusions[0]["reason"] == "runtime_auth_required"
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 3601)
    assert reviewers(orch) == {"a-local"}


def test_manifest_records_excluded_lanes(tmp_path):
    make_cli(tmp_path, "tool-a")
    orch = orch_for(agent("a-local", "va", "tool-a"))
    vp.record_runtime_failure("a-local", "auth_required")
    orch.discover_reviewers()
    out = tmp_path / "reviews" / "review-manifest.json"
    orch.write_manifest([], out, "plan", "cli-dispatch", vendors=[])
    manifest = json.loads(out.read_text())
    assert manifest["excluded_lanes"][0]["vendor"] == "a-local"
    assert manifest["excluded_lanes"][0]["reason"] == "runtime_auth_required"
    assert manifest["excluded_lanes"][0]["since"]
    # empty exclusions leave the manifest unchanged
    orch.last_exclusions = []
    orch.write_manifest([], out, "plan", "cli-dispatch", vendors=[])
    assert "excluded_lanes" not in json.loads(out.read_text())
    assert cf.read_manifest(out.parent)["schema_version"]


# -------------------------------------------------------------- check-vendors


def _check(orch, monkeypatch, mode="review"):
    monkeypatch.setattr(rd, "_orchestrator_for_dispatch", lambda *_a, **_k: orch)
    monkeypatch.setattr(rd, "_execution_environment", lambda: "host")
    return rd.check_vendors_report()["modes"][mode]


def test_check_vendors_tier_verdicts(tmp_path, monkeypatch):
    make_cli(tmp_path, "tool-ok")
    make_cli(tmp_path, "tool-flag", help_text="-p")  # lacks --model
    make_cli(tmp_path, "tool-auth", auth_rc=1)
    make_cli(tmp_path, "tool-billing")
    orch = orch_for(
        agent("ok-local", "v1", "tool-ok"),
        agent("flag-local", "v2", "tool-flag"),
        agent("auth-local", "v3", "tool-auth", auth_status_args=["auth", "status"]),
        agent("bill-local", "v4", "tool-billing"),
        agent("gone-local", "v5", "tool-not-installed"),
    )
    vp.record_runtime_failure("bill-local", "vendor_unavailable")
    report = _check(orch, monkeypatch)
    assert report["verified"] == ["v1"]
    unverified = {u["vendor"]: u["reason"] for u in report["unverified"]}
    assert unverified == {
        "v2": "missing_flags",
        "v3": "auth_failed",
        "v4": "runtime_vendor_unavailable",
        "v5": "cli_not_found",
    }
    # exit-code/JSON shape preserved
    full = rd.check_vendors_report()
    assert "probe_command" in full and "modes" in full


def test_check_vendors_reprobes_even_with_fresh_cache(tmp_path, monkeypatch):
    make_cli(tmp_path, "tool-a")
    orch = orch_for(agent("a-local", "va", "tool-a"))
    _check(orch, monkeypatch)
    n1 = len((tmp_path / "tool-a.log").read_text().splitlines())
    _check(orch, monkeypatch)
    assert len((tmp_path / "tool-a.log").read_text().splitlines()) > n1


def test_check_vendors_writes_cache_used_by_dispatch(tmp_path, monkeypatch):
    make_cli(tmp_path, "tool-a", auth_rc=1)
    orch = orch_for(agent("a-local", "va", "tool-a", auth_status_args=["auth", "status"]))
    _check(orch, monkeypatch)
    assert reviewers(orch) == set()


def test_check_vendors_clears_auth_failure_with_status_command(tmp_path, monkeypatch):
    make_cli(tmp_path, "tool-a")
    orch = orch_for(agent("a-local", "va", "tool-a", auth_status_args=["auth", "status"]))
    vp.record_runtime_failure("a-local", "auth_required")
    time.sleep(1.1)
    report = _check(orch, monkeypatch)
    assert report["verified"] == ["va"]
    assert reviewers(orch) == {"a-local"}


# ------------------------------------------------------- runtime write-back


def dispatch(orch, agent_id, tmp_path):
    adapter = orch.adapters[agent_id]
    return adapter.dispatch("review", "review this", tmp_path, timeout_seconds=20)


def test_nonzero_exit_auth_error_is_remembered(tmp_path):
    make_cli(tmp_path, "tool-a", run_rc=1, run_stderr="401 unauthorized: login required")
    orch = orch_for(agent("a-local", "va", "tool-a"))
    result = dispatch(orch, "a-local", tmp_path)
    assert result.error_class == rd.ErrorClass.AUTH
    assert vp.read_cache()["runtime_failures"]["a-local"]["error_class"] == "auth_required"
    assert reviewers(orch) == set()


def test_billing_error_remembered_as_vendor_unavailable(tmp_path):
    make_cli(tmp_path, "tool-a", run_rc=1, run_stderr="402 insufficient credits")
    orch = orch_for(agent("a-local", "va", "tool-a"))
    dispatch(orch, "a-local", tmp_path)
    assert vp.read_cache()["runtime_failures"]["a-local"]["error_class"] == "vendor_unavailable"


def test_zero_exit_review_mentioning_402_is_not_remembered(tmp_path):
    make_cli(tmp_path, "tool-a", run_rc=0, run_stdout="The service returned HTTP 402 Payment Required for this review.")
    orch = orch_for(agent("a-local", "va", "tool-a"))
    result = dispatch(orch, "a-local", tmp_path)
    assert result.success is False
    assert "a-local" not in vp.read_cache()["runtime_failures"]
    assert reviewers(orch) == {"a-local"}


def test_unwritable_cache_does_not_change_review_result(tmp_path, monkeypatch):
    make_cli(tmp_path, "tool-a", run_rc=1, run_stderr="401 unauthorized")
    orch = orch_for(agent("a-local", "va", "tool-a"))
    baseline = dispatch(orch, "a-local", tmp_path)
    monkeypatch.setenv("AGENTIC_PROBE_CACHE", "/proc/nope/cache.json")
    result = dispatch(orch, "a-local", tmp_path)
    assert (result.success, result.error_class, result.error) == (
        baseline.success, baseline.error_class, baseline.error,
    )


# ---------------------------------------------------- cross-loader instance


def test_loader_shares_module_instance_with_vendor_health():
    import vendor_health

    assert vendor_health._load_vendor_probe() is rd._load_vendor_probe()
