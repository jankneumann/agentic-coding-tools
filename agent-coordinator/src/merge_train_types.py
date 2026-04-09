"""Shared data types for the speculative merge train engine.

This module is the single source of truth for merge-train data structures.
Both `merge_queue.py` (which extends the existing enqueue path) and
`merge_train.py` (the train engine proper) import from here. Keeping types
in a separate module avoids circular imports between queue and engine.

Contents:
  - `MergeTrainStatus` — extended state machine enum
  - `TrainEntry`, `TrainPartition`, `TrainComposition` — dataclasses
  - `PATH_TO_NAMESPACE_RULES` / `file_path_to_namespaces()` — heuristic mapping
    from a repo-relative file path to the set of logical namespaces it could
    belong to. Used for post-speculation claim validation (D8).

Related contracts:
  - `contracts/internal/merge-train-api.yaml`
  - `contracts/internal/git-adapter-api.yaml`

Related docs:
  - `docs/lock-key-namespaces.md` — the 9 canonical lock key prefixes that
    this module's heuristic tries to reverse-map.
"""

from __future__ import annotations

import fnmatch
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum number of consecutive ejections before an entry transitions to
#: ABANDONED instead of being re-queued. Tunable per deployment but not
#: per-entry to prevent gaming (see D12).
MAX_EJECT_COUNT: int = 3

#: Priority decrement applied each time an entry is ejected (D4).
EJECT_PRIORITY_DECREMENT: int = 10

#: Cross-partition cycle detection threshold: no more than this many
#: partitions involved in a single cross-partition sub-train.
MAX_CROSS_PARTITION_SPAN: int = 10

#: Default periodic sweep interval for compose_train, in seconds (R1 scenario).
DEFAULT_SWEEP_INTERVAL_SECONDS: int = 60


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class MergeTrainStatus(Enum):
    """Extended state machine for merge train entries (R3).

    Legacy `MergeStatus` (in merge_queue.py) remains for backward compatibility
    with callers that only care about queue-level state. MergeTrainStatus is a
    superset: all legacy values appear here, plus SPECULATING, SPEC_PASSED,
    EJECTED, and the R14 terminal state ABANDONED.
    """

    QUEUED = "queued"
    SPECULATING = "speculating"
    SPEC_PASSED = "spec_passed"
    MERGING = "merging"
    MERGED = "merged"
    EJECTED = "ejected"
    BLOCKED = "blocked"
    # R14: terminal state after exceeding MAX_EJECT_COUNT. Not automatically
    # re-queued — recoverable only via manual re-enqueue.
    ABANDONED = "abandoned"

    # Legacy values preserved for compatibility with existing merge_queue paths
    PRE_MERGE_CHECK = "pre_merge_check"
    READY = "ready"


