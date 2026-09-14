"""Convergence loop calls fact-check after checkpoint, before synthesis."""

from __future__ import annotations

import json
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

from convergence_loop import converge  # noqa: E402
from review_dispatcher import ReviewResult  # noqa: E402


def _make_review_result(vendor: str, findings: list[dict]) -> ReviewResult:
    return ReviewResult(
        vendor=vendor,
        success=True,
        findings={"findings": findings},
        model_used="test-model",
        models_attempted=["test-model"],
        elapsed_seconds=1.0,
    )


def _finding(**overrides) -> dict:
    doc = {
        "id": "f-1",
        "type": "correctness",
        "criticality": "high",
        "description": "Variable `used_variable` is declared but never used.",
        "disposition": "fix",
        "axis": "correctness",
        "severity": "critical",
        "file_path": "src/foo.py",
    }
    doc.update(overrides)
    return doc


def _setup(tmp_path: Path, results: list[ReviewResult]) -> dict:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    mock_orchestrator = MagicMock()
    mock_orchestrator.dispatch_and_wait.return_value = results
    return {"artifacts_dir": artifacts_dir, "orchestrator": mock_orchestrator}


def test_fact_check_false_disables_the_pass(tmp_path: Path) -> None:
    """No caller resolution is even attempted when fact_check=False."""
    results = [
        _make_review_result("codex", [_finding(id="f-1")]),
        _make_review_result("claude", [_finding(id="f-1")]),
    ]
    ctx = _setup(tmp_path, results)

    call_count = {"n": 0}

    def fake_resolve(_orch, _vendor, _cwd):
        call_count["n"] += 1
        return None

    with patch("convergence_loop._resolve_fact_check_caller", side_effect=fake_resolve):
        result = converge(
            change_id="demo",
            review_type="implementation",
            artifacts_dir=ctx["artifacts_dir"],
            worktree_path=tmp_path,
            orchestrator=ctx["orchestrator"],
            max_rounds=1,
            min_quorum=2,
            fact_check=False,
        )
    assert result.rounds == 1
    assert call_count["n"] == 0
    # No decision files written when the pass is disabled.
    round_dir = ctx["artifacts_dir"] / ".review-cache" / "round-1"
    assert not list(round_dir.glob("fact-check-*.json"))


def test_checkpoint_precedes_fact_check_removal(tmp_path: Path) -> None:
    """The raw checkpointed findings file still holds a finding fact-check removes."""
    finding = _finding(id="f-1")
    results = [
        _make_review_result("codex", [finding]),
        _make_review_result("claude", [finding]),
    ]
    ctx = _setup(tmp_path, results)

    def fake_caller(_system: str, _user: str) -> str:
        return json.dumps({
            "tool": "report_incorrect_comments",
            "items": [{
                "finding_id": "f-1",
                "ground": "B_contradicted_by_diff_line",
                "evidence_line": "+used_variable = compute()",
            }],
        })

    def fake_resolve(_orch, _vendor, _cwd):
        return fake_caller

    with patch("convergence_loop._resolve_fact_check_caller", side_effect=fake_resolve):
        result = converge(
            change_id="demo",
            review_type="implementation",
            artifacts_dir=ctx["artifacts_dir"],
            worktree_path=tmp_path,
            orchestrator=ctx["orchestrator"],
            max_rounds=1,
            min_quorum=2,
        )

    round_dir = ctx["artifacts_dir"] / ".review-cache" / "round-1"
    raw = json.loads((round_dir / "findings-codex-implementation.json").read_text())
    assert raw["findings"][0]["id"] == "f-1"

    decision_doc = json.loads((round_dir / "fact-check-codex.json").read_text())
    assert decision_doc["status"] == "ran"
    assert decision_doc["decisions"][0]["verdict"] == "removed"

    manifest = json.loads((round_dir / "review-manifest.json").read_text())
    codex_entry = next(v for v in manifest["vendors"] if v["name"] == "codex")
    assert codex_entry["fact_check"] == "ran"
    assert codex_entry["fact_check_removed"] == 1
    # The manifest's finding_count reflects the RAW checkpointed count, not
    # the post-fact-check filtered count.
    assert codex_entry["finding_count"] == 1

    # The removed finding never reached the consensus report.
    assert result.consensus is not None
    assert len(result.consensus.get("consensus_findings", [])) == 0


def test_fact_check_failure_removes_nothing_from_synthesis(tmp_path: Path) -> None:
    finding = _finding(id="f-1")
    results = [
        _make_review_result("codex", [finding]),
        _make_review_result("claude", [finding]),
    ]
    ctx = _setup(tmp_path, results)

    def failing_caller(_system: str, _user: str) -> str:
        raise TimeoutError("model unreachable")

    with patch(
        "convergence_loop._resolve_fact_check_caller",
        side_effect=lambda o, v, c: failing_caller,
    ):
        result = converge(
            change_id="demo",
            review_type="implementation",
            artifacts_dir=ctx["artifacts_dir"],
            worktree_path=tmp_path,
            orchestrator=ctx["orchestrator"],
            max_rounds=1,
            min_quorum=2,
        )

    round_dir = ctx["artifacts_dir"] / ".review-cache" / "round-1"
    decision_doc = json.loads((round_dir / "fact-check-codex.json").read_text())
    assert decision_doc["status"] == "skipped"
    # Nothing removed: both vendors still agree, so the finding converges.
    assert result.consensus is not None
    assert len(result.consensus.get("consensus_findings", [])) == 1


def test_default_orchestrator_without_adapters_skips_gracefully(tmp_path: Path) -> None:
    """A bare MagicMock orchestrator (no real .adapters) must not raise."""
    finding = _finding(id="f-1")
    results = [
        _make_review_result("codex", [finding]),
        _make_review_result("claude", [finding]),
    ]
    ctx = _setup(tmp_path, results)

    result = converge(
        change_id="demo",
        review_type="implementation",
        artifacts_dir=ctx["artifacts_dir"],
        worktree_path=tmp_path,
        orchestrator=ctx["orchestrator"],
        max_rounds=1,
        min_quorum=2,
    )
    assert result.rounds == 1
    round_dir = ctx["artifacts_dir"] / ".review-cache" / "round-1"
    decision_doc = json.loads((round_dir / "fact-check-codex.json").read_text())
    assert decision_doc["status"] == "skipped"
    assert decision_doc["skip_reason"] == "no_caller_available"
