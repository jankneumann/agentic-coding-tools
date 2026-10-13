"""`runner.py emit-result` (dispatch-contract Code-Emitted Dispatch Result, D4).

Every terminal and parked loop-state shape is committed in a real git
repository, emitted, and validated against the published result schema. The
mapping is the normative one in ``dispatch_contract.result_from_loop_state``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import autopilot
import runner

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared import dispatch_contract  # noqa: E402

_DISPATCH_ID = "batch-0123456789abcdef01234567:ri-01:attempt-1"
_CHILD_GATES = [
    "gatekeeper_escalation",
    "proposal_approval",
    "plan_review_convergence_failure",
    "validation_failure",
    "escalate_resume",
    "replan_required",
    "pr_creation",
    "merge",
]


def _git(repo: Path, *argv: str) -> None:
    subprocess.run(["git", *argv], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "child"
    root.mkdir()
    _git(root, "init", "-q", "-b", "openspec/demo")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    monkeypatch.chdir(root)
    return root


def _commit_state(repo: Path, **fields: Any) -> Path:
    state = autopilot.LoopState(change_id="demo", current_phase="IMPLEMENT")
    for key, value in fields.items():
        setattr(state, key, value)
    path = repo / "openspec" / "changes" / "demo" / "loop-state.json"
    autopilot.save_state(state, path)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "state")
    return path


def _emit(generation: int = 1) -> int:
    return runner.main(
        [
            "emit-result", "demo",
            "--dispatch-id", _DISPATCH_ID,
            "--generation", str(generation),
            "--attempt", "1",
            "--worktree-ref", "demo",
            "--host-id", "host-a",
        ]
    )


def _written(repo: Path, generation: int = 1) -> dict[str, Any]:
    path = repo / dispatch_contract.result_relpath("demo", _DISPATCH_ID, generation)
    return json.loads(path.read_text())


_SHAPES: list[tuple[str, dict[str, Any], str, str | None, str | None]] = [
    (
        "done-passed",
        {"current_phase": "DONE", "goal_gate": {"verdict": "passed"}, "last_handoff_id": "h-1"},
        "success", None, None,
    ),
    ("done-abandoned", {"current_phase": "DONE", "goal_gate": {"verdict": "abandoned"}}, "failed:abandoned", None, None),
    (
        "done-refused",
        {"current_phase": "DONE", "goal_gate": {"verdict": "refused"}, "last_handoff_id": "h-1"},
        "failed:goal_gate_unverified", None, None,
    ),
    (
        "escalate",
        {"current_phase": "ESCALATE", "previous_phase": "PLAN_REVIEW", "escalation_reason": "max_iter"},
        "parked", "policy_pause", None,
    ),
    *[
        (
            f"pending-{gate}",
            {"current_phase": "PLAN", "pending_gate": {"gate": gate, "prompt": "Approve?"}},
            "parked", "pending_gate", gate,
        )
        for gate in _CHILD_GATES
    ],
    (
        "park-permission",
        {
            "park": {
                "kind": "permission_blocked",
                "tool": "Bash",
                "rule": "Bash(env *)",
                "classifier_reason": "reads credentials",
                "command": "env",
                "reason": "denied",
            }
        },
        "parked", "permission_blocked", None,
    ),
    (
        "park-capability",
        {
            "park": {
                "kind": "capability_unavailable",
                "phase": "PLAN_REVIEW",
                "missing_lanes": ["codex"],
                "reason": "quorum 2 unmet",
            }
        },
        "parked", "capability_unavailable", None,
    ),
]


@pytest.mark.parametrize(
    ("name", "fields", "outcome", "kind", "gate"), _SHAPES, ids=[s[0] for s in _SHAPES]
)
def test_every_terminal_and_parked_shape_maps_to_a_schema_valid_result(
    repo: Path, name: str, fields: dict[str, Any], outcome: str, kind: str | None, gate: str | None
) -> None:
    state_path = _commit_state(repo, **fields)

    assert _emit() == 0

    result = _written(repo)
    assert dispatch_contract.validate_result(result) == result
    assert result["outcome"] == outcome
    assert (result.get("parked") or {}).get("kind") == kind
    if kind == "pending_gate":
        assert result["parked"]["gate"] == gate
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert result["evidence"]["commit"] == head
    assert result["evidence"]["loop_state_path"] == "openspec/changes/demo/loop-state.json"
    import hashlib

    assert result["evidence"]["loop_state_digest"] == hashlib.sha256(state_path.read_bytes()).hexdigest()


def test_a_parked_result_is_never_produced_without_its_loop_state_evidence(repo: Path) -> None:
    """ri-02: a 'parked' result whose loop state is neither ESCALATE, a
    pending gate nor a park was rejected at apply. emit-result derives the
    outcome from those very fields, so that shape cannot be produced: an
    IMPLEMENT state with none of them is not terminal."""
    _commit_state(repo, current_phase="IMPLEMENT")
    assert _emit() == dispatch_contract.EXIT_NOT_TERMINAL
    for _name, fields, outcome, _kind, _gate in _SHAPES:
        if outcome != "parked":
            continue
        assert fields.get("park") or fields.get("pending_gate") or fields.get("current_phase") == "ESCALATE"


def test_a_non_terminal_phase_produces_no_result(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _commit_state(repo, current_phase="IMPLEMENT")

    assert _emit() == 5
    assert "runner: loop state is not terminal or parked" in capsys.readouterr().err
    assert not (repo / "openspec/changes/demo/dispatch-results").exists()


def test_uncommitted_loop_state_is_refused(repo: Path) -> None:
    path = _commit_state(repo, current_phase="DONE", goal_gate={"verdict": "abandoned"})
    path.write_text(path.read_text().replace('"DONE"', '"ESCALATE"'))

    assert _emit() == 2
    assert not (repo / "openspec/changes/demo/dispatch-results").exists()


def test_abandoned_work_is_not_reported_as_success(repo: Path) -> None:
    state = autopilot.LoopState(change_id="demo", current_phase="ESCALATE", previous_phase="PLAN")
    autopilot._apply_transition(state, "abandoned")
    path = repo / "openspec" / "changes" / "demo" / "loop-state.json"
    autopilot.save_state(state, path)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "abandoned")

    assert _emit() == 0
    assert _written(repo)["outcome"] == "failed:abandoned"


def test_the_result_file_is_named_by_slug_and_generation(repo: Path) -> None:
    _commit_state(repo, current_phase="DONE", goal_gate={"verdict": "abandoned"})
    assert _emit(generation=3) == 0
    assert (
        repo / "openspec/changes/demo/dispatch-results/batch-0123456789abcdef01234567-ri-01-attempt-1-g3.json"
    ).is_file()


_SKILLS = Path(__file__).resolve().parents[2]
# An instruction to run `env` / `printenv` (at a line start, opening a code
# span, inside $(...), or after a shell separator) or to expand a credential
# variable. Prose such as "the FOO env var" is not an instruction.
_ENV_PROBE = re.compile(
    r"(?m)(^\s*|`|\$\(|[;|&]\s*)(env|printenv)\b|\$\{?[A-Z0-9_]*(API_KEY|TOKEN|SECRET)\b"
)


@pytest.mark.parametrize("skill", ["autopilot", "supervise"])
def test_worker_protocol_forbids_env_probing(skill: str) -> None:
    text = (_SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
    offending = [match.group(0) for match in _ENV_PROBE.finditer(text)]
    assert offending == [], offending


def test_worker_protocol_returns_only_the_emitted_result() -> None:
    text = (_SKILLS / "autopilot" / "SKILL.md").read_text(encoding="utf-8")
    assert "runner.py emit-result" in text
    assert "never a hand-composed result" in text
    assert "--kind permission_blocked" in text
    assert "--kind capability_unavailable" in text


def test_degradations_travel_into_the_result(repo: Path) -> None:
    degradation = {"code": "single_vendor_review", "phase": "PLAN_REVIEW", "detail": "claude_code only"}
    _commit_state(
        repo,
        current_phase="DONE",
        goal_gate={"verdict": "passed"},
        last_handoff_id="h-1",
        degradations=[degradation],
    )
    assert _emit() == 0
    assert _written(repo)["degradations"] == [degradation]
