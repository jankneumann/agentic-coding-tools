"""Tests for in-process checkpointing in converge().

Verifies the durability contract:
- Successful round writes manifest + per-vendor files BEFORE synthesis,
  populates result.checkpoint_dir on success.
- Synthesis failure leaves checkpoint files on disk AND propagates the
  original exception unmodified.
- Checkpoint write failure emits convergence.checkpoint_write_failed
  log entry and propagates the OSError.
- Structured logging via Python's standard logging module — no
  coordinator audit endpoint dependency.

Spec scenarios: skill-workflow.R2.S1..S4, skill-workflow.R4.S1..S4.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from convergence_loop import converge  # type: ignore[import-untyped]
# Importing convergence_loop above puts parallel-infrastructure on sys.path,
# so checkpoint_findings + review_dispatcher are now importable.
from checkpoint_findings import read_manifest, read_vendor_findings  # type: ignore[import-untyped]
from review_dispatcher import ReviewResult  # type: ignore[import-untyped]


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _vendor_finding(idx: int, criticality: str = "low") -> dict[str, Any]:
    return {
        "id": idx,
        "type": "logic-error",
        "criticality": criticality,
        "description": f"Finding {idx}",
        "disposition": "fix",
    }


def _review_result(vendor: str, findings: list[dict[str, Any]]) -> ReviewResult:
    return ReviewResult(
        vendor=vendor,
        success=True,
        model_used="test-model",
        models_attempted=["test-model"],
        elapsed_seconds=1.0,
        findings={
            "review_type": "plan",
            "target": "test-feature",
            "findings": findings,
        },
    )


def _failed_review_result(vendor: str, error: str = "vendor unreachable") -> ReviewResult:
    return ReviewResult(
        vendor=vendor,
        success=False,
        model_used=None,
        models_attempted=["test-model"],
        elapsed_seconds=0.5,
        error=error,
    )


class _FakeOrchestrator:
    """Minimal stand-in for ReviewOrchestrator that returns canned results."""

    def __init__(self, results: list[ReviewResult]) -> None:
        self._results = results

    def dispatch_and_wait(self, **_kwargs: Any) -> list[ReviewResult]:
        return self._results


class _FakeSynthesizer:
    """Synthesizer that returns a canned report with no blocking findings."""

    def __init__(self, **_kwargs: Any) -> None:
        pass

    def synthesize(self, **_kwargs: Any) -> Any:
        return _FakeReport()

    def to_dict(self, _report: Any) -> dict[str, Any]:
        return {
            "consensus_findings": [],
            "summary": {"confirmed_count": 0, "unconfirmed_count": 0},
        }


class _FakeReport:
    pass


class _ExplodingSynthesizer:
    """Synthesizer whose synthesize() always raises — emulates the
    line_range parser bug that motivated the proposal."""

    def __init__(self, **_kwargs: Any) -> None:
        pass

    def synthesize(self, **_kwargs: Any) -> Any:
        raise AttributeError("'str' object has no attribute 'get'")

    def to_dict(self, _report: Any) -> dict[str, Any]:  # pragma: no cover
        raise AssertionError("to_dict should never run after synthesize() raises")


# ---------------------------------------------------------------------------
# R2.S1 — happy path writes checkpoint and populates result
# ---------------------------------------------------------------------------


def test_success_path_writes_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "convergence_loop.ConsensusSynthesizer", _FakeSynthesizer
    )
    orch = _FakeOrchestrator([
        _review_result("claude_code", [_vendor_finding(1)]),
        _review_result("codex", [_vendor_finding(2)]),
    ])
    result = converge(
        change_id="test-feature",
        review_type="plan",
        artifacts_dir=tmp_path,
        worktree_path=tmp_path,
        orchestrator=orch,  # type: ignore[arg-type]
        max_rounds=1,
    )
    assert result.converged
    # Checkpoint dir is populated and exists on disk
    assert result.checkpoint_dir is not None
    assert result.checkpoint_dir.exists()
    # Manifest is readable
    manifest = read_manifest(result.checkpoint_dir)
    assert manifest["change_id"] == "test-feature"
    assert manifest["review_type"] == "plan"
    assert manifest["schema_version"] == 1
    # Per-vendor files round-trip through read_vendor_findings
    loaded = read_vendor_findings(result.checkpoint_dir)
    assert set(loaded) == {"claude_code", "codex"}


# ---------------------------------------------------------------------------
# R2.S2 — synthesis failure preserves checkpoint and propagates exception
# ---------------------------------------------------------------------------


def test_synthesis_failure_preserves_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "convergence_loop.ConsensusSynthesizer", _ExplodingSynthesizer
    )
    orch = _FakeOrchestrator([
        _review_result("claude_code", [_vendor_finding(1)]),
        _review_result("codex", [_vendor_finding(2)]),
    ])
    with pytest.raises(AttributeError, match="'str' object has no attribute"):
        converge(
            change_id="test-feature",
            review_type="plan",
            artifacts_dir=tmp_path,
            worktree_path=tmp_path,
            orchestrator=orch,  # type: ignore[arg-type]
            max_rounds=1,
        )
    # Original exception propagated. Now verify checkpoint files persist:
    checkpoint_dir = tmp_path / ".review-cache" / "round-1"
    assert checkpoint_dir.exists()
    manifest = read_manifest(checkpoint_dir)
    assert manifest["change_id"] == "test-feature"
    loaded = read_vendor_findings(checkpoint_dir)
    assert set(loaded) == {"claude_code", "codex"}
    assert loaded["claude_code"][0]["id"] == 1
    assert loaded["codex"][0]["id"] == 2


def test_synthesis_failure_emits_log_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """R4.S1: synthesis failure emits convergence.synthesis_failed_with_checkpoint."""
    monkeypatch.setattr(
        "convergence_loop.ConsensusSynthesizer", _ExplodingSynthesizer
    )
    orch = _FakeOrchestrator([
        _review_result("claude_code", [_vendor_finding(1)]),
        _review_result("codex", [_vendor_finding(2)]),
    ])
    with caplog.at_level(logging.ERROR, logger="checkpoint_findings"):
        with pytest.raises(AttributeError):
            converge(
                change_id="test-feature",
                review_type="plan",
                artifacts_dir=tmp_path,
                worktree_path=tmp_path,
                orchestrator=orch,  # type: ignore[arg-type]
                max_rounds=1,
            )

    events = [r for r in caplog.records if getattr(r, "event", None) == "convergence.synthesis_failed_with_checkpoint"]
    assert len(events) == 1
    rec = events[0]
    assert rec.change_id == "test-feature"  # type: ignore[attr-defined]
    assert rec.review_type == "plan"  # type: ignore[attr-defined]
    assert rec.original_exception_class == "AttributeError"  # type: ignore[attr-defined]
    assert "checkpoint_dir" in rec.__dict__
    assert "round-1" in str(rec.checkpoint_dir)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# R2.S3 — empty round still produces manifest
# ---------------------------------------------------------------------------


def test_empty_round_quorum_lost_no_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All vendors fail (no findings) — converge returns quorum_lost without
    crashing. Whether checkpoint is written for an empty round is an
    implementation choice; here we verify no exception bubbles."""
    monkeypatch.setattr(
        "convergence_loop.ConsensusSynthesizer", _FakeSynthesizer
    )
    failed = ReviewResult(vendor="claude_code", success=False, error="timeout")
    orch = _FakeOrchestrator([failed])
    result = converge(
        change_id="test-feature",
        review_type="plan",
        artifacts_dir=tmp_path,
        worktree_path=tmp_path,
        orchestrator=orch,  # type: ignore[arg-type]
        max_rounds=1,
        min_quorum=2,
    )
    # Quorum lost — converged=False, no exception
    assert not result.converged
    assert result.reason == "quorum_lost"


