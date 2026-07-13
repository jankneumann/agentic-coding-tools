"""Deterministic goal-gate scorer over pass/fail fixtures."""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_scenarios import ExpectBlock, PRRef, WorkspaceState
from agent_scenarios.models import GoalGate, GoalGatesBlock
from agent_scenarios.scorer import deterministic_status, score_gate, score_gates


def _state(root: Path, **kw: object) -> WorkspaceState:
    return WorkspaceState(root=str(root), **kw)  # type: ignore[arg-type]


def test_file_gate_pass_and_fail(git_workspace: Path) -> None:
    ok = score_gate(GoalGate(id="f", check="file", path="src/app.py"), _state(git_workspace))
    assert ok.status == "pass"
    missing = score_gate(GoalGate(id="f", check="file", path="nope.py"), _state(git_workspace))
    assert missing.status == "fail"


def test_file_contains(git_workspace: Path) -> None:
    hit = score_gate(
        GoalGate(id="f", check="file", path="src/app.py", contains="handler"),
        _state(git_workspace),
    )
    assert hit.status == "pass"
    miss = score_gate(
        GoalGate(id="f", check="file", path="src/app.py", contains="health"),
        _state(git_workspace),
    )
    assert miss.status == "fail"


def test_prohibit_inverts_polarity(git_workspace: Path) -> None:
    # File exists but does not contain 'health' -> prohibit gate PASSES.
    gate = GoalGate(id="p", check="file", path="src/app.py", contains="health", mode="prohibit")
    assert score_gate(gate, _state(git_workspace)).status == "pass"
    # A prohibited file that IS present -> prohibit gate FAILS.
    (git_workspace / ".env").write_text("SECRET=1", encoding="utf-8")
    gate2 = GoalGate(id="p2", check="file", path=".env", mode="prohibit")
    assert score_gate(gate2, _state(git_workspace)).status == "fail"


def test_branch_gate(git_workspace: Path) -> None:
    subprocess.run(["git", "checkout", "-q", "-b", "feature/x"], cwd=git_workspace, check=True)
    assert (
        score_gate(
            GoalGate(id="b", check="branch", branch="feature/x"), _state(git_workspace)
        ).status
        == "pass"
    )
    assert (
        score_gate(GoalGate(id="b", check="branch", branch="nope"), _state(git_workspace)).status
        == "fail"
    )


def test_commit_message_gate(git_workspace: Path) -> None:
    (git_workspace / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=git_workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fix: correct the thing"], cwd=git_workspace, check=True
    )
    ok = score_gate(
        GoalGate(id="c", check="commit", message_contains="(?i)fix"), _state(git_workspace)
    )
    assert ok.status == "pass"
    miss = score_gate(
        GoalGate(id="c", check="commit", message_contains="nonexistent"), _state(git_workspace)
    )
    assert miss.status == "fail"


def test_pr_gate(git_workspace: Path) -> None:
    with_pr = _state(git_workspace, created_pr=PRRef(number=7, head="feature/x", url="http://pr/7"))
    assert score_gate(GoalGate(id="pr", check="pr", pr_head="feature/x"), with_pr).status == "pass"
    assert score_gate(GoalGate(id="pr", check="pr", pr_head="other"), with_pr).status == "fail"
    assert score_gate(GoalGate(id="pr", check="pr"), _state(git_workspace)).status == "fail"


def test_command_gate_uses_expectblock(git_workspace: Path) -> None:
    ok = score_gate(
        GoalGate(
            id="cmd", check="command", command=["git", "status"], expect=ExpectBlock(exit_code=0)
        ),
        _state(git_workspace),
    )
    assert ok.status == "pass"
    bad = score_gate(
        GoalGate(
            id="cmd", check="command", command=["git", "status"], expect=ExpectBlock(exit_code=42)
        ),
        _state(git_workspace),
    )
    assert bad.status == "fail"
    contains = score_gate(
        GoalGate(
            id="cmd",
            check="command",
            command=["git", "log", "--oneline"],
            expect=ExpectBlock(error_contains="fixture: initial state"),
        ),
        _state(git_workspace),
    )
    assert contains.status == "pass"


def test_artifact_key_gate(git_workspace: Path) -> None:
    st = _state(git_workspace, artifacts={"report": "report.md"})
    assert (
        score_gate(GoalGate(id="a", check="artifact", artifact_key="report"), st).status == "pass"
    )
    assert score_gate(GoalGate(id="a", check="artifact", artifact_key="nope"), st).status == "fail"


def test_deterministic_status_rollup(git_workspace: Path) -> None:
    gates = GoalGatesBlock(
        verify=[
            GoalGate(id="ok", check="file", path="src/app.py"),
            GoalGate(id="bad", check="file", path="missing.py"),
        ]
    )
    verdicts = score_gates(gates, _state(git_workspace))
    assert deterministic_status(verdicts) == "fail"

    all_ok = score_gates(
        GoalGatesBlock(verify=[GoalGate(id="ok", check="file", path="src/app.py")]),
        _state(git_workspace),
    )
    assert deterministic_status(all_ok) == "pass"


def test_command_gate_times_out_to_error() -> None:
    from agent_scenarios.models import GoalGate, WorkspaceState
    from agent_scenarios.scorer import score_gate

    gate = GoalGate(
        id="slow",
        check="command",
        command=["python3", "-c", "import time; time.sleep(30)"],
        command_timeout_seconds=1,
    )
    verdict = score_gate(gate, WorkspaceState(root="."))
    assert verdict.status == "error"
    assert "time" in verdict.detail.lower() or "error" in verdict.detail.lower()


def test_goal_gate_rejects_traversal_and_absolute_paths() -> None:
    import pytest

    from agent_scenarios.models import GoalGate

    for bad in ("../escape.txt", "/etc/passwd", "a/../../b"):
        with pytest.raises(ValueError):
            GoalGate(id="p", check="file", path=bad)


def test_command_gate_rejects_unsupported_expect_fields() -> None:
    import pytest
    from gen_eval.models import ExpectBlock

    from agent_scenarios.models import GoalGate

    # exit_code is supported → OK
    GoalGate(id="ok", check="command", command=["true"], expect=ExpectBlock(exit_code=0))
    # body/rows are HTTP-oriented and silently ignored by the command scorer → rejected
    with pytest.raises(ValueError):
        GoalGate(
            id="bad", check="command", command=["true"], expect=ExpectBlock(body="hi")
        )
