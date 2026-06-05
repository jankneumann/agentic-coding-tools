"""Tests for convergence metrics recording via memory_callback.

Covers Task 3.3 of harness-engineering-features:
  - After converge() completes, memory_callback is invoked with structured
    metrics JSON (in addition to per-round summary strings).
  - Metrics include: rounds_completed, findings_per_round, convergence_status,
    total_time_seconds, vendor_agreement_rate, escalation_count.
  - Metrics follow capability-gap tag schema: failure_type, capability_gap,
    source.

Spec scenarios:
  - harness-engineering.1 (records convergence metrics)

Design decisions:
  - D4 (failure metadata as episodic memory tags)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Ensure the convergence_loop module can find its dependencies
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
_PARALLEL_DIR = str(
    Path(__file__).resolve().parent.parent.parent
    / "parallel-infrastructure"
    / "scripts"
)
for p in (_SCRIPTS_DIR, _PARALLEL_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from consensus_synthesizer import (
    ConsensusFinding,
    ConsensusReport,
    ConsensusSynthesizer,
)
from convergence_loop import converge, ConvergenceResult
from review_dispatcher import ReviewResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_review_result(
    vendor: str,
    success: bool = True,
    findings: list[dict] | None = None,
) -> ReviewResult:
    """Create a ReviewResult with optional findings."""
    findings_dict = None
    if findings is not None:
        findings_dict = {"findings": findings}
    return ReviewResult(
        vendor=vendor,
        success=success,
        findings=findings_dict,
        model_used="test-model",
        models_attempted=["test-model"],
        elapsed_seconds=1.0,
    )


def _make_consensus_finding(
    id: int,
    status: str = "confirmed",
    criticality: str = "medium",
    disposition: str = "fix",
) -> ConsensusFinding:
    """Create a ConsensusFinding."""
    return ConsensusFinding(
        id=id,
        status=status,
        primary_vendor="vendor_a",
        primary_finding_id=id,
        matched_findings=[],
        match_score=0.9,
        agreed_type="bug",
        agreed_criticality=criticality,
        recommended_disposition=disposition,
        description=f"Test finding {id}",
    )


def _make_consensus_report(
    findings: list[ConsensusFinding] | None = None,
    quorum_met: bool = True,
) -> ConsensusReport:
    """Create a ConsensusReport."""
    findings = findings or []
    confirmed = sum(1 for f in findings if f.status == "confirmed")
    unconfirmed = sum(1 for f in findings if f.status == "unconfirmed")
    disagreement = sum(1 for f in findings if f.status == "disagreement")
    return ConsensusReport(
        review_type="implementation",
        target="test-change",
        reviewers=[
            {"vendor": "vendor_a", "agent_id": "vendor_a", "success": True,
             "findings_count": 0, "elapsed_seconds": 1.0, "error": None},
            {"vendor": "vendor_b", "agent_id": "vendor_b", "success": True,
             "findings_count": 0, "elapsed_seconds": 1.0, "error": None},
        ],
        quorum_met=quorum_met,
        quorum_requested=2,
        quorum_received=2,
        consensus_findings=findings,
        total_unique=len(findings),
        confirmed_count=confirmed,
        unconfirmed_count=unconfirmed,
        disagreement_count=disagreement,
        blocking_count=0,
    )


def _setup_converge(
    review_results_per_round: list[list[ReviewResult]],
    consensus_reports_per_round: list[ConsensusReport],
    tmp_path: Path,
) -> dict:
    """Set up mocks for a converge() call and return them."""
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()

    mock_orchestrator = MagicMock()
    mock_orchestrator.dispatch_and_wait.side_effect = review_results_per_round

    mock_synthesizer = MagicMock()
    mock_synthesizer.synthesize.side_effect = consensus_reports_per_round

    real_synth_for_dict = ConsensusSynthesizer()
    to_dict_returns = [
        real_synth_for_dict.to_dict(r) for r in consensus_reports_per_round
    ]
    mock_synthesizer.to_dict.side_effect = to_dict_returns

    return {
        "artifacts_dir": artifacts_dir,
        "orchestrator": mock_orchestrator,
        "synthesizer": mock_synthesizer,
        "to_dict_returns": to_dict_returns,
    }


def _extract_final_metrics_call(memory_cb: MagicMock) -> dict | None:
    """Extract the final (metrics) call from memory_callback.

    The final call is expected to be a JSON string with structured metrics.
    Per-round calls are plain text summary strings.
    """
    for c in memory_cb.call_args_list:
        arg = c[0][0]
        if isinstance(arg, str):
            try:
                parsed = json.loads(arg)
                if isinstance(parsed, dict) and "convergence_status" in parsed:
                    return parsed
            except (json.JSONDecodeError, TypeError):
                continue
    return None


# ---------------------------------------------------------------------------
# Tests: metrics recording on convergence
# ---------------------------------------------------------------------------


class TestMetricsOnConvergence:
    """After converge() completes successfully, memory_callback receives
    structured metrics."""

    def test_metrics_emitted_on_convergence(self, tmp_path: Path) -> None:
        """memory_callback called with structured JSON metrics after convergence."""
        results = [
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[]),
        ]
        report = _make_consensus_report(findings=[])

        ctx = _setup_converge([results], [report], tmp_path)
        memory_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                memory_callback=memory_cb,
            )

        assert result.converged is True
        metrics = _extract_final_metrics_call(memory_cb)
        assert metrics is not None, "Expected structured metrics call"
        assert metrics["convergence_status"] == "converged"
        assert metrics["rounds_completed"] == 1

    def test_metrics_include_all_required_fields(self, tmp_path: Path) -> None:
        """All required metric fields are present."""
        results = [
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[]),
        ]
        report = _make_consensus_report(findings=[])

        ctx = _setup_converge([results], [report], tmp_path)
        memory_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                memory_callback=memory_cb,
            )

        metrics = _extract_final_metrics_call(memory_cb)
        assert metrics is not None
        # All required fields
        assert "rounds_completed" in metrics
        assert "findings_per_round" in metrics
        assert isinstance(metrics["findings_per_round"], list)
        assert "convergence_status" in metrics
        assert "total_time_seconds" in metrics
        assert isinstance(metrics["total_time_seconds"], (int, float))
        assert "vendor_agreement_rate" in metrics
        assert isinstance(metrics["vendor_agreement_rate"], float)
        assert "escalation_count" in metrics
        assert isinstance(metrics["escalation_count"], int)

    def test_findings_per_round_tracks_counts(self, tmp_path: Path) -> None:
        """findings_per_round tracks blocking findings per round."""
        results_per_round = []
        reports_per_round = []

        # Round 1: 3 blocking
        findings_r1 = [
            _make_consensus_finding(i, status="confirmed", criticality="high")
            for i in range(1, 4)
        ]
        results_per_round.append([
            _make_review_result("vendor_a", success=True, findings=[
                {"id": i, "type": "bug", "criticality": "high",
                 "description": f"Bug {i}", "disposition": "fix"}
                for i in range(1, 4)
            ]),
            _make_review_result("vendor_b", success=True, findings=[
                {"id": i, "type": "bug", "criticality": "high",
                 "description": f"Bug {i}", "disposition": "fix"}
                for i in range(1, 4)
            ]),
        ])
        reports_per_round.append(_make_consensus_report(findings=findings_r1))

        # Round 2: 1 blocking
        findings_r2 = [
            _make_consensus_finding(1, status="confirmed", criticality="high"),
        ]
        results_per_round.append([
            _make_review_result("vendor_a", success=True, findings=[
                {"id": 1, "type": "bug", "criticality": "high",
                 "description": "Bug 1", "disposition": "fix"}
            ]),
            _make_review_result("vendor_b", success=True, findings=[
                {"id": 1, "type": "bug", "criticality": "high",
                 "description": "Bug 1", "disposition": "fix"}
            ]),
        ])
        reports_per_round.append(_make_consensus_report(findings=findings_r2))

        # Round 3: 0 findings, converges
        results_per_round.append([
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[]),
        ])
        reports_per_round.append(_make_consensus_report(findings=[]))

        ctx = _setup_converge(results_per_round, reports_per_round, tmp_path)
        memory_cb = MagicMock()
        fix_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=5,
                memory_callback=memory_cb,
                fix_callback=fix_cb,
            )

        assert result.converged is True
        metrics = _extract_final_metrics_call(memory_cb)
        assert metrics is not None
        assert metrics["findings_per_round"] == [3, 1, 0]
        assert metrics["rounds_completed"] == 3


class TestMetricsOnNonConvergence:
    """Metrics are emitted even when the loop does NOT converge."""

    def test_metrics_emitted_on_max_rounds(self, tmp_path: Path) -> None:
        """Metrics emitted with convergence_status='max_rounds'."""
        results_per_round = []
        reports_per_round = []

        for count in [5, 3]:
            findings = [
                _make_consensus_finding(i, status="confirmed", criticality="high")
                for i in range(1, count + 1)
            ]
            results_per_round.append([
                _make_review_result("vendor_a", success=True, findings=[
                    {"id": i, "type": "bug", "criticality": "high",
                     "description": f"Bug {i}", "disposition": "fix"}
                    for i in range(1, count + 1)
                ]),
                _make_review_result("vendor_b", success=True, findings=[
                    {"id": i, "type": "bug", "criticality": "high",
                     "description": f"Bug {i}", "disposition": "fix"}
                    for i in range(1, count + 1)
                ]),
            ])
            reports_per_round.append(_make_consensus_report(findings=findings))

        ctx = _setup_converge(results_per_round, reports_per_round, tmp_path)
        memory_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=2,
                memory_callback=memory_cb,
            )

        assert result.converged is False
        metrics = _extract_final_metrics_call(memory_cb)
        assert metrics is not None
        assert metrics["convergence_status"] == "max_rounds"
        assert metrics["rounds_completed"] == 2

    def test_metrics_emitted_on_stalled(self, tmp_path: Path) -> None:
        """Metrics emitted with convergence_status='stalled'."""
        results_per_round = []
        reports_per_round = []

        for _ in range(3):
            findings = [
                _make_consensus_finding(i, status="confirmed", criticality="medium")
                for i in range(1, 4)
            ]
            results_per_round.append([
                _make_review_result("vendor_a", success=True, findings=[
                    {"id": i, "type": "bug", "criticality": "medium",
                     "description": f"Bug {i}", "disposition": "fix"}
                    for i in range(1, 4)
                ]),
                _make_review_result("vendor_b", success=True, findings=[
                    {"id": i, "type": "bug", "criticality": "medium",
                     "description": f"Bug {i}", "disposition": "fix"}
                    for i in range(1, 4)
                ]),
            ])
            reports_per_round.append(_make_consensus_report(findings=findings))

        ctx = _setup_converge(results_per_round, reports_per_round, tmp_path)
        memory_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=5,
                memory_callback=memory_cb,
            )

        assert result.reason == "stalled"
        metrics = _extract_final_metrics_call(memory_cb)
        assert metrics is not None
        assert metrics["convergence_status"] == "stalled"

    def test_metrics_emitted_on_disagreement(self, tmp_path: Path) -> None:
        """Metrics emitted with convergence_status='escalated' on disagreement."""
        finding = _make_consensus_finding(
            1, status="disagreement", criticality="medium",
        )
        finding.vendor_dispositions = {"vendor_a": "fix", "vendor_b": "accept"}

        results = [
            _make_review_result("vendor_a", success=True, findings=[{
                "id": 1, "type": "bug", "criticality": "medium",
                "description": "Disputed", "disposition": "fix",
            }]),
            _make_review_result("vendor_b", success=True, findings=[{
                "id": 1, "type": "bug", "criticality": "medium",
                "description": "Disputed", "disposition": "accept",
            }]),
        ]
        report = _make_consensus_report(findings=[finding])

        ctx = _setup_converge([results], [report], tmp_path)
        memory_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                memory_callback=memory_cb,
            )

        assert result.reason == "disagreement"
        metrics = _extract_final_metrics_call(memory_cb)
        assert metrics is not None
        assert metrics["convergence_status"] == "escalated"
        assert metrics["escalation_count"] >= 1


class TestMetricsCapabilityGapSchema:
    """Metrics follow the capability-gap tag schema when convergence fails."""

    def test_failed_convergence_includes_failure_type(self, tmp_path: Path) -> None:
        """Non-convergence metrics include failure_type:convergence_failed."""
        results_per_round = []
        reports_per_round = []

        for count in [5, 3]:
            findings = [
                _make_consensus_finding(i, status="confirmed", criticality="high")
                for i in range(1, count + 1)
            ]
            results_per_round.append([
                _make_review_result("vendor_a", success=True, findings=[
                    {"id": i, "type": "bug", "criticality": "high",
                     "description": f"Bug {i}", "disposition": "fix"}
                    for i in range(1, count + 1)
                ]),
                _make_review_result("vendor_b", success=True, findings=[
                    {"id": i, "type": "bug", "criticality": "high",
                     "description": f"Bug {i}", "disposition": "fix"}
                    for i in range(1, count + 1)
                ]),
            ])
            reports_per_round.append(_make_consensus_report(findings=findings))

        ctx = _setup_converge(results_per_round, reports_per_round, tmp_path)
        memory_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=2,
                memory_callback=memory_cb,
            )

        metrics = _extract_final_metrics_call(memory_cb)
        assert metrics is not None
        assert metrics.get("failure_type") == "convergence_failed"
        assert "capability_gap" in metrics
        assert metrics.get("source") == "self-reported"

    def test_converged_does_not_include_failure_type(self, tmp_path: Path) -> None:
        """Successful convergence metrics do NOT have failure_type."""
        results = [
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[]),
        ]
        report = _make_consensus_report(findings=[])

        ctx = _setup_converge([results], [report], tmp_path)
        memory_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                memory_callback=memory_cb,
            )

        metrics = _extract_final_metrics_call(memory_cb)
        assert metrics is not None
        # Successful convergence has no failure_type
        assert "failure_type" not in metrics


class TestMetricsVendorAgreementRate:
    """Vendor agreement rate is computed correctly."""

    def test_full_agreement_rate_1(self, tmp_path: Path) -> None:
        """When all multi-vendor findings are confirmed, rate = 1.0."""
        finding = _make_consensus_finding(1, status="confirmed", criticality="high")

        results_per_round = [
            [
                _make_review_result("vendor_a", success=True, findings=[
                    {"id": 1, "type": "bug", "criticality": "high",
                     "description": "Bug", "disposition": "fix"}
                ]),
                _make_review_result("vendor_b", success=True, findings=[
                    {"id": 1, "type": "bug", "criticality": "high",
                     "description": "Bug", "disposition": "fix"}
                ]),
            ],
            [
                _make_review_result("vendor_a", success=True, findings=[]),
                _make_review_result("vendor_b", success=True, findings=[]),
            ],
        ]
        reports_per_round = [
            _make_consensus_report(findings=[finding]),
            _make_consensus_report(findings=[]),
        ]

        ctx = _setup_converge(results_per_round, reports_per_round, tmp_path)
        memory_cb = MagicMock()
        fix_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                memory_callback=memory_cb,
                fix_callback=fix_cb,
            )

        metrics = _extract_final_metrics_call(memory_cb)
        assert metrics is not None
        assert metrics["vendor_agreement_rate"] == 1.0

    def test_no_agreement_rate_0(self, tmp_path: Path) -> None:
        """When all multi-vendor findings disagree, rate = 0.0."""
        finding = _make_consensus_finding(
            1, status="disagreement", criticality="medium",
        )
        finding.vendor_dispositions = {"vendor_a": "fix", "vendor_b": "accept"}

        results = [
            _make_review_result("vendor_a", success=True, findings=[{
                "id": 1, "type": "bug", "criticality": "medium",
                "description": "Disputed", "disposition": "fix",
            }]),
            _make_review_result("vendor_b", success=True, findings=[{
                "id": 1, "type": "bug", "criticality": "medium",
                "description": "Disputed", "disposition": "accept",
            }]),
        ]
        report = _make_consensus_report(findings=[finding])

        ctx = _setup_converge([results], [report], tmp_path)
        memory_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                memory_callback=memory_cb,
            )

        metrics = _extract_final_metrics_call(memory_cb)
        assert metrics is not None
        assert metrics["vendor_agreement_rate"] == 0.0


class TestMetricsTimeElapsed:
    """total_time_seconds is a non-negative float."""

    def test_time_is_nonnegative(self, tmp_path: Path) -> None:
        results = [
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[]),
        ]
        report = _make_consensus_report(findings=[])

        ctx = _setup_converge([results], [report], tmp_path)
        memory_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                memory_callback=memory_cb,
            )

        metrics = _extract_final_metrics_call(memory_cb)
        assert metrics is not None
        assert metrics["total_time_seconds"] >= 0


class TestNoMemoryCallbackNoError:
    """Without memory_callback, no error is raised and no metrics emitted."""

    def test_no_callback_no_error(self, tmp_path: Path) -> None:
        results = [
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[]),
        ]
        report = _make_consensus_report(findings=[])

        ctx = _setup_converge([results], [report], tmp_path)

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                # No memory_callback
            )

        assert result.converged is True
