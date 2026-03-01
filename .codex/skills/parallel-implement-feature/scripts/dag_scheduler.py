"""DAG Scheduler for parallel-implement-feature Phase A preflight.

Parses work-packages.yaml, validates structure and constraints, computes
topological execution order, and prepares work queue task submissions.

Usage as library:
    from dag_scheduler import DAGScheduler
    scheduler = DAGScheduler(work_packages_path, base_dir)
    result = scheduler.preflight()

Usage as CLI:
    python dag_scheduler.py <work-packages.yaml> [--base-dir <dir>] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# Import validation functions from scripts/validate_work_packages.py
# The scripts/ directory is two levels up from this file
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from validate_work_packages import (
    detect_cycles,
    load_schema,
    load_work_packages,
    validate_depends_on_refs,
    validate_lock_keys,
    validate_lock_overlap,
    validate_schema,
    validate_scope_overlap,
)


class PackageState(str, Enum):
    """Lifecycle state for a work package."""

    PENDING = "pending"
    READY = "ready"
    SUBMITTED = "submitted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PackageStatus:
    """Tracks per-package execution state."""

    package_id: str
    state: PackageState = PackageState.PENDING
    task_id: str | None = None
    attempt: int = 0
    depends_on: list[str] = field(default_factory=list)
    error: str | None = None


def compute_topo_order(packages: list[dict[str, Any]]) -> list[str]:
    """Compute topological execution order from package dependency DAG.

    Returns package_ids in an order where all dependencies of a package
    appear before it. Raises ValueError if cycles exist.
    """
    id_set = {p["package_id"] for p in packages}
    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {p["package_id"]: 0 for p in packages}

    for p in packages:
        for dep in p.get("depends_on", []):
            if dep in id_set:
                adj[dep].append(p["package_id"])
                in_degree[p["package_id"]] += 1

    # Kahn's algorithm — use sorted() for deterministic order among peers
    queue: list[str] = sorted(pid for pid, deg in in_degree.items() if deg == 0)
    order: list[str] = []

    while queue:
        node = queue.pop(0)
        order.append(node)
        newly_ready = []
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                newly_ready.append(neighbor)
        queue.extend(sorted(newly_ready))

    if len(order) != len(packages):
        remaining = id_set - set(order)
        raise ValueError(f"Cycle detected in DAG involving: {sorted(remaining)}")

    return order


def validate_contracts_exist(
    data: dict[str, Any], base_dir: Path
) -> list[str]:
    """Check that all declared contract files exist on disk.

    Returns list of missing file paths.
    """
    missing = []
    contracts = data.get("contracts", {})
    openapi = contracts.get("openapi", {})
    for file_path in openapi.get("files", []):
        full = base_dir / file_path
        if not full.exists():
            missing.append(file_path)
    return missing


def build_context_slice(
    package: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, Any]:
    """Build the input_data envelope for a work queue task submission.

    Produces a context slice with only the information this package needs.
    """
    feature = data.get("feature", {})
    contracts = data.get("contracts", {})

    return {
        "feature_id": feature.get("id", ""),
        "plan_revision": feature.get("plan_revision", 1),
        "contracts_revision": contracts.get("revision", 1),
        "package": {
            "package_id": package["package_id"],
            "task_type": package.get("task_type", ""),
            "description": package.get("description", ""),
            "scope": package.get("scope", {}),
            "locks": package.get("locks", {}),
            "worktree": package.get("worktree", {}),
            "verification": package.get("verification", {}),
            "inputs": package.get("inputs", {}),
            "outputs": package.get("outputs", {}),
        },
        "contracts": {
            "openapi": contracts.get("openapi", {}),
            "generated": contracts.get("generated", {}),
        },
    }


def prepare_task_submissions(
    data: dict[str, Any],
    topo_order: list[str],
) -> list[dict[str, Any]]:
    """Prepare work queue task submission payloads in topological order.

    Each submission dict has the fields needed for submit_work():
    - task_type, description, priority, input_data, depends_on (package_ids)

    The orchestrator resolves package_id depends_on to task_ids after submission.
    """
    pkg_map = {p["package_id"]: p for p in data.get("packages", [])}
    defaults = data.get("defaults", {})
    submissions = []

    for pid in topo_order:
        pkg = pkg_map[pid]
        context = build_context_slice(pkg, data)
        submission = {
            "package_id": pid,
            "task_type": pkg.get("task_type", "implement"),
            "description": f"[{data['feature']['id']}] {pkg.get('title', pid)}: {pkg.get('description', '')}",
            "priority": pkg.get("priority", defaults.get("priority", 5)),
            "input_data": context,
            "depends_on_packages": list(pkg.get("depends_on", [])),
            "timeout_minutes": pkg.get(
                "timeout_minutes", defaults.get("timeout_minutes", 60)
            ),
            "retry_budget": pkg.get(
                "retry_budget", defaults.get("retry_budget", 1)
            ),
        }
        submissions.append(submission)

    return submissions


class DAGScheduler:
    """Orchestrates Phase A preflight for parallel-implement-feature.

    Steps:
    A1. Parse and validate work-packages.yaml
    A2. Validate contracts exist
    A3. Compute DAG order (topological sort)
    A4. Prepare work queue task submissions
    """

    def __init__(self, work_packages_path: Path, base_dir: Path | None = None):
        self.work_packages_path = Path(work_packages_path)
        self.base_dir = Path(base_dir) if base_dir else self.work_packages_path.parent
        self.data: dict[str, Any] = {}
        self.topo_order: list[str] = []
        self.package_statuses: dict[str, PackageStatus] = {}
        self.submissions: list[dict[str, Any]] = []

    def preflight(self) -> dict[str, Any]:
        """Execute the full Phase A preflight sequence.

        Returns a result dict with validation results, DAG order,
        and prepared task submissions.
        """
        result: dict[str, Any] = {
            "valid": True,
            "checks": {},
            "topo_order": [],
            "submissions": [],
            "errors": [],
        }

        # A1: Parse and validate
        a1 = self._step_validate()
        result["checks"]["validation"] = a1
        if not a1["passed"]:
            result["valid"] = False
            result["errors"].extend(a1.get("errors", []))
            return result

        # A2: Validate contracts exist
        a2 = self._step_contracts()
        result["checks"]["contracts"] = a2
        if not a2["passed"]:
            result["valid"] = False
            result["errors"].extend(
                [f"Missing contract: {f}" for f in a2.get("missing", [])]
            )
            return result

        # A3: Compute DAG order
        a3 = self._step_topo_order()
        result["checks"]["dag_order"] = a3
        if not a3["passed"]:
            result["valid"] = False
            result["errors"].extend(a3.get("errors", []))
            return result
        result["topo_order"] = self.topo_order

        # A4: Prepare task submissions
        self.submissions = prepare_task_submissions(self.data, self.topo_order)
        result["submissions"] = self.submissions

        # Initialize package statuses
        for pid in self.topo_order:
            pkg = next(p for p in self.data["packages"] if p["package_id"] == pid)
            self.package_statuses[pid] = PackageStatus(
                package_id=pid,
                state=PackageState.READY if not pkg.get("depends_on") else PackageState.PENDING,
                depends_on=list(pkg.get("depends_on", [])),
            )

        return result

    def _step_validate(self) -> dict[str, Any]:
        """A1: Parse and validate work-packages.yaml."""
        errors = []

        if not self.work_packages_path.exists():
            return {"passed": False, "errors": [f"File not found: {self.work_packages_path}"]}

        try:
            self.data = load_work_packages(self.work_packages_path)
        except Exception as e:
            return {"passed": False, "errors": [f"YAML parse error: {e}"]}

        schema = load_schema()
        schema_errors = validate_schema(self.data, schema)
        if schema_errors:
            errors.extend(schema_errors)

        packages = self.data.get("packages", [])

        ref_errors = validate_depends_on_refs(packages)
        errors.extend(ref_errors)

        cycles = detect_cycles(packages)
        if cycles:
            for cycle in cycles:
                errors.append(f"Cycle: {' -> '.join(cycle)}")

        key_errors = validate_lock_keys(packages)
        errors.extend(key_errors)

        scope_errors = validate_scope_overlap(packages)
        errors.extend(scope_errors)

        lock_errors = validate_lock_overlap(packages)
        errors.extend(lock_errors)

        return {"passed": not errors, "errors": errors}

    def _step_contracts(self) -> dict[str, Any]:
        """A2: Validate contracts exist on disk."""
        missing = validate_contracts_exist(self.data, self.base_dir)
        return {"passed": not missing, "missing": missing}

    def _step_topo_order(self) -> dict[str, Any]:
        """A3: Compute topological execution order."""
        try:
            self.topo_order = compute_topo_order(self.data.get("packages", []))
            return {"passed": True, "order": self.topo_order}
        except ValueError as e:
            return {"passed": False, "errors": [str(e)]}

    def get_ready_packages(self) -> list[str]:
        """Return package_ids that are ready to execute (all deps completed)."""
        ready = []
        for pid, status in self.package_statuses.items():
            if status.state == PackageState.READY:
                ready.append(pid)
            elif status.state == PackageState.PENDING:
                all_deps_done = all(
                    self.package_statuses.get(dep, PackageStatus(package_id=dep)).state
                    == PackageState.COMPLETED
                    for dep in status.depends_on
                )
                if all_deps_done:
                    ready.append(pid)
        return sorted(ready)

    def mark_submitted(self, package_id: str, task_id: str) -> None:
        """Mark a package as submitted to the work queue."""
        if package_id in self.package_statuses:
            self.package_statuses[package_id].state = PackageState.SUBMITTED
            self.package_statuses[package_id].task_id = task_id

    def mark_in_progress(self, package_id: str) -> None:
        """Mark a package as in progress (claimed by agent)."""
        if package_id in self.package_statuses:
            self.package_statuses[package_id].state = PackageState.IN_PROGRESS

    def mark_completed(self, package_id: str) -> None:
        """Mark a package as completed and check for newly ready packages."""
        if package_id in self.package_statuses:
            self.package_statuses[package_id].state = PackageState.COMPLETED

    def mark_failed(self, package_id: str, error: str) -> None:
        """Mark a package as failed."""
        if package_id in self.package_statuses:
            self.package_statuses[package_id].state = PackageState.FAILED
            self.package_statuses[package_id].error = error

    def cancel_dependents(self, failed_package_id: str) -> list[str]:
        """Cancel all packages that depend (transitively) on a failed package.

        Returns list of cancelled package_ids.
        """
        cancelled = []
        to_cancel: deque[str] = deque()

        # Find direct dependents
        for pid, status in self.package_statuses.items():
            if failed_package_id in status.depends_on and status.state in (
                PackageState.PENDING,
                PackageState.READY,
            ):
                to_cancel.append(pid)

        while to_cancel:
            pid = to_cancel.popleft()
            if self.package_statuses[pid].state == PackageState.CANCELLED:
                continue
            self.package_statuses[pid].state = PackageState.CANCELLED
            self.package_statuses[pid].error = f"Dependency {failed_package_id} failed"
            cancelled.append(pid)

            # Propagate to transitive dependents
            for other_pid, other_status in self.package_statuses.items():
                if pid in other_status.depends_on and other_status.state in (
                    PackageState.PENDING,
                    PackageState.READY,
                ):
                    to_cancel.append(other_pid)

        return sorted(cancelled)

    def get_status_summary(self) -> dict[str, Any]:
        """Return a summary of all package statuses."""
        counts: dict[str, int] = defaultdict(int)
        packages = {}
        for pid, status in self.package_statuses.items():
            counts[status.state.value] += 1
            packages[pid] = {
                "state": status.state.value,
                "task_id": status.task_id,
                "attempt": status.attempt,
                "error": status.error,
            }

        all_done = all(
            s.state in (PackageState.COMPLETED, PackageState.CANCELLED, PackageState.FAILED)
            for s in self.package_statuses.values()
        )

        return {
            "all_done": all_done,
            "counts": dict(counts),
            "packages": packages,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DAG Scheduler: Phase A preflight for parallel-implement-feature"
    )
    parser.add_argument("path", type=Path, help="Path to work-packages.yaml")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Base directory for resolving contract paths (default: parent of yaml)",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    scheduler = DAGScheduler(args.path, args.base_dir)
    result = scheduler.preflight()

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        status = "PASS" if result["valid"] else "FAIL"
        print(f"Phase A Preflight: {status}")

        for check_name, check_result in result["checks"].items():
            symbol = "pass" if check_result["passed"] else "FAIL"
            print(f"  [{symbol}] {check_name}")
            for err in check_result.get("errors", []):
                print(f"    {err}")
            for f in check_result.get("missing", []):
                print(f"    missing: {f}")

        if result["topo_order"]:
            print(f"\nExecution order: {' -> '.join(result['topo_order'])}")

        if result["submissions"]:
            print(f"\nTask submissions: {len(result['submissions'])}")
            for sub in result["submissions"]:
                deps = sub["depends_on_packages"]
                dep_str = f" (after: {', '.join(deps)})" if deps else " (root)"
                print(f"  {sub['package_id']}: {sub['task_type']}{dep_str}")

    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
