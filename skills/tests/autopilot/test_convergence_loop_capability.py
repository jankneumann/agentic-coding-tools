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


# --------------------------------------------------------------------------- #
# 5.3: the metered_spend_unrecorded degradation code
# --------------------------------------------------------------------------- #


def test_metered_spend_unrecorded_is_a_closed_degradation_code() -> None:
    import jsonschema

    import runner

    dispatch_contract = runner.dispatch_contract
    schema = dispatch_contract.load_schema(dispatch_contract.RESULT_V2)
    degradation = schema["$defs"]["Degradation"]
    assert "metered_spend_unrecorded" in degradation["properties"]["code"]["enum"]
    jsonschema.Draft202012Validator(degradation).validate(
        {"code": "metered_spend_unrecorded", "phase": "PLAN_REVIEW", "detail": "openrouter round 1"}
    )


def test_runner_records_a_metered_spend_unrecorded_degradation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import autopilot
    import runner

    monkeypatch.chdir(tmp_path)
    path = tmp_path / "openspec" / "changes" / "demo" / "loop-state.json"
    autopilot.save_state(autopilot.LoopState(change_id="demo", current_phase="PLAN_REVIEW"), path)

    assert runner.main(
        ["record-degradation", "demo", "--code", "metered_spend_unrecorded",
         "--phase", "PLAN_REVIEW", "--detail", "openrouter round 1 spend not recorded"]
    ) == 0

    state = json.loads(path.read_text())
    assert [d["code"] for d in state["degradations"]] == ["metered_spend_unrecorded"]


# --------------------------------------------------------------------------- #
# 5.6: spend attribution and the tool-less packet
# --------------------------------------------------------------------------- #


class _Recording:
    """Accepts the dispatcher's keyword-only extras and records them."""

    def __init__(self, rounds: list[list[ReviewResult]]) -> None:
        self._rounds = list(rounds)
        self.kwargs: list[dict] = []

    def dispatch_and_wait(self, review_type, dispatch_mode, prompt, cwd,
                          timeout_seconds=None, packet_path=None, result_callback=None,
                          *, include_lanes=None, toolless_packet_path=None, spend_context=None):
        self.kwargs.append({
            "toolless_packet_path": toolless_packet_path,
            "spend_context": spend_context,
        })
        return self._rounds.pop(0)


def _two_rounds_then_lost() -> list[list[ReviewResult]]:
    return [_round_one(), [_ok("claude_code")]]


def test_a_phase_attributes_each_rounds_spend(tmp_path: Path) -> None:
    from review_dispatcher import SpendContext

    orch = _Recording(_two_rounds_then_lost())

    _converge(tmp_path, orch, phase="PLAN_REVIEW")

    assert [k["spend_context"] for k in orch.kwargs] == [
        SpendContext("demo", "demo:PLAN_REVIEW:round-1"),
        SpendContext("demo", "demo:PLAN_REVIEW:round-2"),
    ]


def test_without_a_phase_no_spend_context_is_passed(tmp_path: Path) -> None:
    orch = _Recording(_two_rounds_then_lost())

    _converge(tmp_path, orch)

    assert [k["spend_context"] for k in orch.kwargs] == [None, None]


def test_an_orchestrator_without_the_keyword_still_runs_with_a_phase(tmp_path: Path) -> None:
    result = _converge(tmp_path, _Scripted(_two_rounds_then_lost()), phase="PLAN_REVIEW")

    assert result.reason == "quorum_lost"


def _stub_packets(monkeypatch: pytest.MonkeyPatch, *, overflow: bool) -> list[dict]:
    toolless_calls: list[dict] = []

    def primary(**kwargs):
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        path = out / "review-packet.md"
        path.write_text("PRIMARY", encoding="utf-8")
        return path, {"tools_overflow": overflow}

    def toolless(**kwargs):
        toolless_calls.append(kwargs)
        path = Path(kwargs["output_dir"]) / "review-packet.toolless.md"
        path.write_text("TOOLLESS", encoding="utf-8")
        return path, {"tools_overflow": False}

    monkeypatch.setattr(convergence_loop, "build_review_packet", primary)
    monkeypatch.setattr(convergence_loop, "build_toolless_packet", toolless)
    return toolless_calls


def test_an_overflowing_packet_gets_a_toolless_companion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_packets(monkeypatch, overflow=True)
    orch = _Recording(_two_rounds_then_lost())

    _converge(tmp_path, orch, base_ref="origin/base")

    assert len(calls) == 2
    assert calls[0]["review_type"] == "plan"
    assert calls[0]["round_num"] == 1
    assert calls[0]["base_ref"] == "origin/base"
    assert calls[0]["last_fix_diff"] is None
    assert calls[1]["last_fix_diff"] is not None
    paths = [k["toolless_packet_path"] for k in orch.kwargs]
    assert [p.name for p in paths] == ["review-packet.toolless.md"] * 2
    assert paths[0].parent.name == "round-1" and paths[1].parent.name == "round-2"


def test_a_packet_that_fits_has_no_toolless_companion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_packets(monkeypatch, overflow=False)
    orch = _Recording(_two_rounds_then_lost())

    _converge(tmp_path, orch)

    assert calls == []
    assert [k["toolless_packet_path"] for k in orch.kwargs] == [None, None]
