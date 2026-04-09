"""MergeTrainService: DB-backed orchestration layer for the merge train engine.

This module is the bridge between the pure business logic in
:mod:`merge_train` (which operates on in-memory :class:`TrainEntry` lists)
and the persistent state in ``feature_registry.metadata["merge_queue"]``.
It exposes the four operations used by MCP tools / HTTP endpoints /
the periodic sweep:

    - :meth:`compose_train` — load queued entries, call the engine, persist
      the new train composition and status transitions.
    - :meth:`eject_from_train` — locate the entry + its downstream successors
      in the same train, call the engine, persist updates.
    - :meth:`get_train_status` — return the current entries for a train_id.
    - :meth:`report_spec_result` — CI callback that transitions SPECULATING
      entries to SPEC_PASSED or BLOCKED.

## refresh-architecture integration (task 5.8)

Before composing, the service probes
:meth:`refresh_rpc_client.RefreshRpcClient.is_graph_stale`. If the graph is
stale and no refresh is in flight, it calls ``trigger_refresh`` (fire-and-forget
— we don't wait in this version). If the client returns
:class:`RefreshClientUnavailable`, the service logs a warning and proceeds
anyway, marking the resulting composition with ``full_test_suite_required=True``
so CI runs the full suite instead of affected-tests-only.

The invariant is **merge train progress must NEVER be blocked on
refresh-architecture availability**.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import merge_train
from .db import DatabaseClient, get_db
from .feature_registry import (
    Feature,
    FeatureRegistryService,
    get_feature_registry_service,
)
from .git_adapter import GitAdapter, SubprocessGitAdapter
from .merge_train import EjectResult
from .merge_train_types import (
    DEFAULT_SWEEP_INTERVAL_SECONDS,
    MergeTrainStatus,
    TrainComposition,
    TrainEntry,
)
from .refresh_rpc_client import RefreshClientUnavailable, RefreshRpcClient

logger = logging.getLogger(__name__)


METADATA_KEY = "merge_queue"

# Stale threshold for the architecture graph — matches D8 and R9 defaults.
GRAPH_STALE_MAX_AGE_HOURS = 6


def _parse_dt(val: Any) -> datetime | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except ValueError:
        return None


def _feature_to_train_entry(feature: Feature) -> TrainEntry | None:
    """Build a TrainEntry from a Feature's merge_queue metadata.

    Returns None if the feature has no merge_queue metadata (i.e. it's not
    in the queue — skip it).
    """
    mq = feature.metadata.get(METADATA_KEY)
    if mq is None:
        return None

    status_str = mq.get("status", MergeTrainStatus.QUEUED.value)
    try:
        status = MergeTrainStatus(status_str)
    except ValueError:
        status = MergeTrainStatus.QUEUED

    return TrainEntry(
        feature_id=feature.feature_id,
        branch_name=feature.branch_name,
        merge_priority=feature.merge_priority,
        status=status,
        train_id=mq.get("train_id"),
        partition_id=mq.get("partition_id"),
        train_position=mq.get("train_position"),
        speculative_ref=mq.get("speculative_ref"),
        base_ref=mq.get("base_ref"),
        resource_claims=list(feature.resource_claims),
        decomposition=mq.get("decomposition", "branch"),
        stack_position=mq.get("stack_position"),
        eject_count=mq.get("eject_count", 0),
        last_eject_reason=mq.get("last_eject_reason"),
        original_priority=mq.get("original_priority"),
        metadata=dict(mq.get("extra", {}) or {}),
        queued_at=_parse_dt(mq.get("queued_at")),
        checked_at=_parse_dt(mq.get("checked_at")),
    )


class MergeTrainService:
    """DB-backed orchestration wrapper around :mod:`merge_train`.

    Thread-safe at the individual-method level only — concurrent invocations
    should be serialized by the caller (the periodic sweep relies on a single
    background task, and MCP/HTTP endpoints fire per-request).
    """

    def __init__(
        self,
        db: DatabaseClient | None = None,
        registry: FeatureRegistryService | None = None,
        git_adapter: GitAdapter | None = None,
        refresh_client: RefreshRpcClient | None = None,
    ) -> None:
        self._db = db
        self._registry = registry
        self._git_adapter = git_adapter
        self._refresh_client = refresh_client

    # ---- lazy accessors ----

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    @property
    def registry(self) -> FeatureRegistryService:
        if self._registry is None:
            self._registry = get_feature_registry_service()
        return self._registry

    @property
    def git_adapter(self) -> GitAdapter:
        if self._git_adapter is None:
            # Default to the current working directory — the coordinator
            # process runs from the repo root. Override via constructor
            # injection in tests or non-standard deployments.
            repo_path = os.environ.get("MERGE_TRAIN_REPO_PATH") or str(Path.cwd())
            self._git_adapter = SubprocessGitAdapter(repo_path=repo_path)
        return self._git_adapter

    @property
    def refresh_client(self) -> RefreshRpcClient:
        if self._refresh_client is None:
            self._refresh_client = RefreshRpcClient()
        return self._refresh_client

    # ---- internals ----

    async def _load_entries(self) -> list[TrainEntry]:
        """Load all active features with merge_queue metadata into TrainEntry objects."""
        features = await self.registry.get_active_features()
        entries: list[TrainEntry] = []
        for feature in features:
            entry = _feature_to_train_entry(feature)
            if entry is not None:
                entries.append(entry)
        return entries

    async def _save_entry(self, entry: TrainEntry, feature: Feature) -> None:
        """Persist a TrainEntry back to feature_registry.metadata."""
        new_meta = dict(feature.metadata)
        # Preserve pr_url / queued_at from the existing merge_queue blob —
        # to_metadata_dict() doesn't carry these (they're queue-layer concerns).
        existing_mq = dict(feature.metadata.get(METADATA_KEY, {}))
        mq_payload = entry.to_metadata_dict()
        # Keep pr_url around for the legacy merge-queue consumers
        if "pr_url" in existing_mq:
            mq_payload["pr_url"] = existing_mq["pr_url"]
        new_meta[METADATA_KEY] = mq_payload
        await self.db.update(
            "feature_registry",
            match={"feature_id": entry.feature_id},
            data={
                "metadata": new_meta,
                "merge_priority": entry.merge_priority,
            },
        )

    async def _persist_entries(
        self, entries: list[TrainEntry], features_by_id: dict[str, Feature]
    ) -> None:
        """Persist every entry whose corresponding feature is in the map."""
        for entry in entries:
            feature = features_by_id.get(entry.feature_id)
            if feature is not None:
                await self._save_entry(entry, feature)

    # ---- refresh-architecture integration (task 5.8) ----

    def _probe_and_maybe_refresh(self) -> bool:
        """Check graph freshness and optionally trigger a refresh.

        Returns ``True`` if CI must run the full test suite for this train
        (either because the graph is stale + we didn't wait for refresh, OR
        because the refresh subsystem is unavailable). Returns ``False`` if
        the graph is fresh and affected-tests-only is safe.

        Per the contract in ``refresh-architecture-rpc.yaml``, this MUST NEVER
        raise — the train must progress regardless of refresh availability.
        """
        client = self.refresh_client
        probe = client.is_graph_stale(max_age_hours=GRAPH_STALE_MAX_AGE_HOURS)
        if isinstance(probe, RefreshClientUnavailable):
            logger.warning(
                "compose_train: refresh client unavailable (%s) — "
                "falling back to full test suite",
                probe.reason,
            )
            return True

        if not probe.get("stale", False):
            return False

        # Graph is stale. If nothing is in flight, kick off a refresh —
        # fire-and-forget, we don't wait. The next compose_train call will see
        # the updated graph. Mark this train full-suite for safety.
        if not probe.get("refresh_in_flight", False):
            trigger_result = client.trigger_refresh(
                reason="compose_train:stale>6h",
                caller="merge_train_service",
            )
            if isinstance(trigger_result, RefreshClientUnavailable):
                logger.warning(
                    "compose_train: trigger_refresh unavailable (%s) — "
                    "full suite fallback",
                    trigger_result.reason,
                )
            else:
                logger.info(
                    "compose_train: triggered refresh id=%s (is_new=%s)",
                    trigger_result.get("refresh_id"),
                    trigger_result.get("is_new"),
                )
        return True

    # ---- public API ----

    async def compose_train(
        self, *, caller_trust_level: int = 3
    ) -> TrainComposition:
        """Compose a new merge train from the current queue.

        Probes refresh-architecture freshness first, then delegates to the
        engine, then persists every entry's updated state.
        """
        full_suite = self._probe_and_maybe_refresh()

        entries = await self._load_entries()
        composition = merge_train.compose_train(
            entries,
            git_adapter=self.git_adapter,
            caller_trust_level=caller_trust_level,
        )
        composition.full_test_suite_required = full_suite

        # Persist every entry (including re-evaluated BLOCKED, newly SPECULATING, etc.)
        features = await self.registry.get_active_features()
        by_id = {f.feature_id: f for f in features}
        await self._persist_entries(entries, by_id)

        logger.info(
            "compose_train: train_id=%s partitions=%d cross=%d full_suite=%s",
            composition.train_id,
            len(composition.partitions),
            len(composition.cross_partition_entries),
            full_suite,
        )
        return composition

    async def eject_from_train(
        self,
        feature_id: str,
        *,
        reason: str,
        caller_agent_id: str,
        caller_trust_level: int,
    ) -> EjectResult | None:
        """Eject an entry from its train.

        Returns None if the feature isn't in the queue. Otherwise delegates to
        the engine, classifies successors (dependent → requeued, independent →
        untouched), and persists affected entries.
        """
        entries = await self._load_entries()
        target = next((e for e in entries if e.feature_id == feature_id), None)
        if target is None:
            logger.warning("eject_from_train: feature %s not in queue", feature_id)
            return None

        # Successors in the same train — entries with a later position.
        successors: list[TrainEntry] = []
        if target.train_id is not None and target.train_position is not None:
            successors = [
                e
                for e in entries
                if e.feature_id != target.feature_id
                and e.train_id == target.train_id
                and e.train_position is not None
                and e.train_position > target.train_position
            ]

        result = merge_train.eject_from_train(
            target,
            reason=reason,
            caller_agent_id=caller_agent_id,
            caller_trust_level=caller_trust_level,
            successors=successors,
        )

        # Persist the ejected target + any requeued successors.
        features = await self.registry.get_active_features()
        by_id = {f.feature_id: f for f in features}
        changed: list[TrainEntry] = [target]
        for entry in entries:
            if entry.feature_id in set(result.requeued_successors):
                changed.append(entry)
        await self._persist_entries(changed, by_id)
        return result

    async def get_train_status(self, train_id: str) -> list[TrainEntry]:
        """Return every entry currently associated with ``train_id``."""
        entries = await self._load_entries()
        return [e for e in entries if e.train_id == train_id]

    async def report_spec_result(
        self,
        feature_id: str,
        *,
        passed: bool,
        error_message: str | None = None,
    ) -> TrainEntry | None:
        """CI callback: record the result of speculative verification.

        - SPECULATING + passed → SPEC_PASSED
        - SPECULATING + failed → BLOCKED (with error_message in metadata)
        - other statuses → idempotent no-op (return entry unchanged)
        - unknown feature → None
        """
        entries = await self._load_entries()
        target = next((e for e in entries if e.feature_id == feature_id), None)
        if target is None:
            return None

        if target.status != MergeTrainStatus.SPECULATING:
            # Idempotent — already acted on.
            return target

        if passed:
            target.status = MergeTrainStatus.SPEC_PASSED
            logger.info("report_spec_result: %s → SPEC_PASSED", feature_id)
        else:
            target.status = MergeTrainStatus.BLOCKED
            target.checked_at = datetime.now(UTC)
            target.metadata["blocked_reason"] = (
                error_message or "spec verification failed"
            )
            logger.warning(
                "report_spec_result: %s → BLOCKED (%s)",
                feature_id,
                error_message,
            )

        features = await self.registry.get_active_features()
        feature = next((f for f in features if f.feature_id == feature_id), None)
        if feature is not None:
            await self._save_entry(target, feature)
        return target


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


_merge_train_service: MergeTrainService | None = None


def get_merge_train_service() -> MergeTrainService:
    """Return the process-wide :class:`MergeTrainService` instance."""
    global _merge_train_service
    if _merge_train_service is None:
        _merge_train_service = MergeTrainService()
    return _merge_train_service


def reset_merge_train_service() -> None:
    """Clear the cached service (test hook)."""
    global _merge_train_service
    _merge_train_service = None


# ---------------------------------------------------------------------------
# Periodic sweeper (task 5.9)
# ---------------------------------------------------------------------------


#: Environment variable name for overriding the sweep interval.
SWEEP_INTERVAL_ENV = "MERGE_TRAIN_SWEEP_INTERVAL_SECONDS"


class MergeTrainSweeper:
    """Periodic ``compose_train`` sweep running as an asyncio task.

    The sweeper enforces R1/R2: if a new entry arrives while the previous
    train is still composing, the next sweep picks it up at the configured
    interval (default 60s). The loop is thin — all correctness lives in
    :meth:`MergeTrainService.compose_train`. The sweeper's only jobs are:

    1. Call ``compose_train`` on a timer.
    2. Swallow every exception so the event loop survives transient failures
       (DB hiccups, git errors, refresh RPC blips). A crashed sweeper would
       freeze the train indefinitely — the invariant is "sweeper MUST stay
       alive".

    Interval is configurable via ``MERGE_TRAIN_SWEEP_INTERVAL_SECONDS`` env
    var for deployment tuning; tests inject a low value to exercise the loop
    quickly.
    """

    def __init__(
        self,
        service: MergeTrainService | None = None,
        interval_seconds: float | None = None,
        caller_trust_level: int = 3,
    ) -> None:
        self._service = service
        self._caller_trust_level = caller_trust_level
        if interval_seconds is not None:
            self.interval_seconds: float = float(interval_seconds)
        else:
            env_val = os.environ.get(SWEEP_INTERVAL_ENV)
            self.interval_seconds = (
                float(env_val) if env_val else float(DEFAULT_SWEEP_INTERVAL_SECONDS)
            )
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def service(self) -> MergeTrainService:
        if self._service is None:
            self._service = get_merge_train_service()
        return self._service

    @property
    def running(self) -> bool:
        return self._running

    async def run_once(self) -> None:
        """Execute a single compose_train pass, swallowing any exception.

        Exposed as a standalone method so tests can exercise the core behavior
        without spinning up the asyncio loop. Production code hits this via
        :meth:`_loop`.
        """
        try:
            await self.service.compose_train(
                caller_trust_level=self._caller_trust_level
            )
        except Exception as exc:  # noqa: BLE001
            # Broad catch is deliberate — the sweeper must NEVER let an
            # exception escape. Log and move on.
            logger.error(
                "MergeTrainSweeper: compose_train failed: %s", exc, exc_info=True
            )

    async def start(self) -> None:
        """Start the sweep loop as a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "MergeTrainSweeper: started (interval=%ss)", self.interval_seconds
        )

    async def stop(self) -> None:
        """Stop the sweep loop gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("MergeTrainSweeper: stopped")

    async def _loop(self) -> None:
        """Main loop: run ``run_once`` then sleep, repeat until stopped."""
        while self._running:
            await self.run_once()
            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break


# ---- module-level sweeper singleton ----

_merge_train_sweeper: MergeTrainSweeper | None = None


def get_merge_train_sweeper() -> MergeTrainSweeper:
    """Return the process-wide :class:`MergeTrainSweeper` instance."""
    global _merge_train_sweeper
    if _merge_train_sweeper is None:
        _merge_train_sweeper = MergeTrainSweeper()
    return _merge_train_sweeper


def reset_merge_train_sweeper() -> None:
    """Clear the cached sweeper (test hook)."""
    global _merge_train_sweeper
    _merge_train_sweeper = None