#: Statuses that count as "terminal" for a train — compose_train skips these.
TERMINAL_STATUSES: frozenset[MergeTrainStatus] = frozenset(
    {
        MergeTrainStatus.MERGED,
        MergeTrainStatus.ABANDONED,
    }
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TrainEntry:
    """An entry in the merge train (one per feature/package).

    Persisted in `feature_registry.metadata["merge_queue"]` (D1); this is the
    in-memory projection used by the train engine. Fields prefixed with
    `eject_` track R14 state.
    """

    feature_id: str
    branch_name: str | None
    merge_priority: int
    status: MergeTrainStatus
    train_id: str | None = None
    partition_id: str | None = None
    train_position: int | None = None
    speculative_ref: str | None = None
    base_ref: str | None = None
    resource_claims: list[str] = field(default_factory=list)
    decomposition: str = "branch"  # "branch" | "stacked"
    stack_position: int | None = None
    eject_count: int = 0
    last_eject_reason: str | None = None
    # The original priority at first enqueue — used to restore on ABANDONED re-enqueue (R14).
    original_priority: int | None = None
    # JSONB catch-all for diagnostics (conflict file list, etc.)
    metadata: dict[str, Any] = field(default_factory=dict)
    queued_at: datetime | None = None
    checked_at: datetime | None = None

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def to_metadata_dict(self) -> dict[str, Any]:
        """Serialize to the JSONB shape stored in feature_registry.metadata."""
        return {
            "status": self.status.value,
            "train_id": self.train_id,
            "partition_id": self.partition_id,
            "train_position": self.train_position,
            "speculative_ref": self.speculative_ref,
            "base_ref": self.base_ref,
            "decomposition": self.decomposition,
            "stack_position": self.stack_position,
            "eject_count": self.eject_count,
            "last_eject_reason": self.last_eject_reason,
            "original_priority": self.original_priority,
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
            "extra": self.metadata,
        }


@dataclass
class TrainPartition:
    """A group of train entries with overlapping lock-key prefixes.

    Entries within a partition are serialized (via speculative positions).
    Different partitions merge independently in the merge executor (R5).
    """

    partition_id: str
    key_prefixes: set[str] = field(default_factory=set)
    entries: list[TrainEntry] = field(default_factory=list)

    def all_passed(self) -> bool:
        return bool(self.entries) and all(
            e.status == MergeTrainStatus.SPEC_PASSED for e in self.entries
        )


@dataclass
class CrossPartitionEntry:
    """A train entry whose resource claims span multiple partitions.

    Cross-partition entries serialize their spanning partitions around
    themselves: the entry merges only after ALL preceding entries in EVERY
    partition it spans have merged (see D4 wave algorithm).
    """

    feature_id: str
    entry: TrainEntry
    spans_partitions: list[str] = field(default_factory=list)


@dataclass
class TrainComposition:
    """The complete composition of a merge train.

    One TrainComposition per call to compose_train(). Train IDs are short
    hex strings (8+ chars) — compatible with the speculative ref name regex.
    """

    train_id: str
    partitions: list[TrainPartition] = field(default_factory=list)
    cross_partition_entries: list[CrossPartitionEntry] = field(default_factory=list)
    composed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    #: R9 / refresh-architecture integration: when the architecture graph is
    #: stale AND the refresh subsystem is unavailable (or we decided not to wait),
    #: the CI layer must run the FULL test suite for every entry in this train
    #: instead of the affected-tests subset. Set by MergeTrainService based on
    #: the refresh_rpc_client probe in compose_train.
    full_test_suite_required: bool = False

    @classmethod
    def new_train_id(cls) -> str:
        """Generate a new 12-char hex train_id (fits the ref regex)."""
        return uuid.uuid4().hex[:12]

    def all_entries(self) -> list[TrainEntry]:
        """All entries across all partitions (flattened)."""
        result: list[TrainEntry] = []
        for p in self.partitions:
            result.extend(p.entries)
        return result

    def total_entry_count(self) -> int:
        return sum(len(p.entries) for p in self.partitions)


# ---------------------------------------------------------------------------
# File-path-to-namespace heuristic mapping (D8)
# ---------------------------------------------------------------------------

#: Ordered list of `(glob_pattern, namespace)` rules used by
#: `file_path_to_namespaces()`. Rules are applied as a UNION — multiple matching
#: rules produce a set with all their namespaces. Rules should be reviewed
#: alongside `docs/lock-key-namespaces.md` when namespaces are added.
#:
#: IMPORTANT: this mapping is HEURISTIC. An empty result means "the path is
#: outside the 9 logical namespaces" (file-level locks still apply) — it does
#: NOT fail claim validation, it opts the path out of namespace-level checking.
PATH_TO_NAMESPACE_RULES: list[tuple[str, str]] = [
    # Contract artifacts
    ("contracts/**", "contract:"),
    ("contracts/**/*", "contract:"),
    # Database migrations (single global slot)
    ("**/migrations/**", "db:migration-slot"),
    ("supabase/migrations/**", "db:migration-slot"),
    # Database schema definitions
    ("**/schema*.py", "db:schema:"),
    ("**/models/**", "db:schema:"),
    ("**/models.py", "db:schema:"),
    # HTTP API surface
    ("src/api/**", "api:"),
    ("**/routes/**", "api:"),
    ("**/endpoints/**", "api:"),
    # Event bus handlers
    ("src/events/**", "event:"),
    ("**/event_handlers/**", "event:"),
    # Feature flags registry
    ("flags.yaml", "flag:"),
]


def file_path_to_namespaces(path: str) -> set[str]:
    """Return the set of lock-key namespaces a repo-relative path likely belongs to.

    This is the reverse of the namespace mapping documented in
    ``docs/lock-key-namespaces.md``. It is HEURISTIC — a best-effort guess
    used to verify post-speculation claim truthfulness (D8). An empty return
    means "out of scope for namespace-level validation" (file-level locks
    still apply), not "claim mismatch".

    The function applies each rule in PATH_TO_NAMESPACE_RULES. All matching
    rules contribute to the result via set union. Unrelated paths (README,
    docs/, tests that aren't in a namespaced location) return an empty set.

    Examples:
        >>> file_path_to_namespaces("src/api/users.py")
        {'api:'}
        >>> file_path_to_namespaces("src/db/migrations/0042_add_trains.sql")
        {'db:migration-slot'}
        >>> file_path_to_namespaces("README.md")
        set()
    """
    if not path:
        return set()
    # Normalize leading "./" if present; strip trailing whitespace.
    normalized = path.strip().lstrip("./")
    if not normalized:
        return set()

    result: set[str] = set()
    for pattern, namespace in PATH_TO_NAMESPACE_RULES:
        if fnmatch.fnmatch(normalized, pattern):
            result.add(namespace)
    return result


def claim_prefix(claim: str) -> str:
    """Extract the namespace prefix from a resource claim string.

    Lock keys use ``<prefix>:<identifier>`` format (see lock-key-namespaces.md).
    This returns the ``<prefix>:`` portion so it can be compared with the
    output of `file_path_to_namespaces()`.

    Examples:
        >>> claim_prefix("api:GET /v1/users")
        'api:'
        >>> claim_prefix("db:schema:users")
        'db:schema:'
        >>> claim_prefix("db:migration-slot")
        'db:migration-slot'
        >>> claim_prefix("src/api/users.py")
        ''
    """
    # File-path locks (no ":" or contain "/") have no logical prefix.
    if ":" not in claim:
        return ""
    # Special-case "db:schema:<table>" and "db:migration-slot"
    if claim.startswith("db:schema:"):
        return "db:schema:"
    if claim.startswith("db:migration-slot"):
        return "db:migration-slot"
    prefix = claim.split(":", 1)[0]
    return f"{prefix}:"
