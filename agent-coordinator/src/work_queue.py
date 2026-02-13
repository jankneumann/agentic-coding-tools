"""Work queue service for Agent Coordinator.

Provides task assignment and tracking for multi-agent coordination.
Tasks are claimed atomically to prevent double-assignment.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from .audit import get_audit_service
from .config import get_config
from .db import DatabaseClient, get_db

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100


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

        result = await self.db.rpc(
            "claim_task",
            {
                "p_agent_id": agent_id or config.agent.agent_id,
                "p_agent_type": agent_type or config.agent.agent_type,
                "p_task_types": task_types,
            },
        )

        claim_result = ClaimResult.from_dict(result)

        # Guardrails pre-execution check on claimed task description/input
        if claim_result.success:
            try:
                from .guardrails import get_guardrails_service

                guardrails = get_guardrails_service()
                scan_text = claim_result.description or ""
                if claim_result.input_data:
                    scan_text += "\n" + str(claim_result.input_data)
                if scan_text.strip():
                    check = await guardrails.check_operation(
                        operation_text=scan_text[:2000],
                        agent_id=agent_id or config.agent.agent_id,
                    )
                    if not check.safe:
                        patterns = [
                            v.pattern_name for v in check.violations if v.blocked
                        ]
                        return ClaimResult(
                            success=False,
                            reason=f"destructive_operation_blocked: {', '.join(patterns)}",
                        )
            except Exception:
                logger.error("Guardrails check failed during claim", exc_info=True)

        try:
            await get_audit_service().log_operation(
                agent_id=agent_id or config.agent.agent_id,
                operation="claim_task",
                parameters={"task_types": task_types},
                result={
                    "task_id": str(claim_result.task_id)
                    if claim_result.task_id else None
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

        # Guardrails pre-execution check on task result
        if success and result:
            try:
                from .guardrails import get_guardrails_service

                guardrails = get_guardrails_service()
                result_text = str(result)
                check = await guardrails.check_operation(
                    operation_text=result_text[:2000],
                    agent_id=agent_id or config.agent.agent_id,
                )
                if not check.safe:
                    patterns = [v.pattern_name for v in check.violations if v.blocked]
                    return CompleteResult(
                        success=False,
                        status="blocked",
                        task_id=task_id,
                        reason=f"destructive_operation_blocked: {', '.join(patterns)}",
                    )
            except Exception:
                logger.error("Guardrails check failed during complete", exc_info=True)

        result_data = await self.db.rpc(
            "complete_task",
            {
                "p_task_id": str(task_id),
                "p_agent_id": agent_id or config.agent.agent_id,
                "p_success": success,
                "p_result": result,
                "p_error_message": error_message,
            },
        )

        complete_result = CompleteResult.from_dict(result_data)

        try:
            await get_audit_service().log_operation(
                agent_id=agent_id or config.agent.agent_id,
                operation="complete_task",
                parameters={
                    "task_id": str(task_id),
                    "success": success,
                },
                success=complete_result.success,
            )
        except Exception:
            logger.warning("Audit log failed for complete_task", exc_info=True)

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
        # Guardrails check on submitted task content
        try:
            from .guardrails import get_guardrails_service

            guardrails = get_guardrails_service()
            scan_text = description
            if input_data:
                scan_text += "\n" + str(input_data)
            check = await guardrails.check_operation(
                operation_text=scan_text[:2000],
            )
            if not check.safe:
                return SubmitResult(
                    success=False,
                    task_id=None,
                )
        except Exception:
            logger.error("Guardrails check failed during submit", exc_info=True)

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

        try:
            await get_audit_service().log_operation(
                operation="submit_task",
                parameters={
                    "task_type": task_type,
                    "priority": priority,
                },
                result={
                    "task_id": str(submit_result.task_id)
                    if submit_result.task_id else None
                },
                success=submit_result.success,
            )
        except Exception:
            logger.warning("Audit log failed for submit_task", exc_info=True)

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


# Global service instance
_work_queue_service: WorkQueueService | None = None


def get_work_queue_service() -> WorkQueueService:
    """Get the global work queue service instance."""
    global _work_queue_service
    if _work_queue_service is None:
        _work_queue_service = WorkQueueService()
    return _work_queue_service
