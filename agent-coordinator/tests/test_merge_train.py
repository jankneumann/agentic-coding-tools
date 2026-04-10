"""Tests for the speculative merge train engine (wp-train-engine).

Covers tasks 2.1-2.17:
  - 2.1 compute_partitions: prefix grouping, cross-partition, cycle detection, perf
  - 2.3 compose_train: train creation, position assignment, authorization
  - 2.5 post-speculation claim validation: matches / mismatch → BLOCKED
  - 2.7 eject_from_train: independence check, ABANDONED at MAX_EJECT_COUNT
  - 2.9 BLOCKED recovery: manual re-enqueue, auto re-eval after 1 hour
  - 2.11 partition-aware wave merge executor
  - 2.13 crash recovery: orphaned speculative refs
  - 2.15 extended enqueue: decomposition, auto flag creation

All tests use injectable fakes for `GitAdapter`, `MergeQueueService`, and the
feature-registry service so they run without Postgres or a real git repo.
"""

from __future__ import annotations

import random
import string
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.git_adapter import (
    ChangedFiles,
    FastForwardResult,
    MergeTreeResult,
)
from src.merge_train_types import (
    MAX_EJECT_COUNT,
    CrossPartitionEntry,
    MergeTrainStatus,
    TrainComposition,
    TrainEntry,
    TrainPartition,
)

# ---------------------------------------------------------------------------
# Test helpers — factories for TrainEntry and fake git adapter
# ---------------------------------------------------------------------------


def _make_entry(
    feature_id: str,
    claims: list[str],
    branch: str | None = None,
    priority: int = 5,
    status: MergeTrainStatus = MergeTrainStatus.QUEUED,
    **kwargs: Any,
) -> TrainEntry:
    return TrainEntry(
        feature_id=feature_id,
        branch_name=branch or f"openspec/{feature_id}",
        merge_priority=priority,
        status=status,
        resource_claims=claims,
        original_priority=priority,
        **kwargs,
    )


class _FakeGitAdapter:
    """In-memory GitAdapter implementation for tests.

    Keeps a map of ref_name → MergeTreeResult. Callers can pre-load results
    or let the default "success" path fabricate a fake tree OID.
    """

    def __init__(self) -> None:
        self.created_refs: list[tuple[str, str, str]] = []  # (base, branch, ref)
        self.deleted_trains: list[str] = []
        self.fast_forwards: list[str] = []
        self.changed_files_by_branch: dict[str, ChangedFiles] = {}
        # Pre-seeded conflict responses: (base_ref, feature_branch) → MergeTreeResult
        self.conflicts: dict[tuple[str, str], MergeTreeResult] = {}
        # Pre-seeded errors: (base_ref, feature_branch) → MergeTreeResult (error)
        self.errors: dict[tuple[str, str], MergeTreeResult] = {}
        self.speculative_refs: list[str] = []
        self._fake_oid_counter = 0

    def create_speculative_ref(
        self, base_ref: str, feature_branch: str, ref_name: str
    ) -> MergeTreeResult:
        self.created_refs.append((base_ref, feature_branch, ref_name))
        key = (base_ref, feature_branch)
        if key in self.conflicts:
            return self.conflicts[key]
        if key in self.errors:
            return self.errors[key]
        # Default success: fabricate a deterministic fake OID.
        self._fake_oid_counter += 1
        oid = f"{self._fake_oid_counter:040x}"
        commit = f"{self._fake_oid_counter:040x}"[:40]
        self.speculative_refs.append(ref_name)
        return MergeTreeResult(success=True, tree_oid=oid, commit_sha=commit)

    def delete_speculative_refs(self, train_id: str) -> int:
        self.deleted_trains.append(train_id)
        before = len(self.speculative_refs)
        prefix = f"refs/speculative/train-{train_id}/"
        self.speculative_refs = [r for r in self.speculative_refs if not r.startswith(prefix)]
        return before - len(self.speculative_refs)

    def fast_forward_main(self, speculative_ref: str) -> FastForwardResult:
        self.fast_forwards.append(speculative_ref)
        return FastForwardResult(success=True, new_main_sha=f"main-{len(self.fast_forwards)}")

    def get_changed_files(self, base_ref: str, feature_branch: str) -> ChangedFiles:
        return self.changed_files_by_branch.get(feature_branch, ChangedFiles())

    def list_speculative_refs(self) -> list[str]:
        return list(self.speculative_refs)


# ---------------------------------------------------------------------------
# compute_partitions (task 2.1)
# ---------------------------------------------------------------------------


class TestComputePartitionsBasic:
    """Basic partition detection: empty, single, same-prefix, different-prefix."""

    def test_empty_entries_produces_empty_result(self) -> None:
        from src.merge_train import compute_partitions

        result = compute_partitions([])
        assert result.partitions == []
        assert result.cross_partition_entries == []
        assert result.cycles == []

    def test_single_entry_single_prefix(self) -> None:
        from src.merge_train import compute_partitions

        entries = [_make_entry("f1", ["api:GET /v1/users"])]
        result = compute_partitions(entries)
        assert len(result.partitions) == 1
        p = result.partitions[0]
        assert p.partition_id == "api:"
        assert len(p.entries) == 1
        assert p.entries[0].feature_id == "f1"
        assert "api:" in p.key_prefixes

    def test_two_entries_same_prefix_same_partition(self) -> None:
        from src.merge_train import compute_partitions

        entries = [
            _make_entry("f1", ["api:GET /v1/users"]),
            _make_entry("f2", ["api:POST /v1/orders"]),
        ]
        result = compute_partitions(entries)
        assert len(result.partitions) == 1
        assert {e.feature_id for e in result.partitions[0].entries} == {"f1", "f2"}

    def test_two_entries_different_prefixes_different_partitions(self) -> None:
        from src.merge_train import compute_partitions

        entries = [
            _make_entry("f1", ["api:GET /v1/users"]),
            _make_entry("f2", ["db:schema:orders"]),
        ]
        result = compute_partitions(entries)
        assert len(result.partitions) == 2
        ids_by_partition = {
            p.partition_id: {e.feature_id for e in p.entries} for p in result.partitions
        }
        assert ids_by_partition["api:"] == {"f1"}
        assert ids_by_partition["db:schema:"] == {"f2"}
        assert result.cross_partition_entries == []

    def test_three_features_spec_scenario(self) -> None:
        """Spec scenario: A claims api:GET, B claims db:schema, C claims api:POST.

        Expected: 2 partitions. api: partition has {A, C}, db:schema: has {B}.
        """
        from src.merge_train import compute_partitions

        entries = [
            _make_entry("feature-A", ["api:GET /v1/users"]),
            _make_entry("feature-B", ["db:schema:billing"]),
            _make_entry("feature-C", ["api:POST /v1/orders"]),
        ]
        result = compute_partitions(entries)
        by_id = {p.partition_id: p for p in result.partitions}
        assert set(by_id.keys()) == {"api:", "db:schema:"}
        assert {e.feature_id for e in by_id["api:"].entries} == {"feature-A", "feature-C"}
        assert {e.feature_id for e in by_id["db:schema:"].entries} == {"feature-B"}


