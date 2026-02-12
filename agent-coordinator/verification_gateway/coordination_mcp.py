"""
Coordination MCP Server - Exposes coordination capabilities as native tools.

Local agents (Claude Code, Codex CLI, Aider) connect to this MCP server
and get coordination tools alongside their standard tools.

Usage:
    # In Claude Code's MCP config (~/.claude/mcp.json):
    {
        "servers": {
            "coordination": {
                "command": "python",
                "args": ["/path/to/coordination_mcp.py"],
                "env": {
                    "SUPABASE_URL": "...",
                    "SUPABASE_SERVICE_KEY": "..."
                }
            }
        }
    }

    # Or run standalone for testing:
    python coordination_mcp.py --transport sse --port 8082
"""

import os
from datetime import datetime

import httpx
from fastmcp import Context, FastMCP

# =============================================================================
# CONFIGURATION
# =============================================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

# Create the MCP server
mcp = FastMCP(
    name="coordination",
    version="1.0.0",
    description="Multi-agent coordination: locks, memory, and work queue",
)


# =============================================================================
# SUPABASE CLIENT (shared with HTTP API)
# =============================================================================

class SupabaseClient:
    """Async Supabase client for coordination operations"""

    def __init__(self):
        self.url = SUPABASE_URL
        self.key = SUPABASE_SERVICE_KEY
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def rpc(self, function_name: str, params: dict) -> dict:
        """Call a Supabase RPC function"""
        response = await self.client.post(
            f"{self.url}/rest/v1/rpc/{function_name}",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
            },
            json=params,
        )
        response.raise_for_status()
        return response.json()

    async def query(self, table: str, query_string: str = "") -> list:
        """Query a table"""
        url = f"{self.url}/rest/v1/{table}"
        if query_string:
            url += f"?{query_string}"

        response = await self.client.get(
            url,
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
            },
        )
        response.raise_for_status()
        return response.json()

    async def insert(self, table: str, data: dict) -> dict:
        """Insert a row"""
        response = await self.client.post(
            f"{self.url}/rest/v1/{table}",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=data,
        )
        response.raise_for_status()
        result = response.json()
        return result[0] if result else {}

    async def update(self, table: str, match: dict, data: dict) -> list:
        """Update matching rows"""
        query_parts = [f"{k}=eq.{v}" for k, v in match.items()]
        query_string = "&".join(query_parts)

        response = await self.client.patch(
            f"{self.url}/rest/v1/{table}?{query_string}",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=data,
        )
        response.raise_for_status()
        return response.json()

    async def delete(self, table: str, match: dict) -> None:
        """Delete matching rows"""
        query_parts = [f"{k}=eq.{v}" for k, v in match.items()]
        query_string = "&".join(query_parts)

        response = await self.client.delete(
            f"{self.url}/rest/v1/{table}?{query_string}",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
            },
        )
        response.raise_for_status()


db = SupabaseClient()


# =============================================================================
# HELPER: Get agent identity from context
# =============================================================================

def get_agent_id(ctx: Context) -> str:
    """
    Extract agent ID from MCP context.

    Falls back to a generated ID if not available.
    In production, this might come from:
    - Environment variable injected by NTM
    - MCP client metadata
    - Session tracking
    """
    # Try to get from context metadata (if your MCP client provides it)
    # For now, use environment or generate
    return os.environ.get("AGENT_ID", f"agent-{os.getpid()}")


def get_agent_type() -> str:
    """Get agent type from environment"""
    return os.environ.get("AGENT_TYPE", "claude_code")


def get_session_id() -> str | None:
    """Get session ID if available"""
    return os.environ.get("SESSION_ID")


# =============================================================================
# MCP TOOLS: File Locks
# =============================================================================