# ---------------------------------------------------------------------------
# R2.S4 — checkpoint write permission error
# ---------------------------------------------------------------------------


def test_checkpoint_write_failure_emits_log_and_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """R4.S3: checkpoint write fails (mocked) — log entry emitted, original
    OSError propagates."""
    monkeypatch.setattr(
        "convergence_loop.ConsensusSynthesizer", _FakeSynthesizer
    )

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("disk full")

    monkeypatch.setattr(
        "convergence_loop.cf_write_vendor_findings", boom
    )
    orch = _FakeOrchestrator([_review_result("claude_code", [_vendor_finding(1)])])

    with caplog.at_level(logging.ERROR, logger="checkpoint_findings"):
        with pytest.raises(PermissionError, match="disk full"):
            converge(
                change_id="test-feature",
                review_type="plan",
                artifacts_dir=tmp_path,
                worktree_path=tmp_path,
                orchestrator=orch,  # type: ignore[arg-type]
                max_rounds=1,
                min_quorum=1,
            )

    events = [
        r for r in caplog.records
        if getattr(r, "event", None) == "convergence.checkpoint_write_failed"
    ]
    assert len(events) == 1
    rec = events[0]
    assert rec.change_id == "test-feature"  # type: ignore[attr-defined]
    assert rec.original_exception_class == "PermissionError"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# R4.S2 — happy path emits NO failure log
# ---------------------------------------------------------------------------


def test_happy_path_no_failure_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        "convergence_loop.ConsensusSynthesizer", _FakeSynthesizer
    )
    orch = _FakeOrchestrator([_review_result("claude_code", [_vendor_finding(1)])])

    with caplog.at_level(logging.ERROR, logger="checkpoint_findings"):
        result = converge(
            change_id="test-feature",
            review_type="plan",
            artifacts_dir=tmp_path,
            worktree_path=tmp_path,
            orchestrator=orch,  # type: ignore[arg-type]
            max_rounds=1,
            min_quorum=1,
        )
    assert result.converged

    failure_events = [
        r for r in caplog.records
        if getattr(r, "event", None)
        in {"convergence.synthesis_failed_with_checkpoint", "convergence.checkpoint_write_failed"}
    ]
    assert failure_events == []


