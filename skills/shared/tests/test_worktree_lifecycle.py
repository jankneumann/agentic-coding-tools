from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from shared import worktree_lifecycle as lifecycle


NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def _v1_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "change_id": "change",
        "agent_id": None,
        "branch": "openspec/change",
        "worktree_path": "/repo/.git-worktrees/change",
        "created_at": "2026-08-16T11:00:00+00:00",
        "last_heartbeat": "2026-08-16T11:30:00+00:00",
        "pinned": True,
    }
    entry.update(overrides)
    return entry


def _v2_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "change_id": "change",
        "agent_id": None,
        "branch": "openspec/change",
        "worktree_path": "/repo/.git-worktrees/change",
        "created_at": NOW.isoformat(),
        "entry_generation": "generation-1",
        "setup_id": None,
        "durability_target": None,
        "retained": False,
        "retention_reason": None,
        "recovery_required": False,
        "recovery_reason": None,
        "recovery_context": None,
        "activity_lease": None,
    }
    entry.update(overrides)
    return entry


def test_v1_normalization_separates_pin_from_live_activity() -> None:
    normalized = lifecycle.normalize_registry({"version": 1, "entries": [_v1_entry()]}, now=NOW)

    entry = normalized["entries"][0]
    assert entry["retained"] is True
    assert entry["retention_reason"] == "legacy-pin"
    assert entry["entry_generation"].startswith("legacy-v1-entry:")
    assert entry["activity_lease"] == {
        "owner": "legacy:change:parent",
        "lease_id": lifecycle.legacy_lease_id(_v1_entry()),
        "controller_instance_id": None,
        "session_id": None,
        "phase": "LEGACY",
        "reason": "legacy-heartbeat-migration",
        "lifecycle_mode": "manual",
        "acquired_at": "2026-08-16T11:00:00+00:00",
        "last_heartbeat": "2026-08-16T11:30:00+00:00",
        "expires_at": "2026-08-16T12:30:00+00:00",
        "ttl_seconds": 3600,
    }


def test_invalid_legacy_heartbeat_is_idle_and_diagnosable() -> None:
    normalized = lifecycle.normalize_registry(
        {"version": 1, "entries": [_v1_entry(last_heartbeat="bad")]}, now=NOW
    )
    entry = normalized["entries"][0]
    assert entry["activity_lease"] is None
    assert entry["extensions"]["legacy_last_heartbeat"] == "bad"


def test_process_evidence_key_is_generation_and_entry_scoped() -> None:
    first = lifecycle.process_evidence_key("a", None, "g1", "same-lease")
    second = lifecycle.process_evidence_key("b", None, "g1", "same-lease")
    third = lifecycle.process_evidence_key("a", None, "g2", "same-lease")
    assert len(first) == 64
    assert len({first, second, third}) == 3


def test_lease_mutations_require_the_exact_controller_fence(tmp_path: Path) -> None:
    lifecycle.write_registry(
        tmp_path,
        lifecycle.empty_registry(entries=[_v2_entry()]),
    )
    acquired = lifecycle.acquire_lease(
        tmp_path,
        "change",
        None,
        owner="owner",
        lease_id="lease",
        controller_instance_id="controller-a",
        phase="IMPLEMENT",
        reason="test",
        mode="standalone",
        now=NOW,
        allow_unleased=True,
    )
    assert acquired["activity_lease"]["controller_instance_id"] == "controller-a"

    with pytest.raises(lifecycle.FenceConflict):
        lifecycle.renew_lease(
            tmp_path,
            "change",
            None,
            owner="owner",
            lease_id="lease",
            controller_instance_id="controller-b",
            now=NOW + timedelta(minutes=1),
        )

    unchanged = lifecycle.read_registry(tmp_path)["entries"][0]
    assert unchanged["activity_lease"]["last_heartbeat"] == NOW.isoformat()


def test_release_is_exact_and_absent_release_is_idempotent(tmp_path: Path) -> None:
    lease = lifecycle.new_lease(
        owner="owner",
        lease_id="lease",
        controller_instance_id="controller",
        session_id=None,
        phase="PLAN",
        reason="test",
        mode="standalone",
        ttl_seconds=1800,
        now=NOW,
    )
    lifecycle.write_registry(
        tmp_path,
        lifecycle.empty_registry(entries=[_v2_entry(activity_lease=lease)]),
    )
    with pytest.raises(lifecycle.OwnerConflict):
        lifecycle.release_lease(
            tmp_path,
            "change",
            None,
            owner="wrong",
            lease_id="lease",
            controller_instance_id="controller",
            now=NOW,
        )
    lifecycle.release_lease(
        tmp_path,
        "change",
        None,
        owner="owner",
        lease_id="lease",
        controller_instance_id="controller",
        now=NOW,
        checkout_present=False,
    )
    result = lifecycle.release_lease(
        tmp_path,
        "change",
        None,
        owner="anything",
        lease_id="anything",
        controller_instance_id="anything",
        now=NOW,
        checkout_present=False,
    )
    assert result["released"] is False


