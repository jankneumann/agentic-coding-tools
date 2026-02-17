"""Coordination HTTP API — write endpoints for cloud agents.

Cloud agents can READ directly from Supabase (using anon key).
Cloud agents must WRITE through this API (using API key).

This ensures:
1. Policy enforcement on writes
2. Audit trail of all modifications
3. Race conditions are managed via service-layer abstractions
"""

from __future__ import annotations

import sys
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .config import get_config

# =============================================================================
# Pydantic request / response models
# =============================================================================


class LockAcquireRequest(BaseModel):
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
    details: dict[str, Any] | None = None
    outcome: str | None = None
    lessons: list[str] | None = None
    tags: list[str] | None = None


class MemoryQueryRequest(BaseModel):
    agent_id: str
    tags: list[str] | None = None
    event_type: str | None = None
    limit: int = 10


class WorkClaimRequest(BaseModel):
    agent_id: str
    agent_type: str
    task_types: list[str] | None = None


class WorkCompleteRequest(BaseModel):
    task_id: str
    agent_id: str
    success: bool
    result: dict[str, Any] | None = None
    error_message: str | None = None


class WorkSubmitRequest(BaseModel):
    task_type: str
    task_description: str
    input_data: dict[str, Any] | None = None
    priority: int = 5
    depends_on: list[str] | None = None


class GuardrailsCheckRequest(BaseModel):
    operation_text: str
    file_paths: list[str] | None = None


class AuditQueryParams(BaseModel):
    agent_id: str | None = None
    operation: str | None = None
    limit: int = 20


# =============================================================================
# Auth helpers
# =============================================================================


async def verify_api_key(x_api_key: str | None = Header(None)) -> dict[str, Any]:
    """Verify the API key for write operations."""
    config = get_config()
    if not x_api_key or x_api_key not in config.api.api_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
    identity = config.api.api_key_identities.get(x_api_key, {})
    return {
        "api_key": x_api_key,
        "agent_id": identity.get("agent_id"),
        "agent_type": identity.get("agent_type"),
    }


def resolve_identity(
    principal: dict[str, Any],
    request_agent_id: str | None,
    request_agent_type: str | None,
) -> tuple[str, str]:
    """Resolve effective identity and block spoofed request identity."""
    bound_agent_id = principal.get("agent_id")
    bound_agent_type = principal.get("agent_type")

    if bound_agent_id and request_agent_id and request_agent_id != bound_agent_id:
        raise HTTPException(
            status_code=403,
            detail="API key is not permitted to act as requested agent_id",
        )
    if (
        bound_agent_type
        and request_agent_type
        and request_agent_type != bound_agent_type
    ):
        raise HTTPException(
            status_code=403,
            detail="API key is not permitted to act as requested agent_type",
        )

    return (
        bound_agent_id or request_agent_id or "cloud-agent",
        bound_agent_type or request_agent_type or "cloud_agent",
    )


async def authorize_operation(
    agent_id: str,
    agent_type: str,
    operation: str,
    resource: str = "",
    context: dict[str, Any] | None = None,
) -> None:
    """Authorize operation using configured policy engine."""
    from .policy_engine import get_policy_engine

    decision = await get_policy_engine().check_operation(
        agent_id=agent_id,
        agent_type=agent_type,
        operation=operation,
        resource=resource,
        context=context,
    )
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason or "Forbidden")


# =============================================================================
# Application factory
# =============================================================================


