"""Speculative merge train engine.

This module contains the train engine proper — the scheduling brain that sits
on top of ``merge_queue.py``. It is intentionally stateless at the module
level: persistence is delegated to the feature registry (D1) and git is
abstracted by ``git_adapter.GitAdapter``.

Responsibilities (by task, one step at a time as the engine is built out):

    2.2 compute_partitions(entries) → PartitionResult
        Group queued entries into partitions via lock-key prefix grouping.
        Detect cross-partition entries and dependency cycles.
    2.4 compose_train() → TrainComposition
        Compose a fresh train, assign positions, spawn speculative refs.
    2.6 validate_post_speculation_claims() → list[TrainEntry]
        Verify each speculative ref's actual changes match the declared
        resource claims (D8 post-speculation check).
    2.8 eject_from_train() → EjectResult
        Remove a failed entry, decrement priority, flag independent
        successors, transition to ABANDONED at MAX_EJECT_COUNT (D12).
    2.10 BLOCKED entry recovery (manual + 1-hour auto).
    2.12 merge_partition() wave executor.
    2.14 crash recovery / watchdog GC.

Design references:
  - ``docs/lock-key-namespaces.md`` — the nine lock key prefixes this
    module partitions against.
  - ``openspec/changes/speculative-merge-trains/design.md`` D2, D4, D8-D12.
  - ``contracts/internal/merge-train-api.yaml`` — canonical method contracts.
"""

from __future__ import annotations

