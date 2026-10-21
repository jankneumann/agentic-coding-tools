"""The committed agent-lane converge driver (``agent_lane.py``).

Replaces per-session scratch drivers, which the auto-mode classifier refuses to
run as external code. The agent serving the lane is simulated by a thread that
answers the file handshake.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import agent_lane

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "validate-feature" / "scripts"))
import gate_logic  # noqa: E402

POLICY = {
    "min_quorum": {"PLAN_REVIEW": 1, "IMPL_REVIEW": 1, "VAL_REVIEW": 1},
    "environment": "cloud_container",
    "policy_id": "cloud-single-vendor",
    "sunset": None,
}


def _policy(**_: Any) -> dict[str, Any]:
    return POLICY


def _serve(proto: Path, *, rounds: int, fix_rounds: tuple[int, ...] = ()) -> threading.Thread:
    """Answer each review request with an empty findings file and each fix request."""

    def run() -> None:
        hs = agent_lane.Handshake(proto, timeout_seconds=10, poll_seconds=0.01)
        for n in range(1, rounds + 1):
            hs.wait_for(f"awaiting-review-{n}")
            (proto / f"findings-round-{n}.json").write_text(json.dumps({"findings": []}))
            if n in fix_rounds:
                hs.wait_for(f"fix-request-round-{n}.json")
                (proto / f"fix-done-round-{n}").touch()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def _change_dir(worktree: Path, change_id: str = "demo") -> Path:
    change_dir = worktree / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True)
    (change_dir / "validation-report.md").write_text(
        "# Validation Report\n\n## Spec Compliance\n\n**Status**: pass\n"
    )
    return change_dir


def _fake_converge(*, review_rounds: int, fix_round: int | None = None, converged: bool = True):
    calls: dict[str, Any] = {}

    def converge(**kwargs: Any) -> SimpleNamespace:
        calls.update(kwargs)
        orch = kwargs["orchestrator"]
        for n in range(1, review_rounds + 1):
            orch.dispatch_and_wait(
                kwargs["review_type"], "review", "prompt", kwargs["worktree_path"],
                packet_path=Path(f"/packets/round-{n}.md"),
            )
            if fix_round == n:
                kwargs["fix_callback"]([{"id": "F1"}], kwargs["worktree_path"])
        return SimpleNamespace(
            converged=converged, rounds=review_rounds, reason=None, consensus={"summary": "0 blocking"},
            escalate_findings=[], validation_errors=[], checkpoint_dir=None,
        )

    return converge, calls


def test_val_review_converges_and_writes_the_section_the_goal_gate_reads(tmp_path: Path) -> None:
    worktree, proto = tmp_path / "wt", tmp_path / "proto"
    change_dir = _change_dir(worktree)
    server = _serve(proto, rounds=2, fix_rounds=(1,))
    converge, calls = _fake_converge(review_rounds=2, fix_round=1)

    out = agent_lane.run_converge(
        change_id="demo", phase="VAL_REVIEW", worktree=worktree, proto_dir=proto,
        base_ref="origin/base", model="model-x", timeout_seconds=10, poll_seconds=0.01,
        converge_fn=converge, policy_fn=_policy,
    )
    server.join(timeout=5)

    assert out["converged"] is True and out["report_section_written"] == "Validation Review"
    report = str(change_dir / "validation-report.md")
    assert gate_logic.check_phase_status(report, "Validation Review") == "pass"
    assert gate_logic.check_phase_status(report, "Spec Compliance") == "pass"
    assert calls["review_type"] == "implementation"
    assert calls["min_quorum"] == 1
    assert calls["base_ref"] == "origin/base"
    assert calls["verified_lanes"] == calls["counting_lanes"] == ["claude_code"]
    events = [json.loads(line)["event"] for line in (proto / "events.jsonl").read_text().splitlines()]
    assert events.count("review_received") == 2
    assert "phase_history_substep" in events
    assert json.loads((proto / "result.json").read_text())["converged"] is True


def test_a_review_result_records_the_given_model(tmp_path: Path) -> None:
    proto = tmp_path / "proto"
    server = _serve(proto, rounds=1)
    orch = agent_lane.AgentLaneOrchestrator(agent_lane.Handshake(proto, timeout_seconds=10, poll_seconds=0.01), model="model-x")

    [result] = orch.dispatch_and_wait("plan", "review", "p", tmp_path)
    server.join(timeout=5)

    assert (result.vendor, result.model_used, result.success) == ("claude_code", "model-x", True)


def test_an_unconverged_val_review_leaves_the_report_untouched(tmp_path: Path) -> None:
    worktree, proto = tmp_path / "wt", tmp_path / "proto"
    change_dir = _change_dir(worktree)
    before = (change_dir / "validation-report.md").read_text()
    server = _serve(proto, rounds=1)
    converge, _ = _fake_converge(review_rounds=1, converged=False)

    out = agent_lane.run_converge(
        change_id="demo", phase="VAL_REVIEW", worktree=worktree, proto_dir=proto,
        base_ref=None, model="m", timeout_seconds=10, poll_seconds=0.01,
        converge_fn=converge, policy_fn=_policy,
    )
    server.join(timeout=5)

    assert out["converged"] is False
    assert (change_dir / "validation-report.md").read_text() == before


@pytest.mark.parametrize("phase, review_type", [("PLAN_REVIEW", "plan"), ("IMPL_REVIEW", "implementation")])
def test_other_phases_map_review_type_and_do_not_touch_the_report(
    tmp_path: Path, phase: str, review_type: str
) -> None:
    worktree, proto = tmp_path / "wt", tmp_path / "proto"
    change_dir = _change_dir(worktree)
    before = (change_dir / "validation-report.md").read_text()
    server = _serve(proto, rounds=1)
    converge, calls = _fake_converge(review_rounds=1)

    agent_lane.run_converge(
        change_id="demo", phase=phase, worktree=worktree, proto_dir=proto, base_ref=None,
        model="m", timeout_seconds=10, poll_seconds=0.01, converge_fn=converge, policy_fn=_policy,
    )
    server.join(timeout=5)

    assert calls["review_type"] == review_type
    assert (change_dir / "validation-report.md").read_text() == before


def test_writing_the_section_twice_replaces_it(tmp_path: Path) -> None:
    report = tmp_path / "validation-report.md"
    report.write_text("# R\n\n## Validation Review\n\n**Status**: fail\n\nold\n\n## Later\n\n**Status**: pass\n")

    agent_lane.write_validation_review_section(report, status="pass", body="- new")
    agent_lane.write_validation_review_section(report, status="pass", body="- newer")

    text = report.read_text()
    assert text.count("## Validation Review") == 1
    assert "old" not in text and "- newer" in text and "## Later" in text
    assert gate_logic.check_phase_status(str(report), "Validation Review") == "pass"
    assert gate_logic.check_phase_status(str(report), "Later") == "pass"


def test_a_lane_that_never_answers_times_out(tmp_path: Path) -> None:
    ticks = iter(range(100))
    hs = agent_lane.Handshake(tmp_path, timeout_seconds=3, sleep=lambda _s: None, clock=lambda: next(ticks))

    with pytest.raises(TimeoutError):
        hs.wait_for("findings-round-1.json")


def test_an_error_inside_converge_is_recorded_not_raised(tmp_path: Path) -> None:
    worktree, proto = tmp_path / "wt", tmp_path / "proto"
    _change_dir(worktree)

    def boom(**_: Any) -> None:
        raise RuntimeError("lane failed")

    out = agent_lane.run_converge(
        change_id="demo", phase="IMPL_REVIEW", worktree=worktree, proto_dir=proto, base_ref=None,
        model="m", converge_fn=boom, policy_fn=_policy,
    )

    assert out == {"phase": "IMPL_REVIEW", "converged": False, "error": "RuntimeError: lane failed"}
    assert json.loads((proto / "result.json").read_text())["error"] == "RuntimeError: lane failed"


def test_a_findings_file_caught_mid_write_is_re_read(tmp_path: Path) -> None:
    (tmp_path / "findings-round-1.json").write_text('{"findings": [')
    reads = iter(range(100))

    def finish_write(_s: float) -> None:
        if next(reads) == 1:
            (tmp_path / "findings-round-1.json").write_text('{"findings": []}')

    hs = agent_lane.Handshake(tmp_path, timeout_seconds=10, sleep=finish_write)

    assert hs.read_json("findings-round-1.json") == {"findings": []}


def test_a_reused_proto_dir_does_not_answer_with_a_previous_runs_findings(tmp_path: Path) -> None:
    worktree, proto = tmp_path / "wt", tmp_path / "proto"
    _change_dir(worktree)
    proto.mkdir()
    (proto / "findings-round-1.json").write_text(json.dumps({"findings": []}))
    (proto / "fix-done-round-1").touch()
    converge, _ = _fake_converge(review_rounds=1)

    out = agent_lane.run_converge(
        change_id="demo", phase="VAL_REVIEW", worktree=worktree, proto_dir=proto, base_ref=None,
        model="m", timeout_seconds=0.2, poll_seconds=0.01, converge_fn=converge, policy_fn=_policy,
    )

    # No agent answers this run, so round 1 times out instead of converging on old files.
    assert out["converged"] is False and out["error"].startswith("TimeoutError")
    assert "report_section_written" not in out
    events = [json.loads(line) for line in (proto / "events.jsonl").read_text().splitlines()]
    assert events[0]["event"] == "stale_round_files_removed"
    assert events[0]["files"] == ["findings-round-1.json", "fix-done-round-1"]


def test_cli_rejects_an_unknown_phase() -> None:
    with pytest.raises(SystemExit):
        agent_lane.main(["converge", "--change-id", "d", "--phase", "VALIDATE", "--proto-dir", "p", "--model", "m"])


# --------------------------------------------------------------------------- #
# 5.4: the composite agent lane (design D7)
# --------------------------------------------------------------------------- #

_LOW_FINDING = {
    "id": 1,
    "type": "correctness",
    "criticality": "low",
    "description": "The retry section does not say what a second timeout does",
    "disposition": "accept",
    "axis": "correctness",
    "severity": "nit",
    "evidence_class": "judgment",  # low judgment never blocks (D3), so round 1 converges
    "file_path": "proposal.md",
}
_BLOCKING_FINDING = {
    **_LOW_FINDING,
    "criticality": "high",
    "disposition": "fix",
    "severity": "critical",
    "evidence_class": "deterministic",
}


def _findings(*findings: dict[str, Any]) -> dict[str, Any]:
    return {"review_type": "plan", "target": "demo", "findings": [dict(f) for f in findings]}


class _ChatTransport:
    """Chat-completions stand-in: one scripted review per call, never the network."""

    def __init__(self, *reviews: dict[str, Any]) -> None:
        self._reviews = list(reviews)
        self.calls = 0

    def __call__(self, url: str, headers: dict[str, str], payload: dict, timeout: float):
        self.calls += 1
        review = self._reviews[min(self.calls, len(self._reviews)) - 1]
        return {
            "id": f"gen-test-{self.calls}",
            "choices": [{"message": {"content": json.dumps(review)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }


class _ProbeTransport:
    def __call__(self, url: str, headers: dict[str, str], timeout: float):
        return 200, {"data": {"limit": 20.0, "limit_remaining": 15.0, "usage": 0.0}}


class _FakeRecorder:
    """Stands in for the ``spend_recorder`` module; never posts anything."""

    def __init__(self, *, recorded: bool = True) -> None:
        self.recorded = recorded
        self.rows: list[tuple[dict, str]] = []

    def row_from_review_result(self, result: Any, **kwargs: Any) -> dict:
        import spend_recorder

        return spend_recorder.row_from_review_result(result, **kwargs)

    def record(self, row: dict, *, change_id: str, **_: Any):
        from spend_recorder import RecordOutcome

        self.rows.append((dict(row), change_id))
        return RecordOutcome(recorded=self.recorded, spooled=not self.recorded)

    def spooled_total_usd(self, change_id: str, **_: Any) -> float:
        return 0.0


@pytest.fixture
def metered(monkeypatch: pytest.MonkeyPatch):
    """Build a real ``ReviewOrchestrator`` with one OpenRouter lane on injected transports."""
    import openai_compat_adapter
    import review_dispatcher

    def _no_network(*_a: Any, **_k: Any) -> None:
        raise AssertionError("no real HTTP request may be sent")

    monkeypatch.setattr(openai_compat_adapter, "_default_transport", _no_network)
    monkeypatch.setattr(openai_compat_adapter, "_default_get_transport", _no_network)
    monkeypatch.setattr(
        review_dispatcher, "_resolve_review_model_spec",
        lambda vendor: ("nvidia/nemotron", None) if vendor == "openrouter" else (None, None),
    )
    monkeypatch.setattr(review_dispatcher, "_derived_tier_fallbacks", lambda _vendor: [])
    monkeypatch.delenv("BAO_ADDR", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-not-a-real-key")

    def build(*, chat: _ChatTransport, recorder: _FakeRecorder, usage: dict[str, Any]):
        return review_dispatcher.ReviewOrchestrator.from_config_dict(
            {"agents": [{
                "agent_id": "openrouter-review", "type": "openrouter", "transport": "http",
                "endpoint_kind": "openrouter", "base_url": "https://openrouter.ai/api/v1",
            }]},
            lane_policy=review_dispatcher.LanePolicy(
                vendor_families={"claude_code": "anthropic", "codex": "openai"},
                fill_target=2,
                review_reservation_usd=1.0,
            ),
            openai_transport=chat,
            probe_transport=_ProbeTransport(),
            usage_fetcher=lambda: usage,
            spend_recorder=recorder,
        )

    return build


def _plan_fixture(worktree: Path) -> Path:
    change_dir = _change_dir(worktree)
    (change_dir / "proposal.md").write_text("# Proposal\n\nRetry a timed-out review once.\n")
    (change_dir / "tasks.md").write_text("## 1. Retry\n\n- [ ] 1.1 Retry once\n")
    return change_dir


def _serve_findings(proto: Path, rounds: list[dict[str, Any]], *, before_fix=None) -> threading.Thread:
    """Answer review round N with ``rounds[N-1]``; acknowledge each fix request between rounds."""

    def run() -> None:
        hs = agent_lane.Handshake(proto, timeout_seconds=20, poll_seconds=0.01)
        for n, findings in enumerate(rounds, start=1):
            hs.wait_for(f"awaiting-review-{n}")
            (proto / f"findings-round-{n}.json").write_text(json.dumps(findings))
            if n < len(rounds):
                hs.wait_for(f"fix-request-round-{n}.json")
                if before_fix is not None:
                    before_fix(n)
                (proto / f"fix-done-round-{n}").touch()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def _run_composite(tmp_path: Path, review_orchestrator: Any, *, phase: str = "PLAN_REVIEW", **kwargs: Any):
    return agent_lane.run_converge(
        change_id="demo", phase=phase, worktree=tmp_path / "wt", proto_dir=tmp_path / "proto",
        base_ref=None, model="model-x", timeout_seconds=20, poll_seconds=0.01,
        verified_lanes=["claude_code", "openrouter"],
        review_orchestrator_factory=lambda: review_orchestrator,
        **kwargs,
    )


def test_a_composite_plan_review_counts_both_lanes(tmp_path: Path, metered, monkeypatch) -> None:
    import convergence_loop

    change_dir = _plan_fixture(tmp_path / "wt")
    recorder = _FakeRecorder()
    review = metered(chat=_ChatTransport(_findings(_LOW_FINDING)), recorder=recorder, usage={})
    server = _serve_findings(tmp_path / "proto", [_findings(_LOW_FINDING)])
    seen: dict[str, Any] = {}
    real_converge = convergence_loop.converge

    def spy(*args: Any, **kwargs: Any):
        seen.update(kwargs)
        return real_converge(*args, **kwargs)

    monkeypatch.setattr(convergence_loop, "converge", spy)
    out = _run_composite(tmp_path, review)
    server.join(timeout=10)

    assert out["converged"] is True, out
    assert seen["min_quorum"] == 2 and out["policy"]["policy_id"] is None
    assert seen["verified_lanes"] == seen["counting_lanes"] == ["claude_code", "openrouter"]
    assert seen["phase"] == "PLAN_REVIEW"
    checkpoint = Path(out["checkpoint_dir"])
    assert (checkpoint / "findings-claude_code-plan.json").is_file()
    assert (checkpoint / "findings-openrouter-plan.json").is_file()
    assert out["quorum_received"] == 2
    assert out["lanes"] == ["claude_code", "openrouter"]
    assert out["missing_lanes"] is None
    assert out["degradations"] == []
    assert out["lane_results"]["openrouter"]["generation_id"] == "gen-test-1"
    assert out["lane_results"]["openrouter"]["model_used"] == "nvidia/nemotron"
    assert out["lane_results"]["claude_code"]["model_used"] == "model-x"

    consensus = json.loads((change_dir / "reviews" / "consensus-plan.json").read_text())
    assert consensus["quorum_received"] == 2
    assert {r["vendor"] for r in consensus["reviewers"]} >= {"claude_code", "openrouter"}
    [finding] = consensus["consensus_findings"]
    assert finding["status"] == "confirmed"
    assert set(finding["vendor_hits"]) == {"claude_code", "openrouter"}
    [(row, change_id)] = recorder.rows
    assert change_id == "demo" and row["work_unit_ref"] == "demo:PLAN_REVIEW:round-1"


def test_unrecorded_metered_spend_is_a_degradation_in_the_result(tmp_path: Path, metered) -> None:
    _plan_fixture(tmp_path / "wt")
    review = metered(
        chat=_ChatTransport(_findings(_LOW_FINDING)), recorder=_FakeRecorder(recorded=False), usage={},
    )
    server = _serve_findings(tmp_path / "proto", [_findings(_LOW_FINDING)])

    out = _run_composite(tmp_path, review)
    server.join(timeout=10)

    assert out["converged"] is True
    assert out["degradations"] == [{
        "code": "metered_spend_unrecorded",
        "phase": "PLAN_REVIEW",
        "detail": "openrouter round 1 spend not recorded",
    }]
    saved = json.loads((tmp_path / "proto" / "result.json").read_text())
    assert saved["degradations"] == out["degradations"]


def test_the_agent_lane_alone_below_quorum_is_capability_unavailable(tmp_path: Path) -> None:
    worktree, proto = tmp_path / "wt", tmp_path / "proto"
    change_dir = _plan_fixture(worktree)

    def never_built() -> Any:
        raise AssertionError("no review orchestrator is needed for the agent lane alone")

    out = agent_lane.run_converge(
        change_id="demo", phase="PLAN_REVIEW", worktree=worktree, proto_dir=proto, base_ref=None,
        model="m", environment="host", timeout_seconds=1, poll_seconds=0.01,
        verified_lanes=["claude_code"], counting_lanes=["claude_code", "openrouter"],
        review_orchestrator_factory=never_built,
    )

    assert out["converged"] is False and out["rounds"] == 0
    assert out["min_quorum"] == 2
    assert out["reason"] == "capability_unavailable"
    assert out["missing_lanes"] == ["openrouter"]
    assert out["lanes"] == []
    assert not list(proto.glob("awaiting-review-*")) and not list(proto.glob("fix-request-*"))
    assert not (change_dir / "reviews").exists()


def test_verified_lanes_are_deduplicated_with_the_agent_lane_first(tmp_path: Path) -> None:
    worktree, proto = tmp_path / "wt", tmp_path / "proto"
    _change_dir(worktree)
    converge, calls = _fake_converge(review_rounds=0)
    counts: list[int] = []

    def policy(**kwargs: Any) -> dict[str, Any]:
        counts.append(kwargs["verified_review_lanes"])
        return POLICY

    agent_lane.run_converge(
        change_id="demo", phase="IMPL_REVIEW", worktree=worktree, proto_dir=proto, base_ref=None,
        model="m", converge_fn=converge, policy_fn=policy,
        verified_lanes=["openrouter", "claude_code", "openrouter"],
    )

    assert calls["verified_lanes"] == ["claude_code", "openrouter"]
    assert counts == [2]
    assert calls["phase"] == "IMPL_REVIEW"


def test_cli_passes_repeated_verified_and_counting_lanes(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_run(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"converged": True}

    monkeypatch.setattr(agent_lane, "run_converge", fake_run)
    assert agent_lane.main([
        "converge", "--change-id", "d", "--phase", "PLAN_REVIEW", "--proto-dir", "p", "--model", "m",
        "--verified-lanes", "claude_code", "--verified-lanes", "openrouter",
        "--counting-lanes", "claude_code", "--counting-lanes", "openrouter",
    ]) == 0
    assert seen["verified_lanes"] == ["claude_code", "openrouter"]
    assert seen["counting_lanes"] == ["claude_code", "openrouter"]


def test_a_composite_val_review_section_lists_both_lanes(tmp_path: Path) -> None:
    worktree, proto = tmp_path / "wt", tmp_path / "proto"
    change_dir = _change_dir(worktree)
    two_lane_policy = {**POLICY, "min_quorum": {p: 2 for p in POLICY["min_quorum"]}, "policy_id": None}

    def converge(**kwargs: Any) -> SimpleNamespace:
        kwargs["orchestrator"].results_by_round.append([
            SimpleNamespace(vendor="claude_code", agent_id="claude_code", success=True,
                            model_used="m", generation_id=None, cost_usd=None, cost_source=None,
                            spend_recorded=None),
            SimpleNamespace(vendor="openrouter", agent_id="openrouter-review", success=True,
                            model_used="nvidia/nemotron", generation_id="gen-1", cost_usd=0.01,
                            cost_source="reported", spend_recorded=True),
        ])
        return SimpleNamespace(
            converged=True, rounds=1, reason=None, missing_lanes=None,
            consensus={"summary": "0 blocking", "quorum_received": 2},
            escalate_findings=[], validation_errors=[], checkpoint_dir=None,
        )

    out = agent_lane.run_converge(
        change_id="demo", phase="VAL_REVIEW", worktree=worktree, proto_dir=proto, base_ref=None,
        model="m", converge_fn=converge, policy_fn=lambda **_: two_lane_policy,
        verified_lanes=["claude_code", "openrouter"],
    )

    report = (change_dir / "validation-report.md").read_text()
    assert "`claude_code`, `openrouter`" in report
    assert "single_vendor_review" not in report
    assert out["lane_results"]["openrouter"]["cost_usd"] == 0.01
    consensus = json.loads((change_dir / "reviews" / "consensus-val-review.json").read_text())
    assert consensus["quorum_received"] == 2


# --------------------------------------------------------------------------- #
# 5.7: the dispatcher's budget re-check fails before round 2 (design D7)
# --------------------------------------------------------------------------- #


def test_a_budget_exhausted_before_round_two_is_capability_unavailable(
    tmp_path: Path, metered
) -> None:
    _plan_fixture(tmp_path / "wt")
    usage = {"metered_ceiling_usd": 50.0, "metered_usd_used": 10.0}
    chat = _ChatTransport(_findings(_BLOCKING_FINDING))
    review = metered(chat=chat, recorder=_FakeRecorder(), usage=usage)

    def spend_elsewhere(_round: int) -> None:
        usage["metered_usd_used"] = 49.5  # the ceiling leaves less than one reservation

    server = _serve_findings(
        tmp_path / "proto", [_findings(_BLOCKING_FINDING), _findings()], before_fix=spend_elsewhere,
    )

    out = _run_composite(tmp_path, review)
    server.join(timeout=10)

    assert out["converged"] is False
    assert out["rounds"] == 2
    assert out["reason"] == "capability_unavailable"
    assert out["missing_lanes"] == ["openrouter"]
    assert chat.calls == 1  # round 2 sent no request
    assert out["lane_results"]["openrouter"]["success"] is False
    assert out["lanes"] == ["claude_code", "openrouter"]
    saved = json.loads((tmp_path / "proto" / "result.json").read_text())
    assert saved["reason"] == "capability_unavailable" and saved["missing_lanes"] == ["openrouter"]


# --------------------------------------------------------------------------- #
# The dispatcher's cross-vendor warning inside the composite
# --------------------------------------------------------------------------- #


def test_a_composite_round_does_not_warn_cross_vendor_not_checked(
    tmp_path: Path, metered, capsys: pytest.CaptureFixture[str]
) -> None:
    """The dispatcher sees only the non-handshake lanes; the composite round is still two vendors."""
    _plan_fixture(tmp_path / "wt")
    review = metered(chat=_ChatTransport(_findings(_LOW_FINDING)), recorder=_FakeRecorder(), usage={})
    server = _serve_findings(tmp_path / "proto", [_findings(_LOW_FINDING)])
    out = _run_composite(tmp_path, review)
    server.join(timeout=10)

    assert out["converged"] is True, out
    assert "NOT CHECKED" not in capsys.readouterr().err


def _dispatch_openrouter_only(review: Any, cwd: Path, **kwargs: Any) -> list[Any]:
    import review_dispatcher

    return review.dispatch_and_wait(
        "plan", "review", "prompt", cwd,
        include_lanes=["openrouter"],
        spend_context=review_dispatcher.SpendContext(change_id="demo", work_unit_ref="demo:r1"),
        **kwargs,
    )


def test_a_standalone_single_vendor_dispatch_still_warns(
    tmp_path: Path, metered, capsys: pytest.CaptureFixture[str]
) -> None:
    review = metered(chat=_ChatTransport(_findings(_LOW_FINDING)), recorder=_FakeRecorder(), usage={})
    results = _dispatch_openrouter_only(review, tmp_path)

    assert [r.success for r in results] == [True]
    err = capsys.readouterr().err
    assert "Cross-vendor plan review NOT CHECKED" in err
    assert "only 1 of 2" in err


def test_caller_vendors_count_toward_the_cross_vendor_minimum(
    tmp_path: Path, metered, capsys: pytest.CaptureFixture[str]
) -> None:
    review = metered(chat=_ChatTransport(_findings(_LOW_FINDING)), recorder=_FakeRecorder(), usage={})
    _dispatch_openrouter_only(review, tmp_path, caller_vendors=["claude_code"])

    assert "NOT CHECKED" not in capsys.readouterr().err

