"""Production vendor-process activation and result metadata tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from shared import vendor_process_surfaces as surfaces
from shared.local_process_backend import LocalProcessResult
from shared.sandbox_activation import SandboxDegradation
from shared.vendor_process_surfaces import (
    VendorProcessInvocation,
    as_completed_process,
    run_vendor_process,
)


def _result(*, applied: bool, reason: str | None = None) -> LocalProcessResult:
    return LocalProcessResult(
        status="completed",
        returncode=0,
        stdout="ok",
        stderr="",
        timed_out=False,
        sandbox_applied=applied,
        degradation_reason=reason,
        cleanup_status="succeeded",
    )


def test_sandbox_surface_activates_before_backend_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch = SimpleNamespace(agent_id="codex-local")
    runtime = SimpleNamespace(version="0.0.77")
    audit = SimpleNamespace(record=lambda _event: None)
    activation = SimpleNamespace(
        launch=launch,
        runtime=runtime,
        audit_port=audit,
        audit_event={"routing_context_digest": "1" * 64},
    )
    seen = {}
    monkeypatch.setattr(surfaces, "activate_sandbox", lambda **_kwargs: activation)

    def fake_backend(request):
        seen["request"] = request
        return _result(applied=True)

    monkeypatch.setattr(surfaces, "run_local_process", fake_backend)
    invocation = VendorProcessInvocation(
        surface="review",
        argv=("/bin/true",),
        cwd=tmp_path,
        env={"OPENAI_API_KEY": "token"},
        timeout_seconds=1,
        isolation="sandbox",
        activation_context=SimpleNamespace(),  # type: ignore[arg-type]
    )

    result = run_vendor_process(invocation)

    assert result.sandbox_applied is True
    assert seen["request"].sandbox_launch is launch
    assert seen["request"].runtime is runtime
    assert seen["request"].audit_port is audit


def test_partially_prepared_sandbox_invocation_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        surfaces,
        "run_local_process",
        lambda _request: pytest.fail("partial sandbox context must not launch"),
    )
    invocation = VendorProcessInvocation(
        surface="review",
        argv=("/bin/true",),
        cwd=tmp_path,
        env={},
        timeout_seconds=1,
        isolation="sandbox",
        sandbox_launch=SimpleNamespace(),  # type: ignore[arg-type]
    )

    result = run_vendor_process(invocation)

    assert result.status == "prelaunch_enforcement_blocked"
    assert result.degradation_reason == "sandbox_context_incomplete"


def test_permitted_degradation_is_audited_before_unsandboxed_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = []
    audit = SimpleNamespace(record=events.append)
    degraded = SandboxDegradation(
        "runtime_missing",
        audit,
        {"sandbox_applied": False, "degradation_reason": "runtime_missing"},
    )
    monkeypatch.setattr(surfaces, "activate_sandbox", lambda **_kwargs: degraded)
    seen = {}

    def fake_backend(request):
        seen["request"] = request
        assert events
        return _result(applied=False)

    monkeypatch.setattr(surfaces, "run_local_process", fake_backend)
    invocation = VendorProcessInvocation(
        surface="review",
        argv=("/bin/true",),
        cwd=tmp_path,
        env={"OPENAI_API_KEY": "token"},
        timeout_seconds=1,
        isolation="sandbox",
        activation_context=SimpleNamespace(),  # type: ignore[arg-type]
    )

    with pytest.warns(RuntimeWarning, match="runtime_missing"):
        result = run_vendor_process(invocation)

    assert seen["request"].isolation == "none"
    assert result.degradation_reason == "runtime_missing"


@pytest.mark.parametrize(
    ("requested", "applied"),
    [("none", "none"), ("worktree", "worktree")],
)
def test_completed_process_preserves_non_sandbox_applied_isolation(
    tmp_path: Path, requested: str, applied: str,
) -> None:
    invocation = VendorProcessInvocation(
        surface="review",
        argv=("/bin/true",),
        cwd=tmp_path,
        env={},
        timeout_seconds=1,
        isolation=requested,  # type: ignore[arg-type]
    )

    completed = as_completed_process(invocation, _result(applied=False))

    assert completed.sandbox_metadata["requested_isolation"] == requested
    assert completed.sandbox_metadata["applied_isolation"] == applied


def test_completed_process_aliases_routing_context_digest_for_result_contract(
    tmp_path: Path,
) -> None:
    invocation = VendorProcessInvocation(
        surface="review",
        argv=("/bin/true",),
        cwd=tmp_path,
        env={},
        timeout_seconds=1,
        isolation="worktree",
        audit_event={"routing_context_digest": "a" * 64},
    )

    completed = as_completed_process(invocation, _result(applied=False))

    assert completed.sandbox_metadata["routing_digest"] == "a" * 64
