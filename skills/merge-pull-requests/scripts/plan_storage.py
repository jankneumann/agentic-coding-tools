#!/usr/bin/env python3
"""Storage tier selection for durable merge plans."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol

from build_plan import write_plan_bundle
from merge_backend import _get_coordinator_status
from merge_plan import MergePlanValidationError, validate_plan
from render_plan import render_plan, write_projection


class PlanStore(Protocol):
    def load(self) -> dict[str, Any]: ...
    def save(self, plan: dict[str, Any]) -> None: ...
    def update_state(
        self,
        pr_number: int,
        *,
        expected_outcome: str | None = None,
        **changes: Any,
    ) -> dict[str, Any]: ...
    def claim_node(
        self,
        pr_number: int,
        claim_id: str,
    ) -> tuple[dict[str, Any], bool]: ...


class PlanWriteConflict(RuntimeError):
    """A writer attempted to persist a plan revision it did not read."""


class FilePlanStore:
    """Phase-1 authoritative store backed by JSON plus a Markdown projection."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._revision: str | None = None

    @property
    def projection_path(self) -> Path:
        return self.path.with_suffix(".md")

    @property
    def state_lock_path(self) -> Path:
        identity = hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()
        lock_dir = Path(tempfile.gettempdir()) / "merge-plan-claim-locks"
        lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        return lock_dir / f"{identity}.lock"

    @contextmanager
    def _state_lock(self) -> Iterator[None]:
        """Serialize file-tier reads and writes without repo artifacts."""

        with self.state_lock_path.open("a", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load_locked(self) -> dict[str, Any]:
        payload = self.path.read_bytes()
        plan = json.loads(payload)
        validate_plan(plan)
        self._revision = hashlib.sha256(payload).hexdigest()
        expected_projection = render_plan(plan)
        try:
            actual_projection = self.projection_path.read_text(encoding="utf-8")
        except OSError:
            actual_projection = ""
        if actual_projection != expected_projection:
            write_projection(plan, self.projection_path)
        return plan

    def load(self) -> dict[str, Any]:
        with self._state_lock():
            return self._load_locked()

    def _save_locked(self, plan: dict[str, Any]) -> None:
        persisted = copy.deepcopy(plan)
        persisted["storage_tier"] = "file"
        validate_plan(persisted)
        write_plan_bundle(persisted, self.path)
        self._revision = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def save(self, plan: dict[str, Any]) -> None:
        with self._state_lock():
            if self.path.exists():
                current = hashlib.sha256(self.path.read_bytes()).hexdigest()
                if self._revision is None or current != self._revision:
                    raise PlanWriteConflict(
                        f"merge plan changed since it was loaded: {self.path}",
                    )
            elif self._revision is not None:
                raise PlanWriteConflict(
                    f"merge plan was removed since it was loaded: {self.path}",
                )
            self._save_locked(plan)

    def update_state(
        self,
        pr_number: int,
        *,
        expected_outcome: str | None = None,
        **changes: Any,
    ) -> dict[str, Any]:
        with self._state_lock():
            plan = self._load_locked()
            node = next(
                (candidate for candidate in plan["nodes"] if candidate["pr"] == pr_number),
                None,
            )
            if node is None:
                raise KeyError(f"PR #{pr_number} is not present in the merge plan")
            if expected_outcome is not None and node["state"]["outcome"] != expected_outcome:
                raise PlanWriteConflict(
                    f"PR #{pr_number} outcome changed from {expected_outcome} "
                    f"to {node['state']['outcome']}",
                )
            unknown = set(changes) - set(node["state"])
            if unknown:
                names = ", ".join(sorted(unknown))
                raise MergePlanValidationError(f"unknown live-state fields: {names}")
            node["state"].update(changes)
            self._save_locked(plan)
            return plan

    def claim_node(
        self,
        pr_number: int,
        claim_id: str,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically claim one pending node across same-host executors."""

        with self._state_lock():
            plan = self._load_locked()
            node = next(
                (candidate for candidate in plan["nodes"] if candidate["pr"] == pr_number),
                None,
            )
            if node is None:
                raise KeyError(f"PR #{pr_number} is not present in the merge plan")
            state = node["state"]
            if state["outcome"] == "in_progress":
                return plan, state.get("claimed_by") == claim_id
            if state["outcome"] != "pending":
                return plan, False
            state["outcome"] = "in_progress"
            state["claimed_by"] = claim_id
            state["blocking_reason"] = None
            self._save_locked(plan)
            return plan, True


class CoordinatorPlanStore:
    """Explicit seam for the deferred coordinator system-of-record tier."""

    @staticmethod
    def _deferred() -> None:
        raise NotImplementedError(
            "Coordinator merge-plan storage is deferred to Phase 2",
        )

    def load(self) -> dict[str, Any]:
        self._deferred()
        raise AssertionError("unreachable")

    def save(self, plan: dict[str, Any]) -> None:
        self._deferred()

    def update_state(
        self,
        pr_number: int,
        *,
        expected_outcome: str | None = None,
        **changes: Any,
    ) -> dict[str, Any]:
        self._deferred()
        raise AssertionError("unreachable")

    def claim_node(
        self,
        pr_number: int,
        claim_id: str,
    ) -> tuple[dict[str, Any], bool]:
        self._deferred()
        raise AssertionError("unreachable")


def select_plan_store(
    path: Path,
    *,
    coordinator_status: dict[str, Any] | None = None,
) -> PlanStore:
    """Reuse merge-backend capability detection to choose plan authority."""

    status = coordinator_status if coordinator_status is not None else _get_coordinator_status()
    if status.get("COORDINATOR_AVAILABLE") and status.get("CAN_QUEUE_WORK"):
        return CoordinatorPlanStore()
    return FilePlanStore(path)
