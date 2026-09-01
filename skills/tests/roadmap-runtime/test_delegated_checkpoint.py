"""TDD coverage for the additive delegated-dispatch checkpoint ledger."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from checkpoint import CheckpointManager
from models import Checkpoint


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CANONICAL_SCHEMA = _REPO_ROOT / "openspec" / "schemas" / "checkpoint.schema.json"
_INSTALLED_SCHEMA = (
    _REPO_ROOT
    / "skills"
    / "roadmap-runtime"
    / "install_assets"
    / "openspec"
    / "schemas"
    / "checkpoint.schema.json"
)


def _legacy_checkpoint() -> dict:
    return {
        "schema_version": 1,
        "roadmap_id": "roadmap-alpha",
        "current_item_id": "ri-03",
        "phase": "implementing",
        "created_at": "2026-09-01T00:00:00Z",
    }


def _prepared_attempt() -> dict:
    return {
        "dispatch_id": "roadmap-alpha:ri-03:attempt-1",
        "item_id": "ri-03",
        "change_id": "add-alpha-capability",
        "phase": "autopilot",
        "attempt": 1,
        "status": "prepared",
        "prepared_at": "2026-09-01T00:01:00Z",
        "launch_token": "launch-token-0001",
        "launch_marker_path": ".git/autopilot/roadmap-alpha-ri-03.marker",
        "lease_generation": 1,
        "launch_history": [],
        "scope": {
            "proof": "proven_disjoint",
            "write_allow": ["skills/alpha/**"],
            "lock_keys": ["feature:add-alpha-capability"],
        },
        "isolation": {
            "mode": "managed_worktree",
            "worktree_path": "/workspace/.git-worktrees/add-alpha-capability",
            "branch": "openspec/add-alpha-capability",
        },
        "context": {"router_vendor": "example-vendor"},
    }


def _launched_attempt() -> dict:
    attempt = _prepared_attempt()
    attempt.update(
        status="launched",
        lease={
            "generation": 1,
            "owner_nonce": "owner-nonce-0001",
            "state": "active",
            "acquired_at": "2026-09-01T00:02:00Z",
            "heartbeat_at": "2026-09-01T00:03:00Z",
            "expires_at": "2026-09-01T00:08:00Z",
        },
        launch_evidence={
            "kind": "host_ack",
            "generation": 1,
            "handle": "task-alpha-1",
            "observed_at": "2026-09-01T00:02:30Z",
        },
        launch_gate={
            "generation": 1,
            "state": "entered",
            "handle": "task-alpha-1",
            "go_released_at": "2026-09-01T00:02:30Z",
            "entered_at": "2026-09-01T00:03:00Z",
        },
        launch_history=[
            {
                "generation": 1,
                "owner_nonce": "owner-nonce-0001",
                "state": "entered",
                "marker_path": ".git/autopilot/roadmap-alpha-ri-03.marker",
                "handle": "task-alpha-1",
                "observed_at": "2026-09-01T00:03:00Z",
            }
        ],
    )
    return attempt


def test_legacy_checkpoint_loads_with_an_empty_additive_attempt_ledger() -> None:
    checkpoint = Checkpoint.from_dict(_legacy_checkpoint())

    assert checkpoint.dispatch_attempts == []
    assert checkpoint.to_dict() == _legacy_checkpoint()


def test_checkpoint_round_trips_exact_unresolved_attempt_state() -> None:
    attempt = _launched_attempt()
    checkpoint = Checkpoint.from_dict({**_legacy_checkpoint(), "dispatch_attempts": [attempt]})

    serialized = checkpoint.to_dict()
    restored = Checkpoint.from_dict(serialized)

    assert serialized["dispatch_attempts"] == [attempt]
    assert restored.dispatch_attempts == [attempt]


def test_checkpoint_manager_persists_attempt_before_reload(tmp_path: Path) -> None:
    manager = CheckpointManager(tmp_path)
    checkpoint = Checkpoint.from_dict(_legacy_checkpoint())
    attempt = _prepared_attempt()

    manager.record_dispatch_attempt(checkpoint, attempt)

    assert json.loads(manager.checkpoint_path.read_text())["dispatch_attempts"] == [attempt]
    assert manager.load().dispatch_attempts == [attempt]


def test_checkpoint_manager_rejects_duplicate_dispatch_identity(tmp_path: Path) -> None:
    manager = CheckpointManager(tmp_path)
    checkpoint = Checkpoint.from_dict(_legacy_checkpoint())
    attempt = _prepared_attempt()
    manager.record_dispatch_attempt(checkpoint, attempt)

    with pytest.raises(ValueError, match="duplicate dispatch attempt"):
        manager.record_dispatch_attempt(checkpoint, copy.deepcopy(attempt))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        pytest.param(
            lambda attempt: attempt.update(
                status="claimed",
                lease={"generation": 1, "state": "active"},
            ),
            "claimed",
            id="claimed-requires-pre-ack-gate-and-marker",
        ),
        pytest.param(
            lambda attempt: attempt.update(
                status="acknowledged",
                lease={"generation": 1, "state": "active"},
                launch_evidence={"kind": "host_ack", "generation": 1},
                launch_gate={"generation": 1, "state": "waiting_ack"},
            ),
            "acknowledged",
            id="acknowledged-requires-go-release",
        ),
        pytest.param(
            lambda attempt: attempt.update(lease_generation=2),
            "generation",
            id="launched-requires-generation-match",
        ),
        pytest.param(
            lambda attempt: attempt.update(
                status="quarantined",
                quarantine={
                    "kind": "unknown_liveness",
                    "reason": "unknown",
                    "observed_at": "2026-09-01T00:09:00Z",
                },
                lease={**attempt["lease"], "state": "released"},
            ),
            "quarantined",
            id="quarantine-retains-uncertain-lease",
        ),
        pytest.param(
            lambda attempt: attempt.update(
                status="parked",
                outcome="parked",
                resolved_at="2026-09-01T00:09:00Z",
                parked={"kind": "pending_gate", "reason": "approval required"},
                lease={**attempt["lease"], "state": "uncertain"},
            ),
            "parked",
            id="parked-releases-lease",
        ),
        pytest.param(
            lambda attempt: attempt.update(launch_history=[{}] * 65),
            "launch_history",
            id="launch-history-is-bounded",
        ),
    ],
)
def test_checkpoint_rejects_attempt_state_contradictions(mutate, message: str) -> None:
    attempt = _launched_attempt()
    mutate(attempt)

    with pytest.raises(ValueError, match=message):
        Checkpoint.from_dict({**_legacy_checkpoint(), "dispatch_attempts": [attempt]})


def test_checkpoint_schemas_publish_the_optional_attempt_ledger() -> None:
    canonical = json.loads(_CANONICAL_SCHEMA.read_text())
    installed = json.loads(_INSTALLED_SCHEMA.read_text())

    assert installed == canonical
    assert "dispatch_attempts" not in canonical["required"]
    assert canonical["properties"]["dispatch_attempts"] == {
        "type": "array",
        "items": {"type": "object"},
        "default": [],
    }
    Draft202012Validator.check_schema(canonical)
    Draft202012Validator(canonical).validate(_legacy_checkpoint())
