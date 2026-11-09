"""A supervisor-relayed gate answer a cloud worker can check (committed ledger)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills"))

from shared import dispatch_contract  # noqa: E402

_DECISION = "4eec73f8-9f8f-46a5-935c-7358a8dcd984"
_REF = f"gate-decision:{_DECISION}"
_DISPATCH = "batch-d8913c4d8e973cd7940e2d09:ri-22:attempt-1"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _record(**fields: Any) -> dict[str, Any]:
    record = {
        "decision_id": _DECISION,
        "gate": "escalate_resume",
        "outcome": "proceed",
        "resolution": "console_approved",
        "provenance": {"source": "human", "approval_ref": None},
        "change_id": "demo",
        "dispatch_id": _DISPATCH,
        "lease_generation": 3,
    }
    record.update(fields)
    return record


def _checkpoint(*records: dict[str, Any], generation: int = 4) -> dict[str, Any]:
    return {
        "gate_decisions": list(records) or [_record()],
        "dispatch_attempts": [{"dispatch_id": _DISPATCH, "change_id": "demo", "lease_generation": generation}],
    }


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _commit(root: Path, checkpoint: dict[str, Any], *, supervisor: bool = True) -> None:
    path = root / "openspec" / "roadmaps" / "rm" / "checkpoint.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "checkpoint")
    if supervisor:
        _git(root, "update-ref", "refs/remotes/origin/openspec/roadmap-rm", "HEAD")


def _read(root: Path, **overrides: Any) -> dict[str, Any] | None:
    kwargs: dict[str, Any] = {"gate": "escalate_resume", "decision": "approved", "approval_ref": _REF}
    kwargs.update(overrides)
    return dispatch_contract.read_committed_gate_answer("demo", repo_root=root, **kwargs)


def test_a_committed_console_answer_verifies(repo: Path) -> None:
    _commit(repo, _checkpoint())

    answer = _read(repo)

    assert answer is not None
    assert {k: v for k, v in answer.items() if k != "checkpoint_commit"} == {
        "dispatch_id": _DISPATCH,
        "generation": 4,
        "gate": "escalate_resume",
        "decision": "approved",
        "approval_ref": _REF,
        "resume_at": None,
        "source": "committed_checkpoint",
        "checkpoint_path": "openspec/roadmaps/rm/checkpoint.json",
    }


def test_the_answer_is_read_at_the_roadmap_tip_not_the_cut_point(repo: Path) -> None:
    """The decision lands on the roadmap branch after the worker branched."""
    _commit(repo, {"gate_decisions": [], "dispatch_attempts": []})
    _git(repo, "branch", "worker")
    _commit(repo, _checkpoint())
    _git(repo, "checkout", "-q", "worker")

    assert _read(repo) is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"gate": "merge"},
        {"decision": "rejected"},
        {"approval_ref": "gate-decision:00000000-0000-4000-8000-000000000000"},
        {"approval_ref": _DECISION},
        {"resume_at": "VALIDATE"},
    ],
    ids=["other-gate", "other-decision", "unknown-ref", "bare-id", "other-resume-at"],
)
def test_an_answer_that_differs_from_the_committed_one_is_refused(repo: Path, overrides: dict[str, Any]) -> None:
    _commit(repo, _checkpoint())

    assert _read(repo, **overrides) is None


@pytest.mark.parametrize(
    "record",
    [
        _record(provenance={"source": "posture"}),
        _record(resolution="auto"),
        _record(change_id="other"),
    ],
    ids=["not-human", "not-console", "other-change"],
)
def test_only_a_human_console_decision_for_this_change_counts(repo: Path, record: dict[str, Any]) -> None:
    _commit(repo, _checkpoint(record))

    assert _read(repo) is None


def test_a_superseded_answer_cannot_be_replayed(repo: Path) -> None:
    newer = _record(decision_id="5eec73f8-9f8f-46a5-935c-7358a8dcd984", lease_generation=4)
    _commit(repo, _checkpoint(_record(), newer, generation=5))

    assert _read(repo) is None


def test_an_answer_whose_attempt_was_not_relaunched_is_refused(repo: Path) -> None:
    _commit(repo, _checkpoint(generation=3))

    assert _read(repo) is None


def test_a_decision_committed_only_on_the_workers_branch_grants_nothing(repo: Path) -> None:
    _commit(repo, {"gate_decisions": [], "dispatch_attempts": []})
    _commit(repo, _checkpoint(), supervisor=False)

    assert _read(repo) is None


def test_a_rejection_verifies_at_the_parked_generation(repo: Path) -> None:
    """A rejection does not relaunch the attempt, so it stays at the decision's generation."""
    _commit(repo, _checkpoint(_record(outcome="blocked", resolution="console_rejected"), generation=3))

    answer = _read(repo, decision="rejected")
    assert answer is not None and answer["generation"] == 3
    assert _read(repo) is None


def test_a_rejection_after_a_relaunch_is_refused(repo: Path) -> None:
    _commit(repo, _checkpoint(_record(outcome="blocked", resolution="console_rejected"), generation=4))

    assert _read(repo, decision="rejected") is None


def test_a_committed_implement_resume_target_must_be_relayed_exactly(repo: Path) -> None:
    _commit(repo, _checkpoint(_record(resume_at="IMPLEMENT")))

    assert _read(repo, resume_at="IMPLEMENT") is not None
    assert _read(repo) is None
    assert _read(repo, resume_at="VALIDATE") is None
