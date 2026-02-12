"""Coordination MCP Server - Multi-agent coordination tools for AI coding assistants.

This MCP server provides tools for:
- File locking to prevent concurrent edits
- Work queue for task assignment and tracking
- Session continuity via handoff documents
- Agent discovery and heartbeat monitoring

Usage (Claude Code):
    Add to ~/.claude/mcp.json:
    {
        "servers": {
            "coordination": {
                "command": "python",
                "args": ["-m", "src.coordination_mcp"],
                "cwd": "/path/to/agent-coordinator",
                "env": {
                    "SUPABASE_URL": "https://xxx.supabase.co",
                    "SUPABASE_SERVICE_KEY": "your-key"
                }
            }
        }
    }

Usage (standalone for testing):
    python -m src.coordination_mcp --transport sse --port 8082
"""

import sys
from typing import Any

from fastmcp import FastMCP

from .config import get_config
from .discovery import get_discovery_service
from .handoffs import get_handoff_service
from .locks import get_lock_service
from .work_queue import get_work_queue_service

# Create the MCP server
mcp = FastMCP(
    name="coordination",
    version="0.2.0",
    description="Multi-agent coordination: file locks, work queue, handoffs, and discovery",  # type: ignore[call-arg]
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
) -> dict[str, Any]:
    """
    Register this agent session for discovery by other agents.

    Call this at the start of a work session to make yourself discoverable.
    Other agents can then find you via discover_agents().

    Args:
        capabilities: What this agent can do (e.g., ['coding', 'testing', 'review'])
        current_task: Description of what you're currently working on

    Returns:
        success: Whether registration succeeded
        session_id: The registered session ID

    Example:
        register_session(
            capabilities=["coding", "testing"],
            current_task="Implementing file locking feature"
        )
    """
    service = get_discovery_service()
    result = await service.register(
        capabilities=capabilities,
        current_task=current_task,
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
# MCP RESOURCES: Read-only context
# =============================================================================


@mcp.resource("locks://current")
async def get_current_locks() -> str:
    """
    All currently active file locks.

    Shows which files are locked, by whom, and when they expire.
    """
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
