"""
Coordination API - Handles write operations from cloud agents.

Cloud agents can READ directly from Supabase (using anon key).
Cloud agents must WRITE through this API (using API key).

This ensures:
1. Policy enforcement on writes
2. Audit trail of all modifications
3. Side effects (notifications, triggers) are handled consistently
4. Race conditions are managed via database transactions
"""

import os
from datetime import datetime

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

# =============================================================================
# CONFIGURATION
# =============================================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")  # Full access
COORDINATION_API_KEYS = os.environ.get("COORDINATION_API_KEYS", "").split(",")


# =============================================================================
# MODELS
# =============================================================================

class LockRequest(BaseModel):
    file_path: str
    agent_id: str
    agent_type: str
    session_id: str | None = None
    reason: str | None = None
    ttl_minutes: int = 30


class LockReleaseRequest(BaseModel):
    file_path: str
    agent_id: str


class MemoryStoreRequest(BaseModel):
    agent_id: str
    session_id: str | None = None
    event_type: str
    summary: str
    details: dict | None = None
    outcome: str | None = None
    lessons: list[str] | None = None
    tags: list[str] | None = None


class MemoryQueryRequest(BaseModel):
    agent_id: str
    task_description: str
    tags: list[str] | None = None
    limit: int = 10


class WorkClaimRequest(BaseModel):
    agent_id: str
    agent_type: str
    task_types: list[str] | None = None


class WorkCompleteRequest(BaseModel):
    task_id: str
    agent_id: str
    success: bool
    result: dict | None = None
    error_message: str | None = None


class WorkingMemoryUpdate(BaseModel):
    agent_id: str
    session_id: str
    context_item: dict  # {type: str, content: str, timestamp: str}


# =============================================================================
# AUTH
# =============================================================================

async def verify_api_key(x_api_key: str = Header(...)):
    """Verify the API key for write operations"""
    if x_api_key not in COORDINATION_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# =============================================================================
# SUPABASE CLIENT
# =============================================================================

class SupabaseClient:
    """Thin wrapper for Supabase RPC calls"""

    def __init__(self):
        self.url = SUPABASE_URL
        self.key = SUPABASE_SERVICE_KEY
        self._client = httpx.AsyncClient()

    async def rpc(self, function_name: str, params: dict) -> dict:
        """Call a Supabase RPC function"""
        response = await self._client.post(
            f"{self.url}/rest/v1/rpc/{function_name}",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
            },
            json=params,
        )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Supabase error: {response.text}"
            )

        return response.json()

    async def insert(self, table: str, data: dict) -> dict:
        """Insert a row into a table"""
        response = await self._client.post(
            f"{self.url}/rest/v1/{table}",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=data,
        )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Supabase error: {response.text}"
            )

        return response.json()

    async def update(self, table: str, match: dict, data: dict) -> dict:
        """Update rows matching criteria"""
        # Build query string from match criteria
        query_parts = [f"{k}=eq.{v}" for k, v in match.items()]
        query_string = "&".join(query_parts)

        response = await self._client.patch(
            f"{self.url}/rest/v1/{table}?{query_string}",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=data,
        )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Supabase error: {response.text}"
            )

        return response.json()


db = SupabaseClient()


# =============================================================================
# API ROUTES
# =============================================================================