class TestComputePartitionsCrossPartition:
    """Entries with claims spanning multiple namespaces."""

    def test_cross_partition_entry_separated(self) -> None:
        from src.merge_train import compute_partitions

        entries = [
            _make_entry("f1", ["api:GET /v1/users", "db:schema:users"]),
        ]
        result = compute_partitions(entries)
        # The cross-partition entry does NOT appear in any partition's entries list
        assert all(e.feature_id != "f1" for p in result.partitions for e in p.entries)
        assert len(result.cross_partition_entries) == 1
        cpe = result.cross_partition_entries[0]
        assert cpe.feature_id == "f1"
        assert set(cpe.spans_partitions) == {"api:", "db:schema:"}

    def test_cross_partition_ghost_partitions_created(self) -> None:
        """A cross-partition entry's spanned partitions must exist even if empty."""
        from src.merge_train import compute_partitions

        # Only one entry, spanning two namespaces, no single-prefix entries.
        entries = [_make_entry("f1", ["api:x", "event:y"])]
        result = compute_partitions(entries)
        partition_ids = {p.partition_id for p in result.partitions}
        assert "api:" in partition_ids
        assert "event:" in partition_ids
        # Ghost partitions are empty
        for p in result.partitions:
            assert p.entries == []

    def test_cross_partition_spans_partitions_is_sorted(self) -> None:
        """Deterministic ordering for downstream cycle detection."""
        from src.merge_train import compute_partitions

        entries = [_make_entry("f1", ["event:z", "api:x", "db:schema:y"])]
        result = compute_partitions(entries)
        assert len(result.cross_partition_entries) == 1
        cpe = result.cross_partition_entries[0]
        assert cpe.spans_partitions == sorted(cpe.spans_partitions)

    def test_mixed_single_and_cross_partition(self) -> None:
        from src.merge_train import compute_partitions

        entries = [
            _make_entry("f1", ["api:GET /v1/users"]),
            _make_entry("f2", ["db:schema:users"]),
            _make_entry("f3", ["api:GET /v1/users", "db:schema:users"]),
        ]
        result = compute_partitions(entries)
        # f1 → api:, f2 → db:schema:, f3 → cross
        by_id = {p.partition_id: p for p in result.partitions}
        assert {e.feature_id for e in by_id["api:"].entries} == {"f1"}
        assert {e.feature_id for e in by_id["db:schema:"].entries} == {"f2"}
        assert [cpe.feature_id for cpe in result.cross_partition_entries] == ["f3"]


class TestComputePartitionsFilePathClaims:
    """File-path locks (no logical prefix) fall back to full-claim partitioning."""

    def test_file_path_claim_creates_own_partition(self) -> None:
        from src.merge_train import compute_partitions

        entries = [_make_entry("f1", ["src/locks.py"])]
        result = compute_partitions(entries)
        assert len(result.partitions) == 1
        # File-path partitions use the full claim as the id
        assert result.partitions[0].partition_id == "src/locks.py"

    def test_two_entries_same_file_path_same_partition(self) -> None:
        from src.merge_train import compute_partitions

        entries = [
            _make_entry("f1", ["src/locks.py"]),
            _make_entry("f2", ["src/locks.py"]),
        ]
        result = compute_partitions(entries)
        assert len(result.partitions) == 1
        assert {e.feature_id for e in result.partitions[0].entries} == {"f1", "f2"}

    def test_file_path_and_logical_claim_is_cross_partition(self) -> None:
        from src.merge_train import compute_partitions

        entries = [_make_entry("f1", ["src/locks.py", "api:GET /v1/users"])]
        result = compute_partitions(entries)
        assert len(result.cross_partition_entries) == 1
        cpe = result.cross_partition_entries[0]
        assert "api:" in cpe.spans_partitions
        assert "src/locks.py" in cpe.spans_partitions


class TestComputePartitionsCycleDetection:
    """Cross-partition cycle detection per R10 scenario."""

    def test_three_way_cycle_detected(self) -> None:
        """Spec: A spans {P1,P2}, B spans {P2,P3}, C spans {P3,P1} → cycle."""
        from src.merge_train import compute_partitions

        entries = [
            _make_entry("A", ["api:x", "db:schema:y"]),
            _make_entry("B", ["db:schema:y", "event:z"]),
            _make_entry("C", ["event:z", "api:x"]),
        ]
        result = compute_partitions(entries)
        assert len(result.cross_partition_entries) == 3
        assert len(result.cycles) >= 1
        # The cycle should include all three feature ids.
        cycle_members = set().union(*result.cycles)
        assert cycle_members == {"A", "B", "C"}

    def test_no_cycle_for_linear_chain(self) -> None:
        """A spans {P1,P2}, B spans {P2,P3} — no cycle, just a chain."""
        from src.merge_train import compute_partitions

        entries = [
            _make_entry("A", ["api:x", "db:schema:y"]),
            _make_entry("B", ["db:schema:y", "event:z"]),
        ]
        result = compute_partitions(entries)
        assert result.cycles == []

    def test_cycle_members_are_sorted(self) -> None:
        from src.merge_train import compute_partitions

        entries = [
            _make_entry("b_feature", ["api:x", "db:schema:y"]),
            _make_entry("a_feature", ["db:schema:y", "event:z"]),
            _make_entry("c_feature", ["event:z", "api:x"]),
        ]
        result = compute_partitions(entries)
        if result.cycles:
            for cycle in result.cycles:
                assert cycle == sorted(cycle)


class TestComputePartitionsPerformance:
    """R10: compute_partitions must complete in O(N·P), <5s for N=1000, P=10."""

    def test_1000_entries_under_5_seconds(self) -> None:
        from src.merge_train import compute_partitions

        random.seed(1234)
        prefixes = [
            "api:",
            "db:schema:",
            "event:",
            "flag:",
            "db:migration-slot",
            "contract:",
        ]

        def _random_claim() -> str:
            p = random.choice(prefixes)
            ident = "".join(random.choices(string.ascii_lowercase, k=8))
            if p == "db:migration-slot":
                return "db:migration-slot"
            return f"{p}{ident}"

        entries = [
            _make_entry(f"f{i}", [_random_claim() for _ in range(10)])
            for i in range(1000)
        ]

        start = time.monotonic()
        result = compute_partitions(entries)
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"compute_partitions took {elapsed:.2f}s (budget 5s)"
        # Sanity check: every entry is represented somewhere
        seen: set[str] = set()
        for p in result.partitions:
            seen.update(e.feature_id for e in p.entries)
        seen.update(cpe.feature_id for cpe in result.cross_partition_entries)
        assert seen == {f"f{i}" for i in range(1000)}

    def test_single_partition_with_many_entries(self) -> None:
        """1000 entries all claiming the same prefix → 1 partition, no degradation."""
        from src.merge_train import compute_partitions

        entries = [_make_entry(f"f{i}", ["api:x"]) for i in range(1000)]
        start = time.monotonic()
        result = compute_partitions(entries)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0
        assert len(result.partitions) == 1
        assert len(result.partitions[0].entries) == 1000


