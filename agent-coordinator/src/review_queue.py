"""Cross-host pull-request review queue.

A review job is one ``work_queue`` row (``task_type='review'``) indexed by
``(repo, pr, head_sha, round)`` in ``review_jobs``. Any host with vendor CLIs
claims it through the ordinary claim path, runs the lanes it can, and records
per-vendor results here. Quorum is distinct vendors with a verified result,
counted across hosts; a pass that falls short re-enqueues a residual pass that
excludes the vendors already verified. See migration 046 for the state
machine — every write here is a single RPC so the transitions stay atomic.
"""

import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .audit import get_audit_service
from .config import get_config
from .db import DatabaseClient, get_db

logger = logging.getLogger(__name__)

REPO_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
SHA_PATTERN = r"^[0-9a-f]{40}$"
VENDOR_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"
MAX_FINDINGS_PER_LANE = 200

Risk = Literal["low", "medium", "high", "critical"]


class ReviewJobRequest(BaseModel):
    """A producer's request to review one PR head."""

    repo: str = Field(pattern=REPO_PATTERN, max_length=200)
    pr: int = Field(gt=0)
    head_sha: str = Field(pattern=SHA_PATTERN)
    base_sha: str = Field(pattern=SHA_PATTERN)
    round: int | None = Field(default=None, ge=1)
    lanes_required: int = Field(default=2, ge=1, le=8)
    risk: Risk = "medium"
    deadline: datetime | None = None


class LaneResultIn(BaseModel):
    """One vendor lane's outcome for a claimed review pass."""

    vendor: str = Field(pattern=VENDOR_PATTERN)
    verified: bool
    verdict: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    findings: list[dict[str, Any]] = Field(
        default_factory=list, max_length=MAX_FINDINGS_PER_LANE
    )
    error: str | None = Field(default=None, max_length=2000)


class ReviewResultsRequest(BaseModel):
    """A worker reporting the lanes it ran for a claimed review task."""

    task_id: str = Field(min_length=1, max_length=64)
    lanes: list[LaneResultIn] = Field(min_length=1, max_length=16)


class ReviewQueueService:
    """Thin RPC wrapper over the review-queue functions in migration 046."""

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def _call(self, fn: str, params: dict[str, Any]) -> dict[str, Any]:
        result = await self.db.rpc(fn, params)
        if not isinstance(result, dict):
            raise RuntimeError(f"{fn} returned {type(result).__name__}, expected object")
        return result

    async def submit_job(self, req: ReviewJobRequest, submitted_by: str) -> dict[str, Any]:
        """Create (or dedup onto) the job for a PR head; supersede older heads."""
        result = await self._call(
            "submit_review_job",
            {
                "p_repo": req.repo,
                "p_pr": req.pr,
                "p_head_sha": req.head_sha,
                "p_base_sha": req.base_sha,
                "p_submitted_by": submitted_by,
                "p_round": req.round,
                "p_lanes_required": req.lanes_required,
                "p_risk": req.risk,
                "p_deadline": req.deadline.isoformat() if req.deadline else None,
            },
        )
        await get_audit_service().log_operation(
            agent_id=submitted_by,
            operation="review_submit",
            parameters={"repo": req.repo, "pr": req.pr, "head_sha": req.head_sha},
            result={
                "created": result.get("created"),
                "superseded_task_ids": result.get("superseded_task_ids"),
                "job_id": (result.get("job") or {}).get("job_id"),
            },
            success=bool(result.get("success")),
        )
        return result

    async def record_lanes(
        self, task_id: str, agent_id: str, lanes: list[LaneResultIn]
    ) -> dict[str, Any]:
        """Record lane results for a claimed pass and advance the job."""
        result = await self._call(
            "record_review_lanes",
            {
                "p_task_id": task_id,
                "p_agent_id": agent_id,
                "p_lanes": [lane.model_dump() for lane in lanes],
                "p_max_passes": get_config().review_queue.max_passes,
            },
        )
        job = result.get("job") or {}
        await get_audit_service().log_operation(
            agent_id=agent_id,
            operation="review_record_lanes",
            parameters={
                "task_id": task_id,
                "lanes": [(lane.vendor, lane.verified) for lane in lanes],
            },
            result={
                "reason": result.get("reason"),
                "status": job.get("status"),
                "verified_vendors": result.get("verified_vendors"),
                "residual_task_id": result.get("residual_task_id"),
            },
            success=bool(result.get("success")),
        )
        return result

    async def get_round(
        self, repo: str, pr: int, head_sha: str, round_: int | None = None
    ) -> dict[str, Any]:
        """Latest round (or the given round) recorded for a PR head."""
        return await self._call(
            "get_review_round",
            {"p_repo": repo, "p_pr": pr, "p_head_sha": head_sha, "p_round": round_},
        )

    async def claim_publication(self, job_id: str) -> dict[str, Any]:
        """Take the single right to post a terminal job's review."""
        return await self._call("claim_review_publication", {"p_job_id": job_id})

    async def finish_publication(
        self, job_id: str, review_id: int | None = None, error: str | None = None
    ) -> None:
        """Record the posted review, or release the claim with the error."""
        await self._call(
            "finish_review_publication",
            {"p_job_id": job_id, "p_review_id": review_id, "p_error": error},
        )


_review_queue_service: ReviewQueueService | None = None


def get_review_queue_service() -> ReviewQueueService:
    """Get the global review queue service instance."""
    global _review_queue_service
    if _review_queue_service is None:
        _review_queue_service = ReviewQueueService()
    return _review_queue_service
