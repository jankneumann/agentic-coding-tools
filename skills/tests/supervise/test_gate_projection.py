"""Tests for the gate projection collector (``supervise/scripts/gate_projection.py``).

Each test builds a throwaway repository under ``tmp_path`` holding the two
sources the collector reads: ``openspec/roadmaps/<id>/checkpoint.json`` and
``openspec/changes/<id>/loop-state.json``. Nothing here names a real change
directory.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "supervise" / "scripts"
if str(_SCRIPTS) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(_SCRIPTS))

import gate_projection  # noqa: E402

_PROJECT = "acme/api"
_ROADMAP = "demo-roadmap"
_CHANGE = "add-demo-thing"
_DISPATCH = "batch-0123456789abcdef:ri-01:attempt-1"
_APPROVAL = "11111111-1111-4111-8111-111111111111"
_NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def _attempt(**updates: Any) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "dispatch_id": _DISPATCH,
        "item_id": "ri-01",
        "change_id": _CHANGE,
        "phase": "autopilot",
        "attempt": 1,
        "status": "parked",
        "parked": {
            "deadline": "2026-11-20T12:00:00+00:00",
            "gate": "merge",
            "kind": "pending_gate",
            "reason": "Authorize merging this pull request?",
            "resume_hint": "answer gate merge through the resume request's gate_answer",
        },
    }
    attempt.update(updates)
    return attempt


def _write_checkpoint(
    repo: Path,
    attempts: list[dict[str, Any]],
    *,
    roadmap: str = _ROADMAP,
    gate_decisions: list[dict[str, Any]] | None = None,
) -> Path:
    path = repo / "openspec" / "roadmaps" / roadmap / "checkpoint.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "roadmap_id": roadmap,
                "current_item_id": "ri-01",
                "phase": "implementing",
                "gate_decisions": gate_decisions or [],
                "dispatch_attempts": attempts,
            }
        )
    )
    return path


def _write_loop_state(
    repo: Path, pending_gate: dict[str, Any] | None, *, change: str = _CHANGE
) -> Path:
    path = repo / "openspec" / "changes" / change / "loop-state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {"schema_version": 6, "change_id": change, "current_phase": "PLAN"}
    if pending_gate is not None:
        state["pending_gate"] = pending_gate
    path.write_text(json.dumps(state))
    return path


def _pending_gate(**updates: Any) -> dict[str, Any]:
    gate: dict[str, Any] = {
        "schema_version": 1,
        "change_id": _CHANGE,
        "gate": "proposal_approval",
        "phase": "PLAN",
        "requested_at": "2026-11-19T10:00:00+00:00",
        "prompt": "Approve the proposal?",
        "context": {},
        "posture": {"disposition": "block", "posture_present": False},
    }
    gate.update(updates)
    return gate


def _write_posture(repo: Path, gates: dict[str, dict[str, Any]]) -> None:
    lines = ["---", "schema_version: 1", "gates:"]
    for name, cfg in gates.items():
        lines.append(f"  {name}:")
        for key, value in cfg.items():
            lines.append(f"    {key}: {value}")
    lines += ["---", "", "# Trust posture (test fixture)", ""]
    (repo / "TRUST_POSTURE.md").write_text("\n".join(lines))


def _collect(repo: Path) -> dict[str, Any]:
    return gate_projection.collect(repo, _PROJECT, now=_NOW)


def _tree_digest(repo: Path) -> dict[str, str]:
    return {
        str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(repo.rglob("*"))
        if p.is_file()
    }


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #


def test_a_parked_dispatch_attempt_is_collected(tmp_path: Path) -> None:
    _write_checkpoint(tmp_path, [_attempt()])

    snapshot = _collect(tmp_path)

    assert snapshot["project"] == _PROJECT
    assert snapshot["collected_at"] == "2026-11-19T12:00:00+00:00"
    assert snapshot["source_errors"] == []
    (gate,) = snapshot["gates"]
    assert gate["source"] == "checkpoint"
    assert gate["roadmap_id"] == _ROADMAP
    assert gate["item_id"] == "ri-01"
    assert gate["change_id"] == _CHANGE
    assert gate["dispatch_id"] == _DISPATCH
    assert gate["gate"] == "merge"
    assert gate["deadline"] == "2026-11-20T12:00:00+00:00"
    assert gate["prompt"] == "Authorize merging this pull request?"
    assert gate["subject"] == f"ri-01 {_CHANGE}"
    assert re.fullmatch(r"[0-9a-f]{16}", gate["gate_id"])
    hint = gate["answer_hint"]
    assert "cycle_state.py" in hint and "gate-answer" in hint
    assert f"--roadmap {_ROADMAP}" in hint
    assert "--gate merge" in hint
    assert f"--dispatch-id {_DISPATCH}" in hint


def test_a_policy_pause_is_listed_under_the_escalate_resume_gate(tmp_path: Path) -> None:
    parked = {"kind": "policy_pause", "reason": "Budget exceeded", "deadline": None}
    _write_checkpoint(tmp_path, [_attempt(parked=parked)])

    (gate,) = _collect(tmp_path)["gates"]

    assert gate["gate"] == "escalate_resume"
    assert "--gate escalate_resume" in gate["answer_hint"]


def test_a_park_with_no_gate_keeps_its_own_resume_hint(tmp_path: Path) -> None:
    parked = {
        "kind": "capability_unavailable",
        "reason": "No container runtime",
        "resume_hint": "install docker and resume",
    }
    _write_checkpoint(tmp_path, [_attempt(parked=parked)])

    (gate,) = _collect(tmp_path)["gates"]

    assert gate["gate"] == "capability_unavailable"
    assert gate["answer_hint"] == "install docker and resume"
    assert gate["disposition"] == "block"


def test_a_loop_state_pending_gate_is_collected(tmp_path: Path) -> None:
    _write_loop_state(tmp_path, _pending_gate())

    snapshot = _collect(tmp_path)

    (gate,) = snapshot["gates"]
    assert gate["source"] == "loop_state"
    assert gate["change_id"] == _CHANGE
    assert gate["gate"] == "proposal_approval"
    assert gate["prompt"] == "Approve the proposal?"
    assert gate["phase"] == "PLAN"
    assert gate["requested_at"] == "2026-11-19T10:00:00+00:00"
    assert gate["subject"] == _CHANGE
    assert f"gate-answer {_CHANGE} --gate proposal_approval" in gate["answer_hint"]


def test_answer_hints_name_the_skills_directory_the_collector_runs_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_checkpoint(tmp_path, [_attempt()])
    _write_loop_state(tmp_path, _pending_gate())
    installed = tmp_path.resolve() / ".claude" / "skills"
    monkeypatch.setattr(gate_projection, "_SKILLS_ROOT", installed)

    parked, pending = _collect(tmp_path)["gates"]

    assert parked["answer_hint"].startswith(
        "python3 .claude/skills/supervise/scripts/cycle_state.py "
    )
    assert pending["answer_hint"].startswith(
        "python3 .claude/skills/autopilot/scripts/runner.py "
    )


def test_answer_hints_for_another_repository_leave_the_skills_directory_open(
    tmp_path: Path,
) -> None:
    _write_checkpoint(tmp_path, [_attempt()])
    _write_loop_state(tmp_path, _pending_gate())

    parked, pending = _collect(tmp_path)["gates"]

    placeholder = gate_projection.SKILLS_DIR_PLACEHOLDER
    assert parked["answer_hint"].startswith(
        f"python3 {placeholder}/supervise/scripts/cycle_state.py "
    )
    assert pending["answer_hint"].startswith(f"python3 {placeholder}/autopilot/scripts/runner.py ")


def test_resolved_and_unparked_records_are_not_collected(tmp_path: Path) -> None:
    _write_checkpoint(
        tmp_path,
        [
            _attempt(status="completed"),
            _attempt(status="launched", parked=None),
            _attempt(status="parked", parked=None),
        ],
    )
    _write_loop_state(tmp_path, None)
    _write_loop_state(tmp_path, {}, change="other-change")

    snapshot = _collect(tmp_path)

    assert snapshot["gates"] == []
    assert snapshot["source_errors"] == []


def test_archived_changes_are_not_scanned(tmp_path: Path) -> None:
    archived = tmp_path / "openspec" / "changes" / "archive" / "2026-01-01-old" / "loop-state.json"
    archived.parent.mkdir(parents=True)
    archived.write_text(json.dumps({"pending_gate": _pending_gate()}))

    assert _collect(tmp_path)["gates"] == []


# --------------------------------------------------------------------------- #
# Disposition
# --------------------------------------------------------------------------- #


def test_the_disposition_comes_from_the_trust_posture(tmp_path: Path) -> None:
    _write_posture(
        tmp_path,
        {
            "merge": {
                "disposition": "notify_with_timeout",
                "timeout_seconds": 600,
                "default_action": "proceed",
            }
        },
    )
    _write_checkpoint(tmp_path, [_attempt()])
    _write_loop_state(tmp_path, _pending_gate())

    by_gate = {g["gate"]: g for g in _collect(tmp_path)["gates"]}

    assert by_gate["merge"]["disposition"] == "notify_with_timeout"
    assert by_gate["merge"]["timeout_seconds"] == 600
    assert by_gate["merge"]["default_action"] == "proceed"
    assert by_gate["proposal_approval"]["disposition"] == "block"
    assert "timeout_seconds" not in by_gate["proposal_approval"]


def test_without_a_trust_posture_every_gate_blocks(tmp_path: Path) -> None:
    _write_checkpoint(tmp_path, [_attempt()])

    (gate,) = _collect(tmp_path)["gates"]

    assert gate["disposition"] == "block"
    assert "default_action" not in gate


def test_an_invalid_trust_posture_is_reported_and_blocks(tmp_path: Path) -> None:
    _write_posture(tmp_path, {"merge": {"disposition": "whenever"}})
    _write_checkpoint(tmp_path, [_attempt()])

    snapshot = _collect(tmp_path)

    assert snapshot["gates"][0]["disposition"] == "block"
    assert [e["path"] for e in snapshot["source_errors"]] == ["TRUST_POSTURE.md"]


# --------------------------------------------------------------------------- #
# Robustness and identity
# --------------------------------------------------------------------------- #


def test_an_unreadable_source_is_reported_and_does_not_stop_the_collection(
    tmp_path: Path,
) -> None:
    _write_checkpoint(tmp_path, [_attempt()])
    broken = tmp_path / "openspec" / "changes" / "broken-change" / "loop-state.json"
    broken.parent.mkdir(parents=True)
    broken.write_text("{not json")
    listy = tmp_path / "openspec" / "roadmaps" / "listy" / "checkpoint.json"
    listy.parent.mkdir(parents=True)
    listy.write_text("[]")

    snapshot = _collect(tmp_path)

    assert [g["gate"] for g in snapshot["gates"]] == ["merge"]
    assert sorted(e["path"] for e in snapshot["source_errors"]) == [
        "openspec/changes/broken-change/loop-state.json",
        "openspec/roadmaps/listy/checkpoint.json",
    ]
    assert all(e["error"] for e in snapshot["source_errors"])


def test_collection_is_repeatable(tmp_path: Path) -> None:
    _write_checkpoint(tmp_path, [_attempt()])
    _write_loop_state(tmp_path, _pending_gate())

    first = _collect(tmp_path)
    second = _collect(tmp_path)

    assert first == second
    ids = [g["gate_id"] for g in first["gates"]]
    assert len(set(ids)) == 2


def test_the_same_gate_in_another_project_has_another_id(tmp_path: Path) -> None:
    _write_checkpoint(tmp_path, [_attempt()])

    here = gate_projection.collect(tmp_path, _PROJECT, now=_NOW)["gates"][0]["gate_id"]
    there = gate_projection.collect(tmp_path, "acme/web", now=_NOW)["gates"][0]["gate_id"]

    assert here != there


def test_the_approval_link_is_carried(tmp_path: Path) -> None:
    decisions = [
        {"gate": "merge", "dispatch_id": _DISPATCH, "approval_id": "stale", "outcome": "blocked"},
        {"gate": "merge", "dispatch_id": "another", "approval_id": "other", "outcome": "blocked"},
        {"gate": "merge", "dispatch_id": _DISPATCH, "approval_id": _APPROVAL, "outcome": "blocked"},
        {"gate": "submit_pr", "dispatch_id": _DISPATCH, "approval_id": "wrong-gate"},
    ]
    _write_checkpoint(tmp_path, [_attempt()], gate_decisions=decisions)
    _write_loop_state(tmp_path, _pending_gate(approval_id=_APPROVAL))

    gates = _collect(tmp_path)["gates"]

    assert [g["approval_id"] for g in gates] == [_APPROVAL, _APPROVAL]


def test_a_gate_with_no_approval_request_carries_no_link(tmp_path: Path) -> None:
    decisions = [{"gate": "merge", "dispatch_id": _DISPATCH, "approval_id": None}]
    _write_checkpoint(tmp_path, [_attempt()], gate_decisions=decisions)

    (gate,) = _collect(tmp_path)["gates"]

    assert "approval_id" not in gate


def test_long_text_is_cut_to_what_the_coordinator_accepts(tmp_path: Path) -> None:
    parked = {"kind": "pending_gate", "gate": "merge", "reason": "x" * 9000}
    _write_checkpoint(tmp_path, [_attempt(parked=parked)])

    (gate,) = _collect(tmp_path)["gates"]

    assert len(gate["prompt"]) == 4000


def test_collecting_does_not_modify_the_repository(tmp_path: Path) -> None:
    _write_posture(tmp_path, {"merge": {"disposition": "auto"}})
    _write_checkpoint(tmp_path, [_attempt()])
    _write_loop_state(tmp_path, _pending_gate())
    before = _tree_digest(tmp_path)

    _collect(tmp_path)

    assert _tree_digest(tmp_path) == before


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def test_collect_prints_the_snapshot(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_checkpoint(tmp_path, [_attempt()])

    code = gate_projection.main(
        ["--repo-root", str(tmp_path), "collect", "--project", _PROJECT]
    )

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["project"] == _PROJECT
    assert [g["gate"] for g in printed["gates"]] == ["merge"]


def test_a_project_that_is_not_owner_slash_name_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = gate_projection.main(
        ["--repo-root", str(tmp_path), "collect", "--project", "not-a-project"]
    )

    assert code != 0
    assert "owner/name" in capsys.readouterr().err


class _FakeClient:
    calls: list[tuple[str, str, Any]] = []
    response: dict[str, Any] = {"status_code": 200, "data": {"gate_count": 1}, "error": None}

    def request(self, method: str, path: str, payload: Any = None) -> dict[str, Any]:
        type(self).calls.append((method, path, payload))
        return type(self).response


@pytest.fixture()
def fake_client(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    _FakeClient.calls = []
    _FakeClient.response = {"status_code": 200, "data": {"gate_count": 1}, "error": None}
    monkeypatch.setattr(gate_projection, "_coordinator_client", lambda: _FakeClient())
    return _FakeClient


def test_push_posts_the_snapshot_to_the_coordinator(
    tmp_path: Path, fake_client: type[_FakeClient], capsys: pytest.CaptureFixture[str]
) -> None:
    _write_checkpoint(tmp_path, [_attempt()])
    before = _tree_digest(tmp_path)

    code = gate_projection.main(["--repo-root", str(tmp_path), "push", "--project", _PROJECT])

    assert code == 0
    ((method, path, payload),) = fake_client.calls
    assert (method, path) == ("POST", "/gates/projection")
    assert payload["project"] == _PROJECT
    assert [g["gate"] for g in payload["gates"]] == ["merge"]
    assert json.loads(capsys.readouterr().out)["gate_count"] == 1
    assert _tree_digest(tmp_path) == before


def test_push_without_a_coordinator_fails_clearly_and_sends_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_checkpoint(tmp_path, [_attempt()])

    def _no_client() -> Any:
        raise ValueError("no allowed coordinator URL")

    monkeypatch.setattr(gate_projection, "_coordinator_client", _no_client)

    code = gate_projection.main(["--repo-root", str(tmp_path), "push", "--project", _PROJECT])

    assert code != 0
    captured = capsys.readouterr()
    assert "no allowed coordinator URL" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize(
    "response",
    [
        {"status_code": 403, "data": {"detail": "Project not enrolled"}, "error": None},
        {"status_code": None, "data": None, "error": "connection refused"},
    ],
)
def test_a_refused_or_failed_push_exits_non_zero(
    tmp_path: Path,
    fake_client: type[_FakeClient],
    capsys: pytest.CaptureFixture[str],
    response: dict[str, Any],
) -> None:
    fake_client.response = response

    code = gate_projection.main(["--repo-root", str(tmp_path), "push", "--project", _PROJECT])

    assert code != 0
    assert "push failed" in capsys.readouterr().err
