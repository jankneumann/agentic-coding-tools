"""Single lifecycle owner for local vendor CLI processes."""

from __future__ import annotations

import os
import signal
import subprocess
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from .sandbox_audit import SandboxAuditPort
from .sandbox_profile import (
    RuntimePaths,
    SandboxLaunch,
    SandboxProfileError,
    prepare_sandbox_command,
)


@dataclass(frozen=True)
class LocalProcessRequest:
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]
    timeout_seconds: float
    isolation: Literal["none", "worktree", "sandbox"]
    stdin_text: str | None = None
    terminate_grace_seconds: float = 2.0
    sandbox_launch: SandboxLaunch | None = None
    runtime: RuntimePaths | None = None
    audit_port: SandboxAuditPort | None = None
    audit_event: dict[str, Any] | None = None


@dataclass(frozen=True)
class LocalProcessResult:
    status: Literal["completed", "timeout", "prelaunch_enforcement_blocked"]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    sandbox_applied: bool
    degradation_reason: str | None
    cleanup_status: Literal["not_started", "succeeded", "failed"]
    cleanup_residual_paths: tuple[str, ...] = ()
    sandbox_metadata: dict[str, Any] = field(default_factory=dict)


def _run_process(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float,
    grace: float,
    stdin_text: str | None,
) -> tuple[int, str, str, bool]:
    process = subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=dict(env),
        stdin=subprocess.PIPE if stdin_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        close_fds=True,
    )
    try:
        stdout, stderr = process.communicate(input=stdin_text, timeout=timeout)
        return process.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=grace)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return process.returncode, stdout, stderr, True


def _record_audit(
    request: LocalProcessRequest, changes: Mapping[str, Any]
) -> dict[str, Any] | None:
    if request.audit_port is None or request.audit_event is None:
        return None
    event = {**request.audit_event, **changes}
    request.audit_port.record(event)
    return event


def run_local_process(request: LocalProcessRequest) -> LocalProcessResult:
    """Run one attempt, owning process group timeout and sandbox cleanup."""

    if request.timeout_seconds <= 0 or request.terminate_grace_seconds <= 0:
        raise ValueError("process timeouts must be positive")
    if not request.argv or not Path(request.argv[0]).is_absolute():
        raise ValueError("vendor executable must be absolute")
    if request.isolation != "sandbox":
        returncode, stdout, stderr, timed_out = _run_process(
            request.argv,
            cwd=request.cwd,
            env=request.env,
            timeout=request.timeout_seconds,
            grace=request.terminate_grace_seconds,
            stdin_text=request.stdin_text,
        )
        return LocalProcessResult(
            status="timeout" if timed_out else "completed",
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            sandbox_applied=False,
            degradation_reason=None,
            cleanup_status="succeeded",
        )
    if request.sandbox_launch is None or request.runtime is None:
        return LocalProcessResult(
            status="prelaunch_enforcement_blocked",
            returncode=None,
            stdout="",
            stderr="",
            timed_out=False,
            sandbox_applied=False,
            degradation_reason="sandbox_context_missing",
            cleanup_status="not_started",
        )
    launch = request.sandbox_launch
    vendor_args = request.argv[1:]
    prepared = None
    try:
        with prepare_sandbox_command(
            runtime=request.runtime,
            launch=launch,
            vendor_argv=vendor_args,
            parent_env=request.env,
        ) as prepared:
            returncode, stdout, stderr, timed_out = _run_process(
                prepared.argv,
                cwd=prepared.cwd,
                env=prepared.env,
                timeout=request.timeout_seconds,
                grace=request.terminate_grace_seconds,
                stdin_text=request.stdin_text,
            )
    except SandboxProfileError as exc:
        if exc.fail_open:
            if request.audit_port is None or request.audit_event is None:
                return LocalProcessResult(
                    status="prelaunch_enforcement_blocked",
                    returncode=None,
                    stdout="",
                    stderr="",
                    timed_out=False,
                    sandbox_applied=False,
                    degradation_reason="audit_unavailable",
                    cleanup_status="not_started",
                )
            try:
                finalized_event = _record_audit(
                    request,
                    {
                        "sandbox_applied": False,
                        "backend": "local-process",
                        "preflight_status": exc.reason,
                        "degradation_reason": exc.reason,
                    },
                )
            except Exception:  # noqa: BLE001 - evidence failure must block launch
                return LocalProcessResult(
                    status="prelaunch_enforcement_blocked",
                    returncode=None,
                    stdout="",
                    stderr="",
                    timed_out=False,
                    sandbox_applied=False,
                    degradation_reason="audit_unavailable",
                    cleanup_status="not_started",
                )
            warnings.warn(
                f"sandbox degraded after durable audit: {exc.reason}",
                RuntimeWarning,
                stacklevel=2,
            )
            returncode, stdout, stderr, timed_out = _run_process(
                request.argv,
                cwd=request.cwd,
                env=request.env,
                timeout=request.timeout_seconds,
                grace=request.terminate_grace_seconds,
                stdin_text=request.stdin_text,
            )
            return LocalProcessResult(
                status="timeout" if timed_out else "completed",
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                sandbox_applied=False,
                degradation_reason=exc.reason,
                cleanup_status="succeeded",
                sandbox_metadata=finalized_event or {},
            )
        return LocalProcessResult(
            status="prelaunch_enforcement_blocked",
            returncode=None,
            stdout="",
            stderr="",
            timed_out=False,
            sandbox_applied=False,
            degradation_reason=exc.reason,
            cleanup_status="not_started",
        )
    assert prepared is not None
    finalized_event = _record_audit(
        request,
        {
            "sandbox_applied": True,
            "runtime_version": prepared.runtime_version,
            "settings_digest": prepared.settings_digest,
            "cleanup_status": prepared.cleanup_status,
            "cleanup_residual_paths": prepared.cleanup_residual_paths,
        },
    )
    return LocalProcessResult(
        status="timeout" if timed_out else "completed",
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        sandbox_applied=True,
        degradation_reason=None,
        cleanup_status=prepared.cleanup_status,
        cleanup_residual_paths=tuple(prepared.cleanup_residual_paths),
        sandbox_metadata=finalized_event or {},
    )
