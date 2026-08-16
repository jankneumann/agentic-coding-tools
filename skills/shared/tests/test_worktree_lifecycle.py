from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

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


def test_process_start_token_converts_permission_failure_to_lifecycle_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "is_file", lambda _path: False)

    def prohibited(*_args: object, **_kwargs: object) -> object:
        raise PermissionError("ps prohibited")

    monkeypatch.setattr(lifecycle.subprocess, "run", prohibited)
    with pytest.raises(lifecycle.LifecycleError, match="process start token unsupported"):
        lifecycle._process_start_token(123)


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


def _systematic_schema_documents() -> list[tuple[str, dict[str, object]]]:
    target = {
        "remote_name": "origin",
        "remote_url_hash_algorithm": "git-remote-url-v1",
        "canonical_remote_url_sha256": "a" * 64,
        "ref_name": "refs/remotes/origin/openspec/change",
    }
    lease = lifecycle.new_lease(
        owner="owner",
        lease_id="lease",
        controller_instance_id="controller",
        session_id="session",
        phase="IMPLEMENT",
        reason="test",
        mode="standalone",
        now=NOW,
    )
    recovery_context = {
        "source": "expired-takeover",
        "prior_owner": "old-owner",
        "prior_lease_id": "old-lease",
        "prior_controller_instance_id": "old-controller",
        "process_evidence_key": "b" * 64,
        "quarantined_at": NOW.isoformat(),
    }
    reservation = {
        "setup_id": "setup",
        "change_id": "reserved-change",
        "agent_id": "reserved-agent",
        "branch": "openspec/reserved-change--reserved-agent",
        "worktree_path": "/repo/.git-worktrees/reserved-change--reserved-agent",
        "entry_generation": "reserved-generation",
        "durability_target": target,
        "lease_intent": {
            "owner": "setup-owner",
            "lease_id": "setup-lease",
            "controller_instance_id": "setup-controller",
            "session_id": "setup-session",
            "phase": "IMPLEMENT",
            "reason": "setup",
            "lifecycle_mode": "continuous",
            "ttl_seconds": 1800,
        },
        "state": "reserved",
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        "ttl_seconds": 1800,
        "expires_at": (NOW + timedelta(seconds=1800)).isoformat(),
    }
    audits = [
        {
            "event_id": "force-event",
            "event": "force-adopted",
            "recorded_at": NOW.isoformat(),
            "change_id": "change",
            "agent_id": None,
            "entry_generation": "generation-1",
            "actor": "operator",
            "rationale": "terminated",
            "prior_owner": None,
            "prior_lease_id": None,
            "prior_controller_instance_id": None,
            "new_owner": "owner",
            "new_lease_id": "lease",
            "new_controller_instance_id": "controller",
            "process_evidence_key": None,
            "established_durability_target": None,
            "termination_confirmed": True,
        },
        {
            "event_id": "setup-event",
            "event": "setup-reconciled",
            "recorded_at": NOW.isoformat(),
            "setup_id": "prior-setup",
            "change_id": "prior-change",
            "agent_id": "prior-agent",
            "entry_generation": "prior-generation",
            "actor": "operator",
            "rationale": "terminated",
            "prior_owner": "prior-owner",
            "prior_lease_id": "prior-lease",
            "prior_controller_instance_id": "prior-controller",
            "process_evidence_key": "c" * 64,
            "termination_confirmed": True,
            "outcome": "quarantined-entry",
        },
        {
            "event_id": "teardown-event",
            "event": "recovery-torn-down",
            "recorded_at": NOW.isoformat(),
            "change_id": "removed-change",
            "agent_id": None,
            "entry_generation": "removed-generation",
            "actor": "operator",
            "rationale": "safe removal",
            "prior_owner": None,
            "prior_lease_id": None,
            "prior_controller_instance_id": None,
            "process_evidence_key": None,
            "termination_confirmed": True,
            "discard_confirmed": False,
            "outcome": "removed-clean-durable",
        },
    ]
    valid: dict[str, object] = lifecycle.empty_registry(
        entries=[
            _v2_entry(
                durability_target=target,
                last_heartbeat=NOW.isoformat(),
                activity_lease=lease,
                extensions={"preserved": [1, True, None]},
            ),
            _v2_entry(
                change_id="recovery-change",
                agent_id="recovery-agent",
                branch="openspec/recovery-change--recovery-agent",
                worktree_path="/repo/.git-worktrees/recovery-change--recovery-agent",
                entry_generation="generation-2",
                recovery_required=True,
                recovery_reason="preserved state",
                recovery_context=recovery_context,
            ),
        ]
    )
    valid["setup_reservations"] = [reservation]
    valid["recovery_audit"] = audits
    valid["extensions"] = {"preserved": [1, True, None]}
    cases = [("valid-v2", valid)]

    def changed(name: str, path: tuple[object, ...], value: object) -> None:
        document = copy.deepcopy(valid)
        target_object: object = document
        for part in path[:-1]:
            target_object = target_object[part]  # type: ignore[index]
        target_object[path[-1]] = value  # type: ignore[index]
        cases.append((name, document))

    def missing(name: str, path: tuple[object, ...]) -> None:
        document = copy.deepcopy(valid)
        target_object: object = document
        for part in path[:-1]:
            target_object = target_object[part]  # type: ignore[index]
        del target_object[path[-1]]  # type: ignore[index]
        cases.append((name, document))

    # Every required list in registryV2 and its nested object definitions.
    required_objects = [
        ("registry", (), ("schema_version", "entries", "setup_reservations", "recovery_audit")),
        (
            "entry",
            ("entries", 0),
            (
                "change_id",
                "agent_id",
                "branch",
                "worktree_path",
                "created_at",
                "entry_generation",
                "setup_id",
                "durability_target",
                "retained",
                "retention_reason",
                "recovery_required",
                "recovery_reason",
                "recovery_context",
                "activity_lease",
            ),
        ),
        (
            "lease",
            ("entries", 0, "activity_lease"),
            (
                "owner",
                "lease_id",
                "controller_instance_id",
                "session_id",
                "phase",
                "reason",
                "lifecycle_mode",
                "acquired_at",
                "last_heartbeat",
                "expires_at",
                "ttl_seconds",
            ),
        ),
        (
            "recovery-context",
            ("entries", 1, "recovery_context"),
            (
                "source",
                "prior_owner",
                "prior_lease_id",
                "prior_controller_instance_id",
                "process_evidence_key",
                "quarantined_at",
            ),
        ),
        (
            "reservation",
            ("setup_reservations", 0),
            (
                "setup_id",
                "change_id",
                "agent_id",
                "branch",
                "worktree_path",
                "entry_generation",
                "durability_target",
                "lease_intent",
                "state",
                "created_at",
                "updated_at",
                "ttl_seconds",
                "expires_at",
            ),
        ),
        (
            "lease-intent",
            ("setup_reservations", 0, "lease_intent"),
            (
                "owner",
                "lease_id",
                "controller_instance_id",
                "session_id",
                "phase",
                "reason",
                "lifecycle_mode",
                "ttl_seconds",
            ),
        ),
        (
            "durability-target",
            ("setup_reservations", 0, "durability_target"),
            (
                "remote_name",
                "remote_url_hash_algorithm",
                "canonical_remote_url_sha256",
                "ref_name",
            ),
        ),
    ]
    audit_required = (
        tuple(audits[0]),
        tuple(audits[1]),
        tuple(audits[2]),
    )
    for index, fields in enumerate(audit_required):
        required_objects.append((f"audit-{index}", ("recovery_audit", index), fields))
    for object_name, path, fields in required_objects:
        for field in fields:
            missing(f"{object_name}-missing-{field}", (*path, field))
            current: object = valid
            for part in (*path, field):
                current = current[part]  # type: ignore[index]
            if isinstance(current, bool):
                invalid_type: object = 1
            elif isinstance(current, int):
                invalid_type = True
            elif isinstance(current, str):
                invalid_type = []
            elif current is None:
                invalid_type = True
            elif isinstance(current, dict):
                invalid_type = []
            else:
                invalid_type = {}
            changed(f"{object_name}-invalid-type-{field}", (*path, field), invalid_type)

    # Types, null/string unions, minLength, enum, const, pattern, and integer bounds.
    invalid_values = [
        (("schema_version",), True),
        (("entries",), {}),
        (("setup_reservations",), {}),
        (("recovery_audit",), {}),
        (("extensions",), []),
        (("entries", 0, "extensions"), []),
        (("entries", 0, "change_id"), 1),
        (("entries", 0, "agent_id"), 1),
        (("entries", 0, "agent_id"), True),
        (("entries", 0, "branch"), ""),
        (("entries", 0, "setup_id"), 1),
        (("entries", 0, "last_heartbeat"), 1),
        (("entries", 0, "retained"), 1),
        (("entries", 0, "retention_reason"), 1),
        (("entries", 0, "recovery_required"), 0),
        (("entries", 0, "recovery_reason"), 1),
        (("entries", 0, "durability_target"), []),
        (("entries", 0, "activity_lease", "session_id"), 1),
        (("entries", 0, "activity_lease", "lifecycle_mode"), "bogus"),
        (("entries", 0, "activity_lease", "ttl_seconds"), True),
        (("entries", 0, "activity_lease", "ttl_seconds"), 59),
        (("entries", 0, "activity_lease", "ttl_seconds"), 86401),
        (("entries", 1, "recovery_context", "source"), "bogus"),
        (("entries", 1, "recovery_context", "prior_owner"), 1),
        (("entries", 1, "recovery_context", "prior_lease_id"), ""),
        (("entries", 1, "recovery_context", "process_evidence_key"), "bad"),
        (("setup_reservations", 0, "agent_id"), True),
        (("setup_reservations", 0, "setup_id"), 1),
        (("setup_reservations", 0, "lease_intent", "session_id"), 1),
        (("setup_reservations", 0, "lease_intent", "lifecycle_mode"), "manual"),
        (("setup_reservations", 0, "lease_intent", "ttl_seconds"), True),
        (("setup_reservations", 0, "state"), "done"),
        (("setup_reservations", 0, "updated_at"), 1),
        (("setup_reservations", 0, "ttl_seconds"), True),
        (("setup_reservations", 0, "durability_target", "remote_name"), "bad/name"),
        (("setup_reservations", 0, "durability_target", "ref_name"), "refs/remotes/origin/"),
        (("setup_reservations", 0, "durability_target", "remote_url_hash_algorithm"), "sha256"),
        (("setup_reservations", 0, "durability_target", "canonical_remote_url_sha256"), "A" * 64),
        (("recovery_audit", 0, "agent_id"), 1),
        (("recovery_audit", 0, "termination_confirmed"), 1),
        (("recovery_audit", 0, "new_owner"), ""),
        (("recovery_audit", 0, "process_evidence_key"), "bad"),
        (("recovery_audit", 0, "established_durability_target"), []),
        (("recovery_audit", 1, "prior_owner"), None),
        (("recovery_audit", 1, "outcome"), "removed"),
        (("recovery_audit", 2, "discard_confirmed"), 0),
        (("recovery_audit", 2, "outcome"), "removed"),
    ]
    for index, (path, value) in enumerate(invalid_values):
        changed(f"invalid-{index}-{'-'.join(str(item) for item in path)}", path, value)

    changed("integral-float-lease-ttl", ("entries", 0, "activity_lease", "ttl_seconds"), 1800.0)
    changed(
        "integral-float-intent-ttl",
        ("setup_reservations", 0, "lease_intent", "ttl_seconds"),
        1800.0,
    )
    changed("integral-float-reservation-ttl", ("setup_reservations", 0, "ttl_seconds"), 1800.0)

    # Conditional dependencies and additionalProperties on every closed object.
    changed("retained-requires-reason", ("entries", 0, "retained"), True)
    changed("recovery-required-requires-metadata", ("entries", 0, "recovery_required"), True)
    changed(
        "automatic-lease-requires-controller",
        ("entries", 0, "activity_lease", "controller_instance_id"),
        None,
    )
    changed(
        "explicit-discard-requires-confirmation",
        ("recovery_audit", 2, "outcome"),
        "removed-explicit-discard",
    )
    for name, path in [
        ("registry", ()),
        ("entry", ("entries", 0)),
        ("lease", ("entries", 0, "activity_lease")),
        ("context", ("entries", 1, "recovery_context")),
        ("reservation", ("setup_reservations", 0)),
        ("intent", ("setup_reservations", 0, "lease_intent")),
        ("target", ("setup_reservations", 0, "durability_target")),
        ("force-audit", ("recovery_audit", 0)),
        ("setup-audit", ("recovery_audit", 1)),
        ("teardown-audit", ("recovery_audit", 2)),
    ]:
        changed(f"{name}-additional-property", (*path, "unknown"), True)
    valid_v1 = {"version": 1, "entries": [_v1_entry(extra=[1, True, None])]}
    cases.append(("valid-v1", valid_v1))
    for name, path, value in [
        ("v1-version-bool", ("version",), True),
        ("v1-entries-type", ("entries",), {}),
        ("v1-entry-type", ("entries", 0), []),
        ("v1-agent-type", ("entries", 0, "agent_id"), True),
        ("v1-pinned-type", ("entries", 0, "pinned"), 1),
        ("v1-schema-version-forbidden", ("schema_version",), 2),
    ]:
        document = copy.deepcopy(valid_v1)
        target_object: object = document
        for part in path[:-1]:
            target_object = target_object[part]  # type: ignore[index]
        target_object[path[-1]] = value  # type: ignore[index]
        cases.append((name, document))
    for field in ("change_id", "branch", "worktree_path", "created_at", "pinned"):
        document = copy.deepcopy(valid_v1)
        del document["entries"][0][field]  # type: ignore[index]
        cases.append((f"v1-entry-missing-{field}", document))
    return cases


def test_writer_matches_canonical_schema_for_systematic_matrix(tmp_path: Path) -> None:
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "openspec/changes/phase-scoped-worktree-lifecycle/contracts/schemas/worktree-registry-v2.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    validator = Draft202012Validator(schema)
    for index, (name, document) in enumerate(_systematic_schema_documents()):
        schema_accepts = validator.is_valid(document)
        try:
            lifecycle.write_registry(tmp_path / str(index), document)
        except lifecycle.RegistryCorrupt:
            writer_accepts = False
        else:
            writer_accepts = True
        assert writer_accepts is schema_accepts, name
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