def test_corrupt_registry_is_never_rewritten_by_mutation(tmp_path: Path) -> None:
    path = lifecycle.registry_path(tmp_path)
    path.parent.mkdir(parents=True)
    original = b"{broken"
    path.write_bytes(original)
    with pytest.raises(lifecycle.RegistryCorrupt):
        lifecycle.set_retention(tmp_path, "change", None, reason="keep")
    assert path.read_bytes() == original


def test_atomic_mutations_preserve_updates_from_distinct_entries(tmp_path: Path) -> None:
    lifecycle.write_registry(
        tmp_path,
        lifecycle.empty_registry(
            entries=[
                _v2_entry(change_id="a", entry_generation="ga"),
                _v2_entry(change_id="b", entry_generation="gb"),
            ]
        ),
    )
    lifecycle.set_retention(tmp_path, "a", None, reason="one")
    lifecycle.set_retention(tmp_path, "b", None, reason="two")
    entries = {entry["change_id"]: entry for entry in lifecycle.read_registry(tmp_path)["entries"]}
    assert entries["a"]["retention_reason"] == "one"
    assert entries["b"]["retention_reason"] == "two"


def test_setup_reservation_has_fixed_expiry_and_does_not_grant_activity(tmp_path: Path) -> None:
    lifecycle.write_registry(tmp_path, lifecycle.empty_registry())
    reservation = lifecycle.reserve_setup(
        tmp_path,
        setup_id="setup-1",
        change_id="change",
        agent_id=None,
        branch="openspec/change",
        worktree_path="/repo/.git-worktrees/change",
        entry_generation="generation-1",
        durability_target={
            "remote_name": "origin",
            "remote_url_hash_algorithm": "git-remote-url-v1",
            "canonical_remote_url_sha256": "a" * 64,
            "ref_name": "refs/remotes/origin/openspec/change",
        },
        lease_intent={
            "owner": "owner",
            "lease_id": "lease",
            "controller_instance_id": "controller",
            "session_id": None,
            "phase": "IMPLEMENT",
            "reason": "test",
            "lifecycle_mode": "standalone",
            "ttl_seconds": 1800,
        },
        now=NOW,
        ttl_seconds=1800,
    )
    assert reservation["expires_at"] == (NOW + timedelta(minutes=30)).isoformat()
    assert lifecycle.read_registry(tmp_path)["entries"] == []


def test_completed_setup_exact_replay_does_not_renew(tmp_path: Path) -> None:
    lease = lifecycle.new_lease(
        owner="owner",
        lease_id="lease",
        controller_instance_id="controller",
        session_id=None,
        phase="IMPLEMENT",
        reason="test",
        mode="standalone",
        ttl_seconds=1800,
        now=NOW,
    )
    entry = _v2_entry(setup_id="setup-1", activity_lease=lease)
    lifecycle.write_registry(tmp_path, lifecycle.empty_registry(entries=[entry]))
    replay = lifecycle.completed_setup_replay(
        tmp_path,
        setup_id="setup-1",
        change_id="change",
        agent_id=None,
        entry_generation="generation-1",
        durability_target=None,
        owner="owner",
        lease_id="lease",
        controller_instance_id="controller",
    )
    assert replay["activity_lease"]["expires_at"] == lease["expires_at"]


def test_registry_json_is_schema_v2_after_first_mutation(tmp_path: Path) -> None:
    path = lifecycle.registry_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "entries": [_v1_entry()]}))
    lifecycle.clear_retention(tmp_path, "change", None)
    assert json.loads(path.read_text())["schema_version"] == 2


def test_exact_setup_retry_preserves_original_fixed_timing(tmp_path: Path) -> None:
    lifecycle.write_registry(tmp_path, lifecycle.empty_registry())
    target = {
        "remote_name": "origin",
        "remote_url_hash_algorithm": "git-remote-url-v1",
        "canonical_remote_url_sha256": "a" * 64,
        "ref_name": "refs/remotes/origin/openspec/change",
    }
    intent = {
        "owner": "owner",
        "lease_id": "lease",
        "controller_instance_id": "controller",
        "session_id": None,
        "phase": "IMPLEMENT",
        "reason": "test",
        "lifecycle_mode": "standalone",
        "ttl_seconds": 1800,
    }
    first = lifecycle.reserve_setup(
        tmp_path,
        setup_id="setup",
        change_id="change",
        agent_id=None,
        branch="openspec/change",
        worktree_path="/x/change",
        entry_generation="generation",
        durability_target=target,
        lease_intent=intent,
        now=NOW,
    )
    retry = lifecycle.reserve_setup(
        tmp_path,
        setup_id="setup",
        change_id="change",
        agent_id=None,
        branch="openspec/change",
        worktree_path="/x/change",
        entry_generation="generation",
        durability_target=target,
        lease_intent=intent,
        now=NOW + timedelta(minutes=5),
    )
    assert retry["created_at"] == first["created_at"]
    assert retry["expires_at"] == first["expires_at"]