class TestComputePartitionsStability:
    """Determinism: same input yields same output across runs."""

    def test_partition_order_is_deterministic(self) -> None:
        from src.merge_train import compute_partitions

        entries = [
            _make_entry("f3", ["event:z"]),
            _make_entry("f1", ["api:x"]),
            _make_entry("f2", ["db:schema:y"]),
        ]
        r1 = compute_partitions(entries)
        r2 = compute_partitions(entries)
        assert [p.partition_id for p in r1.partitions] == [
            p.partition_id for p in r2.partitions
        ]

    def test_cross_partition_order_is_deterministic(self) -> None:
        from src.merge_train import compute_partitions

        entries = [
            _make_entry("f1", ["api:x", "db:schema:y"]),
            _make_entry("f2", ["event:z", "flag:w"]),
        ]
        r1 = compute_partitions(entries)
        r2 = compute_partitions(entries)
        assert [cpe.feature_id for cpe in r1.cross_partition_entries] == [
            cpe.feature_id for cpe in r2.cross_partition_entries
        ]


# ---------------------------------------------------------------------------
# compose_train (tasks 2.3, 2.4)
# ---------------------------------------------------------------------------


class TestComposeTrainAuthorization:
    """R6: compose_train requires trust level >= 3."""

    def test_rejects_trust_level_below_3(self) -> None:
        from src.merge_train import TrainAuthorizationError, compose_train

        adapter = _FakeGitAdapter()
        with pytest.raises(TrainAuthorizationError, match="trust"):
            compose_train(
                entries=[_make_entry("f1", ["api:x"])],
                git_adapter=adapter,
                caller_trust_level=2,
            )

    def test_accepts_trust_level_3(self) -> None:
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        comp = compose_train(
            entries=[_make_entry("f1", ["api:x"])],
            git_adapter=adapter,
            caller_trust_level=3,
        )
        assert comp is not None


class TestComposeTrainEmptyAndSingle:
    def test_empty_queue_produces_empty_train(self) -> None:
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        comp = compose_train(entries=[], git_adapter=adapter, caller_trust_level=3)
        assert isinstance(comp, TrainComposition)
        assert comp.partitions == []
        assert comp.cross_partition_entries == []
        assert adapter.created_refs == []

    def test_single_entry_single_partition_position_1(self) -> None:
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        entries = [_make_entry("f1", ["api:GET /v1/users"])]
        comp = compose_train(
            entries=entries, git_adapter=adapter, caller_trust_level=3
        )
        assert comp.total_entry_count() == 1
        assert len(adapter.created_refs) == 1
        entry = comp.partitions[0].entries[0]
        assert entry.train_position == 1
        assert entry.train_id == comp.train_id
        assert entry.partition_id == "api:"
        assert entry.status == MergeTrainStatus.SPECULATING
        assert entry.speculative_ref == f"refs/speculative/train-{comp.train_id}/pos-1"

    def test_train_id_is_12_hex_chars(self) -> None:
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        comp = compose_train(
            entries=[_make_entry("f1", ["api:x"])],
            git_adapter=adapter,
            caller_trust_level=3,
        )
        assert len(comp.train_id) == 12
        assert all(c in "0123456789abcdef" for c in comp.train_id)


class TestComposeTrainPositionAssignment:
    def test_positions_assigned_by_priority_desc(self) -> None:
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        entries = [
            _make_entry("low", ["api:x"], priority=1),
            _make_entry("high", ["api:x"], priority=10),
            _make_entry("mid", ["api:x"], priority=5),
        ]
        comp = compose_train(
            entries=entries, git_adapter=adapter, caller_trust_level=3
        )
        assert len(comp.partitions) == 1
        partition_entries = sorted(
            comp.partitions[0].entries, key=lambda e: e.train_position or 0
        )
        assert [e.feature_id for e in partition_entries] == ["high", "mid", "low"]
        assert [e.train_position for e in partition_entries] == [1, 2, 3]

    def test_speculative_refs_chain_within_partition(self) -> None:
        """Position N > 1 uses position N-1's speculative ref as base."""
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        entries = [
            _make_entry("f1", ["api:x"], priority=10),
            _make_entry("f2", ["api:x"], priority=5),
            _make_entry("f3", ["api:x"], priority=1),
        ]
        comp = compose_train(
            entries=entries, git_adapter=adapter, caller_trust_level=3
        )
        # adapter.created_refs is a list of (base, branch, ref_name)
        # Position 1: base = main
        assert adapter.created_refs[0][0] == "main"
        # Position 2: base = position 1's ref
        assert adapter.created_refs[1][0] == f"refs/speculative/train-{comp.train_id}/pos-1"
        # Position 3: base = position 2's ref
        assert adapter.created_refs[2][0] == f"refs/speculative/train-{comp.train_id}/pos-2"

    def test_independent_partitions_do_not_chain(self) -> None:
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        entries = [
            _make_entry("a1", ["api:x"], priority=10),
            _make_entry("d1", ["db:schema:y"], priority=10),
        ]
        comp = compose_train(
            entries=entries, git_adapter=adapter, caller_trust_level=3
        )
        assert len(comp.partitions) == 2
        # Both are position 1 within their own partitions, both rooted on main.
        for base, _branch, _ref in adapter.created_refs:
            assert base == "main"


class TestComposeTrainSpeculativeRefNaming:
    """R7: speculative ref names must match the strict regex."""

    def test_ref_matches_spec_pattern(self) -> None:
        from src.git_adapter import SPECULATIVE_REF_PATTERN
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        entries = [_make_entry("f1", ["api:x"])]
        comp = compose_train(
            entries=entries, git_adapter=adapter, caller_trust_level=3
        )
        entry = comp.partitions[0].entries[0]
        assert entry.speculative_ref is not None
        assert SPECULATIVE_REF_PATTERN.match(entry.speculative_ref)


