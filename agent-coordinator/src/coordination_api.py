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
from typing import Any, Literal

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
    agent_requirements: dict[str, Any] | None = None


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
    agent_id: str | None = None
    agent_type: str | None = None
    session_id: str | None = None
    summary: str
    completed_work: list[Any] | None = None
    in_progress: list[Any] | None = None
    decisions: list[Any] | None = None
    next_steps: list[Any] | None = None
    relevant_files: list[Any] | None = None


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
    agent_id: str | None = Field(default=None, max_length=128)
    change_id: str = Field(default="", max_length=128)
    phase: str = Field(default="UNKNOWN", max_length=64)
    message: str = Field(default="", max_length=500)
    needs_human: bool = False
    event_type: str = Field(default="status.phase_transition", max_length=64)
    metadata: dict[str, Any] | None = None
    # wire-autopilot-phase-subagents (D-2, task 3.9): Pydantic ``Literal``
    # enforces enum membership at the API boundary, returning HTTP 422 for
    # out-of-enum values. This complements the SQL CHECK constraint
    # (defense in depth) and the report_status.py client-side validation.
    # Older clients omit this field (no 400 — backward compatible) — the
    # ``| None`` admits both omission and explicit ``null``.
    phase_archetype: Literal[
        "architect",
        "reviewer",
        "implementer",
        "analyst",
        "runner",
    ] | None = Field(default=None)


class ResolveForPhaseRequest(BaseModel):
    """Request body for ``POST /archetypes/resolve_for_phase``.

    Spec: openspec/changes/add-per-phase-archetype-resolution/specs/
          agent-archetypes/spec.md -- Phase Archetype Resolution Endpoint Contract.
    """

    phase: str = Field(max_length=64, description="Non-terminal autopilot phase name.")
    signals: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form signal dict; coordinator filters to keys listed in "
            "phase_mapping[phase].signals."
        ),
    )
    provider: str | None = Field(
        default=None,
        max_length=64,
        description="Optional provider id for provider-specific model resolution.",
    )


class MergeQueueEnqueueRequest(BaseModel):
    feature_id: str
    pr_url: str | None = None


class DiscoveryRegisterRequest(BaseModel):
    agent_id: str | None = None
    agent_type: str | None = None
    session_id: str | None = None
    capabilities: list[str] | None = None
    current_task: str | None = None
    delegated_from: str | None = None
    metadata: dict[str, Any] | None = None


class DiscoveryHeartbeatRequest(BaseModel):
    agent_id: str | None = None
    agent_type: str | None = None
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


class MergeTrainEjectRequest(BaseModel):
    feature_id: str
    reason: str


class MergeTrainReportResultRequest(BaseModel):
    feature_id: str
    passed: bool
    error_message: str | None = None


class AffectedTestsRequest(BaseModel):
    changed_files: list[str]


# ── Kanban-viz request models ──────────────────────────────────────────────

class EventsAuthRequest(BaseModel):
    change_ids: list[str] = Field(min_length=1, description="change-ids to scope the token")
    ttl: int = Field(default=300, ge=1, le=600, description="Token TTL in seconds")


class PatchLabelsRequest(BaseModel):
    add: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)


class KickAgentRequest(BaseModel):
    change_id: str = Field(description="Registry key alongside agent_id")
    skip_agent_id: bool = Field(
        default=False,
        description=(
            "Set true when the registry entry being kicked has no agent_id "
            "(single-agent worktree keyed on change_id alone). When true, "
            "the teardown subprocess omits --agent-id and matches purely on "
            "change_id. Defaults false for backward compatibility with the "
            "parallel-agent kick flow."
        ),
    )


class SavedViewRequest(BaseModel):
    view: dict[str, Any]


class KanbanAuditRequest(BaseModel):
    run_id: str
    event: dict[str, Any]


# =============================================================================
# Auth helpers
# =============================================================================


