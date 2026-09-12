"""Ledger-driven convergence: delta prompts, parked disagreement, stall, scoped fixes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS_DIR = str(
    Path(__file__).resolve().parents[2] / "autopilot" / "scripts"
)
_PARALLEL_DIR = str(
    Path(__file__).resolve().parents[2] / "parallel-infrastructure" / "scripts"
)
for p in (_SCRIPTS_DIR, _PARALLEL_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from consensus_synthesizer import ConsensusFinding, ConsensusReport
from convergence_loop import build_review_prompt, converge
from review_dispatcher import ReviewResult
from review_ledger import ScopeViolation, load_or_create, reject_out_of_scope_fix


def _make_review_result(
    vendor: str,
    success: bool = True,
    findings: list[dict] | None = None,
) -> ReviewResult:
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
) -> ConsensusReport:
    findings = findings or []
    confirmed = sum(1 for f in findings if f.status == "confirmed")
    unconfirmed = sum(1 for f in findings if f.status == "unconfirmed")
    disagreement = sum(1 for f in findings if f.status == "disagreement")
    return ConsensusReport(
        review_type="implementation",
        target="test-change",
        reviewers=[],
        quorum_met=True,
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
    criticality: str = "high",
    disposition: str = "fix",
    *,
    evidence_class: str = "deterministic",
    description: str | None = None,
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
        recommended_disposition=disposition,
        description=description or f"Test finding {id}",
        evidence_class=evidence_class,
    )


def _setup_converge(
    review_results_per_round: list[list[ReviewResult]],
    consensus_reports_per_round: list[ConsensusReport],
    tmp_path: Path,
) -> dict:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    mock_orchestrator = MagicMock()
    mock_orchestrator.dispatch_and_wait.side_effect = review_results_per_round
    mock_synthesizer = MagicMock()
    mock_synthesizer.synthesize.side_effect = consensus_reports_per_round
    real_synth = __import__(
        "consensus_synthesizer", fromlist=["ConsensusSynthesizer"]
    ).ConsensusSynthesizer()
    mock_synthesizer.to_dict.side_effect = [
        real_synth.to_dict(r) for r in consensus_reports_per_round
    ]
    return {
        "artifacts_dir": artifacts_dir,
        "orchestrator": mock_orchestrator,
        "synthesizer": mock_synthesizer,
    }


def test_round_2_prompt_carries_ledger_and_diff(tmp_path: Path) -> None:
    ledger = {
        "items": [
            {
                "id": 1,
                "status": "open",
                "description": "Open null-check finding",
            },
            {
                "id": 2,
                "status": "retired",
                "description": "Already gone",
            },
        ]
    }
    prompt = build_review_prompt(
        tmp_path,
        2,
        ledger=ledger,
        last_fix_diff="diff --git a/src/api.py b/src/api.py\n+fixed",
    )
    assert "Open null-check finding" in prompt
    assert "diff --git a/src/api.py" in prompt
    assert "retired" in prompt.lower() or "parked" in prompt.lower()
    assert "do not re-open" in prompt.lower() or "not to re-open" in prompt.lower()


def test_round_2_prompt_empty_diff_marker(tmp_path: Path) -> None:
    prompt = build_review_prompt(tmp_path, 2, ledger={"items": []}, last_fix_diff="")
    assert "empty-diff" in prompt.lower() or "(empty-diff)" in prompt.lower()


def test_disagreement_plus_agreed_blocking_continues(tmp_path: Path) -> None:
    disputed = _make_consensus_finding(
        1, status="disagreement", criticality="medium", evidence_class="judgment",
    )
    disputed.vendor_dispositions = {"vendor_a": "fix", "vendor_b": "accept"}
    agreed = _make_consensus_finding(
        2, status="confirmed", criticality="high", evidence_class="deterministic",
        description="Confirmed high deterministic bug",
    )

    results_r1 = [
        _make_review_result("vendor_a", findings=[
            {"id": 1, "type": "bug", "criticality": "medium",
             "description": "Disputed issue", "disposition": "fix",
             "file_path": "src/other.py"},
            {"id": 2, "type": "bug", "criticality": "high",
             "description": "Confirmed high deterministic bug", "disposition": "fix",
             "file_path": "src/api.py"},
        ]),
        _make_review_result("vendor_b", findings=[
            {"id": 1, "type": "bug", "criticality": "medium",
             "description": "Disputed issue", "disposition": "accept",
             "file_path": "src/other.py"},
            {"id": 2, "type": "bug", "criticality": "high",
             "description": "Confirmed high deterministic bug", "disposition": "fix",
             "file_path": "src/api.py"},
        ]),
    ]
    results_r2 = [
        _make_review_result("vendor_a", findings=[]),
        _make_review_result("vendor_b", findings=[]),
    ]
    ctx = _setup_converge(
        [results_r1, results_r2],
        [
            _make_consensus_report(findings=[disputed, agreed]),
            _make_consensus_report(findings=[]),
        ],
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
            fix_callback=fix_cb,
        )
    assert result.reason != "disagreement"
    assert fix_cb.called
    blocking_arg = fix_cb.call_args[0][0]
    assert any("Confirmed high" in (b.get("description") or "") for b in blocking_arg)
    parked = ctx["artifacts_dir"] / "reviews" / "parked-disagreements.json"
    assert parked.exists()
    doc = json.loads(parked.read_text())
    assert doc["items"]


def test_only_disagreement_converges_with_leftovers(tmp_path: Path) -> None:
    disputed = _make_consensus_finding(
        1, status="disagreement", criticality="medium", evidence_class="judgment",
    )
    disputed.vendor_dispositions = {"vendor_a": "fix", "vendor_b": "accept"}
    results = [
        _make_review_result("vendor_a", findings=[{
            "id": 1, "type": "bug", "criticality": "medium",
            "description": "Disputed", "disposition": "fix",
        }]),
        _make_review_result("vendor_b", findings=[{
            "id": 1, "type": "bug", "criticality": "medium",
            "description": "Disputed", "disposition": "accept",
        }]),
    ]
    ctx = _setup_converge(
        [results],
        [_make_consensus_report(findings=[disputed])],
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
            fix_callback=fix_cb,
        )
    assert result.converged is True
    assert result.reason != "disagreement"
    assert result.escalate_findings
    fix_cb.assert_not_called()
    parked = ctx["artifacts_dir"] / "reviews" / "parked-disagreements.json"
    assert parked.exists()


def test_unconfirmed_medium_judgment_does_not_enter_fix_callback(tmp_path: Path) -> None:
    finding = _make_consensus_finding(
        1, status="unconfirmed", criticality="medium", evidence_class="judgment",
    )
    results = [
        _make_review_result("vendor_a", findings=[{
            "id": 1, "type": "bug", "criticality": "medium",
            "description": "Style nit", "disposition": "fix",
            "evidence_class": "judgment",
        }]),
        _make_review_result("vendor_b", findings=[]),
    ]
    ctx = _setup_converge(
        [results],
        [_make_consensus_report(findings=[finding])],
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
            fix_callback=fix_cb,
        )
    assert result.converged is True
    fix_cb.assert_not_called()


def test_non_decreasing_blocking_stalls(tmp_path: Path) -> None:
    finding = _make_consensus_finding(1, status="confirmed", criticality="high")
    round_results = [
        _make_review_result("vendor_a", findings=[{
            "id": 1, "type": "bug", "criticality": "high",
            "description": "Critical bug", "disposition": "fix",
            "file_path": "src/api.py",
        }]),
        _make_review_result("vendor_b", findings=[{
            "id": 1, "type": "bug", "criticality": "high",
            "description": "Critical bug", "disposition": "fix",
            "file_path": "src/api.py",
        }]),
    ]
    ctx = _setup_converge(
        [round_results, round_results],
        [
            _make_consensus_report(findings=[finding]),
            _make_consensus_report(findings=[finding]),
        ],
        tmp_path,
    )
    with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
        result = converge(
            change_id="test-change",
            review_type="implementation",
            artifacts_dir=ctx["artifacts_dir"],
            worktree_path=tmp_path,
            orchestrator=ctx["orchestrator"],
            max_rounds=5,
            fix_callback=MagicMock(),
        )
    assert result.converged is False
    assert result.reason == "stalled"
    assert result.rounds == 2


def test_decreasing_blocking_continues(tmp_path: Path) -> None:
    f_two = [
        _make_consensus_finding(1, status="confirmed", criticality="high", description="Bug one"),
        _make_consensus_finding(2, status="confirmed", criticality="high", description="Bug two"),
    ]
    f_one = [_make_consensus_finding(1, status="confirmed", criticality="high", description="Bug one")]
    r2 = [
        _make_review_result("vendor_a", findings=[{
            "id": i, "type": "bug", "criticality": "high",
            "description": f"Bug {'one' if i == 1 else 'two'}", "disposition": "fix",
        } for i in (1, 2)]),
        _make_review_result("vendor_b", findings=[{
            "id": i, "type": "bug", "criticality": "high",
            "description": f"Bug {'one' if i == 1 else 'two'}", "disposition": "fix",
        } for i in (1, 2)]),
    ]
    r1 = [
        _make_review_result("vendor_a", findings=[{
            "id": 1, "type": "bug", "criticality": "high",
            "description": "Bug one", "disposition": "fix",
        }]),
        _make_review_result("vendor_b", findings=[{
            "id": 1, "type": "bug", "criticality": "high",
            "description": "Bug one", "disposition": "fix",
        }]),
    ]
    r0 = [
        _make_review_result("vendor_a", findings=[]),
        _make_review_result("vendor_b", findings=[]),
    ]
    ctx = _setup_converge(
        [r2, r1, r0],
        [
            _make_consensus_report(findings=f_two),
            _make_consensus_report(findings=f_one),
            _make_consensus_report(findings=[]),
        ],
        tmp_path,
    )
    with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
        result = converge(
            change_id="test-change",
            review_type="implementation",
            artifacts_dir=ctx["artifacts_dir"],
            worktree_path=tmp_path,
            orchestrator=ctx["orchestrator"],
            max_rounds=5,
            fix_callback=MagicMock(),
        )
    assert result.converged is True
    assert result.reason is None


def test_fix_callback_scoped_to_cited_file(tmp_path: Path) -> None:
    finding = _make_consensus_finding(1, status="confirmed", criticality="high")
    results_r1 = [
        _make_review_result("vendor_a", findings=[{
            "id": 1, "type": "bug", "criticality": "high",
            "description": "High bug", "disposition": "fix",
            "file_path": "src/api.py",
        }]),
        _make_review_result("vendor_b", findings=[{
            "id": 1, "type": "bug", "criticality": "high",
            "description": "High bug", "disposition": "fix",
            "file_path": "src/api.py",
        }]),
    ]
    results_r2 = [
        _make_review_result("vendor_a", findings=[]),
        _make_review_result("vendor_b", findings=[]),
    ]
    ctx = _setup_converge(
        [results_r1, results_r2],
        [
            _make_consensus_report(findings=[finding]),
            _make_consensus_report(findings=[]),
        ],
        tmp_path,
    )
    fix_cb = MagicMock()
    with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
        converge(
            change_id="test-change",
            review_type="implementation",
            artifacts_dir=ctx["artifacts_dir"],
            worktree_path=tmp_path,
            orchestrator=ctx["orchestrator"],
            fix_callback=fix_cb,
        )
    blocking_arg = fix_cb.call_args[0][0]
    assert blocking_arg[0]["allowed_paths"] == ["src/api.py"]
    assert "src/frontend/app.tsx" not in blocking_arg[0]["allowed_paths"]


def test_out_of_scope_fix_rejected() -> None:
    with pytest.raises(ScopeViolation):
        reject_out_of_scope_fix(["src/frontend/app.tsx"], ["src/api.py"])


def test_missing_ledger_still_runs(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    results = [
        _make_review_result("vendor_a", findings=[]),
        _make_review_result("vendor_b", findings=[]),
    ]
    report = _make_consensus_report(findings=[])
    mock_orchestrator = MagicMock()
    mock_orchestrator.dispatch_and_wait.return_value = results
    mock_synthesizer = MagicMock()
    mock_synthesizer.synthesize.return_value = report
    real_synth = __import__(
        "consensus_synthesizer", fromlist=["ConsensusSynthesizer"]
    ).ConsensusSynthesizer()
    mock_synthesizer.to_dict.return_value = real_synth.to_dict(report)
    with patch("convergence_loop.ConsensusSynthesizer", return_value=mock_synthesizer):
        result = converge(
            change_id="test-change",
            review_type="implementation",
            artifacts_dir=artifacts,
            worktree_path=tmp_path,
            orchestrator=mock_orchestrator,
        )
    assert result.converged is True
    assert (artifacts / ".review-ledger" / "ledger.json").exists()


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=path, check=True, capture_output=True,
    )
    (path / "README").write_text("init\n")
    subprocess.run(["git", "add", "README"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True,
    )


def _blocking_round(tmp_path: Path) -> tuple[dict, object]:
    finding = _make_consensus_finding(1, status="confirmed", criticality="high")
    results_r1 = [
        _make_review_result("vendor_a", findings=[{
            "id": 1, "type": "bug", "criticality": "high",
            "description": "High bug", "disposition": "fix",
            "file_path": "src/api.py",
        }]),
        _make_review_result("vendor_b", findings=[{
            "id": 1, "type": "bug", "criticality": "high",
            "description": "High bug", "disposition": "fix",
            "file_path": "src/api.py",
        }]),
    ]
    results_r2 = [
        _make_review_result("vendor_a", findings=[]),
        _make_review_result("vendor_b", findings=[]),
    ]
    ctx = _setup_converge(
        [results_r1, results_r2],
        [
            _make_consensus_report(findings=[finding]),
            _make_consensus_report(findings=[]),
        ],
        tmp_path,
    )
    return ctx, finding


def test_failed_fix_callback_does_not_mark_addressed(tmp_path: Path) -> None:
    ctx, _finding = _blocking_round(tmp_path)

    def boom(_blocking: list, _path: Path) -> None:
        raise RuntimeError("fixer exploded")

    with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
        with pytest.raises(RuntimeError, match="fixer exploded"):
            converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                fix_callback=boom,
            )
    ledger = load_or_create(ctx["artifacts_dir"], "test-change")
    assert ledger["items"][0]["status"] == "open"


def test_absent_fix_callback_does_not_mark_addressed(tmp_path: Path) -> None:
    finding = _make_consensus_finding(1, status="confirmed", criticality="high")
    results = [
        _make_review_result("vendor_a", findings=[{
            "id": 1, "type": "bug", "criticality": "high",
            "description": "High bug", "disposition": "fix",
            "file_path": "src/api.py",
        }]),
        _make_review_result("vendor_b", findings=[{
            "id": 1, "type": "bug", "criticality": "high",
            "description": "High bug", "disposition": "fix",
            "file_path": "src/api.py",
        }]),
    ]
    ctx = _setup_converge(
        [results],
        [_make_consensus_report(findings=[finding])],
        tmp_path,
    )
    with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
        result = converge(
            change_id="test-change",
            review_type="implementation",
            artifacts_dir=ctx["artifacts_dir"],
            worktree_path=tmp_path,
            orchestrator=ctx["orchestrator"],
            max_rounds=1,
        )
    assert result.converged is False
    ledger = load_or_create(ctx["artifacts_dir"], "test-change")
    assert ledger["items"][0]["status"] == "open"


def test_successful_fix_marks_addressed(tmp_path: Path) -> None:
    ctx, _finding = _blocking_round(tmp_path)
    with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
        converge(
            change_id="test-change",
            review_type="implementation",
            artifacts_dir=ctx["artifacts_dir"],
            worktree_path=tmp_path,
            orchestrator=ctx["orchestrator"],
            fix_callback=MagicMock(),
        )
    ledger = load_or_create(ctx["artifacts_dir"], "test-change")
    assert ledger["items"][0]["status"] == "addressed"


def test_converge_rejects_out_of_scope_fix(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "api.py").write_text("ok\n")
    (src / "frontend.tsx").write_text("ui\n")
    subprocess.run(["git", "add", "src"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "src"], cwd=tmp_path, check=True, capture_output=True,
    )
    ctx, _finding = _blocking_round(tmp_path)

    def edit_unrelated(_blocking: list, worktree: Path) -> None:
        (worktree / "src" / "frontend.tsx").write_text("hacked\n")

    with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
        with pytest.raises(ScopeViolation):
            converge(
                change_id="test-change",
                review_type="implementation",
                artifacts_dir=ctx["artifacts_dir"],
                worktree_path=tmp_path,
                orchestrator=ctx["orchestrator"],
                fix_callback=edit_unrelated,
            )
    ledger = load_or_create(ctx["artifacts_dir"], "test-change")
    assert ledger["items"][0]["status"] == "open"


def test_last_fix_diff_includes_committed_callback_edits(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    ctx, _finding = _blocking_round(tmp_path)

    def commit_fix(_blocking: list, worktree: Path) -> None:
        target = worktree / "src" / "api.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixed-the-bug\n")
        subprocess.run(
            ["git", "add", "src/api.py"], cwd=worktree, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "fix api"], cwd=worktree,
            check=True, capture_output=True,
        )

    with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
        converge(
            change_id="test-change",
            review_type="implementation",
            artifacts_dir=ctx["artifacts_dir"],
            worktree_path=tmp_path,
            orchestrator=ctx["orchestrator"],
            fix_callback=commit_fix,
        )
    round2 = ctx["orchestrator"].dispatch_and_wait.call_args_list[1].kwargs["prompt"]
    assert "fixed-the-bug" in round2
    assert "(empty-diff)" not in round2


def test_spec_gap_payload_includes_derived_spec_file(tmp_path: Path) -> None:
    finding = _make_consensus_finding(
        1, status="confirmed", criticality="high",
    )
    finding.agreed_type = "spec_gap"
    results_r1 = [
        _make_review_result("vendor_a", findings=[{
            "id": 1, "type": "spec_gap", "criticality": "high",
            "description": "Test finding 1", "disposition": "fix",
            "file_path": "src/api.py", "capability": "api",
        }]),
        _make_review_result("vendor_b", findings=[{
            "id": 1, "type": "spec_gap", "criticality": "high",
            "description": "Test finding 1", "disposition": "fix",
            "file_path": "src/api.py", "capability": "api",
        }]),
    ]
    results_r2 = [
        _make_review_result("vendor_a", findings=[]),
        _make_review_result("vendor_b", findings=[]),
    ]
    ctx = _setup_converge(
        [results_r1, results_r2],
        [
            _make_consensus_report(findings=[finding]),
            _make_consensus_report(findings=[]),
        ],
        tmp_path,
    )
    spec = ctx["artifacts_dir"] / "specs" / "api" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# API\nsrc/api.py\n")
    fix_cb = MagicMock()
    with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
        converge(
            change_id="test-change",
            review_type="implementation",
            artifacts_dir=ctx["artifacts_dir"],
            worktree_path=tmp_path,
            orchestrator=ctx["orchestrator"],
            fix_callback=fix_cb,
        )
    payload = fix_cb.call_args[0][0][0]
    assert payload["spec_file"] == str(spec)
    assert str(spec) in payload["allowed_paths"]
    ledger = load_or_create(ctx["artifacts_dir"], "test-change")
    assert ledger["items"][0]["spec_file"] == str(spec)

