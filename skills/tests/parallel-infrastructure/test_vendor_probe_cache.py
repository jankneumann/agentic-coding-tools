"""Tests for the vendor probe cache (task 2.5)."""

from __future__ import annotations

import json
import os
import stat
import threading
import time
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from openspec_paths import change_dir, repo_root_from

import vendor_probe as vp

REPO_ROOT = repo_root_from(__file__, 3)
SCHEMA = json.loads(
    (change_dir(REPO_ROOT, "add-local-agent-probe") / "contracts" / "vendor-probe-cache.schema.json").read_text()
)
VALIDATOR = Draft202012Validator(SCHEMA)


def make_cli(tmp: Path, name="fakecli", auth_rc=0) -> Path:
    bindir = tmp / "bin"
    bindir.mkdir(exist_ok=True)
    log = tmp / f"{name}.log"
    path = bindir / name
    path.write_text(
        f"""#!/bin/sh
echo "$*" >> "{log}"
case "$*" in
  "--version") echo 'fake 1';;
  "--help") echo '-p --model';;
  *) exit {auth_rc};;
esac
"""
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def n_calls(tmp: Path, name="fakecli") -> int:
    log = tmp / f"{name}.log"
    return len(log.read_text().splitlines()) if log.exists() else 0


def cli(**over):
    block = {
        "command": "fakecli",
        "dispatch_modes": {"review": {"args": ["-p"]}},
        "model_flag": "--model",
        "model": "m1",
        "model_fallbacks": ["m2"],
    }
    block.update(over)
    return block


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    monkeypatch.setenv("AGENTIC_PROBE_CACHE", str(tmp_path / "cache.json"))
    for var in ("XDG_CACHE_HOME",):
        monkeypatch.delenv(var, raising=False)
    make_cli(tmp_path)


# ------------------------------------------------------------------- path


def test_cache_path_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTIC_PROBE_CACHE", str(tmp_path / "x.json"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert vp.cache_path() == tmp_path / "x.json"
    monkeypatch.delenv("AGENTIC_PROBE_CACHE")
    assert vp.cache_path() == tmp_path / "xdg" / "agentic-coding-tools" / "vendor-probe.json"
    monkeypatch.delenv("XDG_CACHE_HOME")
    assert vp.cache_path() == Path.home() / ".cache" / "agentic-coding-tools" / "vendor-probe.json"


# ------------------------------------------------------------ fingerprint


def test_fingerprint_stable_across_sources():
    raw = cli()
    del raw["model_flag"]
    serialized = {**cli(), "model_flag": "-m", "prompt_via_stdin": False, "thinking_flag": None}
    assert vp.lane_fingerprint(raw) == vp.lane_fingerprint(serialized)


def test_empty_probe_differs_from_absent():
    assert vp.lane_fingerprint(cli()) != vp.lane_fingerprint(cli(probe={}))


def test_default_version_args_fingerprint_like_absent():
    a = cli(probe={"auth_status_args": ["auth", "status"]})
    b = cli(probe={"auth_status_args": ["auth", "status"], "version_args": ["--version"]})
    assert vp.lane_fingerprint(a) == vp.lane_fingerprint(b)


def test_model_list_edit_keeps_fingerprint_but_args_edit_changes_it():
    base = vp.lane_fingerprint(cli())
    assert base == vp.lane_fingerprint(cli(model_fallbacks=["m3"], model="z"))
    assert base != vp.lane_fingerprint(cli(dispatch_modes={"review": {"args": ["-q"]}}))


# ------------------------------------------------- write / read / freshness


def test_probe_writes_private_valid_cache(tmp_path):
    vp.probe_lanes({"a": cli(probe={})}, reuse_fresh=False)
    path = tmp_path / "cache.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    doc = json.loads(path.read_text())
    assert not list(VALIDATOR.iter_errors(doc))


def test_reuse_fresh_starts_no_subprocess(tmp_path):
    vp.probe_lanes({"a": cli()}, reuse_fresh=False)
    before = n_calls(tmp_path)
    assert before > 0
    result = vp.probe_lanes({"a": cli()}, reuse_fresh=True)
    assert n_calls(tmp_path) == before
    assert result["a"].reused


def test_stale_on_fingerprint_realpath_ttl_and_max_age(tmp_path):
    vp.probe_lanes({"a": cli()}, reuse_fresh=False)
    doc = vp.read_cache()
    assert vp.fresh_entry(doc, "a", cli()) is not None
    assert vp.fresh_entry(doc, "a", cli(dispatch_modes={"review": {"args": ["-z"]}})) is None
    assert vp.fresh_entry(doc, "a", cli(probe={})) is None
    assert vp.fresh_entry(doc, "a", cli(), now=time.time() + 86401) is None
    assert vp.fresh_entry(doc, "a", cli(), now=time.time() + 4000, max_age_seconds=3600) is None
    other = tmp_path / "other"
    other.mkdir()
    make_cli(other)
    os.environ["PATH"] = f"{other / 'bin'}:{os.environ['PATH']}"
    assert vp.fresh_entry(doc, "a", cli()) is None


def test_stale_entry_never_excludes(tmp_path):
    vp.probe_lanes({"a": cli(command="nope-xyz")}, reuse_fresh=False)
    doc = vp.read_cache()
    block = cli(command="nope-xyz")
    assert vp.cache_exclusion("a", block, "review", doc)[0] == "cli_not_found"
    assert vp.cache_exclusion("a", block, "review", doc, now=time.time() + 90000) is None


def test_corrupt_cache_is_empty_and_overwritten(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{not json")
    assert vp.read_cache()["lanes"] == {}
    vp.probe_lanes({"a": cli()}, reuse_fresh=False)
    assert "a" in json.loads(path.read_text())["lanes"]


def test_unwritable_cache_does_not_fail_probe(tmp_path, monkeypatch, caplog):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    monkeypatch.setenv("AGENTIC_PROBE_CACHE", str(ro / "sub" / "cache.json"))
    try:
        result = vp.probe_lanes({"a": cli()}, reuse_fresh=False)
    finally:
        ro.chmod(0o700)
    assert result["a"].entry["l0"] == {"ok": True}
    assert any("not written" in r.message for r in caplog.records)


def test_runtime_failure_write_failure_is_false(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_PROBE_CACHE", "/proc/nope/cache.json")
    assert vp.record_runtime_failure("a", "auth_required") is False


# -------------------------------------------------------- runtime failures


def test_runtime_failure_without_lane_entry_and_ttl():
    assert vp.record_runtime_failure("grok", "auth_required")
    doc = vp.read_cache()
    assert not list(VALIDATOR.iter_errors(doc))
    assert vp.fresh_runtime_failure(doc, "grok")
    assert vp.fresh_runtime_failure(doc, "grok", now=time.time() + 3601) is None
    verdict = vp.cache_exclusion("grok", cli(), "review", doc)
    assert verdict[0] == "runtime_auth_required"


def test_runtime_failure_survives_config_change_and_probe(tmp_path):
    vp.record_runtime_failure("a", "vendor_unavailable")
    vp.probe_lanes({"a": cli(probe={"credential_files": [str(tmp_path)]})}, reuse_fresh=False)
    assert vp.read_cache()["runtime_failures"]["a"]["error_class"] == "vendor_unavailable"


def test_concurrent_writers_do_not_lose_updates():
    threads = [
        threading.Thread(target=vp.record_runtime_failure, args=(f"lane{i}", "auth_required"))
        for i in range(12)
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]
    doc = vp.read_cache()
    assert len(doc["runtime_failures"]) == 12
    assert not list(VALIDATOR.iter_errors(doc))


def test_status_command_clears_auth_required_only(tmp_path):
    block = cli(probe={"auth_status_args": ["auth", "status"]})
    vp.record_runtime_failure("a", "auth_required")
    time.sleep(1.1)  # observed_at has 1 s resolution
    result = vp.probe_lanes({"a": block}, reuse_fresh=False)
    assert result["a"].runtime_failure is None
    assert "a" not in vp.read_cache()["runtime_failures"]


def test_billing_failure_not_cleared_by_auth_ok(tmp_path):
    block = cli(probe={"auth_status_args": ["auth", "status"]})
    vp.record_runtime_failure("a", "vendor_unavailable")
    time.sleep(1.1)
    result = vp.probe_lanes({"a": block}, reuse_fresh=False)
    assert result["a"].runtime_failure["error_class"] == "vendor_unavailable"
    assert vp.cache_exclusion("a", block, "review")[0] == "runtime_vendor_unavailable"


def test_credential_file_evidence_does_not_clear(tmp_path):
    f = tmp_path / "auth.json"
    f.write_text("x")
    block = cli(probe={"credential_files": [str(f)]})
    vp.record_runtime_failure("a", "auth_required")
    time.sleep(1.1)
    result = vp.probe_lanes({"a": block}, reuse_fresh=False)
    assert result["a"].entry["l2"]["status"] == "auth_ok"
    assert result["a"].runtime_failure["error_class"] == "auth_required"


def test_probe_started_before_failure_does_not_clear():
    block = cli(probe={"auth_status_args": ["auth", "status"]})
    probe = vp.probe_lane("a", block)
    started = probe.auth_started_at
    assert started is not None
    vp.record_runtime_failure("a", "auth_required", now=started + 1)
    vp.store_probes([probe])
    assert vp.read_cache()["runtime_failures"]["a"]["error_class"] == "auth_required"
