"""Read cross-host review rounds from the coordinator for ``converge()``.

A review round is the set of lane results for one PR ``head_sha``, whichever
host ran them (factory Phase 1, section 1.5). Hosts with vendor CLIs claim
``review`` jobs from the coordinator queue and post their lanes there; this
module turns the verified lanes of the worktree's current head into
``ReviewResult`` objects that ``converge()`` merges with its local dispatch.

Only verified lanes count. A head that no remote host has reviewed (for
example an unpushed fix commit) yields no results, so the round is counted
from local lanes alone — never from an older head's verdicts.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib import parse as url_parse

_PARALLEL_INFRA_DIR = str(
    Path(__file__).resolve().parent.parent.parent / "parallel-infrastructure" / "scripts"
)
if _PARALLEL_INFRA_DIR not in sys.path:
    sys.path.insert(0, _PARALLEL_INFRA_DIR)

from review_dispatcher import ReviewResult  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_POLL_SECONDS = 15.0


class CoordinatorClient(Protocol):
    """Anything with the coordination bridge's ``{status_code, data}`` shape."""

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


def fetch_round(
    client: CoordinatorClient, repo: str, pr: int, head_sha: str
) -> dict[str, Any] | None:
    """The latest coordinator round job for ``head_sha``, or ``None``."""
    query = url_parse.urlencode({"repo": repo, "pr": pr, "head_sha": head_sha})
    resp = client.request("GET", f"/reviews/rounds?{query}")
    data = resp.get("data") or {}
    if resp.get("status_code") != 200 or not data.get("found"):
        return None
    job: dict[str, Any] = data.get("job") or {}
    return job


def lanes_to_results(job: dict[str, Any]) -> list[ReviewResult]:
    """One successful ``ReviewResult`` per verified lane, first per vendor."""
    results: dict[str, ReviewResult] = {}
    for lane in job.get("lanes") or []:
        vendor = str(lane.get("vendor") or "")
        if not lane.get("verified") or not vendor or vendor in results:
            continue
        results[vendor] = ReviewResult(
            vendor=vendor,
            success=True,
            findings={"findings": list(lane.get("findings") or [])},
            model_used=lane.get("model"),
        )
    return list(results.values())


def worktree_head(worktree: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def coordinator_round_source(
    client: CoordinatorClient,
    repo: str,
    pr: int,
    worktree: Path,
    *,
    wait_seconds: float = 0.0,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Callable[[int], list[ReviewResult]]:
    """Build the ``remote_results`` callable ``converge()`` accepts.

    Each call reads the worktree's HEAD and returns that head's verified
    remote lanes. With ``wait_seconds`` it polls while the coordinator job is
    still ``active`` (remote passes in flight), up to that budget.
    """

    def remote_results(round_num: int) -> list[ReviewResult]:
        head_sha = worktree_head(worktree)
        deadline = clock() + wait_seconds
        while True:
            job = fetch_round(client, repo, pr, head_sha)
            if job is not None and job.get("status") != "active":
                break
            if clock() >= deadline:
                break
            sleep(poll_seconds)
        results = lanes_to_results(job) if job else []
        logger.info(
            "Remote round for %s#%d at %s (converge round %d): %s, vendors %s",
            repo, pr, head_sha[:12], round_num,
            job.get("status") if job else "not found",
            [r.vendor for r in results],
        )
        return results

    return remote_results
