#!/usr/bin/env python3
"""Storage tier selection for durable merge plans."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Protocol

from build_plan import write_plan_bundle
from merge_backend import _get_coordinator_status
from merge_plan import MergePlanValidationError, validate_plan
from render_plan import render_plan, write_projection


class PlanStore(Protocol):
    def load(self) -> dict[str, Any]: ...
    def save(self, plan: dict[str, Any]) -> None: ...
    def update_state(self, pr_number: int, **changes: Any) -> dict[str, Any]: ...


class FilePlanStore:
    """Phase-1 authoritative store backed by JSON plus a Markdown projection."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def projection_path(self) -> Path:
        return self.path.with_suffix(".md")

    def load(self) -> dict[str, Any]:
        plan = json.loads(self.path.read_text(encoding="utf-8"))
        validate_plan(plan)
        expected_projection = render_plan(plan)
        try:
            actual_projection = self.projection_path.read_text(encoding="utf-8")
        except OSError:
            actual_projection = ""
        if actual_projection != expected_projection:
            write_projection(plan, self.projection_path)
        return plan

    def save(self, plan: dict[str, Any]) -> None:
        persisted = copy.deepcopy(plan)
        persisted["storage_tier"] = "file"
        validate_plan(persisted)
        write_plan_bundle(persisted, self.path)

    def update_state(self, pr_number: int, **changes: Any) -> dict[str, Any]:
        plan = self.load()
        node = next(
            (candidate for candidate in plan["nodes"] if candidate["pr"] == pr_number),
            None,
        )
        if node is None:
            raise KeyError(f"PR #{pr_number} is not present in the merge plan")
        unknown = set(changes) - set(node["state"])
        if unknown:
            names = ", ".join(sorted(unknown))
            raise MergePlanValidationError(f"unknown live-state fields: {names}")
        node["state"].update(changes)
        self.save(plan)
        return plan


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

    def update_state(self, pr_number: int, **changes: Any) -> dict[str, Any]:
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