import logging
import re
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .git_adapter import SPECULATIVE_REF_TTL_HOURS, GitAdapter, MergeTreeResult
from .merge_train_types import (
    EJECT_PRIORITY_DECREMENT,
    MAX_EJECT_COUNT,
    CrossPartitionEntry,
    MergeTrainStatus,
    TrainComposition,
    TrainEntry,
    TrainPartition,
    claim_prefix,
    file_path_to_namespaces,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authorization (R6)
# ---------------------------------------------------------------------------

#: Minimum caller trust level to compose a train or query its status.
MIN_COMPOSE_TRUST_LEVEL: int = 3

#: How long a BLOCKED entry must sit before compose_train re-evaluates it (D9).
#: After this window the entry is retried in case preceding merges resolved
#: whatever conflict put it there.
BLOCKED_REEVAL_INTERVAL: timedelta = timedelta(hours=1)


class TrainAuthorizationError(PermissionError):
    """Raised when a caller attempts a train operation without sufficient trust.

    compose_train / get_train_status require trust level >= 3.
    eject_from_train requires trust level >= 3 OR feature ownership.
    """


class TrainDeadlockError(RuntimeError):
    """Raised when the wave-merge executor finds no runnable nodes (D4).

    Indicates a dependency cycle in the train composition that cannot be
    resolved in-band. Callers handle this by logging and aborting the
    current compose/merge attempt; the train recovers on the next sweep.
    """


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PartitionResult:
    """Output of :func:`compute_partitions`.

    Contains the partitions (each an independent sub-train), the cross-partition
    entries (spanning multiple prefixes), and any cycles detected in the
    cross-partition dependency graph. Cycles are *informational* — the train
    engine still partitions the entries, but logs a warning and may choose to
    serialize cyclic groups via the wave-merge executor (task 2.12).
    """

    partitions: list[TrainPartition] = field(default_factory=list)
    cross_partition_entries: list[CrossPartitionEntry] = field(default_factory=list)
    #: List of cycles, each a sorted list of feature_ids participating in the
    #: cycle. Empty when the cross-partition graph is acyclic.
    cycles: list[list[str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Partition computation (tasks 2.1, 2.2)
# ---------------------------------------------------------------------------


def _entry_prefix_set(entry: TrainEntry) -> set[str]:
    """Return the set of partition keys an entry belongs to.

    For each ``resource_claim`` we compute its logical prefix via
    :func:`claim_prefix`. Claims with no logical prefix (file-path locks)
    fall back to the full claim string so that two entries claiming the
    same file land in the same "pseudo-partition" keyed by the file path.

    The resulting set size drives partitioning:

        - ``|set| == 0`` → no claims, placed in the ``"(unclaimed)"`` bucket
        - ``|set| == 1`` → regular single-partition member
        - ``|set| >= 2`` → cross-partition entry spanning each prefix
    """
    prefixes: set[str] = set()
    for claim in entry.resource_claims:
        prefix = claim_prefix(claim)
        # File-path locks (no ":" in the claim) get their full claim as a
        # partition id so that overlapping file paths still converge.
        prefixes.add(prefix if prefix else claim)
    return prefixes


def _find_cycles_in_cross_partition_graph(
    cross_entries: list[CrossPartitionEntry],
) -> list[list[str]]:
    """Detect cycles in the undirected cross-partition hypergraph.

    The graph has one node per partition and one hyperedge per cross-partition
    entry. A cycle exists when removing any single hyperedge leaves the
    remaining entries' partitions still connected through each other — i.e.,
    two or more cross-partition entries form a ring over the same partitions.

    Algorithm: build a multigraph where nodes are partition ids and each
    cross-partition entry contributes edges between consecutive partitions in
    its spans. Run DFS with a back-edge check. On a back-edge, reconstruct
    the cycle by walking the parent chain.

    The returned list contains each cycle as a sorted list of feature ids.
    """
    if len(cross_entries) < 2:
        return []

    # Build adjacency: partition_id → list of (neighbor_partition_id, entry_feature_id, edge_index)
    # Each cross-partition entry connects every pair of its spanned partitions.
    adjacency: dict[str, list[tuple[str, str, int]]] = {}
    edges_by_index: list[tuple[str, str, str]] = []  # (partition_a, partition_b, feature_id)
    for cpe in cross_entries:
        spans = cpe.spans_partitions
        for i in range(len(spans)):
            for j in range(i + 1, len(spans)):
                a, b = spans[i], spans[j]
                edge_idx = len(edges_by_index)
                edges_by_index.append((a, b, cpe.feature_id))
                adjacency.setdefault(a, []).append((b, cpe.feature_id, edge_idx))
                adjacency.setdefault(b, []).append((a, cpe.feature_id, edge_idx))

    # DFS to detect cycles. A cycle requires ≥2 distinct cross-partition entries.
    cycles: list[list[str]] = []
    seen_cycles: set[frozenset[str]] = set()
    visited: set[str] = set()

    def _dfs(node: str, parent_edge: int | None, path_edges: list[int]) -> None:
        visited.add(node)
        for neighbor, feature_id, edge_idx in adjacency.get(node, []):
            if edge_idx == parent_edge:
                continue  # don't traverse back through the edge we came on
            if edge_idx in path_edges:
                continue  # same edge already in current path
            if neighbor in visited and neighbor in _path_nodes:
                # Back edge → cycle found. Reconstruct the feature ids on the cycle.
                cycle_feature_ids: set[str] = {feature_id}
                # Walk the path edges in reverse to collect features until we
                # find the edge that closes the cycle.
                for idx in reversed(path_edges):
                    edge_a, edge_b, edge_feature = edges_by_index[idx]
                    cycle_feature_ids.add(edge_feature)
                    if edge_a == neighbor or edge_b == neighbor:
                        break
                if len(cycle_feature_ids) >= 2:
                    fs = frozenset(cycle_feature_ids)
                    if fs not in seen_cycles:
                        seen_cycles.add(fs)
                        cycles.append(sorted(cycle_feature_ids))
            elif neighbor not in visited:
                _path_nodes.add(neighbor)
                _dfs(neighbor, edge_idx, path_edges + [edge_idx])
                _path_nodes.discard(neighbor)

    _path_nodes: set[str] = set()
    for start in list(adjacency.keys()):
        if start not in visited:
            _path_nodes = {start}
            _dfs(start, None, [])

    return cycles


def compute_partitions(entries: list[TrainEntry]) -> PartitionResult:
    """Group train entries into partitions based on lock-key prefix overlap (D2).

    Algorithm (O(N·P) where P = max claims per entry):

      1. For each entry, compute its set of partition keys (claim prefixes,
         or full claim for file-path locks).
      2. Entries with exactly one key land in a ``TrainPartition`` keyed by
         that prefix.
      3. Entries with two or more keys become ``CrossPartitionEntry`` objects,
         spanning each of those prefixes. "Ghost" ``TrainPartition`` objects
         are created for any prefix that has no single-prefix entries but is
         spanned by a cross-partition entry — the wave merge executor in
         task 2.12 needs every spanned partition to exist.
      4. Cross-partition entries are analyzed for cycles in an undirected
         hypergraph (partitions = nodes, cross-partition entries = hyperedges).
         Cycles are surfaced via :attr:`PartitionResult.cycles` with a warning
         log; the caller decides whether to serialize the cycle group.

    Determinism: partitions are returned sorted by ``partition_id`` and
    cross-partition entries by ``feature_id``. This makes tests stable and
    simplifies debugging.
    """
    if not entries:
        return PartitionResult()

    partitions: dict[str, TrainPartition] = {}
    cross_entries: list[CrossPartitionEntry] = []

    for entry in entries:
        prefix_set = _entry_prefix_set(entry)

        if not prefix_set:
            # Degenerate entry with no claims — park it in a special bucket.
            # The wave merge executor can choose to merge these independently.
            bucket_id = "(unclaimed)"
            bucket = partitions.setdefault(bucket_id, TrainPartition(partition_id=bucket_id))
            bucket.key_prefixes.add(bucket_id)
            bucket.entries.append(entry)
            continue

        if len(prefix_set) == 1:
            prefix = next(iter(prefix_set))
            partition = partitions.setdefault(prefix, TrainPartition(partition_id=prefix))
            partition.key_prefixes.add(prefix)
            partition.entries.append(entry)
            continue

        # Cross-partition entry — ensure each spanned partition exists (ghost-ok).
        spans = sorted(prefix_set)
        for prefix in spans:
            ghost = partitions.setdefault(prefix, TrainPartition(partition_id=prefix))
            ghost.key_prefixes.add(prefix)
        cross_entries.append(
            CrossPartitionEntry(
                feature_id=entry.feature_id,
                entry=entry,
                spans_partitions=spans,
            )
        )

    cycles = _find_cycles_in_cross_partition_graph(cross_entries)
    if cycles:
        logger.warning(
            "compute_partitions: cross-partition cycle detected among %d feature(s): %s",
            sum(len(c) for c in cycles),
            cycles,
        )

    result = PartitionResult(
        partitions=sorted(partitions.values(), key=lambda p: p.partition_id),
        cross_partition_entries=sorted(cross_entries, key=lambda cpe: cpe.feature_id),
        cycles=cycles,
    )
    return result


# ---------------------------------------------------------------------------
# compose_train (tasks 2.3, 2.4)
# ---------------------------------------------------------------------------


def _speculative_ref_name(train_id: str, position: int) -> str:
    """Build a speculative ref name that satisfies the R7 regex."""
    return f"refs/speculative/train-{train_id}/pos-{position}"


def _sort_entries_by_priority(entries: list[TrainEntry]) -> list[TrainEntry]:
    """Descending priority, with stable tie-break on feature_id."""
    return sorted(entries, key=lambda e: (-e.merge_priority, e.feature_id))


def _handle_conflict(entry: TrainEntry, merge_result: MergeTreeResult) -> None:
    """Mutate *entry* in-place to reflect a speculative merge conflict (R11).

    Also bumps ``checked_at`` so the 1-hour re-eval timer (R9) starts fresh
    from *this* conflict — repeated re-evals don't spam git operations.
    """
    entry.status = MergeTrainStatus.BLOCKED
    entry.speculative_ref = None
    entry.metadata["conflict_files"] = list(merge_result.conflict_files)
    entry.metadata["blocked_reason"] = "speculative_merge_conflict"
    entry.last_eject_reason = "speculative_merge_conflict"
    entry.checked_at = datetime.now(UTC)


def _handle_speculative_success(
    entry: TrainEntry,
    merge_result: MergeTreeResult,
    *,
    train_id: str,
    partition_id: str,
    train_position: int,
    base_ref: str,
    ref_name: str,
) -> None:
    """Mutate *entry* in-place to reflect a successful speculation."""
    entry.status = MergeTrainStatus.SPECULATING
    entry.train_id = train_id
    entry.partition_id = partition_id
    entry.train_position = train_position
    entry.base_ref = base_ref
    entry.speculative_ref = ref_name
    entry.metadata["tree_oid"] = merge_result.tree_oid
    entry.metadata["commit_sha"] = merge_result.commit_sha


def compose_train(
    entries: list[TrainEntry],
    git_adapter: GitAdapter,
    *,
    base_ref: str = "main",
    caller_trust_level: int = 3,
    force_recompose: bool = False,
) -> TrainComposition:
    """Compose a fresh merge train from queued entries (R1, R6, R11).

    Algorithm:

      1. **Authorization** (R6) — caller trust level must be >= 3.
      2. **Partition computation** — delegates to :func:`compute_partitions`.
      3. **Cross-partition entries first** — each gets its own speculative ref
         chained on top of ``base_ref``. This ensures that any regular entry
         in a spanned partition can use the cross-partition entry's ref as
         its base (per the R1 scenario).
      4. **Regular partitions** — within each partition, sort entries by
         ``(priority desc, feature_id asc)`` and chain speculative refs: each
         position's base is the prior position's ref (or the cross-partition
         entry ref if the partition is spanned, or ``base_ref`` otherwise).
      5. **Conflict handling** (R11) — any conflict transitions the offending
         entry to ``BLOCKED`` *without* affecting subsequent entries in
         independent partitions. The conflict file list is stored in the
         entry's metadata.

    Tree caching (task 2.4): an in-call ``(base_ref, feature_branch)``
    cache avoids redundant ``create_speculative_ref`` calls within one
    compose_train. A persistent cache across calls is deferred to the
    git adapter layer.

    Args:
        entries: The queued entries to compose. Terminal entries (MERGED,
            ABANDONED) are skipped silently.
        git_adapter: Injected git abstraction used to create speculative refs.
        base_ref: The starting ref for the train (typically ``main``).
        caller_trust_level: The calling agent's trust level; must be >= 3.
        force_recompose: If True, recompose even if an existing train matches
            the input. Currently a no-op placeholder — v1 always recomposes.

    Returns:
        A :class:`TrainComposition` with all positions assigned and any
        conflicts reflected in entry statuses.

    Raises:
        TrainAuthorizationError: if ``caller_trust_level < 3``.
    """
    if caller_trust_level < MIN_COMPOSE_TRUST_LEVEL:
        raise TrainAuthorizationError(
            f"compose_train requires trust level >= {MIN_COMPOSE_TRUST_LEVEL}, "
            f"got {caller_trust_level}"
        )

    # R9/D9: auto re-evaluate BLOCKED entries that have aged past the threshold.
    # We promote them in-place back to QUEUED so the existing pipeline retries
    # them. Recent conflicts skip this — they'd just reproduce the same error.
    now = datetime.now(UTC)
    for entry in entries:
        if entry.status != MergeTrainStatus.BLOCKED:
            continue
        if entry.checked_at is None:
            # Unknown age — treat as eligible (legacy rows missing the field).
            aged = True
        else:
            # Handle naive datetimes defensively by assuming UTC.
            ts = (
                entry.checked_at
                if entry.checked_at.tzinfo is not None
                else entry.checked_at.replace(tzinfo=UTC)
            )
            aged = (now - ts) >= BLOCKED_REEVAL_INTERVAL
        if aged:
            logger.info(
                "compose_train: re-evaluating BLOCKED entry %s "
                "(blocked since %s)",
                entry.feature_id,
                entry.checked_at,
            )
            entry.status = MergeTrainStatus.QUEUED
            # Drop the prior blocked metadata — if the retry re-conflicts,
            # _handle_conflict repopulates it.
            entry.metadata.pop("blocked_reason", None)
            entry.metadata.pop("conflict_files", None)

    # Skip terminal entries (MERGED, ABANDONED) AND entries still BLOCKED.
    active_entries = [
        e
        for e in entries
        if not e.is_terminal() and e.status != MergeTrainStatus.BLOCKED
    ]
    if not active_entries:
        logger.info("compose_train: no active entries to compose")
        return TrainComposition(train_id=TrainComposition.new_train_id())

    partition_result = compute_partitions(active_entries)
    train_id = TrainComposition.new_train_id()
    composition = TrainComposition(
        train_id=train_id,
        partitions=partition_result.partitions,
        cross_partition_entries=partition_result.cross_partition_entries,
    )

    # In-call tree cache (task 2.4). Keyed by (base_ref, feature_branch).
    tree_cache: dict[tuple[str, str | None], MergeTreeResult] = {}

    def _speculate(
        entry: TrainEntry, base: str, position: int
    ) -> MergeTreeResult:
        """Call the git adapter with caching; falls through on cache miss."""
        cache_key = (base, entry.branch_name)
        if not force_recompose and cache_key in tree_cache:
            logger.debug(
                "compose_train: reusing cached merge result for %s", cache_key
            )
            return tree_cache[cache_key]
        ref_name = _speculative_ref_name(train_id, position)
        if entry.branch_name is None:
            raise ValueError(
                f"entry {entry.feature_id} has no branch_name; "
                "cannot create speculative ref"
            )
        result = git_adapter.create_speculative_ref(base, entry.branch_name, ref_name)
        tree_cache[cache_key] = result
        return result

    # Position counter is global across the train so ref names remain unique.
    position_counter = 0

    # ── Stage 1: cross-partition entries chain on top of base_ref ─────────
    sorted_cross = _sort_entries_by_priority(
        [cpe.entry for cpe in partition_result.cross_partition_entries]
    )
    cross_base = base_ref
    for cross_entry in sorted_cross:
        position_counter += 1
        result = _speculate(cross_entry, cross_base, position_counter)
        if not result.success:
            _handle_conflict(cross_entry, result)
            # On conflict, subsequent cross-partition entries continue from
            # the last successful base (the one that failed is skipped).
            continue
        _handle_speculative_success(
            cross_entry,
            result,
            train_id=train_id,
            partition_id="(cross)",
            train_position=position_counter,
            base_ref=cross_base,
            ref_name=_speculative_ref_name(train_id, position_counter),
        )
        cross_base = _speculative_ref_name(train_id, position_counter)

    # Track, per partition, the latest ref introduced by a cross-partition
    # entry so regular-partition entries can build on top of it.
    spanned_partition_base: dict[str, str] = {}
    for cpe in partition_result.cross_partition_entries:
        if cpe.entry.speculative_ref is None:
            continue
        for spanned in cpe.spans_partitions:
            spanned_partition_base[spanned] = cpe.entry.speculative_ref

    # ── Stage 2: regular partitions ───────────────────────────────────────
    for partition in composition.partitions:
        sorted_entries = _sort_entries_by_priority(partition.entries)
        # Start each partition from its cross-partition head if any.
        current_base = spanned_partition_base.get(partition.partition_id, base_ref)
        prior_position_counter = position_counter
        for idx, entry in enumerate(sorted_entries):
            position_counter += 1
            result = _speculate(entry, current_base, position_counter)
            if not result.success:
                _handle_conflict(entry, result)
                # Do NOT advance current_base on conflict — subsequent entries
                # in this partition build from the same base (the last
                # successful one). This is simpler than gap-filling.
                continue
            _handle_speculative_success(
                entry,
                result,
                train_id=train_id,
                partition_id=partition.partition_id,
                train_position=position_counter,
                base_ref=current_base,
                ref_name=_speculative_ref_name(train_id, position_counter),
            )
            current_base = _speculative_ref_name(train_id, position_counter)
        if prior_position_counter == position_counter:
            logger.debug(
                "compose_train: partition %s produced no new refs",
                partition.partition_id,
            )

    logger.info(
        "compose_train: id=%s partitions=%d cross=%d positions=%d",
        train_id,
        len(composition.partitions),
        len(composition.cross_partition_entries),
        position_counter,
    )
    return composition


# ---------------------------------------------------------------------------
# Post-speculation claim validation (tasks 2.5, 2.6) — D8, R8
# ---------------------------------------------------------------------------


def _declared_namespaces(entry: TrainEntry) -> set[str]:
    """Return the set of namespace prefixes an entry has declared in its claims."""
    declared: set[str] = set()
    for claim in entry.resource_claims:
        prefix = claim_prefix(claim)
        if prefix:
            declared.add(prefix)
    return declared


def validate_post_speculation_claims(
    entries: list[TrainEntry],
    git_adapter: GitAdapter,
) -> list[TrainEntry]:
    """Verify that actual file changes match declared resource claims (D8, R8).

    After a speculative ref is created, an entry's declared resource claims
    are a PROMISE about which namespaces the change will touch. This function
    cashes the promise by asking the git adapter for the actual changed file
    list and comparing against the declared namespaces.

    A mismatch means the agent was wrong about its scope — the entry is
    transitioned to BLOCKED (not EJECTED) with a detailed reason, so the
    owner can update the claims and re-enqueue. Entries with no speculative
    ref (QUEUED, BLOCKED already, or ABANDONED) are skipped.

    Heuristic semantics (D8): files that don't map to any namespace (e.g.,
    ``README.md``) are OUT OF SCOPE for validation. They can't contradict
    the claim because the heuristic doesn't know how to classify them.
    File-level locks handle these separately.

    Args:
        entries: train entries to validate. Only entries in ``SPECULATING`` or
            with a ``speculative_ref`` set are considered.
        git_adapter: used to read actual changed files per speculative ref.

    Returns:
        The list of entries that FAILED validation (now in ``BLOCKED`` state).
    """
    newly_blocked: list[TrainEntry] = []
    for entry in entries:
        if entry.speculative_ref is None or entry.status != MergeTrainStatus.SPECULATING:
            continue
        base_ref = entry.base_ref or "main"
        changed = git_adapter.get_changed_files(base_ref, entry.speculative_ref)
        actual_namespaces: set[str] = set()
        for path in changed.changed_files:
            actual_namespaces.update(file_path_to_namespaces(path))

        declared = _declared_namespaces(entry)
        extra = actual_namespaces - declared
        if extra:
            reason = (
                f"claim mismatch: actual changes span namespaces "
                f"{sorted(extra)} not declared in resource_claims"
            )
            entry.status = MergeTrainStatus.BLOCKED
            entry.metadata["blocked_reason"] = reason
            entry.metadata["actual_namespaces"] = sorted(actual_namespaces)
            entry.metadata["declared_namespaces"] = sorted(declared)
            logger.warning(
                "validate_post_speculation_claims: %s BLOCKED — %s",
                entry.feature_id,
                reason,
            )
            newly_blocked.append(entry)
    return newly_blocked


# ---------------------------------------------------------------------------
# eject_from_train (tasks 2.7, 2.8) — D12, R14
# ---------------------------------------------------------------------------


@dataclass
class EjectResult:
    """Outcome of an :func:`eject_from_train` call.

    - ``ejected`` is always ``True`` on success (failure raises).
    - ``priority_after`` reflects the post-decrement priority, or the unchanged
      priority if the entry transitioned to ABANDONED.
    - ``abandoned`` is ``True`` when this ejection crossed MAX_EJECT_COUNT.
    - ``independent_successors`` lists feature_ids whose claims are fully
      disjoint from the ejected entry's claims — these can keep their
      speculative refs (they merge normally).
    - ``requeued_successors`` lists feature_ids whose claims share at least one
      prefix with the ejected entry — these need re-speculation and are
      returned to the queue at SPECULATING → QUEUED.
    """

    ejected: bool
    priority_after: int
    abandoned: bool = False
    independent_successors: list[str] = field(default_factory=list)
    requeued_successors: list[str] = field(default_factory=list)


def _caller_is_authorized_to_eject(
    entry: TrainEntry, caller_agent_id: str, caller_trust_level: int
) -> bool:
    """D11/R6 eject authorization: trust level >= 3 OR feature ownership.

    Ownership is read from ``entry.metadata["owner_agent_id"]`` (set at
    enqueue time by the submitting agent). We intentionally do NOT fall
    back to the branch name or feature id — those are not authenticatable.
    """
    if caller_trust_level >= MIN_COMPOSE_TRUST_LEVEL:
        return True
    owner = entry.metadata.get("owner_agent_id")
    return owner is not None and owner == caller_agent_id


def eject_from_train(
    entry: TrainEntry,
    *,
    reason: str,
    caller_agent_id: str,
    caller_trust_level: int,
    successors: list[TrainEntry],
) -> EjectResult:
    """Remove a failed entry from the train (D12, R14).

    Semantics:

      1. **Authorization** (R6/D11): caller must be the feature owner OR have
         trust level >= 3. Violations raise :class:`TrainAuthorizationError`.
      2. **Eject count increment**: ``entry.eject_count += 1``.
      3. **Terminal transition at threshold** (D12): if the new eject_count
         equals ``MAX_EJECT_COUNT``, the entry becomes ``ABANDONED``. The
         priority is NOT further decremented — abandonment is the decision.
         Otherwise the priority decreases by ``EJECT_PRIORITY_DECREMENT``
         (R14) and status becomes ``EJECTED``.
      4. **Successor classification** (R12): successors whose claim-prefix
         sets are disjoint from the ejected entry's claim-prefix set are
         **independent** (no re-speculation needed). The rest **depend**
         on the ejected entry's merged state and are re-queued.

    The speculative ref is cleared. The train_id/partition_id/train_position
    fields are preserved for audit purposes — the caller may decide to null
    them when recomposing.

    Args:
        entry: The train entry to eject. Must not already be terminal.
        reason: Human-readable cause of ejection (e.g., "CI failure: test_x").
        caller_agent_id: The agent making the eject call.
        caller_trust_level: The caller's trust level.
        successors: Other train entries that came after ``entry`` in the
            same train. Used to classify dependent vs independent.

    Returns:
        An :class:`EjectResult` describing the outcome.

    Raises:
        TrainAuthorizationError: if the caller has neither ownership nor
            sufficient trust.
    """
    if not _caller_is_authorized_to_eject(
        entry, caller_agent_id, caller_trust_level
    ):
        raise TrainAuthorizationError(
            f"caller {caller_agent_id!r} (trust {caller_trust_level}) is "
            f"not authorized to eject {entry.feature_id!r}: "
            f"requires ownership or trust >= {MIN_COMPOSE_TRUST_LEVEL}"
        )

    entry.eject_count += 1
    entry.last_eject_reason = reason
    # Speculative ref is invalidated regardless of transition target.
    entry.speculative_ref = None

    abandoned = entry.eject_count >= MAX_EJECT_COUNT
    if abandoned:
        # D12: terminal state. Priority is frozen — the scheduler should
        # never consider this entry again until a human re-enqueues it.
        entry.status = MergeTrainStatus.ABANDONED
        logger.warning(
            "eject_from_train: %s ABANDONED after %d ejections (reason=%s)",
            entry.feature_id,
            entry.eject_count,
            reason,
        )
    else:
        entry.status = MergeTrainStatus.EJECTED
        entry.merge_priority -= EJECT_PRIORITY_DECREMENT
        logger.info(
            "eject_from_train: %s EJECTED (count=%d, new_priority=%d, reason=%s)",
            entry.feature_id,
            entry.eject_count,
            entry.merge_priority,
            reason,
        )

    # Successor classification (R12) — independent vs. dependent.
    ejected_prefixes = _entry_prefix_set(entry)
    independent: list[str] = []
    requeued: list[str] = []
    for succ in successors:
        succ_prefixes = _entry_prefix_set(succ)
        if ejected_prefixes.isdisjoint(succ_prefixes):
            independent.append(succ.feature_id)
        else:
            requeued.append(succ.feature_id)
            # Dependent successors go back to the queue; their speculative
            # ref is stale because the ejected entry's merge position has
            # shifted. compose_train rebuilds them on the next sweep.
            succ.status = MergeTrainStatus.QUEUED
            succ.speculative_ref = None
            succ.train_id = None
            succ.partition_id = None
            succ.train_position = None
            succ.base_ref = None

    return EjectResult(
        ejected=True,
        priority_after=entry.merge_priority,
        abandoned=abandoned,
        independent_successors=independent,
        requeued_successors=requeued,
    )


def reset_blocked_entry(entry: TrainEntry) -> None:
    """Manual re-enqueue of a BLOCKED entry (R9, D9).

    This is the owner-initiated recovery path: after the owner has fixed
    the conflict (updated branch, resolved merge, or changed claims), they
    can call this to push the entry back into the queue. It is a no-op for
    entries not in BLOCKED state, so callers don't need to check first.

    What it clears:
      - ``status`` → ``QUEUED``
      - blocked metadata (``blocked_reason``, ``conflict_files``, actual/declared namespaces)
      - ``speculative_ref``, ``train_id``, ``partition_id``, ``train_position``, ``base_ref``
      - ``checked_at`` is preserved — the R9 auto-re-eval uses it for timing

    What it does NOT clear:
      - ``eject_count`` — ejections and blocks are independent failure modes
      - ``merge_priority`` — BLOCKED doesn't alter priority in the first place
    """
    if entry.status != MergeTrainStatus.BLOCKED:
        logger.debug(
            "reset_blocked_entry: %s not BLOCKED (status=%s), no-op",
            entry.feature_id,
            entry.status.value,
        )
        return
    entry.status = MergeTrainStatus.QUEUED
    for key in (
        "blocked_reason",
        "conflict_files",
        "actual_namespaces",
        "declared_namespaces",
    ):
        entry.metadata.pop(key, None)
    entry.speculative_ref = None
    entry.train_id = None
    entry.partition_id = None
    entry.train_position = None
    entry.base_ref = None
    logger.info(
        "reset_blocked_entry: %s re-queued for retry", entry.feature_id
    )


def reset_abandoned_entry(entry: TrainEntry) -> None:
    """Restore an ABANDONED entry to QUEUED state for manual re-enqueue (R14).

    Resets ``eject_count`` and ``last_eject_reason``, restores the
    ``merge_priority`` from ``original_priority`` if present, and sets the
    status back to ``QUEUED``. Does nothing if the entry isn't ABANDONED —
    this keeps the function idempotent for callers that can't easily check
    the status ahead of time.
    """
    if entry.status != MergeTrainStatus.ABANDONED:
        logger.debug(
            "reset_abandoned_entry: %s not ABANDONED (status=%s), no-op",
            entry.feature_id,
            entry.status.value,
        )
        return
    entry.eject_count = 0
    entry.last_eject_reason = None
    entry.status = MergeTrainStatus.QUEUED
    if entry.original_priority is not None:
        entry.merge_priority = entry.original_priority
    # Clear any stale train bookkeeping from the previous life.
    entry.speculative_ref = None
    entry.train_id = None
    entry.partition_id = None
    entry.train_position = None
    entry.base_ref = None
    logger.info(
        "reset_abandoned_entry: %s re-queued (priority=%d)",
        entry.feature_id,
        entry.merge_priority,
    )


# ---------------------------------------------------------------------------
# Wave merge executor (tasks 2.11, 2.12) — D4, R5
# ---------------------------------------------------------------------------


@dataclass
class _MergeNode:
    """A single mergeable unit in the wave-merge graph.

    Represents either a whole partition (fast-forward main to the partition's
    last speculative ref) or a single cross-partition entry (fast-forward
    main to that entry's ref). Dependencies are tracked as ``node_id`` strings
    so the same graph handles both kinds uniformly.
    """

    node_id: str
    kind: str  # "partition" | "cross"
    final_ref: str
    entries: list[TrainEntry]
    depends_on: set[str] = field(default_factory=set)


@dataclass
class WaveMergeResult:
    """Outcome of a full :func:`execute_wave_merge` run.

    - ``waves`` is a list of waves, each wave a list of ``node_id``s that
      merged simultaneously. Useful for metrics and post-mortems.
    - ``merged_entries`` lists every feature_id whose entry transitioned to
      MERGED during this run. Entries that were not SPEC_PASSED are absent.
    - ``deleted_ref_count`` is the return value of
      ``git_adapter.delete_speculative_refs(train_id)``.
    """

    waves: list[list[str]] = field(default_factory=list)
    merged_entries: list[str] = field(default_factory=list)
    deleted_ref_count: int = 0


def _build_merge_graph(composition: TrainComposition) -> dict[str, _MergeNode]:
    """Construct the wave-merge graph from a :class:`TrainComposition`.

    Nodes:
      * Each partition with ≥1 SPEC_PASSED entry becomes ``partition:<id>``.
      * Each cross-partition entry (whose ``entry`` is SPEC_PASSED) becomes
        ``cross:<feature_id>``.

    Edges (dependencies):
      * A partition depends on every cross entry whose ``spans_partitions``
        includes that partition — cross entries must merge first because the
        partition's speculative refs are chained on top of them.
      * Cross entries depend on every lower-position cross entry (chain).

    Nodes whose entries aren't SPEC_PASSED are dropped; this propagates as a
    deadlock if a dependent partition still references them via ``depends_on``.
    """
    nodes: dict[str, _MergeNode] = {}

    # Build cross-entry nodes, sorted by train_position so chain dependencies
    # are deterministic.
    sorted_cross = sorted(
        composition.cross_partition_entries,
        key=lambda cpe: (cpe.entry.train_position or 0, cpe.feature_id),
    )
    cross_order: list[str] = []
    for cpe in sorted_cross:
        entry = cpe.entry
        if entry.status != MergeTrainStatus.SPEC_PASSED:
            # Missing cross-entry — dependents will deadlock (test case).
            continue
        if entry.speculative_ref is None:
            continue
        node_id = f"cross:{cpe.feature_id}"
        node = _MergeNode(
            node_id=node_id,
            kind="cross",
            final_ref=entry.speculative_ref,
            entries=[entry],
        )
        # Chain: each cross entry depends on the previous cross entry.
        if cross_order:
            node.depends_on.add(cross_order[-1])
        nodes[node_id] = node
        cross_order.append(node_id)

    # Build partition nodes. Empty partitions (ghosts) are skipped — they
    # represent spanned prefixes with no local entries, nothing to merge.
    for partition in composition.partitions:
        ready_entries = [
            e for e in partition.entries if e.status == MergeTrainStatus.SPEC_PASSED
        ]
        # If a partition has entries but none are SPEC_PASSED, skip the node
        # but DO NOT raise — the full-suite run may legitimately run this
        # executor against a train that's only partially ready.
        if not partition.entries:
            continue
        if not ready_entries:
            continue
        if len(ready_entries) != len(partition.entries):
            # Some entries not ready → partition node is NOT added. We do
            # not merge partial partitions; the train will retry on the
            # next sweep once the stragglers pass CI.
            continue
        # Final ref = the highest-positioned entry's speculative_ref.
        sorted_by_pos = sorted(
            ready_entries, key=lambda e: e.train_position or 0
        )
        final_entry = sorted_by_pos[-1]
        if final_entry.speculative_ref is None:
            continue
        node_id = f"partition:{partition.partition_id}"
        node = _MergeNode(
            node_id=node_id,
            kind="partition",
            final_ref=final_entry.speculative_ref,
            entries=list(sorted_by_pos),
        )
        # Partition depends on every cross entry that spans its prefix.
        for cpe in composition.cross_partition_entries:
            if partition.partition_id in cpe.spans_partitions:
                dep = f"cross:{cpe.feature_id}"
                # Only add the dep if the cross node actually exists; if it
                # doesn't, the dependency is unresolvable → deadlock later.
                node.depends_on.add(dep)
        nodes[node_id] = node

    return nodes


def _compute_wave_order(nodes: dict[str, _MergeNode]) -> list[list[str]]:
    """Kahn-style topological wave layering.

    Each wave is a maximal set of nodes whose ``depends_on`` are all in
    prior waves. Raises :class:`TrainDeadlockError` if a wave would be empty
    while nodes remain — this means the dependency graph references a node
    that isn't present (e.g., a skipped cross entry).
    """
    if not nodes:
        return []

    remaining = dict(nodes)
    completed: set[str] = set()
    waves: list[list[str]] = []

    while remaining:
        wave: list[str] = []
        for node_id, node in remaining.items():
            # A node is ready when all its deps are either completed OR not
            # present in the graph at all (the latter is a red flag — we
            # must treat it as unmet to surface deadlocks cleanly).
            unmet = {
                d for d in node.depends_on if d not in completed
            }
            if not unmet:
                wave.append(node_id)
        if not wave:
            raise TrainDeadlockError(
                f"wave merge deadlock: {sorted(remaining.keys())} have "
                f"unresolvable dependencies. This typically indicates a "
                f"cross entry that failed CI and wasn't ejected before "
                f"merge execution."
            )
        # Deterministic in-wave ordering: cross entries before partitions,
        # then alphabetic on node_id. This matters for test stability.
        wave.sort(key=lambda nid: (0 if nid.startswith("cross:") else 1, nid))
        waves.append(wave)
        for nid in wave:
            completed.add(nid)
            del remaining[nid]
    return waves


def execute_wave_merge(
    composition: TrainComposition,
    git_adapter: GitAdapter,
    *,
    transaction: AbstractContextManager[object] | None = None,
) -> WaveMergeResult:
    """Execute the wave-based merge algorithm for a fully speculated train (D4).

    Algorithm (per design.md D4):

      1. Build a ready-graph from the composition's partitions and cross-
         partition entries. Nodes whose entries aren't all SPEC_PASSED are
         skipped; dependencies become unresolvable in that case and the
         executor raises :class:`TrainDeadlockError`.
      2. Topologically layer the graph into waves. Each wave contains all
         nodes whose dependencies have been merged in prior waves.
      3. Within a coordinator transaction, walk the waves in order. Per node:
           a. Transition all of its entries to ``MERGING``.
           b. ``git_adapter.fast_forward_main(node.final_ref)``.
           c. Transition entries to ``MERGED`` on success.
      4. After all waves complete, call
         ``git_adapter.delete_speculative_refs(train_id)`` to reclaim ref
         storage. This runs inside the transaction so a rollback leaves the
         refs intact for retry.

    Transaction semantics: if ``transaction`` is None, the executor uses a
    no-op context manager. In production, the coordinator supplies a
    DB-backed transaction so merge state is atomic with ref updates.

    Raises:
        TrainDeadlockError: if any wave is empty while nodes remain (cycle
            or missing dependency).

    Returns:
        A :class:`WaveMergeResult` with per-wave breakdown and the list of
        merged feature ids.
    """
    tx: AbstractContextManager[object] = transaction if transaction is not None else nullcontext()
    result = WaveMergeResult()

    with tx:
        nodes = _build_merge_graph(composition)
        result.waves = _compute_wave_order(nodes)

        for wave in result.waves:
            for node_id in wave:
                node = nodes[node_id]
                # Transition entries to MERGING before the git operation —
                # observers polling the status see a clean state machine.
                for e in node.entries:
                    e.status = MergeTrainStatus.MERGING
                ff = git_adapter.fast_forward_main(node.final_ref)
                if not ff.success:
                    # Fast-forward failure is a hard error: another process
                    # must have advanced main between compose and merge.
                    # Revert the entries back to SPEC_PASSED so the next
                    # sweep retries. The outer transaction rolls back too.
                    for e in node.entries:
                        e.status = MergeTrainStatus.SPEC_PASSED
                    raise RuntimeError(
                        f"fast_forward_main failed for {node_id} "
                        f"(ref={node.final_ref}, error={ff.error}); "
                        f"main advanced concurrently"
                    )
                for e in node.entries:
                    e.status = MergeTrainStatus.MERGED
                    result.merged_entries.append(e.feature_id)
                logger.info(
                    "execute_wave_merge: merged %s (%d entries, ref=%s)",
                    node_id,
                    len(node.entries),
                    node.final_ref,
                )

        # Cleanup: delete speculative refs even if the train was empty, to
        # sweep any refs left over from earlier failed attempts.
        if composition.train_id:
            result.deleted_ref_count = git_adapter.delete_speculative_refs(
                composition.train_id
            )

    logger.info(
        "execute_wave_merge: train=%s waves=%d entries=%d deleted_refs=%d",
        composition.train_id,
        len(result.waves),
        len(result.merged_entries),
        result.deleted_ref_count,
    )
    return result


# ---------------------------------------------------------------------------
# Crash recovery + watchdog TTL garbage collection (tasks 2.13, 2.14) — R7
# ---------------------------------------------------------------------------

#: Extracts a train_id from a speculative ref name. Kept local to this module
#: because the git_adapter pattern is a strict validator — we want a more
#: permissive extractor that tolerates variable hex lengths.
_TRAIN_ID_FROM_REF = re.compile(
    r"^refs/speculative/train-([a-f0-9]{8,32})/pos-\d{1,4}$"
)


@dataclass
class CrashRecoveryResult:
    """Outcome of :func:`cleanup_orphaned_speculative_refs` or
    :func:`gc_aged_speculative_refs`.

    - ``deleted_train_ids`` enumerates train_ids whose refs were deleted.
    - ``deleted_ref_count`` is the total number of individual refs deleted,
      summed across all trains.
    - ``skipped_refs`` collects refs that didn't match the validator (for
      audit logging; not a fatal condition).
    """

    deleted_train_ids: list[str] = field(default_factory=list)
    deleted_ref_count: int = 0
    skipped_refs: list[str] = field(default_factory=list)


def _group_refs_by_train_id(
    refs: list[str],
) -> tuple[dict[str, list[str]], list[str]]:
    """Parse a list of speculative refs into a ``{train_id: [refs]}`` mapping.

    Returns a tuple ``(groups, skipped)`` where ``skipped`` contains refs
    that didn't match the validator (e.g., refs pushed by an older release
    with a different naming convention).
    """
    groups: dict[str, list[str]] = {}
    skipped: list[str] = []
    for ref in refs:
        match = _TRAIN_ID_FROM_REF.match(ref)
        if not match:
            skipped.append(ref)
            continue
        groups.setdefault(match.group(1), []).append(ref)
    return groups, skipped


def cleanup_orphaned_speculative_refs(
    git_adapter: GitAdapter,
    *,
    active_train_ids: set[str],
) -> CrashRecoveryResult:
    """Startup cleanup: delete speculative refs whose train_id is not active (R7).

    Called at coordinator startup (or after a crash). Enumerates every ref
    under ``refs/speculative/`` via the adapter, groups them by train_id,
    and deletes any train whose id is NOT in ``active_train_ids``. The
    active set is typically built by querying the merge queue for entries
    in non-terminal states with a ``train_id`` set.

    This is distinct from :func:`gc_aged_speculative_refs`, which uses TTL
    for periodic cleanup. The startup routine ignores age entirely — an
    orphan is an orphan whether it's 1 minute or 1 week old, because the
    coordinator has no way to resume the train after a crash.

    Note: ref naming is validated by ``_TRAIN_ID_FROM_REF`` before deletion.
    Malformed refs are recorded in ``result.skipped_refs`` and left alone.
    This prevents accidental deletion of refs under ``refs/speculative/``
    that a sibling process might legitimately own.
    """
    refs = git_adapter.list_speculative_refs()
    groups, skipped = _group_refs_by_train_id(refs)
    result = CrashRecoveryResult(skipped_refs=skipped)

    for train_id, train_refs in sorted(groups.items()):
        if train_id in active_train_ids:
            continue
        deleted = git_adapter.delete_speculative_refs(train_id)
        result.deleted_train_ids.append(train_id)
        result.deleted_ref_count += deleted
        logger.info(
            "cleanup_orphaned_speculative_refs: deleted %d refs for orphan train %s",
            deleted,
            train_id,
        )

    if skipped:
        logger.warning(
            "cleanup_orphaned_speculative_refs: %d refs did not match "
            "the validator and were skipped: %s",
            len(skipped),
            skipped[:10],
        )
    return result


def gc_aged_speculative_refs(
    git_adapter: GitAdapter,
    *,
    train_creation_times: dict[str, datetime],
    max_age: timedelta = timedelta(hours=SPECULATIVE_REF_TTL_HOURS),
    now: datetime | None = None,
) -> CrashRecoveryResult:
    """Watchdog TTL garbage collection (R7).

    Called periodically by the watchdog (see ``DEFAULT_SWEEP_INTERVAL_SECONDS``
    in ``merge_train_types.py``). Deletes any speculative ref whose train
    has been alive longer than ``max_age``.

    The caller supplies ``train_creation_times`` — a snapshot of
    ``{train_id: created_at}`` read from the feature registry. A train whose
    id is missing from the snapshot is treated as orphaned and deleted
    immediately (it may have crashed before persisting creation time, or
    the registry may have already reaped its metadata).

    Args:
        git_adapter: used to enumerate and delete refs.
        train_creation_times: mapping of train_id to its creation timestamp.
            Passed in by the caller rather than queried here so the
            function is pure and easy to test.
        max_age: the TTL threshold. Defaults to ``SPECULATIVE_REF_TTL_HOURS``
            from ``git_adapter.py``.
        now: clock override for testing. Defaults to ``datetime.now(UTC)``.
    """
    reference_now = now if now is not None else datetime.now(UTC)
    refs = git_adapter.list_speculative_refs()
    groups, skipped = _group_refs_by_train_id(refs)
    result = CrashRecoveryResult(skipped_refs=skipped)

    for train_id, train_refs in sorted(groups.items()):
        created = train_creation_times.get(train_id)
        if created is None:
            # Unknown train — treat as orphan.
            eligible = True
        else:
            # Defensive: handle naive datetimes as UTC so we can diff safely.
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            eligible = (reference_now - created) >= max_age
        if not eligible:
            continue
        deleted = git_adapter.delete_speculative_refs(train_id)
        result.deleted_train_ids.append(train_id)
        result.deleted_ref_count += deleted
        logger.info(
            "gc_aged_speculative_refs: deleted %d refs for train %s "
            "(age=%s, max_age=%s)",
            deleted,
            train_id,
            reference_now - created if created is not None else "unknown",
            max_age,
        )
    return result
