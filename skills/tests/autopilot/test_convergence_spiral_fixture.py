"""Seeded spiral fixture: round-1 extra unconfirmed medium must not grow blocking."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_SCRIPTS_DIR = str(Path(__file__).resolve().parents[2] / "autopilot" / "scripts")
_PARALLEL_DIR = str(
    Path(__file__).resolve().parents[2] / "parallel-infrastructure" / "scripts"
)
for p in (_SCRIPTS_DIR, _PARALLEL_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from consensus_synthesizer import ConsensusFinding, ConsensusReport
from convergence_loop import converge
from review_dispatcher import ReviewResult


def _result(vendor: str, findings: list[dict]) -> ReviewResult:
    return ReviewResult(
        vendor=vendor,
        success=True,
        findings={"findings": findings},
        model_used="test-model",
        models_attempted=["test-model"],
        elapsed_seconds=1.0,
    )


def _finding(
    id: int,
    *,
    status: str,
    criticality: str,
    description: str,
    evidence_class: str,
) -> ConsensusFinding:
    return ConsensusFinding(
        id=id,
        status=status,
        primary_vendor="vendor_a",
        primary_finding_id=id,
        matched_findings=[],
        match_score=0.9,
        agreed_type="bug",
        agreed_criticality=criticality,
        recommended_disposition="fix",
        description=description,
        evidence_class=evidence_class,
    )


def _report(findings: list[ConsensusFinding]) -> ConsensusReport:
    return ConsensusReport(
        review_type="implementation",
        target="spiral",
        reviewers=[],
        quorum_met=True,
        quorum_requested=2,
        quorum_received=2,
        consensus_findings=findings,
        total_unique=len(findings),
        confirmed_count=sum(1 for f in findings if f.status == "confirmed"),
        unconfirmed_count=sum(1 for f in findings if f.status == "unconfirmed"),
        disagreement_count=sum(1 for f in findings if f.status == "disagreement"),
        blocking_count=0,
    )


def test_round_1_extra_unconfirmed_medium_does_not_grow_blocking(tmp_path: Path) -> None:
    """Round 1 invents an extra unconfirmed medium judgment finding.

    Round 2 must not grow the post-compact blocking count: the extra finding
    never enters fix_callback, so it cannot spawn a spiral.
    """
    blocking = _finding(
        1,
        status="confirmed",
        criticality="high",
        description="Deterministic parse failure in src/api.py",
        evidence_class="deterministic",
    )
    extra = _finding(
        2,
        status="unconfirmed",
        criticality="medium",
        description="Maybe rename this helper for style",
        evidence_class="judgment",
    )

    r1_findings = [
        {
            "id": 1, "type": "bug", "criticality": "high",
            "description": "Deterministic parse failure in src/api.py",
            "disposition": "fix", "file_path": "src/api.py",
            "evidence_class": "deterministic",
        },
        {
            "id": 2, "type": "style", "criticality": "medium",
            "description": "Maybe rename this helper for style",
            "disposition": "accept", "file_path": "src/api.py",
            "evidence_class": "judgment",
        },
    ]
    r1 = [
        _result("vendor_a", r1_findings),
        _result("vendor_b", [r1_findings[0]]),
    ]
    r2 = [
        _result("vendor_a", [r1_findings[0]]),
        _result("vendor_b", [r1_findings[0]]),
    ]
    r3 = [
        _result("vendor_a", []),
        _result("vendor_b", []),
    ]

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    mock_orchestrator = MagicMock()
    mock_orchestrator.dispatch_and_wait.side_effect = [r1, r2, r3]
    reports = [
        _report([blocking, extra]),
        _report([blocking]),
        _report([]),
    ]
    mock_synthesizer = MagicMock()
    mock_synthesizer.synthesize.side_effect = reports
    real = __import__(
        "consensus_synthesizer", fromlist=["ConsensusSynthesizer"]
    ).ConsensusSynthesizer()
    mock_synthesizer.to_dict.side_effect = [real.to_dict(r) for r in reports]

    blocking_counts: list[int] = []

    def fix_cb(items, _wt):
        blocking_counts.append(len(items))
        for item in items:
            assert item.get("criticality") != "medium" or item.get("evidence_class") != "judgment"

    with patch("convergence_loop.ConsensusSynthesizer", return_value=mock_synthesizer):
        result = converge(
            change_id="spiral",
            review_type="implementation",
            artifacts_dir=artifacts,
            worktree_path=tmp_path,
            orchestrator=mock_orchestrator,
            max_rounds=3,
            fix_callback=fix_cb,
        )

    assert blocking_counts, "expected at least one fix round"
    assert blocking_counts[0] == 1
    if len(blocking_counts) > 1:
        assert blocking_counts[1] <= blocking_counts[0]
    assert result.reason != "disagreement"
    # Either converged with a non-increasing trend, or stalled without growth.
    if result.converged:
        assert True
    else:
        assert result.reason == "stalled"
