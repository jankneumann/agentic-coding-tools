"""Honest review quorum (dispatch-contract SW Honest Review Quorum, D10).

`converge()` refuses to dispatch below quorum and reports the missing lanes;
the park itself is recorded only by `runner.py park` (the one writer), and a
dispatched child's emitted result is then `parked/capability_unavailable`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import autopilot
import convergence_loop
import runner


class _ExplodingOrchestrator:
    """Any dispatch attempt is a test failure."""

    def __getattr__(self, name: str):
        raise AssertionError(f"review was dispatched below quorum ({name})")


def test_converge_below_quorum_returns_capability_unavailable_without_dispatch(tmp_path: Path) -> None:
    result = convergence_loop.converge(
        "demo",
        "plan",
        tmp_path,
        tmp_path,
        min_quorum=2,
        orchestrator=_ExplodingOrchestrator(),
        verified_lanes=["claude_code"],
        counting_lanes=["claude_code", "codex"],
    )

    assert result.converged is False
    assert result.rounds == 0
    assert result.reason == "capability_unavailable"
    assert result.missing_lanes == ["codex"]
    assert not (tmp_path / "loop-state.json").exists()
    assert list(tmp_path.iterdir()) == []


def test_converge_at_quorum_does_not_trip_the_guard(tmp_path: Path, monkeypatch) -> None:
    called: list[bool] = []

    def fake_packet(**_kwargs):
        called.append(True)
        raise RuntimeError("stop after the guard")

    monkeypatch.setattr(convergence_loop, "build_review_packet", fake_packet)
    with pytest.raises(RuntimeError, match="stop after the guard"):
        convergence_loop.converge(
            "demo", "plan", tmp_path, tmp_path,
            min_quorum=1,
            orchestrator=object(),
            verified_lanes=["claude_code"],
            counting_lanes=["claude_code", "codex"],
        )
    assert called == [True]


def _git(repo: Path, *argv: str) -> None:
    subprocess.run(["git", *argv], cwd=repo, check=True, capture_output=True)


def test_a_dispatched_child_below_quorum_parks_and_emits_capability_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "child"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "openspec/demo")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    monkeypatch.chdir(repo)
    state_path = repo / "openspec" / "changes" / "demo" / "loop-state.json"
    autopilot.save_state(autopilot.LoopState(change_id="demo", current_phase="PLAN_REVIEW"), state_path)

    marker = {"review_requirements": {"min_quorum": {"PLAN_REVIEW": 2}, "counting_lanes": ["claude_code", "codex"]},
              "execution_profile": {"lanes": {"review": ["claude_code"]}}}
    guard = convergence_loop.converge(
        "demo", "plan", repo, repo,
        min_quorum=marker["review_requirements"]["min_quorum"]["PLAN_REVIEW"],
        orchestrator=_ExplodingOrchestrator(),
        verified_lanes=marker["execution_profile"]["lanes"]["review"],
        counting_lanes=marker["review_requirements"]["counting_lanes"],
    )
    argv = ["park", "demo", "--kind", "capability_unavailable", "--phase", "PLAN_REVIEW"]
    for lane in guard.missing_lanes:
        argv += ["--missing-lane", lane]
    assert runner.main(argv) == 0
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "park")

    assert runner.main(
        ["emit-result", "demo", "--dispatch-id", "d:1", "--generation", "1", "--attempt", "1",
         "--worktree-ref", "demo", "--host-id", "host-a"]
    ) == 0
    result = json.loads((repo / "openspec/changes/demo/dispatch-results/d-1-g1.json").read_text())
    assert result["outcome"] == "parked"
    assert result["parked"]["kind"] == "capability_unavailable"
    assert result["parked"]["missing_lanes"] == ["codex"]


def test_a_standalone_run_below_quorum_records_review_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "openspec" / "changes" / "demo" / "loop-state.json"
    autopilot.save_state(
        autopilot.LoopState(change_id="demo", current_phase="INIT", cli_review_enabled=False), path
    )

    assert runner.main(
        ["record-degradation", "demo", "--code", "review_skipped", "--phase", "PLAN_REVIEW",
         "--detail", "fewer than 2 dispatchable review lanes"]
    ) == 0

    state = json.loads(path.read_text())
    assert state["cli_review_enabled"] is False
    assert [d["code"] for d in state["degradations"]] == ["review_skipped"]
    assert state["degradations"][0]["phase"] == "PLAN_REVIEW"
