"""Circuit breaker for parallel-implement-feature.

Detects stuck agents via heartbeat timeout, enforces retry budgets,
and propagates cancellation to dependent packages when a package
exhausts its retry budget.

Usage:
    from circuit_breaker import CircuitBreaker

    breaker = CircuitBreaker(
        packages=work_packages_data["packages"],
        default_timeout_minutes=60,
        default_retry_budget=1,
    )

    # Register heartbeat
    breaker.heartbeat("wp-backend")

    # Check for stuck packages
    stuck = breaker.check_stuck_packages()

    # Check retry budget
    can_retry = breaker.can_retry("wp-backend")
    breaker.record_attempt("wp-backend")
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any


class CircuitBreaker:
    """Monitors agent health and enforces retry budgets.

    The circuit breaker runs on the orchestrator side and tracks:
    - Last heartbeat time per package (from discover_agents or get_task polling)
    - Attempt count per package (incremented on each retry)
    - Retry budget per package (from work-packages.yaml)
    - Timeout per package (from work-packages.yaml)
    """

    def __init__(
        self,
        packages: list[dict[str, Any]],
        default_timeout_minutes: int = 60,
        default_retry_budget: int = 1,
    ):
        self._packages = {p["package_id"]: p for p in packages}
        self._default_timeout = default_timeout_minutes
        self._default_retry_budget = default_retry_budget
        self._heartbeats: dict[str, datetime] = {}
        self._attempt_counts: dict[str, int] = defaultdict(int)
        self._tripped: set[str] = set()

    def get_timeout_minutes(self, package_id: str) -> int:
        """Get the timeout for a package."""
        pkg = self._packages.get(package_id, {})
        return pkg.get("timeout_minutes", self._default_timeout)

    def get_retry_budget(self, package_id: str) -> int:
        """Get the retry budget for a package."""
        pkg = self._packages.get(package_id, {})
        return pkg.get("retry_budget", self._default_retry_budget)

    def heartbeat(self, package_id: str, timestamp: datetime | None = None) -> None:
        """Record a heartbeat for a package.

        Called when the orchestrator detects activity from a package's agent
        (e.g., via discover_agents() or get_task() polling).
        """
        self._heartbeats[package_id] = timestamp or datetime.now(timezone.utc)

    def start_monitoring(self, package_id: str) -> None:
        """Start monitoring a package (records initial heartbeat)."""
        self.heartbeat(package_id)

    def check_stuck_packages(
        self, now: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Check for packages that have exceeded their timeout.

        Returns list of dicts with package_id, last_heartbeat, timeout_minutes,
        and elapsed_minutes for each stuck package.
        """
        now = now or datetime.now(timezone.utc)
        stuck = []

        for pid, last_hb in self._heartbeats.items():
            if pid in self._tripped:
                continue
            timeout = self.get_timeout_minutes(pid)
            elapsed = (now - last_hb).total_seconds() / 60
            if elapsed > timeout:
                stuck.append({
                    "package_id": pid,
                    "last_heartbeat": last_hb.isoformat(),
                    "timeout_minutes": timeout,
                    "elapsed_minutes": round(elapsed, 1),
                })

        return stuck

    def record_attempt(self, package_id: str) -> None:
        """Record a retry attempt for a package."""
        self._attempt_counts[package_id] += 1

    def get_attempt_count(self, package_id: str) -> int:
        """Get the current attempt count for a package."""
        return self._attempt_counts[package_id]

    def can_retry(self, package_id: str) -> bool:
        """Check if a package has remaining retry budget.

        Returns True if attempt_count <= retry_budget.
        (First attempt = 0, first retry = 1, etc.)
        """
        budget = self.get_retry_budget(package_id)
        return self._attempt_counts[package_id] < budget

    def trip(self, package_id: str) -> None:
        """Trip the circuit breaker for a package.

        Called when a package exhausts its retry budget or when the
        orchestrator decides to permanently fail the package.
        Prevents further heartbeat monitoring.
        """
        self._tripped.add(package_id)

    def is_tripped(self, package_id: str) -> bool:
        """Check if a package's circuit breaker has been tripped."""
        return package_id in self._tripped

    def get_dependent_packages(self, failed_package_id: str) -> list[str]:
        """Get packages that depend (directly) on the failed package.

        Used for cancellation propagation.
        """
        dependents = []
        for pid, pkg in self._packages.items():
            if failed_package_id in pkg.get("depends_on", []):
                dependents.append(pid)
        return sorted(dependents)

    def get_transitive_dependents(self, failed_package_id: str) -> list[str]:
        """Get all packages that depend transitively on the failed package."""
        visited: set[str] = set()
        queue = [failed_package_id]

        while queue:
            current = queue.pop(0)
            for pid, pkg in self._packages.items():
                if current in pkg.get("depends_on", []) and pid not in visited:
                    visited.add(pid)
                    queue.append(pid)

        return sorted(visited)

    def get_status_summary(self) -> dict[str, Any]:
        """Return a summary of circuit breaker state."""
        return {
            "monitored": len(self._heartbeats),
            "tripped": sorted(self._tripped),
            "attempt_counts": dict(self._attempt_counts),
            "packages": {
                pid: {
                    "last_heartbeat": self._heartbeats.get(pid, "").isoformat()
                    if pid in self._heartbeats
                    else None,
                    "attempts": self._attempt_counts[pid],
                    "retry_budget": self.get_retry_budget(pid),
                    "timeout_minutes": self.get_timeout_minutes(pid),
                    "tripped": pid in self._tripped,
                }
                for pid in self._packages
            },
        }
