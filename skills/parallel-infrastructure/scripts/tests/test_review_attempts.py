"""Characterization tests for the review-attempt core contract."""

from __future__ import annotations

import sys
import subprocess
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from review_attempts import (  # noqa: E402
    run_vendor_recovery,
    sanitize_diagnostic,
    select_replacement_vendor,
    validate_review_attempt_chain,
)
from review_result_policy import is_quorum_eligible, quorum_summary  # noqa: E402


def _attempt(
    index: int,
    *,
    vendor: str = "alpha",
    model: str = "primary",
    reason: str = "initial",
    terminal: bool = False,
    success: bool = False,
    error_class: str | None = "invalid_output",
) -> dict[str, object]:
    return {
        "attempt_index": index,
        "vendor": vendor,
        "transport": "cli",
        "reason": reason,
        "terminal": terminal,
        "success": success,
        "elapsed_seconds": 0.1,
        "parser_stage": "schema" if success else "json",
        "validation_status": "schema_valid" if success else "invalid",
        "error_class": None if success else error_class,
        "error_detail": None if success else "malformed result",
        "stdout_excerpt": None,
        "stderr_excerpt": None,
        "diagnostics_truncated": False,
        "resolved_execution": {
            "model": model,
            "requested_thinking": None,
            "applied_thinking": None,
            "thinking_translation": "not_requested",
            "fallback_reason": None,
        },
    }


def _chain(attempts: list[dict[str, object]]) -> dict[str, object]:
    terminal = attempts[-1]
    success = bool(terminal["success"])
    return {
        "logical_request_id": "round-1-alpha",
        "requested_vendor": "alpha",
        "requested_routing": {
            "archetype": "reviewer",
            "tier": "premium",
            "phase": "review",
            "source": "test",
            "fallback_reason": None,
        },
        "deadline_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
        "budget": {"corrective_max": 1, "replacement_max": 1, "fallback_models": ["fallback"]},
        "attempts": attempts,
        "terminal_outcome": "success" if success else "invalid_output_exhausted",
        "terminal_vendor": terminal["vendor"] if success else "alpha",
        "quorum_eligible": success,
    }


def test_invalid_output_uses_one_corrective_then_fallback() -> None:
    outcomes = iter([
        {"validation_status": "invalid", "error_detail": "not json", "stdout": "not json"},
        {"validation_status": "invalid", "error_detail": "still not json"},
        {"validation_status": "schema_valid", "findings": []},
    ])

    result = run_vendor_recovery(
        logical_request_id="round-1-alpha",
        vendor="alpha",
        primary_model="primary",
        fallback_models=["fallback", "fallback"],
        invoke=lambda *_args: next(outcomes),
        timeout_seconds=60,
    )

    assert [a["reason"] for a in result["attempts"]] == [
        "initial", "corrective_redispatch", "model_fallback",
    ]
    assert [a["resolved_execution"]["model"] for a in result["attempts"]] == [
        "primary", "primary", "fallback",
    ]
    assert result["terminal_outcome"] == "success"
    assert is_quorum_eligible(result)


def test_capacity_skips_corrective_and_auth_is_terminal() -> None:
    capacity = iter([
        {"error_class": "capacity_exhausted", "error_detail": "full"},
        {"validation_status": "schema_valid", "findings": []},
    ])
    result = run_vendor_recovery(
        logical_request_id="capacity", vendor="alpha", primary_model="primary",
        fallback_models=["fallback"], invoke=lambda *_args: next(capacity), timeout_seconds=60,
    )
    assert [a["reason"] for a in result["attempts"]] == ["initial", "model_fallback"]

    auth = run_vendor_recovery(
        logical_request_id="auth", vendor="alpha", primary_model="primary",
        fallback_models=["fallback"],
        invoke=lambda *_args: {"error_class": "auth", "error_detail": "expired"}, timeout_seconds=60,
    )
    assert len(auth["attempts"]) == 1
    assert auth["terminal_outcome"] == "auth"


