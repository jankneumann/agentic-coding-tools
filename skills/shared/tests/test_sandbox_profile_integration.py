"""Controlled real-runtime smoke probe; incapable hosts skip with exact prerequisites."""

import subprocess
import sys
from pathlib import Path

import pytest

from shared.local_process_backend import LocalProcessRequest, run_local_process
from shared.sandbox_profile import (
    SandboxLaunch,
    SandboxProfileError,
    discover_sandbox_runtime,
    preflight_runtime,
)


def _git_path(repo: Path, flag: str) -> Path:
    raw = subprocess.run(
        ["git", "rev-parse", flag],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    path = Path(raw)
    return (repo / path).resolve() if not path.is_absolute() else path.resolve()


def _deny_all_policy() -> dict:
    return {
        "schema_version": 1,
        "agent_id": "fixture",
        "default_action": "deny",
        "rules": [],
        "policy_revision": "v1:none:0",
        "policy_digest": "0" * 64,
    }


class _RecordingAudit:
    def __init__(self) -> None:
        self.events = []

    def record(self, event):
        self.events.append(event)


def test_real_srt_runtime_capability_or_exact_skip() -> None:
    repo = Path(__file__).resolve().parents[3]
    try:
        runtime = discover_sandbox_runtime(repo, runtime_override=repo / "tools/sandbox-runtime")
    except SandboxProfileError as exc:
        pytest.skip(f"sandbox runtime unavailable: {exc.reason}")
    result = preflight_runtime(runtime, run_probe=True)
    if not result.ok:
        pytest.skip("sandbox runtime incapable: " + ", ".join(result.missing))
    assert result.status == "passed"


def test_real_srt_controlled_vendor_enforces_filesystem_and_network(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    runtime = discover_sandbox_runtime(repo, runtime_override=repo / "tools/sandbox-runtime")
    preflight = preflight_runtime(runtime, run_probe=True)
    if not preflight.ok:
        pytest.skip("sandbox runtime incapable: " + ", ".join(preflight.missing))
    common_git = _git_path(repo, "--git-common-dir")
    common_repo = common_git.parent
    fixture = Path(__file__).parent / "fixtures" / "sandbox_vendor.py"
    secret = tmp_path / "credential.txt"
    secret.write_text("do-not-read")
    launch = SandboxLaunch(
        worktree_root=repo,
        common_repo=common_repo,
        common_git_dir=common_git,
        git_toplevel=_git_path(repo, "--show-toplevel"),
        git_common_dir=common_git,
        vendor_executable=Path(sys.executable),
        vendor_install_root=Path(sys.executable).resolve().parent,
        policy=_deny_all_policy(),
        write_capable=False,
        credential_env_key="VENDOR_TOKEN",
        state_env_keys=(),
        credential_paths=(secret,),
        authored_read_paths=(fixture,),
    )
    audit = _RecordingAudit()

    denied_write = repo / "sandbox-runtime-review-write.tmp"
    denied_write.unlink(missing_ok=True)
    result = run_local_process(
        LocalProcessRequest(
            argv=(sys.executable, str(fixture), "write", str(denied_write)),
            cwd=repo,
            env={"VENDOR_TOKEN": "fixture-token"},
            timeout_seconds=15,
            isolation="sandbox",
            sandbox_launch=launch,
            runtime=runtime,
            audit_port=audit,
            audit_event={"event_id": "review-write"},
        )
    )
    assert result.sandbox_applied is True
    assert not denied_write.exists()

    credential = run_local_process(
        LocalProcessRequest(
            argv=(sys.executable, str(fixture), "read", str(secret)),
            cwd=repo,
            env={"VENDOR_TOKEN": "fixture-token"},
            timeout_seconds=15,
            isolation="sandbox",
            sandbox_launch=launch,
            runtime=runtime,
            audit_port=audit,
            audit_event={"event_id": "credential-read"},
        )
    )
    assert credential.returncode != 0
    assert "do-not-read" not in credential.stdout

    private_network = run_local_process(
        LocalProcessRequest(
            argv=(sys.executable, str(fixture), "fetch", "http://127.0.0.1:9"),
            cwd=repo,
            env={"VENDOR_TOKEN": "fixture-token"},
            timeout_seconds=15,
            isolation="sandbox",
            sandbox_launch=launch,
            runtime=runtime,
            audit_port=audit,
            audit_event={"event_id": "private-network"},
        )
    )
    assert private_network.returncode != 0
