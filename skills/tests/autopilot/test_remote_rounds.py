"""Cross-host review rounds (factory Phase 1, 1.5).

``remote_rounds`` turns the coordinator's ``/reviews/rounds`` lanes for the
worktree's HEAD into ``ReviewResult`` objects, and ``converge()`` merges them
with local dispatch so quorum counts distinct vendors from any host.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_PARALLEL_DIR = str(Path(__file__).resolve().parents[2] / "parallel-infrastructure" / "scripts")
if _PARALLEL_DIR not in sys.path:
    sys.path.insert(0, _PARALLEL_DIR)

import convergence_loop
import remote_rounds
from consensus_synthesizer import ConsensusReport, ConsensusSynthesizer
from review_dispatcher import ReviewResult

FINDING = {
    "id": 1,
    "type": "bug",
    "criticality": "low",
    "description": "off by one",
    "disposition": "fix",
}


class FakeCoordinator:
    """Serves ``/reviews/rounds`` from a queue of canned job states."""

    def __init__(self, *jobs: dict[str, Any] | None):
        self._jobs = list(jobs)
        self.paths: list[str] = []

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert method == "GET"
        self.paths.append(path)
        job = self._jobs.pop(0) if len(self._jobs) > 1 else self._jobs[0]
        if job is None:
            return {"status_code": 200, "data": {"found": False}}
        return {"status_code": 200, "data": {"found": True, "job": job}}


def _job(status: str, *lanes: dict[str, Any]) -> dict[str, Any]:
    return {"job_id": "j1", "status": status, "lanes": list(lanes)}


def _lane(vendor: str, verified: bool = True, **extra: Any) -> dict[str, Any]:
    return {"vendor": vendor, "verified": verified, "findings": [FINDING], **extra}


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    repo = tmp_path / "wt"
    repo.mkdir()
    for argv in (
        ["init", "-q"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "t"],
        ["commit", "-q", "--allow-empty", "-m", "base"],
    ):
        subprocess.run(["git", "-C", str(repo), *argv], check=True, capture_output=True)
    return repo


# --- remote_rounds ---------------------------------------------------------


def test_only_verified_lanes_become_results_once_per_vendor() -> None:
    job = _job(
        "quorum_met",
        _lane("codex", model="m1"),
        _lane("gemini", verified=False),
        _lane("codex", model="m2"),
        _lane(""),
    )
    results = remote_rounds.lanes_to_results(job)
    assert [(r.vendor, r.success, r.model_used) for r in results] == [("codex", True, "m1")]
    assert results[0].findings == {"findings": [FINDING]}


def test_fetch_queries_by_head_and_reports_missing_rounds() -> None:
    client = FakeCoordinator(None)
    assert remote_rounds.fetch_round(client, "o/r", 7, "abc") is None
    assert client.paths == ["/reviews/rounds?repo=o%2Fr&pr=7&head_sha=abc"]


def test_source_reads_the_worktree_head(worktree: Path) -> None:
    head = remote_rounds.worktree_head(worktree)
    client = FakeCoordinator(_job("quorum_met", _lane("codex")))
    source = remote_rounds.coordinator_round_source(client, "o/r", 7, worktree)
    assert [r.vendor for r in source(1)] == ["codex"]
    assert client.paths == [f"/reviews/rounds?repo=o%2Fr&pr=7&head_sha={head}"]


def test_source_waits_while_the_job_is_active(worktree: Path) -> None:
    client = FakeCoordinator(
        None, _job("active"), _job("quorum_met", _lane("codex"), _lane("gemini"))
    )
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    source = remote_rounds.coordinator_round_source(
        client, "o/r", 7, worktree,
        wait_seconds=60, poll_seconds=10, sleep=sleep, clock=lambda: now[0],
    )
    assert [r.vendor for r in source(1)] == ["codex", "gemini"]
    assert sleeps == [10, 10]


def test_source_returns_partial_lanes_at_the_deadline(worktree: Path) -> None:
    client = FakeCoordinator(_job("active", _lane("codex")))
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    source = remote_rounds.coordinator_round_source(
        client, "o/r", 7, worktree,
        wait_seconds=25, poll_seconds=10, sleep=sleep, clock=lambda: now[0],
    )
    assert [r.vendor for r in source(1)] == ["codex"]
    assert len(client.paths) == 4  # t=0, 10, 20, 30 (past the deadline)


def test_unreviewed_head_yields_no_results(worktree: Path) -> None:
    source = remote_rounds.coordinator_round_source(FakeCoordinator(None), "o/r", 7, worktree)
    assert source(2) == []


# --- converge() merge --------------------------------------------------------


def _local(vendor: str, success: bool = True) -> ReviewResult:
    return ReviewResult(
        vendor=vendor,
        success=success,
        findings={"findings": []} if success else None,
        error=None if success else "timeout",
    )


def _remote(vendor: str) -> ReviewResult:
    return ReviewResult(vendor=vendor, success=True, findings={"findings": [FINDING]})


def test_merge_keeps_local_success_and_replaces_local_failure() -> None:
    merged = convergence_loop._merge_remote_results(
        [_local("claude_code"), _local("codex", success=False)],
        [_remote("claude_code"), _remote("codex"), _remote("gemini")],
    )
    assert [(r.vendor, r.success, bool(r.findings and r.findings["findings"])) for r in merged] == [
        ("claude_code", True, False),
        ("codex", True, True),
        ("gemini", True, True),
    ]


def _run_converge(
    tmp_path: Path, local: list[ReviewResult], remote_results: Any, **kwargs: Any
) -> tuple[Any, MagicMock]:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    orchestrator = MagicMock()
    orchestrator.dispatch_and_wait.return_value = local
    report = ConsensusReport(
        review_type="implementation", target="demo", reviewers=[], quorum_met=True,
        quorum_requested=2, quorum_received=2, consensus_findings=[], total_unique=0,
        confirmed_count=0, unconfirmed_count=0, disagreement_count=0, blocking_count=0,
    )
    synthesizer = MagicMock()
    synthesizer.synthesize.return_value = report
    synthesizer.to_dict.return_value = ConsensusSynthesizer().to_dict(report)
    with patch("convergence_loop.ConsensusSynthesizer", return_value=synthesizer):
        result = convergence_loop.converge(
            change_id="demo",
            review_type="implementation",
            artifacts_dir=artifacts,
            worktree_path=tmp_path,
            orchestrator=orchestrator,
            min_quorum=2,
            fact_check=False,
            remote_results=remote_results,
            **kwargs,
        )
    return result, synthesizer


def test_remote_lane_completes_a_round_one_host_could_not(tmp_path: Path) -> None:
    rounds: list[int] = []

    def remote(round_num: int) -> list[ReviewResult]:
        rounds.append(round_num)
        return [_remote("codex")]

    result, synthesizer = _run_converge(
        tmp_path, [_local("claude_code")], remote,
        verified_lanes=["claude_code"], counting_lanes=["claude_code", "codex"],
    )
    assert result.converged is True
    assert rounds == [1]
    vendors = [v.vendor for v in synthesizer.synthesize.call_args.kwargs["vendor_results"]]
    assert vendors == ["claude_code", "codex"]
    checkpoint = tmp_path / "artifacts" / ".review-cache" / "round-1"
    assert any("codex" in p.name for p in checkpoint.iterdir())


def test_round_still_short_of_quorum_is_quorum_lost(tmp_path: Path) -> None:
    result, synthesizer = _run_converge(
        tmp_path, [_local("claude_code")], lambda _round: [_remote("claude_code")],
        verified_lanes=["claude_code"],
    )
    assert result.converged is False
    assert result.reason == "quorum_lost"
    synthesizer.synthesize.assert_not_called()


def test_remote_read_failure_falls_back_to_local_lanes(tmp_path: Path) -> None:
    def remote(_round: int) -> list[ReviewResult]:
        raise ConnectionError("coordinator down")

    result, _ = _run_converge(tmp_path, [_local("claude_code"), _local("codex")], remote)
    assert result.converged is True
