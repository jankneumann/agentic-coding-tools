"""Work queue service for Agent Coordinator.

Provides task assignment and tracking for multi-agent coordination.
Tasks are claimed atomically to prevent double-assignment.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from .config import get_config
from .db import get_db, SupabaseClient


@dataclass
class Task:
    """Represents a task in the work queue."""

    id: UUID
    task_type: str
    description: str
    status: str
    priority: int
    input_data: Optional[dict[str, Any]] = None
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    depends_on: list[UUID] = field(default_factory=list)
    deadline: Optional[datetime] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        def parse_dt(val: Any) -> Optional[datetime]:
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
    task_id: Optional[UUID] = None
    task_type: Optional[str] = None
    description: Optional[str] = None
    input_data: Optional[dict[str, Any]] = None
    priority: Optional[int] = None
    deadline: Optional[datetime] = None
    reason: Optional[str] = None  # Error reason if no task available

    @classmethod
    def from_dict(cls, data: dict) -> "ClaimResult":
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
    status: Optional[str] = None
    task_id: Optional[UUID] = None
    reason: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "CompleteResult":
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
    task_id: Optional[UUID] = None

    @classmethod
    def from_dict(cls, data: dict) -> "SubmitResult":
        task_id = None
        if data.get("task_id"):
            task_id = UUID(str(data["task_id"]))

        return cls(
            success=data["success"],
            task_id=task_id,
        )


class WorkQueueService:
    """Service for managing the work queue."""

    def __init__(self, db: Optional[SupabaseClient] = None):
        self._db = db

    @property
    def db(self) -> SupabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def claim(
        self,
        agent_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        task_types: Optional[list[str]] = None,
    ) -> ClaimResult:
        """Claim a task from the work queue.

        Atomically claims the highest-priority available task.
        Only returns tasks whose dependencies are satisfied.

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

        return ClaimResult.from_dict(result)

    async def complete(
        self,
        task_id: UUID,
        success: bool,
        result: Optional[dict[str, Any]] = None,
        error_message: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> CompleteResult:
        """Mark a task as completed.

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

        return CompleteResult.from_dict(result_data)

    async def submit(
        self,
        task_type: str,
        description: str,
        input_data: Optional[dict[str, Any]] = None,
        priority: int = 5,
        depends_on: Optional[list[UUID]] = None,
        deadline: Optional[datetime] = None,
    ) -> SubmitResult:
        """Submit a new task to the work queue.

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

        return SubmitResult.from_dict(result)

    async def get_pending(
        self,
        task_types: Optional[list[str]] = None,
        limit: int = 20,
    ) -> list[Task]:
        """Get pending tasks from the queue.

        Args:
            task_types: Filter by task types (None for all)
            limit: Maximum number of tasks to return

        Returns:
            List of pending tasks ordered by priority
        """
        query = f"status=eq.pending&order=priority.asc,created_at.asc&limit={limit}"

        if task_types:
            types_str = ",".join(task_types)
            query += f"&task_type=in.({types_str})"

        tasks = await self.db.query("work_queue", query)
        return [Task.from_dict(t) for t in tasks]

    async def get_task(self, task_id: UUID) -> Optional[Task]:
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
        agent_id: Optional[str] = None,
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

        query = f"claimed_by=eq.{agent}&order=claimed_at.desc"
        if not include_completed:
            query += "&status=in.(claimed,running)"

        tasks = await self.db.query("work_queue", query)
        return [Task.from_dict(t) for t in tasks]


# Global service instance
_work_queue_service: Optional[WorkQueueService] = None


def get_work_queue_service() -> WorkQueueService:
    """Get the global work queue service instance."""
    global _work_queue_service
    if _work_queue_service is None:
        _work_queue_service = WorkQueueService()
    return _work_queue_service