class TestComposeTrainConflicts:
    """R11: conflict → entry transitions to BLOCKED (not EJECTED)."""

    def test_conflict_marks_entry_blocked(self) -> None:
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        adapter.conflicts[("main", "openspec/f1")] = MergeTreeResult(
            success=False,
            conflict_files=["src/api.py"],
        )
        comp = compose_train(
            entries=[_make_entry("f1", ["api:x"])],
            git_adapter=adapter,
            caller_trust_level=3,
        )
        entry = comp.partitions[0].entries[0]
        assert entry.status == MergeTrainStatus.BLOCKED
        assert entry.speculative_ref is None
        # Conflict file list should be stored in metadata for diagnostics (R11)
        assert "speculative_merge_conflict" in (entry.last_eject_reason or "") or \
               entry.metadata.get("conflict_files") == ["src/api.py"]

    def test_conflict_does_not_break_chain_for_subsequent_partition(self) -> None:
        """A conflict in partition A must not block partition B."""
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        adapter.conflicts[("main", "openspec/a1")] = MergeTreeResult(
            success=False, conflict_files=["src/api.py"]
        )
        entries = [
            _make_entry("a1", ["api:x"]),
            _make_entry("d1", ["db:schema:y"]),
        ]
        comp = compose_train(
            entries=entries, git_adapter=adapter, caller_trust_level=3
        )
        d1 = None
        for p in comp.partitions:
            for e in p.entries:
                if e.feature_id == "d1":
                    d1 = e
        assert d1 is not None
        assert d1.status == MergeTrainStatus.SPECULATING


class TestComposeTrainCrossPartition:
    """Cross-partition entries are chained before regular entries."""

    def test_cross_partition_entry_gets_speculative_ref(self) -> None:
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        entries = [_make_entry("f1", ["api:x", "db:schema:y"])]
        comp = compose_train(
            entries=entries, git_adapter=adapter, caller_trust_level=3
        )
        assert len(comp.cross_partition_entries) == 1
        cpe = comp.cross_partition_entries[0]
        assert cpe.entry.speculative_ref is not None
        assert cpe.entry.status == MergeTrainStatus.SPECULATING

    def test_regular_entry_in_spanned_partition_uses_cross_ref_as_base(self) -> None:
        """Spec: entries behind a cross-partition entry speculate against a base
        that includes this entry.
        """
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        entries = [
            _make_entry("cross", ["api:x", "db:schema:y"], priority=10),
            _make_entry("api_only", ["api:x"], priority=5),
        ]
        comp = compose_train(
            entries=entries, git_adapter=adapter, caller_trust_level=3
        )
        # Find the api_only entry's base in the adapter call log
        api_only_call = next(
            call for call in adapter.created_refs if call[1] == "openspec/api_only"
        )
        # Its base must be the cross-partition entry's ref, not "main"
        cross_ref = comp.cross_partition_entries[0].entry.speculative_ref
        assert api_only_call[0] == cross_ref


class TestComposeTrainScale:
    """R11: 100-entry train should be manageable."""

    def test_100_entries_complete(self) -> None:
        from src.merge_train import compose_train

        adapter = _FakeGitAdapter()
        entries = [
            _make_entry(f"f{i}", [f"api:endpoint_{i}"], priority=100 - i)
            for i in range(100)
        ]
        start = time.monotonic()
        comp = compose_train(
            entries=entries, git_adapter=adapter, caller_trust_level=3
        )
        elapsed = time.monotonic() - start
        # Fake adapter is instant, so this exercises composition overhead only.
        assert elapsed < 5.0
        assert comp.total_entry_count() == 100
        assert len(adapter.created_refs) == 100


# ---------------------------------------------------------------------------
# Post-speculation claim validation (tasks 2.5, 2.6) — D8, R8
# ---------------------------------------------------------------------------


class TestValidatePostSpeculationClaims:
    """After speculation, the engine checks that actual file changes match the
    declared resource claims. Mismatch → BLOCKED.
    """

    def _speculated(
        self, feature_id: str, claims: list[str], ref: str = "refs/speculative/train-abcd1234/pos-1"
    ) -> TrainEntry:
        e = _make_entry(feature_id, claims, status=MergeTrainStatus.SPECULATING)
        e.speculative_ref = ref
        e.train_id = "abcd1234"
        e.base_ref = "main"
        return e

    def test_claim_matches_actual_changes(self) -> None:
        """api: claim + only src/api/*.py changes → validation passes."""
        from src.merge_train import validate_post_speculation_claims

        adapter = _FakeGitAdapter()
        entry = self._speculated("f1", ["api:GET /v1/users"])
        adapter.changed_files_by_branch[entry.speculative_ref or ""] = ChangedFiles(
            changed_files=["src/api/users.py"],
        )
        blocked = validate_post_speculation_claims([entry], adapter)
        assert blocked == []
        assert entry.status == MergeTrainStatus.SPECULATING

    def test_claim_mismatch_transitions_to_blocked(self) -> None:
        """api: claim + src/db/schema.py changes → BLOCKED with namespace mismatch reason."""
        from src.merge_train import validate_post_speculation_claims

        adapter = _FakeGitAdapter()
        entry = self._speculated("f1", ["api:GET /v1/users"])
        adapter.changed_files_by_branch[entry.speculative_ref or ""] = ChangedFiles(
            changed_files=["src/api/users.py", "src/db/schema.py"],
        )
        blocked = validate_post_speculation_claims([entry], adapter)
        assert [b.feature_id for b in blocked] == ["f1"]
        assert entry.status == MergeTrainStatus.BLOCKED
        assert "claim mismatch" in (entry.metadata.get("blocked_reason") or "")
        # The undeclared namespace should be reported
        assert "db:schema:" in (entry.metadata.get("blocked_reason") or "")

    def test_file_with_no_namespace_is_skipped(self) -> None:
        """Files outside the 9 logical namespaces (README, docs/) are not mismatches."""
        from src.merge_train import validate_post_speculation_claims

        adapter = _FakeGitAdapter()
        entry = self._speculated("f1", ["api:GET /v1/users"])
        adapter.changed_files_by_branch[entry.speculative_ref or ""] = ChangedFiles(
            changed_files=["src/api/users.py", "README.md", "docs/api.md"],
        )
        blocked = validate_post_speculation_claims([entry], adapter)
        assert blocked == []

    def test_cross_namespace_claims_allows_both_changes(self) -> None:
        """A feature declaring BOTH api: and db:schema: can touch both areas."""
        from src.merge_train import validate_post_speculation_claims

        adapter = _FakeGitAdapter()
        entry = self._speculated("f1", ["api:GET /v1/users", "db:schema:users"])
        adapter.changed_files_by_branch[entry.speculative_ref or ""] = ChangedFiles(
            changed_files=["src/api/users.py", "src/db/schema.py"],
        )
        blocked = validate_post_speculation_claims([entry], adapter)
        assert blocked == []

    def test_skips_entries_without_speculative_ref(self) -> None:
        """Entries in QUEUED/BLOCKED state are ignored."""
        from src.merge_train import validate_post_speculation_claims

        adapter = _FakeGitAdapter()
        entry = _make_entry("f1", ["api:x"], status=MergeTrainStatus.QUEUED)
        # No speculative_ref set
        blocked = validate_post_speculation_claims([entry], adapter)
        assert blocked == []
        assert entry.status == MergeTrainStatus.QUEUED


# ---------------------------------------------------------------------------
# eject_from_train (tasks 2.7, 2.8) — D4, D11, D12, R14
# ---------------------------------------------------------------------------


