"""Process lifecycle and fail-open/fail-closed tests for the shared backend."""

from __future__ import annotations

import sys
from pathlib import Path

from shared import local_process_backend as backend
from shared.local_process_backend import LocalProcessRequest, run_local_process
from shared.sandbox_profile import SandboxLaunch, SandboxProfileError


def test_unsandboxed_path_preserves_environment_and_output(tmp_path: Path) -> None:
    request = LocalProcessRequest(
        argv=(sys.executable, "-c", "import os; print(os.environ['EXACT'])"),
        cwd=tmp_path,
        env={"EXACT": "preserved"},
        timeout_seconds=2,
        isolation="none",
    )
    result = run_local_process(request)
    assert result.status == "completed"
    assert result.stdout.strip() == "preserved"
    assert result.sandbox_applied is False


def test_unsandboxed_path_preserves_optional_stdin(tmp_path: Path) -> None:
    request = LocalProcessRequest(
        argv=(sys.executable, "-c", "import sys; print(sys.stdin.read())"),
        cwd=tmp_path,
        env={},
        timeout_seconds=2,
        isolation="none",
        stdin_text="vendor prompt",
    )

    result = run_local_process(request)

    assert result.status == "completed"
    assert result.stdout.strip() == "vendor prompt"


def test_timeout_terminates_process_group(tmp_path: Path) -> None:
    request = LocalProcessRequest(
        argv=(sys.executable, "-c", "import time; time.sleep(30)"),
        cwd=tmp_path,
        env={},
        timeout_seconds=0.05,
        isolation="none",
        terminate_grace_seconds=0.05,
    )
    result = run_local_process(request)
    assert result.status == "timeout"
    assert result.timed_out is True
    assert result.cleanup_status == "succeeded"


def test_sandbox_without_launch_contract_fails_before_process(tmp_path: Path) -> None:
    request = LocalProcessRequest(
        argv=(sys.executable, "-c", "raise SystemExit(99)"),
        cwd=tmp_path,
        env={},
        timeout_seconds=1,
        isolation="sandbox",
    )
    result = run_local_process(request)
    assert result.status == "prelaunch_enforcement_blocked"
    assert result.returncode is None
    assert result.degradation_reason == "sandbox_context_missing"


def test_fail_open_requires_durable_audit_before_original_command(
    tmp_path: Path, monkeypatch
) -> None:
    marker = tmp_path / "ran"
    launch = SandboxLaunch(
        worktree_root=tmp_path,
        common_repo=tmp_path,
        common_git_dir=tmp_path / ".git",
        git_toplevel=tmp_path,
        git_common_dir=tmp_path / ".git",
        vendor_executable=Path(sys.executable),
        vendor_install_root=Path(sys.executable).resolve().parent,
        policy={},
        agent_id="fixture",
        write_capable=False,
        credential_env_key="TOKEN",
        state_env_keys=(),
    )
    runtime = object()
    monkeypatch.setattr(
        backend,
        "prepare_sandbox_command",
        lambda **_kwargs: (_ for _ in ()).throw(
            SandboxProfileError("runtime_missing", fail_open=True)
        ),
    )

    class FailedAudit:
        def record(self, _event):
            raise OSError("audit unavailable")

    result = run_local_process(
        LocalProcessRequest(
            argv=(sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"),
            cwd=tmp_path,
            env={},
            timeout_seconds=1,
            isolation="sandbox",
            sandbox_launch=launch,
            runtime=runtime,  # type: ignore[arg-type]
            audit_port=FailedAudit(),
            audit_event={"event_id": "event"},
        )
    )
    assert result.status == "prelaunch_enforcement_blocked"
    assert result.degradation_reason == "audit_unavailable"
    assert not marker.exists()
