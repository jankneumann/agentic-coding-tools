"""The committed dispatch scope a cloud worker reads in place of a launch marker (D8)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills"))

from shared import dispatch_contract  # noqa: E402
from shared import trust_posture as tp  # noqa: E402
from shared.approval_gate import ApprovalGate, Outcome, Resolution  # noqa: E402
from shared.trust_posture import Gate  # noqa: E402

_APPROVAL = "40776beb-63e5-4a06-b7b9-b349f3a918df"
_REF = f"gate-decision:{_APPROVAL}"
_DISPATCH = "batch-d8913c4d8e973cd7940e2d09:ri-22:attempt-1"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _checkpoint(
    *, resolution: str = "console_approved", outcome: str = "proceed", ref: str = _REF, generation: int = 2
) -> dict[str, Any]:
    return {
        "gate_decisions": [
            {"decision_id": _APPROVAL, "gate": "roadmap_approval", "outcome": outcome, "resolution": resolution}
        ],
        "dispatch_attempts": [
            {
                "dispatch_id": _DISPATCH,
                "change_id": "demo",
                "attempt": 1,
                "lease_generation": generation,
                "roadmap_approval_ref": ref,
            }
        ],
    }


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _commit(root: Path, checkpoint: dict[str, Any], roadmap: str = "rm") -> Path:
    path = root / "openspec" / "roadmaps" / roadmap / "checkpoint.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "checkpoint")
    return path


def test_a_committed_attempt_with_a_human_approval_yields_its_scope(repo: Path) -> None:
    _commit(repo, _checkpoint())

    scope = dispatch_contract.read_committed_dispatch_scope("demo", repo_root=repo)

    assert scope == {
        "dispatch_id": _DISPATCH,
        "generation": 2,
        "roadmap_approval_ref": _REF,
        "source": "committed_checkpoint",
        "checkpoint_path": "openspec/roadmaps/rm/checkpoint.json",
    }
    assert "gate_answer" not in scope and "owner_nonce" not in scope


def test_the_latest_generation_wins(repo: Path) -> None:
    checkpoint = _checkpoint()
    checkpoint["dispatch_attempts"].append(dict(checkpoint["dispatch_attempts"][0], lease_generation=5))
    _commit(repo, checkpoint)

    assert dispatch_contract.read_committed_dispatch_scope("demo", repo_root=repo)["generation"] == 5


def test_an_uncommitted_edit_is_ignored(repo: Path) -> None:
    path = _commit(repo, _checkpoint(resolution="posture_block", outcome="blocked"))
    path.write_text(json.dumps(_checkpoint()))

    assert dispatch_contract.read_committed_dispatch_scope("demo", repo_root=repo) is None


@pytest.mark.parametrize(
    "checkpoint",
    [
        _checkpoint(resolution="posture_block", outcome="blocked"),
        _checkpoint(resolution="console_rejected", outcome="blocked"),
        _checkpoint(resolution="auto"),
        _checkpoint(ref="gate-decision:00000000-0000-4000-8000-000000000000"),
    ],
    ids=["posture-block", "rejected", "auto", "unknown-ref"],
)
def test_no_human_approval_means_no_scope(repo: Path, checkpoint: dict[str, Any]) -> None:
    _commit(repo, checkpoint)

    assert dispatch_contract.read_committed_dispatch_scope("demo", repo_root=repo) is None


def test_archived_roadmaps_and_other_changes_do_not_count(repo: Path) -> None:
    _commit(repo, _checkpoint(), roadmap="archive/2026-01-01-rm")

    assert dispatch_contract.read_committed_dispatch_scope("demo", repo_root=repo) is None
    assert dispatch_contract.read_committed_dispatch_scope("other", repo_root=repo) is None


def test_outside_a_git_repository_there_is_no_scope(tmp_path: Path) -> None:
    assert dispatch_contract.read_committed_dispatch_scope("demo", repo_root=tmp_path) is None


def _posture(root: Path, **gates: str) -> None:
    doc = {"schema_version": 1, "gates": {k: {"disposition": v} for k, v in gates.items()}}
    (root / tp.DEFAULT_CONTRACT_FILENAME).write_text("---\n" + yaml.safe_dump(doc) + "---\n")


class _Audit:
    def record(self, _record: dict[str, Any]) -> bool:
        return True


def _default_gate(root: Path) -> ApprovalGate:
    # No marker_reader: the gate's own default reader, which a cloud worker uses.
    return ApprovalGate(coordinator=None, audit=_Audit(), repo_root=str(root), sleep=lambda _s: None)


def test_the_default_gate_takes_scoped_auto_from_the_committed_scope(repo: Path) -> None:
    _posture(repo, proposal_approval="auto")
    _commit(repo, _checkpoint())

    decision = _default_gate(repo).evaluate(Gate.PROPOSAL_APPROVAL, {"change_id": "demo"})

    assert (decision.outcome, decision.resolution) == (Outcome.PROCEED, Resolution.AUTO)
    assert decision.scope == "roadmap_approval"


def test_without_a_committed_scope_the_default_gate_falls_back_to_unscoped(repo: Path) -> None:
    _posture(repo, proposal_approval="auto")
    _commit(repo, _checkpoint(resolution="posture_block", outcome="blocked"))

    decision = _default_gate(repo).evaluate(Gate.PROPOSAL_APPROVAL, {"change_id": "demo"})

    assert decision.outcome is Outcome.BLOCKED
    assert decision.scope == "unscoped"