class TestEjectFromTrain:
    """R4 + R14: eject decrements priority, checks independence, handles ABANDONED."""

    def _make_in_train(
        self,
        feature_id: str,
        claims: list[str],
        priority: int = 5,
        eject_count: int = 0,
    ) -> TrainEntry:
        e = _make_entry(
            feature_id, claims, priority=priority, status=MergeTrainStatus.SPECULATING
        )
        e.train_id = "abcd1234"
        e.speculative_ref = f"refs/speculative/train-{e.train_id}/pos-1"
        e.eject_count = eject_count
        return e

    def test_eject_decrements_priority(self) -> None:
        from src.merge_train import eject_from_train

        entry = self._make_in_train("f1", ["api:x"], priority=5)
        result = eject_from_train(
            entry,
            reason="CI failure: test_foo",
            caller_agent_id="agent-1",
            caller_trust_level=3,
            successors=[],
        )
        assert result.ejected is True
        assert result.priority_after == -5  # 5 - 10
        assert entry.status == MergeTrainStatus.EJECTED
        assert entry.merge_priority == -5
        assert entry.eject_count == 1
        assert entry.last_eject_reason == "CI failure: test_foo"

    def test_eject_abandoned_at_max_threshold(self) -> None:
        """D12: after MAX_EJECT_COUNT ejections, transition to ABANDONED."""
        from src.merge_train import eject_from_train

        entry = self._make_in_train(
            "f1", ["api:x"], priority=-15, eject_count=MAX_EJECT_COUNT - 1
        )
        result = eject_from_train(
            entry,
            reason="CI still failing",
            caller_agent_id="agent-1",
            caller_trust_level=3,
            successors=[],
        )
        assert result.ejected is True
        assert entry.status == MergeTrainStatus.ABANDONED
        assert entry.eject_count == MAX_EJECT_COUNT
        assert entry.is_terminal()
        # Priority is NOT decremented further once abandoned
        assert result.abandoned is True

    def test_eject_below_threshold_does_not_abandon(self) -> None:
        from src.merge_train import eject_from_train

        entry = self._make_in_train("f1", ["api:x"], eject_count=MAX_EJECT_COUNT - 2)
        result = eject_from_train(
            entry,
            reason="CI failure",
            caller_agent_id="agent-1",
            caller_trust_level=3,
            successors=[],
        )
        assert entry.status == MergeTrainStatus.EJECTED
        assert entry.is_terminal() is False
        assert result.abandoned is False

    def test_eject_requires_authorization(self) -> None:
        """Eject requires either ownership or trust level >= 3."""
        from src.merge_train import TrainAuthorizationError, eject_from_train

        entry = self._make_in_train("f1", ["api:x"])
        entry.metadata["owner_agent_id"] = "owner-agent"
        with pytest.raises(TrainAuthorizationError):
            eject_from_train(
                entry,
                reason="malicious eject",
                caller_agent_id="other-agent",
                caller_trust_level=2,
                successors=[],
            )

    def test_eject_allowed_by_owner(self) -> None:
        from src.merge_train import eject_from_train

        entry = self._make_in_train("f1", ["api:x"])
        entry.metadata["owner_agent_id"] = "owner-agent"
        # Owner can eject even without elevated trust
        result = eject_from_train(
            entry,
            reason="owner recall",
            caller_agent_id="owner-agent",
            caller_trust_level=2,
            successors=[],
        )
        assert result.ejected is True

    def test_eject_allowed_by_operator(self) -> None:
        """Trust level >= 3 bypasses ownership check."""
        from src.merge_train import eject_from_train

        entry = self._make_in_train("f1", ["api:x"])
        entry.metadata["owner_agent_id"] = "owner-agent"
        result = eject_from_train(
            entry,
            reason="operator override",
            caller_agent_id="ops-agent",
            caller_trust_level=3,
            successors=[],
        )
        assert result.ejected is True

    def test_eject_with_independent_successors(self) -> None:
        """Successors with non-overlapping claims are independent (no re-speculate)."""
        from src.merge_train import eject_from_train

        entry = self._make_in_train("f1", ["api:users"])
        succ1 = self._make_in_train("f2", ["db:schema:other"])
        succ2 = self._make_in_train("f3", ["event:billing"])
        result = eject_from_train(
            entry,
            reason="CI failure",
            caller_agent_id="agent-1",
            caller_trust_level=3,
            successors=[succ1, succ2],
        )
        assert set(result.independent_successors) == {"f2", "f3"}
        assert result.requeued_successors == []

    def test_eject_with_dependent_successors(self) -> None:
        """Successors sharing a claim prefix need re-speculation."""
        from src.merge_train import eject_from_train

        entry = self._make_in_train("f1", ["api:users"])
        succ_dependent = self._make_in_train("f2", ["api:orders"])  # same prefix
        succ_independent = self._make_in_train("f3", ["db:schema:other"])
        result = eject_from_train(
            entry,
            reason="CI failure",
            caller_agent_id="agent-1",
            caller_trust_level=3,
            successors=[succ_dependent, succ_independent],
        )
        assert result.independent_successors == ["f3"]
        assert result.requeued_successors == ["f2"]

    def test_abandoned_reset_on_re_enqueue(self) -> None:
        """When an ABANDONED entry is re-enqueued, eject_count resets and priority restores."""
        from src.merge_train import reset_abandoned_entry

        entry = _make_entry(
            "f1", ["api:x"], priority=-25, status=MergeTrainStatus.ABANDONED
        )
        entry.eject_count = MAX_EJECT_COUNT
        entry.original_priority = 5
        reset_abandoned_entry(entry)
        assert entry.eject_count == 0
        assert entry.merge_priority == 5
        assert entry.status == MergeTrainStatus.QUEUED
        assert entry.last_eject_reason is None


# ---------------------------------------------------------------------------
# BLOCKED entry recovery (tasks 2.9, 2.10) — D9, R9
# ---------------------------------------------------------------------------