def create_coordination_api() -> FastAPI:
    """Create the coordination API application"""

    app = FastAPI(
        title="Agent Coordination API",
        description="Write operations for multi-agent coordination",
    )

    # -------------------------------------------------------------------------
    # FILE LOCKS
    # -------------------------------------------------------------------------

    @app.post("/locks/acquire")
    async def acquire_lock(
        request: LockRequest,
        _: str = Depends(verify_api_key),
    ):
        """
        Acquire a file lock.

        Cloud agents call this before modifying files.
        Returns success/failure and lock details.
        """
        result = await db.rpc("acquire_file_lock", {
            "p_file_path": request.file_path,
            "p_agent_id": request.agent_id,
            "p_agent_type": request.agent_type,
            "p_session_id": request.session_id,
            "p_reason": request.reason,
            "p_ttl_minutes": request.ttl_minutes,
        })

        return result

    @app.post("/locks/release")
    async def release_lock(
        request: LockReleaseRequest,
        _: str = Depends(verify_api_key),
    ):
        """
        Release a file lock.

        Called when agent completes work or encounters an error.
        """
        await db.update(
            "file_locks",
            {"file_path": request.file_path, "locked_by": request.agent_id},
            {"expires_at": datetime.utcnow().isoformat()},  # Immediate expiry
        )

        return {"success": True, "released": request.file_path}

    @app.get("/locks/status/{file_path:path}")
    async def check_lock_status(file_path: str):
        """
        Check lock status for a file.

        This is READ-ONLY and doesn't require API key.
        Cloud agents can also query Supabase directly.
        """
        # This would typically go direct to Supabase from the agent
        # Included here for completeness
        pass

    # -------------------------------------------------------------------------
    # MEMORY OPERATIONS
    # -------------------------------------------------------------------------

    @app.post("/memory/episodic/store")
    async def store_episodic_memory(
        request: MemoryStoreRequest,
        _: str = Depends(verify_api_key),
    ):
        """
        Store an episodic memory (experience/event).

        Includes deduplication - similar recent memories are merged.
        """
        result = await db.rpc("store_episodic_memory", {
            "p_agent_id": request.agent_id,
            "p_session_id": request.session_id,
            "p_event_type": request.event_type,
            "p_summary": request.summary,
            "p_details": request.details,
            "p_outcome": request.outcome,
            "p_lessons": request.lessons,
            "p_tags": request.tags,
        })

        return {"success": True, "memory_id": result}

    @app.post("/memory/query")
    async def query_memories(
        request: MemoryQueryRequest,
        _: str = Depends(verify_api_key),
    ):
        """
        Query relevant memories for a task.

        Returns both episodic (experiences) and procedural (skills) memories.
        """
        result = await db.rpc("get_relevant_memories", {
            "p_agent_id": request.agent_id,
            "p_task_description": request.task_description,
            "p_tags": request.tags,
            "p_limit": request.limit,
        })

        return {"memories": result}

    @app.post("/memory/working/update")
    async def update_working_memory(
        request: WorkingMemoryUpdate,
        _: str = Depends(verify_api_key),
    ):
        """
        Add item to working memory.

        Working memory is compressed when it exceeds token budget.
        """
        # Get current working memory
        # This is simplified - production would handle compression
        await db.rpc("append_working_memory", {
            "p_agent_id": request.agent_id,
            "p_session_id": request.session_id,
            "p_context_item": request.context_item,
        })

        return {"success": True}

    @app.post("/memory/procedural/record-use")
    async def record_skill_use(
        skill_id: str,
        success: bool,
        _: str = Depends(verify_api_key),
    ):
        """
        Record that a skill was used (for Thompson sampling).

        Updates success rate which influences future suggestions.
        """
        if success:
            await db.rpc("increment_skill_success", {"p_skill_id": skill_id})
        else:
            await db.rpc("increment_skill_attempt", {"p_skill_id": skill_id})

        return {"success": True}

    # -------------------------------------------------------------------------
    # WORK QUEUE
    # -------------------------------------------------------------------------

    @app.post("/work/claim")
    async def claim_work(
        request: WorkClaimRequest,
        _: str = Depends(verify_api_key),
    ):
        """
        Claim a task from the work queue.

        Returns the highest priority task this agent can handle.
        Atomic - prevents multiple agents claiming same task.
        """
        result = await db.rpc("claim_work", {
            "p_agent_id": request.agent_id,
            "p_agent_type": request.agent_type,
            "p_task_types": request.task_types,
        })

        return result

    @app.post("/work/complete")
    async def complete_work(
        request: WorkCompleteRequest,
        _: str = Depends(verify_api_key),
    ):
        """
        Mark a task as completed.

        Triggers downstream verification if configured.
        """
        status = "completed" if request.success else "failed"

        await db.update(
            "work_queue",
            {"id": request.task_id, "assigned_to": request.agent_id},
            {
                "status": status,
                "result": request.result,
                "error_message": request.error_message,
                "completed_at": datetime.utcnow().isoformat(),
            },
        )

        # Trigger verification gateway if this was a code change
        # (This would integrate with the verification gateway from gateway.py)

        return {"success": True, "status": status}

    @app.post("/work/submit")
    async def submit_work(
        task_type: str,
        task_description: str,
        input_data: dict = None,
        priority: int = 5,
        preferred_agent_type: str = None,
        depends_on: list[str] = None,
        _: str = Depends(verify_api_key),
    ):
        """
        Submit new work to the queue.

        Used by orchestrators or agents spawning subtasks.
        """
        result = await db.insert("work_queue", {
            "task_type": task_type,
            "task_description": task_description,
            "input_data": input_data,
            "priority": priority,
            "preferred_agent_type": preferred_agent_type,
            "depends_on": depends_on,
        })

        return {"success": True, "task_id": result[0]["id"]}

    # -------------------------------------------------------------------------
    # NEWSLETTER-SPECIFIC
    # -------------------------------------------------------------------------

    @app.post("/newsletter/record-summary")
    async def record_newsletter_summary(
        newsletter_id: str,
        summary: str,
        tokens_used: int,
        agent_id: str,
        _: str = Depends(verify_api_key),
    ):
        """
        Record a completed newsletter summary.

        Called by Haiku summarization agents.
        """
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

    return app