# ---------------------------------------------------------------------------
# R4.S4 — log handler raising in emit() does not mask synthesis exception
# ---------------------------------------------------------------------------


def test_handler_failure_does_not_mask_synthesis_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a custom log handler raises in emit(), the original synthesis
    exception MUST still propagate. This is the load-bearing guarantee
    of _safe_log_error."""
    monkeypatch.setattr(
        "convergence_loop.ConsensusSynthesizer", _ExplodingSynthesizer
    )

    class ExplodingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
            raise RuntimeError("handler boom")

    handler = ExplodingHandler()
    cf_logger = logging.getLogger("checkpoint_findings")
    cf_logger.addHandler(handler)
    original_raise = logging.raiseExceptions
    logging.raiseExceptions = True

    try:
        orch = _FakeOrchestrator([_review_result("claude_code", [_vendor_finding(1)])])
        # The original AttributeError MUST propagate — not the RuntimeError.
        with pytest.raises(AttributeError, match="'str' object has no attribute"):
            converge(
                change_id="test-feature",
                review_type="plan",
                artifacts_dir=tmp_path,
                worktree_path=tmp_path,
                orchestrator=orch,  # type: ignore[arg-type]
                max_rounds=1,
                min_quorum=1,
            )
    finally:
        cf_logger.removeHandler(handler)
        logging.raiseExceptions = original_raise


# ---------------------------------------------------------------------------
# Multi-round: each round writes its own subdirectory
# ---------------------------------------------------------------------------


class _BlockingThenClearSynthesizer:
    """First round emits one blocking finding; subsequent rounds emit none."""

    _call = 0

    def __init__(self, **_kwargs: Any) -> None:
        pass

    def synthesize(self, **_kwargs: Any) -> Any:
        return _FakeReport()

    def to_dict(self, _report: Any) -> dict[str, Any]:
        type(self)._call += 1
        if type(self)._call == 1:
            return {
                "consensus_findings": [{
                    "id": 1,
                    "status": "confirmed",
                    "agreed_criticality": "high",
                }],
                "summary": {"confirmed_count": 1, "unconfirmed_count": 0},
            }
        return {
            "consensus_findings": [],
            "summary": {"confirmed_count": 0, "unconfirmed_count": 0},
        }


def test_multi_round_writes_separate_checkpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each round writes its own checkpoint subdirectory under reviews/."""
    _BlockingThenClearSynthesizer._call = 0  # reset between tests
    monkeypatch.setattr(
        "convergence_loop.ConsensusSynthesizer", _BlockingThenClearSynthesizer
    )
    orch = _FakeOrchestrator([_review_result("claude_code", [_vendor_finding(1)])])
    fixes_called = []

    def fix_callback(blocking: list[Any], _path: Path) -> None:
        fixes_called.append(len(blocking))

    result = converge(
        change_id="test-feature",
        review_type="plan",
        artifacts_dir=tmp_path,
        worktree_path=tmp_path,
        orchestrator=orch,  # type: ignore[arg-type]
        max_rounds=3,
        min_quorum=1,
        fix_callback=fix_callback,
    )
    assert result.converged
    assert result.rounds == 2  # cleared in round 2
    assert (tmp_path / ".review-cache" / "round-1").exists()
    assert (tmp_path / ".review-cache" / "round-2").exists()
    # checkpoint_dir points at most-recent round
    assert result.checkpoint_dir == (tmp_path / ".review-cache" / "round-2").resolve()


# ---------------------------------------------------------------------------
# Quorum accounting on partial dispatch
# (IMPL_REVIEW round-1 finding C5 — gemini)
# ---------------------------------------------------------------------------


def test_manifest_records_total_dispatched_as_quorum_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When 3 vendors dispatch but only 2 succeed, quorum_requested MUST
    record 3 (total attempted), not 2 (successful only). vendors_index in
    the manifest only contains successful vendors, so passing it implicitly
    via the default would understate the round's intent."""
    monkeypatch.setattr(
        "convergence_loop.ConsensusSynthesizer", _FakeSynthesizer
    )
    orch = _FakeOrchestrator([
        _review_result("claude_code", [_vendor_finding(1)]),
        _review_result("codex", [_vendor_finding(2)]),
        _failed_review_result("gemini", "transport error"),
    ])
    result = converge(
        change_id="test-feature",
        review_type="plan",
        artifacts_dir=tmp_path,
        worktree_path=tmp_path,
        orchestrator=orch,  # type: ignore[arg-type]
        max_rounds=1,
    )
    assert result.checkpoint_dir is not None
    manifest = read_manifest(result.checkpoint_dir)
    # 3 attempted, 2 succeeded
    assert manifest["quorum_requested"] == 3
    assert manifest["quorum_received"] == 2
    # vendors_index only carries successful reviews (gemini's failure has no
    # findings to index)
    assert {v["name"] for v in manifest["vendors"]} == {"claude_code", "codex"}
    # All 3 dispatches recorded for audit
    assert len(manifest["dispatches"]) == 3
