"""End-to-end proof of the supervised background-dispatch host boundary."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from models import Effort, ItemStatus, Roadmap, RoadmapItem, load_roadmap


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SUPERVISE_SCRIPTS = _REPO_ROOT / "skills" / "supervise" / "scripts"
sys.path.insert(0, str(_SUPERVISE_SCRIPTS))

from execution import ExecutionAdapter  # noqa: E402
import gate_router  # noqa: E402
from checkpoint import CheckpointManager  # noqa: E402
from shared.approval_gate import (  # noqa: E402
    ApprovalDecision,
    Disposition as _ApprovalDisposition,
    Outcome as _ApprovalOutcome,
    Resolution as _ApprovalResolution,
    build_gate_decision_record,
)
from shared.trust_posture import Gate  # noqa: E402


_FIXTURE = (
    Path(__file__).parent / "fixtures" / "supervised-dispatch" / "scenarios.json"
)
_CONTRACT_ROOT = (
    _REPO_ROOT
    / "openspec/contracts/roadmap-orchestration/schemas"
)


def _write_work_packages(repo: Path, entry: dict[str, Any]) -> None:
    change_id = entry["change_id"]
    package = {
        "package_id": f"wp-{change_id}",
        "task_type": "implementation",
        "description": f"Integration fixture for {change_id}",
        "depends_on": [],
        "priority": 1,
        "locks": {"files": [], "keys": [f"feature:{change_id}:fixture"]},
        "scope": {"write_allow": [entry["scope"]], "read_allow": ["**"]},
        "worktree": {"name": change_id},
        "timeout_minutes": 10,
        "retry_budget": 0,
        "min_trust_level": 0,
        "verification": {
            "tier_required": "C",
            "steps": [{
                "name": "fixture",
                "kind": "command",
                "command": "true",
                "evidence": {"artifacts": [], "result_keys": ["fixture"]},
            }],
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
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _build_runtime(
    tmp_path: Path,
    scenario: list[dict[str, Any]],
) -> tuple[Path, Path, Path, dict[str, str]]:
    repo = tmp_path / "repo"
    schemas = repo / "openspec" / "schemas"
    schemas.mkdir(parents=True)
    for name in ("roadmap.schema.json", "checkpoint.schema.json"):
        (schemas / name).write_text(
            (_REPO_ROOT / "openspec" / "schemas" / name).read_text(),
            encoding="utf-8",
        )
    workspace = repo / "roadmap"
    workspace.mkdir()
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id="roadmap-e2e",
        source_proposal="proposal.md",
        items=[
            RoadmapItem(
                entry["item_id"],
                entry["change_id"],
                ItemStatus.APPROVED,
                entry["priority"],
                Effort.S,
                change_id=entry["change_id"],
            )
            for entry in scenario
        ],
    )
    (workspace / "roadmap.yaml").write_text(
        yaml.safe_dump(roadmap.to_dict(), sort_keys=False), encoding="utf-8"
    )
    managed_root = repo / ".git-worktrees"
    branches: dict[str, str] = {}
    for entry in scenario:
        _write_work_packages(repo, entry)
        worktree = managed_root / entry["change_id"]
        worktree.mkdir(parents=True)
        (worktree / ".git").write_text(
            f"gitdir: /tmp/fake-{entry['change_id']}-gitdir\n",
            encoding="utf-8",
        )
        loop_state = (
            worktree
            / "openspec"
            / "changes"
            / entry["change_id"]
            / "loop-state.json"
        )
        loop_state.parent.mkdir(parents=True)
        handoff_id = f"handoff-{entry['item_id']}"
        loop_state.write_text(
            json.dumps(
                {
                    "schema_version": 5,
                    "change_id": entry["change_id"],
                    "current_phase": "DONE",
                    "handoff_ids": [handoff_id],
                    "last_handoff_id": handoff_id,
                    "pending_gate": None,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        branches[str(worktree.resolve())] = f"openspec/{entry['change_id']}"
    return repo, workspace, managed_root, branches


def _result(request: dict[str, Any]) -> dict[str, Any]:
    loop_state_path = (
        Path(request["isolation"]["worktree_path"])
        / "openspec"
        / "changes"
        / request["change_id"]
        / "loop-state.json"
    )
    return {
        "schema_version": 1,
        "dispatch_id": request["dispatch_id"],
        "change_id": request["change_id"],
        "attempt": request["attempt"],
        "lease_generation": request["lease_generation"],
        "outcome": "success",
        "handoff_id": f"handoff-{request['item_id']}",
        "worktree_path": request["isolation"]["worktree_path"],
        "branch": request["isolation"]["branch"],
        "evidence": {
            "loop_state_path": f"openspec/changes/{request['change_id']}/loop-state.json",
            "commit": "a" * 40,
            "loop_state_digest": hashlib.sha256(loop_state_path.read_bytes()).hexdigest(),
        },
    }


class FakeHostCapture:
    """Threaded host capture that never exposes child transcript text."""

    def __init__(self, sentinels: dict[str, str]) -> None:
        self.sentinels = sentinels
        self.events: list[dict[str, Any]] = []
        self.child_transcripts: dict[str, str] = {}
        self.result_files: list[str] = []
        self.max_live = 0
        self._live = 0
        self._lock = threading.Lock()
        self._workers: dict[str, dict[str, Any]] = {}
        self._barrier: threading.Barrier | None = None

    def child_entry(self, change_id: str, request: dict[str, Any]) -> str:
        worker = self._workers[request["dispatch_id"]]
        transcript = (
            f"private child transcript for {change_id}: "
            f"{self.sentinels[change_id]}"
        )
        with self._lock:
            self.child_transcripts[change_id] = transcript
            self._live += 1
            self.max_live = max(self.max_live, self._live)
        worker["entered"].set()
        try:
            if self._barrier is not None:
                self._barrier.wait(timeout=5)
            assert self.sentinels[change_id] in transcript
            return "entered"
        finally:
            with self._lock:
                self._live -= 1

    def observe_result_file(self, path: Path) -> None:
        self.result_files.append(path.read_text(encoding="utf-8"))

    def run_batch(
        self,
        adapter: ExecutionAdapter,
        workspace: Path,
        requests: list[dict[str, Any]],
        request_validator: Draft202012Validator,
        result_validator: Draft202012Validator,
    ) -> tuple[list[dict[str, Any]], int]:
        self._barrier = threading.Barrier(len(requests)) if len(requests) > 1 else None
        self._workers = {}
        errors: list[BaseException] = []
        for index, request in enumerate(requests, start=1):
            assert list(request_validator.iter_errors(request)) == []
            worker: dict[str, Any] = {
                "request": request,
                "claimed": threading.Event(),
                "go": threading.Event(),
                "entered": threading.Event(),
                "handle": f"task-{index:02d}",
                "owner": f"owner-{index:02d}-nonce-00000000",
            }
            self._workers[request["dispatch_id"]] = worker
            self.events.append({"kind": "request", "value": request})

            def child(target: dict[str, Any] = worker) -> None:
                value = target["request"]
                try:
                    adapter.child_start(
                        workspace,
                        dispatch_id=value["dispatch_id"],
                        launch_token=value["launch_token"],
                        lease_generation=value["lease_generation"],
                        owner_nonce=target["owner"],
                    )
                    target["claimed"].set()
                    target["go"].wait(timeout=5)
                    adapter.enter(
                        workspace,
                        dispatch_id=value["dispatch_id"],
                        lease_generation=value["lease_generation"],
                        owner_nonce=target["owner"],
                    )
                    target["result"] = _result(value)
                except BaseException as error:  # pragma: no cover - surfaced below
                    errors.append(error)
                    target["claimed"].set()
                    target["entered"].set()

            worker["thread"] = threading.Thread(target=child, daemon=True)
            worker["thread"].start()
            assert worker["claimed"].wait(timeout=5), errors
            self.events.append({
                "kind": "task_handle",
                "dispatch_id": request["dispatch_id"],
                "handle": worker["handle"],
            })

        live_before_await = sum(
            worker["thread"].is_alive() for worker in self._workers.values()
        )
        for worker in self._workers.values():
            request = worker["request"]
            adapter.acknowledge(
                workspace,
                dispatch_id=request["dispatch_id"],
                lease_generation=request["lease_generation"],
                handle=worker["handle"],
            )
            self.events.append({
                "kind": "lease_event",
                "dispatch_id": request["dispatch_id"],
                "state": "go_released",
            })
        for worker in self._workers.values():
            worker["go"].set()
            assert worker["entered"].wait(timeout=5), errors

        self.events.append({"kind": "result_await", "count": len(requests)})
        results: list[dict[str, Any]] = []
        for worker in self._workers.values():
            worker["thread"].join(timeout=5)
            assert not worker["thread"].is_alive()
            assert errors == []
            result = worker["result"]
            assert list(result_validator.iter_errors(result)) == []
            results.append(result)
            self.events.append({"kind": "result", "value": result})
        return results, live_before_await


def _approve_roadmap(workspace: Path, roadmap_id: str = "roadmap-e2e") -> str:
    """Inject a `proceed` roadmap_approval gate-decision record, stamped with
    the roadmap's current fingerprint (D3/D5 -- `require_approval_ref` always
    recomputes and compares it), and return the resulting `approval_ref`."""
    import uuid as _uuid

    roadmap = load_roadmap(workspace / "roadmap.yaml", None)
    decision = ApprovalDecision(
        gate=Gate.ROADMAP_APPROVAL,
        outcome=_ApprovalOutcome.PROCEED,
        resolution=_ApprovalResolution.AUTO,
        disposition=_ApprovalDisposition.AUTO,
        reason="roadmap_approval auto-approved by e2e fixture",
        posture_present=True,
    )
    record = build_gate_decision_record(
        decision,
        phase="SUPERVISE",
        extra={
            "decision_id": str(_uuid.uuid4()),
            "source": "supervise",
            "verb": "execute",
            "roadmap_id": roadmap_id,
            "roadmap_fingerprint": gate_router.roadmap_fingerprint(roadmap),
        },
    )
    manager = CheckpointManager(workspace)
    checkpoint = manager.load() if manager.exists() else manager.create(roadmap)
    manager.record_gate_decision(checkpoint, record)
    return f"gate-decision:{record['decision_id']}"


def _run_scenario(
    tmp_path: Path,
    scenario: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any]:
    repo, workspace, managed_root, branches = _build_runtime(tmp_path, scenario)
    schemas = [
        json.loads((_CONTRACT_ROOT / name).read_text())
        for name in (
            "bounded-dispatch-context.schema.json",
            "supervised-dispatch-request.schema.json",
            "supervised-dispatch-result.schema.json",
        )
    ]
    registry = Registry().with_resources(
        [
            (
                schema["$id"],
                Resource.from_contents(schema, default_specification=DRAFT202012),
            )
            for schema in schemas
        ]
    )
    validators = [
        Draft202012Validator(
            schema, registry=registry, format_checker=FormatChecker()
        )
        for schema in schemas[1:]
    ]
    host = FakeHostCapture({entry["change_id"]: entry["sentinel"] for entry in scenario})
    adapter = ExecutionAdapter(
        managed_worktree_root=managed_root,
        branch_resolver=lambda path: branches[str(path.resolve())],
        commit_resolver=lambda _: "a" * 40,
        liveness_probe=lambda _: "live",
        host_entry=host.child_entry,
        temp_dir=tmp_path / "results",
        result_file_observer=host.observe_result_file,
    )
    def isolate(item: RoadmapItem) -> dict[str, str]:
        return {
            "mode": "managed_worktree",
            "worktree_path": str(managed_root / item.change_id),
            "branch": f"openspec/{item.change_id}",
        }
    batches: list[list[dict[str, Any]]] = []
    live_counts: list[int] = []
    calls: list[str] = []
    all_results: list[dict[str, Any]] = []
    roadmap_approval_ref = _approve_roadmap(workspace)
    while True:
        prepared = adapter.prepare(
            workspace,
            repo_root=repo,
            isolation_resolver=isolate,
            roadmap_approval_ref=roadmap_approval_ref,
            context=context,
        )
        if not prepared["requests"]:
            break
        batches.append(prepared["requests"])
        results, live = host.run_batch(
            adapter, workspace, prepared["requests"], *validators
        )
        live_counts.append(live)
        all_results.extend(results)
        adapter.apply(
            workspace,
            batch_id=prepared["batch_id"],
            results=results,
            dispatch_fn=lambda item, _phase, value: calls.append(item)
            or value["dispatch_result"],
            repo_root=repo,
        )
    outcomes = [
        {"outcome": value["outcome"], "handoff_id": value["handoff_id"]}
        for value in all_results
    ]
    supervisor = repo / "openspec" / "supervise" / "supervisor-record.json"
    supervisor.parent.mkdir(parents=True)
    supervisor.write_text(json.dumps({"outcomes": outcomes}))
    (workspace / "handoff.json").write_text(json.dumps({"outcomes": outcomes}))
    return {
        "repo": repo,
        "workspace": workspace,
        "host": host,
        "batches": batches,
        "live_counts": live_counts,
        "calls": calls,
        "sentinels": [entry["sentinel"] for entry in scenario],
    }


def _assert_outcome_only(result: dict[str, Any]) -> None:
    events = result["host"].events
    child_transcripts = result["host"].child_transcripts
    assert len(child_transcripts) == len(result["sentinels"])
    for sentinel in result["sentinels"]:
        assert sum(sentinel in transcript for transcript in child_transcripts.values()) == 1
    assert result["host"].result_files
    assert {event["kind"] for event in events} == {
        "request", "task_handle", "lease_event", "result_await", "result"
    }
    parent_text = json.dumps(events, sort_keys=True)
    durable_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in result["repo"].rglob("*")
        if path.is_file()
    )
    for sentinel in result["sentinels"]:
        assert sentinel not in parent_text
        assert sentinel not in durable_text
        assert all(sentinel not in content for content in result["host"].result_files)
    checkpoint = json.loads((result["workspace"] / "checkpoint.json").read_text())
    expected_context = {
        "router_vendor": "fixture-router",
        "routing": {"model": "fixture-model"},
    }
    assert all(
        attempt["context"] == expected_context
        and "transcript" not in attempt
        for attempt in checkpoint["dispatch_attempts"]
    )


def test_disjoint_children_are_live_together_in_distinct_isolation_without_transcripts(
    tmp_path: Path,
) -> None:
    fixture = json.loads(_FIXTURE.read_text())
    result = _run_scenario(tmp_path, fixture["disjoint"], fixture["router_context"])

    assert [len(batch) for batch in result["batches"]] == [2]
    assert result["live_counts"] == [2]
    assert result["host"].max_live == 2
    requests = result["batches"][0]
    assert len({value["isolation"]["worktree_path"] for value in requests}) == 2
    assert len({value["isolation"]["branch"] for value in requests}) == 2
    await_index = next(
        index for index, event in enumerate(result["host"].events)
        if event["kind"] == "result_await"
    )
    assert sum(
        event["kind"] == "task_handle"
        for event in result["host"].events[:await_index]
    ) == 2
    assert result["calls"] == ["ri-01", "ri-02"]
    _assert_outcome_only(result)


def test_overlapping_children_are_serialized_with_maximum_one_live_handle(
    tmp_path: Path,
) -> None:
    fixture = json.loads(_FIXTURE.read_text())
    result = _run_scenario(tmp_path, fixture["overlapping"], fixture["router_context"])

    assert [len(batch) for batch in result["batches"]] == [1, 1]
    assert [
        [request["scope"]["proof"] for request in batch]
        for batch in result["batches"]
    ] == [["serial_indeterminate"], ["serial_indeterminate"]]
    assert result["live_counts"] == [1, 1]
    assert result["host"].max_live == 1
    assert result["calls"] == ["ri-01", "ri-02"]
    _assert_outcome_only(result)