def test_validator_fails_closed_for_bad_indexes_and_after_success() -> None:
    bad = _chain([_attempt(2, terminal=True)])
    with pytest.raises(ValueError, match="indexes"):
        validate_review_attempt_chain(bad)

    success = _attempt(1, terminal=False, success=True, error_class=None)
    trailing = _attempt(2, terminal=True)
    with pytest.raises(ValueError, match="schema"):
        validate_review_attempt_chain(_chain([success, trailing]))


def test_validator_applies_schema_and_rejects_illegal_transitions() -> None:
    second_initial = _attempt(2, reason="initial", terminal=True)
    with pytest.raises(ValueError, match="schema"):
        validate_review_attempt_chain(_chain([_attempt(1), second_initial]))

    fallback = _attempt(2, reason="model_fallback", model="fallback")
    late_corrective = _attempt(3, reason="corrective_redispatch", terminal=True)
    with pytest.raises(ValueError, match="corrective"):
        validate_review_attempt_chain(_chain([_attempt(1), fallback, late_corrective]))


def test_quorum_requires_valid_terminal_routing_but_accepts_empty_findings() -> None:
    valid = _chain([_attempt(1, terminal=True, success=True, error_class=None)])
    assert is_quorum_eligible(valid)
    invalid = dict(valid, terminal_vendor="other")
    assert not is_quorum_eligible(invalid)
    assert quorum_summary([valid, invalid], minimum_required=1) == {
        "requested": 2, "received": 1, "minimum_required": 1, "met": True,
    }


def test_replacement_is_config_ordered_and_never_already_dispatched() -> None:
    assert select_replacement_vendor(
        ["alpha", "beta", "gamma"], dispatched_vendors={"alpha", "beta"}
    ) == "gamma"
    assert select_replacement_vendor(["alpha", "beta"], dispatched_vendors={"alpha", "beta"}) is None


def test_success_after_logical_deadline_is_terminal_timeout() -> None:
    calls = 0

    def now() -> float:
        nonlocal calls
        calls += 1
        return 0.0 if calls <= 3 else 2.0

    result = run_vendor_recovery(
        logical_request_id="timeout", vendor="alpha", primary_model="primary",
        fallback_models=[], timeout_seconds=1,
        invoke=lambda *_args: {"validation_status": "schema_valid", "findings": []},
        now=now,
    )

    assert result["terminal_outcome"] == "timeout"
    assert result["quorum_eligible"] is False


def test_diagnostics_redact_and_bound_sensitive_output() -> None:
    text, truncated = sanitize_diagnostic("token=sk-super-secret Bearer abcdefghijklmnop", limit=20)
    assert "super-secret" not in text
    assert "abcdefghijklmnop" not in text
    assert truncated


def test_error_detail_is_redacted_and_contributes_to_diagnostic_truncation() -> None:
    result = run_vendor_recovery(
        logical_request_id="redacted-error", vendor="alpha", primary_model="primary",
        fallback_models=[], timeout_seconds=60,
        invoke=lambda *_args: {
            "error_class": "auth",
            "error_detail": "token=sk-super-secret " + ("x" * 5000),
        },
    )

    attempt = result["attempts"][0]
    assert "super-secret" not in attempt["error_detail"]
    assert len(attempt["error_detail"]) <= 4096
    assert attempt["diagnostics_truncated"] is True


def test_blocking_invoke_cannot_hold_recovery_past_remaining_deadline() -> None:
    started = time.monotonic()
    result = run_vendor_recovery(
        logical_request_id="blocking", vendor="alpha", primary_model="primary",
        fallback_models=[], timeout_seconds=0.05,
        invoke=lambda *_args: (time.sleep(0.25) or {"validation_status": "schema_valid"}),
    )

    assert time.monotonic() - started < 0.15
    assert result["terminal_outcome"] == "timeout"
    assert result["quorum_eligible"] is False
    assert not any(thread.name == "review-attempt-invoke" for thread in threading.enumerate())


