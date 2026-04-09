"""Tests for merge train shared types and file-path-to-namespace heuristic.

Covers wp-contracts tasks:
  - 1.3 MergeTrainStatus enum, TrainEntry, TrainPartition, TrainComposition
  - 1.4 state machine transitions, eject_count tracking, ABANDONED state (R14)
  - 1.4a / 1.4b file_path_to_namespaces mapping (D8, R8)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.merge_train_types import (
    DEFAULT_SWEEP_INTERVAL_SECONDS,
    EJECT_PRIORITY_DECREMENT,
    MAX_EJECT_COUNT,
    PATH_TO_NAMESPACE_RULES,
    TERMINAL_STATUSES,
    CrossPartitionEntry,
    MergeTrainStatus,
    TrainComposition,
    TrainEntry,
    TrainPartition,
    claim_prefix,
    file_path_to_namespaces,
)

# ---------------------------------------------------------------------------
# MergeTrainStatus state machine (R3)
# ---------------------------------------------------------------------------


class TestMergeTrainStatus:
    def test_all_states_present(self) -> None:
        expected = {
            "queued",
            "speculating",
            "spec_passed",
            "merging",
            "merged",
            "ejected",
            "blocked",
            "abandoned",
            # Legacy values from original MergeStatus
            "pre_merge_check",
            "ready",
        }
        assert {s.value for s in MergeTrainStatus} == expected

    def test_terminal_statuses_include_merged_and_abandoned(self) -> None:
        assert MergeTrainStatus.MERGED in TERMINAL_STATUSES
        assert MergeTrainStatus.ABANDONED in TERMINAL_STATUSES
        # EJECTED is NOT terminal — it gets re-queued until MAX_EJECT_COUNT (R14)
        assert MergeTrainStatus.EJECTED not in TERMINAL_STATUSES
        # BLOCKED is NOT terminal — it can recover (R9)
        assert MergeTrainStatus.BLOCKED not in TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# TrainEntry dataclass (R3, R14)
# ---------------------------------------------------------------------------


class TestTrainEntry:
    def _make(self, **overrides: object) -> TrainEntry:
        defaults: dict[str, object] = {
            "feature_id": "f1",
            "branch_name": "openspec/f1",
            "merge_priority": 5,
            "status": MergeTrainStatus.QUEUED,
            "resource_claims": ["api:GET /v1/users"],
        }
        defaults.update(overrides)
        return TrainEntry(**defaults)  # type: ignore[arg-type]

    def test_defaults(self) -> None:
        entry = self._make()
        assert entry.eject_count == 0
        assert entry.last_eject_reason is None
        assert entry.decomposition == "branch"
        assert entry.stack_position is None
        assert not entry.is_terminal()

    def test_is_terminal_merged(self) -> None:
        entry = self._make(status=MergeTrainStatus.MERGED)
        assert entry.is_terminal()

    def test_is_terminal_abandoned(self) -> None:
        entry = self._make(status=MergeTrainStatus.ABANDONED)
        assert entry.is_terminal()

    def test_to_metadata_dict_roundtrip(self) -> None:
        now = datetime.now(UTC)
        entry = self._make(
            status=MergeTrainStatus.SPECULATING,
            train_id="abcd1234",
            partition_id="api-partition",
            train_position=2,
            speculative_ref="refs/speculative/train-abcd1234/pos-2",
            eject_count=1,
            last_eject_reason="CI flake",
            queued_at=now,
        )
        meta = entry.to_metadata_dict()
        assert meta["status"] == "speculating"
        assert meta["train_id"] == "abcd1234"
        assert meta["partition_id"] == "api-partition"
        assert meta["train_position"] == 2
        assert meta["eject_count"] == 1
        assert meta["last_eject_reason"] == "CI flake"
        assert meta["queued_at"] == now.isoformat()


# ---------------------------------------------------------------------------
# TrainPartition / TrainComposition
# ---------------------------------------------------------------------------


class TestTrainPartition:
    def test_all_passed_empty_is_false(self) -> None:
        partition = TrainPartition(partition_id="p1")
        assert partition.all_passed() is False

    def test_all_passed_mixed_is_false(self) -> None:
        partition = TrainPartition(partition_id="p1")
        partition.entries.append(
            TrainEntry("f1", None, 5, MergeTrainStatus.SPEC_PASSED)
        )
        partition.entries.append(
            TrainEntry("f2", None, 5, MergeTrainStatus.SPECULATING)
        )
        assert partition.all_passed() is False

    def test_all_passed_true(self) -> None:
        partition = TrainPartition(partition_id="p1")
        partition.entries.append(
            TrainEntry("f1", None, 5, MergeTrainStatus.SPEC_PASSED)
        )
        partition.entries.append(
            TrainEntry("f2", None, 5, MergeTrainStatus.SPEC_PASSED)
        )
        assert partition.all_passed() is True


class TestTrainComposition:
    def test_new_train_id_is_hex_12(self) -> None:
        train_id = TrainComposition.new_train_id()
        assert len(train_id) == 12
        assert all(c in "0123456789abcdef" for c in train_id)

    def test_total_entry_count_sums_partitions(self) -> None:
        comp = TrainComposition(train_id="abcd1234")
        p1 = TrainPartition(partition_id="p1")
        p1.entries.extend(
            [
                TrainEntry("f1", None, 5, MergeTrainStatus.QUEUED),
                TrainEntry("f2", None, 5, MergeTrainStatus.QUEUED),
            ]
        )
        p2 = TrainPartition(partition_id="p2")
        p2.entries.append(TrainEntry("f3", None, 5, MergeTrainStatus.QUEUED))
        comp.partitions.extend([p1, p2])
        assert comp.total_entry_count() == 3
        assert {e.feature_id for e in comp.all_entries()} == {"f1", "f2", "f3"}


# ---------------------------------------------------------------------------
# Constants (D4, D12)
# ---------------------------------------------------------------------------


class TestConstants:
    def test_max_eject_count_default(self) -> None:
        assert MAX_EJECT_COUNT == 3

    def test_eject_priority_decrement(self) -> None:
        assert EJECT_PRIORITY_DECREMENT == 10

    def test_sweep_interval_default(self) -> None:
        assert DEFAULT_SWEEP_INTERVAL_SECONDS == 60


# ---------------------------------------------------------------------------
# file_path_to_namespaces heuristic (D8, R8, tasks 1.4a / 1.4b)
# ---------------------------------------------------------------------------


class TestFilePathToNamespaces:
    """Exercise the reverse mapping from file paths to lock-key namespaces."""

    def test_api_source_file(self) -> None:
        assert file_path_to_namespaces("src/api/users.py") == {"api:"}

    def test_routes_module(self) -> None:
        assert file_path_to_namespaces("backend/routes/users.py") == {"api:"}

    def test_endpoints_module(self) -> None:
        assert file_path_to_namespaces("src/endpoints/billing.py") == {"api:"}

    def test_db_schema_file(self) -> None:
        result = file_path_to_namespaces("src/db/schema.py")
        assert "db:schema:" in result

    def test_models_py(self) -> None:
        assert file_path_to_namespaces("src/app/models.py") == {"db:schema:"}

    def test_models_directory(self) -> None:
        assert file_path_to_namespaces("backend/models/user.py") == {"db:schema:"}

    def test_migration_path(self) -> None:
        result = file_path_to_namespaces(
            "agent-coordinator/supabase/migrations/20240101_init.sql"
        )
        assert "db:migration-slot" in result

    def test_supabase_migration(self) -> None:
        assert file_path_to_namespaces("supabase/migrations/0042.sql") == {
            "db:migration-slot"
        }

    def test_event_handlers(self) -> None:
        assert file_path_to_namespaces("src/events/user_registered.py") == {"event:"}

    def test_contract_file(self) -> None:
        result = file_path_to_namespaces("contracts/openapi/v1.yaml")
        assert "contract:" in result

    def test_flags_yaml_maps_to_flag_namespace(self) -> None:
        assert file_path_to_namespaces("flags.yaml") == {"flag:"}

    @pytest.mark.parametrize(
        "unrelated_path",
        [
            "README.md",
            "docs/architecture.md",
            "src/util/helpers.py",
            "tests/test_foo.py",
            "pyproject.toml",
        ],
    )
    def test_unrelated_path_returns_empty_set(self, unrelated_path: str) -> None:
        """Empty set means 'out of scope for logical validation' (D8)."""
        assert file_path_to_namespaces(unrelated_path) == set()

    def test_empty_path_returns_empty_set(self) -> None:
        assert file_path_to_namespaces("") == set()

    def test_normalizes_leading_dot_slash(self) -> None:
        assert file_path_to_namespaces("./src/api/users.py") == {"api:"}

    def test_rules_table_is_list_of_tuples(self) -> None:
        """The rule table must be inspectable and unit-testable."""
        assert isinstance(PATH_TO_NAMESPACE_RULES, list)
        assert all(
            isinstance(r, tuple) and len(r) == 2 for r in PATH_TO_NAMESPACE_RULES
        )


class TestClaimPrefix:
    """Extract the namespace prefix from a lock-key string."""

    def test_api_claim(self) -> None:
        assert claim_prefix("api:GET /v1/users") == "api:"

    def test_db_schema_claim(self) -> None:
        assert claim_prefix("db:schema:users") == "db:schema:"

    def test_db_migration_slot(self) -> None:
        assert claim_prefix("db:migration-slot") == "db:migration-slot"

    def test_event_claim(self) -> None:
        assert claim_prefix("event:user.created") == "event:"

    def test_flag_claim(self) -> None:
        assert claim_prefix("flag:billing/invoice") == "flag:"

    def test_file_path_has_no_prefix(self) -> None:
        assert claim_prefix("src/api/users.py") == ""


# ---------------------------------------------------------------------------
# CrossPartitionEntry dataclass
# ---------------------------------------------------------------------------


class TestCrossPartitionEntry:
    def test_spans_partitions_default_empty(self) -> None:
        entry = TrainEntry("f1", None, 5, MergeTrainStatus.QUEUED)
        cpe = CrossPartitionEntry(feature_id="f1", entry=entry)
        assert cpe.spans_partitions == []

    def test_spans_partitions_assigned(self) -> None:
        entry = TrainEntry("f1", None, 5, MergeTrainStatus.QUEUED)
        cpe = CrossPartitionEntry(
            feature_id="f1",
            entry=entry,
            spans_partitions=["api-partition", "db-partition"],
        )
        assert len(cpe.spans_partitions) == 2
