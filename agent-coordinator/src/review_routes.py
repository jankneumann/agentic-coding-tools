"""HTTP routes for the cross-host review queue (``/reviews/*``).

Installed onto the app by a function, like ``install_routing_routes``, so the
auth helpers from ``coordination_api`` can be passed in rather than imported
back (which would be circular). The routes depend on the very same
``verify_api_key`` object, so the OpenAPI drift test still sees the key
requirement in each route's dependency tree. They are registered on the app
itself rather than through ``include_router``: an included router is not a
plain ``APIRoute`` in ``app.routes``, so route-walking checks would skip it.
"""

import hmac
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request

from .config import get_config
from .review_publisher import GitHubReviewPublisher, PublishError
from .review_queue import (
    REPO_PATTERN,
    SHA_PATTERN,
    ReviewJobRequest,
    ReviewResultsRequest,
    get_review_queue_service,
)

logger = logging.getLogger(__name__)

PRODUCER_HEADER = "x-review-producer-token"
PRODUCER_AGENT_ID = "review-producer"

# Reasons record_review_lanes returns that are caller errors, not job state.
_RESULT_ERRORS = {"not_claimant": 403, "task_not_found": 404, "job_not_found": 404}

VerifyKey = Callable[..., Awaitable[dict[str, Any]]]
Authorize = Callable[..., Awaitable[None]]
ResolveIdentity = Callable[[dict[str, Any], str | None, str | None], tuple[str, str]]


def install_review_routes(
    app: FastAPI,
    verify_api_key: VerifyKey,
    authorize_operation: Authorize,
    resolve_identity: ResolveIdentity,
) -> None:
    """Register the ``/reviews`` routes, bound to the API's auth helpers."""

    async def verify_review_submitter(http_request: Request) -> dict[str, Any]:
        """Accept the producer token (CI) or fall through to the API key."""
        presented = http_request.headers.get(PRODUCER_HEADER)
        if presented is not None:
            expected = get_config().review_queue.producer_token
            if not expected or not hmac.compare_digest(presented, expected):
                raise HTTPException(status_code=401, detail="Invalid producer token")
            return {"api_key": None, "agent_id": PRODUCER_AGENT_ID, "producer": True}
        principal = await verify_api_key(
            x_api_key=http_request.headers.get("x-api-key"),
            authorization=http_request.headers.get("authorization"),
            x_coordinator_api_key=http_request.headers.get("x-coordinator-api-key"),
        )
        return {**principal, "producer": False}

    @app.post("/reviews/jobs")
    async def submit_review_job(
        request: ReviewJobRequest,
        principal: dict[str, Any] = Depends(verify_review_submitter),
    ) -> dict[str, Any]:
        """Enqueue a review of one PR head; a new head supersedes older ones."""
        allowed = get_config().review_queue.allowed_repos
        if principal["producer"]:
            # The producer token is a CI secret; it only ever reaches allowlisted repos.
            submitted_by = PRODUCER_AGENT_ID
            if request.repo not in allowed:
                raise HTTPException(status_code=403, detail="Repository not allowed")
        else:
            submitted_by, agent_type = resolve_identity(principal, None, None)
            await authorize_operation(
                agent_id=submitted_by,
                agent_type=agent_type,
                operation="submit_work",
                resource=request.repo,
                context={"task_type": "review", "pr": request.pr},
            )
            if allowed and request.repo not in allowed:
                raise HTTPException(status_code=403, detail="Repository not allowed")

        result = await get_review_queue_service().submit_job(request, submitted_by)
        if not result.get("success"):
            raise HTTPException(status_code=422, detail=result.get("reason", "rejected"))
        return result

    @app.post("/reviews/results")
    async def record_review_results(
        request: ReviewResultsRequest,
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Record a claimed pass's lane results; publish once the job is terminal."""
        agent_id, agent_type = resolve_identity(principal, None, None)
        await authorize_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="complete_work",
            resource=request.task_id,
            context={"task_type": "review"},
        )
        result = await get_review_queue_service().record_lanes(
            request.task_id, agent_id, request.lanes
        )
        reason = result.get("reason")
        if reason in _RESULT_ERRORS:
            raise HTTPException(status_code=_RESULT_ERRORS[reason], detail=reason)
        if result.get("publish_ready"):
            result["publication"] = await _publish(result["job"]["job_id"])
        return result

    @app.get("/reviews/rounds")
    async def get_review_round(
        repo: str = Query(pattern=REPO_PATTERN, max_length=200),
        pr: int = Query(gt=0),
        head_sha: str = Query(pattern=SHA_PATTERN),
        round: int | None = Query(default=None, ge=1),  # noqa: A002 - wire name
        principal: dict[str, Any] = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """The latest (or a given) round for a PR head, with every lane result."""
        return await get_review_queue_service().get_round(repo, pr, head_sha, round)


async def _publish(job_id: str) -> dict[str, Any]:
    """Post a terminal job to GitHub at most once; release the claim on failure."""
    cfg = get_config().review_queue
    if not cfg.publisher_enabled():
        return {"published": False, "reason": "publisher_disabled"}
    service = get_review_queue_service()
    claim = await service.claim_publication(job_id)
    if not claim.get("claimed"):
        return {"published": False, "reason": "already_claimed"}
    try:
        review_id = await GitHubReviewPublisher(cfg).publish(claim["job"])
    except (PublishError, httpx.HTTPError) as exc:
        code = exc.code if isinstance(exc, PublishError) else "github_unreachable"
        logger.warning("review publication failed for job %s: %s", job_id, exc)
        await service.finish_publication(job_id, error=str(exc)[:500])
        return {"published": False, "reason": code}
    await service.finish_publication(job_id, review_id=review_id)
    return {"published": True, "review_id": review_id}
