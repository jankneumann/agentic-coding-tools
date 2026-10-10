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
