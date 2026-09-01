"""TDD lifecycle coverage for the leased supervised-execution host adapter."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

_SKILLS = Path(__file__).resolve().parents[2]
_RUNTIME_SCRIPTS = _SKILLS / "roadmap-runtime" / "scripts"
_SCRIPTS = _SKILLS / "supervise" / "scripts"
for script_dir in (_RUNTIME_SCRIPTS, _SCRIPTS):
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

from models import Effort, ItemStatus, Roadmap, RoadmapItem  # noqa: E402
from execution import ExecutionAdapter  # noqa: E402


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = Path(__file__).parent / "fixtures" / "execution" / "lifecycle"


class FakeClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def _write_work_packages(repo: Path, change_id: str) -> None:
    package = {
        "package_id": f"wp-{change_id}",
        "task_type": "implementation",
        "description": f"Fixture for {change_id}",
        "depends_on": [],
        "priority": 1,
        "locks": {"files": [], "keys": [f"feature:{change_id}:fixture"]},
        "scope": {"write_allow": [f"src/{change_id}/**"], "read_allow": ["**"]},
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


def _workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
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
        roadmap_id="roadmap-host-adapter",
        source_proposal="proposal.md",
        items=[
            RoadmapItem(
                "ri-01",
                "Alpha",
                ItemStatus.APPROVED,
                1,
                Effort.S,
                change_id="change-alpha",
            )
        ],
    )
    (workspace / "roadmap.yaml").write_text(
        yaml.safe_dump(roadmap.to_dict(), sort_keys=False)
    )
    _write_work_packages(repo, "change-alpha")
    managed_root = repo / ".git-worktrees"
    worktree = managed_root / "change-alpha"
    loop_state = worktree / ".git" / "autopilot" / "loop-state.json"
    loop_state.parent.mkdir(parents=True)
    loop_state.write_text('{"status":"running"}\n')
    return repo, workspace, managed_root


def _adapter(
    managed_root: Path,
    clock: FakeClock,
    *,
    liveness: str = "live",
    host_calls: list[tuple[str, dict[str, Any]]] | None = None,
) -> ExecutionAdapter:
    calls = host_calls if host_calls is not None else []
    return ExecutionAdapter(
        managed_worktree_root=managed_root,
        clock=clock,
        branch_resolver=lambda _: "openspec/change-alpha",
        liveness_probe=lambda _: liveness,
        host_entry=lambda change_id, request: calls.append((change_id, request)) or "entered",
    )


def _isolation(managed_root: Path) -> dict[str, str]:
    return {
        "mode": "managed_worktree",
        "worktree_path": str(managed_root / "change-alpha"),
        "branch": "openspec/change-alpha",
    }


def _prepare(
    adapter: ExecutionAdapter,
    workspace: Path,
    repo: Path,
    managed_root: Path,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return adapter.prepare(
        workspace,
        repo_root=repo,
        isolation_resolver=lambda _: _isolation(managed_root),
        context=context,
    )


def _attempt(workspace: Path) -> dict[str, Any]:
    checkpoint = json.loads((workspace / "checkpoint.json").read_text())
    return checkpoint["dispatch_attempts"][0]


def _result(name: str, request: dict[str, Any]) -> dict[str, Any]:
    value = json.loads((_FIXTURES / name).read_text())
    value.update(
        dispatch_id=request["dispatch_id"],
        change_id=request["change_id"],
        attempt=request["attempt"],
        lease_generation=request["lease_generation"],
        worktree_path=request["isolation"]["worktree_path"],
        branch=request["isolation"]["branch"],
    )
    return value


def _launch(
    adapter: ExecutionAdapter,
    workspace: Path,
    request: dict[str, Any],
    *,
    owner: str = "owner-nonce-0001",
) -> None:
    adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=request["lease_generation"],
        owner_nonce=owner,
    )
    adapter.acknowledge(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=request["lease_generation"],
        handle="task-alpha-001",
    )
    adapter.enter(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=request["lease_generation"],
        owner_nonce=owner,
    )


def test_lifecycle_fixtures_are_schema_valid() -> None:
    schema_root = (
        _REPO_ROOT
        / "openspec"
        / "changes"
        / "wire-supervise-execution-through-the-dispatch-fn-seam"
        / "contracts"
        / "schemas"
    )
    result_validator = Draft202012Validator(
        json.loads((schema_root / "supervised-dispatch-result.schema.json").read_text()),
        format_checker=FormatChecker(),
    )
    context_validator = Draft202012Validator(
        json.loads((schema_root / "bounded-dispatch-context.schema.json").read_text()),
        format_checker=FormatChecker(),
    )

    assert list(result_validator.iter_errors(json.loads((_FIXTURES / "success-result.json").read_text()))) == []
    assert list(result_validator.iter_errors(json.loads((_FIXTURES / "parked-result.json").read_text()))) == []
    assert list(context_validator.iter_errors(json.loads((_FIXTURES / "router-context.json").read_text()))) == []


def test_prepare_sanitizes_router_context_before_checkpoint_persistence(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    clock = FakeClock()
    context = json.loads((_FIXTURES / "router-context.json").read_text())

    prepared = _prepare(_adapter(managed_root, clock), workspace, repo, managed_root, context=context)

    assert prepared["requests"][0]["context"] == context
    assert _attempt(workspace)["context"] == context


@pytest.mark.parametrize(
    "unsafe",
    [
        {"routing": {"metadata": {"Api_Token": "nope"}}},
        {"a": {"b": {"c": {"d": {"too_deep": True}}}}},
        {"routing": {"raw-response": "SENTINEL_DO_NOT_PERSIST"}},
        {"items": list(range(65))},
        {f"key-{index}": index for index in range(33)},
        {"value": "x" * 4097},
        {f"field-{index}": "x" * 3500 for index in range(5)},
    ],
)
def test_prepare_rejects_unsafe_nested_context_before_any_checkpoint_write(
    tmp_path: Path,
    unsafe: dict[str, Any],
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)

    with pytest.raises(ValueError, match="dispatch context"):
        _prepare(_adapter(managed_root, FakeClock()), workspace, repo, managed_root, context=unsafe)

    assert not (workspace / "checkpoint.json").exists()


def test_prepare_rejects_managed_isolation_before_launch_or_attempt_persistence(
    tmp_path: Path,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    outside = repo / "outside"
    outside.mkdir()
    adapter = _adapter(managed_root, FakeClock())

    with pytest.raises(ValueError, match="managed worktree containment"):
        adapter.prepare(
            workspace,
            repo_root=repo,
            isolation_resolver=lambda _: {
                "mode": "managed_worktree",
                "worktree_path": str(outside),
                "branch": "openspec/change-alpha",
            },
        )

    assert json.loads((workspace / "checkpoint.json").read_text()).get(
        "dispatch_attempts", []
    ) == []


def test_prepare_rejects_exact_managed_branch_mismatch(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = ExecutionAdapter(
        managed_worktree_root=managed_root,
        clock=FakeClock(),
        branch_resolver=lambda _: "openspec/wrong-change",
        liveness_probe=lambda _: "live",
        host_entry=lambda *_: pytest.fail("host entry must not run"),
    )

    with pytest.raises(ValueError, match="managed worktree branch"):
        _prepare(adapter, workspace, repo, managed_root)

    assert _attempt_count(workspace) == 0


def _attempt_count(workspace: Path) -> int:
    path = workspace / "checkpoint.json"
    return len(json.loads(path.read_text()).get("dispatch_attempts", [])) if path.exists() else 0


def test_child_start_waits_for_durable_ack_and_go_before_host_entry(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    clock = FakeClock()
    host_calls: list[tuple[str, dict[str, Any]]] = []
    adapter = _adapter(managed_root, clock, host_calls=host_calls)
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]

    claimed = adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
    )
    assert claimed["status"] == "claimed"
    assert claimed["launch_gate"]["state"] == "waiting_ack"
    assert Path(request["isolation"]["worktree_path"], request["launch_marker_path"]).exists()
    with pytest.raises(ValueError, match="go has not been released"):
        adapter.enter(
            workspace,
            dispatch_id=request["dispatch_id"],
            lease_generation=1,
            owner_nonce="owner-nonce-0001",
        )
    assert host_calls == []

    acknowledged = adapter.acknowledge(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=1,
        handle="task-alpha-001",
    )
    assert acknowledged["status"] == "acknowledged"
    assert acknowledged["launch_gate"]["state"] == "go_released"
    entered = adapter.enter(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
    )
    assert entered["status"] == "launched"
    assert entered["launch_gate"]["state"] == "entered"
    assert [change_id for change_id, _ in host_calls] == ["change-alpha"]


def test_marker_collision_refuses_duplicate_owner_without_state_change(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    marker = Path(request["isolation"]["worktree_path"], request["launch_marker_path"])
    marker.write_text("other-owner\n")

    with pytest.raises(FileExistsError):
        adapter.child_start(
            workspace,
            dispatch_id=request["dispatch_id"],
            launch_token=request["launch_token"],
            lease_generation=1,
            owner_nonce="owner-nonce-0001",
        )

    assert _attempt(workspace)["status"] == "prepared"


def test_waiting_heartbeat_is_child_owned_and_generation_bound(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    clock = FakeClock()
    adapter = _adapter(managed_root, clock)
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
    )
    before = _attempt(workspace)["lease"]["heartbeat_at"]
    clock.advance(10)

    updated = adapter.heartbeat_waiting(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
    )
    assert updated["lease"]["heartbeat_at"] != before
    with pytest.raises(ValueError, match="lease owner"):
        adapter.heartbeat_waiting(
            workspace,
            dispatch_id=request["dispatch_id"],
            lease_generation=1,
            owner_nonce="owner-nonce-other",
        )


def test_expired_pre_go_claim_allows_generation_cas_takeover(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    clock = FakeClock()
    adapter = _adapter(managed_root, clock)
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=1,
        owner_nonce="owner-nonce-0001",
        lease_seconds=5,
    )
    clock.advance(6)

    reclaimed = adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=1,
        owner_nonce="owner-nonce-0002",
    )

    assert reclaimed["lease_generation"] == 2
    assert reclaimed["lease"]["generation"] == 2
    assert reclaimed["lease"]["owner_nonce"] == "owner-nonce-0002"
    assert [entry["state"] for entry in reclaimed["launch_history"][-2:]] == [
        "stale_takeover",
        "claimed",
    ]
    with pytest.raises(ValueError, match="generation"):
        adapter.acknowledge(
            workspace,
            dispatch_id=request["dispatch_id"],
            lease_generation=1,
            handle="stale-task",
        )
    adapter.acknowledge(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=2,
        handle="task-alpha-002",
    )
    with pytest.raises(ValueError, match="generation"):
        adapter.enter(
            workspace,
            dispatch_id=request["dispatch_id"],
            lease_generation=1,
            owner_nonce="owner-nonce-0001",
        )


def test_harness_provided_isolation_preserves_exact_external_path_and_branch(
    tmp_path: Path,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    harness_path = repo / "harness-checkout"
    (harness_path / ".git" / "autopilot").mkdir(parents=True)
    adapter = ExecutionAdapter(
        managed_worktree_root=managed_root,
        clock=FakeClock(),
        branch_resolver=lambda path: "harness/session-123"
        if path == harness_path.resolve()
        else "unexpected",
        liveness_probe=lambda _: "live",
        host_entry=lambda *_: "entered",
    )

    prepared = adapter.prepare(
        workspace,
        repo_root=repo,
        isolation_resolver=lambda _: {
            "mode": "harness_provided",
            "worktree_path": str(harness_path),
            "branch": "harness/session-123",
        },
    )

    assert prepared["requests"][0]["isolation"] == {
        "mode": "harness_provided",
        "worktree_path": str(harness_path.resolve()),
        "branch": "harness/session-123",
    }


def test_positive_live_reconciliation_preserves_generation_and_owner(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock(), liveness="live")
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    before = _attempt(workspace)

    reconciled = adapter.reconcile(workspace, dispatch_id=request["dispatch_id"])

    assert reconciled == before
    assert reconciled["lease_generation"] == 1
    assert reconciled["lease"]["owner_nonce"] == "owner-nonce-0001"


def test_unknown_post_go_liveness_quarantines_and_never_resumes(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock(), liveness="unknown")
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)

    reconciled = adapter.reconcile(workspace, dispatch_id=request["dispatch_id"])

    assert reconciled["status"] == "quarantined"
    assert reconciled["lease"]["state"] == "uncertain"
    with pytest.raises(ValueError, match="quarantined"):
        adapter.resume(
            workspace,
            dispatch_id=request["dispatch_id"],
            approval_ref="approval-001",
            kind="pending_gate",
        )


def test_only_positive_task_death_allows_post_go_generation_takeover(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    clock = FakeClock()
    adapter = _adapter(managed_root, clock, liveness="dead")
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)

    reclaimed = adapter.reconcile(workspace, dispatch_id=request["dispatch_id"])

    assert reclaimed["status"] == "prepared"
    assert reclaimed["lease_generation"] == 2
    restarted = adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=2,
        owner_nonce="owner-nonce-0002",
    )
    assert restarted["status"] == "claimed"


def test_parked_attempt_releases_lease_and_authorized_resume_increments_generation(
    tmp_path: Path,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("parked-result.json", request)

    applied = adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[result],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    assert applied["parked_item_ids"] == ["ri-01"]
    assert _attempt(workspace)["lease"]["state"] == "released"

    resumed = adapter.resume(
        workspace,
        dispatch_id=request["dispatch_id"],
        approval_ref="approval-001",
        kind="pending_gate",
    )
    assert resumed["dispatch_id"] == request["dispatch_id"]
    assert resumed["attempt"] == request["attempt"]
    assert resumed["launch_token"] == request["launch_token"]
    assert resumed["lease_generation"] == 2
    assert resumed["continuation"] == {
        "kind": "pending_gate",
        "approval_ref": "approval-001",
    }
    with pytest.raises(ValueError, match="not parked"):
        adapter.resume(
            workspace,
            dispatch_id=request["dispatch_id"],
            approval_ref="approval-002",
            kind="pending_gate",
        )


def test_resumed_parked_generation_runs_normal_ack_go_with_exact_continuation(
    tmp_path: Path,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    host_calls: list[tuple[str, dict[str, Any]]] = []
    adapter = _adapter(managed_root, FakeClock(), host_calls=host_calls)
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    parked = _result("parked-result.json", request)
    adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[parked],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    resumed = adapter.resume(
        workspace,
        dispatch_id=request["dispatch_id"],
        approval_ref="approval-001",
        kind="pending_gate",
    )

    claimed = adapter.child_start(
        workspace,
        dispatch_id=request["dispatch_id"],
        launch_token=request["launch_token"],
        lease_generation=2,
        owner_nonce="owner-nonce-0002",
    )
    assert claimed["status"] == "claimed"
    adapter.acknowledge(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=2,
        handle="task-alpha-002",
    )
    entered = adapter.enter(
        workspace,
        dispatch_id=request["dispatch_id"],
        lease_generation=2,
        owner_nonce="owner-nonce-0002",
    )

    assert entered["status"] == "launched"
    assert host_calls[-1][1]["continuation"] == resumed["continuation"]
    with pytest.raises(ValueError):
        adapter.enter(
            workspace,
            dispatch_id=request["dispatch_id"],
            lease_generation=1,
            owner_nonce="owner-nonce-0001",
        )
    marker = Path(request["isolation"]["worktree_path"], request["launch_marker_path"])
    marker_record = json.loads(marker.read_text())
    assert marker_record["generation"] == 2
    assert marker_record["owner_nonce"] == "owner-nonce-0002"


def test_failed_child_start_never_creates_an_orphan_marker(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    marker = Path(request["isolation"]["worktree_path"], request["launch_marker_path"])

    with pytest.raises(ValueError, match="owner nonce"):
        adapter.child_start(
            workspace,
            dispatch_id=request["dispatch_id"],
            launch_token=request["launch_token"],
            lease_generation=1,
            owner_nonce="short",
        )

    assert not marker.exists()
    assert _attempt(workspace)["status"] == "prepared"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda result: result.update(worktree_path="/other"), "worktree"),
        (lambda result: result.update(branch="openspec/other"), "branch"),
        (
            lambda result: result["evidence"].update(loop_state_path="../outside.json"),
            "loop-state containment",
        ),
        (
            lambda result: result["evidence"].update(loop_state_digest="0" * 64),
            "loop-state digest",
        ),
    ],
)
def test_apply_rejects_exact_isolation_and_loop_state_evidence_before_callback(
    tmp_path: Path,
    mutation: Any,
    message: str,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    mutation(result)
    calls: list[str] = []

    with pytest.raises(ValueError, match=message):
        adapter.apply(
            workspace,
            batch_id=request["dispatch_id"].split(":", 1)[0],
            results=[result],
            dispatch_fn=lambda item, _phase, _context: calls.append(item) or "success",
            repo_root=repo,
        )

    assert calls == []
    assert _attempt(workspace)["status"] == "launched"


def test_apply_rejects_noncanonical_inside_worktree_evidence_before_callback(
    tmp_path: Path,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    other = Path(request["isolation"]["worktree_path"]) / ".git" / "autopilot" / "other.json"
    other.write_text('{"status":"other"}\n')
    result["evidence"]["loop_state_path"] = ".git/autopilot/other.json"
    calls: list[str] = []

    with pytest.raises(ValueError, match="exact loop-state path"):
        adapter.apply(
            workspace,
            batch_id=request["dispatch_id"].split(":", 1)[0],
            results=[result],
            dispatch_fn=lambda item, _phase, _context: calls.append(item) or "success",
            repo_root=repo,
        )

    assert calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gate", 7),
        ("deadline", "not-a-date-time"),
        ("resume_hint", 7),
    ],
)
def test_invalid_optional_parked_fields_never_reach_temp_result_file(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    observed: list[Path] = []
    adapter = ExecutionAdapter(
        managed_worktree_root=managed_root,
        clock=FakeClock(),
        branch_resolver=lambda _: "openspec/change-alpha",
        liveness_probe=lambda _: "live",
        host_entry=lambda *_: "entered",
        result_file_observer=observed.append,
    )
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("parked-result.json", request)
    result["parked"][field] = value

    with pytest.raises(ValueError, match="schema-valid"):
        adapter.apply(
            workspace,
            batch_id=request["dispatch_id"].split(":", 1)[0],
            results=[result],
            dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
            repo_root=repo,
        )

    assert observed == []
    assert _attempt(workspace)["status"] == "launched"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda result: result.update(schema_version=True),
        lambda result: result.update(outcome="failed:boom", worktree_path=7),
        lambda result: result.update(outcome="vendor_limit:test:busy", branch=""),
    ],
)
def test_invalid_result_scalar_types_never_reach_temp_result_file(
    tmp_path: Path,
    mutation: Any,
) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    observed: list[Path] = []
    adapter = ExecutionAdapter(
        managed_worktree_root=managed_root,
        clock=FakeClock(),
        branch_resolver=lambda _: "openspec/change-alpha",
        liveness_probe=lambda _: "live",
        host_entry=lambda *_: "entered",
        result_file_observer=observed.append,
    )
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    mutation(result)

    with pytest.raises(ValueError, match="schema-valid"):
        adapter.apply(
            workspace,
            batch_id=request["dispatch_id"].split(":", 1)[0],
            results=[result],
            dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
            repo_root=repo,
        )

    assert observed == []
    assert _attempt(workspace)["status"] == "launched"


def test_apply_rejects_symlinked_loop_state_escape_before_callback(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    worktree = Path(request["isolation"]["worktree_path"])
    outside = repo / "outside-loop-state.json"
    outside.write_text('{"status":"outside"}\n')
    link = worktree / ".git" / "autopilot" / "loop-state.json"
    link.unlink()
    link.symlink_to(outside)
    calls: list[str] = []

    with pytest.raises(ValueError, match="loop-state containment"):
        adapter.apply(
            workspace,
            batch_id=request["dispatch_id"].split(":", 1)[0],
            results=[result],
            dispatch_fn=lambda item, _phase, _context: calls.append(item) or "success",
            repo_root=repo,
        )

    assert calls == []
    assert _attempt(workspace)["status"] == "launched"


def test_apply_accepts_exact_digest_and_uses_bounded_temp_result_only(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    loop_state = Path(request["isolation"]["worktree_path"]) / result["evidence"][
        "loop_state_path"
    ]
    result["evidence"]["loop_state_digest"] = hashlib.sha256(loop_state.read_bytes()).hexdigest()

    applied = adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[result],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )

    assert applied["completed_item_ids"] == ["ri-01"]
    durable = json.dumps(json.loads((workspace / "checkpoint.json").read_text()))
    assert "transcript" not in durable.lower()


def test_adapter_source_has_no_model_provider_or_network_boundary() -> None:
    source = (_SCRIPTS / "execution.py").read_text()
    tree = ast.parse(source)
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint({"anthropic", "openai", "google", "litellm", "httpx", "requests"})
