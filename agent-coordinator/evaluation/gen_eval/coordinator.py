"""Optional coordinator integration for distributed scenario execution.

When the agent-coordinator service is available, this module enables:
- Distributing scenarios as work queue tasks across agents
- Storing evaluation findings in coordinator memory
- Recalling previous findings for regression detection

All methods degrade gracefully when the coordinator is unavailable,
returning empty results and logging an info-level message.
"""

from __future__ import annotations

import logging
from typing import Any

from evaluation.gen_eval.models import EvalFeedback, Scenario

logger = logging.getLogger(__name__)

# Default timeout for coordinator HTTP calls (seconds)
_DEFAULT_TIMEOUT = 10.0


class CoordinatorIntegration:
    """Optional coordinator integration for distributed scenario execution.

    When the coordinator is reachable, scenarios can be submitted as work
    queue tasks and findings stored in coordinator memory. When unavailable,
    all methods return gracefully with empty results.
    """

    def __init__(
        self,
        coordinator_url: str = "http://localhost:8081",
        api_key: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.url = coordinator_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._available: bool | None = None
        self._client: Any | None = None

    async def __aenter__(self) -> CoordinatorIntegration:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()

    async def _ensure_client(self) -> Any:
        """Lazily create an httpx.AsyncClient."""
        if self._client is None:
            import httpx

            headers: dict[str, str] = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            self._client = httpx.AsyncClient(
                base_url=self.url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    async def is_available(self) -> bool:
        """Check if coordinator is reachable.

        Caches the result after first successful/failed check.
        Call ``reset()`` to force re-check.
        """
        if self._available is not None:
            return self._available

        try:
            client = await self._ensure_client()
            resp = await client.get("/health")
            self._available = resp.status_code == 200
        except Exception:
            logger.info("Coordinator not available at %s", self.url)
            self._available = False

        return self._available

    async def distribute_scenarios(self, scenarios: list[Scenario]) -> list[str]:
        """Submit scenarios as work queue tasks.

        Returns a list of task IDs for the submitted scenarios.
        Returns an empty list if the coordinator is unavailable.
        """
        if not await self.is_available():
            logger.info("Coordinator unavailable; skipping scenario distribution")
            return []

        task_ids: list[str] = []
        client = await self._ensure_client()

        for scenario in scenarios:
            try:
                resp = await client.post(
                    "/work/submit",
                    json={
                        "task_type": "gen-eval-scenario",
                        "description": f"Evaluate scenario: {scenario.name}",
                        "metadata": {
                            "scenario_id": scenario.id,
                            "category": scenario.category,
                            "priority": scenario.priority,
                        },
                        "priority": scenario.priority,
                    },
                )
                if resp.is_success:
                    data = resp.json()
                    task_id = data.get("task_id", "")
                    if task_id:
                        task_ids.append(task_id)
                else:
                    logger.warning(
                        "Failed to submit scenario %s: HTTP %d",
                        scenario.id,
                        resp.status_code,
                    )
            except Exception as exc:
                logger.warning("Error submitting scenario %s: %s", scenario.id, exc)

        logger.info(
            "Distributed %d/%d scenarios to coordinator",
            len(task_ids),
            len(scenarios),
        )
        return task_ids

    async def store_findings(self, report: Any) -> None:
        """Store evaluation findings in coordinator memory.

        Stores a summary of the gen-eval report as an episodic memory
        entry. Does nothing if the coordinator is unavailable.
        """
        if not await self.is_available():
            logger.info("Coordinator unavailable; skipping findings storage")
            return

        try:
            client = await self._ensure_client()
            summary = _build_findings_summary(report)
            await client.post(
                "/memory/store",
                json={
                    "event_type": "gen_eval_findings",
                    "summary": summary,
                    "tags": ["gen-eval", "evaluation", "findings"],
                    "metadata": {
                        "total_scenarios": getattr(report, "total_scenarios", 0),
                        "pass_rate": getattr(report, "pass_rate", 0.0),
                        "coverage_pct": getattr(report, "coverage_pct", 0.0),
                    },
                },
            )
            logger.info("Stored gen-eval findings in coordinator memory")
        except Exception as exc:
            logger.warning("Failed to store findings: %s", exc)

    async def recall_previous_findings(self, project: str) -> list[EvalFeedback]:
        """Recall findings from previous runs.

        Queries coordinator memory for past gen-eval findings and converts
        them to EvalFeedback objects. Returns an empty list if the
        coordinator is unavailable or no findings are found.
        """
        if not await self.is_available():
            logger.info("Coordinator unavailable; skipping findings recall")
            return []

        try:
            client = await self._ensure_client()
            resp = await client.post(
                "/memory/query",
                json={
                    "tags": ["gen-eval", "findings"],
                    "event_type": "gen_eval_findings",
                    "limit": 10,
                },
            )
            if resp.status_code != 200:
                logger.warning("Failed to recall findings: HTTP %d", resp.status_code)
                return []

            data = resp.json()
            memories = data.get("memories", [])
            feedbacks: list[EvalFeedback] = []

            for i, memory in enumerate(memories):
                metadata = memory.get("metadata", {})
                feedbacks.append(
                    EvalFeedback(
                        iteration=i + 1,
                        failing_interfaces=metadata.get("failing_interfaces", []),
                        under_tested_categories=metadata.get("under_tested_categories", []),
                        coverage_summary=metadata.get("coverage_summary", {}),
                    )
                )

            logger.info("Recalled %d previous findings", len(feedbacks))
            return feedbacks

        except Exception as exc:
            logger.warning("Failed to recall findings: %s", exc)
            return []

    def reset(self) -> None:
        """Reset availability cache to force re-check."""
        self._available = None

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _build_findings_summary(report: Any) -> str:
    """Build a human-readable summary from a GenEvalReport."""
    total = getattr(report, "total_scenarios", 0)
    passed = getattr(report, "passed", 0)
    failed = getattr(report, "failed", 0)
    errors = getattr(report, "errors", 0)
    pass_rate = getattr(report, "pass_rate", 0.0)
    coverage = getattr(report, "coverage_pct", 0.0)

    return (
        f"Gen-eval run: {total} scenarios, "
        f"{passed} passed, {failed} failed, {errors} errors. "
        f"Pass rate: {pass_rate:.1%}, Coverage: {coverage:.1f}%"
    )