def test_worker_thread_rejects_unmanaged_invocation_without_forking() -> None:
    observed: dict[str, object] = {}
    gate = threading.Lock()
    gate.acquire()
    invoked = threading.Event()

    def unsafe_invoke(*_args: object) -> dict[str, object]:
        invoked.set()
        with gate:
            return {"validation_status": "schema_valid"}

    def run() -> None:
        started = time.monotonic()
        observed["result"] = run_vendor_recovery(
            logical_request_id="worker-blocking",
            vendor="alpha",
            primary_model="primary",
            fallback_models=[],
            timeout_seconds=0.3,
            invoke=unsafe_invoke,
        )
        observed["elapsed"] = time.monotonic() - started

    worker = threading.Thread(target=run, name="review-recovery-caller")
    worker.start()
    worker.join(timeout=0.15)
    gate.release()

    assert not worker.is_alive()
    assert float(observed["elapsed"]) < 0.15
    assert observed["result"]["terminal_outcome"] == "configuration"
    assert not invoked.is_set()


def test_worker_thread_receives_large_response_without_false_timeout() -> None:
    observed: dict[str, object] = {}

    def run() -> None:
        observed["result"] = run_vendor_recovery(
            logical_request_id="worker-large-response",
            vendor="alpha",
            primary_model="primary",
            fallback_models=[],
            timeout_seconds=1,
            invoke_owns_deadline=True,
            invoke=lambda *_args: {
                "validation_status": "schema_valid",
                "stdout": "x" * (128 * 1024),
            },
        )

    worker = threading.Thread(target=run, name="review-large-response-caller")
    worker.start()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert observed["result"]["terminal_outcome"] == "success"


def test_worker_thread_unmanaged_invocation_cannot_spawn_descendant(tmp_path: Path) -> None:
    pid_file = tmp_path / "descendant.pid"
    observed: dict[str, object] = {}

    def invoke(*_args: object) -> dict[str, object]:
        child = subprocess.Popen([
            sys.executable,
            "-c",
            "import time; time.sleep(10)",
        ])
        pid_file.write_text(str(child.pid), encoding="utf-8")
        time.sleep(10)
        return {"validation_status": "schema_valid"}

    def run() -> None:
        observed["result"] = run_vendor_recovery(
            logical_request_id="worker-descendant",
            vendor="alpha",
            primary_model="primary",
            fallback_models=[],
            timeout_seconds=0.2,
            invoke=invoke,
        )

    worker = threading.Thread(target=run, name="review-descendant-caller")
    worker.start()
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert observed["result"]["terminal_outcome"] == "configuration"
    assert not pid_file.exists()


@pytest.mark.parametrize("terminal_class", ["transient", "timeout", "configuration", "unknown", "auth"])
def test_nonrecoverable_fallback_failure_stops_chain(terminal_class: str) -> None:
    outcomes = iter([
        {"error_class": "capacity_exhausted"},
        {"error_class": terminal_class},
        {"validation_status": "schema_valid"},
    ])
    result = run_vendor_recovery(
        logical_request_id="terminal-fallback", vendor="alpha", primary_model="primary",
        fallback_models=["fallback", "unused"], invoke=lambda *_args: next(outcomes),
        timeout_seconds=10,
    )
    assert len(result["attempts"]) == 2
    assert result["terminal_outcome"] == terminal_class


def test_copied_install_uses_portable_review_attempt_schema(tmp_path: Path) -> None:
    scripts = tmp_path / "parallel-infrastructure" / "scripts"
    assets = tmp_path / "parallel-infrastructure" / "install_assets" / "openspec" / "schemas"
    scripts.mkdir(parents=True)
    assets.mkdir(parents=True)
    source = Path(__file__).resolve().parents[1]
    shutil.copy2(source / "review_attempts.py", scripts / "review_attempts.py")
    shutil.copy2(
        source.parent / "install_assets" / "openspec" / "schemas" / "review-attempt.schema.json",
        assets / "review-attempt.schema.json",
    )
    program = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from review_attempts import run_vendor_recovery; "
        "r=run_vendor_recovery(logical_request_id='x',vendor='v',primary_model='m',"
        "fallback_models=[],invoke=lambda *_:{'validation_status':'schema_valid'},timeout_seconds=1); "
        "assert r['terminal_outcome']=='success'"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program, str(scripts)],
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
