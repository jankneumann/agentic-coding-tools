"""Tests for human escalation pathway and author-agent autonomous response.

Covers Task 3.1 of harness-engineering-features:
  - When reason="max_rounds" or reason="disagreement", the loop produces
    a structured escalation summary via escalation_callback.
  - fix_callback is invoked per round; author-agent responses to "fix"
    findings trigger re-review.
  - Configurable convergence thresholds (blocking_criticalities param).
  - Configurable stall detection window.

Spec scenarios:
  - harness-engineering.1 (converges within limit)
  - harness-engineering.1 (escalates on consensus failure)

Design decisions:
  - D1 (extend convergence_loop.py)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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
from convergence_loop import (
    _is_blocking,
    converge,
    ConvergenceResult,
)
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


# ---------------------------------------------------------------------------
# Escalation callback tests
# ---------------------------------------------------------------------------


class TestEscalationOnMaxRounds:
    """When max_rounds exhausted with unresolved findings, escalation_callback
    is invoked with a structured summary."""

    def test_escalation_callback_called_on_max_rounds(self, tmp_path: Path) -> None:
        """escalation_callback fires when reason='max_rounds'."""
        finding = _make_consensus_finding(1, status="confirmed", criticality="high")

        results_per_round = []
        reports_per_round = []
        # Two rounds: findings decrease to avoid stall detection (5, 3)
        counts = [5, 3]
        for count in counts:
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
        escalation_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=2,
                escalation_callback=escalation_cb,
            )

        assert result.converged is False
        assert result.reason == "max_rounds"
        escalation_cb.assert_called_once()

        # Verify structured summary
        summary = escalation_cb.call_args[0][0]
        assert "reason" in summary
        assert summary["reason"] == "max_rounds"
        assert "unresolved_findings" in summary
        assert "rounds_completed" in summary
        assert "iteration_history" in summary

    def test_escalation_callback_not_called_on_convergence(self, tmp_path: Path) -> None:
        """escalation_callback is NOT invoked when loop converges."""
        results = [
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[]),
        ]
        report = _make_consensus_report(findings=[])

        ctx = _setup_converge([results], [report], tmp_path)
        escalation_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                escalation_callback=escalation_cb,
            )

        assert result.converged is True
        escalation_cb.assert_not_called()


class TestEscalationOnDisagreement:
    """When reason='disagreement', escalation_callback is invoked."""

    def test_escalation_callback_called_on_disagreement(self, tmp_path: Path) -> None:
        """escalation_callback fires when reason='disagreement'."""
        finding = _make_consensus_finding(
            1, status="disagreement", criticality="medium",
        )
        finding.vendor_dispositions = {"vendor_a": "fix", "vendor_b": "accept"}

        results = [
            _make_review_result("vendor_a", success=True, findings=[{
                "id": 1, "type": "bug", "criticality": "medium",
                "description": "Disputed issue", "disposition": "fix",
            }]),
            _make_review_result("vendor_b", success=True, findings=[{
                "id": 1, "type": "bug", "criticality": "medium",
                "description": "Disputed issue", "disposition": "accept",
            }]),
        ]
        report = _make_consensus_report(findings=[finding])

        ctx = _setup_converge([results], [report], tmp_path)
        escalation_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                escalation_callback=escalation_cb,
            )

        assert result.converged is False
        assert result.reason == "disagreement"
        escalation_cb.assert_called_once()

        summary = escalation_cb.call_args[0][0]
        assert summary["reason"] == "disagreement"
        assert len(summary["unresolved_findings"]) >= 1

    def test_escalation_summary_includes_vendor_agreement_rate(self, tmp_path: Path) -> None:
        """Escalation summary includes vendor_agreement_rate."""
        finding = _make_consensus_finding(
            1, status="disagreement", criticality="medium",
        )
        finding.vendor_dispositions = {"vendor_a": "fix", "vendor_b": "accept"}

        results = [
            _make_review_result("vendor_a", success=True, findings=[{
                "id": 1, "type": "bug", "criticality": "medium",
                "description": "Disputed issue", "disposition": "fix",
            }]),
            _make_review_result("vendor_b", success=True, findings=[{
                "id": 1, "type": "bug", "criticality": "medium",
                "description": "Disputed issue", "disposition": "accept",
            }]),
        ]
        report = _make_consensus_report(findings=[finding])

        ctx = _setup_converge([results], [report], tmp_path)
        escalation_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                escalation_callback=escalation_cb,
            )

        summary = escalation_cb.call_args[0][0]
        assert "vendor_agreement_rate" in summary
        assert isinstance(summary["vendor_agreement_rate"], float)


class TestEscalationNotCalledOnStall:
    """escalation_callback also fires on stall (stalled is a non-convergence)."""

    def test_escalation_callback_called_on_stall(self, tmp_path: Path) -> None:
        """Stall is also an escalation-worthy event."""
        results_per_round = []
        reports_per_round = []

        for _ in range(3):
            findings = [
                _make_consensus_finding(i, status="confirmed", criticality="medium")
                for i in range(1, 6)
            ]
            results_per_round.append([
                _make_review_result("vendor_a", success=True, findings=[
                    {"id": i, "type": "bug", "criticality": "medium",
                     "description": f"Bug {i}", "disposition": "fix"}
                    for i in range(1, 6)
                ]),
                _make_review_result("vendor_b", success=True, findings=[
                    {"id": i, "type": "bug", "criticality": "medium",
                     "description": f"Bug {i}", "disposition": "fix"}
                    for i in range(1, 6)
                ]),
            ])
            reports_per_round.append(_make_consensus_report(findings=findings))

        ctx = _setup_converge(results_per_round, reports_per_round, tmp_path)
        escalation_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=5,
                escalation_callback=escalation_cb,
            )

        assert result.reason == "stalled"
        escalation_cb.assert_called_once()
        summary = escalation_cb.call_args[0][0]
        assert summary["reason"] == "stalled"


# ---------------------------------------------------------------------------
# fix_callback per-round invocation tests
# ---------------------------------------------------------------------------


class TestFixCallbackPerRound:
    """fix_callback is invoked per round for blocking findings."""

    def test_fix_callback_invoked_each_round(self, tmp_path: Path) -> None:
        """fix_callback fires once per round that has blocking findings."""
        finding = _make_consensus_finding(1, status="confirmed", criticality="high")

        results_per_round = []
        reports_per_round = []

        # Round 1: blocking finding
        results_per_round.append([
            _make_review_result("vendor_a", success=True, findings=[
                {"id": 1, "type": "bug", "criticality": "high",
                 "description": "Bug", "disposition": "fix"}
            ]),
            _make_review_result("vendor_b", success=True, findings=[
                {"id": 1, "type": "bug", "criticality": "high",
                 "description": "Bug", "disposition": "fix"}
            ]),
        ])
        reports_per_round.append(_make_consensus_report(findings=[finding]))

        # Round 2: no findings, converges
        results_per_round.append([
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[]),
        ])
        reports_per_round.append(_make_consensus_report(findings=[]))

        ctx = _setup_converge(results_per_round, reports_per_round, tmp_path)
        fix_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=3,
                fix_callback=fix_cb,
            )

        assert result.converged is True
        assert result.rounds == 2
        fix_cb.assert_called_once()
        # Verify fix_callback receives blocking findings + worktree path
        blocking_arg = fix_cb.call_args[0][0]
        assert len(blocking_arg) == 1
        assert blocking_arg[0]["agreed_criticality"] == "high"
        assert fix_cb.call_args[0][1] == tmp_path

    def test_fix_callback_called_multiple_rounds(self, tmp_path: Path) -> None:
        """fix_callback is called in each round with blocking findings
        before convergence."""
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

        # Round 2: 1 blocking (decreasing, no stall)
        findings_r2 = [
            _make_consensus_finding(1, status="confirmed", criticality="high")
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
        fix_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=5,
                fix_callback=fix_cb,
            )

        assert result.converged is True
        assert result.rounds == 3
        assert fix_cb.call_count == 2


# ---------------------------------------------------------------------------
# Configurable blocking criticalities
# ---------------------------------------------------------------------------


class TestConfigurableBlockingCriticalities:
    """blocking_criticalities param controls which findings are blocking."""

    def test_default_blocking_criticalities(self) -> None:
        """Default: medium, high, critical are blocking."""
        assert _is_blocking(
            {"status": "confirmed", "agreed_criticality": "medium"}
        ) is True
        assert _is_blocking(
            {"status": "confirmed", "agreed_criticality": "low"}
        ) is False

    def test_custom_blocking_criticalities_high_only(self, tmp_path: Path) -> None:
        """Only high/critical treated as blocking when custom set provided."""
        finding = _make_consensus_finding(
            1, status="confirmed", criticality="medium",
        )

        results = [
            _make_review_result("vendor_a", success=True, findings=[
                {"id": 1, "type": "bug", "criticality": "medium",
                 "description": "Medium bug", "disposition": "fix"}
            ]),
            _make_review_result("vendor_b", success=True, findings=[
                {"id": 1, "type": "bug", "criticality": "medium",
                 "description": "Medium bug", "disposition": "fix"}
            ]),
        ]
        report = _make_consensus_report(findings=[finding])

        ctx = _setup_converge([results], [report], tmp_path)

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                blocking_criticalities={"high", "critical"},
            )

        # Medium is no longer blocking with custom set
        assert result.converged is True
        assert result.rounds == 1

    def test_custom_blocking_includes_low(self, tmp_path: Path) -> None:
        """When 'low' is in blocking_criticalities, low findings block."""
        finding = _make_consensus_finding(
            1, status="confirmed", criticality="low",
        )

        results_per_round = []
        reports_per_round = []

        # Round 1: low finding blocks
        results_per_round.append([
            _make_review_result("vendor_a", success=True, findings=[
                {"id": 1, "type": "style", "criticality": "low",
                 "description": "Style nit", "disposition": "fix"}
            ]),
            _make_review_result("vendor_b", success=True, findings=[
                {"id": 1, "type": "style", "criticality": "low",
                 "description": "Style nit", "disposition": "fix"}
            ]),
        ])
        reports_per_round.append(_make_consensus_report(findings=[finding]))

        # Round 2: converges
        results_per_round.append([
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[]),
        ])
        reports_per_round.append(_make_consensus_report(findings=[]))

        ctx = _setup_converge(results_per_round, reports_per_round, tmp_path)
        fix_cb = MagicMock()

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                blocking_criticalities={"low", "medium", "high", "critical"},
                fix_callback=fix_cb,
            )

        # Low finding was blocking, fix_callback called
        assert fix_cb.call_count == 1
        assert result.converged is True
        assert result.rounds == 2


# ---------------------------------------------------------------------------
# Configurable stall window
# ---------------------------------------------------------------------------


class TestConfigurableStallWindow:
    """stall_window parameter controls the stall detection window size."""

    def test_default_stall_window_3(self, tmp_path: Path) -> None:
        """Default 3-point stall detection: [5, 5, 5] stalls at round 3."""
        results_per_round = []
        reports_per_round = []

        for _ in range(3):
            findings = [
                _make_consensus_finding(i, status="confirmed", criticality="medium")
                for i in range(1, 6)
            ]
            results_per_round.append([
                _make_review_result("vendor_a", success=True, findings=[
                    {"id": i, "type": "bug", "criticality": "medium",
                     "description": f"Bug {i}", "disposition": "fix"}
                    for i in range(1, 6)
                ]),
                _make_review_result("vendor_b", success=True, findings=[
                    {"id": i, "type": "bug", "criticality": "medium",
                     "description": f"Bug {i}", "disposition": "fix"}
                    for i in range(1, 6)
                ]),
            ])
            reports_per_round.append(_make_consensus_report(findings=findings))

        ctx = _setup_converge(results_per_round, reports_per_round, tmp_path)

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=5,
            )

        assert result.reason == "stalled"
        assert result.rounds == 3

    def test_stall_window_5_delays_detection(self, tmp_path: Path) -> None:
        """With stall_window=5, stall is not detected until 5 rounds of
        data points exist with no improvement."""
        results_per_round = []
        reports_per_round = []

        # 4 rounds of constant findings - should NOT stall with window=5
        for _ in range(4):
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

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=4,
                stall_window=5,
            )

        # With window=5, 4 rounds is not enough data to detect stall
        assert result.reason == "max_rounds"

    def test_stall_window_2_detects_earlier(self, tmp_path: Path) -> None:
        """With stall_window=2, stall detected at round 2 for constant findings."""
        results_per_round = []
        reports_per_round = []

        for _ in range(2):
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

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=5,
                stall_window=2,
            )

        assert result.reason == "stalled"
        assert result.rounds == 2


# ---------------------------------------------------------------------------
# Backward compatibility: no escalation_callback = current behavior
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """All new parameters default to current behavior."""

    def test_no_escalation_callback_still_works(self, tmp_path: Path) -> None:
        """Without escalation_callback, max_rounds exits as before."""
        finding = _make_consensus_finding(1, status="confirmed", criticality="high")
        results_per_round = []
        reports_per_round = []

        # 2 rounds decreasing to avoid stall
        for count in [3, 2]:
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

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=2,
                # No escalation_callback
            )

        assert result.converged is False
        assert result.reason == "max_rounds"

    def test_default_blocking_criticalities_unchanged(self) -> None:
        """Default blocking criticalities are medium, high, critical."""
        # These match the existing _BLOCKING_CRITICALITIES set
        assert _is_blocking(
            {"status": "confirmed", "agreed_criticality": "medium"},
        ) is True
        assert _is_blocking(
            {"status": "confirmed", "agreed_criticality": "high"},
        ) is True
        assert _is_blocking(
            {"status": "confirmed", "agreed_criticality": "critical"},
        ) is True
        assert _is_blocking(
            {"status": "confirmed", "agreed_criticality": "low"},
        ) is False