def test_unleased_acquire_quarantines_before_refusing(tmp_path: Path) -> None:
    lifecycle.write_registry(
        tmp_path,
        lifecycle.empty_registry(entries=[_v2_entry()]),
    )
    with pytest.raises(lifecycle.RecoveryRequired):
        lifecycle.acquire_lease(
            tmp_path,
            "change",
            None,
            owner="owner",
            lease_id="lease",
            controller_instance_id="controller",
            phase="IMPLEMENT",
            reason="test",
            now=NOW,
        )
    entry = lifecycle.read_registry(tmp_path)["entries"][0]
    assert entry["activity_lease"] is None
    assert entry["recovery_required"] is True
    assert entry["recovery_context"]["source"] == "legacy-adoption"


def test_evidence_files_do_not_collide_when_entries_share_lease_id(tmp_path: Path) -> None:
    key_a, _ = lifecycle.write_process_evidence(
        tmp_path,
        change_id="a",
        agent_id=None,
        entry_generation="ga",
        lease_id="same",
        owner="owner-a",
        controller_instance_id="controller-a",
        process_start_token="token-a",
        pid=123,
    )
    key_b, _ = lifecycle.write_process_evidence(
        tmp_path,
        change_id="b",
        agent_id=None,
        entry_generation="gb",
        lease_id="same",
        owner="owner-b",
        controller_instance_id="controller-b",
        process_start_token="token-b",
        pid=456,
    )
    assert key_a != key_b
    assert len(list(lifecycle.evidence_directory(tmp_path).glob("*.json"))) == 2


def test_remote_url_canonicalization_strips_only_credentials() -> None:
    assert (
        lifecycle.canonicalize_remote_url("https://user:secret@Example.test:443/A%2Fb/repo.git/")
        == "https://Example.test:443/A%2Fb/repo.git/"
    )
    assert (
        lifecycle.canonicalize_remote_url("git@example.test:Org/Repo.git")
        == "example.test:Org/Repo.git"
    )


def test_competing_setup_id_cannot_claim_same_identity(tmp_path: Path) -> None:
    lifecycle.write_registry(tmp_path, lifecycle.empty_registry())
    target = {
        "remote_name": "origin",
        "remote_url_hash_algorithm": "git-remote-url-v1",
        "canonical_remote_url_sha256": "a" * 64,
        "ref_name": "refs/remotes/origin/x",
    }
    intent = {
        "owner": "o",
        "lease_id": "l",
        "controller_instance_id": "c",
        "session_id": None,
        "phase": "P",
        "reason": "r",
        "lifecycle_mode": "standalone",
        "ttl_seconds": 1800,
    }
    lifecycle.reserve_setup(
        tmp_path,
        setup_id="one",
        change_id="x",
        agent_id=None,
        branch="b",
        worktree_path="/x",
        entry_generation="g1",
        durability_target=target,
        lease_intent=intent,
        now=NOW,
    )
    with pytest.raises(lifecycle.FenceConflict):
        lifecycle.reserve_setup(
            tmp_path,
            setup_id="two",
            change_id="x",
            agent_id=None,
            branch="b",
            worktree_path="/x",
            entry_generation="g2",
            durability_target=target,
            lease_intent={**intent, "lease_id": "l2"},
            now=NOW,
        )


def test_writer_rejects_unknown_fields_and_invalid_targets(tmp_path: Path) -> None:
    with pytest.raises(lifecycle.RegistryCorrupt):
        lifecycle.write_registry(
            tmp_path, lifecycle.empty_registry(entries=[_v2_entry(extra="no")])
        )
    lease = lifecycle.new_lease(
        owner="o",
        lease_id="l",
        controller_instance_id="c",
        session_id=None,
        phase="P",
        reason="r",
        mode="standalone",
        now=NOW,
    )
    lease["lifecycle_mode"] = "bogus"
    with pytest.raises(lifecycle.RegistryCorrupt):
        lifecycle.write_registry(
            tmp_path, lifecycle.empty_registry(entries=[_v2_entry(activity_lease=lease)])
        )
    malformed = lifecycle.empty_registry()
    malformed["recovery_audit"] = [
        {
            "event_id": "e",
            "event": "force-adopted",
            "recorded_at": NOW.isoformat(),
            "termination_confirmed": True,
        }
    ]
    with pytest.raises(lifecycle.RegistryCorrupt):
        lifecycle.write_registry(tmp_path, malformed)
    with pytest.raises(lifecycle.RegistryCorrupt):
        lifecycle.write_registry(
            tmp_path,
            lifecycle.empty_registry(
                entries=[_v2_entry(durability_target={"remote_name": "origin"})]
            ),
        )


def test_bulk_release_ignores_checkout_already_removed(tmp_path: Path) -> None:
    lease = lifecycle.new_lease(
        owner="o",
        lease_id="l",
        controller_instance_id="c",
        session_id="s",
        phase="P",
        reason="r",
        mode="standalone",
        now=NOW,
    )
    lifecycle.write_registry(
        tmp_path,
        lifecycle.empty_registry(
            entries=[_v2_entry(worktree_path=str(tmp_path / "missing"), activity_lease=lease)]
        ),
    )
    assert lifecycle.release_matching(tmp_path, session_id="s", now=NOW) == []
    assert lifecycle.read_registry(tmp_path)["entries"][0]["activity_lease"] == lease