def create_coordination_api() -> FastAPI:
    """Create the coordination HTTP API application."""

    app = FastAPI(
        title="Agent Coordination API",
        description="Write operations for multi-agent coordination",
        version="0.2.0",
    )

    # --------------------------------------------------------------------- #
    # FILE LOCKS
    # --------------------------------------------------------------------- #

    @app.post("/locks/acquire")
    async def acquire_lock(
        request: LockAcquireRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Acquire a file lock. Cloud agents call this before modifying files."""
        agent_id, agent_type = resolve_identity(
            principal, request.agent_id, request.agent_type
        )
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="acquire_lock",
            resource=request.file_path,
            context={"ttl_minutes": request.ttl_minutes},
        )

        from .locks import get_lock_service

        result = await get_lock_service().acquire(
            file_path=request.file_path,
            agent_id=agent_id,
            agent_type=agent_type,
            session_id=request.session_id,
            reason=request.reason,
            ttl_minutes=request.ttl_minutes,
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

    @app.post("/locks/release")
    async def release_lock(
        request: LockReleaseRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Release a file lock."""
        agent_id, _agent_type = resolve_identity(
            principal, request.agent_id, None
        )
        await authorize_operation(
            agent_id=agent_id,
            agent_type=_agent_type,
            operation="release_lock",
            resource=request.file_path,
        )

        from .locks import get_lock_service

        result = await get_lock_service().release(
            file_path=request.file_path,
            agent_id=agent_id,
        )
        return {
            "success": result.success,
            "action": result.action,
            "file_path": result.file_path,
            "reason": result.reason,
        }

    @app.get("/locks/status/{file_path:path}")
    async def check_lock_status(file_path: str) -> dict[str, Any]:
        """Check lock status for a file. Read-only, no API key required."""
        from .locks import get_lock_service

        locks = await get_lock_service().check(file_paths=[file_path])
        if not locks:
            return {"locked": False, "file_path": file_path}
        lock = locks[0]
        return {
            "locked": True,
            "file_path": file_path,
            "lock": {
                "locked_by": lock.locked_by,
                "agent_type": lock.agent_type,
                "locked_at": lock.locked_at.isoformat(),
                "expires_at": lock.expires_at.isoformat(),
                "reason": lock.reason,
            },
        }

    # --------------------------------------------------------------------- #
    # MEMORY
    # --------------------------------------------------------------------- #

    @app.post("/memory/store")
    async def store_memory(
        request: MemoryStoreRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Store an episodic memory."""
        agent_id, agent_type = resolve_identity(principal, request.agent_id, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="remember",
            context={"event_type": request.event_type},
        )

        from .memory import get_memory_service

        result = await get_memory_service().remember(
            event_type=request.event_type,
            summary=request.summary,
            details=request.details,
            outcome=request.outcome,
            lessons=request.lessons,
            tags=request.tags,
            agent_id=agent_id,
            session_id=request.session_id,
        )
        return {
            "success": result.success,
            "memory_id": result.memory_id,
            "action": result.action,
        }

    @app.post("/memory/query")
    async def query_memories(
        request: MemoryQueryRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Query relevant memories for a task."""
        agent_id, agent_type = resolve_identity(principal, request.agent_id, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="recall",
            context={"limit": request.limit},
        )

        from .memory import get_memory_service

        result = await get_memory_service().recall(
            tags=request.tags,
            event_type=request.event_type,
            limit=request.limit,
            agent_id=agent_id,
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

    # --------------------------------------------------------------------- #
    # WORK QUEUE
    # --------------------------------------------------------------------- #

    @app.post("/work/claim")
    async def claim_work(
        request: WorkClaimRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Claim a task from the work queue."""
        agent_id, agent_type = resolve_identity(
            principal, request.agent_id, request.agent_type
        )
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="get_work",
            context={"task_types": request.task_types or []},
        )

        from .work_queue import get_work_queue_service

        result = await get_work_queue_service().claim(
            agent_id=agent_id,
            agent_type=agent_type,
            task_types=request.task_types,
        )
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

    @app.post("/work/complete")
    async def complete_work(
        request: WorkCompleteRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Mark a task as completed."""
        from uuid import UUID

        agent_id, agent_type = resolve_identity(principal, request.agent_id, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="complete_work",
            resource=request.task_id,
            context={"success": request.success},
        )

        from .work_queue import get_work_queue_service

        result = await get_work_queue_service().complete(
            task_id=UUID(request.task_id),
            success=request.success,
            result=request.result,
            error_message=request.error_message,
        )
        return {
            "success": result.success,
            "status": result.status,
            "task_id": str(result.task_id) if result.task_id else None,
            "reason": result.reason,
        }

    @app.post("/work/submit")
    async def submit_work(
        request: WorkSubmitRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Submit new work to the queue."""
        from uuid import UUID

        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="submit_work",
            context={"task_type": request.task_type, "priority": request.priority},
        )

        depends_on_uuids = None
        if request.depends_on:
            depends_on_uuids = [UUID(d) for d in request.depends_on]

        from .work_queue import get_work_queue_service

        result = await get_work_queue_service().submit(
            task_type=request.task_type,
            description=request.task_description,
            input_data=request.input_data,
            priority=request.priority,
            depends_on=depends_on_uuids,
        )
        return {
            "success": result.success,
            "task_id": str(result.task_id) if result.task_id else None,
        }

    # --------------------------------------------------------------------- #
    # GUARDRAILS
    # --------------------------------------------------------------------- #

    @app.post("/guardrails/check")
    async def check_guardrails(
        request: GuardrailsCheckRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Check an operation for destructive patterns."""
        from .guardrails import get_guardrails_service

        result = await get_guardrails_service().check_operation(
            operation_text=request.operation_text,
            file_paths=request.file_paths,
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

    # --------------------------------------------------------------------- #
    # PROFILES
    # --------------------------------------------------------------------- #

    @app.get("/profiles/me")
    async def get_my_profile(
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Get the calling agent's profile."""
        agent_id, agent_type = resolve_identity(principal, None, None)

        from .profiles import get_profiles_service

        result = await get_profiles_service().get_profile(
            agent_id=agent_id,
            agent_type=agent_type,
        )
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

    # --------------------------------------------------------------------- #
    # AUDIT
    # --------------------------------------------------------------------- #

    @app.get("/audit")
    async def query_audit(
        agent_id: str | None = None,
        operation: str | None = None,
        limit: int = 20,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Query audit trail entries."""
        from .audit import get_audit_service

        entries = await get_audit_service().query(
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

    # --------------------------------------------------------------------- #
    # HEALTH
    # --------------------------------------------------------------------- #

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok", "version": "0.2.0"}

    return app


# =============================================================================
# MAIN
# =============================================================================


def main() -> None:
    """Entry point for the HTTP API server."""
    import uvicorn

    config = get_config()
    host = config.api.host
    port = config.api.port

    # Allow CLI overrides
    for arg in sys.argv[1:]:
        if arg.startswith("--host="):
            host = arg.split("=", 1)[1]
        elif arg.startswith("--port="):
            port = int(arg.split("=", 1)[1])

    app = create_coordination_api()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
