"""Package execution protocol for parallel-implement-feature Phase B.

Implements the worker-side protocol that every agent executing a work
package MUST follow. Steps B1-B11 from the design.

Key responsibilities:
- Pause-lock checks at B2 (before start) and B9 (before finalize)
- Deadlock-safe lock acquisition (B3) with sorted ordering
- Scope enforcement via git diff (B7)
- Structured result building conforming to work-queue-result.schema.json

Usage:
    from package_executor import PackageExecutor

    executor = PackageExecutor(
        feature_id="add-user-auth",
        package_def=package_dict,  # from work-packages.yaml
        contracts_revision=1,
        plan_revision=1,
    )

    # B2: Check pause lock
    if executor.check_pause_lock(active_locks):
        # Feature is paused, abort

    # B3: Compute lock acquisition order
    lock_order = executor.compute_lock_order()

    # B7: After implementation, check scope
    scope_result = executor.check_scope(files_modified)

    # B10: Build structured result
    result = executor.build_result(
        status="completed",
        files_modified=[...],
        git_base_ref="main",
        git_head_commit="abc1234",
        verification_steps=[...],
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from scope_checker import check_scope_compliance


PAUSE_LOCK_PREFIX = "feature:"
PAUSE_LOCK_SUFFIX = ":pause"


def make_pause_lock_key(feature_id: str) -> str:
    """Build the pause-lock key for a feature.

    Format: feature:<feature_id>:pause
    """
    return f"{PAUSE_LOCK_PREFIX}{feature_id}{PAUSE_LOCK_SUFFIX}"


class PackageExecutor:
    """Implements the Phase B package execution protocol.

    This class provides the protocol methods that a worker agent uses
    during work package execution. It does NOT directly interact with
    the coordinator — the calling agent handles coordinator communication.
    """

    def __init__(
        self,
        feature_id: str,
        package_def: dict[str, Any],
        contracts_revision: int,
        plan_revision: int,
        attempt: int = 1,
    ):
        self.feature_id = feature_id
        self.package_id: str = package_def["package_id"]
        self.package_def = package_def
        self.contracts_revision = contracts_revision
        self.plan_revision = plan_revision
        self.attempt = attempt
        self._started_at: datetime | None = None
        self._finished_at: datetime | None = None
        self._acquired_locks: list[str] = []
        self._escalations: list[dict[str, Any]] = []

    @property
    def pause_lock_key(self) -> str:
        """The pause-lock key for this feature."""
        return make_pause_lock_key(self.feature_id)

    def check_pause_lock(self, active_locks: list[str]) -> bool:
        """B2/B9: Check if the feature is paused.

        Args:
            active_locks: List of currently held lock keys (from check_locks()).

        Returns:
            True if the feature is paused (worker should abort).
        """
        return self.pause_lock_key in active_locks

    def compute_lock_order(self) -> list[str]:
        """B3: Compute deadlock-safe lock acquisition order.

        Returns all lock keys (files + logical keys) in a deterministic
        sorted order. Acquiring locks in this order prevents deadlocks
        when multiple packages try to acquire overlapping sets.
        """
        locks = self.package_def.get("locks", {})
        file_locks = list(locks.get("files", []))
        key_locks = list(locks.get("keys", []))
        # Sort all locks together for global ordering
        return sorted(set(file_locks + key_locks))

    def record_lock_acquired(self, lock_key: str) -> None:
        """Track a successfully acquired lock for cleanup."""
        if lock_key not in self._acquired_locks:
            self._acquired_locks.append(lock_key)

    def get_acquired_locks(self) -> list[str]:
        """Return list of locks acquired during execution."""
        return list(self._acquired_locks)

    def mark_started(self) -> None:
        """Record execution start time."""
        self._started_at = datetime.now(timezone.utc)

    def mark_finished(self) -> None:
        """Record execution finish time."""
        self._finished_at = datetime.now(timezone.utc)

    def check_scope(self, files_modified: list[str]) -> dict[str, Any]:
        """B7: Deterministic scope check via file list.

        Args:
            files_modified: Repo-relative paths from git diff --name-only.

        Returns:
            Scope compliance result dict.
        """
        scope = self.package_def.get("scope", {})
        return check_scope_compliance(
            files_modified=files_modified,
            write_allow=scope.get("write_allow", []),
            deny=scope.get("deny", []),
        )

    def add_escalation(self, escalation: dict[str, Any]) -> None:
        """Record an escalation emitted during execution."""
        self._escalations.append(escalation)

    def build_result(
        self,
        status: str,
        files_modified: list[str],
        git_base_ref: str,
        git_head_commit: str,
        verification_steps: list[dict[str, Any]],
        git_branch: str | None = None,
        git_worktree: str | None = None,
        error_code: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """B10: Build structured result conforming to work-queue-result.schema.json.

        Args:
            status: "completed" or "failed"
            files_modified: Repo-relative paths from git diff
            git_base_ref: Base branch/ref for the diff
            git_head_commit: HEAD commit SHA
            verification_steps: List of verification step results
            git_branch: Optional branch name
            git_worktree: Optional worktree name
            error_code: Required when status="failed"
            notes: Optional execution notes
        """
        self.mark_finished()

        scope = self.package_def.get("scope", {})
        locks = self.package_def.get("locks", {})

        # Run scope check
        scope_result = self.check_scope(files_modified)

        # Compute verification summary
        verification_passed = all(
            step.get("passed", False) for step in verification_steps
        )
        verification_tier = self.package_def.get("verification", {}).get(
            "tier_required", "A"
        )

        result: dict[str, Any] = {
            "schema_version": 1,
            "feature_id": self.feature_id,
            "package_id": self.package_id,
            "attempt": self.attempt,
            "plan_revision": self.plan_revision,
            "contracts_revision": self.contracts_revision,
            "status": status,
            "locks": {
                "files": list(locks.get("files", [])),
                "keys": list(locks.get("keys", [])),
            },
            "scope": {
                "write_allow": list(scope.get("write_allow", [])),
                "read_allow": list(scope.get("read_allow", [])),
                "deny": list(scope.get("deny", [])),
            },
            "files_modified": files_modified,
            "scope_check": {
                "passed": scope_result["compliant"],
                "violations": [v["file"] for v in scope_result.get("violations", [])],
            },
            "git": {
                "base": {"ref": git_base_ref},
                "head": {"commit": git_head_commit},
            },
            "verification": {
                "tier": verification_tier,
                "passed": verification_passed,
                "steps": verification_steps,
            },
            "escalations": list(self._escalations),
        }

        # Optional fields
        if git_branch:
            result["git"]["head"]["branch"] = git_branch
        if git_worktree:
            result["git"]["head"]["worktree"] = git_worktree
        if error_code:
            result["error_code"] = error_code
        if self._started_at or self._finished_at:
            result["timestamps"] = {}
            if self._started_at:
                result["timestamps"]["started_at"] = self._started_at.isoformat()
            if self._finished_at:
                result["timestamps"]["finished_at"] = self._finished_at.isoformat()
        if notes:
            result["notes"] = notes

        return result

    def build_failure_result(
        self,
        error_code: str,
        git_base_ref: str,
        git_head_commit: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Build a failure result with minimal verification data.

        Used when execution fails before verification steps complete.
        """
        return self.build_result(
            status="failed",
            files_modified=[],
            git_base_ref=git_base_ref,
            git_head_commit=git_head_commit,
            verification_steps=[{
                "name": "aborted",
                "kind": "command",
                "command": "N/A",
                "exit_code": 1,
                "passed": False,
                "evidence": {"artifacts": [], "metrics": {}},
            }],
            error_code=error_code,
            notes=notes,
        )
