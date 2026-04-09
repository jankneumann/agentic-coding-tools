"""Coordination MCP Server - Multi-agent coordination tools for AI coding assistants.

This MCP server provides tools for:
- File locking to prevent concurrent edits
- Work queue for task assignment and tracking
- Session continuity via handoff documents
- Agent discovery and heartbeat monitoring

Usage (Claude Code):
    cd agent-coordinator && make claude-mcp-setup

    Or manually:
    claude mcp add-json --scope user coordination \
        '{"type":"stdio","command":".venv/bin/python","args":["-m","src.coordination_mcp"],"cwd":"/path/to/agent-coordinator","env":{"DB_BACKEND":"postgres","POSTGRES_DSN":"postgresql://user:pass@localhost:54322/dbname","AGENT_ID":"claude-code-1","AGENT_TYPE":"claude_code"}}'

Usage (standalone for testing):
    python -m src.coordination_mcp --transport sse --port 8082
"""

import sys
from typing import Any

from fastmcp import FastMCP

from . import http_proxy
from .approval import get_approval_service
from .audit import get_audit_service
from .config import get_config
from .discovery import get_discovery_service
from .guardrails import get_guardrails_service
from .handoffs import get_handoff_service
from .locks import get_lock_service
from .memory import get_memory_service
from .port_allocator import get_port_allocator
from .profiles import get_profiles_service
from .session_grants import get_session_grant_service
from .work_queue import get_work_queue_service

# Transport mode — set at startup by main(), read by tool handlers.
# "db" uses the service layer directly; "http" proxies to coordination_api.
_transport: str = "db"

# D6: MCP resources are not proxied in HTTP mode (low-value: tools provide
# the same data). When transport is "http", each resource returns this
# message instead of attempting a direct DB read.
_RESOURCE_UNAVAILABLE_IN_PROXY_MODE = (
    "This MCP resource is unavailable in HTTP proxy mode. "
    "Use the corresponding tool instead (e.g., check_locks, read_handoff, recall)."
)

# Create the MCP server
mcp = FastMCP(
    name="coordination",
    version="0.2.0",
    instructions="Multi-agent coordination: file locks, work queue, handoffs, and discovery",
)


# =============================================================================
# HELPER: Get agent identity from environment
# =============================================================================


def get_agent_id() -> str:
    """Get the current agent ID from config."""
    return get_config().agent.agent_id


def get_agent_type() -> str:
    """Get the current agent type from config."""
    return get_config().agent.agent_type


# =============================================================================
# MCP TOOLS: File Locks
# =============================================================================


@mcp.tool()
async def acquire_lock(
    file_path: str,
    reason: str | None = None,
    ttl_minutes: int | None = None,
) -> dict[str, Any]:
    """
    Acquire an exclusive lock on a file before modifying it.

    Use this before editing any file that other agents might also be working on.
    The lock automatically expires after ttl_minutes (default 2 hours).

    Args:
        file_path: Path to the file to lock (relative to repo root)
        reason: Why you need the lock (helps with debugging)
        ttl_minutes: How long to hold the lock (default from config, usually 120)

    Returns:
        success: Whether the lock was acquired
        action: 'acquired', 'refreshed', or reason for failure
        expires_at: When the lock will expire (if successful)
        locked_by: Which agent holds the lock (if failed)

    Example:
        result = acquire_lock("src/main.py", reason="refactoring error handling")
        if result["success"]:
            # Safe to edit the file
            ...
            release_lock("src/main.py")
    """
    if _transport == "http":
        return await http_proxy.proxy_acquire_lock(
            file_path=file_path,
            reason=reason,
            ttl_minutes=ttl_minutes,
        )
    service = get_lock_service()
    result = await service.acquire(
        file_path=file_path,
        reason=reason,
        ttl_minutes=ttl_minutes,
    )

    return {
        "success": result.success,
        "action": result.action,
        "file_path": result.file_path,
        "expires_at": result.expires_at.isoformat() if result.expires_at else None,
        "reason": result.reason,
        "locked_by": result.locked_by,
        "lock_reason": result.lock_reason,
    }


@mcp.tool()
async def release_lock(file_path: str) -> dict[str, Any]:
    """
    Release a lock you previously acquired.

    Always release locks when you're done editing a file, even if you
    encountered an error. This lets other agents proceed.

    Args:
        file_path: Path to the file to unlock

    Returns:
        success: Whether the lock was released
        file_path: The file that was unlocked
    """
    if _transport == "http":
        return await http_proxy.proxy_release_lock(file_path=file_path)
    service = get_lock_service()
    result = await service.release(file_path=file_path)

    return {
        "success": result.success,
        "action": result.action,
        "file_path": result.file_path,
        "reason": result.reason,
    }


@mcp.tool()
async def check_locks(file_paths: list[str] | None = None) -> list[dict[str, Any]]:
    """
    Check which files are currently locked.

    Use this before starting work to see if files you need are available.

    Args:
        file_paths: Specific files to check (or None for all active locks)

    Returns:
        List of active locks with file_path, locked_by, reason, expires_at
    """
    if _transport == "http":
        return await http_proxy.proxy_check_locks(file_paths=file_paths)
    service = get_lock_service()
    locks = await service.check(file_paths=file_paths)

    return [
        {
            "file_path": lock.file_path,
            "locked_by": lock.locked_by,
            "agent_type": lock.agent_type,
            "locked_at": lock.locked_at.isoformat(),
            "expires_at": lock.expires_at.isoformat(),
            "reason": lock.reason,
        }
        for lock in locks
    ]


# =============================================================================
# MCP TOOLS: Work Queue
# =============================================================================


@mcp.tool()
async def get_work(task_types: list[str] | None = None) -> dict[str, Any]:
    """
    Claim a task from the work queue.

    Tasks are assigned atomically - if you get a task, no other agent will.
    You should complete the task when done using complete_work().

    Args:
        task_types: Only claim these types of tasks (optional)
                   Examples: 'summarize', 'refactor', 'test', 'verify'

    Returns:
        success: Whether a task was claimed
        task_id: ID for completing the task
        task_type: Type of task
        description: What to do
        input_data: Task-specific input
        deadline: When it needs to be done (if set)

    Example:
        work = get_work(task_types=["summarize", "refactor"])
        if work["success"]:
            # Do the work...
            complete_work(work["task_id"], success=True, result={...})
    """
    if _transport == "http":
        return await http_proxy.proxy_get_work(task_types=task_types)
    service = get_work_queue_service()
    result = await service.claim(task_types=task_types)

    return {
        "success": result.success,
        "task_id": str(result.task_id) if result.task_id else None,
        "task_type": result.task_type,
        "description": result.description,
        "input_data": result.input_data,
        "priority": result.priority,
        "deadline": result.deadline.isoformat() if result.deadline else None,
        "reason": result.reason,
    }