def _extract_api_key(
    x_api_key: str | None,
    authorization: str | None,
    x_coordinator_api_key: str | None,
) -> str | None:
    """Resolve effective API key by supported header precedence."""
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()
    if x_coordinator_api_key:
        return x_coordinator_api_key.strip() or None
    if x_api_key:
        return x_api_key.strip() or None
    return None


def _principal_for_api_key(resolved_key: str) -> dict[str, Any]:
    """Return the coordinator principal bound to an API key."""
    config = get_config()
    if resolved_key not in config.api.api_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
    identity = config.api.api_key_identities.get(resolved_key, {})
    return {
        "api_key": resolved_key,
        "agent_id": identity.get("agent_id"),
        "agent_type": identity.get("agent_type"),
    }


async def verify_api_key(
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
    x_coordinator_api_key: str | None = Header(None),
) -> dict[str, Any]:
    """Verify the API key for write operations.

    Accepts keys from three headers (precedence order):
      1. ``Authorization: Bearer <key>`` — preferred by the Kanban UI and
         required by the ``POST /events/auth`` JWT-mint flow.
      2. ``X-Coordinator-API-Key`` — secondary alias added for CORS allow-list
         symmetry; avoids reusing the legacy header name.
      3. ``X-API-Key`` — legacy header retained for backward compatibility.

    Existing callers using only ``X-API-Key`` are unaffected.
    """
    resolved_key = _extract_api_key(x_api_key, authorization, x_coordinator_api_key)
    if not resolved_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return _principal_for_api_key(resolved_key)