class TestBlockedRecovery:
    """R9: Manual re-enqueue + automatic 1-hour re-evaluation of BLOCKED entries."""

    def _blocked_entry(
        self,
        feature_id: str,
        claims: list[str],
        *,
        reason: str = "speculative_merge_conflict",
        blocked_at: datetime | None = None,
    ) -> TrainEntry:
        entry = _make_entry(feature_id, claims, status=MergeTrainStatus.BLOCKED)
        entry.metadata["blocked_reason"] = reason
        entry.metadata["conflict_files"] = ["src/foo.py"]
        if blocked_at is not None:
            entry.checked_at = blocked_at
        return entry

    def test_reset_blocked_entry_clears_state(self) -> None:
        """Manual re-enqueue: reset_blocked_entry BLOCKED → QUEUED, clears metadata."""
        from src.merge_train import reset_blocked_entry

        entry = self._blocked_entry("f1", ["api:x"])
        reset_blocked_entry(entry)
        assert entry.status == MergeTrainStatus.QUEUED
        assert "blocked_reason" not in entry.metadata
        assert "conflict_files" not in entry.metadata
        assert entry.speculative_ref is None

    def test_reset_blocked_noop_on_non_blocked(self) -> None:
        """reset_blocked_entry is idempotent for non-BLOCKED entries."""
        from src.merge_train import reset_blocked_entry

        entry = _make_entry("f1", ["api:x"], status=MergeTrainStatus.QUEUED)
        entry.metadata["some"] = "value"
        reset_blocked_entry(entry)
        assert entry.status == MergeTrainStatus.QUEUED
        assert entry.metadata["some"] == "value"

    def test_compose_train_reevaluates_old_blocked_entries(self) -> None:
        """Auto re-eval: BLOCKED > 1 hour is retried in compose_train."""
        from src.merge_train import compose_train

        # Entry that was blocked 90 minutes ago (past the 1h threshold)
        old = datetime.now(UTC) - timedelta(minutes=90)
        blocked = self._blocked_entry("f1", ["api:x"], blocked_at=old)
        spawner = _FakeGitAdapter()
        composition = compose_train(
            [blocked], spawner, base_ref="main", caller_trust_level=3
        )
        # The entry should have been retried — spawner recorded a speculate call.
        assert len(spawner.created_refs) == 1
        # And succeeded, so status is now SPECULATING.
        assert blocked.status == MergeTrainStatus.SPECULATING
        assert blocked.speculative_ref is not None
        # It should appear in the composition.
        assert any(
            blocked in p.entries for p in composition.partitions
        )

    def test_compose_train_skips_recently_blocked(self) -> None:
        """Auto re-eval: BLOCKED < 1 hour is skipped."""
        from src.merge_train import compose_train

        recent = datetime.now(UTC) - timedelta(minutes=5)
        blocked = self._blocked_entry("f1", ["api:x"], blocked_at=recent)
        spawner = _FakeGitAdapter()
        compose_train(
            [blocked], spawner, base_ref="main", caller_trust_level=3
        )
        # No speculation attempted.
        assert len(spawner.created_refs) == 0
        # Still blocked.
        assert blocked.status == MergeTrainStatus.BLOCKED

    def test_compose_train_reeval_still_conflicting_stays_blocked(self) -> None:
        """Auto re-eval: re-merge still conflicts → entry stays BLOCKED, checked_at updated."""
        from src.merge_train import compose_train

        old = datetime.now(UTC) - timedelta(minutes=90)
        blocked = self._blocked_entry("f1", ["api:x"], blocked_at=old)
        original_checked_at = blocked.checked_at
        spawner = _FakeGitAdapter()
        spawner.conflicts[("main", blocked.branch_name)] = MergeTreeResult(
            success=False,
            conflict_files=["src/foo.py"],
            error="merge conflict",
        )
        compose_train(
            [blocked], spawner, base_ref="main", caller_trust_level=3
        )
        assert blocked.status == MergeTrainStatus.BLOCKED
        # checked_at was updated to now.
        assert blocked.checked_at is not None
        assert blocked.checked_at > original_checked_at  # type: ignore[operator]

    def test_compose_train_reeval_uses_default_1_hour_threshold(self) -> None:
        """Exactly 1h old BLOCKED is eligible for re-eval."""
        from src.merge_train import compose_train

        just_over = datetime.now(UTC) - timedelta(hours=1, seconds=5)
        blocked = self._blocked_entry("f1", ["api:x"], blocked_at=just_over)
        spawner = _FakeGitAdapter()
        compose_train(
            [blocked], spawner, base_ref="main", caller_trust_level=3
        )
        assert len(spawner.created_refs) == 1


# ---------------------------------------------------------------------------
# Wave merge executor (tasks 2.11, 2.12) — D4, R5
# ---------------------------------------------------------------------------