# =============================================================================
# AGENT SDK (for cloud agents to use)
# =============================================================================

class AgentCoordinationClient:
    """
    SDK for agents to interact with the coordination API.

    Usage:
        client = AgentCoordinationClient(
            api_url="https://coordination.yourdomain.com",
            api_key="your-api-key",
            agent_id="claude-haiku-1",
            agent_type="claude_api",
        )

        # Check if file is locked (direct Supabase read)
        is_locked = await client.is_file_locked("src/main.py")

        # Acquire lock (via coordination API)
        lock = await client.acquire_lock("src/main.py", reason="refactoring")

        # Get relevant memories
        memories = await client.get_memories("implement caching for API calls")

        # Store what we learned
        await client.store_memory(
            event_type="task_completed",
            summary="Added Redis caching to API client",
            outcome="success",
            lessons=["Use TTL of 5 minutes for user data"],
        )
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        agent_id: str,
        agent_type: str,
        supabase_url: str = None,
        supabase_anon_key: str = None,
        session_id: str = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.session_id = session_id

        # For direct reads
        self.supabase_url = supabase_url
        self.supabase_anon_key = supabase_anon_key

        self._http = httpx.AsyncClient()

    async def _api_call(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Make an API call to the coordination service"""
        response = await self._http.request(
            method,
            f"{self.api_url}{endpoint}",
            headers={"X-API-Key": self.api_key},
            json=data,
        )
        response.raise_for_status()
        return response.json()

    async def _supabase_read(self, table: str, query: str = "") -> list:
        """Direct read from Supabase"""
        if not self.supabase_url:
            raise ValueError("Supabase URL not configured for direct reads")

        response = await self._http.get(
            f"{self.supabase_url}/rest/v1/{table}?{query}",
            headers={
                "apikey": self.supabase_anon_key,
                "Authorization": f"Bearer {self.supabase_anon_key}",
            },
        )
        response.raise_for_status()
        return response.json()

    # --- File Locks ---

    async def is_file_locked(self, file_path: str) -> dict | None:
        """Check if a file is locked (direct Supabase read)"""
        locks = await self._supabase_read(
            "file_locks",
            f"file_path=eq.{file_path}&expires_at=gt.now()"
        )
        return locks[0] if locks else None

    async def acquire_lock(
        self,
        file_path: str,
        reason: str = None,
        ttl_minutes: int = 30,
    ) -> dict:
        """Acquire a file lock (via coordination API)"""
        return await self._api_call("POST", "/locks/acquire", {
            "file_path": file_path,
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "session_id": self.session_id,
            "reason": reason,
            "ttl_minutes": ttl_minutes,
        })

    async def release_lock(self, file_path: str) -> dict:
        """Release a file lock"""
        return await self._api_call("POST", "/locks/release", {
            "file_path": file_path,
            "agent_id": self.agent_id,
        })

    # --- Memory ---

    async def get_memories(
        self,
        task_description: str,
        tags: list[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """Get relevant memories for a task"""
        result = await self._api_call("POST", "/memory/query", {
            "agent_id": self.agent_id,
            "task_description": task_description,
            "tags": tags,
            "limit": limit,
        })
        return result.get("memories", [])

    async def store_memory(
        self,
        event_type: str,
        summary: str,
        details: dict = None,
        outcome: str = None,
        lessons: list[str] = None,
        tags: list[str] = None,
    ) -> str:
        """Store an episodic memory"""
        result = await self._api_call("POST", "/memory/episodic/store", {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "event_type": event_type,
            "summary": summary,
            "details": details,
            "outcome": outcome,
            "lessons": lessons,
            "tags": tags,
        })
        return result.get("memory_id")

    # --- Work Queue ---

    async def claim_work(self, task_types: list[str] = None) -> dict | None:
        """Claim a task from the work queue"""
        result = await self._api_call("POST", "/work/claim", {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "task_types": task_types,
        })
        return result if result.get("success") else None

    async def complete_work(
        self,
        task_id: str,
        success: bool,
        result: dict = None,
        error_message: str = None,
    ) -> dict:
        """Mark a task as completed"""
        return await self._api_call("POST", "/work/complete", {
            "task_id": task_id,
            "agent_id": self.agent_id,
            "success": success,
            "result": result,
            "error_message": error_message,
        })


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    app = create_coordination_api()
    uvicorn.run(app, host="0.0.0.0", port=8081)
