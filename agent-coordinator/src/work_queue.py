"""Work queue service for Agent Coordinator.

Provides task assignment and tracking for multi-agent coordination.
Tasks are claimed atomically to prevent double-assignment.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from .audit import get_audit_service
from .config import get_config
from .db import DatabaseClient, get_db
from .telemetry import get_queue_meter, start_span

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100

# ---------------------------------------------------------------------------
# Lazy metric instruments — created on first use, None when OTel is disabled
# ---------------------------------------------------------------------------

_instruments: tuple[Any, ...] | None = None


def _ensure_instruments() -> tuple[Any, ...]:
    global _instruments
    if _instruments is None:
        meter = get_queue_meter()
        if meter is None:
            _instruments = (None,) * 5
        else:
            _instruments = (
                meter.create_histogram(
                    "queue.claim.duration_ms",
                    unit="ms",
                    description="Task claim latency",
                ),
                meter.create_histogram(
                    "queue.wait_time_ms",
                    unit="ms",
                    description="Time from submit to claim",
                ),
                meter.create_histogram(
                    "queue.task.duration_ms",
                    unit="ms",
                    description="Time from claim to completion",
                ),
                meter.create_counter(
                    "queue.submit.total",
                    unit="1",
                    description="Task submissions",
                ),
                meter.create_counter(
                    "queue.guardrail_block.total",
                    unit="1",
                    description="Tasks blocked by guardrails",
                ),
            )
    return _instruments


@dataclass
class Task:
    """Represents a task in the work queue."""

    id: UUID
    task_type: str
    description: str
    status: str
    priority: int
    input_data: dict[str, Any] | None = None
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None
    depends_on: list[UUID] = field(default_factory=list)
    deadline: datetime | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        def parse_dt(val: Any) -> datetime | None:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))

        depends_on = []
        if data.get("depends_on"):
            depends_on = [UUID(str(d)) for d in data["depends_on"]]

        return cls(
            id=UUID(str(data["id"])),
            task_type=data["task_type"],
            description=data["description"],
            status=data["status"],
            priority=data["priority"],
            input_data=data.get("input_data"),
            claimed_by=data.get("claimed_by"),
            claimed_at=parse_dt(data.get("claimed_at")),
            result=data.get("result"),
            error_message=data.get("error_message"),
            depends_on=depends_on,
            deadline=parse_dt(data.get("deadline")),
            created_at=parse_dt(data.get("created_at")),
            completed_at=parse_dt(data.get("completed_at")),
        )


@dataclass
class ClaimResult:
    """Result of attempting to claim a task."""

    success: bool
    task_id: UUID | None = None
    task_type: str | None = None
    description: str | None = None
    input_data: dict[str, Any] | None = None
    priority: int | None = None
    deadline: datetime | None = None
    reason: str | None = None  # Error reason if no task available

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClaimResult":
        deadline = None
        if data.get("deadline"):
            deadline = datetime.fromisoformat(
                str(data["deadline"]).replace("Z", "+00:00")
            )

        task_id = None
        if data.get("task_id"):
            task_id = UUID(str(data["task_id"]))

        return cls(
            success=data["success"],
            task_id=task_id,
            task_type=data.get("task_type"),
            description=data.get("description"),
            input_data=data.get("input_data"),
            priority=data.get("priority"),
            deadline=deadline,
            reason=data.get("reason"),
        )


@dataclass
class CompleteResult:
    """Result of completing a task."""

    success: bool
    status: str | None = None
    task_id: UUID | None = None
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompleteResult":
        task_id = None
        if data.get("task_id"):
            task_id = UUID(str(data["task_id"]))

        return cls(
            success=data["success"],
            status=data.get("status"),
            task_id=task_id,
            reason=data.get("reason"),
        )


@dataclass
class SubmitResult:
    """Result of submitting a new task."""

    success: bool
    task_id: UUID | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubmitResult":
        task_id = None
        if data.get("task_id"):
            task_id = UUID(str(data["task_id"]))

        return cls(
            success=data["success"],
            task_id=task_id,
        )


class WorkQueueService:
    """Service for managing the work queue."""

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def _resolve_trust_level(self, agent_id: str, agent_type: str) -> int:
        """Resolve effective trust level for guardrail evaluation."""
        from .profiles import get_profiles_service

        try:
            profile = await get_profiles_service().get_profile(
                agent_id=agent_id,
                agent_type=agent_type,
            )
            if profile.success and profile.profile is not None:
                return profile.profile.trust_level
        except Exception:
            logger.debug("Failed to resolve trust level; using default", exc_info=True)
        return get_config().profiles.default_trust_level

    async def claim(
        self,
        agent_id: str | None = None,
        agent_type: str | None = None,
        task_types: list[str] | None = None,
    ) -> ClaimResult:
        """Claim a task from the work queue.

        Atomically claims the highest-priority available task.
        Only returns tasks whose dependencies are satisfied.
        Runs guardrail checks on the task description and input_data
        before returning; blocks claim if destructive patterns are found.

        Args:
            agent_id: Agent claiming the task (default: from config)
            agent_type: Type of agent (default: from config)
            task_types: Only claim these types of tasks (None for any)

        Returns:
            ClaimResult with task details or failure reason
        """
        config = get_config()
        resolved_agent_id = agent_id or config.agent.agent_id
        resolved_agent_type = agent_type or config.agent.agent_type

        claim_duration_hist, wait_time_hist, _, _, guardrail_counter = (
            _ensure_instruments()
        )

        with start_span("queue.claim", {"agent_id": resolved_agent_id}):
            from .policy_engine import get_policy_engine

            decision = await get_policy_engine().check_operation(
                agent_id=resolved_agent_id,
                agent_type=resolved_agent_type,
                operation="get_work",
                context={"task_types": task_types or []},
            )
            if not decision.allowed:
                return ClaimResult(
                    success=False,
                    reason=decision.reason or "operation_not_permitted",
                )

            t0 = time.monotonic()
            outcome = "claimed"
            task_type_label = "unknown"
            try:
                result = await self.db.rpc(
                    "claim_task",
                    {
                        "p_agent_id": resolved_agent_id,
                        "p_agent_type": resolved_agent_type,
                        "p_task_types": task_types,
                    },
                )
                claim_result = ClaimResult.from_dict(result)
                if claim_result.success:
                    task_type_label = claim_result.task_type or "unknown"
                else:
                    outcome = "empty"
                    task_type_label = claim_result.task_type or "unknown"
            except Exception:
                outcome = "error"
                duration_ms = (time.monotonic() - t0) * 1000
                try:
                    if claim_duration_hist is not None:
                        claim_duration_hist.record(
                            duration_ms,
                            {"task_type": "unknown", "outcome": "error"},
                        )
                except Exception:
                    pass
                raise
            duration_ms = (time.monotonic() - t0) * 1000

            # Record claim duration metric
            try:
                if claim_duration_hist is not None:
                    claim_duration_hist.record(
                        duration_ms,
                        {"task_type": task_type_label, "outcome": outcome},
                    )
            except Exception:
                logger.debug("Failed to record claim duration metric", exc_info=True)

            # Record wait time (time from created_at to now) if available
            if claim_result.success and result.get("created_at"):
                try:
                    if wait_time_hist is not None:
                        created_at_str = str(result["created_at"]).replace(
                            "Z", "+00:00"
                        )
                        created_at = datetime.fromisoformat(created_at_str)
                        now = datetime.now(UTC)
                        wait_ms = (now - created_at).total_seconds() * 1000
                        if wait_ms >= 0:
                            wait_time_hist.record(
                                wait_ms,
                                {
                                    "task_type": task_type_label,
                                    "priority": str(claim_result.priority or 5),
                                },
                            )
                except Exception:
                    logger.debug("Failed to record wait time metric", exc_info=True)

            # Guardrails pre-execution check on claimed task description/input
            if claim_result.success:
                try:
                    from .guardrails import get_guardrails_service

                    guardrails = get_guardrails_service()
                    trust_level = await self._resolve_trust_level(
                        resolved_agent_id, resolved_agent_type
                    )
                    scan_text = claim_result.description or ""
                    if claim_result.input_data:
                        scan_text += "\n" + str(claim_result.input_data)
                    if scan_text.strip():
                        check = await guardrails.check_operation(
                            operation_text=scan_text[:2000],
                            agent_id=resolved_agent_id,
                            agent_type=resolved_agent_type,
                            trust_level=trust_level,
                        )
                        if not check.safe:
                            patterns = [
                                v.pattern_name
                                for v in check.violations
                                if v.blocked
                            ]
                            # Record guardrail block counter
                            try:
                                if guardrail_counter is not None:
                                    guardrail_counter.add(
                                        1,
                                        {
                                            "pattern": patterns[0]
                                            if patterns
                                            else "unknown"
                                        },
                                    )
                            except Exception:
                                logger.debug(
                                    "Failed to record guardrail block metric",
                                    exc_info=True,
                                )
                            # Release the DB claim so the task doesn't stay
                            # stuck in "claimed" with no agent to work it.
                            if claim_result.task_id:
                                try:
                                    msg = (
                                        "Blocked by guardrails: "
                                        f"{', '.join(patterns)}"
                                    )
                                    await self.db.rpc(
                                        "complete_task",
                                        {
                                            "p_task_id": str(
                                                claim_result.task_id
                                            ),
                                            "p_agent_id": resolved_agent_id,
                                            "p_success": False,
                                            "p_result": None,
                                            "p_error_message": msg,
                                        },
                                    )
                                except Exception:
                                    logger.error(
                                        "Failed to release guardrail-blocked task %s",
                                        claim_result.task_id,
                                        exc_info=True,
                                    )
                            return ClaimResult(
                                success=False,
                                reason=(
                                    "destructive_operation_blocked: "
                                    f"{', '.join(patterns)}"
                                ),
                            )
                except Exception:
                    logger.error(
                        "Guardrails check failed during claim", exc_info=True
                    )

            try:
                await get_audit_service().log_operation(
                    agent_id=resolved_agent_id,
                    operation="claim_task",
                    parameters={"task_types": task_types},
                    result={
                        "task_id": str(claim_result.task_id)
                        if claim_result.task_id
                        else None
                    },
                    success=claim_result.success,
                )
            except Exception:
                logger.warning("Audit log failed for claim_task", exc_info=True)

            return claim_result

    async def complete(
        self,
        task_id: UUID,
        success: bool,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
        agent_id: str | None = None,
    ) -> CompleteResult:
        """Mark a task as completed.

        Defense-in-depth: scans the result payload for destructive patterns.
        This supplements the pre-execution checks in claim() and submit(),
        catching cases where an agent produces destructive output not
        present in the original task description.

        Args:
            task_id: ID of the task to complete
            success: Whether the task completed successfully
            result: Output data from the task (for success)
            error_message: What went wrong (for failure)
            agent_id: Agent completing the task (default: from config)

        Returns:
            CompleteResult indicating success/failure
        """
        config = get_config()
        resolved_agent_id = agent_id or config.agent.agent_id
        resolved_agent_type = config.agent.agent_type

        _, _, task_duration_hist, _, _ = _ensure_instruments()

        with start_span("queue.complete", {"task_id": str(task_id)}):
            from .policy_engine import get_policy_engine

            decision = await get_policy_engine().check_operation(
                agent_id=resolved_agent_id,
                agent_type=resolved_agent_type,
                operation="complete_work",
                resource=str(task_id),
                context={"success": success},
            )
            if not decision.allowed:
                return CompleteResult(
                    success=False,
                    status="blocked",
                    task_id=task_id,
                    reason=decision.reason or "operation_not_permitted",
                )

            # Guardrails pre-execution check on task result
            if success and result:
                try:
                    from .guardrails import get_guardrails_service

                    guardrails = get_guardrails_service()
                    trust_level = await self._resolve_trust_level(
                        resolved_agent_id, resolved_agent_type
                    )
                    result_text = str(result)
                    check = await guardrails.check_operation(
                        operation_text=result_text[:2000],
                        agent_id=resolved_agent_id,
                        agent_type=resolved_agent_type,
                        trust_level=trust_level,
                    )
                    if not check.safe:
                        patterns = [
                            v.pattern_name for v in check.violations if v.blocked
                        ]
                        return CompleteResult(
                            success=False,
                            status="blocked",
                            task_id=task_id,
                            reason=(
                                "destructive_operation_blocked: "
                                f"{', '.join(patterns)}"
                            ),
                        )
                except Exception:
                    logger.error(
                        "Guardrails check failed during complete", exc_info=True
                    )

            # Look up the task for claimed_at to compute task duration
            task_type_label = "unknown"
            claimed_at_snapshot = None
            try:
                task_obj = await self.get_task(task_id)
                if task_obj is not None:
                    task_type_label = task_obj.task_type
                    claimed_at_snapshot = task_obj.claimed_at
            except Exception:
                logger.debug(
                    "Failed to fetch task for duration metric", exc_info=True
                )

            result_data = await self.db.rpc(
                "complete_task",
                {
                    "p_task_id": str(task_id),
                    "p_agent_id": resolved_agent_id,
                    "p_success": success,
                    "p_result": result,
                    "p_error_message": error_message,
                },
            )

            complete_result = CompleteResult.from_dict(result_data)

            # Record task duration only after completion succeeds
            if (
                complete_result.success
                and claimed_at_snapshot is not None
                and task_duration_hist is not None
            ):
                try:
                    now = datetime.now(UTC)
                    claimed_at = claimed_at_snapshot
                    if claimed_at.tzinfo is None:
                        claimed_at = claimed_at.replace(tzinfo=UTC)
                    task_dur_ms = (now - claimed_at).total_seconds() * 1000
                    if task_dur_ms >= 0:
                        task_duration_hist.record(
                            task_dur_ms,
                            {
                                "task_type": task_type_label,
                                "outcome": "completed" if success else "failed",
                            },
                        )
                except Exception:
                    logger.debug(
                        "Failed to record task duration metric", exc_info=True
                    )

            try:
                await get_audit_service().log_operation(
                    agent_id=resolved_agent_id,
                    operation="complete_task",
                    parameters={
                        "task_id": str(task_id),
                        "success": success,
                    },
                    success=complete_result.success,
                )
            except Exception:
                logger.warning(
                    "Audit log failed for complete_task", exc_info=True
                )

            return complete_result

    async def submit(
        self,
        task_type: str,
        description: str,
        input_data: dict[str, Any] | None = None,
        priority: int = 5,
        depends_on: list[UUID] | None = None,
        deadline: datetime | None = None,
    ) -> SubmitResult:
        """Submit a new task to the work queue.

        Runs guardrail checks on the task description and input_data before
        persisting. Rejects submissions containing destructive patterns.

        Args:
            task_type: Category of task (e.g., 'summarize', 'refactor', 'test')
            description: What needs to be done
            input_data: Data needed to complete the task
            priority: 1 (highest) to 10 (lowest), default 5
            depends_on: Task IDs that must complete first
            deadline: When the task needs to be done by

        Returns:
            SubmitResult with the new task ID
        """
        config = get_config()
        resolved_agent_id = config.agent.agent_id
        resolved_agent_type = config.agent.agent_type

        _, _, _, submit_counter, _ = _ensure_instruments()

        with start_span("queue.submit", {"task_type": task_type}):
            from .policy_engine import get_policy_engine

            decision = await get_policy_engine().check_operation(
                agent_id=resolved_agent_id,
                agent_type=resolved_agent_type,
                operation="submit_work",
                context={
                    "task_type": task_type,
                    "priority": priority,
                    "has_dependencies": bool(depends_on),
                },
            )
            if not decision.allowed:
                return SubmitResult(success=False, task_id=None)

            # Guardrails check on submitted task content
            try:
                from .guardrails import get_guardrails_service

                guardrails = get_guardrails_service()
                trust_level = await self._resolve_trust_level(
                    resolved_agent_id, resolved_agent_type
                )
                scan_text = description
                if input_data:
                    scan_text += "\n" + str(input_data)
                check = await guardrails.check_operation(
                    operation_text=scan_text[:2000],
                    agent_id=resolved_agent_id,
                    agent_type=resolved_agent_type,
                    trust_level=trust_level,
                )
                if not check.safe:
                    return SubmitResult(
                        success=False,
                        task_id=None,
                    )
            except Exception:
                logger.error(
                    "Guardrails check failed during submit", exc_info=True
                )

            depends_on_str = None
            if depends_on:
                depends_on_str = [str(d) for d in depends_on]

            deadline_str = None
            if deadline:
                deadline_str = deadline.isoformat()

            result = await self.db.rpc(
                "submit_task",
                {
                    "p_task_type": task_type,
                    "p_description": description,
                    "p_input_data": input_data,
                    "p_priority": priority,
                    "p_depends_on": depends_on_str,
                    "p_deadline": deadline_str,
                },
            )

            submit_result = SubmitResult.from_dict(result)

            # Record submit counter metric
            try:
                if submit_counter is not None:
                    submit_counter.add(1, {"task_type": task_type})
            except Exception:
                logger.debug(
                    "Failed to record submit counter metric", exc_info=True
                )

            try:
                await get_audit_service().log_operation(
                    operation="submit_task",
                    parameters={
                        "task_type": task_type,
                        "priority": priority,
                    },
                    result={
                        "task_id": str(submit_result.task_id)
                        if submit_result.task_id
                        else None
                    },
                    success=submit_result.success,
                )
            except Exception:
                logger.warning(
                    "Audit log failed for submit_task", exc_info=True
                )

            return submit_result

    async def get_pending(
        self,
        task_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[Task]:
        """Get pending tasks from the queue.

        Args:
            task_types: Filter by task types (None for all)
            limit: Maximum number of tasks to return (capped at MAX_PAGE_SIZE)

        Returns:
            List of pending tasks ordered by priority
        """
        limit = min(limit, MAX_PAGE_SIZE)
        query = f"status=eq.pending&order=priority.asc,created_at.asc&limit={limit}"

        if task_types:
            types_str = ",".join(task_types)
            query += f"&task_type=in.({types_str})"

        tasks = await self.db.query("work_queue", query)
        return [Task.from_dict(t) for t in tasks]

    async def get_task(self, task_id: UUID) -> Task | None:
        """Get a specific task by ID.

        Args:
            task_id: Task ID to retrieve

        Returns:
            Task if found, None otherwise
        """
        tasks = await self.db.query("work_queue", f"id=eq.{task_id}")
        return Task.from_dict(tasks[0]) if tasks else None

    async def get_my_tasks(
        self,
        agent_id: str | None = None,
        include_completed: bool = False,
    ) -> list[Task]:
        """Get tasks claimed by this agent.

        Args:
            agent_id: Agent ID (default: from config)
            include_completed: Whether to include completed tasks

        Returns:
            List of tasks claimed by the agent
        """
        config = get_config()
        agent = agent_id or config.agent.agent_id

        query = f"claimed_by=eq.{agent}&order=claimed_at.desc&limit={MAX_PAGE_SIZE}"
        if not include_completed:
            query += "&status=in.(claimed,running)"

        tasks = await self.db.query("work_queue", query)
        return [Task.from_dict(t) for t in tasks]

    async def cancel_task_convention(
        self,
        task_id: UUID,
        reason: str,
        agent_id: str | None = None,
    ) -> CompleteResult:
        """Cancel a task using the orchestrator cancellation convention.

        Calls complete(success=False) with error_code="cancelled_by_orchestrator"
        in the result payload. This is the standard way for an orchestrator to
        signal that a task should be abandoned.

        Args:
            task_id: ID of the task to cancel
            reason: Human-readable reason for cancellation
            agent_id: Agent performing the cancellation (default: from config)

        Returns:
            CompleteResult indicating whether the cancellation was recorded
        """
        return await self.complete(
            task_id=task_id,
            success=False,
            result={"error_code": "cancelled_by_orchestrator", "reason": reason},
            error_message=f"Cancelled by orchestrator: {reason}",
            agent_id=agent_id,
        )


# Global service instance
_work_queue_service: WorkQueueService | None = None


def get_work_queue_service() -> WorkQueueService:
    """Get the global work queue service instance."""
    global _work_queue_service
    if _work_queue_service is None:
        _work_queue_service = WorkQueueService()
    return _work_queue_service


def reset_instruments() -> None:
    """Reset cached metric instruments. For testing only."""
    global _instruments
    _instruments = None