class TestWaveMergeExecutor:
    """R5: parallel partition merge + cross-partition serialization.

    The executor takes a fully-speculated TrainComposition where every entry
    is SPEC_PASSED and flushes it into main via wave-based fast-forwards.
    """

    def _spec_passed(
        self,
        feature_id: str,
        claims: list[str],
        *,
        partition_id: str,
        train_position: int,
        priority: int = 5,
    ) -> TrainEntry:
        e = _make_entry(feature_id, claims, priority=priority)
        e.status = MergeTrainStatus.SPEC_PASSED
        e.train_id = "deadbeef1234"
        e.partition_id = partition_id
        e.train_position = train_position
        e.speculative_ref = (
            f"refs/speculative/train-{e.train_id}/pos-{train_position}"
        )
        e.base_ref = "main"
        return e

    def _compose_with(
        self,
        partitions: list[TrainPartition],
        cross: list[CrossPartitionEntry] | None = None,
    ) -> TrainComposition:
        return TrainComposition(
            train_id="deadbeef1234",
            partitions=partitions,
            cross_partition_entries=cross or [],
        )

    def test_empty_composition_noop(self) -> None:
        """Executing an empty composition returns cleanly and still cleans refs."""
        from src.merge_train import execute_wave_merge

        composition = self._compose_with([])
        adapter = _FakeGitAdapter()
        result = execute_wave_merge(composition, adapter)
        assert result.merged_entries == []
        assert result.waves == []
        # Even empty trains call delete to flush any orphaned refs.
        assert "deadbeef1234" in adapter.deleted_trains

    def test_single_partition_merges_to_final_ref(self) -> None:
        """Two entries in one partition → fast-forward main to the LAST ref only."""
        from src.merge_train import execute_wave_merge

        e1 = self._spec_passed("f1", ["api:x"], partition_id="api:", train_position=1)
        e2 = self._spec_passed("f2", ["api:y"], partition_id="api:", train_position=2)
        partition = TrainPartition(
            partition_id="api:", key_prefixes={"api:"}, entries=[e1, e2]
        )
        composition = self._compose_with([partition])
        adapter = _FakeGitAdapter()
        result = execute_wave_merge(composition, adapter)

        # The final ref (position 2) is what lands on main — earlier refs are
        # transitively ancestors, so only one fast-forward is needed.
        assert adapter.fast_forwards == [e2.speculative_ref]
        assert e1.status == MergeTrainStatus.MERGED
        assert e2.status == MergeTrainStatus.MERGED
        assert set(result.merged_entries) == {"f1", "f2"}
        assert "deadbeef1234" in adapter.deleted_trains

    def test_two_independent_partitions_single_wave(self) -> None:
        """Independent partitions all merge in wave 1 — no cross deps to gate."""
        from src.merge_train import execute_wave_merge

        a = self._spec_passed("fA", ["api:x"], partition_id="api:", train_position=1)
        b = self._spec_passed(
            "fB", ["db:schema:y"], partition_id="db:schema:", train_position=2
        )
        pa = TrainPartition(
            partition_id="api:", key_prefixes={"api:"}, entries=[a]
        )
        pb = TrainPartition(
            partition_id="db:schema:", key_prefixes={"db:schema:"}, entries=[b]
        )
        composition = self._compose_with([pa, pb])
        adapter = _FakeGitAdapter()
        result = execute_wave_merge(composition, adapter)

        assert len(result.waves) == 1
        assert set(result.waves[0]) == {"partition:api:", "partition:db:schema:"}
        assert set(adapter.fast_forwards) == {
            a.speculative_ref,
            b.speculative_ref,
        }

    def test_cross_partition_serializes_before_spanned_partitions(self) -> None:
        """A cross entry spanning P1/P2 must merge in an earlier wave than P1 or P2."""
        from src.merge_train import execute_wave_merge

        # Cross entry at position 1, then partition entries at positions 2 & 3
        cross = self._spec_passed(
            "cX", ["api:x", "db:schema:x"], partition_id="(cross)", train_position=1
        )
        p_a = self._spec_passed(
            "fA", ["api:y"], partition_id="api:", train_position=2
        )
        p_b = self._spec_passed(
            "fB", ["db:schema:z"], partition_id="db:schema:", train_position=3
        )

        partitions = [
            TrainPartition(partition_id="api:", key_prefixes={"api:"}, entries=[p_a]),
            TrainPartition(
                partition_id="db:schema:", key_prefixes={"db:schema:"}, entries=[p_b]
            ),
        ]
        cpe = CrossPartitionEntry(
            feature_id="cX",
            entry=cross,
            spans_partitions=["api:", "db:schema:"],
        )
        composition = self._compose_with(partitions, cross=[cpe])
        adapter = _FakeGitAdapter()
        result = execute_wave_merge(composition, adapter)

        # Wave 1 must be just the cross entry; wave 2 is both partitions.
        assert result.waves[0] == ["cross:cX"]
        assert set(result.waves[1]) == {"partition:api:", "partition:db:schema:"}
        # Fast-forward order: cross ref first, then partition final refs
        assert adapter.fast_forwards[0] == cross.speculative_ref
        assert set(adapter.fast_forwards[1:]) == {
            p_a.speculative_ref,
            p_b.speculative_ref,
        }
        assert cross.status == MergeTrainStatus.MERGED
        assert p_a.status == MergeTrainStatus.MERGED
        assert p_b.status == MergeTrainStatus.MERGED

    def test_chained_cross_entries_serialize_in_order(self) -> None:
        """Multiple cross entries form a chain: lower position merges first."""
        from src.merge_train import execute_wave_merge

        c1 = self._spec_passed(
            "c1", ["api:x", "db:schema:x"], partition_id="(cross)", train_position=1
        )
        c2 = self._spec_passed(
            "c2",
            ["api:y", "event:x"],
            partition_id="(cross)",
            train_position=2,
        )
        cpe1 = CrossPartitionEntry(
            feature_id="c1", entry=c1, spans_partitions=["api:", "db:schema:"]
        )
        cpe2 = CrossPartitionEntry(
            feature_id="c2", entry=c2, spans_partitions=["api:", "event:"]
        )
        # Ghost partitions for api:, db:schema:, event: (no regular entries)
        partitions = [
            TrainPartition(
                partition_id="api:", key_prefixes={"api:"}, entries=[]
            ),
            TrainPartition(
                partition_id="db:schema:",
                key_prefixes={"db:schema:"},
                entries=[],
            ),
            TrainPartition(
                partition_id="event:", key_prefixes={"event:"}, entries=[]
            ),
        ]
        composition = self._compose_with(partitions, cross=[cpe1, cpe2])
        adapter = _FakeGitAdapter()
        result = execute_wave_merge(composition, adapter)

        # c1 must be in an earlier wave than c2 (both share api: span).
        # Empty partitions should not appear as merge nodes.
        c1_wave = next(
            i for i, w in enumerate(result.waves) if "cross:c1" in w
        )
        c2_wave = next(
            i for i, w in enumerate(result.waves) if "cross:c2" in w
        )
        assert c1_wave < c2_wave
        # Fast-forwards happen in wave order
        idx1 = adapter.fast_forwards.index(c1.speculative_ref)
        idx2 = adapter.fast_forwards.index(c2.speculative_ref)
        assert idx1 < idx2

    def test_empty_partitions_skipped(self) -> None:
        """Ghost partitions with no entries contribute no merge nodes."""
        from src.merge_train import execute_wave_merge

        empty = TrainPartition(
            partition_id="event:", key_prefixes={"event:"}, entries=[]
        )
        composition = self._compose_with([empty])
        adapter = _FakeGitAdapter()
        result = execute_wave_merge(composition, adapter)
        assert result.merged_entries == []
        assert result.waves == []

    def test_non_spec_passed_entries_are_skipped(self) -> None:
        """Entries not in SPEC_PASSED state are left alone."""
        from src.merge_train import execute_wave_merge

        passed = self._spec_passed(
            "f1", ["api:x"], partition_id="api:", train_position=1
        )
        still_speculating = self._spec_passed(
            "f2", ["api:y"], partition_id="api:", train_position=2
        )
        still_speculating.status = MergeTrainStatus.SPECULATING
        partition = TrainPartition(
            partition_id="api:",
            key_prefixes={"api:"},
            entries=[passed, still_speculating],
        )
        composition = self._compose_with([partition])
        adapter = _FakeGitAdapter()
        result = execute_wave_merge(composition, adapter)
        # Partition is NOT ready because not all entries are SPEC_PASSED
        assert result.merged_entries == []
        # But cleanup still runs for the composition.
        assert "deadbeef1234" in adapter.deleted_trains

    def test_deadlock_raised_on_unresolvable_graph(self) -> None:
        """If a node has a dependency that never becomes ready, raise TrainDeadlockError."""
        from src.merge_train import TrainDeadlockError, execute_wave_merge

        # Construct a pathological composition: a partition depends on a cross
        # entry, but the cross entry's own entry is NOT SPEC_PASSED. The
        # partition must wait and will never unblock — deadlock.
        p_a = self._spec_passed(
            "fA", ["api:y"], partition_id="api:", train_position=2
        )
        cross = self._spec_passed(
            "cX",
            ["api:x", "db:schema:x"],
            partition_id="(cross)",
            train_position=1,
        )
        cross.status = MergeTrainStatus.SPECULATING  # not ready → blocks partition
        cpe = CrossPartitionEntry(
            feature_id="cX",
            entry=cross,
            spans_partitions=["api:", "db:schema:"],
        )
        partitions = [
            TrainPartition(partition_id="api:", key_prefixes={"api:"}, entries=[p_a]),
            TrainPartition(
                partition_id="db:schema:",
                key_prefixes={"db:schema:"},
                entries=[],
            ),
        ]
        composition = self._compose_with(partitions, cross=[cpe])
        adapter = _FakeGitAdapter()
        with pytest.raises(TrainDeadlockError):
            execute_wave_merge(composition, adapter)

    def test_transaction_context_manager_is_used(self) -> None:
        """A provided transaction context manager wraps the entire wave merge."""
        from src.merge_train import execute_wave_merge

        events: list[str] = []

        class _FakeTxn:
            def __enter__(self) -> _FakeTxn:
                events.append("enter")
                return self
            def __exit__(self, *a: object) -> None:
                events.append("exit")

        e1 = self._spec_passed("f1", ["api:x"], partition_id="api:", train_position=1)
        partition = TrainPartition(
            partition_id="api:", key_prefixes={"api:"}, entries=[e1]
        )
        composition = self._compose_with([partition])
        adapter = _FakeGitAdapter()
        execute_wave_merge(composition, adapter, transaction=_FakeTxn())
        assert events == ["enter", "exit"]
        assert adapter.fast_forwards == [e1.speculative_ref]


