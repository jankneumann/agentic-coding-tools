#!/usr/bin/env python3
"""Review-queue worker: claim PR review passes from the coordinator and run them.

Any host with vendor CLIs runs this loop (factory Phase 1, step 1.3). Each pass
is a ``review`` task on the coordinator's work queue, enqueued by the
review-queue GitHub Action for one PR head SHA. For every pass the worker:

1. claims it with ``/work/claim`` (``task_types=["review"]``);
2. confirms via ``/reviews/rounds`` that the pass is still the job's current
   one — a newer push supersedes it;
3. checks the head out with ``git worktree add --detach`` and makes the tree
   read-only;
4. dispatches every eligible vendor through ``ReviewOrchestrator``, minus the
   vendors an earlier pass already verified (``exclude_vendors``);
5. posts one lane per vendor to ``/reviews/results`` and then ``/work/complete``.

The worker holds no GitHub credential. Vendors read the diff with ``git diff``,
and the coordinator — not this host — posts the consolidated review.

Usage:
  python review_worker.py [--once] [--poll-seconds 30]
                          [--repo-dir owner/name=/path ...]
                          [--timeout 600] [--exclude-vendor VENDOR ...]

Coordinator URL and API key come from the same environment variables as the
coordination bridge (``COORDINATION_API_URL`` / ``COORDINATION_API_KEY``).
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib import parse as url_parse

_SCRIPTS_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _SCRIPTS_DIR.parent.parent
for _dir in (
    _SKILLS_DIR / "coordination-bridge" / "scripts",
    _SKILLS_DIR / "parallel-infrastructure" / "scripts",
):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

from vendor_review import build_review_prompt  # noqa: E402

logger = logging.getLogger("review_worker")

DEFAULT_POLL_SECONDS = 30
DEFAULT_REVIEW_TIMEOUT = 600
HTTP_TIMEOUT_SECONDS = 30.0

# Limits the coordinator enforces on POST /reviews/results; trimming here keeps
# one oversized lane from failing the whole submission.
MAX_LANES = 16
MAX_FINDINGS = 200
MAX_MODEL_CHARS = 128
MAX_ERROR_CHARS = 2000

_BLOCKING_CRITICALITY = frozenset({"high", "critical"})


class CoordinatorClient(Protocol):
    """One coordinator HTTP call: ``{"status_code", "data", "error"}``."""

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ReviewTask:
    """A claimed review pass, as ``review_enqueue_pass`` wrote its input_data."""

    task_id: str
    job_id: str
    repo: str
    pr: int
    head_sha: str
    base_sha: str
    round: int
    pass_number: int
    exclude_vendors: frozenset[str]

    @classmethod
    def from_claim(cls, claim: dict[str, Any]) -> ReviewTask:
        data = claim.get("input_data") or {}
        return cls(
            task_id=str(claim["task_id"]),
            job_id=str(data["review_job_id"]),
            repo=str(data["repo"]),
            pr=int(data["pr"]),
            head_sha=str(data["head_sha"]),
            base_sha=str(data["base_sha"]),
            round=int(data["round"]),
            pass_number=int(data.get("pass", 1)),
            exclude_vendors=frozenset(
                str(v).lower() for v in data.get("exclude_vendors") or []
            ),
        )


# ---------------------------------------------------------------------------
# Lane mapping
# ---------------------------------------------------------------------------


def lane_from_result(result: Any) -> dict[str, Any]:
    """Map one ``ReviewResult`` to a ``/reviews/results`` lane.

    A lane is verified only when the vendor succeeded AND returned a parsed
    findings list: a vendor that exited 0 but printed prose has not reviewed
    anything the coordinator can count toward quorum.
    """
    findings_doc = result.findings if isinstance(result.findings, dict) else {}
    findings = findings_doc.get("findings")
    verified = bool(result.success) and isinstance(findings, list)
    lane: dict[str, Any] = {"vendor": str(result.vendor).lower(), "verified": verified}
    if verified:
        assert isinstance(findings, list)
        lane["findings"] = findings[:MAX_FINDINGS]
        lane["verdict"] = _verdict(findings)
    if result.model_used:
        lane["model"] = str(result.model_used)[:MAX_MODEL_CHARS]
    if result.error:
        lane["error"] = str(result.error)[:MAX_ERROR_CHARS]
    elif not verified:
        lane["error"] = "vendor returned no parseable findings"
    return lane


def _verdict(findings: list[Any]) -> str:
    criticalities = {
        str(f.get("criticality", "")).lower() for f in findings if isinstance(f, dict)
    }
    if criticalities & _BLOCKING_CRITICALITY:
        return "blocking"
    return "advisory" if findings else "clean"


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


def _git(repo_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _has_commit(repo_dir: Path, sha: str) -> bool:
    return _git(repo_dir, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def ensure_commits(repo_dir: Path, task: ReviewTask) -> None:
    """Fetch the PR head and base when the local clone does not have them yet."""
    if not _has_commit(repo_dir, task.head_sha):
        _git(repo_dir, "fetch", "--no-tags", "origin", f"refs/pull/{task.pr}/head")
    if not _has_commit(repo_dir, task.base_sha):
        _git(repo_dir, "fetch", "--no-tags", "origin", task.base_sha)
    missing = [s for s in (task.head_sha, task.base_sha) if not _has_commit(repo_dir, s)]
    if missing:
        raise RuntimeError(f"commits not reachable from origin: {', '.join(missing)}")


def _set_writable(root: Path, writable: bool) -> None:
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod(mode | 0o200 if writable else mode & ~0o222)


@contextmanager
def review_checkout(repo_dir: Path, head_sha: str) -> Iterator[Path]:
    """A detached, read-only worktree at ``head_sha``, removed afterwards."""
    workdir = Path(tempfile.mkdtemp(prefix="review-"))
    added = _git(repo_dir, "worktree", "add", "--detach", str(workdir), head_sha)
    if added.returncode != 0:
        workdir.rmdir()
        raise RuntimeError(f"git worktree add failed: {added.stderr.strip()}")
    try:
        _set_writable(workdir, False)
        yield workdir
    finally:
        _set_writable(workdir, True)
        _git(repo_dir, "worktree", "remove", "--force", str(workdir))
        _git(repo_dir, "worktree", "prune")


def diff_size(repo_dir: Path, base_sha: str, head_sha: str) -> dict[str, Any]:
    """The ``pr_size`` shape ``build_review_prompt`` expects, from ``git diff``."""
    out = _git(repo_dir, "diff", "--numstat", f"{base_sha}...{head_sha}")
    files: list[str] = []
    additions = deletions = 0
    for line in out.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added, deleted, name = parts
        files.append(name)
        # Binary files report "-" for both counts.
        additions += int(added) if added.isdigit() else 0
        deletions += int(deleted) if deleted.isdigit() else 0
    return {
        "files": files,
        "changed_files": len(files),
        "additions": additions,
        "deletions": deletions,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def default_orchestrator() -> Any:
    """Coordinator-registered adapters first, agents.yaml as the fallback."""
    from review_dispatcher import ReviewOrchestrator

    orch = ReviewOrchestrator.from_coordinator()
    if not orch.adapters:
        orch = ReviewOrchestrator.from_agents_yaml()
    return orch


def exclude_vendors(orch: Any, vendors: frozenset[str]) -> None:
    """Drop every adapter for ``vendors`` from all three dispatch tiers.

    ``dispatch_and_wait`` excludes a single vendor; a residual pass can carry
    several, so the worker narrows the adapter maps instead.
    """
    if not vendors:
        return
    for attr in ("adapters", "sdk_adapters", "openai_adapters"):
        current = getattr(orch, attr, None) or {}
        setattr(
            orch,
            attr,
            {
                agent_id: adapter
                for agent_id, adapter in current.items()
                if str(adapter.vendor).lower() not in vendors
            },
        )


def available_vendors(orch: Any) -> list[str]:
    return [r.vendor for r in orch.discover_reviewers() if r.available]


# ---------------------------------------------------------------------------
# One pass
# ---------------------------------------------------------------------------


def is_current_pass(client: CoordinatorClient, task: ReviewTask) -> bool:
    """True while the job is active and this task is still its current pass."""
    query = url_parse.urlencode(
        {"repo": task.repo, "pr": task.pr, "head_sha": task.head_sha, "round": task.round}
    )
    resp = client.request("GET", f"/reviews/rounds?{query}")
    data = resp.get("data") or {}
    job = data.get("job") or {}
    if resp.get("status_code") != 200 or not data.get("found"):
        return False
    return job.get("status") == "active" and str(job.get("task_id")) == task.task_id


def _complete(
    client: CoordinatorClient,
    task_id: str,
    success: bool,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    payload: dict[str, Any] = {"task_id": task_id, "success": success}
    if result is not None:
        payload["result"] = result
    if error:
        payload["error_message"] = error[:MAX_ERROR_CHARS]
    resp = client.request("POST", "/work/complete", payload)
    if resp.get("status_code") != 200:
        logger.warning("work/complete for %s: %s", task_id, resp.get("error"))


def run_once(
    client: CoordinatorClient,
    orchestrator_factory: Callable[[], Any],
    repo_dirs: dict[str, Path],
    *,
    timeout_seconds: int = DEFAULT_REVIEW_TIMEOUT,
    host_excluded: frozenset[str] = frozenset(),
) -> str:
    """Claim and run at most one review pass. Returns a short outcome label."""
    orch = orchestrator_factory()
    exclude_vendors(orch, host_excluded)
    # Claim nothing this host cannot review: an idle host must not strand a
    # pass that another host could have run.
    if not available_vendors(orch):
        return "no_reviewers"

    claim = client.request("POST", "/work/claim", {"task_types": ["review"]})
    data = claim.get("data") or {}
    if claim.get("status_code") != 200 or not data.get("success") or not data.get("task_id"):
        return "idle"

    try:
        task = ReviewTask.from_claim(data)
    except (KeyError, TypeError, ValueError) as exc:
        _complete(client, str(data["task_id"]), False, error=f"malformed review task: {exc}")
        return "failed"
    logger.info(
        "claimed %s: %s#%d @ %s round %d pass %d",
        task.task_id, task.repo, task.pr, task.head_sha[:12], task.round, task.pass_number,
    )

    try:
        return _run_pass(client, orch, task, repo_dirs, timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - every claimed pass must be closed out
        logger.exception("review pass %s failed", task.task_id)
        _complete(client, task.task_id, False, error=f"{type(exc).__name__}: {exc}")
        return "failed"


def _run_pass(
    client: CoordinatorClient,
    orch: Any,
    task: ReviewTask,
    repo_dirs: dict[str, Path],
    timeout_seconds: int,
) -> str:
    if not is_current_pass(client, task):
        _complete(client, task.task_id, False, error="superseded")
        return "superseded"

    repo_dir = repo_dirs.get(task.repo)
    if repo_dir is None:
        _complete(client, task.task_id, False, error=f"no local clone for {task.repo}")
        return "failed"

    exclude_vendors(orch, task.exclude_vendors)
    if not available_vendors(orch):
        # The pass stays open on the coordinator until dead-pass recovery
        # exists; failing it here at least records why.
        _complete(client, task.task_id, False, error="no eligible reviewer on this host")
        return "failed"

    ensure_commits(repo_dir, task)
    diff_command = f"git diff {task.base_sha}...{task.head_sha}"
    prompt = build_review_prompt(
        task.pr, diff_size(repo_dir, task.base_sha, task.head_sha), diff_command
    )
    with review_checkout(repo_dir, task.head_sha) as worktree:
        results = orch.dispatch_and_wait(
            review_type="pr",
            dispatch_mode="review",
            prompt=prompt,
            cwd=worktree,
            timeout_seconds=timeout_seconds,
        )

    lanes = [
        lane
        for lane in (lane_from_result(r) for r in results)
        if lane["vendor"] not in task.exclude_vendors
    ][:MAX_LANES]
    if not lanes:
        _complete(client, task.task_id, False, error="no vendor produced a lane")
        return "failed"

    recorded = client.request(
        "POST", "/reviews/results", {"task_id": task.task_id, "lanes": lanes}
    )
    body = recorded.get("data") or {}
    if recorded.get("status_code") != 200:
        _complete(client, task.task_id, False, error=f"reviews/results: {recorded.get('error')}")
        return "failed"
    if not body.get("success"):
        reason = str(body.get("reason") or "rejected")
        _complete(client, task.task_id, False, error=reason)
        return "superseded" if reason in ("superseded", "stale_pass") else "failed"

    summary = {
        "review_job_id": task.job_id,
        "lanes": [{"vendor": lane["vendor"], "verified": lane["verified"]} for lane in lanes],
        "job_status": (body.get("job") or {}).get("status"),
    }
    _complete(client, task.task_id, True, result=summary)
    return "reviewed"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _origin_repo(repo_dir: Path) -> str | None:
    """``owner/name`` from a GitHub origin URL (https or ssh form)."""
    url = _git(repo_dir, "remote", "get-url", "origin").stdout.strip()
    if not url:
        return None
    path = url.split("github.com", 1)[-1].lstrip(":/")
    path = path.removesuffix(".git")
    return path if path.count("/") == 1 else None


def parse_repo_dirs(specs: list[str], cwd: Path) -> dict[str, Path]:
    """``owner/name=/path`` pairs; with none given, the cwd clone's origin."""
    if not specs:
        repo = _origin_repo(cwd)
        return {repo: cwd} if repo else {}
    repo_dirs: dict[str, Path] = {}
    for spec in specs:
        repo, sep, path = spec.partition("=")
        if not sep or not repo or not path:
            raise SystemExit(f"--repo-dir expects owner/name=/path, got {spec!r}")
        repo_dirs[repo] = Path(path).expanduser().resolve()
    return repo_dirs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--once", action="store_true", help="run at most one pass")
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--repo-dir", action="append", default=[], metavar="OWNER/NAME=PATH")
    parser.add_argument("--timeout", type=int, default=DEFAULT_REVIEW_TIMEOUT)
    parser.add_argument("--exclude-vendor", action="append", default=[], metavar="VENDOR")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    repo_dirs = parse_repo_dirs(args.repo_dir, Path.cwd())
    if not repo_dirs:
        raise SystemExit("review_worker: no repository to review (pass --repo-dir)")
    from coordination_bridge import CoordinatorHttpClient

    try:
        client = CoordinatorHttpClient(timeout=HTTP_TIMEOUT_SECONDS)
    except ValueError as exc:
        raise SystemExit(f"review_worker: {exc}") from exc
    host_excluded = frozenset(v.lower() for v in args.exclude_vendor)

    while True:
        outcome = run_once(
            client,
            default_orchestrator,
            repo_dirs,
            timeout_seconds=args.timeout,
            host_excluded=host_excluded,
        )
        logger.info("outcome: %s", outcome)
        if args.once:
            return 0 if outcome in ("reviewed", "idle", "superseded") else 1
        # Back-to-back passes while work is queued; poll only when idle.
        if outcome not in ("reviewed", "superseded"):
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
