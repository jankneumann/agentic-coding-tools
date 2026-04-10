"""Tests for the convergence loop engine."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# Ensure the convergence_loop module can find its dependencies
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
_PARALLEL_DIR = str(
    Path(__file__).resolve().parent.parent.parent.parent
    / "parallel-infrastructure"
    / "scripts"
)
for p in (_SCRIPTS_DIR, _PARALLEL_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from convergence_loop import (
    _is_blocking,
    build_review_prompt,
    converge,
)
from consensus_synthesizer import (
    ConsensusFinding,
    ConsensusReport,
)
from review_dispatcher import ReviewResult


# ---------------------------------------------------------------------------
# Fixtures
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
        reviewers=[],
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

    # Build to_dict return values from reports
    real_synth_for_dict = __import__(
        "consensus_synthesizer", fromlist=["ConsensusSynthesizer"]
    ).ConsensusSynthesizer()
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
# Tests
# ---------------------------------------------------------------------------

class TestConvergenceZeroFindings:
    """2 vendors return empty findings → converged in 1 round."""

    def test_converges_round_1(self, tmp_path: Path) -> None:
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
            )

        assert result.converged is True
        assert result.rounds == 1
        assert result.reason is None


class TestConvergenceQuorumMet:
    """2/3 vendors succeed with 0 medium+ findings → converged."""

    def test_quorum_2_of_3(self, tmp_path: Path) -> None:
        results = [
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[]),
            _make_review_result("vendor_c", success=False),
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
                min_quorum=2,
            )

        assert result.converged is True
        assert result.rounds == 1


class TestQuorumLost:
    """Only 1 vendor succeeds → quorum_lost."""

    def test_quorum_lost(self, tmp_path: Path) -> None:
        results = [
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=False),
        ]

        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()

        mock_orchestrator = MagicMock()
        mock_orchestrator.dispatch_and_wait.return_value = results

        result = converge(
            change_id="test-change",
            review_type="implementation",
            artifacts_dir=artifacts_dir,
            worktree_path=tmp_path,
            orchestrator=mock_orchestrator,
            min_quorum=2,
        )

        assert result.converged is False
        assert result.reason == "quorum_lost"
        assert result.rounds == 1


class TestMaxRoundsNotConverged:
    """Medium+ findings persist across 3 rounds → max_rounds."""

    def test_max_rounds(self, tmp_path: Path) -> None:
        # Each round returns the same blocking finding
        finding = _make_consensus_finding(1, status="confirmed", criticality="high")
        results_per_round = []
        reports_per_round = []

        for _ in range(3):
            results_per_round.append([
                _make_review_result("vendor_a", success=True, findings=[{
                    "id": 1, "type": "bug", "criticality": "high",
                    "description": "Critical bug", "disposition": "fix",
                }]),
                _make_review_result("vendor_b", success=True, findings=[{
                    "id": 1, "type": "bug", "criticality": "high",
                    "description": "Critical bug", "disposition": "fix",
                }]),
            ])
            reports_per_round.append(_make_consensus_report(findings=[finding]))

        ctx = _setup_converge(results_per_round, reports_per_round, tmp_path)

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=3,
            )

        # With constant findings [1, 1, 1], round 3 sees trend[-1]=1 >= trend[-3]=1 → stalled
        assert result.converged is False
        assert result.reason == "stalled"


class TestStallDetection:
    """Findings [5, 5, 5] → stalled after round 3."""

    def test_stall_detected(self, tmp_path: Path) -> None:
        results_per_round = []
        reports_per_round = []

        for round_idx in range(3):
            # Create 5 blocking findings per round
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

        assert result.converged is False
        assert result.reason == "stalled"
        assert result.rounds == 3


class TestStallNotTriggeredWhenDecreasing:
    """Findings [10, 5, 3] → continues (no stall)."""

    def test_decreasing_not_stalled(self, tmp_path: Path) -> None:
        results_per_round = []
        reports_per_round = []
        counts = [10, 5, 3, 0]  # 4th round converges

        for round_idx, count in enumerate(counts):
            findings = [
                _make_consensus_finding(i, status="confirmed", criticality="medium")
                for i in range(1, count + 1)
            ]
            results_per_round.append([
                _make_review_result("vendor_a", success=True, findings=[
                    {"id": i, "type": "bug", "criticality": "medium",
                     "description": f"Bug {i}", "disposition": "fix"}
                    for i in range(1, count + 1)
                ]),
                _make_review_result("vendor_b", success=True, findings=[
                    {"id": i, "type": "bug", "criticality": "medium",
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
                max_rounds=5,
            )

        assert result.converged is True
        assert result.rounds == 4


class TestDisagreementEscalate:
    """Disagreement finding → reason='disagreement'."""

    def test_disagreement(self, tmp_path: Path) -> None:
        finding = _make_consensus_finding(1, status="disagreement", criticality="medium")
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

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
            )

        assert result.converged is False
        assert result.reason == "disagreement"
        assert result.escalate_findings is not None
        assert len(result.escalate_findings) == 1


class TestUnconfirmedRelaxedFinalRound:
    """Unconfirmed medium finding in final round (round 3) → converged."""

    def test_relaxed_final_round(self, tmp_path: Path) -> None:
        # Rounds 1-2: confirmed medium findings (blocking)
        # Round 3: only unconfirmed medium (relaxed in final round)
        results_per_round = []
        reports_per_round = []

        # Round 1: confirmed blocking
        f1 = _make_consensus_finding(1, status="confirmed", criticality="medium")
        results_per_round.append([
            _make_review_result("vendor_a", success=True, findings=[
                {"id": 1, "type": "bug", "criticality": "medium",
                 "description": "Bug 1", "disposition": "fix"}
            ]),
            _make_review_result("vendor_b", success=True, findings=[
                {"id": 1, "type": "bug", "criticality": "medium",
                 "description": "Bug 1", "disposition": "fix"}
            ]),
        ])
        reports_per_round.append(_make_consensus_report(findings=[f1]))

        # Round 2: fewer confirmed (decreasing trend)
        results_per_round.append([
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[
                {"id": 2, "type": "style", "criticality": "medium",
                 "description": "Style nit", "disposition": "accept"}
            ]),
        ])
        f2_unconfirmed = _make_consensus_finding(2, status="unconfirmed", criticality="medium")
        reports_per_round.append(_make_consensus_report(findings=[f2_unconfirmed]))

        # Round 3 (final): only unconfirmed medium → relaxed
        results_per_round.append([
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[
                {"id": 3, "type": "style", "criticality": "medium",
                 "description": "Minor nit", "disposition": "accept"}
            ]),
        ])
        f3_unconfirmed = _make_consensus_finding(3, status="unconfirmed", criticality="medium")
        reports_per_round.append(_make_consensus_report(findings=[f3_unconfirmed]))

        ctx = _setup_converge(results_per_round, reports_per_round, tmp_path)

        with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
            result = converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                max_rounds=3,
            )

        assert result.converged is True
        assert result.rounds == 3


class TestUnconfirmedBlocksEarlyRounds:
    """Unconfirmed medium finding blocks early rounds but relaxes in final."""

    def test_unconfirmed_blocks_early_relaxes_final(self, tmp_path: Path) -> None:
        """Unconfirmed medium blocks rounds 1-2 (fix dispatched), relaxed in round 3."""
        finding = _make_consensus_finding(1, status="unconfirmed", criticality="medium")

        # 3 rounds of the same unconfirmed finding
        results_per_round = []
        reports_per_round = []
        for _ in range(3):
            results_per_round.append([
                _make_review_result("vendor_a", success=True, findings=[
                    {"id": 1, "type": "bug", "criticality": "medium",
                     "description": "Unconfirmed bug", "disposition": "fix"}
                ]),
                _make_review_result("vendor_b", success=True, findings=[]),
            ])
            reports_per_round.append(_make_consensus_report(findings=[finding]))

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

        # Rounds 1-2: unconfirmed medium blocks, fix_callback called
        assert fix_cb.call_count == 2
        # Round 3 (final): unconfirmed relaxed, 0 blocking, converged
        assert result.converged is True
        assert result.rounds == 3

    def test_unconfirmed_blocks_round_1(self, tmp_path: Path) -> None:
        """With more rounds available, unconfirmed medium blocks round 1."""
        finding = _make_consensus_finding(1, status="unconfirmed", criticality="medium")

        # Round 1: unconfirmed blocks
        results_round1 = [
            _make_review_result("vendor_a", success=True, findings=[
                {"id": 1, "type": "bug", "criticality": "medium",
                 "description": "Unconfirmed bug", "disposition": "fix"}
            ]),
            _make_review_result("vendor_b", success=True, findings=[]),
        ]
        report1 = _make_consensus_report(findings=[finding])

        # Round 2: no findings, converges
        results_round2 = [
            _make_review_result("vendor_a", success=True, findings=[]),
            _make_review_result("vendor_b", success=True, findings=[]),
        ]
        report2 = _make_consensus_report(findings=[])

        ctx = _setup_converge(
            [results_round1, results_round2],
            [report1, report2],
            tmp_path,
        )
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

        # Round 1 blocked (unconfirmed medium), fix dispatched
        fix_cb.assert_called_once()
        # Round 2 clean, converged
        assert result.converged is True
        assert result.rounds == 2


class TestFixCallbackCalled:
    """When not converged, fix_callback is invoked with blocking findings."""

    def test_fix_callback(self, tmp_path: Path) -> None:
        finding = _make_consensus_finding(1, status="confirmed", criticality="high")

        results_per_round = []
        reports_per_round = []

        # Round 1: blocking finding → fix_callback called
        results_per_round.append([
            _make_review_result("vendor_a", success=True, findings=[
                {"id": 1, "type": "bug", "criticality": "high",
                 "description": "High bug", "disposition": "fix"}
            ]),
            _make_review_result("vendor_b", success=True, findings=[
                {"id": 1, "type": "bug", "criticality": "high",
                 "description": "High bug", "disposition": "fix"}
            ]),
        ])
        reports_per_round.append(_make_consensus_report(findings=[finding]))

        # Round 2: no findings → converged
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
        # First arg is the list of blocking findings
        blocking_arg = fix_cb.call_args[0][0]
        assert len(blocking_arg) == 1
        assert blocking_arg[0]["agreed_criticality"] == "high"
        # Second arg is the worktree path
        assert fix_cb.call_args[0][1] == tmp_path


class TestMemoryCallbackCalled:
    """Memory callback invoked each round with correct details."""

    def test_memory_callback(self, tmp_path: Path) -> None:
        # Round 1: no findings → converged
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
        memory_cb.assert_called_once()
        call_arg = memory_cb.call_args[0][0]
        assert "Round 1" in call_arg
        assert "0 blocking" in call_arg


class TestBuildReviewPrompt:
    """Test the review prompt builder."""

    def test_basic_prompt(self, tmp_path: Path) -> None:
        prompt = build_review_prompt(tmp_path, 2)
        assert "Round 2" in prompt
        assert "findings" in prompt.lower()

    def test_with_proposal(self, tmp_path: Path) -> None:
        (tmp_path / "proposal.md").write_text("# My Proposal\nDetails here.")
        prompt = build_review_prompt(tmp_path, 1)
        assert "My Proposal" in prompt
        assert "### Proposal" in prompt

    def test_with_design(self, tmp_path: Path) -> None:
        (tmp_path / "design.md").write_text("# Design Doc\nArchitecture.")
        prompt = build_review_prompt(tmp_path, 1)
        assert "Design Doc" in prompt


class TestIsBlocking:
    """Test the _is_blocking helper."""

    def test_confirmed_medium_blocks(self) -> None:
        assert _is_blocking({"status": "confirmed", "agreed_criticality": "medium"}) is True

    def test_confirmed_low_does_not_block(self) -> None:
        assert _is_blocking({"status": "confirmed", "agreed_criticality": "low"}) is False

    def test_unconfirmed_medium_blocks_by_default(self) -> None:
        assert _is_blocking({"status": "unconfirmed", "agreed_criticality": "medium"}) is True

    def test_unconfirmed_medium_relaxed(self) -> None:
        assert _is_blocking(
            {"status": "unconfirmed", "agreed_criticality": "medium"},
            relax_unconfirmed=True,
        ) is False

    def test_confirmed_high_not_relaxed(self) -> None:
        assert _is_blocking(
            {"status": "confirmed", "agreed_criticality": "high"},
            relax_unconfirmed=True,
        ) is True
