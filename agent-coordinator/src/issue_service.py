"""Issue tracking service for Agent Coordinator.

Extends the work_queue table with issue-tracking features: labels, epics,
comments, hierarchy, and human-friendly status mapping. Issues use
task_type='issue' to avoid being accidentally claimed by get_work().

This service delegates to DatabaseClient directly (not WorkQueueService)
to avoid inheriting agent-coordination semantics (policy checks, guardrails)
that are inappropriate for issue CRUD.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from .config import get_config
from .db import DatabaseClient, get_db

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100

# Maps user-friendly status names to work_queue status values
STATUS_MAP: dict[str, list[str]] = {
    "open": ["pending", "claimed"],
    "in_progress": ["running"],
    "closed": ["completed"],
    "all": ["pending", "claimed", "running", "completed", "failed", "cancelled"],
}

# Maps user-friendly status to stored status for writes
STATUS_WRITE_MAP: dict[str, str] = {
    "open": "pending",
    "in_progress": "running",
    "closed": "completed",
}

VALID_ISSUE_TYPES = {"task", "epic", "bug", "feature"}


@dataclass
class Issue:
    """Represents an issue in the tracker."""

    id: UUID
    title: str
    description: str | None
    status: str
    priority: int
    issue_type: str
    labels: list[str]
    assignee: str | None = None
    parent_id: UUID | None = None
    depends_on: list[UUID] = field(default_factory=list)
    created_at: datetime | None = None
    completed_at: datetime | None = None
    closed_at: datetime | None = None
    close_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list[dict[str, Any]] | None = None
    comments: list[dict[str, Any]] | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Issue:
        def parse_dt(val: Any) -> datetime | None:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))

        depends_on: list[UUID] = []
        if row.get("depends_on"):
            depends_on = [UUID(str(d)) for d in row["depends_on"]]

        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return cls(
            id=UUID(str(row["id"])),
            title=row["description"],  # work_queue.description = issue title
            description=metadata.get("body"),
            status=row["status"],
            priority=row.get("priority", 5),
            issue_type=row.get("issue_type", "task"),
            labels=row.get("labels") or [],
            assignee=row.get("assignee"),
            parent_id=UUID(str(row["parent_id"])) if row.get("parent_id") else None,
            depends_on=depends_on,
            created_at=parse_dt(row.get("created_at")),
            completed_at=parse_dt(row.get("completed_at")),
            closed_at=parse_dt(row.get("closed_at")),
            close_reason=row.get("close_reason"),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "issue_type": self.issue_type,
            "labels": self.labels,
            "assignee": self.assignee,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "depends_on": [str(d) for d in self.depends_on],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "close_reason": self.close_reason,
            "metadata": self.metadata,
            "children": self.children,
            "comments": self.comments,
        }


@dataclass
class Comment:
    """Represents a comment on an issue."""

    id: UUID
    issue_id: UUID
    author: str
    body: str
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Comment:
        created_at = row.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return cls(
            id=UUID(str(row["id"])),
            issue_id=UUID(str(row["issue_id"])),
            author=row["author"],
            body=row["body"],
            created_at=created_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "issue_id": str(self.issue_id),
            "author": self.author,
            "body": self.body,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class IssueService:
    """Service for managing issues in the coordinator."""

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def create(
        self,
        title: str,
        description: str | None = None,
        issue_type: str = "task",
        priority: int = 5,
        labels: list[str] | None = None,
        parent_id: UUID | None = None,
        assignee: str | None = None,
        depends_on: list[UUID] | None = None,
    ) -> Issue:
        """Create a new issue.

        Args:
            title: Issue title
            description: Detailed description
            issue_type: task, epic, bug, or feature
            priority: 1 (highest) to 10 (lowest)
            labels: List of label strings
            parent_id: Parent issue UUID (for epic children)
            assignee: Who is assigned
            depends_on: Issue IDs that must complete first
        """
        if issue_type not in VALID_ISSUE_TYPES:
            raise ValueError(
                f"Invalid issue_type: {issue_type}. Must be one of {VALID_ISSUE_TYPES}"
            )
        if not 1 <= priority <= 10:
            raise ValueError(f"Priority must be 1-10, got {priority}")

        metadata: dict[str, Any] = {}
        if description:
            metadata["body"] = description

        data: dict[str, Any] = {
            "task_type": "issue",
            "description": title,
            "input_data": json.dumps(metadata) if metadata else None,
            "priority": priority,
            "status": "pending",
            "issue_type": issue_type,
            "labels": labels or [],
            "assignee": assignee,
            "metadata": json.dumps(metadata),
        }
        if parent_id:
            data["parent_id"] = str(parent_id)
        if depends_on:
            data["depends_on"] = [str(d) for d in depends_on]

        row = await self.db.insert("work_queue", data)
        return Issue.from_row(row)

    async def list_issues(
        self,
        status: str | None = None,
        issue_type: str | None = None,
        labels: list[str] | None = None,
        parent_id: UUID | None = None,
        assignee: str | None = None,
        limit: int = 50,
    ) -> list[Issue]:
        """List issues with optional filters.

        Args:
            status: Filter by friendly status (open, in_progress, closed, all)
            issue_type: Filter by type (task, epic, bug, feature)
            labels: Filter by labels (must contain ALL specified)
            parent_id: Filter by parent issue
            assignee: Filter by assignee
            limit: Max results (capped at 100)
        """
        limit = min(limit, MAX_PAGE_SIZE)

        # Build PostgREST-style query
        parts = [
            "task_type=eq.issue",
            "order=priority.asc,created_at.asc",
            f"limit={limit}",
        ]

        if status and status != "all":
            statuses = STATUS_MAP.get(status, [status])
            parts.append(f"status=in.({','.join(statuses)})")

        if issue_type:
            parts.append(f"issue_type=eq.{issue_type}")

        if parent_id:
            parts.append(f"parent_id=eq.{parent_id}")

        if assignee:
            parts.append(f"assignee=eq.{assignee}")

        query = "&".join(parts)
        rows = await self.db.query("work_queue", query)

        issues = [Issue.from_row(r) for r in rows]

        # Post-filter by labels (array containment not in PostgREST syntax)
        if labels:
            issues = [
                i for i in issues
                if all(label in i.labels for label in labels)
            ]

        return issues

    async def show(self, issue_id: UUID) -> Issue | None:
        """Get full issue details including comments and children.

        Args:
            issue_id: Issue UUID
        """
        rows = await self.db.query("work_queue", f"id=eq.{issue_id}")
        if not rows:
            return None

        issue = Issue.from_row(rows[0])

        # Load comments
        comment_rows = await self.db.query(
            "issue_comments",
            f"issue_id=eq.{issue_id}&order=created_at.asc",
        )
        issue.comments = [Comment.from_row(c).to_dict() for c in comment_rows]

        # Load children if this is an epic
        if issue.issue_type == "epic":
            child_rows = await self.db.query(
                "work_queue",
                f"parent_id=eq.{issue_id}&task_type=eq.issue&order=priority.asc",
            )
            issue.children = [
                {
                    "id": str(r["id"]),
                    "title": r["description"],
                    "status": r["status"],
                    "priority": r.get("priority", 5),
                    "issue_type": r.get("issue_type", "task"),
                }
                for r in child_rows
            ]

        return issue

    async def update(
        self,
        issue_id: UUID,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        labels: list[str] | None = None,
        assignee: str | None = None,
        issue_type: str | None = None,
    ) -> Issue | None:
        """Update issue fields.

        Args:
            issue_id: Issue UUID
            title: New title
            description: New description
            status: New status (open, in_progress, closed)
            priority: New priority (1-10)
            labels: Replace labels
            assignee: New assignee
            issue_type: New type
        """
        data: dict[str, Any] = {}

        if title is not None:
            data["description"] = title
        if status is not None:
            mapped = STATUS_WRITE_MAP.get(status, status)
            data["status"] = mapped
        if priority is not None:
            if not 1 <= priority <= 10:
                raise ValueError(f"Priority must be 1-10, got {priority}")
            data["priority"] = priority
        if labels is not None:
            data["labels"] = labels
        if assignee is not None:
            data["assignee"] = assignee
        if issue_type is not None:
            if issue_type not in VALID_ISSUE_TYPES:
                raise ValueError(f"Invalid issue_type: {issue_type}")
            data["issue_type"] = issue_type

        if description is not None:
            # Merge description into metadata
            existing = await self.db.query("work_queue", f"id=eq.{issue_id}")
            if not existing:
                return None
            metadata = existing[0].get("metadata") or {}
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            metadata["body"] = description
            data["metadata"] = json.dumps(metadata)

        if not data:
            # Nothing to update, just return current state
            rows = await self.db.query("work_queue", f"id=eq.{issue_id}")
            return Issue.from_row(rows[0]) if rows else None

        rows = await self.db.update(
            "work_queue",
            match={"id": issue_id},
            data=data,
        )
        return Issue.from_row(rows[0]) if rows else None

    async def close(
        self,
        issue_id: UUID | None = None,
        issue_ids: list[UUID] | None = None,
        reason: str | None = None,
    ) -> list[Issue]:
        """Close one or more issues.

        Args:
            issue_id: Single issue to close
            issue_ids: Multiple issues to close (batch)
            reason: Closure reason
        """
        ids = []
        if issue_id:
            ids.append(issue_id)
        if issue_ids:
            ids.extend(issue_ids)
        if not ids:
            raise ValueError("Must provide issue_id or issue_ids")

        now = datetime.now(UTC)
        results: list[Issue] = []

        for iid in ids:
            data: dict[str, Any] = {
                "status": "completed",
                "completed_at": now.isoformat(),
                "closed_at": now.isoformat(),
            }
            if reason:
                data["close_reason"] = reason

            rows = await self.db.update(
                "work_queue",
                match={"id": iid},
                data=data,
            )
            if rows:
                results.append(Issue.from_row(rows[0]))

        return results

    async def comment(
        self,
        issue_id: UUID,
        body: str,
        author: str | None = None,
    ) -> Comment:
        """Add a comment to an issue.

        Args:
            issue_id: Issue UUID
            body: Comment text
            author: Comment author (default: current agent ID)
        """
        config = get_config()
        resolved_author = author or config.agent.agent_id

        row = await self.db.insert(
            "issue_comments",
            {
                "issue_id": str(issue_id),
                "author": resolved_author,
                "body": body,
            },
        )
        return Comment.from_row(row)

    async def ready(
        self,
        parent_id: UUID | None = None,
        limit: int = 50,
    ) -> list[Issue]:
        """List issues with no unresolved dependencies.

        Args:
            parent_id: Optional parent to scope to
            limit: Max results
        """
        limit = min(limit, MAX_PAGE_SIZE)

        parts = [
            "task_type=eq.issue",
            "status=in.(pending,claimed,running)",
            "order=priority.asc,created_at.asc",
            f"limit={limit}",
        ]
        if parent_id:
            parts.append(f"parent_id=eq.{parent_id}")

        query = "&".join(parts)
        rows = await self.db.query("work_queue", query)

        # Filter out issues with unresolved dependencies
        ready_issues: list[Issue] = []
        for row in rows:
            issue = Issue.from_row(row)
            if not issue.depends_on:
                ready_issues.append(issue)
            else:
                # Check if all dependencies are completed
                all_resolved = True
                for dep_id in issue.depends_on:
                    dep_rows = await self.db.query(
                        "work_queue", f"id=eq.{dep_id}"
                    )
                    if dep_rows and dep_rows[0]["status"] != "completed":
                        all_resolved = False
                        break
                if all_resolved:
                    ready_issues.append(issue)

        return ready_issues

    async def blocked(self, limit: int = 50) -> list[Issue]:
        """List issues blocked by unresolved dependencies.

        Args:
            limit: Max results
        """
        limit = min(limit, MAX_PAGE_SIZE)

        rows = await self.db.query(
            "work_queue",
            f"task_type=eq.issue&status=in.(pending,claimed,running)&order=priority.asc&limit={limit}",
        )

        blocked_issues: list[Issue] = []
        for row in rows:
            issue = Issue.from_row(row)
            if not issue.depends_on:
                continue
            # Check if any dependency is unresolved
            for dep_id in issue.depends_on:
                dep_rows = await self.db.query(
                    "work_queue", f"id=eq.{dep_id}"
                )
                if dep_rows and dep_rows[0]["status"] != "completed":
                    blocked_issues.append(issue)
                    break

        return blocked_issues

    async def search(
        self,
        query: str,
        limit: int = 50,
    ) -> list[Issue]:
        """Search issues by text matching in title and description.

        Uses case-insensitive substring matching.

        Args:
            query: Search string
            limit: Max results
        """
        limit = min(limit, MAX_PAGE_SIZE)

        # Fetch all issues and filter in-memory (ILIKE not in PostgREST query syntax)
        rows = await self.db.query(
            "work_queue",
            f"task_type=eq.issue&order=priority.asc&limit={MAX_PAGE_SIZE}",
        )

        query_lower = query.lower()
        results: list[Issue] = []
        for row in rows:
            issue = Issue.from_row(row)
            if query_lower in issue.title.lower():
                results.append(issue)
            elif issue.description and query_lower in issue.description.lower():
                results.append(issue)

            if len(results) >= limit:
                break

        return results


# Global service instance
_issue_service: IssueService | None = None


def get_issue_service() -> IssueService:
    """Get the global issue service instance."""
    global _issue_service
    if _issue_service is None:
        _issue_service = IssueService()
    return _issue_service
