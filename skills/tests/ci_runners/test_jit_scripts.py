"""mint-jitconfig.sh and cleanup-runner.sh against a stub curl (D5). No network."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from ._stubs import install_curl_stub, path_with, read_calls

HOST = "testhost"
REPO = "owner/repo"
RUNNER_DEFAULTS = {"self-hosted", "linux", "arm64"}


def _run(script: Path, args: list[str], env_extra: dict[str, str], tmp: Path, config: dict):
    bin_dir = tmp / "bin"
    stub_env, log = install_curl_stub(bin_dir, config, tmp)
    runtime = tmp / "run"
    runtime.mkdir(exist_ok=True)
    token = tmp / "token"
    if not token.exists():
        token.write_text("ghp_SECRETTOKEN\n")
        token.chmod(0o600)
    env = {
        "PATH": path_with(bin_dir),
        "HOME": str(tmp),
        "XDG_RUNTIME_DIR": str(runtime),
        "GX10_RUNNER_REPO": REPO,
        "GX10_HOSTNAME": HOST,
        "GX10_RUNNER_TOKEN_FILE": str(token),
        "GX10_RUNNER_LABELS": "self-hosted,linux,ARM64,gx10",
        "GX10_MINT_BASE_DELAY": "0.01",
        "GX10_MINT_MAX_ELAPSED": "5",
        "GX10_MINT_FAIL_HOLDOFF": "0",
        "GX10_MINT_REQ_MAX": "0.01",
        **stub_env,
        **env_extra,
    }
    res = subprocess.run(
        ["bash", str(script), *args], env=env, capture_output=True, text=True, timeout=60
    )
    return res, read_calls(log), runtime / "gx10-runner"


def _mint_ok_route():
    return {
        "method": "POST",
        "pattern": r"generate-jitconfig$",
        "status": 201,
        "body": {"runner": {"id": 4242}, "encoded_jit_config": "ENCODEDJIT=="},
    }


@pytest.fixture()
def mint(kit_dir):
    return kit_dir / "mint-jitconfig.sh"


@pytest.fixture()
def cleanup(kit_dir):
    return kit_dir / "cleanup-runner.sh"


def test_mint_writes_only_jitconfig_and_runner_id(mint, tmp_path):
    cfg = {"routes": [_mint_ok_route()]}
    res, calls, env_dir = _run(mint, ["1"], {}, tmp_path, cfg)
    assert res.returncode == 0, res.stderr
    env_file = env_dir / "1.env"
    assert oct(env_file.stat().st_mode & 0o777) == "0o600"
    lines = env_file.read_text().splitlines()
    assert lines == ["ACTIONS_RUNNER_INPUT_JITCONFIG=ENCODEDJIT==", "GX10_RUNNER_ID=4242"]
    # the credential is on the host only: not in the env file, not in any curl argument
    assert "SECRETTOKEN" not in env_file.read_text()
    for call in calls:
        assert "SECRETTOKEN" not in json.dumps(call)


def test_mint_refuses_wide_credential_mode(mint, tmp_path):
    token = tmp_path / "token"
    token.write_text("ghp_x\n")
    token.chmod(0o640)
    res, calls, env_dir = _run(mint, ["1"], {}, tmp_path, {"routes": [_mint_ok_route()]})
    assert res.returncode != 0
    assert "mode" in res.stderr
    assert calls == []
    assert not (env_dir / "1.env").exists()


def test_mint_prefers_systemd_credential_directory(mint, tmp_path):
    cred = tmp_path / "creds"
    cred.mkdir()
    (cred / "github-token").write_text("ghp_FROMCRED\n")
    (cred / "github-token").chmod(0o400)
    res, _, _ = _run(
        mint,
        ["1"],
        {"CREDENTIALS_DIRECTORY": str(cred), "GX10_RUNNER_TOKEN_FILE": "/nonexistent"},
        tmp_path,
        {"routes": [_mint_ok_route()]},
    )
    assert res.returncode == 0, res.stderr


def test_mint_requests_only_custom_labels(mint, tmp_path, manifest):
    res, calls, _ = _run(mint, ["1"], {}, tmp_path, {"routes": [_mint_ok_route()]})
    assert res.returncode == 0, res.stderr
    (post,) = [c for c in calls if c["method"] == "POST"]
    assert post["url"].endswith(f"/repos/{REPO}/actions/runners/generate-jitconfig")
    body = json.loads(post["data"])
    requested = {x.lower() for x in body["labels"]}
    assert not requested & RUNNER_DEFAULTS
    assert requested | RUNNER_DEFAULTS == {
        x.lower() for x in manifest["routing"]["self_hosted_labels"]
    }
    assert body["name"].startswith(f"gx10-{HOST}-1-")
    assert body["runner_group_id"] == 1 and body["work_folder"] == "_work"


def test_mint_retries_with_backoff_then_gives_up(mint, tmp_path):
    cfg = {
        "routes": [{"method": "POST", "pattern": r"generate-jitconfig$", "status": 503, "body": {}}]
    }
    res, calls, env_dir = _run(mint, ["1"], {"GX10_MINT_MAX_ELAPSED": "0.5"}, tmp_path, cfg)
    assert res.returncode != 0
    posts = [c for c in calls if c["method"] == "POST"]
    assert len(posts) >= 3, "expected several attempts before the budget was spent"
    assert "retry budget" in res.stderr
    assert not (env_dir / "1.env").exists()


def test_mint_does_not_retry_client_errors(mint, tmp_path):
    cfg = {
        "routes": [{"method": "POST", "pattern": r"generate-jitconfig$", "status": 422, "body": {}}]
    }
    res, calls, env_dir = _run(mint, ["1"], {}, tmp_path, cfg)
    assert res.returncode != 0
    assert len([c for c in calls if c["method"] == "POST"]) == 1
    assert not (env_dir / "1.env").exists()


def test_non_retryable_failure_holds_off_before_exiting(mint, tmp_path):
    """Restart=always re-runs the mint every RestartSec: a revoked token must not hot-loop."""
    import time

    cfg = {
        "routes": [{"method": "POST", "pattern": r"generate-jitconfig$", "status": 401, "body": {}}]
    }
    start = time.monotonic()
    res, _, _ = _run(mint, ["1"], {"GX10_MINT_FAIL_HOLDOFF": "1"}, tmp_path, cfg)
    assert res.returncode != 0
    assert time.monotonic() - start >= 1, "exited without the hold-off"
    assert "holding off 1s" in res.stderr


def test_whole_mint_run_is_bounded_below_the_start_timeout(mint, kit_dir):
    """TimeoutStartSec bounds ALL of ExecStartPre: sweep, mint retries and hold-off share one
    clock started before the first API call, and no request starts unless it fits."""
    import re

    text = mint.read_text()
    unit_text = (kit_dir / "systemd" / "gx10-runner@.service").read_text()
    env_text = (kit_dir / "gx10-runner.env.example").read_text()
    max_elapsed = int(re.search(r"^GX10_MINT_MAX_ELAPSED=(\d+)", env_text, re.M).group(1))
    req_max = int(re.search(r"GX10_MINT_REQ_MAX:-(\d+)", text).group(1))
    holdoff = int(re.search(r"GX10_MINT_FAIL_HOLDOFF:-(\d+)", text).group(1))
    timeout = int(re.search(r"^TimeoutStartSec=(\d+)", unit_text, re.M).group(1))
    assert max_elapsed + req_max < timeout
    assert holdoff <= max_elapsed
    # The clock starts before the sweep, and every request goes through the budget check.
    assert text.index('start_us="$(now_us)"') < text.index("\nsweep() {")
    assert "sweep_cap_us" in text and "if ! fits 0; then" in text
    assert '--max-time "$req_max"' in text and "--max-time 30" not in text


def test_hold_off_is_clipped_to_the_remaining_budget(mint, tmp_path):
    cfg = {
        "routes": [{"method": "POST", "pattern": r"generate-jitconfig$", "status": 403, "body": {}}]
    }
    res, _, _ = _run(
        mint, ["1"], {"GX10_MINT_FAIL_HOLDOFF": "300", "GX10_MINT_MAX_ELAPSED": "1"}, tmp_path, cfg
    )
    assert res.returncode != 0
    assert re.search(r"holding off [01]s", res.stderr), res.stderr


@pytest.mark.parametrize(
    "value",
    ["--privileged", "--network host", "--volume /:/host", "--volume gx10-runner-uv-cache:/home/runner/.cache/uv --cap-add ALL"],
)
def test_mint_refuses_unexpected_cache_args(mint, tmp_path, value):
    cfg = {"routes": [_mint_ok_route()]}
    res, calls, env_dir = _run(mint, ["1"], {"GX10_RUNNER_CACHE_ARGS": value}, tmp_path, cfg)
    assert res.returncode != 0 and "refusing GX10_RUNNER_CACHE_ARGS" in res.stderr
    assert calls == [] and not (env_dir / "1.env").exists()


@pytest.mark.parametrize("value", ["", "--volume gx10-runner-uv-cache:/home/runner/.cache/uv"])
def test_mint_accepts_documented_cache_args(mint, tmp_path, value):
    cfg = {"routes": [_mint_ok_route()]}
    res, _, env_dir = _run(mint, ["1"], {"GX10_RUNNER_CACHE_ARGS": value}, tmp_path, cfg)
    assert res.returncode == 0, res.stderr
    assert (env_dir / "1.env").exists()


def _runner(rid, name, status):
    return {"id": rid, "name": name, "status": status}


def test_sweep_deletes_only_own_offline_runners_across_pages(mint, tmp_path):
    page1 = {
        "runners": [
            _runner(1, f"gx10-{HOST}-1-100", "offline"),  # ours, offline: delete
            _runner(2, f"gx10-{HOST}-1-101", "online"),  # ours, online: keep
            _runner(3, f"gx10-{HOST}-2-102", "offline"),  # other instance: keep
            _runner(4, "gx10-otherhost-1-103", "offline"),  # other host: keep
            _runner(5, f"gx10-{HOST}-10-104", "offline"),  # instance 10, not 1: keep
        ]
    }
    page2 = {"runners": [_runner(6, f"gx10-{HOST}-1-105", "offline")]}  # second page: delete
    cfg = {
        "routes": [
            {
                "method": "GET",
                "pattern": r"runners\?per_page=100&page=1$",
                "status": 200,
                "body": page1,
                "headers": {"Link": '<https://api.github.com/x?page=2>; rel="next"'},
            },
            {
                "method": "GET",
                "pattern": r"runners\?per_page=100&page=2$",
                "status": 200,
                "body": page2,
            },
            {"method": "DELETE", "pattern": r"/runners/\d+$", "status": 204, "body": {}},
            _mint_ok_route(),
        ]
    }
    res, calls, _ = _run(mint, ["1"], {}, tmp_path, cfg)
    assert res.returncode == 0, res.stderr
    deletes = sorted(c["url"].rsplit("/", 1)[1] for c in calls if c["method"] == "DELETE")
    assert deletes == ["1", "6"]
    order = [c["method"] for c in calls]
    assert order.index("POST") > max(i for i, m in enumerate(order) if m == "DELETE")
    # Every listing page is read before the first DELETE: deleting while paging shifts later
    # runners onto pages already read, and the next page request would skip them.
    last_get = max(i for i, m in enumerate(order) if m == "GET")
    first_delete = min(i for i, m in enumerate(order) if m == "DELETE")
    assert last_get < first_delete, order


def test_failing_sweep_does_not_stop_the_mint(mint, tmp_path):
    cfg = {
        "routes": [
            {"method": "GET", "pattern": r"/runners\?", "status": 500, "body": {}},
            _mint_ok_route(),
        ]
    }
    res, _, env_dir = _run(mint, ["1"], {}, tmp_path, cfg)
    assert res.returncode == 0, res.stderr
    assert (env_dir / "1.env").exists()


def _seed_env(tmp_path, rid="4242"):
    d = tmp_path / "run" / "gx10-runner"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "1.env"
    f.write_text(f"ACTIONS_RUNNER_INPUT_JITCONFIG=abc\nGX10_RUNNER_ID={rid}\n")
    return f


def test_cleanup_deletes_offline_runner(cleanup, tmp_path):
    env_file = _seed_env(tmp_path)
    cfg = {
        "routes": [
            {
                "method": "GET",
                "pattern": r"/runners/4242$",
                "status": 200,
                "body": {"status": "offline"},
            },
            {"method": "DELETE", "pattern": r"/runners/4242$", "status": 204, "body": {}},
        ]
    }
    res, calls, _ = _run(cleanup, ["1"], {}, tmp_path, cfg)
    assert res.returncode == 0
    assert [c["method"] for c in calls] == ["GET", "DELETE"]
    assert not env_file.exists(), "the single-use JIT config must not be left on disk"


def test_cleanup_leaves_online_runner_alone(cleanup, tmp_path):
    _seed_env(tmp_path)
    cfg = {
        "routes": [
            {
                "method": "GET",
                "pattern": r"/runners/4242$",
                "status": 200,
                "body": {"status": "online"},
            },
        ]
    }
    res, calls, _ = _run(cleanup, ["1"], {}, tmp_path, cfg)
    assert res.returncode == 0
    assert [c["method"] for c in calls] == ["GET"]


def test_cleanup_always_exits_zero(cleanup, tmp_path):
    # no env file, an unregistered runner, and an API outage must all exit 0
    res, calls, _ = _run(cleanup, ["1"], {}, tmp_path, {"routes": []})
    assert res.returncode == 0 and calls == []
    _seed_env(tmp_path)
    res, _, _ = _run(
        cleanup,
        ["1"],
        {},
        tmp_path,
        {"routes": [{"method": "GET", "pattern": ".", "status": 500, "body": {}}]},
    )
    assert res.returncode == 0
    _seed_env(tmp_path)
    res, _, _ = _run(
        cleanup, ["1"], {"GX10_RUNNER_TOKEN_FILE": "/nonexistent"}, tmp_path, {"routes": []}
    )
    assert res.returncode == 0


def test_scripts_are_executable(kit_dir):
    for name in ("mint-jitconfig.sh", "cleanup-runner.sh"):
        assert os.access(kit_dir / name, os.X_OK), name
