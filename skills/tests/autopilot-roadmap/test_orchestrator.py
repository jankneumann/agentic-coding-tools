"""Tests for the roadmap orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

import yaml
from models import (
    Effort,
    ItemStatus,
    Policy,
    PolicyAction,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
)
from orchestrator import _handle_vendor_limit, execute_roadmap


def _write_roadmap(workspace: Path, items: list[RoadmapItem] | None = None, **kwargs) -> Roadmap:
    """Helper to write a roadmap.yaml in the workspace."""
    if items is None:
        items = [
            RoadmapItem("ri-01", "First item", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem("ri-02", "Second item", ItemStatus.APPROVED, 2, Effort.M, depends_on=["ri-01"]),
            RoadmapItem("ri-03", "Third item", ItemStatus.APPROVED, 3, Effort.M, depends_on=["ri-02"]),
        ]
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id=kwargs.get("roadmap_id", "test-roadmap"),
        source_proposal="test-proposal.md",
        items=items,
        status=kwargs.get("status", RoadmapStatus.APPROVED),
        policy=kwargs.get("policy", Policy()),
    )
    roadmap_path = workspace / "roadmap.yaml"
    roadmap_path.write_text(yaml.dump(roadmap.to_dict(), default_flow_style=False, sort_keys=False))
    return roadmap


def _route_decision(agent_id: str = "codex-cloud", decision_id: str = "decision-1") -> dict:
    return {
        "decision_id": decision_id,
        "assignment": {
            "agent_id": agent_id,
            "vendor_type": "openai",
            "location": "cloud",
            "isolation": "sandbox",
            "dispatch_mode": "sdk",
            "model": "gpt-test",
            "endpoint_kind": "vendor-sdk",
        },
    }


def _routed_result(context: dict, *, status: str = "completed") -> dict:
    routing = context["routing"]
    outcome = "success" if status == "completed" else "vendor_limit:openai:capacity"
    return {
        "outcome": outcome,
        "routing_proof": {
            "routing_decision_id": routing["decision_id"],
            "dispatch_work_id": routing["dispatch_work_id"],
            "observed_agent_id": routing["assignment"]["agent_id"],
            "ledger_status": status,
        },
    }


class TestExecutionOrder:
    """Verify items execute in dependency and priority order."""

    def test_executes_items_in_dependency_order(self, tmp_path):
        _write_roadmap(tmp_path)
        executed: list[str] = []

        def track_dispatch(item_id, phase, context):
            if phase == "implementing":
                executed.append(item_id)
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=track_dispatch)

        assert executed == ["ri-01", "ri-02", "ri-03"]
        assert result["completed_count"] == 3
        assert result["status"] == "completed"

    def test_respects_priority_for_independent_items(self, tmp_path):
        items = [
            RoadmapItem("ri-a", "High priority", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem("ri-b", "Low priority", ItemStatus.APPROVED, 5, Effort.S),
            RoadmapItem("ri-c", "Mid priority", ItemStatus.APPROVED, 3, Effort.S),
        ]
        _write_roadmap(tmp_path, items=items)
        executed: list[str] = []

        def track_dispatch(item_id, phase, context):
            if phase == "implementing":
                executed.append(item_id)
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=track_dispatch)

        assert executed == ["ri-a", "ri-c", "ri-b"]
        assert result["completed_count"] == 3

class TestCheckpointLifecycle:
    """Verify checkpoint creation and phase advancement."""

    def test_creates_checkpoint_on_start(self, tmp_path):
        _write_roadmap(tmp_path)
        execute_roadmap(tmp_path)

        checkpoint_path = tmp_path / "checkpoint.json"
        assert checkpoint_path.exists()
        data = json.loads(checkpoint_path.read_text())
        assert data["roadmap_id"] == "test-roadmap"

    def test_advances_checkpoint_phases_correctly(self, tmp_path):
        _write_roadmap(tmp_path)
        phases_seen: dict[str, list[str]] = {}

        def track_phases(item_id, phase, context):
            phases_seen.setdefault(item_id, []).append(phase)
            return "success"

        execute_roadmap(tmp_path, dispatch_fn=track_phases)

        # Each item should go through planning, implementing, reviewing, validating
        for item_id in ("ri-01", "ri-02", "ri-03"):
            assert phases_seen[item_id] == [
                "planning", "implementing", "reviewing", "validating",
            ]

    def test_checkpoint_records_completed_items(self, tmp_path):
        _write_roadmap(tmp_path)
        execute_roadmap(tmp_path)

        data = json.loads((tmp_path / "checkpoint.json").read_text())
        assert "ri-01" in data["completed_items"]
        assert "ri-02" in data["completed_items"]
        assert "ri-03" in data["completed_items"]

class TestFailureHandling:
    """Verify failure and propagation behavior."""

    def test_handles_item_failure(self, tmp_path):
        _write_roadmap(tmp_path)

        def fail_first(item_id, phase, context):
            if item_id == "ri-01" and phase == "implementing":
                return "failed:Tests failed"
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=fail_first)

        assert result["failed_count"] == 1
        assert result["blocked_count"] >= 1  # ri-02 and ri-03 should be blocked

    def test_failure_propagates_to_dependents(self, tmp_path):
        _write_roadmap(tmp_path)

        def fail_first(item_id, phase, context):
            if item_id == "ri-01" and phase == "implementing":
                return "failed:Build error"
            return "success"

        _result = execute_roadmap(tmp_path, dispatch_fn=fail_first)

        # Read updated roadmap to check propagation
        roadmap_data = yaml.safe_load((tmp_path / "roadmap.yaml").read_text())
        statuses = {item["item_id"]: item["status"] for item in roadmap_data["items"]}
        assert statuses["ri-01"] == "failed"
        assert statuses["ri-02"] == "blocked"

    def test_continues_with_independent_items_after_failure(self, tmp_path):
        items = [
            RoadmapItem("ri-01", "Will fail", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem("ri-02", "Independent", ItemStatus.APPROVED, 2, Effort.S),
            RoadmapItem("ri-03", "Depends on ri-01", ItemStatus.APPROVED, 3, Effort.S, depends_on=["ri-01"]),
        ]
        _write_roadmap(tmp_path, items=items)
        executed: list[str] = []

        def selective_fail(item_id, phase, context):
            if item_id == "ri-01" and phase == "implementing":
                return "failed:Error"
            if phase == "implementing":
                executed.append(item_id)
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=selective_fail)

        assert "ri-02" in executed
        assert "ri-03" not in executed  # blocked by ri-01
        assert result["completed_count"] == 1
        assert result["failed_count"] == 1

class TestResumeFromCheckpoint:
    """Verify checkpoint resume semantics."""

    def test_resumes_from_existing_checkpoint(self, tmp_path):
        _write_roadmap(tmp_path)

        # First run: complete only ri-01, then "crash"
        call_count = {"n": 0}

        def crash_after_first(item_id, phase, context):
            if item_id == "ri-01":
                return "success"
            call_count["n"] += 1
            if call_count["n"] > 1:
                # Let it process a bit then we'll check resume
                return "success"
            return "success"

        # Complete first run
        first_result = execute_roadmap(tmp_path, dispatch_fn=crash_after_first)
        assert first_result["completed_count"] == 3

        # Re-run: should resume and find everything completed
        resumed: list[str] = []

        def track_resume(item_id, phase, context):
            resumed.append(item_id)
            return "success"

        second_result = execute_roadmap(tmp_path, dispatch_fn=track_resume)

        # All items already completed — nothing new to dispatch
        assert len(resumed) == 0
        assert second_result["completed_count"] == 3

    def test_skips_completed_items_on_resume(self, tmp_path):
        items = [
            RoadmapItem("ri-01", "First", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem("ri-02", "Second", ItemStatus.APPROVED, 2, Effort.S),
        ]
        _write_roadmap(tmp_path, items=items)

        # Write a checkpoint with ri-01 already completed
        checkpoint_data = {
            "schema_version": 1,
            "roadmap_id": "test-roadmap",
            "current_item_id": "ri-01",
            "phase": "completed",
            "created_at": "2026-01-01T00:00:00+00:00",
            "completed_items": ["ri-01"],
        }
        (tmp_path / "checkpoint.json").write_text(json.dumps(checkpoint_data))

        # Also update roadmap to reflect ri-01 is completed
        roadmap_data = yaml.safe_load((tmp_path / "roadmap.yaml").read_text())
        roadmap_data["items"][0]["status"] = "completed"
        (tmp_path / "roadmap.yaml").write_text(yaml.dump(roadmap_data, default_flow_style=False))

        executed: list[str] = []

        def track(item_id, phase, context):
            if phase == "implementing":
                executed.append(item_id)
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=track)

        assert "ri-01" not in executed
        assert "ri-02" in executed
        assert result["completed_count"] == 2

class TestSummary:
    """Verify the returned summary dict."""

    def test_returns_correct_summary(self, tmp_path):
        _write_roadmap(tmp_path)

        result = execute_roadmap(tmp_path)

        assert "completed_count" in result
        assert "failed_count" in result
        assert "blocked_count" in result
        assert "skipped_count" in result
        assert "status" in result
        assert "policy_decisions" in result
        assert isinstance(result["policy_decisions"], list)

    def test_all_completed_status(self, tmp_path):
        _write_roadmap(tmp_path)
        result = execute_roadmap(tmp_path)
        assert result["status"] == "completed"

    def test_blocked_all_status(self, tmp_path):
        items = [
            RoadmapItem("ri-01", "Will fail", ItemStatus.APPROVED, 1, Effort.S),
            RoadmapItem("ri-02", "Depends", ItemStatus.APPROVED, 2, Effort.S, depends_on=["ri-01"]),
        ]
        _write_roadmap(tmp_path, items=items)

        def always_fail(item_id, phase, context):
            if phase == "implementing":
                return "failed:Error"
            return "success"

        result = execute_roadmap(tmp_path, dispatch_fn=always_fail)

        assert result["status"] == "blocked_all"

class TestVendorLimitHandling:
    """Verify vendor limit events flow through the policy engine."""

    def test_vendor_limit_triggers_policy_decision(self, tmp_path):
        items = [RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)]
        _write_roadmap(
            tmp_path,
            items=items,
            policy=Policy(default_action=PolicyAction.SWITCH),
        )
        decisions: list = []

        call_count = {"n": 0}

        def limit_then_succeed(item_id, phase, context):
            call_count["n"] += 1
            if call_count["n"] == 2:  # implementing phase, first call
                return "vendor_limit:claude:rate limit hit"
            return "success"

        result = execute_roadmap(
            tmp_path,
            dispatch_fn=limit_then_succeed,
            on_policy_decision=lambda d: decisions.append(d),
            registry_provider=lambda **_: {
                "status": "ok",
                "response": {"vendors": [
                    _registry_lane("codex-cloud", "codex"),
                ]},
            },
        )

        assert len(decisions) == 1
        assert decisions[0].action == "switch"
        assert len(result["policy_decisions"]) == 1


def _registry_lane(agent_id: str, policy_vendor: str) -> dict:
    return {
        "agent_id": agent_id,
        "policy_vendor": policy_vendor,
        "location": "cloud",
        "capabilities": ["queue"],
        "archetypes": ["implementer"],
        "dispatch_modes": ["alternative"],
        "dispatchable": True,
        "availability": {"available": True, "status": "available", "rate_limits": []},
        "cost": {"known": False, "models": []},
    }


def test_wait_policy_persists_pause_and_does_not_retry_or_select_lane(
    tmp_path,
) -> None:
    reset_at = "2999-09-17T12:00:00+00:00"
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem(
            "ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S, capability="queue"
        )],
        policy=Policy(default_action=PolicyAction.WAIT),
    )
    dispatch_calls: list[tuple[str, dict]] = []
    registry_calls: list[dict] = []

    def dispatch(_item_id, phase, context):
        dispatch_calls.append((phase, dict(context)))
        if phase == "implementing":
            if sum(call_phase == "implementing" for call_phase, _ in dispatch_calls) > 1:
                raise AssertionError("WAIT policy retried the paused phase")
            return {
                "outcome": "vendor_limit:claude:capacity",
                "agent_id": "claude-local",
                "capacity_reset_at": reset_at,
                "capacity_report_status": "persisted",
            }
        return "success"

    def registry_provider(**filters):
        registry_calls.append(filters)
        return {
            "status": "ok",
            "response": {"vendors": [_registry_lane("codex-cloud", "codex")]},
        }

    result = execute_roadmap(
        tmp_path,
        dispatch_fn=dispatch,
        registry_provider=registry_provider,
    )

    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert result["status"] == "paused"
    assert checkpoint["phase"] == "implementing"
    assert checkpoint["pause_state"]["paused"] is True
    assert checkpoint["pause_state"]["blocked_vendor"] == "claude"
    assert checkpoint["pause_state"]["expected_resume_at"] == reset_at
    assert "capacity" in checkpoint["pause_state"]["reason"]
    assert [phase for phase, _ in dispatch_calls].count("implementing") == 1
    assert registry_calls == []
    decision = result["policy_decisions"][0]["decision"]
    assert decision["action"] == "wait"
    assert decision["to_agent_id"] is None

    resumed_dispatches: list[str] = []
    still_paused = execute_roadmap(
        tmp_path,
        dispatch_fn=lambda _item, phase, _context: (
            resumed_dispatches.append(phase) or "success"
        ),
        registry_provider=registry_provider,
    )
    assert still_paused["status"] == "paused"
    assert resumed_dispatches == []

    checkpoint["pause_state"]["expected_resume_at"] = "2000-01-01T00:00:00+00:00"
    (tmp_path / "checkpoint.json").write_text(json.dumps(checkpoint))
    resumed = execute_roadmap(
        tmp_path,
        dispatch_fn=lambda _item, phase, _context: (
            resumed_dispatches.append(phase) or "success"
        ),
        registry_provider=registry_provider,
    )
    assert resumed["status"] == "completed"
    assert resumed_dispatches[0] == "implementing"
    resumed_checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert resumed_checkpoint.get("pause_state") in (None, {})


def test_wait_pause_sanitizes_adapter_reason_only_at_persistence_boundary(
    tmp_path,
) -> None:
    vendor = "claude-api_key=lane-secret"
    secret_reason = (
        "capacity token=tok-secret "
        "raw_response=private upstream payload"
    )
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem(
            "ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S, capability="queue"
        )],
        policy=Policy(default_action=PolicyAction.WAIT),
    )

    def dispatch(_item_id, phase, _context):
        if phase == "implementing":
            return {
                "outcome": f"vendor_limit:{vendor}:{secret_reason}",
                "agent_id": "claude-local",
                "capacity_reset_at": "2999-09-17T12:00:00+00:00",
            }
        return "success"

    result = execute_roadmap(tmp_path, dispatch_fn=dispatch)
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    persisted = checkpoint["pause_state"]

    assert secret_reason in result["policy_decisions"][0]["decision"]["reason"]
    assert persisted["reason"].startswith("Waiting for")
    assert "[REDACTED:token]" in persisted["reason"]
    assert "[REDACTED:raw_response]" in persisted["reason"]
    assert "tok-secret" not in persisted["reason"]
    assert "private upstream payload" not in persisted["reason"]
    assert "[REDACTED:api_key]" in persisted["blocked_vendor"]
    assert "lane-secret" not in persisted["blocked_vendor"]


def test_vendor_limit_uses_registry_lanes_not_hardcoded_roster(tmp_path) -> None:
    roadmap = _write_roadmap(
        tmp_path,
        items=[RoadmapItem(
            "ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S, capability="queue"
        )],
        policy=Policy(default_action=PolicyAction.SWITCH),
    )
    calls: list[dict] = []

    def registry_provider(**filters):
        calls.append(filters)
        return {
            "status": "ok",
            "response": {
                "vendors": [
                    _registry_lane("codex-cloud", "codex"),
                    _registry_lane("custom-cloud", "custom"),
                ]
            },
        }

    decision = _handle_vendor_limit(
        roadmap,
        "ri-01",
        "claude",
        "capacity",
        {},
        registry_provider=registry_provider,
        phase="implementing",
    )

    assert decision.action == "switch"
    assert decision.to_agent_id in {"codex-cloud", "custom-cloud"}
    assert calls == [{
        "capability": "queue",
        "archetype": "implementer",
        "dispatch_mode": "alternative",
        "location": None,
        "available_only": False,
    }]


def test_registry_outage_fails_closed_without_explicit_fallback(tmp_path) -> None:
    roadmap = _write_roadmap(
        tmp_path,
        items=[RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)],
        policy=Policy(default_action=PolicyAction.SWITCH),
    )

    decision = _handle_vendor_limit(
        roadmap, "ri-01", "claude", "capacity", {},
        registry_provider=lambda **_: {"status": "error", "reason": "server_error"},
        phase="implementing",
    )

    assert decision.action == "fail_closed"
    assert "registry" in decision.reason.lower()


def test_explicit_agents_yaml_fallback_has_unknown_state_and_cost(tmp_path) -> None:
    roadmap = _write_roadmap(
        tmp_path,
        items=[RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)],
        policy=Policy(default_action=PolicyAction.SWITCH),
    )
    fallback_lane = _registry_lane("codex-cloud", "codex")
    fallback_lane["availability"] = {
        "available": False, "status": "unknown", "rate_limits": []
    }
    fallback_lane["cost"] = {"known": False, "models": []}

    decision = _handle_vendor_limit(
        roadmap, "ri-01", "claude", "capacity", {},
        registry_provider=lambda **_: {"status": "error", "reason": "timeout"},
        agents_yaml_fallback=lambda **_: [fallback_lane],
        phase="implementing",
    )

    assert decision.action == "switch"
    assert decision.to_agent_id == "codex-cloud"
    assert decision.expected_cost_delta_usd is None
    assert decision.cost_guard == "unavailable"


def test_legacy_provider_limit_excludes_all_provider_lanes_for_decision(tmp_path) -> None:
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem(
            "ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S, capability="queue"
        )],
        policy=Policy(default_action=PolicyAction.SWITCH),
    )
    calls = {"count": 0}

    def dispatch(_item_id, _phase, _context):
        calls["count"] += 1
        if calls["count"] == 2:
            return "vendor_limit:claude:capacity"
        return "success"

    result = execute_roadmap(
        tmp_path,
        dispatch_fn=dispatch,
        registry_provider=lambda **_: {
            "status": "ok",
            "response": {"vendors": [
                _registry_lane("claude-local", "claude"),
                _registry_lane("claude-remote", "claude"),
                _registry_lane("codex-cloud", "codex"),
            ]},
        },
    )

    decision = result["policy_decisions"][0]["decision"]
    assert decision["to_agent_id"] == "codex-cloud"
    assert decision["legacy_provider_scope"] is True
    assert decision["durable_persistence"] == "skipped_ambiguous"


def test_structured_limit_excludes_only_exact_lane(tmp_path) -> None:
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem(
            "ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S, capability="queue"
        )],
        policy=Policy(
            default_action=PolicyAction.SWITCH, preferred_vendor="claude"
        ),
    )
    calls = {"count": 0}

    def dispatch(_item_id, _phase, _context):
        calls["count"] += 1
        if calls["count"] == 2:
            return {
                "outcome": "vendor_limit:claude:capacity",
                "dispatch_agent_id": "claude-local",
            }
        return "success"

    result = execute_roadmap(
        tmp_path,
        dispatch_fn=dispatch,
        registry_provider=lambda **_: {
            "status": "ok",
            "response": {"vendors": [
                _registry_lane("claude-local", "claude"),
                _registry_lane("claude-remote", "claude"),
                _registry_lane("codex-cloud", "codex"),
            ]},
        },
    )

    decision = result["policy_decisions"][0]["decision"]
    assert decision["to_agent_id"] == "claude-remote"
    assert decision["legacy_provider_scope"] is False
    assert decision["durable_persistence"] == "delegated_unconfirmed"


def test_structured_limit_retries_same_phase_on_selected_lane(tmp_path) -> None:
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem(
            "ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S, capability="queue"
        )],
        policy=Policy(
            default_action=PolicyAction.SWITCH, preferred_vendor="claude"
        ),
    )
    calls: list[tuple[str, dict]] = []

    def dispatch(_item_id, phase, context):
        calls.append((phase, dict(context)))
        implementing_calls = [call for call in calls if call[0] == "implementing"]
        if phase == "implementing" and len(implementing_calls) == 1:
            return {
                "outcome": "vendor_limit:claude:capacity",
                # Provider/phase carriers use the additive agent_id field.
                "agent_id": "claude-local",
                "capacity_report_status": "persisted",
            }
        return "success"

    result = execute_roadmap(
        tmp_path,
        dispatch_fn=dispatch,
        registry_provider=lambda **_: {
            "status": "ok",
            "response": {"vendors": [
                _registry_lane("claude-local", "claude"),
                _registry_lane("claude-remote", "claude"),
            ]},
        },
    )

    implementing = [context for phase, context in calls if phase == "implementing"]
    assert len(implementing) == 2
    assert implementing[1]["dispatch_agent_id"] == "claude-remote"
    assert implementing[1]["agent_id"] == "claude-remote"
    assert result["completed_count"] == 1
    decision = result["policy_decisions"][0]["decision"]
    assert decision["legacy_provider_scope"] is False
    assert decision["durable_persistence"] == "persisted"


def test_unconfirmed_dispatch_reporting_is_not_claimed_as_persisted(tmp_path) -> None:
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)],
        policy=Policy(default_action=PolicyAction.SWITCH),
    )
    calls = {"implementing": 0}

    def dispatch(_item_id, phase, _context):
        if phase == "implementing":
            calls["implementing"] += 1
            if calls["implementing"] == 1:
                return {
                    "outcome": "vendor_limit:claude:capacity",
                    "agent_id": "claude-local",
                }
        return "success"

    result = execute_roadmap(
        tmp_path,
        dispatch_fn=dispatch,
        registry_provider=lambda **_: {
            "status": "ok",
            "response": {"vendors": [_registry_lane("codex-cloud", "codex")]},
        },
    )

    decision = result["policy_decisions"][0]["decision"]
    assert decision["durable_persistence"] == "delegated_unconfirmed"


def test_injected_routing_resolver_adds_validated_context_and_canonical_isolation_to_every_dispatch(
    tmp_path,
) -> None:
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)],
    )
    dispatched_contexts: list[tuple[str, dict]] = []
    persisted_attempts: list[dict] = []

    def resolve_route(_item, phase, _context):
        assignment = {
            "agent_id": "codex-cloud",
            "vendor_type": "openai",
            "policy_vendor": "codex",
            "catalog_vendor": "openai",
            "location": "cloud",
            "isolation": "sandbox",
            "dispatch_mode": "sdk",
            "model": "gpt-test",
            "endpoint_kind": "vendor-sdk",
        }
        return {
            "decision_id": f"00000000-0000-4000-8000-00000000000{len(phase)}",
            "selected": {
                "vendor": "openai",
                "model": "gpt-test",
                "endpoint_kind": "vendor-sdk",
                "score": 1.0,
                "assignment": assignment,
            },
            "alternatives": [],
            "assignment": assignment,
            "provenance": {
                "source": "coordinator",
                "policy_version": "linear-utility-v1",
                "policy_checksum": "a" * 64,
                "matched_rule_ids": [],
                "rationale": [],
                "persisted": True,
                "durable_audit": True,
                "catalog_key": ["openai", "gpt-test", "vendor-sdk", None],
            },
        }

    def dispatch(_item_id, phase, context):
        checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
        persisted = checkpoint["routing_attempts"][-1]
        assert persisted["status"] == "prepared"
        assert persisted["dispatch_work_id"] == context["routing"]["dispatch_work_id"]
        assert persisted["decision_id"] == context["routing"]["decision_id"]
        persisted_attempts.append(persisted)
        dispatched_contexts.append((phase, dict(context)))
        return {
            "outcome": "success",
            "routing_proof": {
                "routing_decision_id": context["routing"]["decision_id"],
                "dispatch_work_id": context["routing"]["dispatch_work_id"],
                "observed_agent_id": context["routing"]["assignment"]["agent_id"],
                "ledger_status": "completed",
            },
        }

    execute_roadmap(
        tmp_path,
        dispatch_fn=dispatch,
        routing_resolver=resolve_route,
    )

    assert [phase for phase, _ in dispatched_contexts] == [
        "planning", "implementing", "reviewing", "validating",
    ]
    for _phase, context in dispatched_contexts:
        assert context["routing"]["assignment"]["agent_id"] == "codex-cloud"
        assert context["routing"]["schema_version"] == 1
        assert context["routing"]["item_id"] == "ri-01"
        assert context["routing"]["phase"] == _phase
        assert context["routing"]["attempt"] == 1
        assert context["routing"]["dispatch_work_id"]
        assert context["routing"]["assignment"]["isolation"] == "sandbox"
        assert context["isolation"] == "sandbox"


    assert len(persisted_attempts) == 4
def test_none_routing_resolver_result_fails_closed_before_host_dispatch(tmp_path) -> None:
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)],
    )
    dispatched: list[tuple[str, str]] = []

    result = execute_roadmap(
        tmp_path,
        dispatch_fn=lambda item_id, phase, _context: (
            dispatched.append((item_id, phase)) or "success"
        ),
        routing_resolver=lambda _item, _phase, _context: None,
    )

    assert dispatched == []
    assert result["completed_count"] == 0
    assert result["failed_count"] == 1
    assert result["status"] == "blocked_all"



def test_routed_success_with_mismatched_ledger_proof_fails_closed(tmp_path) -> None:
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)],
    )

    def resolve_route(_item, _phase, _context):
        return {
            "decision_id": "decision-active",
            "assignment": {
                "agent_id": "codex-cloud",
                "vendor_type": "openai",
                "location": "cloud",
                "isolation": "sandbox",
                "dispatch_mode": "sdk",
                "model": "gpt-test",
                "endpoint_kind": "vendor-sdk",
            },
        }

    result = execute_roadmap(
        tmp_path,
        routing_resolver=resolve_route,
        dispatch_fn=lambda _item, _phase, context: {
            "outcome": "success",
            "routing_proof": {
                "routing_decision_id": "decision-stale",
                "dispatch_work_id": context["routing"]["dispatch_work_id"],
                "observed_agent_id": "codex-cloud",
                "ledger_status": "completed",
            },
        },
    )

    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert result["completed_count"] == 0
    assert result["failed_count"] == 1
    assert checkpoint["routing_attempts"][-1]["status"] == "failed"


def test_routed_vendor_limit_resolves_fresh_excluded_lane_on_same_phase(tmp_path) -> None:
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)],
    )
    resolver_calls: list[tuple[str, dict]] = []
    dispatch_calls: list[tuple[str, dict]] = []

    def resolve_route(_item, phase, context):
        resolver_calls.append((phase, dict(context)))
        excluded = context.get("routing_exclusions", {}).get("agent_ids", [])
        agent_id = "codex-alt" if "codex-primary" in excluded else "codex-primary"
        return {
            "decision_id": f"decision-{len(resolver_calls)}",
            "assignment": {
                "agent_id": agent_id,
                "vendor_type": "openai",
                "location": "cloud",
                "isolation": "sandbox",
                "dispatch_mode": "sdk",
                "model": "gpt-test",
                "endpoint_kind": "vendor-sdk",
            },
        }

    def dispatch(_item, phase, context):
        dispatch_calls.append((phase, dict(context)))
        routing = context["routing"]
        agent_id = routing["assignment"]["agent_id"]
        proof = {
            "routing_decision_id": routing["decision_id"],
            "dispatch_work_id": routing["dispatch_work_id"],
            "observed_agent_id": agent_id,
            "ledger_status": "completed",
        }
        if phase == "planning" and agent_id == "codex-primary":
            proof["ledger_status"] = "vendor_limit"
            return {"outcome": "vendor_limit:openai:capacity", "routing_proof": proof}
        return {"outcome": "success", "routing_proof": proof}

    result = execute_roadmap(
        tmp_path,
        routing_resolver=resolve_route,
        dispatch_fn=dispatch,
    )

    planning = [context for phase, context in dispatch_calls if phase == "planning"]
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert [context["routing"]["assignment"]["agent_id"] for context in planning] == [
        "codex-primary", "codex-alt",
    ]
    assert resolver_calls[1][1]["routing_exclusions"]["agent_ids"] == ["codex-primary"]
    assert [attempt["status"] for attempt in checkpoint["routing_attempts"][:2]] == [
        "vendor_limit", "completed",
    ]
    assert result["completed_count"] == 1



def test_routing_resume_parks_before_duplicate_when_ledger_is_unavailable(tmp_path) -> None:
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)],
    )

    with pytest.raises(RuntimeError, match="simulated crash"):
        execute_roadmap(
            tmp_path,
            routing_resolver=lambda *_: _route_decision(),
            dispatch_fn=lambda *_: (_ for _ in ()).throw(RuntimeError("simulated crash")),
        )

    dispatched: list[str] = []
    result = execute_roadmap(
        tmp_path,
        routing_resolver=lambda *_: _route_decision(decision_id="decision-new"),
        routing_reconciler=lambda _attempt: None,
        dispatch_fn=lambda _item, phase, _context: dispatched.append(phase) or "success",
    )

    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert dispatched == []
    assert len(checkpoint["routing_attempts"]) == 1
    assert checkpoint["execution_safety"]["escalation"]["kind"] == "ledger_reconciliation_required"
    assert result["status"] == "paused"


def test_global_iteration_cap_checkpoints_before_next_dispatch(tmp_path) -> None:
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)],
    )
    dispatched: list[str] = []

    def dispatch(_item, phase, context):
        dispatched.append(phase)
        return _routed_result(context)

    result = execute_roadmap(
        tmp_path,
        routing_resolver=lambda *_: _route_decision(),
        dispatch_fn=dispatch,
        max_iterations=1,
    )

    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert dispatched == ["planning"]
    assert checkpoint["execution_safety"]["iteration_count"] == 1
    assert checkpoint["execution_safety"]["escalation"]["kind"] == "iteration_cap"
    assert result["status"] == "paused"



def test_no_progress_cap_checkpoints_before_repeating_same_phase(tmp_path) -> None:
    _write_roadmap(
        tmp_path,
        items=[
            RoadmapItem(
                "ri-01",
                "Item",
                ItemStatus.APPROVED,
                1,
                Effort.S,
                capability="queue",
            )
        ],
        policy=Policy(default_action=PolicyAction.SWITCH, preferred_vendor="codex"),
    )
    dispatched: list[str] = []

    result = execute_roadmap(
        tmp_path,
        dispatch_fn=lambda _item, phase, _context: (
            dispatched.append(phase)
            or ("success" if phase == "planning" else {
                "outcome": "vendor_limit:codex:capacity",
                "agent_id": "codex-primary",
            })
        ),
        registry_provider=lambda **_: {
            "status": "ok",
            "response": {
                "vendors": [
                    _registry_lane("codex-primary", "codex"),
                    _registry_lane("codex-alt", "codex"),
                ]
            },
        },
        max_no_progress=1,
    )

    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert dispatched == ["planning", "implementing"]
    assert checkpoint["execution_safety"]["consecutive_no_progress"] == 1
    assert checkpoint["execution_safety"]["escalation"]["kind"] == "no_progress_cap"
    assert result["status"] == "paused"



@pytest.mark.parametrize(
    "field,value",
    [
        ("agent_id", ""),
        ("vendor_type", None),
        ("location", 7),
        ("dispatch_mode", ""),
        ("model", None),
        ("endpoint_kind", []),
    ],
)
def test_invalid_routing_assignment_field_fails_before_dispatch(
    tmp_path, field, value
) -> None:
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)],
    )
    decision = _route_decision()
    decision["assignment"][field] = value
    dispatched: list[str] = []

    result = execute_roadmap(
        tmp_path,
        routing_resolver=lambda *_: decision,
        dispatch_fn=lambda _item, phase, _context: dispatched.append(phase) or "success",
    )

    assert dispatched == []
    assert result["failed_count"] == 1


def test_routing_resume_parks_when_ledger_reconciler_raises(tmp_path) -> None:
    _write_roadmap(
        tmp_path,
        items=[RoadmapItem("ri-01", "Item", ItemStatus.APPROVED, 1, Effort.S)],
    )
    with pytest.raises(RuntimeError, match="simulated crash"):
        execute_roadmap(
            tmp_path,
            routing_resolver=lambda *_: _route_decision(),
            dispatch_fn=lambda *_: (_ for _ in ()).throw(RuntimeError("simulated crash")),
        )

    result = execute_roadmap(
        tmp_path,
        routing_resolver=lambda *_: _route_decision(decision_id="decision-new"),
        routing_reconciler=lambda _attempt: (_ for _ in ()).throw(
            RuntimeError("ledger unavailable")
        ),
        dispatch_fn=lambda *_: pytest.fail("must not duplicate dispatch"),
    )

    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert checkpoint["execution_safety"]["escalation"]["kind"] == "ledger_reconciliation_required"
    assert result["status"] == "paused"
