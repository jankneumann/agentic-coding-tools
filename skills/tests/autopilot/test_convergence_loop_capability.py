"""Honest quorum after dispatch: mid-run lane loss (design D7).

A round that falls below quorum because a verified lane stopped being able to
review (``vendor_unavailable`` / ``auth_required``) ends
``capability_unavailable`` and names the lost lanes. Any other shortfall stays
``quorum_lost``: an ``unknown`` failure, or a verified lane that returned
nothing at all. ``missing_lanes`` is never vacuous.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import convergence_loop
from review_dispatcher import ErrorClass, ReviewResult

_BUG = {
    "id": 1,
    "type": "bug",
    "criticality": "high",
    "description": "Off-by-one in the retry counter",
    "disposition": "fix",
    "file_path": "src/retry.py",
}


def _ok(lane: str, *, agent_id: str | None = None, **extra) -> ReviewResult:
    return ReviewResult(
        vendor=lane,
        success=True,
        findings={"findings": [dict(_BUG)]},
        model_used=f"{lane}-model",
        models_attempted=[f"{lane}-model"],
        elapsed_seconds=1.0,
        agent_id=agent_id,
        **extra,
    )


def _failed(lane: str, error_class: ErrorClass, *, agent_id: str | None = None) -> ReviewResult:
    return ReviewResult(
        vendor=lane,
        success=False,
        findings=None,
        model_used=None,
        models_attempted=[],
        elapsed_seconds=0.1,
        error=f"{lane} failed",
        error_class=error_class,
        agent_id=agent_id,
    )


class _Scripted:
    """Returns one scripted result list per round."""

    def __init__(self, rounds: list[list[ReviewResult]]) -> None:
        self._rounds = list(rounds)
        self.calls: list[dict] = []

    def dispatch_and_wait(self, review_type, dispatch_mode, prompt, cwd,
                          timeout_seconds=None, packet_path=None, result_callback=None):
        self.calls.append({"review_type": review_type})
        return self._rounds.pop(0)


def _converge(tmp_path: Path, orchestrator, **kwargs):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(exist_ok=True)
    return convergence_loop.converge(
        "demo",
        "plan",
        artifacts,
        tmp_path,
        min_quorum=2,
        orchestrator=orchestrator,
        fix_callback=MagicMock(),
        fact_check=False,
        verified_lanes=["claude_code", "openrouter"],
        counting_lanes=["claude_code", "openrouter"],
        **kwargs,
    )


def _round_one() -> list[ReviewResult]:
    return [_ok("claude_code"), _ok("openrouter", agent_id="openrouter-review")]


@pytest.mark.parametrize("error_class", [ErrorClass.UNAVAILABLE, ErrorClass.AUTH])
def test_a_lane_that_becomes_unavailable_mid_run_is_capability_unavailable(
    tmp_path: Path, error_class: ErrorClass
) -> None:
    orch = _Scripted([
        _round_one(),
        [_ok("claude_code"), _failed("openrouter", error_class, agent_id="openrouter-review")],
    ])

    result = _converge(tmp_path, orch)

    assert result.converged is False
    assert result.rounds == 2
    assert result.reason == "capability_unavailable"
    assert result.missing_lanes == ["openrouter"]
    assert result.checkpoint_dir is not None


def test_an_unknown_failure_mid_run_stays_quorum_lost(tmp_path: Path) -> None:
    orch = _Scripted([
        _round_one(),
        [_ok("claude_code"), _failed("openrouter", ErrorClass.UNKNOWN)],
    ])

    result = _converge(tmp_path, orch)

    assert result.reason == "quorum_lost"
    assert result.rounds == 2
    assert result.missing_lanes == ["openrouter"]


def test_a_verified_lane_with_no_result_is_quorum_lost_not_vacuous(tmp_path: Path) -> None:
    orch = _Scripted([_round_one(), [_ok("claude_code")]])

    result = _converge(tmp_path, orch)

    assert result.reason == "quorum_lost"
    assert result.missing_lanes == ["openrouter"]


def test_one_unavailable_and_one_silent_lane_is_quorum_lost(tmp_path: Path) -> None:
    orch = _Scripted([[_failed("openrouter", ErrorClass.UNAVAILABLE)]])
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    result = convergence_loop.converge(
        "demo", "plan", artifacts, tmp_path,
        min_quorum=2, orchestrator=orch, fact_check=False,
        verified_lanes=["claude_code", "openrouter"],
        counting_lanes=["claude_code", "openrouter"],
    )

    assert result.reason == "quorum_lost"
    assert result.missing_lanes == ["claude_code", "openrouter"]


def test_quorum_lost_without_verified_lanes_keeps_the_legacy_shape(tmp_path: Path) -> None:
    orch = _Scripted([[_failed("codex", ErrorClass.UNAVAILABLE)]])
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    result = convergence_loop.converge(
        "demo", "plan", artifacts, tmp_path,
        min_quorum=2, orchestrator=orch, fact_check=False,
    )

    assert result.reason == "quorum_lost"
    assert result.missing_lanes is None


def test_the_checkpoint_vendor_index_carries_generation_and_cost(tmp_path: Path) -> None:
    metered = _ok(
        "openrouter",
        agent_id="openrouter-review",
        generation_id="gen-abc",
        prompt_tokens=1200,
        completion_tokens=340,
        cost_usd=0.0123,
        cost_source="generation",
    )
    orch = _Scripted([[_ok("claude_code"), metered], [_ok("claude_code")]])

    result = _converge(tmp_path, orch)

    manifest = json.loads(
        (tmp_path / "artifacts" / ".review-cache" / "round-1" / "review-manifest.json").read_text()
    )
    entries = {v["name"]: v for v in manifest["vendors"]}
    assert entries["openrouter"]["generation_id"] == "gen-abc"
    assert entries["openrouter"]["prompt_tokens"] == 1200
    assert entries["openrouter"]["completion_tokens"] == 340
    assert entries["openrouter"]["cost_usd"] == pytest.approx(0.0123)
    assert entries["openrouter"]["cost_source"] == "generation"
    assert entries["claude_code"]["generation_id"] is None
    assert result.reason == "quorum_lost"