async def optional_api_key(
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
    x_coordinator_api_key: str | None = Header(None),
) -> dict[str, Any]:
    """Resolve API-key identity when provided; preserve unauthenticated hooks."""
    resolved_key = _extract_api_key(x_api_key, authorization, x_coordinator_api_key)
    if not resolved_key:
        return {"api_key": None, "agent_id": None, "agent_type": None}
    return _principal_for_api_key(resolved_key)


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

    logger = logging.getLogger(__name__)

    from .langfuse_tracing import init_langfuse, shutdown_langfuse
    from .sse_log_redaction import install_token_redaction_filter
    from .telemetry import get_prometheus_app, init_telemetry

    init_telemetry()
    init_langfuse()
    # IMPL_REVIEW R2-id=13 (security, cross-vendor confirmed): mask token=
    # in uvicorn's access log so the SSE auth JWT in the /events/work query
    # string never reaches stdout or downstream log aggregators. Idempotent
    # (the module tracks an installed flag), so calling from both main()
    # and the factory is safe.
    install_token_redaction_filter("uvicorn.access")

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

        # Start merge-train sweeper (R1/R2 — task 5.9). Disable via
        # MERGE_TRAIN_SWEEP_DISABLED=1 for tests or manual operation.
        from .merge_train_service import get_merge_train_sweeper

        sweeper = get_merge_train_sweeper()
        if not os.environ.get("MERGE_TRAIN_SWEEP_DISABLED", "").strip():
            try:
                await sweeper.start()
            except Exception:  # noqa: BLE001
                logging.getLogger(__name__).warning(
                    "MergeTrainSweeper startup failed.", exc_info=True,
                )

        yield

        # Shutdown sweeper, watchdog, notifier, event bus, langfuse
        try:
            await sweeper.stop()
        except Exception:  # noqa: BLE001
            pass
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

    # CORS middleware — design decision D12.
    # Allows http://localhost:5173 (Vite dev) plus additional origins from
    # COORDINATOR_CORS_ALLOWED_ORIGINS CSV.  Credentials=False; the API key
    # travels in headers, not cookies.
    import os as _os

    from fastapi.middleware.cors import CORSMiddleware

    _cors_origins = ["http://localhost:5173"]
    _extra_origins = _os.environ.get("COORDINATOR_CORS_ALLOWED_ORIGINS", "").strip()
    if _extra_origins:
        _cors_origins.extend(o.strip() for o in _extra_origins.split(",") if o.strip())

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "X-Coordinator-API-Key",
            "X-API-Key",
            "Content-Type",
        ],
        allow_credentials=False,
        max_age=600,
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
            agent_requirements=request.agent_requirements,
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
        except Exception as e:  # noqa: BLE001
            logger.exception("create_issue failed")
            return {"success": False, "reason": f"{type(e).__name__}: {e}"}

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
        except Exception as e:  # noqa: BLE001
            logger.exception("update_issue failed")
            return {"success": False, "reason": f"{type(e).__name__}: {e}"}

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
        except Exception as e:  # noqa: BLE001
            logger.exception("close_issue failed")
            return {"success": False, "reason": f"{type(e).__name__}: {e}"}

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
        try:
            comment = await service.comment(UUID(request.issue_id), request.body)
        except Exception as e:  # noqa: BLE001
            logger.exception("comment_issue failed")
            return {"success": False, "reason": f"{type(e).__name__}: {e}"}
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
        since: str | None = None,
        change_id: str | None = None,
        limit: int = 20,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Query audit trail entries.

        IMPL_REVIEW claude_code#9 (high contract_mismatch): extended (was
        previously forked into a parallel ``/audit/v2`` route, contradicting
        design.md §"GET /audit?since=<iso>&change_id=<id>&limit=<n>"). The
        ``since`` and ``change_id`` filters are additive and optional, so
        existing callers (passing only agent_id/operation/limit) are
        unaffected.
        """
        from datetime import datetime

        from .audit import get_audit_service

        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid since format; use ISO-8601",
                )

        entries = await get_audit_service().query(
            agent_id=agent_id,
            operation=operation,
            since=since_dt,
            change_id=change_id,
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
        agent_id, agent_type = resolve_identity(
            principal, request.agent_id, request.agent_type
        )

        from .handoffs import get_handoff_service

        result = await get_handoff_service().write(
            summary=request.summary,
            agent_name=agent_id,
            agent_type=agent_type,
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
    # MERGE TRAIN (speculative-merge-trains, task 5.3)
    # --------------------------------------------------------------------- #

    @app.post("/merge-train/compose")
    async def compose_train_endpoint(
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Compose a new speculative merge train from the current queue.

        Partitions entries by lock-key prefix, creates chained speculative
        refs, and persists status transitions. Probes refresh-architecture
        for graph freshness — stale/unavailable sets ``full_test_suite_required=True``.

        Authorization: trust level >= 3 (D11). Violations return 403.
        """
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="compose_train",
        )
        trust = await resolve_trust_level(agent_id, agent_type)

        from .merge_train import TrainAuthorizationError
        from .merge_train_service import get_merge_train_service

        try:
            composition = await get_merge_train_service().compose_train(
                caller_trust_level=trust
            )
        except TrainAuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

        return {
            "success": True,
            "train_id": composition.train_id,
            "partition_count": len(composition.partitions),
            "cross_partition_count": len(composition.cross_partition_entries),
            "full_test_suite_required": composition.full_test_suite_required,
            "partitions": [
                {
                    "partition_id": p.partition_id,
                    "key_prefixes": sorted(p.key_prefixes),
                    "entries": [
                        {
                            "feature_id": e.feature_id,
                            "train_position": e.train_position,
                            "status": e.status.value,
                            "speculative_ref": e.speculative_ref,
                        }
                        for e in p.entries
                    ],
                }
                for p in composition.partitions
            ],
        }

    @app.post("/merge-train/eject")
    async def eject_from_train_endpoint(
        request: MergeTrainEjectRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Eject a feature from its current merge train.

        Authorization: caller must own the feature OR have trust level >= 3.
        Violations return 403. Unknown feature_id returns ``success: false``
        with reason ``feature_not_in_queue``.
        """
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="eject_from_train",
            resource=request.feature_id,
        )
        trust = await resolve_trust_level(agent_id, agent_type)

        from .merge_train import TrainAuthorizationError
        from .merge_train_service import get_merge_train_service

        try:
            result = await get_merge_train_service().eject_from_train(
                request.feature_id,
                reason=request.reason,
                caller_agent_id=agent_id,
                caller_trust_level=trust,
            )
        except TrainAuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

        if result is None:
            return {
                "success": False,
                "reason": "feature_not_in_queue",
                "feature_id": request.feature_id,
            }
        return {
            "success": True,
            "feature_id": request.feature_id,
            "ejected": result.ejected,
            "abandoned": result.abandoned,
            "priority_after": result.priority_after,
            "independent_successors": result.independent_successors,
            "requeued_successors": result.requeued_successors,
        }

    @app.get("/merge-train/status/{train_id}")
    async def get_train_status_endpoint(
        train_id: str,
        _identity: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Return every entry currently belonging to ``train_id``.

        Empty list for unknown train_ids — treat as "train no longer active"
        (already merged or never composed).
        """
        from .merge_train_service import get_merge_train_service

        entries = await get_merge_train_service().get_train_status(train_id)
        return {
            "train_id": train_id,
            "entries": [
                {
                    "feature_id": e.feature_id,
                    "status": e.status.value,
                    "partition_id": e.partition_id,
                    "train_position": e.train_position,
                    "speculative_ref": e.speculative_ref,
                    "eject_count": e.eject_count,
                    "merge_priority": e.merge_priority,
                    "last_eject_reason": e.last_eject_reason,
                }
                for e in entries
            ],
        }

    @app.post("/merge-train/report-result")
    async def report_spec_result_endpoint(
        request: MergeTrainReportResultRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Record the result of speculative CI verification.

        Transitions: SPECULATING + passed → SPEC_PASSED; SPECULATING + failed
        → BLOCKED (with ``error_message`` persisted to metadata). Any other
        status is a no-op (idempotent).
        """
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="report_spec_result",
            resource=request.feature_id,
        )

        from .merge_train_service import get_merge_train_service

        entry = await get_merge_train_service().report_spec_result(
            request.feature_id,
            passed=request.passed,
            error_message=request.error_message,
        )
        if entry is None:
            return {
                "success": False,
                "reason": "feature_not_in_queue",
                "feature_id": request.feature_id,
            }
        return {
            "success": True,
            "feature_id": request.feature_id,
            "status": entry.status.value,
            "train_id": entry.train_id,
        }

    @app.post("/merge-train/affected-tests")
    async def affected_tests_endpoint(
        request: AffectedTestsRequest,
        _identity: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Compute the test subset for a given set of changed files (R9).

        Shells out to ``skills/refresh-architecture/scripts/affected_tests.py``.
        When the graph is missing/stale/bound-exceeded or any transport error
        occurs, returns ``full_suite_required=True`` with an empty test list
        — callers MUST run the full test suite in that case.
        """
        from .refresh_rpc_client import compute_affected_tests

        result = compute_affected_tests(request.changed_files)
        if result is None:
            return {"full_suite_required": True, "test_files": []}
        return {"full_suite_required": False, "test_files": result}

    # --------------------------------------------------------------------- #
    # ARCHETYPES — per-phase resolution
    # --------------------------------------------------------------------- #

    @app.post("/archetypes/resolve_for_phase")
    async def resolve_archetype_for_phase_endpoint(
        request: ResolveForPhaseRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Resolve archetype + model + system_prompt for an autopilot phase.

        See OpenSpec change `add-per-phase-archetype-resolution`:
        - specs/agent-coordinator/spec.md (Phase Archetype Resolution Endpoint)
        - specs/agent-archetypes/spec.md  (Phase Archetype Resolution Endpoint Contract)
        - contracts/openapi/v1.yaml#/paths/~1archetypes~1resolve_for_phase

        Audit: emits a coordination operation `resolve_archetype_for_phase`
        with phase + resolved {archetype, model} on every successful call.
        """
        from .agents_config import resolve_archetype_for_phase as _resolve
        from .audit import get_audit_service

        try:
            resolved = _resolve(
                request.phase,
                request.signals,
                provider=request.provider,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": str(exc), "phase": request.phase},
            ) from exc
        except RuntimeError as exc:
            # Cache mutation / undefined archetype reference at lookup time.
            raise HTTPException(
                status_code=500,
                detail={"error": str(exc), "phase": request.phase},
            ) from exc

        # Best-effort audit. Failures here MUST NOT block the resolution.
        try:
            await get_audit_service().log_operation(
                agent_id=principal.get("agent_id"),
                agent_type=principal.get("agent_type"),
                operation="resolve_archetype_for_phase",
                parameters={
                    "phase": request.phase,
                    "signals": request.signals,
                    "provider": request.provider,
                },
                result={
                    "archetype": resolved.archetype,
                    "model": resolved.model,
                    "provider": resolved.provider,
                },
                success=True,
            )
        except Exception:  # noqa: BLE001
            import logging as _logging
            _logging.getLogger(__name__).debug(
                "Audit logging failed for resolve_archetype_for_phase",
                exc_info=True,
            )

        return {
            "model": resolved.model,
            "system_prompt": resolved.system_prompt,
            "archetype": resolved.archetype,
            "reasons": list(resolved.reasons),
            "provider": resolved.provider,
        }

    # --------------------------------------------------------------------- #
    # STATUS REPORTING
    # --------------------------------------------------------------------- #

    @app.post("/status/report")
    async def report_status(
        request: StatusReportRequest,
        principal: dict[str, Any] = Depends(optional_api_key),
    ) -> dict[str, Any]:
        """Accept status reports from agent hooks (Stop/SubagentStop).

        API key identity is used when present; unauthenticated status reports
        remain fire-and-forget for hooks without credentials configured.
        """
        import logging as _logging

        from .discovery import get_discovery_service
        from .event_bus import CoordinatorEvent, classify_urgency, get_event_bus

        _log = _logging.getLogger(__name__)
        metadata = request.metadata or {}
        request_agent_type = metadata.get("agent_type")
        if not isinstance(request_agent_type, str):
            request_agent_type = None
        agent_id, agent_type = resolve_identity(
            principal,
            request.agent_id,
            request_agent_type,
        )

        # Update heartbeat for the reporting agent (not the coordinator itself).
        # wire-autopilot-phase-subagents (task 3.8): forward phase_archetype
        # so the value lands in agent_sessions.phase_archetype via the
        # agent_heartbeat RPC (and surfaces in /discovery/agents). The
        # archived per-phase-archetype-resolution change added the field to
        # the request body and the event-bus context, but stopped short of
        # the discovery persistence path — closing that gap inline here.
        try:
            discovery = get_discovery_service()
            await discovery.heartbeat(
                agent_id=agent_id,
                phase_archetype=request.phase_archetype,
            )
        except Exception:  # noqa: BLE001
            _log.debug("Heartbeat update failed for status report", exc_info=True)

        # Determine urgency
        urgency = classify_urgency(request.event_type)
        if request.needs_human and urgency != "high":
            urgency = "high"

        # Emit coordinator_status NOTIFY via event bus.
        # phase_archetype (when present) flows into the event context so
        # downstream observers can correlate phase ↔ archetype without a
        # separate query (per agent-coordinator.3).
        event = CoordinatorEvent(
            event_type=request.event_type,
            channel="coordinator_status",
            entity_id=request.change_id or "unknown",
            agent_id=agent_id,
            urgency=urgency,
            summary=f"[{request.phase}] {request.message}"[:200],
            change_id=request.change_id or None,
            context={
                "phase": request.phase,
                "phase_archetype": request.phase_archetype,
                "needs_human": request.needs_human,
                **metadata,
                "agent_type": agent_type,
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
                    # wire-autopilot-phase-subagents (D-1): surface the resolved
                    # archetype for the agent's current phase. None for legacy
                    # rows that pre-date the migration.
                    "phase_archetype": a.phase_archetype,
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

    # -------------------------------------------------------------------- #
    # KANBAN-VIZ — sync-point status, worktrees, SSE, write/file-write    #
    # -------------------------------------------------------------------- #

    @app.get("/sync-points/status")
    async def get_sync_points_status(
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> list[dict[str, Any]]:
        """Return the blocker state of the three sync-point skills.

        Alphabetical by skill; reuses check_no_active_agents() from
        skills/shared/active_agents.py (design D5).
        """
        from .sync_points import get_sync_points_status as _get

        return _get()

    @app.get("/worktrees/active")
    async def get_active_worktrees(
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> list[dict[str, Any]]:
        """Return active worktree entries from .git-worktrees/.registry.json.

        Omits stale entries (heartbeat > 1h); pinned entries always included.
        """
        from .worktrees_view import get_active_worktrees as _get

        return _get()

    @app.post("/events/auth")
    async def mint_events_token(
        request: EventsAuthRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> Any:
        """Mint a short-lived JWT for the SSE auth handshake.

        Fails closed (503) when COORDINATOR_SSE_SIGNING_KEY is unset.
        """
        from fastapi.responses import JSONResponse

        from .event_stream import _get_signing_key
        from .event_stream import mint_events_token as _mint

        if _get_signing_key() is None:
            return JSONResponse(
                status_code=503,
                content={"error": "SSE signing key not configured (fail-closed)"},
            )

        if not request.change_ids:
            raise HTTPException(status_code=400, detail="change_ids must be non-empty")

        try:
            result = _mint(
                change_ids=request.change_ids,
                key_id=principal.get("agent_id"),
                ttl=request.ttl,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return result

    @app.get("/events/work")
    async def stream_work_events(
        change_ids: str = "",
        token: str = "",
    ) -> Any:
        """SSE stream of work-queue transitions and audit events.

        Auth: JWT in ``?token=<jwt>`` minted by POST /events/auth.
        change_ids: comma-separated list (required; rejected with 400 if empty).
        Fails closed (503) when COORDINATOR_SSE_SIGNING_KEY is unset.
        """
        from fastapi.responses import JSONResponse

        from .event_stream import _get_signing_key, sse_event_generator, validate_events_token

        if _get_signing_key() is None:
            return JSONResponse(
                status_code=503,
                content={"error": "SSE signing key not configured (fail-closed)"},
            )

        if not change_ids.strip():
            return JSONResponse(status_code=400, content={"error": "change_ids required"})

        ids = [c.strip() for c in change_ids.split(",") if c.strip()]
        if not ids:
            return JSONResponse(status_code=400, content={"error": "change_ids required"})

        if not token.strip():
            return JSONResponse(status_code=401, content={"error": "token required"})

        try:
            validate_events_token(token.strip(), ids)
        except Exception as exc:
            logger.info("SSE token validation failed: %s", exc)
            return JSONResponse(status_code=401, content={"error": "invalid token"})

        try:
            from sse_starlette.sse import EventSourceResponse

            from .event_bus import get_event_bus

            event_bus = get_event_bus()
            generator = sse_event_generator(ids, event_bus)
            return EventSourceResponse(generator)
        except Exception as exc:
            logger.error("SSE stream setup failed: %s", exc)
            return JSONResponse(
                status_code=500, content={"error": "stream setup failed"}
            )

    @app.patch("/issues/{issue_id}/labels")
    async def patch_issue_labels(
        issue_id: str,
        request: PatchLabelsRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Add or remove labels on a work_queue row (drag-to-Ready interaction).

        Wraps IssueService.update with a labels-only mutation path.
        Reversibility: reversible-write; audit emitted.
        """
        from uuid import UUID

        from .audit import get_audit_service
        from .issue_service import IssueService

        service = IssueService()
        try:
            issue = await service.show(UUID(issue_id))
        except Exception:
            raise HTTPException(status_code=404, detail=f"Issue {issue_id!r} not found")
        if issue is None:
            raise HTTPException(status_code=404, detail=f"Issue {issue_id!r} not found")

        current_labels = set(issue.labels)
        current_labels.update(request.add)
        current_labels.difference_update(request.remove)

        updated = await service.update(
            issue_id=UUID(issue_id),
            labels=list(current_labels),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Issue {issue_id!r} not found")

        agent_id = principal.get("agent_id") or get_config().agent.agent_id
        try:
            await get_audit_service().log_operation(
                agent_id=agent_id,
                operation="patch_issue_labels",
                parameters={
                    "issue_id": issue_id,
                    "add": request.add,
                    "remove": request.remove,
                },
                success=True,
            )
        except Exception:
            pass

        return updated.to_dict()

    @app.delete("/locks/{file_path:path}")
    async def force_release_lock(
        file_path: str,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Force-release a lock regardless of holder (destructive-write).

        Invokes LockService.force_release (new method, design D9).
        Audit emitted regardless of outcome.
        """
        from .audit import get_audit_service
        from .locks import get_lock_service

        agent_id = principal.get("agent_id") or get_config().agent.agent_id
        result = await get_lock_service().force_release(file_path, agent_id=agent_id)

        try:
            await get_audit_service().log_operation(
                agent_id=agent_id,
                operation="force_release_lock",
                parameters={
                    "file_path": file_path,
                    "prior_holder": result.get("prior_holder"),
                },
                success=result.get("released", False),
            )
        except Exception:
            pass

        prior = result.get("prior_holder") or {}
        return {
            "released": result.get("released", False),
            "prior_holder_agent_id": prior.get("agent_id"),
            "prior_acquired_at": prior.get("locked_at"),
        }

    @app.post("/agents/{agent_id}/kick")
    async def kick_agent(
        agent_id: str,
        request: KickAgentRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Clear a stale agent's worktree-registry entry and mark session disconnected.

        Body must include ``change_id`` (registry is keyed by change_id + agent_id).
        The load-bearing side effect is the registry clear (check_no_active_agents
        reads the registry, NOT agent_sessions).
        Reversibility: destructive-write.
        """
        import subprocess as _sp
        import sys
        from pathlib import Path

        from .audit import get_audit_service

        if not request.change_id:
            raise HTTPException(status_code=422, detail="change_id is required in request body")

        caller_id = principal.get("agent_id") or get_config().agent.agent_id
        registry_cleared = False
        agent_sessions_updated = False
        errors: list[str] = []

        # 1. Clear registry via worktree.py teardown --force
        #
        # IMPL_REVIEW gemini#2 (high architecture): in Docker/cloud
        # environments, skills/worktree/scripts/worktree.py is NOT copied
        # into the deployed image (skills/ is local-only tooling). Worktree
        # registry isolation is also not needed there — each agent runs in
        # its own container, so there's no registry to clear. Detect the
        # script's existence and skip gracefully when absent.
        repo_root = Path(__file__).resolve().parents[2]
        worktree_script = repo_root / "skills" / "worktree" / "scripts" / "worktree.py"
        if not worktree_script.is_file():
            # Docker/cloud path: registry isolation is provided by the
            # container, so registry teardown is vacuously complete.
            logger.debug(
                "kick_agent: worktree.py not present at %s — skipping registry "
                "teardown (cloud/Docker environment provides isolation).",
                worktree_script,
            )
            registry_cleared = True
        else:
            teardown_cmd: list[str] = [
                sys.executable,
                str(worktree_script),
                "teardown",
                request.change_id,
            ]
            if not request.skip_agent_id:
                teardown_cmd.extend(["--agent-id", agent_id])
            teardown_cmd.append("--force")
            try:
                proc = _sp.run(
                    teardown_cmd,
                    cwd=str(repo_root),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if "REMOVED=true" in proc.stdout or "REMOVED=skipped" in proc.stdout:
                    registry_cleared = True
                else:
                    errors.append(f"registry: worktree teardown failed: {proc.stderr.strip()}")
            except Exception as exc:
                errors.append(f"registry: {exc}")

        # 2. Update agent_sessions
        try:
            from .db import get_db
            db = get_db()
            await db.update(
                "agent_sessions",
                match={"agent_id": agent_id},
                data={"status": "disconnected", "last_heartbeat": "1970-01-01T00:00:00+00:00"},
                return_data=False,
            )
            agent_sessions_updated = True
        except Exception as exc:
            errors.append(f"agent_sessions: {exc}")

        # 3. Collect held locks
        held_locks: list[str] = []
        try:
            from .locks import get_lock_service
            locks = await get_lock_service().check(locked_by=agent_id)
            held_locks = [lk.file_path for lk in locks]
        except Exception:
            pass

        # 4. Audit
        try:
            await get_audit_service().log_operation(
                agent_id=caller_id,
                operation="kick_agent",
                parameters={
                    "target_agent_id": agent_id,
                    "change_id": request.change_id,
                    "registry_cleared": registry_cleared,
                    "agent_sessions_updated": agent_sessions_updated,
                    "held_locks": held_locks,
                },
                success=registry_cleared,
            )
        except Exception:
            pass

        kicked = registry_cleared
        return {
            "kicked": kicked,
            "agent_id": agent_id,
            "registry_cleared": registry_cleared,
            "agent_sessions_updated": agent_sessions_updated,
            "held_locks": held_locks,
            **({"errors": errors} if errors else {}),
        }

    @app.put("/kanban-viz/saved-views/{slug}")
    async def put_saved_view(
        slug: str,
        request: SavedViewRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Write a saved-view JSON file (coordinator-owned, design D10).

        Validates slug, resolves path within WORKDIR_ROOT, stamps mandatory
        artifact header, writes atomically.
        Reversibility: reversible-write.
        """
        from .audit import get_audit_service
        from .kanban_viz_files import write_saved_view

        agent_id = principal.get("agent_id") or get_config().agent.agent_id

        try:
            result = write_saved_view(slug=slug, view_payload=request.view)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            logger.error("put_saved_view failed: %s", exc)
            raise HTTPException(status_code=500, detail="write failed")

        try:
            await get_audit_service().log_operation(
                agent_id=agent_id,
                operation="kanban_viz.save_view",
                parameters={"slug": slug, "path": result.get("path")},
                success=result.get("saved", False),
            )
        except Exception:
            pass

        return result

    @app.post("/kanban-viz/audit")
    async def post_kanban_audit(
        request: KanbanAuditRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Append a UI audit event (coordinator-owned, design D10).

        Same path-safety and atomic-write semantics as PUT /kanban-viz/saved-views.
        Date subdirectory derived server-side.
        Reversibility: event-class artifact.
        """
        from .audit import get_audit_service
        from .kanban_viz_files import write_audit_event

        agent_id = principal.get("agent_id") or get_config().agent.agent_id

        try:
            result = write_audit_event(run_id=request.run_id, event_payload=request.event)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            logger.error("post_kanban_audit failed: %s", exc)
            raise HTTPException(status_code=500, detail="write failed")

        try:
            await get_audit_service().log_operation(
                agent_id=agent_id,
                operation="kanban_viz.audit",
                parameters={"run_id": request.run_id, "path": result.get("path")},
                success=result.get("appended", False),
            )
        except Exception:
            pass

        return result

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

    # IMPL_REVIEW R2-id=13 (security): mask token= in uvicorn access log
    # BEFORE uvicorn writes its first line. The filter is idempotent.
    from .sse_log_redaction import install_token_redaction_filter

    install_token_redaction_filter("uvicorn.access")

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