@mcp.tool()
async def acquire_lock(
    file_path: str,
    reason: str | None = None,
    ttl_minutes: int = 30,
    ctx: Context = None,
) -> dict:
    """
    Acquire an exclusive lock on a file before modifying it.

    Use this before editing any file that other agents might also be working on.
    The lock automatically expires after ttl_minutes (default 30).

    Args:
        file_path: Path to the file to lock (relative to repo root)
        reason: Why you need the lock (helps with debugging)
        ttl_minutes: How long to hold the lock (default 30 minutes)

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
    agent_id = get_agent_id(ctx)
    agent_type = get_agent_type()
    session_id = get_session_id()

    result = await db.rpc("acquire_file_lock", {
        "p_file_path": file_path,
        "p_agent_id": agent_id,
        "p_agent_type": agent_type,
        "p_session_id": session_id,
        "p_reason": reason,
        "p_ttl_minutes": ttl_minutes,
    })

    return result


@mcp.tool()
async def release_lock(
    file_path: str,
    ctx: Context = None,
) -> dict:
    """
    Release a lock you previously acquired.

    Always release locks when you're done editing a file, even if you
    encountered an error. This lets other agents proceed.

    Args:
        file_path: Path to the file to unlock

    Returns:
        success: Whether the lock was released
        released: The file path that was unlocked
    """
    agent_id = get_agent_id(ctx)

    await db.delete("file_locks", {
        "file_path": file_path,
        "locked_by": agent_id,
    })

    return {"success": True, "released": file_path}


@mcp.tool()
async def check_locks(
    file_paths: list[str] | None = None,
) -> list[dict]:
    """
    Check which files are currently locked.

    Use this before starting work to see if files you need are available.

    Args:
        file_paths: Specific files to check (or None for all locks)

    Returns:
        List of active locks with file_path, locked_by, reason, expires_at
    """
    query = "expires_at=gt.now()&order=locked_at.desc"

    if file_paths:
        paths_filter = ",".join(f'"{p}"' for p in file_paths)
        query += f"&file_path=in.({paths_filter})"

    locks = await db.query("file_locks", query)
    return locks


# =============================================================================
# MCP TOOLS: Memory
# =============================================================================

@mcp.tool()
async def remember(
    event_type: str,
    summary: str,
    details: dict | None = None,
    outcome: str | None = None,
    lessons: list[str] | None = None,
    tags: list[str] | None = None,
    ctx: Context = None,
) -> dict:
    """
    Store a memory of something you learned or accomplished.

    Use this to record:
    - Solutions to problems you solved
    - Patterns that worked well
    - Mistakes to avoid
    - Useful discoveries

    These memories can be retrieved later by you or other agents.

    Args:
        event_type: Category of memory ('task_completed', 'error_resolved',
                    'discovery', 'pattern_found', 'mistake_made')
        summary: Brief description (1-2 sentences)
        details: Additional structured data (optional)
        outcome: 'success', 'failure', or 'partial' (optional)
        lessons: List of specific lessons learned (optional)
        tags: Tags for retrieval (e.g., ['python', 'caching', 'api'])

    Returns:
        memory_id: ID of the stored memory

    Example:
        remember(
            event_type="error_resolved",
            summary="Fixed race condition in cache invalidation",
            outcome="success",
            lessons=["Always use Redis WATCH for read-modify-write"],
            tags=["redis", "caching", "concurrency"]
        )
    """
    agent_id = get_agent_id(ctx)
    session_id = get_session_id()

    result = await db.rpc("store_episodic_memory", {
        "p_agent_id": agent_id,
        "p_session_id": session_id,
        "p_event_type": event_type,
        "p_summary": summary,
        "p_details": details,
        "p_outcome": outcome,
        "p_lessons": lessons,
        "p_tags": tags,
    })

    return {"success": True, "memory_id": result}


@mcp.tool()
async def recall(
    task_description: str,
    tags: list[str] | None = None,
    limit: int = 10,
    ctx: Context = None,
) -> list[dict]:
    """
    Retrieve relevant memories for your current task.

    Use this at the start of a task to see if you or other agents
    have encountered similar problems before.

    Args:
        task_description: What you're trying to do
        tags: Filter by specific tags (optional)
        limit: Maximum memories to return (default 10)

    Returns:
        List of relevant memories with type, content, and relevance score

    Example:
        memories = recall(
            task_description="implement Redis caching for API responses",
            tags=["redis", "caching"]
        )
        for m in memories:
            print(f"{m['memory_type']}: {m['content']}")
    """
    agent_id = get_agent_id(ctx)

    result = await db.rpc("get_relevant_memories", {
        "p_agent_id": agent_id,
        "p_task_description": task_description,
        "p_tags": tags,
        "p_limit": limit,
    })

    return result if result else []


# =============================================================================
# MCP TOOLS: Work Queue
# =============================================================================

@mcp.tool()
async def get_work(
    task_types: list[str] | None = None,
    ctx: Context = None,
) -> dict:
    """
    Claim a task from the work queue.

    Tasks are assigned atomically - if you get a task, no other agent will.
    You should complete or release the task when done.

    Args:
        task_types: Only claim these types of tasks (optional)
                   Examples: 'summarize', 'refactor', 'test', 'verify'

    Returns:
        success: Whether a task was claimed
        task_id: ID for completing the task
        task_type: Type of task
        task_description: What to do
        input_data: Task-specific input
        deadline: When it needs to be done (if set)

    Example:
        work = get_work(task_types=["summarize", "refactor"])
        if work["success"]:
            # Do the work...
            complete_work(work["task_id"], success=True, result={...})
    """
    agent_id = get_agent_id(ctx)
    agent_type = get_agent_type()

    result = await db.rpc("claim_work", {
        "p_agent_id": agent_id,
        "p_agent_type": agent_type,
        "p_task_types": task_types,
    })

    return result


@mcp.tool()
async def complete_work(
    task_id: str,
    success: bool,
    result: dict | None = None,
    error_message: str | None = None,
    ctx: Context = None,
) -> dict:
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
    agent_id = get_agent_id(ctx)

    status = "completed" if success else "failed"

    await db.update(
        "work_queue",
        {"id": task_id, "assigned_to": agent_id},
        {
            "status": status,
            "result": result,
            "error_message": error_message,
            "completed_at": datetime.utcnow().isoformat(),
        },
    )

    return {"success": True, "status": status}


@mcp.tool()
async def submit_work(
    task_type: str,
    task_description: str,
    input_data: dict | None = None,
    priority: int = 5,
    depends_on: list[str] | None = None,
    ctx: Context = None,
) -> dict:
    """
    Submit a new task to the work queue.

    Use this to create subtasks or delegate work to other agents.

    Args:
        task_type: Category of task ('summarize', 'refactor', 'test', etc.)
        task_description: What needs to be done
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
            task_description="Write unit tests for cache module",
            input_data={"files": ["src/cache.py"]},
            priority=3
        )
    """
    result = await db.insert("work_queue", {
        "task_type": task_type,
        "task_description": task_description,
        "input_data": input_data,
        "priority": priority,
        "depends_on": depends_on,
    })

    return {"success": True, "task_id": result["id"]}


# =============================================================================
# MCP TOOLS: Newsletter-Specific
# =============================================================================

@mcp.tool()
async def get_pending_newsletters(
    limit: int = 10,
) -> list[dict]:
    """
    Get newsletters that need summarization.

    Returns newsletters that have been fetched but not yet summarized.

    Args:
        limit: Maximum number to return (default 10)

    Returns:
        List of newsletters with id, sender, subject, received_at
    """
    newsletters = await db.query(
        "newsletter_processing",
        f"summarize_status=eq.pending&order=received_at.asc&limit={limit}"
    )

    return newsletters


@mcp.tool()
async def record_newsletter_summary(
    newsletter_id: str,
    summary: str,
    tokens_used: int,
    ctx: Context = None,
) -> dict:
    """
    Record a completed newsletter summary.

    Call this after successfully summarizing a newsletter.

    Args:
        newsletter_id: ID of the newsletter
        summary: The generated summary
        tokens_used: How many tokens the summarization used

    Returns:
        success: Whether the summary was recorded
    """
    agent_id = get_agent_id(ctx)

    await db.update(
        "newsletter_processing",
        {"id": newsletter_id},
        {
            "haiku_summary": summary,
            "haiku_tokens_used": tokens_used,
            "processing_agent": agent_id,
            "summarize_status": "completed",
            "summarized_at": datetime.utcnow().isoformat(),
        },
    )

    return {"success": True}


# =============================================================================
# MCP RESOURCES: Read-only context
# =============================================================================

@mcp.resource("locks://current")
async def get_current_locks() -> str:
    """
    All currently active file locks.

    Shows which files are locked, by whom, and when they expire.
    """
    locks = await db.query("file_locks", "expires_at=gt.now()&order=locked_at.desc")

    if not locks:
        return "No active locks."

    lines = ["# Active File Locks\n"]
    for lock in locks:
        lines.append(f"- **{lock['file_path']}**")
        lines.append(f"  - Locked by: {lock['locked_by']} ({lock['agent_type']})")
        lines.append(f"  - Reason: {lock.get('lock_reason', 'Not specified')}")
        lines.append(f"  - Expires: {lock['expires_at']}")
        lines.append("")

    return "\n".join(lines)


@mcp.resource("work://pending")
async def get_pending_work() -> str:
    """
    Tasks waiting to be claimed from the work queue.

    Shows available work organized by priority.
    """
    tasks = await db.query(
        "work_queue",
        "status=eq.pending&order=priority.asc,created_at.asc&limit=20"
    )

    if not tasks:
        return "No pending tasks."

    lines = ["# Pending Work Queue\n"]
    current_priority = None

    for task in tasks:
        if task['priority'] != current_priority:
            current_priority = task['priority']
            lines.append(f"\n## Priority {current_priority}\n")

        lines.append(f"- **{task['task_type']}**: {task['task_description']}")
        lines.append(f"  - ID: `{task['id']}`")
        if task.get('preferred_agent_type'):
            lines.append(f"  - Preferred: {task['preferred_agent_type']}")
        if task.get('deadline'):
            lines.append(f"  - Deadline: {task['deadline']}")
        lines.append("")

    return "\n".join(lines)


@mcp.resource("newsletters://status")
async def get_newsletter_status() -> str:
    """
    Current newsletter processing status.

    Shows how many newsletters are pending, processing, and completed.
    """
    # Get counts by status
    pending = await db.query(
        "newsletter_processing",
        "summarize_status=eq.pending&select=count"
    )
    completed = await db.query(
        "newsletter_processing",
        "summarize_status=eq.completed&select=count"
    )

    # Get recent completions
    recent = await db.query(
        "newsletter_processing",
        "summarize_status=eq.completed&order=summarized_at.desc&limit=5"
    )

    lines = [
        "# Newsletter Processing Status\n",
        f"- Pending: {pending[0]['count'] if pending else 0}",
        f"- Completed: {completed[0]['count'] if completed else 0}",
        "\n## Recently Processed\n",
    ]

    for n in recent:
        lines.append(f"- {n['subject'][:50]}... ({n['processing_agent']})")

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

    Recalls relevant memories and checks available work.
    """
    return """Starting a new work session. Let me:

1. Check for any pending work assigned to me
2. Recall memories relevant to my current tasks
3. Check what files are currently locked

Then I can either:
- Claim new work from the queue
- Continue on previously started tasks
- Pick up work that others have submitted
"""


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import sys

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
