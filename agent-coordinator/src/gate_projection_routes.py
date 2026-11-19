"""HTTP routes for the project-keyed gate projection (``/gates/*``).

Installed by a function, like ``review_routes``: the auth helpers are passed in
rather than imported, which avoids a circular import with ``coordination_api``,
and the routes are registered on the app itself.

Every route takes the coordinator API key and asks the policy engine before it
touches the service. Pushing, deleting and deciding are checked as
``request_approval`` (a write action), listing as ``check_approval`` (a read
action): the projection is a view over approval-shaped state, so it reuses the
approval operations instead of adding policy vocabulary of its own.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query

from .gate_projection import (
    PROJECT_PATTERN,
    GateDecisionRequest,
    GateNotDecidableError,
    GateNotFoundError,
    GateSnapshotRequest,
    ProjectNotEnrolledError,
    get_gate_projection_service,
)

VerifyKey = Callable[..., Awaitable[dict[str, Any]]]
Authorize = Callable[..., Awaitable[None]]
ResolveIdentity = Callable[[dict[str, Any], str | None, str | None], tuple[str, str]]

NOT_ENROLLED = "Project not enrolled"


def install_gate_projection_routes(
    app: FastAPI,
    verify_api_key: VerifyKey,
    authorize_operation: Authorize,
    resolve_identity: ResolveIdentity,
) -> None:
    """Register the ``/gates/*`` routes on ``app``."""

    async def _authorize(
        principal: dict[str, Any], operation: str, resource: str, action: str
    ) -> str:
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation=operation,
            resource=resource,
            context={"surface": "gate_projection", "action": action},
        )
        return agent_id

    @app.post("/gates/projection")
    async def push_gate_projection(
        request: GateSnapshotRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Replace one project's pending-gate snapshot."""
        await _authorize(principal, "request_approval", request.project, "push")
        try:
            return await get_gate_projection_service().replace_snapshot(request)
        except ProjectNotEnrolledError:
            raise HTTPException(status_code=403, detail=NOT_ENROLLED) from None

    @app.delete("/gates/projection")
    async def delete_gate_projection(
        project: str = Query(pattern=PROJECT_PATTERN, max_length=200),
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Drop one project's snapshot; its next push restores it."""
        await _authorize(principal, "request_approval", project, "delete")
        try:
            return await get_gate_projection_service().delete_snapshot(project)
        except ProjectNotEnrolledError:
            raise HTTPException(status_code=403, detail=NOT_ENROLLED) from None

    @app.get("/gates/pending")
    async def list_pending_gates(
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """List pending gates across every enrolled project."""
        await _authorize(principal, "check_approval", "", "list")
        return await get_gate_projection_service().list_pending()

    @app.post("/gates/decide")
    async def decide_gate(
        request: GateDecisionRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Decide a listed gate through its approval request."""
        agent_id = await _authorize(principal, "request_approval", request.project, "decide")
        try:
            return await get_gate_projection_service().decide(
                request, decided_by=request.decided_by or agent_id
            )
        except ProjectNotEnrolledError:
            raise HTTPException(status_code=403, detail=NOT_ENROLLED) from None
        except GateNotFoundError:
            raise HTTPException(status_code=404, detail="Gate not found") from None
        except GateNotDecidableError as exc:
            raise HTTPException(
                status_code=409,
                detail={"reason": exc.reason, "answer_hint": exc.answer_hint},
            ) from None
