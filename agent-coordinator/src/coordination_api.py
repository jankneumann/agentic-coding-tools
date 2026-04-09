"""Coordination HTTP API — write endpoints for cloud agents.

Cloud agents can READ directly from Supabase (using anon key).
Cloud agents must WRITE through this API (using API key).

This ensures:
1. Policy enforcement on writes
2. Audit trail of all modifications
3. Race conditions are managed via service-layer abstractions
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .approval import get_approval_service
from .config import get_config
from .port_allocator import get_port_allocator

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


class WorkGetTaskRequest(BaseModel):
    task_id: str


class IssueCreateRequest(BaseModel):
    title: str
    description: str | None = None
    issue_type: str = "task"
    priority: int = 5
    labels: list[str] | None = None
    parent_id: str | None = None
    assignee: str | None = None
    depends_on: list[str] | None = None


class IssueListRequest(BaseModel):
    status: str | None = None
    issue_type: str | None = None
    labels: list[str] | None = None
    parent_id: str | None = None
    assignee: str | None = None
    limit: int = 50


class IssueUpdateRequest(BaseModel):
    issue_id: str
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    labels: list[str] | None = None
    assignee: str | None = None
    issue_type: str | None = None


class IssueCloseRequest(BaseModel):
    issue_id: str | None = None
    issue_ids: list[str] | None = None
    reason: str | None = None


class IssueCommentRequest(BaseModel):
    issue_id: str
    body: str


class GuardrailsCheckRequest(BaseModel):
    operation_text: str
    file_paths: list[str] | None = None


class AuditQueryParams(BaseModel):
    agent_id: str | None = None
    operation: str | None = None
    limit: int = 20


class HandoffWriteRequest(BaseModel):
    agent_id: str
    agent_type: str
    session_id: str | None = None
    summary: str
    completed_work: list[str] | None = None
    in_progress: list[str] | None = None
    decisions: list[str] | None = None
    next_steps: list[str] | None = None
    relevant_files: list[str] | None = None


class HandoffReadRequest(BaseModel):
    agent_name: str | None = None
    limit: int = 1


class PolicyCheckRequest(BaseModel):
    agent_id: str
    agent_type: str
    operation: str
    resource: str = ""
    context: dict[str, Any] | None = None


class PolicyValidateRequest(BaseModel):
    policy_text: str


class PortAllocateRequest(BaseModel):
    session_id: str


class PortReleaseRequest(BaseModel):
    session_id: str


class ApprovalDecisionRequest(BaseModel):
    decision: str  # "approved" or "denied"
    reason: str | None = None
    decided_by: str | None = None


class PolicyRollbackRequest(BaseModel):
    version: int


class FeatureRegisterRequest(BaseModel):
    feature_id: str
    resource_claims: list[str]
    title: str | None = None
    agent_id: str | None = None
    branch_name: str | None = None
    merge_priority: int = 5
    metadata: dict[str, Any] | None = None


class FeatureDeregisterRequest(BaseModel):
    feature_id: str
    status: str = "completed"


class FeatureConflictsRequest(BaseModel):
    candidate_feature_id: str
    candidate_claims: list[str]


class StatusReportRequest(BaseModel):
    agent_id: str = Field(max_length=128)
    change_id: str = Field(default="", max_length=128)
    phase: str = Field(default="UNKNOWN", max_length=64)
    message: str = Field(default="", max_length=500)
    needs_human: bool = False
    event_type: str = Field(default="status.phase_transition", max_length=64)
    metadata: dict[str, Any] | None = None


class MergeQueueEnqueueRequest(BaseModel):
    feature_id: str
    pr_url: str | None = None


class DiscoveryRegisterRequest(BaseModel):
    agent_id: str
    agent_type: str
    session_id: str | None = None
    capabilities: list[str] | None = None
    current_task: str | None = None
    delegated_from: str | None = None
    metadata: dict[str, Any] | None = None


class DiscoveryHeartbeatRequest(BaseModel):
    agent_id: str
    agent_type: str
    session_id: str | None = None


class DiscoveryCleanupRequest(BaseModel):
    stale_threshold_minutes: int = 15
    idle_minutes: int | None = None  # alias accepted; mapped to stale_threshold_minutes
    dry_run: bool = False


class GenEvalValidateRequest(BaseModel):
    yaml_content: str


class GenEvalCreateRequest(BaseModel):
    category: str
    description: str
    interfaces: list[str]
    scenario_type: str = "success"
    priority: int = 2


class GenEvalRunRequest(BaseModel):
    mode: str = "template-only"
    categories: list[str] | None = None
    time_budget_minutes: float = 60.0


class IssueSearchRequest(BaseModel):
    query: str
    status: str | None = None
    labels: list[str] | None = None
    limit: int = 50


class IssueReadyRequest(BaseModel):
    parent_id: str | None = None
    issue_id: str | None = None
    agent_id: str | None = None
    limit: int = 50


class PermissionRequestRequest(BaseModel):
    agent_id: str
    operation: str
    justification: str | None = None
    session_id: str | None = None


class ApprovalSubmitRequest(BaseModel):
    agent_id: str
    operation: str
    agent_type: str | None = None
    resource: str | None = None
    context: dict[str, Any] | None = None
    timeout_seconds: int = 3600


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


async def resolve_trust_level(agent_id: str, agent_type: str) -> int:
    """Resolve effective trust level for guardrail evaluation."""
    from .profiles import get_profiles_service

    try:
        profile_result = await get_profiles_service().get_profile(
            agent_id=agent_id,
            agent_type=agent_type,
        )
        if profile_result.success and profile_result.profile is not None:
            return profile_result.profile.trust_level
    except Exception:
        pass
    return get_config().profiles.default_trust_level


# =============================================================================
# Application factory
# =============================================================================


def create_coordination_api() -> FastAPI:
    """Create the coordination HTTP API application."""
    import logging
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    from .langfuse_tracing import init_langfuse, shutdown_langfuse
    from .telemetry import get_prometheus_app, init_telemetry

    init_telemetry()
    init_langfuse()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Apply pending database migrations on startup
        from .migrations import ensure_schema

        try:
            applied = await ensure_schema()
            if applied:
                logging.getLogger(__name__).info(
                    "Applied %d pending migration(s) at startup.", len(applied)
                )
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "Migration check failed — continuing with existing schema.",
                exc_info=True,
            )

        # Start event bus for status NOTIFY
        from .event_bus import get_event_bus

        event_bus = get_event_bus()
        try:
            await event_bus.start()
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "Event bus startup failed — status NOTIFY disabled.",
                exc_info=True,
            )

        # Start notifier digest loop and watchdog (only when channels configured)
        from .notifications.notifier import get_notifier
        from .watchdog import get_watchdog

        notifier = get_notifier()
        watchdog = get_watchdog()
        notification_channels = os.environ.get("NOTIFICATION_CHANNELS", "")

        if notification_channels.strip():
            try:
                await notifier.start_digest_loop()
            except Exception:  # noqa: BLE001
                logging.getLogger(__name__).warning(
                    "Notifier digest loop startup failed.", exc_info=True,
                )
            try:
                await watchdog.start()
            except Exception:  # noqa: BLE001
                logging.getLogger(__name__).warning(
                    "Watchdog startup failed.", exc_info=True,
                )

        yield

        # Shutdown watchdog, notifier, event bus, langfuse
        try:
            await watchdog.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            await notifier.stop_digest_loop()
        except Exception:  # noqa: BLE001
            pass
        try:
            await event_bus.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            shutdown_langfuse()
        except Exception:  # noqa: BLE001
            pass

    app = FastAPI(
        title="Agent Coordination API",
        description="Write operations for multi-agent coordination",
        version="0.2.0",
        lifespan=lifespan,
    )

    # Mount Prometheus /metrics endpoint if enabled
    prometheus_app = get_prometheus_app()
    if prometheus_app is not None:
        app.mount("/metrics", prometheus_app)

    # Langfuse request tracing middleware (cloud agent observability)
    from .langfuse_tracing import get_langfuse

    if get_langfuse() is not None and get_config().langfuse.trace_api_requests:
        from .langfuse_middleware import LangfuseTracingMiddleware

        app.add_middleware(LangfuseTracingMiddleware)

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

    @app.post("/work/get")
    async def get_task_endpoint(
        request: WorkGetTaskRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Get a specific task by ID."""
        from uuid import UUID

        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="get_work",
            resource=request.task_id,
        )

        from .work_queue import get_work_queue_service

        task = await get_work_queue_service().get_task(UUID(request.task_id))

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

    # --------------------------------------------------------------------- #
    # ISSUE TRACKING
    # --------------------------------------------------------------------- #

    @app.post("/issues/create")
    async def create_issue(
        request: IssueCreateRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Create a new issue."""
        from uuid import UUID

        from .issue_service import get_issue_service

        service = get_issue_service()
        parent_uuid = UUID(request.parent_id) if request.parent_id else None
        depends_uuids = (
            [UUID(d) for d in request.depends_on] if request.depends_on else None
        )

        try:
            issue = await service.create(
                title=request.title,
                description=request.description,
                issue_type=request.issue_type,
                priority=request.priority,
                labels=request.labels,
                parent_id=parent_uuid,
                assignee=request.assignee,
                depends_on=depends_uuids,
            )
            return {"success": True, "issue": issue.to_dict()}
        except ValueError as e:
            return {"success": False, "reason": str(e)}

    @app.post("/issues/list")
    async def list_issues(
        request: IssueListRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """List issues with optional filters."""
        from uuid import UUID

        from .issue_service import get_issue_service

        service = get_issue_service()
        parent_uuid = UUID(request.parent_id) if request.parent_id else None

        issues = await service.list_issues(
            status=request.status,
            issue_type=request.issue_type,
            labels=request.labels,
            parent_id=parent_uuid,
            assignee=request.assignee,
            limit=request.limit,
        )
        return {
            "success": True,
            "issues": [i.to_dict() for i in issues],
            "count": len(issues),
        }

    @app.get("/issues/blocked")
    async def blocked_issues_early(limit: int = 50) -> dict[str, Any]:
        """List issues blocked by unresolved dependencies. Read-only, no auth.

        Registered before ``/issues/{issue_id}`` so FastAPI does not match
        ``blocked`` as an issue_id path parameter.
        """
        from .issue_service import get_issue_service

        service = get_issue_service()
        issues = await service.blocked(limit=limit)
        return {
            "success": True,
            "issues": [i.to_dict() for i in issues],
            "count": len(issues),
        }

    @app.get("/issues/{issue_id}")
    async def show_issue(
        issue_id: str,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Get full issue details."""
        from uuid import UUID

        from .issue_service import get_issue_service

        service = get_issue_service()
        issue = await service.show(UUID(issue_id))

        if issue is None:
            return {"success": False, "reason": "issue_not_found"}
        return {"success": True, "issue": issue.to_dict()}

    @app.post("/issues/update")
    async def update_issue(
        request: IssueUpdateRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Update an issue."""
        from uuid import UUID

        from .issue_service import get_issue_service

        service = get_issue_service()
        try:
            issue = await service.update(
                issue_id=UUID(request.issue_id),
                title=request.title,
                description=request.description,
                status=request.status,
                priority=request.priority,
                labels=request.labels,
                assignee=request.assignee,
                issue_type=request.issue_type,
            )
        except ValueError as e:
            return {"success": False, "reason": str(e)}

        if issue is None:
            return {"success": False, "reason": "issue_not_found"}
        return {"success": True, "issue": issue.to_dict()}

    @app.post("/issues/close")
    async def close_issue(
        request: IssueCloseRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Close one or more issues."""
        from uuid import UUID

        from .issue_service import get_issue_service

        service = get_issue_service()
        id_uuid = UUID(request.issue_id) if request.issue_id else None
        ids_uuids = [UUID(i) for i in request.issue_ids] if request.issue_ids else None

        try:
            results = await service.close(
                issue_id=id_uuid,
                issue_ids=ids_uuids,
                reason=request.reason,
            )
        except ValueError as e:
            return {"success": False, "reason": str(e)}

        return {
            "success": True,
            "closed": [i.to_dict() for i in results],
            "count": len(results),
        }

    @app.post("/issues/comment")
    async def comment_issue(
        request: IssueCommentRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Add a comment to an issue."""
        from uuid import UUID

        from .issue_service import get_issue_service

        service = get_issue_service()
        comment = await service.comment(UUID(request.issue_id), request.body)
        return {"success": True, "comment": comment.to_dict()}

    # --------------------------------------------------------------------- #
    # GUARDRAILS
    # --------------------------------------------------------------------- #

    @app.post("/guardrails/check")
    async def check_guardrails(
        request: GuardrailsCheckRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Check an operation for destructive patterns."""
        agent_id, agent_type = resolve_identity(principal, None, None)
        trust_level = await resolve_trust_level(agent_id, agent_type)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="check_guardrails",
            context={
                "trust_level": trust_level,
                "operation_text_length": len(request.operation_text),
                "file_count": len(request.file_paths or []),
            },
        )

        from .guardrails import get_guardrails_service

        result = await get_guardrails_service().check_operation(
            operation_text=request.operation_text,
            file_paths=request.file_paths,
            agent_id=agent_id,
            agent_type=agent_type,
            trust_level=trust_level,
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

    @app.get("/agents/dispatch-configs")
    async def get_agent_dispatch_configs() -> dict[str, Any]:
        """Get CLI dispatch configs for agents with cli sections.

        No auth required — dispatch configs are not sensitive.
        """
        from .agents_config import get_dispatch_configs

        return get_dispatch_configs()

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
    # HANDOFFS
    # --------------------------------------------------------------------- #

    @app.post("/handoffs/write")
    async def write_handoff(
        request: HandoffWriteRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Write a handoff document for session continuity."""
        agent_id, _agent_type = resolve_identity(
            principal, request.agent_id, request.agent_type
        )

        from .handoffs import get_handoff_service

        result = await get_handoff_service().write(
            summary=request.summary,
            agent_name=agent_id,
            session_id=request.session_id,
            completed_work=request.completed_work,
            in_progress=request.in_progress,
            decisions=request.decisions,
            next_steps=request.next_steps,
            relevant_files=request.relevant_files,
        )
        return {
            "success": result.success,
            "handoff_id": str(result.handoff_id) if result.handoff_id else None,
            "error": result.error,
        }

    @app.post("/handoffs/read")
    async def read_handoff(
        request: HandoffReadRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Read previous handoff documents for session continuity."""
        from .handoffs import get_handoff_service

        result = await get_handoff_service().read(
            agent_name=request.agent_name,
            limit=request.limit,
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

    # --------------------------------------------------------------------- #
    # POLICY
    # --------------------------------------------------------------------- #

    @app.post("/policy/check")
    async def check_policy(
        request: PolicyCheckRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Check if an operation is authorized by the policy engine."""
        agent_id, agent_type = resolve_identity(
            principal, request.agent_id, request.agent_type
        )

        from .policy_engine import get_policy_engine

        engine = get_policy_engine()
        result = await engine.check_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation=request.operation,
            resource=request.resource,
            context=request.context,
        )
        return {
            "allowed": result.allowed,
            "reason": result.reason,
            "engine": type(engine).__name__,
            "diagnostics": result.diagnostics,
        }

    @app.post("/policy/validate")
    async def validate_cedar_policy(
        request: PolicyValidateRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Validate Cedar policy text against the schema."""
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
        result = engine.validate_policy(request.policy_text)
        return {
            "valid": result.valid,
            "errors": result.errors,
        }

    # --------------------------------------------------------------------- #
    # PORT ALLOCATION
    # --------------------------------------------------------------------- #

    @app.post("/ports/allocate")
    async def allocate_ports(
        request: PortAllocateRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Allocate a block of ports for a session."""
        allocation = get_port_allocator().allocate(request.session_id)
        if allocation is None:
            return {"success": False, "error": "no_ports_available"}
        return {
            "success": True,
            "allocation": {
                "session_id": allocation.session_id,
                "db_port": allocation.db_port,
                "rest_port": allocation.rest_port,
                "realtime_port": allocation.realtime_port,
                "api_port": allocation.api_port,
                "compose_project_name": allocation.compose_project_name,
            },
            "env_snippet": allocation.env_snippet,
        }

    @app.post("/ports/release")
    async def release_ports(
        request: PortReleaseRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Release a port allocation for a session."""
        get_port_allocator().release(request.session_id)
        return {"success": True}

    @app.get("/ports/status")
    async def port_status() -> list[dict[str, Any]]:
        """List all active port allocations. Read-only, no API key required."""
        allocations = get_port_allocator().status()
        return [
            {
                "session_id": alloc.session_id,
                "db_port": alloc.db_port,
                "rest_port": alloc.rest_port,
                "realtime_port": alloc.realtime_port,
                "api_port": alloc.api_port,
                "compose_project_name": alloc.compose_project_name,
                "remaining_ttl_minutes": max(
                    0, (alloc.expires_at - time.time()) / 60
                ),
            }
            for alloc in allocations
        ]

    # --------------------------------------------------------------------- #
    # APPROVALS
    # --------------------------------------------------------------------- #

    def _approval_to_dict(r: object) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": r.id,  # type: ignore[attr-defined]
            "agent_id": r.agent_id,  # type: ignore[attr-defined]
            "operation": r.operation,  # type: ignore[attr-defined]
            "status": r.status,  # type: ignore[attr-defined]
            "created_at": r.created_at.isoformat(),  # type: ignore[attr-defined]
            "expires_at": r.expires_at.isoformat(),  # type: ignore[attr-defined]
        }
        if r.resource:  # type: ignore[attr-defined]
            d["resource"] = r.resource  # type: ignore[attr-defined]
        if r.decided_by:  # type: ignore[attr-defined]
            d["decided_by"] = r.decided_by  # type: ignore[attr-defined]
        if r.reason:  # type: ignore[attr-defined]
            d["reason"] = r.reason  # type: ignore[attr-defined]
        return d

    @app.get("/approvals/pending")
    async def list_pending_approvals(
        agent_id: str | None = None,
        limit: int = 50,
        _identity: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """List pending approval requests."""
        service = get_approval_service()
        requests = await service.list_pending(agent_id=agent_id, limit=limit)
        return {"approvals": [_approval_to_dict(r) for r in requests]}

    @app.post("/approvals/{request_id}/decide")
    async def decide_approval(
        request_id: str,
        body: ApprovalDecisionRequest,
        identity: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Approve or deny an approval request."""
        service = get_approval_service()
        decided_by = body.decided_by or identity.get("agent_id", "unknown")
        result = await service.decide_request(
            request_id,
            body.decision,
            decided_by=decided_by,
            reason=body.reason,
        )
        if not result:
            raise HTTPException(404, detail="Request not found or already decided")
        return {
            "success": True,
            "request_id": result.id,
            "status": result.status,
        }

    # --------------------------------------------------------------------- #
    # POLICY VERSIONING
    # --------------------------------------------------------------------- #

    @app.get("/policies/{policy_name}/versions")
    async def list_policy_versions_endpoint(
        policy_name: str,
        limit: int = 20,
        _identity: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """List version history for a Cedar policy."""
        from .policy_engine import get_policy_engine

        engine = get_policy_engine()
        versions = await engine.list_policy_versions(policy_name, limit)
        return {"versions": versions}

    @app.post("/policies/{policy_name}/rollback")
    async def rollback_policy_endpoint(
        policy_name: str,
        body: PolicyRollbackRequest,
        _identity: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Rollback a Cedar policy to a previous version."""
        from .policy_engine import get_policy_engine

        engine = get_policy_engine()
        result = await engine.rollback_policy(policy_name, body.version)
        if not result.get("success"):
            raise HTTPException(404, detail=result.get("error", "Rollback failed"))
        return result

    # --------------------------------------------------------------------- #
    # FEATURE REGISTRY
    # --------------------------------------------------------------------- #

    @app.post("/features/register")
    async def register_feature_endpoint(
        request: FeatureRegisterRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Register a feature with resource claims."""
        agent_id, agent_type = resolve_identity(
            principal, request.agent_id, None
        )
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="register_feature",
            resource=request.feature_id,
        )

        from .feature_registry import get_feature_registry_service

        result = await get_feature_registry_service().register(
            feature_id=request.feature_id,
            resource_claims=request.resource_claims,
            title=request.title,
            agent_id=agent_id,
            branch_name=request.branch_name,
            merge_priority=request.merge_priority,
            metadata=request.metadata,
        )
        return {
            "success": result.success,
            "feature_id": result.feature_id,
            "action": result.action,
            "reason": result.reason,
        }

    @app.post("/features/deregister")
    async def deregister_feature_endpoint(
        request: FeatureDeregisterRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Deregister a feature (mark completed/cancelled)."""
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="deregister_feature",
            resource=request.feature_id,
        )

        from .feature_registry import get_feature_registry_service

        result = await get_feature_registry_service().deregister(
            feature_id=request.feature_id,
            status=request.status,
        )
        return {
            "success": result.success,
            "feature_id": result.feature_id,
            "status": result.status,
            "reason": result.reason,
        }

    @app.get("/features/{feature_id}")
    async def get_feature_endpoint(
        feature_id: str,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Get details of a specific feature."""
        from .feature_registry import get_feature_registry_service

        feature = await get_feature_registry_service().get_feature(feature_id)
        if feature is None:
            raise HTTPException(404, detail="Feature not found")
        return {
            "feature_id": feature.feature_id,
            "title": feature.title,
            "status": feature.status,
            "registered_by": feature.registered_by,
            "resource_claims": feature.resource_claims,
            "branch_name": feature.branch_name,
            "merge_priority": feature.merge_priority,
            "metadata": feature.metadata,
            "registered_at": feature.registered_at.isoformat() if feature.registered_at else None,
            "updated_at": feature.updated_at.isoformat() if feature.updated_at else None,
        }

    @app.get("/features/active")
    async def list_active_features_endpoint(
        _identity: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """List all active features ordered by merge priority."""
        from .feature_registry import get_feature_registry_service

        features = await get_feature_registry_service().get_active_features()
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

    @app.post("/features/conflicts")
    async def analyze_feature_conflicts_endpoint(
        request: FeatureConflictsRequest,
        _identity: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Analyze resource conflicts between a candidate and active features."""
        from .feature_registry import get_feature_registry_service

        report = await get_feature_registry_service().analyze_conflicts(
            request.candidate_feature_id,
            request.candidate_claims,
        )
        return {
            "candidate_feature_id": report.candidate_feature_id,
            "feasibility": report.feasibility.value,
            "total_candidate_claims": report.total_candidate_claims,
            "total_conflicting_claims": report.total_conflicting_claims,
            "conflicts": report.conflicts,
        }

    # --------------------------------------------------------------------- #
    # MERGE QUEUE
    # --------------------------------------------------------------------- #

    @app.post("/merge-queue/enqueue")
    async def enqueue_merge_endpoint(
        request: MergeQueueEnqueueRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Add a feature to the merge queue."""
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="enqueue_merge",
            resource=request.feature_id,
        )

        from .merge_queue import get_merge_queue_service

        entry = await get_merge_queue_service().enqueue(
            feature_id=request.feature_id,
            pr_url=request.pr_url,
        )
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

    @app.get("/merge-queue")
    async def get_merge_queue_endpoint(
        _identity: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Get all features in the merge queue."""
        from .merge_queue import get_merge_queue_service

        entries = await get_merge_queue_service().get_queue()
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

    @app.get("/merge-queue/next")
    async def get_next_merge_endpoint(
        _identity: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Get the highest-priority feature ready to merge."""
        from .merge_queue import get_merge_queue_service

        entry = await get_merge_queue_service().get_next_to_merge()
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

    @app.post("/merge-queue/check/{feature_id}")
    async def run_pre_merge_checks_endpoint(
        feature_id: str,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Run pre-merge validation checks on a feature."""
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="run_pre_merge_checks",
            resource=feature_id,
        )

        from .merge_queue import get_merge_queue_service

        result = await get_merge_queue_service().run_pre_merge_checks(feature_id)
        return {
            "feature_id": result.feature_id,
            "passed": result.passed,
            "checks": result.checks,
            "issues": result.issues,
            "conflicts": result.conflicts,
        }

    @app.post("/merge-queue/merged/{feature_id}")
    async def mark_merged_endpoint(
        feature_id: str,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Mark a feature as merged and deregister it."""
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="mark_merged",
            resource=feature_id,
        )

        from .merge_queue import get_merge_queue_service

        success = await get_merge_queue_service().mark_merged(feature_id)
        return {"success": success, "feature_id": feature_id}

    @app.delete("/merge-queue/{feature_id}")
    async def remove_from_merge_queue_endpoint(
        feature_id: str,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Remove a feature from the merge queue without merging."""
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="remove_from_merge_queue",
            resource=feature_id,
        )

        from .merge_queue import get_merge_queue_service

        success = await get_merge_queue_service().remove_from_queue(feature_id)
        return {"success": success, "feature_id": feature_id}

    # --------------------------------------------------------------------- #
    # STATUS REPORTING
    # --------------------------------------------------------------------- #

    @app.post("/status/report")
    async def report_status(
        request: StatusReportRequest,
    ) -> dict[str, Any]:
        """Accept status reports from agent hooks (Stop/SubagentStop).

        No API key required — status reports are fire-and-forget from hooks
        that may not have credentials configured.
        """
        import logging as _logging

        from .discovery import get_discovery_service
        from .event_bus import CoordinatorEvent, classify_urgency, get_event_bus

        _log = _logging.getLogger(__name__)

        # Update heartbeat for the reporting agent (not the coordinator itself)
        try:
            discovery = get_discovery_service()
            await discovery.heartbeat(agent_id=request.agent_id)
        except Exception:  # noqa: BLE001
            _log.debug("Heartbeat update failed for status report", exc_info=True)

        # Determine urgency
        urgency = classify_urgency(request.event_type)
        if request.needs_human and urgency != "high":
            urgency = "high"

        # Emit coordinator_status NOTIFY via event bus
        event = CoordinatorEvent(
            event_type=request.event_type,
            channel="coordinator_status",
            entity_id=request.change_id or "unknown",
            agent_id=request.agent_id,
            urgency=urgency,
            summary=f"[{request.phase}] {request.message}"[:200],
            change_id=request.change_id or None,
            context={
                "phase": request.phase,
                "needs_human": request.needs_human,
                **(request.metadata or {}),
            },
        )

        bus = get_event_bus()
        if bus.running and not bus.failed:
            try:
                import asyncpg

                conn = await asyncpg.connect(
                    dsn=bus._dsn,  # noqa: SLF001
                )
                try:
                    await conn.execute(
                        "SELECT pg_notify($1, $2)",
                        "coordinator_status",
                        event.to_json(),
                    )
                finally:
                    await conn.close()
            except Exception:  # noqa: BLE001
                _log.debug("pg_notify failed for status report", exc_info=True)

        return {"success": True, "urgency": urgency}

    # --------------------------------------------------------------------- #
    # NOTIFICATIONS (status/diagnostics)
    # --------------------------------------------------------------------- #

    @app.post("/notifications/test")
    async def test_notification(
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Send a test notification through the event bus."""
        from .event_bus import CoordinatorEvent, get_event_bus

        event = CoordinatorEvent(
            event_type="notification.test",
            channel="coordinator_status",
            entity_id="test",
            agent_id=principal.get("agent_id", "api"),
            urgency="low",
            summary="Test notification from API",
        )

        bus = get_event_bus()
        sent = False
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
                    sent = True
                finally:
                    await conn.close()
            except Exception:  # noqa: BLE001
                pass

        return {"success": True, "sent": sent}

    @app.get("/notifications/status")
    async def notifications_status() -> dict[str, Any]:
        """Get event bus and notification system status."""
        from .event_bus import get_event_bus

        bus = get_event_bus()
        return {
            "event_bus": {
                "running": bus.running,
                "failed": bus.failed,
            },
        }

    # --------------------------------------------------------------------- #
    # DISCOVERY
    # --------------------------------------------------------------------- #

    @app.post("/discovery/register")
    async def discovery_register(
        request: DiscoveryRegisterRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Register an agent session for discovery."""
        agent_id, agent_type = resolve_identity(
            principal, request.agent_id, request.agent_type
        )
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="register_session",
            context={"capabilities": request.capabilities or []},
        )

        from .discovery import get_discovery_service

        result = await get_discovery_service().register(
            agent_id=agent_id,
            agent_type=agent_type,
            session_id=request.session_id,
            capabilities=request.capabilities,
            current_task=request.current_task,
            delegated_from=request.delegated_from,
        )
        return {
            "success": result.success,
            "session_id": result.session_id,
        }

    @app.get("/discovery/agents")
    async def discovery_agents(
        capability: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Discover agents with optional capability/status filters."""
        from .discovery import get_discovery_service

        result = await get_discovery_service().discover(
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
                    "last_heartbeat": a.last_heartbeat.isoformat()
                    if a.last_heartbeat
                    else None,
                    "started_at": a.started_at.isoformat() if a.started_at else None,
                }
                for a in result.agents
            ],
        }

    @app.post("/discovery/heartbeat")
    async def discovery_heartbeat(
        request: DiscoveryHeartbeatRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Send a heartbeat for an agent session."""
        agent_id, agent_type = resolve_identity(
            principal, request.agent_id, request.agent_type
        )
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="heartbeat",
        )

        from .discovery import get_discovery_service

        result = await get_discovery_service().heartbeat(
            session_id=request.session_id,
            agent_id=agent_id,
        )
        return {
            "success": result.success,
            "session_id": result.session_id,
            "error": result.error,
        }

    @app.post("/discovery/cleanup")
    async def discovery_cleanup(
        request: DiscoveryCleanupRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Clean up stale agent sessions and release their locks."""
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="cleanup_dead_agents",
            context={
                "stale_threshold_minutes": request.stale_threshold_minutes,
                "dry_run": request.dry_run,
            },
        )

        from .discovery import get_discovery_service

        threshold = (
            request.idle_minutes
            if request.idle_minutes is not None
            else request.stale_threshold_minutes
        )
        result = await get_discovery_service().cleanup_dead_agents(
            stale_threshold_minutes=threshold,
        )
        return {
            "success": result.success,
            "agents_cleaned": result.agents_cleaned,
            "locks_released": result.locks_released,
        }

    # --------------------------------------------------------------------- #
    # GEN-EVAL
    # --------------------------------------------------------------------- #

    @app.get("/gen-eval/scenarios")
    async def gen_eval_list_scenarios(
        category: str | None = None,
        interface: str | None = None,
    ) -> dict[str, Any]:
        """List gen-eval scenarios, optionally filtered by category or interface."""
        from evaluation.gen_eval.mcp_service import get_gen_eval_service

        scenarios = await get_gen_eval_service().list_scenarios(
            category=category, interface=interface
        )
        return {
            "scenarios": [
                {
                    "id": s.id,
                    "name": s.name,
                    "category": s.category,
                    "priority": s.priority,
                    "interfaces": s.interfaces,
                    "step_count": s.step_count,
                    "tags": s.tags,
                    "has_cleanup": s.has_cleanup,
                    "file_path": s.file_path,
                }
                for s in scenarios
            ],
        }

    @app.post("/gen-eval/validate")
    async def gen_eval_validate(
        request: GenEvalValidateRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Validate a gen-eval scenario YAML document."""
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="validate_scenario",
        )

        from evaluation.gen_eval.mcp_service import get_gen_eval_service

        result = await get_gen_eval_service().validate_scenario(request.yaml_content)
        return {
            "valid": result.valid,
            "scenario_id": result.scenario_id,
            "step_count": result.step_count,
            "interfaces": result.interfaces,
            "errors": result.errors,
        }

    @app.post("/gen-eval/create")
    async def gen_eval_create(
        request: GenEvalCreateRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Generate a scaffold scenario YAML from a description."""
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="create_scenario",
            context={"category": request.category, "priority": request.priority},
        )

        from evaluation.gen_eval.mcp_service import get_gen_eval_service

        result = await get_gen_eval_service().create_scenario(
            category=request.category,
            description=request.description,
            interfaces=request.interfaces,
            scenario_type=request.scenario_type,
            priority=request.priority,
        )
        return result if isinstance(result, dict) else {"result": result}

    @app.post("/gen-eval/run")
    async def gen_eval_run(
        request: GenEvalRunRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Run gen-eval testing against the coordinator's interfaces."""
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="run_gen_eval",
            context={
                "mode": request.mode,
                "time_budget_minutes": request.time_budget_minutes,
            },
        )

        from evaluation.gen_eval.mcp_service import get_gen_eval_service

        result = await get_gen_eval_service().run_evaluation(
            mode=request.mode,
            categories=request.categories,
            time_budget_minutes=request.time_budget_minutes,
        )
        return result if isinstance(result, dict) else {"result": result}

    # --------------------------------------------------------------------- #
    # ISSUE SEARCH / READY / BLOCKED
    # --------------------------------------------------------------------- #

    @app.post("/issues/search")
    async def search_issues(
        request: IssueSearchRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Search issues by text matching in title and description."""
        from .issue_service import get_issue_service

        service = get_issue_service()
        issues = await service.search(query=request.query, limit=request.limit)
        return {
            "success": True,
            "issues": [i.to_dict() for i in issues],
            "count": len(issues),
        }

    @app.post("/issues/ready")
    async def ready_issues(
        request: IssueReadyRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """List issues with no unresolved dependencies (ready to work on)."""
        from uuid import UUID

        from .issue_service import get_issue_service

        service = get_issue_service()
        parent_uuid = UUID(request.parent_id) if request.parent_id else None
        issues = await service.ready(parent_id=parent_uuid, limit=request.limit)
        return {
            "success": True,
            "issues": [i.to_dict() for i in issues],
            "count": len(issues),
        }

    # NOTE: GET /issues/blocked is registered earlier (before /issues/{issue_id})
    # to prevent FastAPI from matching "blocked" as an issue_id parameter.

    # --------------------------------------------------------------------- #
    # SESSION GRANTS
    # --------------------------------------------------------------------- #

    @app.post("/permissions/request")
    async def request_permission_endpoint(
        request: PermissionRequestRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Request a session-scoped permission grant."""
        agent_id, agent_type = resolve_identity(principal, request.agent_id, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="request_permission",
            context={"requested_operation": request.operation},
        )

        config = get_config()
        if not config.session_grants.enabled:
            raise HTTPException(
                status_code=400, detail="Session grants are not enabled"
            )

        from .session_grants import get_session_grant_service

        grant = await get_session_grant_service().request_grant(
            session_id=request.session_id or agent_id,
            agent_id=agent_id,
            operation=request.operation,
            justification=request.justification,
        )
        return {
            "success": True,
            "granted": True,
            "grant_id": grant.id,
            "operation": grant.operation,
        }

    # --------------------------------------------------------------------- #
    # APPROVALS (request + check)
    # --------------------------------------------------------------------- #

    @app.post("/approvals/request")
    async def request_approval_endpoint(
        request: ApprovalSubmitRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Submit a human-in-the-loop approval request."""
        agent_id, agent_type = resolve_identity(
            principal, request.agent_id, request.agent_type
        )
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="request_approval",
            resource=request.resource or "",
            context={"requested_operation": request.operation},
        )

        config = get_config()
        if not config.approval.enabled:
            raise HTTPException(
                status_code=400, detail="Approval gates are not enabled"
            )

        service = get_approval_service()
        approval_request = await service.submit_request(
            agent_id=agent_id,
            agent_type=agent_type,
            operation=request.operation,
            resource=request.resource,
            context=request.context,
            timeout_seconds=request.timeout_seconds,
        )
        return {
            "success": True,
            "request_id": approval_request.id,
            "status": approval_request.status,
            "expires_at": approval_request.expires_at.isoformat(),
        }

    @app.get("/approvals/{request_id}")
    async def check_approval_endpoint(
        request_id: str,
        _identity: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Check the status of an approval request."""
        service = get_approval_service()
        approval_request = await service.check_request(request_id)
        if approval_request is None:
            raise HTTPException(status_code=404, detail="Approval request not found")

        result: dict[str, Any] = {
            "success": True,
            "request_id": approval_request.id,
            "status": approval_request.status,
            "agent_id": approval_request.agent_id,
            "operation": approval_request.operation,
            "created_at": approval_request.created_at.isoformat(),
            "expires_at": approval_request.expires_at.isoformat(),
        }
        if approval_request.resource:
            result["resource"] = approval_request.resource
        if approval_request.decided_by:
            result["decided_by"] = approval_request.decided_by
        if approval_request.reason:
            result["reason"] = approval_request.reason
        return result

    # --------------------------------------------------------------------- #
    # HEALTH
    # --------------------------------------------------------------------- #

    async def _database_health() -> str:
        """Return database connectivity status for readiness/observability."""
        import asyncio

        db_status = "connected"
        cfg = get_config()
        if cfg.database.backend == "postgres" and cfg.database.postgres.dsn:
            try:
                import asyncpg

                conn = await asyncio.wait_for(
                    asyncpg.connect(dsn=cfg.database.postgres.dsn),
                    timeout=2.0,
                )
                try:
                    await conn.fetchval("SELECT 1")
                finally:
                    await conn.close()
            except Exception:
                db_status = "unreachable"

        return db_status

    # --------------------------------------------------------------------- #
    # HELP — Progressive Discovery
    # --------------------------------------------------------------------- #

    @app.get("/help")
    async def help_overview() -> dict[str, Any]:
        """Compact overview of all coordinator capabilities.

        No auth required — this is a discovery endpoint for agents.
        """
        from .help_service import get_help_overview

        return get_help_overview()

    @app.get("/help/{topic}")
    async def help_topic(topic: str) -> Any:
        """Detailed help for a specific capability group.

        No auth required — this is a discovery endpoint for agents.
        """
        from fastapi.responses import JSONResponse

        from .help_service import get_help_topic, list_topic_names

        detail = get_help_topic(topic)
        if detail is not None:
            return detail

        return JSONResponse(
            status_code=404,
            content={
                "error": f"Unknown topic: {topic}",
                "available_topics": list_topic_names(),
                "hint": "GET /help for an overview of all topics",
            },
        )

    @app.get("/live")
    async def live() -> dict[str, str]:
        """Cheap liveness probe for container platforms."""
        return {"status": "ok", "version": "0.2.0"}

    @app.get("/ready")
    async def ready() -> Any:
        """Readiness probe that verifies required dependencies."""
        from fastapi.responses import JSONResponse

        db_status = await _database_health()
        status = "ok" if db_status == "connected" else "degraded"
        payload = {"status": status, "db": db_status, "version": "0.2.0"}
        if db_status != "connected":
            return JSONResponse(status_code=503, content=payload)
        return payload

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Human-facing health summary without affecting platform liveness."""
        db_status = await _database_health()
        status = "ok" if db_status == "connected" else "degraded"
        return {"status": status, "db": db_status, "version": "0.2.0"}

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

    uvicorn.run(
        "src.coordination_api:create_coordination_api",
        factory=True,
        host=host,
        port=port,
        workers=config.api.workers,
        timeout_keep_alive=config.api.timeout_keep_alive,
        access_log=config.api.access_log,
    )


if __name__ == "__main__":
    main()
