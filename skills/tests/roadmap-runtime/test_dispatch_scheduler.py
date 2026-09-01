"""Scope-boundary tests for deterministic delegated dispatch batching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from dispatch_scheduler import (
    ReadyDispatchItem,
    ScopeEvidence,
    ScopeRelation,
    aggregate_change_scope,
    classify_scope_relationship,
    select_safe_ready_batch,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "dispatch-scopes"
_SCHEMA_ROOT = (
    _REPO_ROOT
    / "openspec"
    / "changes"
    / "wire-supervise-execution-through-the-dispatch-fn-seam"
    / "contracts"
    / "schemas"
)
_REQUEST_SCHEMA = _SCHEMA_ROOT / "supervised-dispatch-request.schema.json"
_CONTEXT_SCHEMA = _SCHEMA_ROOT / "bounded-dispatch-context.schema.json"
_INVALID_WORK_PACKAGES = _FIXTURE_ROOT / "invalid-work-packages.invalid.yaml"


def _scenario_root(tmp_path: Path, change_id: str) -> Path:
    if change_id != "invalid-work-packages":
        return _FIXTURE_ROOT
    repo_root = tmp_path / "invalid-scope-fixture"
    target = (
        repo_root
        / "openspec"
        / "changes"
        / change_id
        / "work-packages.yaml"
    )
    target.parent.mkdir(parents=True)
    target.write_text(_INVALID_WORK_PACKAGES.read_text(), encoding="utf-8")
    return repo_root


def _scope(*writes: str, locks: tuple[str, ...] = ()) -> ScopeEvidence:
    return ScopeEvidence(
        change_id="scope-fixture",
        proof="proven_disjoint",
        write_allow=tuple(writes),
        lock_keys=locks,
        package_ids=("wp-scope",),
    )


def test_aggregate_change_scope_includes_integration_and_runtime_mirror_packages() -> None:
    scope = aggregate_change_scope(_FIXTURE_ROOT, "disjoint-alpha")

    assert scope.proof == "proven_disjoint"
    assert scope.package_ids == ("wp-core", "wp-integration", "wp-runtime-mirror")
    assert scope.write_allow == (
        ".agents/skills/alpha/**",
        "docs/alpha/**",
        "src/alpha/**",
    )
    assert scope.lock_keys == (
        "contract:alpha",
        "feature:alpha:integration",
        "feature:alpha:runtime-mirror",
    )


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (_scope("src/alpha/**"), _scope("src/beta/**"), ScopeRelation.PROVEN_DISJOINT),
        (_scope("src/**"), _scope("src/alpha/**"), ScopeRelation.OVERLAP),
        (
            _scope("src/alpha/**", locks=("contract:shared",)),
            _scope("src/beta/**", locks=("contract:shared",)),
            ScopeRelation.OVERLAP,
        ),
        (_scope("a/*/c"), _scope("a/b/*"), ScopeRelation.AMBIGUOUS),
    ],
)
def test_scope_relationship_is_conservative_and_tri_state(
    first: ScopeEvidence,
    second: ScopeEvidence,
    expected: ScopeRelation,
) -> None:
    assert classify_scope_relationship(first, second) is expected


def test_schema_invalid_but_scope_shaped_document_fails_closed() -> None:
    scope = aggregate_change_scope(_FIXTURE_ROOT, "schema-invalid-shaped")

    assert scope.proof == "serial_indeterminate"
    assert scope.reason == "work_packages_invalid"


@pytest.mark.parametrize(
    "change_id",
    ["missing-work-packages", "invalid-work-packages", "empty-scope", "boundless-scope"],
)
def test_indeterminate_scope_is_a_schema_valid_singleton(
    change_id: str, tmp_path: Path
) -> None:
    repo_root = _scenario_root(tmp_path, change_id)
    plan = select_safe_ready_batch(
        repo_root,
        [
            ReadyDispatchItem(item_id="ri-02", change_id="disjoint-beta", priority=2),
            ReadyDispatchItem(item_id="ri-01", change_id=change_id, priority=1),
        ],
    )

    assert [item.item_id for item in plan.items] == ["ri-01"]
    assert plan.items[0].scope.proof == "serial_indeterminate"
    assert plan.deferred_item_ids == ("ri-02",)

    request = {
        "schema_version": 1,
        "dispatch_id": "roadmap-fixture:ri-01:attempt-1",
        "roadmap_id": "roadmap-fixture",
        "item_id": "ri-01",
        "change_id": change_id,
        "phase": "autopilot",
        "attempt": 1,
        "launch_token": "launch-token-0001",
        "lease_generation": 1,
        "launch_marker_path": ".git/autopilot/ri-01.marker",
        "scope": plan.items[0].scope.to_request_scope(),
        "isolation": {
            "mode": "managed_worktree",
            "worktree_path": "/workspace/ri-01",
            "branch": f"openspec/{change_id}",
        },
        "context": {},
    }
    request_schema = json.loads(_REQUEST_SCHEMA.read_text())
    context_schema = json.loads(_CONTEXT_SCHEMA.read_text())
    registry = Registry().with_resource(
        context_schema["$id"],
        Resource.from_contents(context_schema, default_specification=DRAFT202012),
    )
    validator = Draft202012Validator(request_schema, registry=registry)
    assert list(validator.iter_errors(request)) == []


def test_batch_is_deterministic_priority_item_id_maximal_and_preserves_evidence() -> None:
    plan = select_safe_ready_batch(
        _FIXTURE_ROOT,
        [
            ReadyDispatchItem(item_id="ri-03", change_id="overlaps-beta", priority=2),
            ReadyDispatchItem(item_id="ri-02", change_id="disjoint-alpha", priority=2),
            ReadyDispatchItem(item_id="ri-01", change_id="disjoint-beta", priority=1),
        ],
    )

    assert [item.item_id for item in plan.items] == ["ri-01", "ri-02"]
    assert plan.deferred_item_ids == ("ri-03",)
    assert all(item.scope.proof == "proven_disjoint" for item in plan.items)
    assert plan.items[1].scope.package_ids == (
        "wp-core",
        "wp-integration",
        "wp-runtime-mirror",
    )


@pytest.mark.parametrize("change_id", [None, "", "Invalid-ID", "path/traversal"])
def test_missing_or_invalid_change_id_is_not_dispatched(change_id: str | None) -> None:
    plan = select_safe_ready_batch(
        _FIXTURE_ROOT,
        [ReadyDispatchItem(item_id="ri-01", change_id=change_id, priority=1)],
    )

    assert plan.items == ()
    assert plan.deferred_item_ids == ()
    assert [(failure.item_id, failure.reason) for failure in plan.failures] == [
        ("ri-01", "invalid_change_id")
    ]