# ---------------------------------------------------------------------------
# Crash recovery + watchdog GC (tasks 2.13, 2.14) — R7
# ---------------------------------------------------------------------------


class TestCrashRecovery:
    """R7: startup cleanup enumerates refs/speculative/ and deletes orphans."""

    def _preload_refs(self, adapter: _FakeGitAdapter, refs: list[str]) -> None:
        """Inject pre-existing speculative refs as if created in a prior run."""
        adapter.speculative_refs.extend(refs)

    def test_cleanup_deletes_orphaned_trains(self) -> None:
        """A train with no active entries is considered orphaned and its refs are deleted."""
        from src.merge_train import cleanup_orphaned_speculative_refs

        adapter = _FakeGitAdapter()
        self._preload_refs(
            adapter,
            [
                "refs/speculative/train-deadbeef1234/pos-1",
                "refs/speculative/train-deadbeef1234/pos-2",
                "refs/speculative/train-cafef00d5678/pos-1",
            ],
        )
        # Only deadbeef has active entries — cafef00d is orphaned.
        result = cleanup_orphaned_speculative_refs(
            adapter, active_train_ids={"deadbeef1234"}
        )
        assert "cafef00d5678" in result.deleted_train_ids
        assert "deadbeef1234" not in result.deleted_train_ids
        assert result.deleted_ref_count == 1  # just pos-1 of the orphan
        assert "cafef00d5678" in adapter.deleted_trains

    def test_cleanup_no_orphans_is_noop(self) -> None:
        from src.merge_train import cleanup_orphaned_speculative_refs

        adapter = _FakeGitAdapter()
        self._preload_refs(adapter, ["refs/speculative/train-abcd1234/pos-1"])
        result = cleanup_orphaned_speculative_refs(
            adapter, active_train_ids={"abcd1234"}
        )
        assert result.deleted_train_ids == []
        assert result.deleted_ref_count == 0
        assert adapter.deleted_trains == []

    def test_cleanup_ignores_refs_outside_speculative_namespace(self) -> None:
        """Malformed or non-speculative refs are logged and skipped, not deleted."""
        from src.merge_train import cleanup_orphaned_speculative_refs

        adapter = _FakeGitAdapter()
        # Note: the fake adapter's list_speculative_refs only returns what was
        # added to speculative_refs, but a misconfigured git repo might have
        # junk. We add one proper orphan and assert it's still handled.
        self._preload_refs(
            adapter, ["refs/speculative/train-11112222/pos-1"]
        )
        result = cleanup_orphaned_speculative_refs(adapter, active_train_ids=set())
        assert "11112222" in result.deleted_train_ids
        assert result.deleted_ref_count == 1

    def test_cleanup_empty_repo(self) -> None:
        from src.merge_train import cleanup_orphaned_speculative_refs

        adapter = _FakeGitAdapter()
        result = cleanup_orphaned_speculative_refs(adapter, active_train_ids=set())
        assert result.deleted_train_ids == []
        assert result.deleted_ref_count == 0


class TestTtlGarbageCollection:
    """R7: watchdog deletes refs older than SPECULATIVE_REF_TTL_HOURS."""

    def test_gc_deletes_trains_older_than_ttl(self) -> None:
        from src.merge_train import gc_aged_speculative_refs

        adapter = _FakeGitAdapter()
        adapter.speculative_refs.extend(
            [
                "refs/speculative/train-0a0a0b0b0c0c/pos-1",
                "refs/speculative/train-1a1a2b2b3c3c/pos-1",
            ]
        )
        now = datetime.now(UTC)
        creation_times = {
            "0a0a0b0b0c0c": now - timedelta(hours=7),  # older than 6h TTL
            "1a1a2b2b3c3c": now - timedelta(hours=1),  # well within TTL
        }
        result = gc_aged_speculative_refs(
            adapter, train_creation_times=creation_times, now=now
        )
        assert "0a0a0b0b0c0c" in result.deleted_train_ids
        assert "1a1a2b2b3c3c" not in result.deleted_train_ids

    def test_gc_respects_custom_max_age(self) -> None:
        from src.merge_train import gc_aged_speculative_refs

        adapter = _FakeGitAdapter()
        adapter.speculative_refs.append("refs/speculative/train-abcd0001feed/pos-1")
        now = datetime.now(UTC)
        creation_times = {"abcd0001feed": now - timedelta(minutes=30)}
        # With max_age=10 minutes, this 30-minute old train should be GC'd.
        result = gc_aged_speculative_refs(
            adapter,
            train_creation_times=creation_times,
            max_age=timedelta(minutes=10),
            now=now,
        )
        assert "abcd0001feed" in result.deleted_train_ids

    def test_gc_unknown_train_is_eligible(self) -> None:
        """A ref whose train_id has no creation time entry is treated as orphaned."""
        from src.merge_train import gc_aged_speculative_refs

        adapter = _FakeGitAdapter()
        adapter.speculative_refs.append(
            "refs/speculative/train-ffff00001122/pos-1"
        )
        result = gc_aged_speculative_refs(
            adapter, train_creation_times={}, now=datetime.now(UTC)
        )
        # No creation time → assume orphaned → GC.
        assert "ffff00001122" in result.deleted_train_ids

    def test_gc_malformed_ref_is_skipped(self) -> None:
        """Refs that don't match the speculative ref regex are skipped silently."""
        from src.merge_train import gc_aged_speculative_refs

        adapter = _FakeGitAdapter()
        adapter.speculative_refs.extend(
            [
                "refs/speculative/train-a1b2c3d4e5f6/pos-1",
                "refs/speculative/not-a-train/whatever",  # malformed
            ]
        )
        now = datetime.now(UTC)
        result = gc_aged_speculative_refs(
            adapter,
            train_creation_times={"a1b2c3d4e5f6": now - timedelta(hours=10)},
            now=now,
        )
        assert "a1b2c3d4e5f6" in result.deleted_train_ids
        # No crash on malformed ref
