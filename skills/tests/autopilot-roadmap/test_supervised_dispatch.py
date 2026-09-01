"""TDD coverage for opt-in delegated roadmap lifecycle orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from models import Effort, ItemStatus, Roadmap, RoadmapItem
import orchestrator as orchestrator_module
from orchestrator import apply_delegated_batch, execute_roadmap, prepare_delegated_batch


_REPO_ROOT = Path(__file__).resolve().parents[3]
_NOW = "2026-09-01T00:00:00+00:00"


def _write_workspace(repo: Path, items: list[RoadmapItem]) -> Path:
    schema_root = repo / "openspec" / "schemas"
    schema_root.mkdir(parents=True)
    for schema_name in ("roadmap.schema.json", "checkpoint.schema.json"):
        (schema_root / schema_name).write_text(
            (_REPO_ROOT / "openspec" / "schemas" / schema_name).read_text()
        )
    workspace = repo / "roadmap"
    workspace.mkdir()
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id="roadmap-supervised",
        source_proposal="proposal.md",
        items=items,
    )
    (workspace / "roadmap.yaml").write_text(
        yaml.safe_dump(roadmap.to_dict(), sort_keys=False)
    )
    return workspace


def _write_work_packages(repo: Path, change_id: str, write_allow: str) -> None:
    package = {
        "package_id": f"wp-{change_id}",
        "task_type": "implementation",
        "description": f"Fixture for {change_id}",
        "depends_on": [],
        "priority": 1,
        "locks": {"files": [], "keys": [f"feature:{change_id}:fixture"]},
        "scope": {"write_allow": [write_allow], "read_allow": ["**"]},
        "worktree": {"name": change_id},
        "timeout_minutes": 10,
        "retry_budget": 0,
        "min_trust_level": 0,
        "verification": {
            "tier_required": "C",
            "steps": [
                {
                    "name": "fixture",
                    "kind": "command",
                    "command": "true",
                    "evidence": {"artifacts": [], "result_keys": ["fixture"]},
                }
            ],
        },
        "outputs": {"result_keys": ["fixture"]},
    }
    document = {
        "schema_version": 1,
        "feature": {"id": change_id, "plan_revision": 1},
        "contracts": {
            "revision": 1,
            "openapi": {
                "primary": "contracts/openapi.yaml",
                "files": ["contracts/openapi.yaml"],
            },
        },
        "packages": [package],
    }
    path = repo / "openspec" / "changes" / change_id / "work-packages.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False))


def _isolation(item: RoadmapItem) -> dict[str, str]:
    return {
        "mode": "managed_worktree",
        "worktree_path": f"/worktrees/{item.change_id}",
        "branch": f"openspec/{item.change_id}",
    }


def _mark_batch_launched(workspace: Path) -> None:
    path = workspace / "checkpoint.json"
    checkpoint = json.loads(path.read_text())
    for attempt in checkpoint["dispatch_attempts"]:
        generation = attempt["lease_generation"]
        handle = f"task-{attempt['item_id']}"
        attempt.update(
            status="launched",
            lease={
                "generation": generation,
                "owner_nonce": "owner-nonce-0001",
                "state": "active",
                "acquired_at": _NOW,
                "heartbeat_at": _NOW,
                "expires_at": "2026-09-01T00:05:00+00:00",
            },
            launch_evidence={
                "kind": "host_ack",
                "generation": generation,
                "handle": handle,
                "observed_at": _NOW,
            },
            launch_gate={
                "generation": generation,
                "state": "entered",
                "handle": handle,
                "go_released_at": _NOW,
                "entered_at": _NOW,
            },
            launch_history=[],
        )
    path.write_text(json.dumps(checkpoint, indent=2) + "\n")


def _result(request: dict[str, Any], outcome: str = "success") -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": 1,
        "dispatch_id": request["dispatch_id"],
        "change_id": request["change_id"],
        "attempt": request["attempt"],
        "lease_generation": request["lease_generation"],
        "outcome": outcome,
        "worktree_path": request["isolation"]["worktree_path"],
        "branch": request["isolation"]["branch"],
        "evidence": {"loop_state_path": ".git/autopilot/loop-state.json"},
    }
    if outcome == "success":
        result["handoff_id"] = f"handoff-{request['item_id']}"
    return result


def test_prepare_persists_exact_safe_batch_before_returning_requests(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    items = [
        RoadmapItem(
            "ri-02", "Beta", ItemStatus.APPROVED, 2, Effort.S, change_id="change-beta"
        ),
        RoadmapItem(
            "ri-01", "Alpha", ItemStatus.APPROVED, 1, Effort.S, change_id="change-alpha"
        ),
    ]
    workspace = _write_workspace(repo, items)
    _write_work_packages(repo, "change-alpha", "src/alpha/**")
    _write_work_packages(repo, "change-beta", "src/beta/**")
    router_context = {"router_vendor": "codex", "routing": {"model": "gpt-test"}}

    prepared = prepare_delegated_batch(
        workspace,
        repo_root=repo,
        isolation_resolver=_isolation,
        context=router_context,
    )

    assert [request["item_id"] for request in prepared["requests"]] == ["ri-01", "ri-02"]
    assert prepared["failures"] == []
    checkpoint = json.loads((workspace / "checkpoint.json").read_text())
    assert [attempt["dispatch_id"] for attempt in checkpoint["dispatch_attempts"]] == [
        request["dispatch_id"] for request in prepared["requests"]
    ]
    assert all(attempt["status"] == "prepared" for attempt in checkpoint["dispatch_attempts"])
    assert all(request["context"]["router_vendor"] == "codex" for request in prepared["requests"])
    assert all(request["context"]["routing"] == {"model": "gpt-test"} for request in prepared["requests"])


def test_prepare_preserves_preexisting_delegated_batch_id_router_key(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    workspace = _write_workspace(
        repo,
        [RoadmapItem("ri-01", "Alpha", ItemStatus.APPROVED, 1, Effort.S, change_id="change-alpha")],
    )
    _write_work_packages(repo, "change-alpha", "src/alpha/**")

    prepared = prepare_delegated_batch(
        workspace,
        repo_root=repo,
        isolation_resolver=_isolation,
        context={"delegated_batch_id": "router-owned-value", "router_vendor": "codex"},
    )

    assert prepared["requests"][0]["context"] == {
        "delegated_batch_id": "router-owned-value",
        "router_vendor": "codex",
    }
    checkpoint = json.loads((workspace / "checkpoint.json").read_text())
    assert checkpoint["dispatch_attempts"][0]["context"] == prepared["requests"][0]["context"]


def test_invalid_exact_change_id_is_non_dispatched_and_resumable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    workspace = _write_workspace(
        repo,
        [RoadmapItem("ri-01", "Invalid", ItemStatus.APPROVED, 1, Effort.S, change_id="Invalid-ID")],
    )

    prepared = prepare_delegated_batch(
        workspace,
        repo_root=repo,
        isolation_resolver=_isolation,
    )

    assert prepared["requests"] == []
    assert prepared["failures"] == [
        {"item_id": "ri-01", "reason": "invalid_change_id"}
    ]
    roadmap = yaml.safe_load((workspace / "roadmap.yaml").read_text())
    assert roadmap["items"][0]["status"] == "approved"
    checkpoint = json.loads((workspace / "checkpoint.json").read_text())
    assert checkpoint.get("dispatch_attempts", []) == []
    assert checkpoint.get("failed_items", []) == []


def test_apply_binds_out_of_order_results_and_dispatches_once_with_router_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    workspace = _write_workspace(
        repo,
        [
            RoadmapItem("ri-01", "Alpha", ItemStatus.APPROVED, 1, Effort.S, change_id="change-alpha"),
            RoadmapItem("ri-02", "Beta", ItemStatus.APPROVED, 2, Effort.S, change_id="change-beta"),
        ],
    )
    _write_work_packages(repo, "change-alpha", "src/alpha/**")
    _write_work_packages(repo, "change-beta", "src/beta/**")
    prepared = prepare_delegated_batch(
        workspace,
        repo_root=repo,
        isolation_resolver=_isolation,
        context={"router_vendor": "codex", "router_budget": 17},
    )
    _mark_batch_launched(workspace)
    monkeypatch.setattr(
        orchestrator_module,
        "_RESULT_SCHEMA_PATH",
        tmp_path / "archived-change-contract-does-not-exist.json",
        raising=False,
    )
    results = [_result(request) for request in reversed(prepared["requests"])]
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def result_lookup(item_id: str, phase: str, context: dict[str, Any]) -> dict[str, Any]:
        calls.append((item_id, phase, context))
        return context["dispatch_result"]

    applied = apply_delegated_batch(
        workspace,
        prepared["batch_id"],
        results,
        result_lookup,
        repo_root=repo,
    )

    assert applied["completed_item_ids"] == ["ri-01", "ri-02"]
    assert [(item_id, phase) for item_id, phase, _ in calls] == [
        ("ri-01", "autopilot"),
        ("ri-02", "autopilot"),
    ]
    assert all(context["router_vendor"] == "codex" for _, _, context in calls)
    assert all(context["router_budget"] == 17 for _, _, context in calls)
    assert {context["dispatch_id"] for _, _, context in calls} == {
        request["dispatch_id"] for request in prepared["requests"]
    }
    checkpoint = json.loads((workspace / "checkpoint.json").read_text())
    assert checkpoint["completed_items"] == ["ri-01", "ri-02"]
    assert all(attempt["status"] == "completed" for attempt in checkpoint["dispatch_attempts"])
    assert (workspace / "learnings/ri-01.md").exists()
    assert (workspace / "learnings/ri-02.md").exists()

    with pytest.raises(ValueError, match="already applied"):
        apply_delegated_batch(
            workspace,
            prepared["batch_id"],
            results,
            result_lookup,
            repo_root=repo,
        )
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("dispatch_id", "other-dispatch", "result membership mismatch"),
        ("change_id", "other-change", "change_id mismatch"),
        ("attempt", 2, "attempt mismatch"),
        ("lease_generation", 2, "lease_generation mismatch"),
        ("worktree_path", "/worktrees/other", "worktree_path mismatch"),
        ("branch", "openspec/other", "branch mismatch"),
    ],
)
def test_apply_rejects_exact_correlation_mismatch_before_dispatch(
    tmp_path: Path,
    field: str,
    replacement: object,
    message: str,
) -> None:
    repo = tmp_path / "repo"
    workspace = _write_workspace(
        repo,
        [RoadmapItem("ri-01", "Alpha", ItemStatus.APPROVED, 1, Effort.S, change_id="change-alpha")],
    )
    _write_work_packages(repo, "change-alpha", "src/alpha/**")
    prepared = prepare_delegated_batch(workspace, repo_root=repo, isolation_resolver=_isolation)
    _mark_batch_launched(workspace)
    result = _result(prepared["requests"][0])
    result[field] = replacement
    calls: list[str] = []

    with pytest.raises(ValueError, match=message):
        apply_delegated_batch(
            workspace,
            prepared["batch_id"],
            [result],
            lambda item_id, phase, context: calls.append(item_id) or context["dispatch_result"],
            repo_root=repo,
        )

    assert calls == []
    checkpoint = json.loads((workspace / "checkpoint.json").read_text())
    assert checkpoint.get("completed_items", []) == []
    assert checkpoint["dispatch_attempts"][0]["status"] == "launched"


@pytest.mark.parametrize("membership", ["missing", "extra", "duplicate"])
def test_apply_rejects_inexact_result_membership_without_partial_completion(
    tmp_path: Path,
    membership: str,
) -> None:
    repo = tmp_path / "repo"
    workspace = _write_workspace(
        repo,
        [RoadmapItem("ri-01", "Alpha", ItemStatus.APPROVED, 1, Effort.S, change_id="change-alpha")],
    )
    _write_work_packages(repo, "change-alpha", "src/alpha/**")
    prepared = prepare_delegated_batch(workspace, repo_root=repo, isolation_resolver=_isolation)
    _mark_batch_launched(workspace)
    valid = _result(prepared["requests"][0])
    if membership == "missing":
        results = []
    elif membership == "extra":
        extra = dict(valid, dispatch_id="other-dispatch")
        results = [valid, extra]
    else:
        results = [valid, dict(valid)]
    calls: list[str] = []

    with pytest.raises(ValueError, match="result membership|duplicate dispatch result"):
        apply_delegated_batch(
            workspace,
            prepared["batch_id"],
            results,
            lambda item_id, phase, context: calls.append(item_id) or context["dispatch_result"],
            repo_root=repo,
        )

    assert calls == []
    checkpoint = json.loads((workspace / "checkpoint.json").read_text())
    assert checkpoint.get("completed_items", []) == []
    assert checkpoint["dispatch_attempts"][0]["status"] == "launched"


def test_parked_result_is_nonterminal_and_does_not_unblock_dependent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    workspace = _write_workspace(
        repo,
        [
            RoadmapItem("ri-01", "Alpha", ItemStatus.APPROVED, 1, Effort.S, change_id="change-alpha"),
            RoadmapItem(
                "ri-02",
                "Dependent",
                ItemStatus.APPROVED,
                2,
                Effort.S,
                depends_on=["ri-01"],
                change_id="change-beta",
            ),
        ],
    )
    _write_work_packages(repo, "change-alpha", "src/alpha/**")
    prepared = prepare_delegated_batch(workspace, repo_root=repo, isolation_resolver=_isolation)
    _mark_batch_launched(workspace)
    result = _result(prepared["requests"][0], outcome="parked")
    result["parked"] = {
        "kind": "pending_gate",
        "reason": "operator approval required",
        "gate": "deploy",
    }

    applied = apply_delegated_batch(
        workspace,
        prepared["batch_id"],
        [result],
        lambda item_id, phase, context: context["dispatch_result"],
        repo_root=repo,
    )

    assert applied["parked_item_ids"] == ["ri-01"]
    checkpoint = json.loads((workspace / "checkpoint.json").read_text())
    assert checkpoint.get("completed_items", []) == []
    assert checkpoint.get("failed_items", []) == []
    assert checkpoint["dispatch_attempts"][0]["status"] == "parked"
    roadmap = yaml.safe_load((workspace / "roadmap.yaml").read_text())
    statuses = {item["item_id"]: item["status"] for item in roadmap["items"]}
    assert statuses == {"ri-01": "in_progress", "ri-02": "approved"}


def test_legacy_execute_roadmap_call_shape_remains_exact(tmp_path: Path) -> None:
    workspace = _write_workspace(
        tmp_path / "repo",
        [RoadmapItem("ri-01", "Legacy", ItemStatus.APPROVED, 1, Effort.S)],
    )
    calls: list[tuple[str, str, dict[str, Any]]] = []

    result = execute_roadmap(
        workspace,
        dispatch_fn=lambda item_id, phase, context: calls.append((item_id, phase, context))
        or "success",
    )

    assert result["status"] == "completed"
    assert calls == [
        ("ri-01", "planning", {"item_id": "ri-01", "roadmap_id": "roadmap-supervised", "completed_items": []}),
        ("ri-01", "implementing", {"item_id": "ri-01", "roadmap_id": "roadmap-supervised", "completed_items": []}),
        ("ri-01", "reviewing", {"item_id": "ri-01", "roadmap_id": "roadmap-supervised", "completed_items": []}),
        ("ri-01", "validating", {"item_id": "ri-01", "roadmap_id": "roadmap-supervised", "completed_items": []}),
    ]
