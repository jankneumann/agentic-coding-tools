"""Registered front door for every production local vendor process."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from .local_process_backend import (
    LocalProcessRequest,
    LocalProcessResult,
    run_local_process,
)
from .sandbox_audit import SandboxAuditPort
from .sandbox_activation import (
    SandboxActivationContext,
    SandboxActivationError,
    SandboxDegradation,
    activate_sandbox,
)
from .sandbox_profile import RuntimePaths, SandboxLaunch


@dataclass(frozen=True)
class VendorProcessSurface:
    path: str
    inherited_sandbox: bool = False


PRODUCTION_VENDOR_SURFACES: dict[str, VendorProcessSurface] = {
    "review": VendorProcessSurface(
        "skills/parallel-infrastructure/scripts/review_dispatcher.py"
    ),
    "fact_check": VendorProcessSurface(
        "skills/parallel-infrastructure/scripts/fact_check.py"
    ),
    "autopilot_provider": VendorProcessSurface(
        "skills/autopilot/scripts/provider_dispatch.py"
    ),
    "phase_fixer": VendorProcessSurface("skills/autopilot/scripts/phase_fixer.py"),
    "quick_task": VendorProcessSurface("skills/quick-task/scripts/quick_task.py"),
    "evaluation_claude_code": VendorProcessSurface(
        "agent-coordinator/evaluation/backends/claude_code.py"
    ),
    "evaluation_codex": VendorProcessSurface(
        "agent-coordinator/evaluation/backends/codex.py"
    ),
    "evaluation_antigravity": VendorProcessSurface(
        "agent-coordinator/evaluation/backends/antigravity.py"
    ),
    "evaluation_grok": VendorProcessSurface(
        "agent-coordinator/evaluation/backends/grok.py"
    ),
    "evaluation_pi": VendorProcessSurface(
        "agent-coordinator/evaluation/backends/pi.py"
    ),
    "ocr_descendant": VendorProcessSurface(
        "skills/parallel-infrastructure/scripts/ocr_adapter.py",
        inherited_sandbox=True,
    ),
    "local_process_backend": VendorProcessSurface(
        "skills/shared/local_process_backend.py"
    ),
}


class VendorProcessBlocked(OSError):
    """A vendor process was blocked before launch by enforcement."""


@dataclass(frozen=True)
class VendorProcessInvocation:
    surface: str
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
    activation_context: SandboxActivationContext | None = None


def _absolute_argv(argv: tuple[str, ...], env: Mapping[str, str]) -> tuple[str, ...]:
    if not argv:
        raise ValueError("vendor argv cannot be empty")
    executable = Path(argv[0])
    if executable.is_absolute():
        return argv
    resolved = shutil.which(
        argv[0],
        path=env.get("PATH") or os.environ.get("PATH") or os.defpath,
    )
    if resolved is None:
        raise FileNotFoundError(f"vendor executable not found: {argv[0]}")
    return (str(Path(resolved).resolve()), *argv[1:])


def run_vendor_process(invocation: VendorProcessInvocation) -> LocalProcessResult:
    """Run one registered process attempt through the shared lifecycle owner."""

    if invocation.surface not in PRODUCTION_VENDOR_SURFACES:
        raise ValueError(f"unregistered vendor process surface: {invocation.surface}")
    argv = _absolute_argv(invocation.argv, invocation.env)
    launch = invocation.sandbox_launch
    runtime = invocation.runtime
    audit_port = invocation.audit_port
    audit_event = invocation.audit_event
    if invocation.isolation == "sandbox" and launch is None:
        if invocation.activation_context is None:
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
        try:
            activated = activate_sandbox(
                context=invocation.activation_context,
                vendor_executable=Path(argv[0]),
                env=invocation.env,
            )
        except (SandboxActivationError, OSError, ValueError) as exc:
            return LocalProcessResult(
                status="prelaunch_enforcement_blocked",
                returncode=None,
                stdout="",
                stderr="",
                timed_out=False,
                sandbox_applied=False,
                degradation_reason=getattr(exc, "reason", str(exc)),
                cleanup_status="not_started",
            )
        if isinstance(activated, SandboxDegradation):
            try:
                activated.audit_port.record(activated.audit_event)
            except Exception:  # noqa: BLE001 - fail-open requires durable evidence
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
                f"sandbox degraded after durable audit: {activated.reason}",
                RuntimeWarning,
                stacklevel=2,
            )
            result = run_local_process(
                LocalProcessRequest(
                    argv=argv,
                    cwd=invocation.cwd,
                    env=invocation.env,
                    timeout_seconds=invocation.timeout_seconds,
                    isolation="none",
                    stdin_text=invocation.stdin_text,
                    terminate_grace_seconds=invocation.terminate_grace_seconds,
                )
            )
            degraded = LocalProcessResult(
                status=result.status,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                timed_out=result.timed_out,
                sandbox_applied=False,
                degradation_reason=activated.reason,
                cleanup_status=result.cleanup_status,
                cleanup_residual_paths=result.cleanup_residual_paths,
            )
            object.__setattr__(degraded, "sandbox_metadata", activated.audit_event)
            return degraded
        launch = activated.launch
        runtime = activated.runtime
        audit_port = activated.audit_port
        audit_event = activated.audit_event
    if invocation.isolation == "sandbox" and (
        launch is None
        or runtime is None
        or audit_port is None
        or audit_event is None
    ):
        return LocalProcessResult(
            status="prelaunch_enforcement_blocked",
            returncode=None,
            stdout="",
            stderr="",
            timed_out=False,
            sandbox_applied=False,
            degradation_reason="sandbox_context_incomplete",
            cleanup_status="not_started",
        )
    result = run_local_process(
        LocalProcessRequest(
            argv=argv,
            cwd=invocation.cwd,
            env=invocation.env,
            timeout_seconds=invocation.timeout_seconds,
            isolation=invocation.isolation,
            stdin_text=invocation.stdin_text,
            terminate_grace_seconds=invocation.terminate_grace_seconds,
            sandbox_launch=launch,
            runtime=runtime,
            audit_port=audit_port,
            audit_event=audit_event,
        )
    )
    if audit_event:
        object.__setattr__(result, "sandbox_metadata", audit_event)
    return result


async def run_vendor_process_async(
    invocation: VendorProcessInvocation,
) -> LocalProcessResult:
    """Async compatibility wrapper around the one synchronous lifecycle owner."""

    return await asyncio.to_thread(run_vendor_process, invocation)


def as_completed_process(
    invocation: VendorProcessInvocation,
    result: LocalProcessResult,
) -> subprocess.CompletedProcess[str]:
    """Adapt the shared result for legacy callers without losing enforcement."""

    if result.status == "prelaunch_enforcement_blocked":
        raise VendorProcessBlocked(result.degradation_reason or result.status)
    if result.timed_out:
        raise subprocess.TimeoutExpired(
            list(invocation.argv),
            invocation.timeout_seconds,
            output=result.stdout,
            stderr=result.stderr,
        )
    completed = subprocess.CompletedProcess(
        list(invocation.argv),
        result.returncode or 0,
        result.stdout,
        result.stderr,
    )
    result_evidence = getattr(result, "sandbox_metadata", {})
    evidence = dict(result_evidence if isinstance(result_evidence, dict) else {})
    evidence.update(invocation.audit_event or {})
    if "routing_digest" not in evidence and isinstance(
        evidence.get("routing_context_digest"), str
    ):
        evidence["routing_digest"] = evidence["routing_context_digest"]
    evidence.update(
        requested_isolation=invocation.isolation,
        applied_isolation=(
            "sandbox"
            if result.sandbox_applied
            else invocation.isolation
            if invocation.isolation in {"none", "worktree"}
            else "none"
        ),
        cleanup_status=result.cleanup_status,
        cleanup_residual_paths=list(result.cleanup_residual_paths),
    )
    setattr(completed, "sandbox_metadata", evidence)
    return completed