@mcp.tool()
async def complete_work(
    task_id: str,
    success: bool,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """
    Mark a claimed task as completed.

    Always call this after finishing a task from get_work(),
    whether it succeeded or failed.

    Args:
        task_id: ID from get_work()
        success: Whether the task completed successfully
        result: Output data from the task (optional)
        error_message: What went wrong if success=False (optional)

    Returns:
        success: Whether the completion was recorded
        status: 'completed' or 'failed'
    """
    if _transport == "http":
        return await http_proxy.proxy_complete_work(
            task_id=task_id,
            success=success,
            result=result,
            error_message=error_message,
        )
    from uuid import UUID

    service = get_work_queue_service()
    completion = await service.complete(
        task_id=UUID(task_id),
        success=success,
        result=result,
        error_message=error_message,
    )

    return {
        "success": completion.success,
        "status": completion.status,
        "task_id": str(completion.task_id) if completion.task_id else None,
        "reason": completion.reason,
    }


@mcp.tool()
async def submit_work(
    task_type: str,
    description: str,
    input_data: dict[str, Any] | None = None,
    priority: int = 5,
    depends_on: list[str] | None = None,
) -> dict[str, Any]:
    """
    Submit a new task to the work queue.

    Use this to create subtasks or delegate work to other agents.

    Args:
        task_type: Category of task ('summarize', 'refactor', 'test', etc.)
        description: What needs to be done
        input_data: Data needed to complete the task (optional)
        priority: 1 (highest) to 10 (lowest), default 5
        depends_on: List of task_ids that must complete first (optional)

    Returns:
        success: Whether the task was created
        task_id: ID of the new task

    Example:
        # Create a subtask for testing
        result = submit_work(
            task_type="test",
            description="Write unit tests for cache module",
            input_data={"files": ["src/cache.py"]},
            priority=3
        )
    """
    if _transport == "http":
        return await http_proxy.proxy_submit_work(
            task_type=task_type,
            description=description,
            input_data=input_data,
            priority=priority,
            depends_on=depends_on,
        )
    from uuid import UUID

    service = get_work_queue_service()

    depends_on_uuids = None
    if depends_on:
        depends_on_uuids = [UUID(d) for d in depends_on]

    result = await service.submit(
        task_type=task_type,
        description=description,
        input_data=input_data,
        priority=priority,
        depends_on=depends_on_uuids,
    )

    return {
        "success": result.success,
        "task_id": str(result.task_id) if result.task_id else None,
    }


@mcp.tool()
async def get_task(task_id: str) -> dict[str, Any]:
    """
    Retrieve a specific task by ID.

    Use this to check the status, result, or details of any task
    in the work queue.

    Args:
        task_id: UUID of the task to retrieve

    Returns:
        success: Whether the task was found
        task: Task details (id, task_type, description, status, etc.)

    Example:
        result = get_task("550e8400-e29b-41d4-a716-446655440000")
        if result["success"]:
            print(result["task"]["status"])
    """
    if _transport == "http":
        return await http_proxy.proxy_get_task(task_id=task_id)
    from uuid import UUID

    service = get_work_queue_service()
    task = await service.get_task(UUID(task_id))

    if task is None:
        return {"success": False, "reason": "task_not_found"}

    return {
        "success": True,
        "task": {
            "id": str(task.id),
            "task_type": task.task_type,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "input_data": task.input_data,
            "claimed_by": task.claimed_by,
            "claimed_at": task.claimed_at.isoformat() if task.claimed_at else None,
            "result": task.result,
            "error_message": task.error_message,
            "depends_on": [str(d) for d in task.depends_on],
            "deadline": task.deadline.isoformat() if task.deadline else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        },
    }


# =============================================================================
# MCP TOOLS: Issue Tracking
# =============================================================================


@mcp.tool()
async def issue_create(
    title: str,
    description: str | None = None,
    issue_type: str = "task",
    priority: int = 5,
    labels: list[str] | None = None,
    parent_id: str | None = None,
    assignee: str | None = None,
    depends_on: list[str] | None = None,
) -> dict[str, Any]:
    """
    Create a new issue in the coordinator's issue tracker.

    Issues are stored in the work_queue with task_type='issue' so they
    won't be accidentally claimed by get_work().

    Args:
        title: Issue title (required)
        description: Detailed description
        issue_type: task, epic, bug, or feature (default: task)
        priority: 1 (highest) to 10 (lowest), default 5
        labels: List of label strings for categorization
        parent_id: Parent issue UUID (for epic children)
        assignee: Who is assigned to this issue
        depends_on: List of issue UUIDs that must complete first

    Returns:
        success: Whether the issue was created
        issue: The created issue details

    Example:
        issue_create(
            title="Add CORS middleware",
            issue_type="bug",
            priority=3,
            labels=["api", "followup"]
        )
    """
    if _transport == "http":
        return await http_proxy.proxy_issue_create(
            title=title,
            description=description,
            issue_type=issue_type,
            priority=priority,
            labels=labels,
            parent_id=parent_id,
            assignee=assignee,
            depends_on=depends_on,
        )
    from uuid import UUID

    from .issue_service import get_issue_service

    service = get_issue_service()

    parent_uuid = UUID(parent_id) if parent_id else None
    depends_uuids = [UUID(d) for d in depends_on] if depends_on else None

    try:
        issue = await service.create(
            title=title,
            description=description,
            issue_type=issue_type,
            priority=priority,
            labels=labels,
            parent_id=parent_uuid,
            assignee=assignee,
            depends_on=depends_uuids,
        )
        return {"success": True, "issue": issue.to_dict()}
    except ValueError as e:
        return {"success": False, "reason": str(e)}


@mcp.tool()
async def issue_list(
    status: str | None = None,
    issue_type: str | None = None,
    labels: list[str] | None = None,
    parent_id: str | None = None,
    assignee: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    List issues with optional filters.

    Args:
        status: Filter by status (open, in_progress, closed, all)
        issue_type: Filter by type (task, epic, bug, feature)
        labels: Filter by labels (issues must have ALL specified labels)
        parent_id: Filter by parent issue UUID
        assignee: Filter by assignee
        limit: Max results (default 50, max 100)

    Returns:
        success: true
        issues: List of issue objects
        count: Number of issues returned
    """
    if _transport == "http":
        return await http_proxy.proxy_issue_list(
            status=status,
            issue_type=issue_type,
            labels=labels,
            parent_id=parent_id,
            assignee=assignee,
            limit=limit,
        )
    from uuid import UUID

    from .issue_service import get_issue_service

    service = get_issue_service()
    parent_uuid = UUID(parent_id) if parent_id else None

    issues = await service.list_issues(
        status=status,
        issue_type=issue_type,
        labels=labels,
        parent_id=parent_uuid,
        assignee=assignee,
        limit=limit,
    )

    return {
        "success": True,
        "issues": [i.to_dict() for i in issues],
        "count": len(issues),
    }


@mcp.tool()
async def issue_show(issue_id: str) -> dict[str, Any]:
    """
    Get full details of an issue, including comments and children.

    Args:
        issue_id: UUID of the issue

    Returns:
        success: Whether the issue was found
        issue: Full issue details with comments array and children (for epics)
    """
    if _transport == "http":
        return await http_proxy.proxy_issue_show(issue_id=issue_id)
    from uuid import UUID

    from .issue_service import get_issue_service

    service = get_issue_service()
    issue = await service.show(UUID(issue_id))

    if issue is None:
        return {"success": False, "reason": "issue_not_found"}

    return {"success": True, "issue": issue.to_dict()}


@mcp.tool()
async def issue_update(
    issue_id: str,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    labels: list[str] | None = None,
    assignee: str | None = None,
    issue_type: str | None = None,
) -> dict[str, Any]:
    """
    Update one or more fields on an issue.

    Args:
        issue_id: UUID of the issue to update
        title: New title
        description: New description
        status: New status (open, in_progress, closed)
        priority: New priority (1-10)
        labels: Replace labels array
        assignee: New assignee
        issue_type: New type (task, epic, bug, feature)

    Returns:
        success: Whether the update succeeded
        issue: Updated issue details
    """
    if _transport == "http":
        return await http_proxy.proxy_issue_update(
            issue_id=issue_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            labels=labels,
            assignee=assignee,
            issue_type=issue_type,
        )
    from uuid import UUID

    from .issue_service import get_issue_service

    service = get_issue_service()

    try:
        issue = await service.update(
            issue_id=UUID(issue_id),
            title=title,
            description=description,
            status=status,
            priority=priority,
            labels=labels,
            assignee=assignee,
            issue_type=issue_type,
        )
    except ValueError as e:
        return {"success": False, "reason": str(e)}

    if issue is None:
        return {"success": False, "reason": "issue_not_found"}

    return {"success": True, "issue": issue.to_dict()}


@mcp.tool()
async def issue_close(
    issue_id: str | None = None,
    issue_ids: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """
    Close one or more issues.

    Args:
        issue_id: UUID of a single issue to close
        issue_ids: List of UUIDs for batch close
        reason: Closure reason (e.g., "Implemented in PR #42")

    Returns:
        success: Whether the close succeeded
        closed: List of closed issue details
        count: Number of issues closed
    """
    if _transport == "http":
        return await http_proxy.proxy_issue_close(
            issue_id=issue_id,
            issue_ids=issue_ids,
            reason=reason,
        )
    from uuid import UUID

    from .issue_service import get_issue_service

    service = get_issue_service()

    id_uuid = UUID(issue_id) if issue_id else None
    ids_uuids = [UUID(i) for i in issue_ids] if issue_ids else None

    try:
        results = await service.close(
            issue_id=id_uuid,
            issue_ids=ids_uuids,
            reason=reason,
        )
    except ValueError as e:
        return {"success": False, "reason": str(e)}

    return {
        "success": True,
        "closed": [i.to_dict() for i in results],
        "count": len(results),
    }


@mcp.tool()
async def issue_comment(
    issue_id: str,
    body: str,
) -> dict[str, Any]:
    """
    Add a comment to an issue.

    Args:
        issue_id: UUID of the issue
        body: Comment text

    Returns:
        success: true
        comment: The created comment details
    """
    if _transport == "http":
        return await http_proxy.proxy_issue_comment(
            issue_id=issue_id,
            body=body,
        )
    from uuid import UUID

    from .issue_service import get_issue_service

    service = get_issue_service()
    comment = await service.comment(UUID(issue_id), body)

    return {"success": True, "comment": comment.to_dict()}


@mcp.tool()
async def issue_ready(
    parent_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    List issues with no unresolved dependencies (ready to work on).

    Args:
        parent_id: Optional parent UUID to scope to epic children
        limit: Max results (default 50)

    Returns:
        success: true
        issues: List of ready issue objects
        count: Number of ready issues
    """
    if _transport == "http":
        return await http_proxy.proxy_issue_ready(
            parent_id=parent_id,
            limit=limit,
        )
    from uuid import UUID

    from .issue_service import get_issue_service

    service = get_issue_service()
    parent_uuid = UUID(parent_id) if parent_id else None

    issues = await service.ready(parent_id=parent_uuid, limit=limit)

    return {
        "success": True,
        "issues": [i.to_dict() for i in issues],
        "count": len(issues),
    }


@mcp.tool()
async def issue_blocked() -> dict[str, Any]:
    """
    List issues blocked by unresolved dependencies.

    Returns:
        success: true
        issues: List of blocked issue objects
        count: Number of blocked issues
    """
    if _transport == "http":
        return await http_proxy.proxy_issue_blocked()
    from .issue_service import get_issue_service

    service = get_issue_service()
    issues = await service.blocked()

    return {
        "success": True,
        "issues": [i.to_dict() for i in issues],
        "count": len(issues),
    }


@mcp.tool()
async def issue_search(
    query: str,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Search issues by text matching in title and description.

    Args:
        query: Search string (case-insensitive substring match)
        limit: Max results (default 50)

    Returns:
        success: true
        issues: List of matching issues
        count: Number of matches
    """
    if _transport == "http":
        return await http_proxy.proxy_issue_search(
            query=query,
            limit=limit,
        )
    from .issue_service import get_issue_service

    service = get_issue_service()
    issues = await service.search(query=query, limit=limit)

    return {
        "success": True,
        "issues": [i.to_dict() for i in issues],
        "count": len(issues),
    }


# =============================================================================
# MCP TOOLS: Handoff Documents (Session Continuity)
# =============================================================================


@mcp.tool()
async def write_handoff(
    summary: str,
    completed_work: list[str] | None = None,
    in_progress: list[str] | None = None,
    decisions: list[str] | None = None,
    next_steps: list[str] | None = None,
    relevant_files: list[str] | None = None,
) -> dict[str, Any]:
    """
    Write a handoff document to preserve session context.

    Call this before ending a session or when hitting context limits.
    The next session can read this to resume where you left off.

    Args:
        summary: What was accomplished and current state (required)
        completed_work: List of completed work items
        in_progress: List of items still being worked on
        decisions: Key decisions made during the session
        next_steps: What should be done next
        relevant_files: File paths relevant to the work

    Returns:
        success: Whether the handoff was written
        handoff_id: UUID of the created handoff document

    Example:
        write_handoff(
            summary="Implemented file locking with TTL expiration",
            completed_work=["Lock acquisition", "Lock release", "TTL cleanup"],
            in_progress=["Integration tests"],
            decisions=["Used PostgreSQL advisory locks for atomicity"],
            next_steps=["Write integration tests", "Add lock contention metrics"],
            relevant_files=["src/locks.py", "supabase/migrations/001_core_schema.sql"]
        )
    """
    if _transport == "http":
        return await http_proxy.proxy_write_handoff(
            summary=summary,
            completed_work=completed_work,
            in_progress=in_progress,
            decisions=decisions,
            next_steps=next_steps,
            relevant_files=relevant_files,
        )
    service = get_handoff_service()
    result = await service.write(
        summary=summary,
        completed_work=completed_work,
        in_progress=in_progress,
        decisions=decisions,
        next_steps=next_steps,
        relevant_files=relevant_files,
    )

    return {
        "success": result.success,
        "handoff_id": str(result.handoff_id) if result.handoff_id else None,
        "error": result.error,
    }


@mcp.tool()
async def read_handoff(
    agent_name: str | None = None,
    limit: int = 1,
) -> dict[str, Any]:
    """
    Read previous handoff documents for session continuity.

    Call this at the start of a new session to resume prior context.
    Returns the most recent handoff(s) for the specified agent.

    Args:
        agent_name: Filter by agent name (None for current agent's handoffs)
        limit: Number of handoffs to retrieve (default: 1, most recent)

    Returns:
        handoffs: List of handoff documents with summary, completed work, etc.

    Example:
        result = read_handoff()
        if result["handoffs"]:
            # Resume from previous session context
            previous = result["handoffs"][0]
            print(f"Previous session: {previous['summary']}")
    """
    if _transport == "http":
        return await http_proxy.proxy_read_handoff(
            agent_name=agent_name,
            limit=limit,
        )
    service = get_handoff_service()

    # Default to current agent if no name specified
    if agent_name is None:
        agent_name = get_agent_id()

    result = await service.read(
        agent_name=agent_name,
        limit=limit,
    )

    return {
        "handoffs": [
            {
                "id": str(h.id),
                "agent_name": h.agent_name,
                "session_id": h.session_id,
                "summary": h.summary,
                "completed_work": h.completed_work,
                "in_progress": h.in_progress,
                "decisions": h.decisions,
                "next_steps": h.next_steps,
                "relevant_files": h.relevant_files,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in result.handoffs
        ],
    }


# =============================================================================
# MCP TOOLS: Agent Discovery and Heartbeat
# =============================================================================


@mcp.tool()
async def register_session(
    capabilities: list[str] | None = None,
    current_task: str | None = None,
    delegated_from: str | None = None,
) -> dict[str, Any]:
    """
    Register this agent session for discovery by other agents.

    Call this at the start of a work session to make yourself discoverable.
    Other agents can then find you via discover_agents().

    Args:
        capabilities: What this agent can do (e.g., ['coding', 'testing', 'review'])
        current_task: Description of what you're currently working on
        delegated_from: Agent ID of the delegating agent (for delegated identity)

    Returns:
        success: Whether registration succeeded
        session_id: The registered session ID

    Example:
        register_session(
            capabilities=["coding", "testing"],
            current_task="Implementing file locking feature"
        )
    """
    if _transport == "http":
        return await http_proxy.proxy_register_session(
            capabilities=capabilities,
            current_task=current_task,
            delegated_from=delegated_from,
        )
    service = get_discovery_service()
    result = await service.register(
        capabilities=capabilities,
        current_task=current_task,
        delegated_from=delegated_from,
    )

    return {
        "success": result.success,
        "session_id": result.session_id,
    }


@mcp.tool()
async def discover_agents(
    capability: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """
    Discover other agents working in this coordination system.

    Use this to find agents with specific capabilities or check who's active.

    Args:
        capability: Filter by capability (e.g., 'coding', 'review', 'testing')
        status: Filter by status ('active', 'idle', 'disconnected')

    Returns:
        agents: List of matching agents with their capabilities and status

    Example:
        # Find all active agents
        result = discover_agents(status="active")

        # Find agents that can review code
        result = discover_agents(capability="review")
    """
    if _transport == "http":
        return await http_proxy.proxy_discover_agents(
            capability=capability,
            status=status,
        )
    service = get_discovery_service()
    result = await service.discover(
        capability=capability,
        status=status,
    )

    return {
        "agents": [
            {
                "agent_id": a.agent_id,
                "agent_type": a.agent_type,
                "session_id": a.session_id,
                "capabilities": a.capabilities,
                "status": a.status,
                "current_task": a.current_task,
                "last_heartbeat": a.last_heartbeat.isoformat() if a.last_heartbeat else None,
                "started_at": a.started_at.isoformat() if a.started_at else None,
            }
            for a in result.agents
        ],
    }


@mcp.tool()
async def heartbeat() -> dict[str, Any]:
    """
    Send a heartbeat to indicate this agent is still alive.

    Call this periodically (every few minutes) during long-running work.
    Agents that don't heartbeat for 15+ minutes may have their locks released.

    Returns:
        success: Whether the heartbeat was recorded
        session_id: The session that was updated
    """
    if _transport == "http":
        return await http_proxy.proxy_heartbeat()
    service = get_discovery_service()
    result = await service.heartbeat()

    return {
        "success": result.success,
        "session_id": result.session_id,
        "error": result.error,
    }


@mcp.tool()
async def cleanup_dead_agents(
    stale_threshold_minutes: int = 15,
) -> dict[str, Any]:
    """
    Clean up agents that have stopped responding.

    Marks stale agents as disconnected and releases their file locks.
    Use this if you suspect an agent has crashed and is holding locks.

    Args:
        stale_threshold_minutes: Minutes without heartbeat before cleanup (default: 15)

    Returns:
        success: Whether cleanup ran
        agents_cleaned: Number of agents marked as disconnected
        locks_released: Number of locks released
    """
    if _transport == "http":
        return await http_proxy.proxy_cleanup_dead_agents(
            stale_threshold_minutes=stale_threshold_minutes,
        )
    service = get_discovery_service()
    result = await service.cleanup_dead_agents(
        stale_threshold_minutes=stale_threshold_minutes,
    )

    return {
        "success": result.success,
        "agents_cleaned": result.agents_cleaned,
        "locks_released": result.locks_released,
    }


# =============================================================================
# MCP TOOLS: Memory (Phase 2)
# =============================================================================


@mcp.tool()
async def remember(
    event_type: str = "discovery",
    summary: str = "",
    details: dict[str, Any] | None = None,
    outcome: str | None = None,
    lessons: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    Store an episodic memory for cross-session learning.

    Use this to record important events, decisions, errors, and learnings
    so future sessions can benefit from past experience.

    Args:
        event_type: Type of event ('error', 'success', 'decision', 'discovery', 'optimization')
        summary: Short description of what happened
        details: Additional structured data (optional)
        outcome: 'positive', 'negative', or 'neutral' (optional)
        lessons: Lessons learned from this event (optional)
        tags: Tags for filtering during recall (optional)

    Returns:
        success: Whether the memory was stored
        memory_id: UUID of the stored memory
        action: 'created' or 'deduplicated' (if similar memory exists within 1 hour)
    """
    if _transport == "http":
        return await http_proxy.proxy_remember(
            event_type=event_type,
            summary=summary,
            details=details,
            outcome=outcome,
            lessons=lessons,
            tags=tags,
        )
    service = get_memory_service()
    result = await service.remember(
        event_type=event_type,
        summary=summary,
        details=details,
        outcome=outcome,
        lessons=lessons,
        tags=tags,
    )

    return {
        "success": result.success,
        "memory_id": result.memory_id,
        "action": result.action,
        "error": result.error,
    }


@mcp.tool()
async def recall(
    tags: list[str] | None = None,
    event_type: str | None = None,
    limit: int = 10,
    min_relevance: float = 0.0,
) -> dict[str, Any]:
    """
    Recall relevant memories from past sessions.

    Use this at the start of a session or when facing a problem
    to benefit from past experience.

    Args:
        tags: Filter by tags (memories matching ANY tag are returned)
        event_type: Filter by event type (optional)
        limit: Maximum number of memories to return (default: 10)
        min_relevance: Minimum relevance score (0.0-1.0, default: 0.0)

    Returns:
        memories: List of relevant memories sorted by relevance
    """
    if _transport == "http":
        return await http_proxy.proxy_recall(
            tags=tags,
            event_type=event_type,
            limit=limit,
            min_relevance=min_relevance,
        )
    service = get_memory_service()
    result = await service.recall(
        tags=tags,
        event_type=event_type,
        limit=limit,
        min_relevance=min_relevance,
    )

    return {
        "memories": [
            {
                "id": m.id,
                "event_type": m.event_type,
                "summary": m.summary,
                "details": m.details,
                "outcome": m.outcome,
                "lessons": m.lessons,
                "tags": m.tags,
                "relevance_score": m.relevance_score,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in result.memories
        ],
    }


# =============================================================================
# MCP TOOLS: Guardrails (Phase 3)
# =============================================================================


@mcp.tool()
async def check_guardrails(
    operation_text: str,
    file_paths: list[str] | None = None,
) -> dict[str, Any]:
    """
    Check an operation for destructive patterns.

    Use this proactively before running potentially dangerous commands.
    The system also runs guardrail checks automatically on work completion.

    Args:
        operation_text: The command or operation text to check
        file_paths: File paths involved in the operation (optional)

    Returns:
        safe: True if no destructive patterns matched
        violations: List of matched patterns with category and severity
    """
    if _transport == "http":
        return await http_proxy.proxy_check_guardrails(
            operation_text=operation_text,
            file_paths=file_paths,
        )
    from .policy_engine import get_policy_engine

    engine = get_policy_engine()
    decision = await engine.check_operation(
        agent_id=get_agent_id(),
        agent_type=get_agent_type(),
        operation="check_guardrails",
        context={
            "operation_text_length": len(operation_text),
            "file_count": len(file_paths or []),
        },
    )
    if not decision.allowed:
        return {
            "safe": False,
            "violations": [],
            "reason": decision.reason or "operation_not_permitted",
        }

    service = get_guardrails_service()
    result = await service.check_operation(
        operation_text=operation_text,
        file_paths=file_paths,
        agent_id=get_agent_id(),
        agent_type=get_agent_type(),
    )

    return {
        "safe": result.safe,
        "violations": [
            {
                "pattern_name": v.pattern_name,
                "category": v.category,
                "severity": v.severity,
                "matched_text": v.matched_text,
                "blocked": v.blocked,
            }
            for v in result.violations
        ],
    }


# =============================================================================
# MCP TOOLS: Profiles (Phase 3)
# =============================================================================


@mcp.tool()
async def get_my_profile() -> dict[str, Any]:
    """
    Get the current agent's profile including trust level and permissions.

    Returns the agent's profile with allowed operations, trust level,
    and resource limits.

    Returns:
        success: Whether the profile was found
        profile: Profile details including trust_level, allowed_operations, etc.
        source: How the profile was determined ('assignment', 'default', 'cache')
    """
    if _transport == "http":
        return await http_proxy.proxy_get_my_profile()
    service = get_profiles_service()
    result = await service.get_profile()

    profile_data = None
    if result.profile:
        profile_data = {
            "name": result.profile.name,
            "agent_type": result.profile.agent_type,
            "trust_level": result.profile.trust_level,
            "allowed_operations": result.profile.allowed_operations,
            "blocked_operations": result.profile.blocked_operations,
            "max_file_modifications": result.profile.max_file_modifications,
        }

    return {
        "success": result.success,
        "profile": profile_data,
        "source": result.source,
        "reason": result.reason,
    }


@mcp.tool()
async def get_agent_dispatch_configs() -> dict[str, Any]:
    """
    Get CLI dispatch configurations for all agents with a `cli` section.

    Returns agent CLI configs needed by the review dispatcher to
    invoke vendor CLIs.  Only agents with a `cli` section in
    ``agents.yaml`` are included.

    Returns:
        agents: List of agent dispatch configs with cli details
    """
    if _transport == "http":
        return await http_proxy.proxy_get_agent_dispatch_configs()
    from .agents_config import get_dispatch_configs

    return get_dispatch_configs()


# =============================================================================
# MCP TOOLS: Audit (Phase 3)
# =============================================================================


@mcp.tool()
async def query_audit(
    agent_id: str | None = None,
    operation: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Query the audit trail for recent operations.

    Use this for debugging, compliance, or understanding what happened.

    Args:
        agent_id: Filter by agent ID (optional)
        operation: Filter by operation type (optional)
        limit: Maximum number of entries to return (default: 20)

    Returns:
        entries: List of audit log entries
    """
    if _transport == "http":
        return await http_proxy.proxy_query_audit(
            agent_id=agent_id,
            operation=operation,
            limit=limit,
        )
    service = get_audit_service()
    entries = await service.query(
        agent_id=agent_id,
        operation=operation,
        limit=limit,
    )

    return {
        "entries": [
            {
                "id": e.id,
                "agent_id": e.agent_id,
                "agent_type": e.agent_type,
                "operation": e.operation,
                "parameters": e.parameters,
                "result": e.result,
                "duration_ms": e.duration_ms,
                "success": e.success,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ],
    }


# =============================================================================
# MCP TOOLS: Policy Engine (Phase 3 / Cedar)
# =============================================================================


@mcp.tool()
async def check_policy(
    operation: str,
    resource: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Check if an operation is authorized by the policy engine.

    Uses either native (profiles + network) or Cedar engine based on config.

    Args:
        operation: Operation name (e.g., 'acquire_lock', 'network_access')
        resource: Target resource (file path, domain, etc.)
        context: Additional context (trust_level, files_modified, etc.)

    Returns:
        allowed: Whether the operation is authorized
        reason: Explanation of the decision
        engine: Which policy engine made the decision
    """
    if _transport == "http":
        return await http_proxy.proxy_check_policy(
            operation=operation,
            resource=resource,
            context=context,
        )
    from .policy_engine import get_policy_engine

    engine = get_policy_engine()
    result = await engine.check_operation(
        agent_id=get_agent_id(),
        agent_type=get_agent_type(),
        operation=operation,
        resource=resource,
        context=context,
    )

    engine_name = type(engine).__name__
    return {
        "allowed": result.allowed,
        "reason": result.reason,
        "engine": engine_name,
        "diagnostics": result.diagnostics,
    }


@mcp.tool()
async def validate_cedar_policy(policy_text: str) -> dict[str, Any]:
    """
    Validate Cedar policy text against the schema.

    Only available when POLICY_ENGINE=cedar.

    Args:
        policy_text: Cedar policy text to validate

    Returns:
        valid: Whether the policy is valid
        errors: List of validation errors (if any)
    """
    if _transport == "http":
        return await http_proxy.proxy_validate_cedar_policy(policy_text=policy_text)
    config = get_config()
    if config.policy_engine.engine != "cedar":
        return {
            "valid": False,
            "errors": ["Cedar engine not active. Set POLICY_ENGINE=cedar"],
        }

    from .policy_engine import get_policy_engine

    engine = get_policy_engine()
    if not hasattr(engine, "validate_policy"):
        return {
            "valid": False,
            "errors": ["Current engine does not support policy validation"],
        }

    result = engine.validate_policy(policy_text)
    return {
        "valid": result.valid,
        "errors": result.errors,
    }


# =============================================================================
# MCP TOOLS: Port Allocation
# =============================================================================


@mcp.tool()
async def allocate_ports(session_id: str) -> dict[str, Any]:
    """
    Allocate a conflict-free port block for a parallel docker-compose stack.

    Each allocation provides 4 ports (db, rest, realtime, api) and a unique
    compose project name. Duplicate calls for the same session_id refresh the
    TTL and return the existing allocation.

    Args:
        session_id: Unique identifier for the session requesting ports

    Returns:
        success: Whether ports were allocated
        allocation: Port details (db_port, rest_port, realtime_port, api_port,
                    compose_project_name) if successful
        env_snippet: Shell export snippet ready for sourcing (if successful)
        error: 'no_ports_available' if all port blocks are in use

    Example:
        result = allocate_ports("session-abc-123")
        if result["success"]:
            # Use result["env_snippet"] to configure docker-compose
            ...
    """
    if _transport == "http":
        return await http_proxy.proxy_allocate_ports(session_id=session_id)
    allocator = get_port_allocator()
    allocation = allocator.allocate(session_id)

    if allocation is None:
        return {
            "success": False,
            "error": "no_ports_available",
        }

    return {
        "success": True,
        "allocation": {
            "db_port": allocation.db_port,
            "rest_port": allocation.rest_port,
            "realtime_port": allocation.realtime_port,
            "api_port": allocation.api_port,
            "compose_project_name": allocation.compose_project_name,
        },
        "env_snippet": allocation.env_snippet,
    }


@mcp.tool()
async def release_ports(session_id: str) -> dict[str, Any]:
    """
    Release a previously allocated port block.

    Call this when a session's docker-compose stack is torn down.
    The operation is idempotent - releasing a non-existent allocation succeeds.

    Args:
        session_id: The session whose ports should be released

    Returns:
        success: Always True (idempotent release)

    Example:
        release_ports("session-abc-123")
    """
    if _transport == "http":
        return await http_proxy.proxy_release_ports(session_id=session_id)
    allocator = get_port_allocator()
    allocator.release(session_id)

    return {
        "success": True,
    }


@mcp.tool()
async def ports_status() -> list[dict[str, Any]]:
    """
    List all active port allocations.

    Returns currently allocated port blocks with remaining TTL information.
    Expired allocations are automatically cleaned up before reporting.

    Returns:
        List of active allocations with session_id, ports, compose_project_name,
        and remaining_ttl_minutes

    Example:
        status = ports_status()
        for alloc in status:
            print(f"{alloc['session_id']}: db={alloc['db_port']} "
                  f"(TTL: {alloc['remaining_ttl_minutes']:.1f}m)")
    """
    if _transport == "http":
        return await http_proxy.proxy_ports_status()
    import time

    allocator = get_port_allocator()
    allocations = allocator.status()
    now = time.time()

    return [
        {
            "session_id": alloc.session_id,
            "db_port": alloc.db_port,
            "rest_port": alloc.rest_port,
            "realtime_port": alloc.realtime_port,
            "api_port": alloc.api_port,
            "compose_project_name": alloc.compose_project_name,
            "remaining_ttl_minutes": max(0.0, (alloc.expires_at - now) / 60),
        }
        for alloc in allocations
    ]


# =============================================================================
# MCP TOOLS: Approval Gates
# =============================================================================


@mcp.tool()
async def request_approval(
    operation: str,
    resource: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Request human approval for a high-risk operation."""
    if _transport == "http":
        return await http_proxy.proxy_request_approval(
            operation=operation,
            resource=resource,
            context=context,
        )
    config = get_config()
    if not config.approval.enabled:
        return {"success": False, "error": "Approval gates are not enabled"}
    service = get_approval_service()
    request = await service.submit_request(
        agent_id=config.agent.agent_id,
        operation=operation,
        resource=resource,
        context=context,
        timeout_seconds=config.approval.default_timeout_seconds,
    )
    return {
        "success": True,
        "request_id": request.id,
        "status": request.status,
        "expires_at": request.expires_at.isoformat(),
    }


@mcp.tool()
async def check_approval(request_id: str) -> dict[str, Any]:
    """Check the status of an approval request."""
    if _transport == "http":
        return await http_proxy.proxy_check_approval(request_id=request_id)
    service = get_approval_service()
    request = await service.check_request(request_id)
    if not request:
        return {"success": False, "error": "Request not found"}
    result: dict[str, Any] = {
        "success": True,
        "request_id": request.id,
        "status": request.status,
    }
    if request.decided_by:
        result["decided_by"] = request.decided_by
    if request.reason:
        result["reason"] = request.reason
    return result


# =============================================================================
# MCP TOOLS: Policy Versioning
# =============================================================================


@mcp.tool()
async def list_policy_versions(policy_name: str, limit: int = 20) -> dict[str, Any]:
    """List version history for a Cedar policy."""
    if _transport == "http":
        return await http_proxy.proxy_list_policy_versions(
            policy_name=policy_name,
            limit=limit,
        )
    from .policy_engine import get_policy_engine

    engine = get_policy_engine()
    versions = await engine.list_policy_versions(policy_name, limit)
    return {"versions": versions}


# =============================================================================
# MCP TOOLS: Session Grants
# =============================================================================


@mcp.tool()
async def request_permission(
    operation: str, justification: str | None = None
) -> dict[str, Any]:
    """Request a session-scoped permission grant."""
    if _transport == "http":
        return await http_proxy.proxy_request_permission(
            operation=operation,
            justification=justification,
        )
    config = get_config()
    if not config.session_grants.enabled:
        return {"success": False, "error": "Session grants are not enabled"}
    service = get_session_grant_service()
    grant = await service.request_grant(
        session_id=config.agent.agent_id,  # use agent_id as session_id for MCP
        agent_id=config.agent.agent_id,
        operation=operation,
        justification=justification,
    )
    return {
        "success": True,
        "granted": True,
        "grant_id": grant.id,
        "operation": grant.operation,
    }


# =============================================================================
# MCP TOOLS: Feature Registry
# =============================================================================


@mcp.tool()
async def register_feature(
    feature_id: str,
    resource_claims: list[str],
    title: str | None = None,
    branch_name: str | None = None,
    merge_priority: int = 5,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register a feature with its resource claims for cross-feature coordination.

    Call this before implementation to declare which files/keys this feature
    will modify. The registry detects overlaps with other active features.

    Args:
        feature_id: Unique feature identifier (e.g., OpenSpec change-id)
        resource_claims: Lock keys this feature will use (file paths, logical keys)
        title: Human-readable feature title
        branch_name: Git branch for this feature
        merge_priority: Merge priority (1=highest, 10=lowest, default 5)
        metadata: Additional metadata

    Returns:
        success: Whether registration succeeded
        feature_id: The registered feature ID
        action: 'registered' or 'updated'
    """
    if _transport == "http":
        return await http_proxy.proxy_register_feature(
            feature_id=feature_id,
            resource_claims=resource_claims,
            title=title,
            branch_name=branch_name,
            merge_priority=merge_priority,
            metadata=metadata,
        )
    from .feature_registry import get_feature_registry_service

    service = get_feature_registry_service()
    result = await service.register(
        feature_id=feature_id,
        resource_claims=resource_claims,
        title=title,
        agent_id=get_agent_id(),
        branch_name=branch_name,
        merge_priority=merge_priority,
        metadata=metadata,
    )
    return {
        "success": result.success,
        "feature_id": result.feature_id,
        "action": result.action,
        "reason": result.reason,
    }


@mcp.tool()
async def deregister_feature(
    feature_id: str,
    status: str = "completed",
) -> dict[str, Any]:
    """Deregister a feature (mark as completed or cancelled).

    Call this after a feature is merged or abandoned to free its resource claims.

    Args:
        feature_id: Feature to deregister
        status: Target status ('completed' or 'cancelled')

    Returns:
        success: Whether deregistration succeeded
        feature_id: The deregistered feature ID
        status: Final status
    """
    if _transport == "http":
        return await http_proxy.proxy_deregister_feature(
            feature_id=feature_id,
            status=status,
        )
    from .feature_registry import get_feature_registry_service

    service = get_feature_registry_service()
    result = await service.deregister(feature_id=feature_id, status=status)
    return {
        "success": result.success,
        "feature_id": result.feature_id,
        "status": result.status,
        "reason": result.reason,
    }


@mcp.tool()
async def get_feature(feature_id: str) -> dict[str, Any]:
    """Get details of a specific registered feature.

    Args:
        feature_id: Feature ID to look up

    Returns:
        Feature details including status, resource claims, and merge priority
    """
    if _transport == "http":
        return await http_proxy.proxy_get_feature(feature_id=feature_id)
    from .feature_registry import get_feature_registry_service

    service = get_feature_registry_service()
    feature = await service.get_feature(feature_id)
    if feature is None:
        return {"success": False, "reason": "feature_not_found"}
    return {
        "success": True,
        "feature": {
            "feature_id": feature.feature_id,
            "title": feature.title,
            "status": feature.status,
            "registered_by": feature.registered_by,
            "resource_claims": feature.resource_claims,
            "branch_name": feature.branch_name,
            "merge_priority": feature.merge_priority,
            "metadata": feature.metadata,
            "registered_at": feature.registered_at.isoformat() if feature.registered_at else None,
        },
    }


@mcp.tool()
async def list_active_features() -> dict[str, Any]:
    """List all active features ordered by merge priority.

    Returns:
        List of active features with their resource claims and priorities
    """
    if _transport == "http":
        return await http_proxy.proxy_list_active_features()
    from .feature_registry import get_feature_registry_service

    service = get_feature_registry_service()
    features = await service.get_active_features()
    return {
        "features": [
            {
                "feature_id": f.feature_id,
                "title": f.title,
                "status": f.status,
                "registered_by": f.registered_by,
                "resource_claims": f.resource_claims,
                "branch_name": f.branch_name,
                "merge_priority": f.merge_priority,
                "registered_at": f.registered_at.isoformat() if f.registered_at else None,
            }
            for f in features
        ],
    }


@mcp.tool()
async def analyze_feature_conflicts(
    candidate_feature_id: str,
    candidate_claims: list[str],
) -> dict[str, Any]:
    """Analyze resource conflicts between a candidate and active features.

    Use before registration to check if a feature's resource claims
    overlap with other active features.

    Args:
        candidate_feature_id: Feature being analyzed
        candidate_claims: Lock keys the candidate intends to use

    Returns:
        feasibility: FULL (no conflicts), PARTIAL (some), or SEQUENTIAL (too many)
        conflicts: List of conflicting features and overlapping keys
    """
    if _transport == "http":
        return await http_proxy.proxy_analyze_feature_conflicts(
            candidate_feature_id=candidate_feature_id,
            candidate_claims=candidate_claims,
        )
    from .feature_registry import get_feature_registry_service

    service = get_feature_registry_service()
    report = await service.analyze_conflicts(candidate_feature_id, candidate_claims)
    return {
        "candidate_feature_id": report.candidate_feature_id,
        "feasibility": report.feasibility.value,
        "total_candidate_claims": report.total_candidate_claims,
        "total_conflicting_claims": report.total_conflicting_claims,
        "conflicts": report.conflicts,
    }


# =============================================================================
# MCP TOOLS: Merge Queue
# =============================================================================


@mcp.tool()
async def enqueue_merge(
    feature_id: str,
    pr_url: str | None = None,
) -> dict[str, Any]:
    """Add a feature to the merge queue for ordered merging.

    The feature must be active in the registry. Call this when a
    feature's PR is ready for merge.

    Args:
        feature_id: Feature to enqueue
        pr_url: URL of the pull request

    Returns:
        success: Whether enqueue succeeded
        entry: Queue entry with status and priority
    """
    if _transport == "http":
        return await http_proxy.proxy_enqueue_merge(
            feature_id=feature_id,
            pr_url=pr_url,
        )
    from .merge_queue import get_merge_queue_service

    service = get_merge_queue_service()
    entry = await service.enqueue(feature_id=feature_id, pr_url=pr_url)
    if entry is None:
        return {"success": False, "reason": "feature_not_found_or_not_active"}
    return {
        "success": True,
        "entry": {
            "feature_id": entry.feature_id,
            "branch_name": entry.branch_name,
            "merge_priority": entry.merge_priority,
            "merge_status": entry.merge_status.value,
            "pr_url": entry.pr_url,
        },
    }


@mcp.tool()
async def get_merge_queue() -> dict[str, Any]:
    """Get all features in the merge queue, ordered by priority.

    Returns:
        List of queued features with their merge status and priority
    """
    if _transport == "http":
        return await http_proxy.proxy_get_merge_queue()
    from .merge_queue import get_merge_queue_service

    service = get_merge_queue_service()
    entries = await service.get_queue()
    return {
        "entries": [
            {
                "feature_id": e.feature_id,
                "branch_name": e.branch_name,
                "merge_priority": e.merge_priority,
                "merge_status": e.merge_status.value,
                "pr_url": e.pr_url,
                "queued_at": e.queued_at.isoformat() if e.queued_at else None,
                "checked_at": e.checked_at.isoformat() if e.checked_at else None,
            }
            for e in entries
        ],
    }


@mcp.tool()
async def get_next_merge() -> dict[str, Any]:
    """Get the highest-priority feature ready to merge.

    Returns the first entry with status READY, or indicates none are ready.

    Returns:
        entry: Next feature to merge, or null if none ready
    """
    if _transport == "http":
        return await http_proxy.proxy_get_next_merge()
    from .merge_queue import get_merge_queue_service

    service = get_merge_queue_service()
    entry = await service.get_next_to_merge()
    if entry is None:
        return {"success": True, "entry": None, "reason": "no_features_ready"}
    return {
        "success": True,
        "entry": {
            "feature_id": entry.feature_id,
            "branch_name": entry.branch_name,
            "merge_priority": entry.merge_priority,
            "merge_status": entry.merge_status.value,
            "pr_url": entry.pr_url,
        },
    }


@mcp.tool()
async def run_pre_merge_checks(feature_id: str) -> dict[str, Any]:
    """Run pre-merge validation checks on a feature.

    Checks: feature is active, no new resource conflicts, feature is in queue.
    Updates merge status to READY or BLOCKED based on results.

    Args:
        feature_id: Feature to validate

    Returns:
        passed: Whether all checks passed
        checks: Individual check results
        issues: List of issues found
    """
    if _transport == "http":
        return await http_proxy.proxy_run_pre_merge_checks(feature_id=feature_id)
    from .merge_queue import get_merge_queue_service

    service = get_merge_queue_service()
    result = await service.run_pre_merge_checks(feature_id)
    return {
        "feature_id": result.feature_id,
        "passed": result.passed,
        "checks": result.checks,
        "issues": result.issues,
        "conflicts": result.conflicts,
    }


@mcp.tool()
async def mark_merged(feature_id: str) -> dict[str, Any]:
    """Mark a feature as merged and deregister it from the registry.

    Call this after successfully merging the feature's PR to main.
    Frees the feature's resource claims for other features.

    Args:
        feature_id: Feature that was merged

    Returns:
        success: Whether the operation succeeded
    """
    if _transport == "http":
        return await http_proxy.proxy_mark_merged(feature_id=feature_id)
    from .merge_queue import get_merge_queue_service

    service = get_merge_queue_service()
    success = await service.mark_merged(feature_id)
    return {"success": success, "feature_id": feature_id}


@mcp.tool()
async def remove_from_merge_queue(feature_id: str) -> dict[str, Any]:
    """Remove a feature from the merge queue without merging.

    Clears merge queue metadata but keeps the feature active in the registry.

    Args:
        feature_id: Feature to remove from queue

    Returns:
        success: Whether the feature was removed
    """
    if _transport == "http":
        return await http_proxy.proxy_remove_from_merge_queue(feature_id=feature_id)
    from .merge_queue import get_merge_queue_service

    service = get_merge_queue_service()
    success = await service.remove_from_queue(feature_id)
    return {"success": success, "feature_id": feature_id}


# =============================================================================
# MCP TOOLS: Status Reporting
# =============================================================================


@mcp.tool()
async def report_status(
    agent_id: str,
    change_id: str,
    phase: str,
    message: str = "",
    needs_human: bool = False,
    event_type: str = "phase_transition",
    metadata: dict[str, Any] | None = None,
) -> str:
    """Report agent status (phase transitions, escalations) to the coordinator.

    Called by hook scripts on Stop/SubagentStop events, or directly by agents
    to report phase transitions. Emits a coordinator_status NOTIFY event and
    updates the agent heartbeat.

    Args:
        agent_id: The agent reporting status
        change_id: OpenSpec change identifier
        phase: Current loop phase (e.g., PLAN, IMPLEMENT, ESCALATE)
        message: Human-readable status message
        needs_human: True if human intervention is needed (escalation)
        event_type: Event classification (default: phase_transition)
        metadata: Additional context

    Returns:
        JSON string with success status and urgency level
    """
    import json

    if _transport == "http":
        http_result = await http_proxy.proxy_report_status(
            agent_id=agent_id,
            change_id=change_id,
            phase=phase,
            message=message,
            needs_human=needs_human,
            event_type=event_type,
            metadata=metadata,
        )
        return json.dumps(http_result) if not isinstance(http_result, str) else http_result
    import logging

    from .discovery import get_discovery_service
    from .event_bus import CoordinatorEvent, classify_urgency, get_event_bus

    _log = logging.getLogger(__name__)

    # Update heartbeat (best-effort)
    try:
        discovery = get_discovery_service()
        await discovery.heartbeat()
    except Exception:  # noqa: BLE001
        _log.debug("Heartbeat update failed for MCP status report", exc_info=True)

    # Determine urgency
    urgency = classify_urgency(event_type)
    if needs_human and urgency != "high":
        urgency = "high"

    # Emit coordinator_status NOTIFY
    event = CoordinatorEvent(
        event_type=event_type,
        channel="coordinator_status",
        entity_id=change_id or "unknown",
        agent_id=agent_id,
        urgency=urgency,
        summary=f"[{phase}] {message}"[:200],
        change_id=change_id or None,
        context={
            "phase": phase,
            "needs_human": needs_human,
            **(metadata or {}),
        },
    )

    bus = get_event_bus()
    if bus.running and not bus.failed:
        try:
            import asyncpg

            conn = await asyncpg.connect(dsn=bus._dsn)  # noqa: SLF001
            try:
                await conn.execute(
                    "SELECT pg_notify($1, $2)",
                    "coordinator_status",
                    event.to_json(),
                )
            finally:
                await conn.close()
        except Exception:  # noqa: BLE001
            _log.debug("pg_notify failed for MCP status report", exc_info=True)

    return json.dumps({"success": True, "urgency": urgency})


# =============================================================================
# MCP RESOURCES: Read-only context
# =============================================================================


@mcp.resource("locks://current")
async def get_current_locks() -> str:
    """
    All currently active file locks.

    Shows which files are locked, by whom, and when they expire.
    """
    if _transport == "http":
        return _RESOURCE_UNAVAILABLE_IN_PROXY_MODE
    service = get_lock_service()
    locks = await service.check()

    if not locks:
        return "No active locks."

    lines = ["# Active File Locks\n"]
    for lock in locks:
        lines.append(f"- **{lock.file_path}**")
        lines.append(f"  - Locked by: {lock.locked_by} ({lock.agent_type})")
        lines.append(f"  - Reason: {lock.reason or 'Not specified'}")
        lines.append(f"  - Expires: {lock.expires_at.isoformat()}")
        lines.append("")

    return "\n".join(lines)


@mcp.resource("handoffs://recent")
async def get_recent_handoffs() -> str:
    """
    Recent handoff documents from agent sessions.

    Shows the latest session continuity documents across all agents.
    """
    if _transport == "http":
        return _RESOURCE_UNAVAILABLE_IN_PROXY_MODE
    service = get_handoff_service()
    handoffs = await service.get_recent(limit=5)

    if not handoffs:
        return "No handoff documents found."

    lines = ["# Recent Handoff Documents\n"]
    for h in handoffs:
        lines.append(f"## {h.agent_name}")
        if h.created_at:
            lines.append(f"*{h.created_at.isoformat()}*\n")
        lines.append(f"**Summary**: {h.summary}\n")
        if h.completed_work:
            lines.append("**Completed:**")
            for item in h.completed_work:
                lines.append(f"- {item}")
            lines.append("")
        if h.in_progress:
            lines.append("**In Progress:**")
            for item in h.in_progress:
                lines.append(f"- {item}")
            lines.append("")
        if h.next_steps:
            lines.append("**Next Steps:**")
            for item in h.next_steps:
                lines.append(f"- {item}")
            lines.append("")
        lines.append("---\n")

    return "\n".join(lines)


@mcp.resource("work://pending")
async def get_pending_work() -> str:
    """
    Tasks waiting to be claimed from the work queue.

    Shows available work organized by priority.
    """
    if _transport == "http":
        return _RESOURCE_UNAVAILABLE_IN_PROXY_MODE
    service = get_work_queue_service()
    tasks = await service.get_pending(limit=20)

    if not tasks:
        return "No pending tasks."

    lines = ["# Pending Work Queue\n"]
    current_priority = None

    for task in tasks:
        if task.priority != current_priority:
            current_priority = task.priority
            lines.append(f"\n## Priority {current_priority}\n")

        lines.append(f"- **{task.task_type}**: {task.description}")
        lines.append(f"  - ID: `{task.id}`")
        if task.deadline:
            lines.append(f"  - Deadline: {task.deadline.isoformat()}")
        lines.append("")

    return "\n".join(lines)


@mcp.resource("memories://recent")
async def get_recent_memories() -> str:
    """
    Recent episodic memories across all agents.

    Shows the latest memories with relevance scores and tags.
    """
    if _transport == "http":
        return _RESOURCE_UNAVAILABLE_IN_PROXY_MODE
    service = get_memory_service()
    result = await service.recall(limit=10)

    if not result.memories:
        return "No memories stored yet."

    lines = ["# Recent Memories\n"]
    for m in result.memories:
        lines.append(f"- **{m.event_type}**: {m.summary}")
        if m.tags:
            lines.append(f"  - Tags: {', '.join(m.tags)}")
        if m.outcome:
            lines.append(f"  - Outcome: {m.outcome}")
        if m.lessons:
            lines.append(f"  - Lessons: {'; '.join(m.lessons)}")
        lines.append("")

    return "\n".join(lines)


@mcp.resource("guardrails://patterns")
async def get_guardrail_patterns() -> str:
    """
    Active guardrail patterns for destructive operation detection.

    Shows all patterns that are currently being enforced.
    """
    if _transport == "http":
        return _RESOURCE_UNAVAILABLE_IN_PROXY_MODE
    service = get_guardrails_service()
    patterns = await service._load_patterns()

    if not patterns:
        return "No guardrail patterns configured."

    lines = ["# Active Guardrail Patterns\n"]
    current_category = None

    for p in sorted(patterns, key=lambda x: x.category):
        if p.category != current_category:
            current_category = p.category
            lines.append(f"\n## {current_category.title()}\n")

        lines.append(f"- **{p.name}** [{p.severity}] (trust >= {p.min_trust_level} to bypass)")
        lines.append(f"  - Pattern: `{p.pattern}`")
        lines.append("")

    return "\n".join(lines)


@mcp.resource("profiles://current")
async def get_current_profile() -> str:
    """
    Current agent's profile and permissions.

    Shows trust level, allowed operations, and resource limits.
    """
    if _transport == "http":
        return _RESOURCE_UNAVAILABLE_IN_PROXY_MODE
    service = get_profiles_service()
    result = await service.get_profile()

    if not result.success or not result.profile:
        return "No profile assigned. Using default permissions."

    p = result.profile
    lines = [
        f"# Agent Profile: {p.name}\n",
        f"- **Trust Level**: {p.trust_level}",
        f"- **Agent Type**: {p.agent_type}",
        f"- **Max File Modifications**: {p.max_file_modifications}",
        f"- **Source**: {result.source}",
        "",
        "## Allowed Operations",
    ]
    for op in p.allowed_operations:
        lines.append(f"- {op}")

    if p.blocked_operations:
        lines.append("\n## Blocked Operations")
        for op in p.blocked_operations:
            lines.append(f"- {op}")

    return "\n".join(lines)


@mcp.resource("audit://recent")
async def get_recent_audit() -> str:
    """
    Recent audit log entries.

    Shows the latest coordination operations across all agents.
    """
    if _transport == "http":
        return _RESOURCE_UNAVAILABLE_IN_PROXY_MODE
    service = get_audit_service()
    entries = await service.query(limit=20)

    if not entries:
        return "No audit log entries."

    lines = ["# Recent Audit Log\n"]
    for e in entries:
        status = "OK" if e.success else "FAIL"
        duration = f" ({e.duration_ms}ms)" if e.duration_ms else ""
        lines.append(f"- [{status}] **{e.operation}** by {e.agent_id}{duration}")
        if e.created_at:
            lines.append(f"  - {e.created_at.isoformat()}")
        if e.error_message:
            lines.append(f"  - Error: {e.error_message}")
        lines.append("")

    return "\n".join(lines)


@mcp.resource("features://active")
async def get_active_features_resource() -> str:
    """Active features in the registry with their resource claims and priorities."""
    if _transport == "http":
        return _RESOURCE_UNAVAILABLE_IN_PROXY_MODE
    from .feature_registry import get_feature_registry_service

    service = get_feature_registry_service()
    features = await service.get_active_features()

    if not features:
        return "No active features registered."

    lines = ["# Active Features\n"]
    for f in features:
        lines.append(f"## {f.feature_id}")
        if f.title:
            lines.append(f"**{f.title}**\n")
        lines.append(f"- Priority: {f.merge_priority}")
        lines.append(f"- Status: {f.status}")
        lines.append(f"- Registered by: {f.registered_by}")
        if f.branch_name:
            lines.append(f"- Branch: {f.branch_name}")
        if f.resource_claims:
            lines.append(f"- Claims: {', '.join(f.resource_claims[:10])}")
            if len(f.resource_claims) > 10:
                lines.append(f"  ... and {len(f.resource_claims) - 10} more")
        lines.append("")

    return "\n".join(lines)


@mcp.resource("merge-queue://pending")
async def get_merge_queue_resource() -> str:
    """Features queued for merge with their status and priority."""
    if _transport == "http":
        return _RESOURCE_UNAVAILABLE_IN_PROXY_MODE
    from .merge_queue import get_merge_queue_service

    service = get_merge_queue_service()
    entries = await service.get_queue()

    if not entries:
        return "No features in the merge queue."

    lines = ["# Merge Queue\n"]
    for e in entries:
        lines.append(f"- **{e.feature_id}** [{e.merge_status.value}] priority={e.merge_priority}")
        if e.pr_url:
            lines.append(f"  - PR: {e.pr_url}")
        if e.queued_at:
            lines.append(f"  - Queued: {e.queued_at.isoformat()}")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# GEN-EVAL: Generator-evaluator testing tools
# =============================================================================


@mcp.tool()
async def list_scenarios(
    category: str | None = None,
    interface: str | None = None,
) -> str:
    """
    List gen-eval test scenarios, optionally filtered by category or interface.

    Args:
        category: Filter to a specific category (e.g., "lock-lifecycle", "auth-boundary")
        interface: Filter to scenarios using a specific transport (e.g., "http", "mcp", "cli", "db")

    Returns:
        JSON list of scenarios with id, name, category, priority, interfaces, step count, and tags.
    """
    import json as json_mod

    if _transport == "http":
        result = await http_proxy.proxy_list_scenarios(
            category=category,
            interface=interface,
        )
        return json_mod.dumps(result) if not isinstance(result, str) else result

    from evaluation.gen_eval.mcp_service import get_gen_eval_service

    service = get_gen_eval_service()
    scenarios = await service.list_scenarios(category=category, interface=interface)

    return json_mod.dumps([
        {
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "priority": s.priority,
            "interfaces": s.interfaces,
            "step_count": s.step_count,
            "tags": s.tags,
            "has_cleanup": s.has_cleanup,
        }
        for s in scenarios
    ])


@mcp.tool()
async def validate_scenario(
    yaml_content: str,
) -> str:
    """
    Validate gen-eval scenario YAML against the Scenario model schema.

    Use this to check that a scenario YAML is well-formed before saving it.

    Args:
        yaml_content: The scenario YAML content to validate.

    Returns:
        Validation result: valid (bool), scenario_id, step_count, interfaces, and any errors.
    """
    import json as json_mod

    if _transport == "http":
        http_result = await http_proxy.proxy_validate_scenario(yaml_content=yaml_content)
        return json_mod.dumps(http_result) if not isinstance(http_result, str) else http_result

    from evaluation.gen_eval.mcp_service import get_gen_eval_service

    service = get_gen_eval_service()
    result = await service.validate_scenario(yaml_content)

    return json_mod.dumps({
        "valid": result.valid,
        "scenario_id": result.scenario_id,
        "step_count": result.step_count,
        "interfaces": result.interfaces,
        "errors": result.errors,
    })


@mcp.tool()
async def create_scenario(
    category: str,
    description: str,
    interfaces: list[str],
    scenario_type: str = "success",
    priority: int = 2,
) -> str:
    """
    Generate a scaffold scenario YAML from a description.

    Produces a YAML template with TODO placeholders for endpoints, tools, and
    assertions. Edit the TODO fields to complete the scenario. Does NOT write
    the file — use the returned YAML and suggested_path to save it.

    Args:
        category: Scenario category (e.g., "lock-lifecycle", "auth-boundary", "cross-interface")
        description: Human-readable description of what the scenario tests
        interfaces: List of transports to exercise (e.g., ["http", "mcp", "db"])
        scenario_type: "success" for happy-path or "failure" for error/edge-case scenarios
        priority: 1=critical, 2=important, 3=coverage

    Returns:
        Generated YAML string, suggested file path, step count, and interfaces.
    """
    import json as json_mod

    if _transport == "http":
        http_result = await http_proxy.proxy_create_scenario(
            category=category,
            description=description,
            interfaces=interfaces,
            scenario_type=scenario_type,
            priority=priority,
        )
        return json_mod.dumps(http_result) if not isinstance(http_result, str) else http_result

    from evaluation.gen_eval.mcp_service import get_gen_eval_service

    service = get_gen_eval_service()
    result = await service.create_scenario(
        category=category,
        description=description,
        interfaces=interfaces,
        scenario_type=scenario_type,
        priority=priority,
    )

    return json_mod.dumps(result)


@mcp.tool()
async def run_gen_eval(
    mode: str = "template-only",
    categories: list[str] | None = None,
    time_budget_minutes: float = 60.0,
) -> str:
    """
    Run gen-eval testing against the coordinator's interfaces.

    Executes test scenarios from the interface descriptor and returns a
    pass/fail summary. In template-only mode (default), this runs instantly
    with no LLM calls. In cli-augmented mode, it uses CLI tools covered by
    subscription for scenario generation.

    Args:
        mode: Execution mode — "template-only" (fast, no LLM), "cli-augmented"
              (subscription-covered LLM), or "sdk-only" (per-token cost)
        categories: Filter to specific categories (e.g., ["lock-lifecycle", "auth-boundary"]).
                    Omit to run all categories.
        time_budget_minutes: Time budget in minutes for CLI/SDK modes (default: 60)

    Returns:
        Success status and report summary (pass rate, coverage, failing interfaces).
    """
    import json as json_mod

    if _transport == "http":
        http_result = await http_proxy.proxy_run_gen_eval(
            mode=mode,
            categories=categories,
            time_budget_minutes=time_budget_minutes,
        )
        return json_mod.dumps(http_result) if not isinstance(http_result, str) else http_result

    from evaluation.gen_eval.mcp_service import get_gen_eval_service

    service = get_gen_eval_service()
    result = await service.run_evaluation(
        mode=mode,
        categories=categories,
        time_budget_minutes=time_budget_minutes,
    )

    return json_mod.dumps(result)


@mcp.resource("gen-eval://coverage")
async def get_gen_eval_coverage() -> str:
    """
    Gen-eval scenario coverage summary by category.

    Shows how many scenarios exist per category, which transports
    they exercise, and overall interface coverage percentage.
    """
    if _transport == "http":
        return _RESOURCE_UNAVAILABLE_IN_PROXY_MODE
    from evaluation.gen_eval.mcp_service import get_gen_eval_service

    service = get_gen_eval_service()
    coverage = await service.get_coverage()

    lines = ["# Gen-Eval Scenario Coverage\n"]
    lines.append(f"**Total scenarios**: {coverage.total_scenarios}")
    lines.append(f"**Interface coverage**: {coverage.coverage_pct:.0f}% "
                 f"({coverage.interfaces_covered}/{coverage.total_interfaces})\n")

    lines.append("| Category | Scenarios | Success | Failure | Transports |")
    lines.append("|----------|-----------|---------|---------|------------|")
    for cat in sorted(coverage.categories, key=lambda c: c.category):
        transports = ", ".join(cat.interfaces)
        lines.append(
            f"| {cat.category} | {cat.scenario_count} | "
            f"{cat.success_count} | {cat.failure_count} | {transports} |"
        )

    return "\n".join(lines)


@mcp.resource("gen-eval://report")
async def get_gen_eval_report() -> str:
    """
    Latest gen-eval report summary.

    Shows pass rate, coverage, failing interfaces, and categories
    below the 95% pass threshold from the most recent evaluation run.
    """
    if _transport == "http":
        return _RESOURCE_UNAVAILABLE_IN_PROXY_MODE
    from evaluation.gen_eval.mcp_service import get_gen_eval_service

    service = get_gen_eval_service()
    summary = await service.get_report_summary()

    if not summary:
        return "No gen-eval report found. Run `/gen-eval` or `make gen-eval` to generate one."

    lines = ["# Latest Gen-Eval Report\n"]
    lines.append(f"**Pass rate**: {summary['pass_rate']:.1%}")
    lines.append(f"**Coverage**: {summary['coverage_pct']:.0f}%")
    lines.append(f"**Scenarios**: {summary['passed']} passed, "
                 f"{summary['failed']} failed, {summary['errors']} errors "
                 f"(of {summary['total_scenarios']} total)")
    lines.append(f"**Budget exhausted**: {'Yes' if summary['budget_exhausted'] else 'No'}\n")

    if summary["failing_interfaces"]:
        lines.append("**Failing interfaces:**")
        for iface in summary["failing_interfaces"]:
            lines.append(f"- {iface}")
        lines.append("")

    if summary["categories_below_threshold"]:
        lines.append("**Categories below 95% threshold:**")
        for cat in summary["categories_below_threshold"]:
            lines.append(f"- {cat}")
        lines.append("")

    lines.append(f"*Report: {summary['report_path']}*")
    return "\n".join(lines)


# =============================================================================
# MCP PROMPTS: Reusable prompt templates
# =============================================================================


@mcp.prompt()
def coordinate_file_edit(file_path: str, task: str) -> str:
    """
    Template for safely editing a file with coordination.

    Includes lock acquisition, edit, and release pattern.
    """
    return f"""I need to edit {file_path} to {task}.

First, let me check if anyone else is working on this file:
1. Use check_locks to see current locks
2. Use acquire_lock to get exclusive access
3. Make my changes
4. Use release_lock when done

If the file is locked by someone else, I should either:
- Wait and retry later
- Work on a different task
- Coordinate via the work queue
"""


@mcp.prompt()
def start_work_session() -> str:
    """
    Template for starting a coordinated work session.

    Checks available work and current locks.
    """
    return """Starting a new work session. Let me:

1. Check for any pending work in the queue
2. Check what files are currently locked
3. Either claim work from the queue or start on assigned tasks

Before editing any files, I'll acquire locks to prevent conflicts.
After completing work, I'll release locks and mark tasks as done.
"""


# =============================================================================
# MAIN
# =============================================================================


def main() -> None:
    """Entry point for the MCP server."""
    import asyncio
    import logging
    import os

    from .telemetry import init_telemetry

    init_telemetry()

    # -----------------------------------------------------------------------
    # D1: Startup transport selection
    #
    # Probe the local PostgreSQL DSN and the HTTP API URL. If the DB is
    # reachable, use the existing "db" service-layer path. If the DB is
    # unreachable but the HTTP API is reachable, switch to "http" proxy
    # mode. If neither is reachable, default to "db" so the user sees the
    # existing DB connection error (preserves current failure mode).
    # -----------------------------------------------------------------------
    global _transport

    proxy_config = http_proxy.HttpProxyConfig.from_env()
    dsn = os.environ.get("POSTGRES_DSN", "")
    http_base_url = proxy_config.base_url if proxy_config else ""

    try:
        selected = asyncio.run(
            http_proxy.select_transport(dsn=dsn, http_base_url=http_base_url)
        )
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "Transport probe failed — defaulting to 'db'.",
            exc_info=True,
        )
        selected = "db"

    if selected == "http" and proxy_config is not None:
        _transport = "http"
        http_proxy.init_client(proxy_config)
        logging.getLogger(__name__).info(
            "Coordination MCP server running in HTTP proxy mode (target: %s)",
            proxy_config.base_url,
        )
    else:
        _transport = "db"
        logging.getLogger(__name__).info(
            "Coordination MCP server running with direct DB transport."
        )

        # Apply any pending database migrations before accepting tool calls.
        # Skip in HTTP proxy mode — migrations require direct DB access.
        from .migrations import ensure_schema

        try:
            applied = asyncio.run(ensure_schema())
            if applied:
                logging.getLogger(__name__).info(
                    "Applied %d pending migration(s) at startup.", len(applied)
                )
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "Migration check failed — continuing with existing schema.",
                exc_info=True,
            )

    # Default to stdio transport (for Claude Code integration)
    transport = "stdio"
    port = 8082

    for arg in sys.argv[1:]:
        if arg.startswith("--transport="):
            transport = arg.split("=")[1]
        elif arg.startswith("--port="):
            port = int(arg.split("=")[1])

    if transport == "sse":
        # Run as SSE server (for testing or remote agents)
        mcp.run(transport="sse", port=port)
    else:
        # Run as stdio (for direct Claude Code integration)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
