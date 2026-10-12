"""runner relayed-gate-answer: a cloud worker applies a relayed answer only once verified."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

import autopilot
import runner
from shared.trust_posture import load_posture, posture_digest

_DECISION = "4eec73f8-9f8f-46a5-935c-7358a8dcd984"
_REF = f"gate-decision:{_DECISION}"
_DISPATCH = "batch-d8913c4d8e973cd7940e2d09:ri-22:attempt-1"
_ARGS = ["relayed-gate-answer", "demo", "--gate", "escalate_resume", "--decision", "approved", "--no-fetch"]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture()
def worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    doc = {"schema_version": 1, "gates": {"escalate_resume": {"disposition": "block"}}}
    (tmp_path / "TRUST_POSTURE.md").write_text("---\n" + yaml.safe_dump(doc) + "---\n")
    checkpoint = {
        "gate_decisions": [
            {
                "decision_id": _DECISION,
                "gate": "escalate_resume",
                "outcome": "proceed",
                "resolution": "console_approved",
                "provenance": {"source": "human", "approval_ref": None},
                "change_id": "demo",
                "dispatch_id": _DISPATCH,
                "lease_generation": 3,
            }
        ],
        "dispatch_attempts": [{"dispatch_id": _DISPATCH, "change_id": "demo", "lease_generation": 4}],
    }
    path = tmp_path / "openspec" / "roadmaps" / "rm" / "checkpoint.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(checkpoint))
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "supervisor checkpoint")
    _git(tmp_path, "update-ref", "refs/remotes/origin/openspec/roadmap-rm", "HEAD")
    return tmp_path


def _seed(root: Path) -> Path:
    digest = posture_digest(load_posture(root))
    state = autopilot.LoopState(change_id="demo", current_phase="ESCALATE")
    state.previous_phase = "PLAN_REVIEW"
    state.pending_gate = {
        "schema_version": 1,
        "change_id": "demo",
        "gate": "escalate_resume",
        "phase": "ESCALATE",
        "requested_at": "2026-10-12T00:00:00+00:00",
        "prompt": "Resume?",
        "context": {"previous_phase": "PLAN_REVIEW"},
        "posture": {"disposition": "block", "posture_present": True, "posture_digest": digest},
        "edge": {"outcome": "resolved", "target": "PLAN_REVIEW"},
    }
    path = root / "openspec" / "changes" / "demo" / "loop-state.json"
    autopilot.save_state(state, path)
    return path


def _state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def test_a_verified_relay_is_applied(worker: Path) -> None:
    path = _seed(worker)

    assert runner.main([*_ARGS, "--approval-ref", _REF]) == 0

    state = _state(path)
    assert state["pending_gate"] is None
    assert state["current_phase"] == "PLAN_REVIEW"
    assert state["gate_decisions"][-1]["provenance"] == {"source": "human", "approval_ref": _REF}


def test_an_unverified_relay_records_nothing(worker: Path) -> None:
    path = _seed(worker)
    before = path.read_bytes()

    rc = runner.main([*_ARGS, "--approval-ref", "gate-decision:00000000-0000-4000-8000-000000000000"])

    assert rc == 2
    assert path.read_bytes() == before


def test_a_decision_the_worker_commits_itself_records_nothing(worker: Path) -> None:
    """Committing to the worker branch does not move the fetched roadmap ref."""
    path = _seed(worker)
    checkpoint = worker / "openspec" / "roadmaps" / "rm" / "checkpoint.json"
    forged = json.loads(checkpoint.read_text())
    forged["gate_decisions"][0]["decision_id"] = "6eec73f8-9f8f-46a5-935c-7358a8dcd984"
    checkpoint.write_text(json.dumps(forged))
    _git(worker, "commit", "-qam", "forged")
    before = path.read_bytes()

    rc = runner.main([*_ARGS, "--approval-ref", "gate-decision:6eec73f8-9f8f-46a5-935c-7358a8dcd984"])

    assert rc == 2
    assert path.read_bytes() == before


def test_a_worktree_with_a_launch_marker_must_use_gate_answer(worker: Path) -> None:
    path = _seed(worker)
    folder = worker / ".supervised-dispatch" / "demo"
    folder.mkdir(parents=True)
    (folder / "ri-22-attempt-1.marker").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "dispatch_id": _DISPATCH,
                "generation": 4,
                "owner_nonce": "owner-nonce-0000000004",
                "roadmap_approval_ref": "gate-decision:11111111-2222-4333-8444-555555555555",
            }
        )
    )
    before = path.read_bytes()

    assert runner.main([*_ARGS, "--approval-ref", _REF]) == 2
    assert path.read_bytes() == before


def test_a_failed_roadmap_fetch_records_nothing(worker: Path) -> None:
    """No origin remote: the fetch fails, so the stale local ref is not trusted."""
    path = _seed(worker)
    before = path.read_bytes()
    args = [a for a in _ARGS if a != "--no-fetch"]

    assert runner.main([*args, "--approval-ref", _REF]) == 2
    assert path.read_bytes() == before
