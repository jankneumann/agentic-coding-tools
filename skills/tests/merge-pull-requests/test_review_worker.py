"""Review-queue worker: one claimed pass end to end, against a fake coordinator.

The worker is the host side of factory Phase 1 (design doc step 1.3). These
tests pin the contract with the coordinator's review routes — what a lane
looks like, when a pass is abandoned as superseded, which vendors a residual
pass may use — and the checkout's lifecycle, using a real git repository so
the worktree, fetch and diff paths run for real.
"""

from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "merge-pull-requests" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import review_worker  # noqa: E402
from review_worker import (  # noqa: E402
    ReviewTask,
    diff_size,
    ensure_commits,
    lane_from_result,
    parse_repo_dirs,
    review_checkout,
    run_once,
)

REPO = "acme/widgets"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@test", *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def origin(tmp_path: Path) -> SimpleNamespace:
    """A repository with a base commit and a PR head published as refs/pull/7/head."""
    repo = tmp_path / "origin"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "app.py").write_text("print('one')\n")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "app.py").write_text("print('two')\nprint('three')\n")
    (repo / "new.py").write_text("x = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "head")
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/pull/7/head", head)
    _git(repo, "checkout", "-q", "main")
    _git(repo, "branch", "-D", "feature")
    return SimpleNamespace(path=repo, base=base, head=head)


@pytest.fixture
def clone(tmp_path: Path, origin: SimpleNamespace) -> Path:
    """A host clone that has main but not the PR head yet."""
    path = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", "--single-branch", "-b", "main", str(origin.path), str(path)],
        check=True,
    )
    return path


def _task(origin: SimpleNamespace, **overrides: Any) -> ReviewTask:
    fields: dict[str, Any] = {
        "task_id": "task-1",
        "job_id": "job-1",
        "repo": REPO,
        "pr": 7,
        "head_sha": origin.head,
        "base_sha": origin.base,
        "round": 1,
        "pass_number": 1,
        "exclude_vendors": frozenset(),
    }
    fields.update(overrides)
    return ReviewTask(**fields)


def _result(vendor: str, *, success: bool = True, findings: Any = None, **kw: Any) -> Any:
    return SimpleNamespace(
        vendor=vendor,
        success=success,
        findings=findings,
        model_used=kw.get("model_used"),
        error=kw.get("error"),
    )


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeCoordinator:
    """Canned responses per (method, path prefix); records every request."""

    def __init__(self, origin: SimpleNamespace, *, job_status: str = "active",
                 current_task: str = "task-1", exclude: list[str] | None = None,
                 results_body: dict[str, Any] | None = None, queue_empty: bool = False):
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.origin = origin
        self.job_status = job_status
        self.current_task = current_task
        self.exclude = exclude or []
        self.results_body = results_body or {
            "success": True, "job": {"status": "quorum_met"}, "publish_ready": True,
        }
        self.queue_empty = queue_empty

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None):
        self.calls.append((method, path, payload))
        if path == "/work/claim":
            if self.queue_empty:
                return {"status_code": 200, "data": {"success": False, "reason": "no_tasks"}}
            return {"status_code": 200, "data": {
                "success": True, "task_id": "task-1", "task_type": "review",
                "input_data": {
                    "review_job_id": "job-1", "repo": REPO, "pr": 7,
                    "head_sha": self.origin.head, "base_sha": self.origin.base,
                    "round": 1, "lanes_required": 2, "risk": "medium", "pass": 2,
                    "exclude_vendors": self.exclude, "submitted_by": "producer",
                },
            }}
        if path.startswith("/reviews/rounds?"):
            return {"status_code": 200, "data": {"found": True, "job": {
                "job_id": "job-1", "status": self.job_status, "task_id": self.current_task,
            }}}
        if path == "/reviews/results":
            return {"status_code": 200, "data": self.results_body}
        if path == "/work/complete":
            return {"status_code": 200, "data": {"success": True}}
        raise AssertionError(f"unexpected request {method} {path}")

    def paths(self) -> list[str]:
        return [path.split("?")[0] for _, path, _ in self.calls]

    def payload(self, path: str) -> dict[str, Any]:
        return next(p for _, call_path, p in self.calls if call_path == path) or {}


class FakeOrchestrator:
    """The slice of ReviewOrchestrator the worker uses."""

    def __init__(self, vendors: list[str], results: dict[str, Any] | None = None):
        self.adapters = {f"{v}-local": SimpleNamespace(vendor=v) for v in vendors}
        self.sdk_adapters: dict[str, Any] = {}
        self.openai_adapters: dict[str, Any] = {}
        self.results = results or {}
        self.dispatched: list[dict[str, Any]] = []

    def discover_reviewers(self) -> list[Any]:
        return [SimpleNamespace(vendor=a.vendor, available=True) for a in self.adapters.values()]

    def dispatch_and_wait(self, **kwargs: Any) -> list[Any]:
        cwd = Path(kwargs["cwd"])
        kwargs["worktree_files"] = sorted(p.name for p in cwd.iterdir() if p.name != ".git")
        kwargs["worktree_writable"] = bool((cwd / "app.py").stat().st_mode & stat.S_IWUSR)
        self.dispatched.append(kwargs)
        return [
            self.results.get(a.vendor, _result(a.vendor, findings={"findings": []}))
            for a in self.adapters.values()
        ]


def _run(coord: FakeCoordinator, orch: FakeOrchestrator, clone: Path, **kw: Any) -> str:
    return run_once(coord, lambda: orch, {REPO: clone}, timeout_seconds=5, **kw)


# ---------------------------------------------------------------------------
# Lane mapping
# ---------------------------------------------------------------------------


def test_lane_is_verified_only_with_a_parsed_findings_list() -> None:
    assert lane_from_result(_result("codex", findings={"findings": []}))["verified"] is True
    prose = lane_from_result(_result("codex", findings=None))
    assert prose["verified"] is False
    assert prose["error"] == "vendor returned no parseable findings"
    failed = lane_from_result(_result("codex", success=False, error="timeout"))
    assert failed == {"vendor": "codex", "verified": False, "error": "timeout"}


@pytest.mark.parametrize(("criticalities", "verdict"), [
    ([], "clean"),
    (["low", "medium"], "advisory"),
    (["low", "high"], "blocking"),
    (["critical"], "blocking"),
])
def test_verdict_follows_the_worst_criticality(criticalities: list[str], verdict: str) -> None:
    findings = [{"id": i, "criticality": c} for i, c in enumerate(criticalities)]
    lane = lane_from_result(_result("gemini", findings={"findings": findings}))
    assert lane["verdict"] == verdict


def test_lane_fields_are_trimmed_to_the_coordinator_limits() -> None:
    lane = lane_from_result(_result(
        "Codex",
        findings={"findings": [{"id": i} for i in range(250)]},
        model_used="m" * 300,
        error="e" * 5000,
    ))
    assert lane["vendor"] == "codex"
    assert len(lane["findings"]) == review_worker.MAX_FINDINGS
    assert len(lane["model"]) == review_worker.MAX_MODEL_CHARS
    assert len(lane["error"]) == review_worker.MAX_ERROR_CHARS


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


def test_missing_commits_are_fetched_from_the_pull_ref(clone: Path, origin: SimpleNamespace) -> None:
    ensure_commits(clone, _task(origin))
    _git(clone, "cat-file", "-e", f"{origin.head}^{{commit}}")


def test_unreachable_head_is_an_error(clone: Path, origin: SimpleNamespace) -> None:
    with pytest.raises(RuntimeError, match="not reachable"):
        ensure_commits(clone, _task(origin, head_sha="f" * 40))


def test_checkout_is_detached_read_only_and_removed(clone: Path, origin: SimpleNamespace) -> None:
    ensure_commits(clone, _task(origin))
    with review_checkout(clone, origin.head) as worktree:
        assert _git(worktree, "rev-parse", "HEAD") == origin.head
        assert _git(worktree, "branch", "--show-current") == ""
        assert not (worktree / "new.py").stat().st_mode & 0o222
    assert not worktree.exists()
    assert str(worktree) not in _git(clone, "worktree", "list")


def test_diff_size_counts_the_merge_base_diff(clone: Path, origin: SimpleNamespace) -> None:
    ensure_commits(clone, _task(origin))
    size = diff_size(clone, origin.base, origin.head)
    assert size == {"files": ["app.py", "new.py"], "changed_files": 2,
                    "additions": 3, "deletions": 1}


# ---------------------------------------------------------------------------
# One pass
# ---------------------------------------------------------------------------


def test_pass_posts_lanes_then_completes(clone: Path, origin: SimpleNamespace) -> None:
    coord = FakeCoordinator(origin)
    orch = FakeOrchestrator(["codex", "gemini"], results={
        "gemini": _result("gemini", findings={"findings": [{"id": 1, "criticality": "high"}]},
                          model_used="g-pro"),
    })

    assert _run(coord, orch, clone) == "reviewed"

    assert coord.paths() == ["/work/claim", "/reviews/rounds", "/reviews/results", "/work/complete"]
    assert coord.payload("/work/claim") == {"task_types": ["review"]}
    lanes = coord.payload("/reviews/results")["lanes"]
    assert [(lane["vendor"], lane["verified"], lane["verdict"]) for lane in lanes] == [
        ("codex", True, "clean"), ("gemini", True, "blocking"),
    ]
    complete = coord.payload("/work/complete")
    assert complete["success"] is True
    assert complete["result"]["job_status"] == "quorum_met"

    dispatch = orch.dispatched[0]
    assert dispatch["review_type"] == "pr" and dispatch["dispatch_mode"] == "review"
    assert f"git diff {origin.base}...{origin.head}" in dispatch["prompt"]
    assert "gh pr diff" not in dispatch["prompt"]
    assert dispatch["worktree_files"] == ["app.py", "new.py"]
    assert dispatch["worktree_writable"] is False


def test_residual_pass_skips_vendors_already_verified(clone: Path, origin: SimpleNamespace) -> None:
    coord = FakeCoordinator(origin, exclude=["codex"])
    orch = FakeOrchestrator(["codex", "gemini"])

    assert _run(coord, orch, clone) == "reviewed"

    assert [lane["vendor"] for lane in coord.payload("/reviews/results")["lanes"]] == ["gemini"]


def test_superseded_pass_is_closed_without_reviewing(clone: Path, origin: SimpleNamespace) -> None:
    coord = FakeCoordinator(origin, job_status="superseded")
    orch = FakeOrchestrator(["codex"])

    assert _run(coord, orch, clone) == "superseded"

    assert "/reviews/results" not in coord.paths()
    assert orch.dispatched == []
    assert coord.payload("/work/complete") == {
        "task_id": "task-1", "success": False, "error_message": "superseded",
    }


def test_stale_pass_is_closed_without_reviewing(clone: Path, origin: SimpleNamespace) -> None:
    coord = FakeCoordinator(origin, current_task="task-2")
    assert _run(coord, FakeOrchestrator(["codex"]), clone) == "superseded"


def test_push_during_review_is_reported_as_superseded(clone: Path, origin: SimpleNamespace) -> None:
    coord = FakeCoordinator(origin, results_body={"success": False, "reason": "superseded"})

    assert _run(coord, FakeOrchestrator(["codex"]), clone) == "superseded"

    assert coord.payload("/work/complete")["error_message"] == "superseded"


def test_host_without_reviewers_does_not_claim(clone: Path, origin: SimpleNamespace) -> None:
    coord = FakeCoordinator(origin)

    assert _run(coord, FakeOrchestrator(["codex"]), clone, host_excluded=frozenset({"codex"})) \
        == "no_reviewers"

    assert coord.calls == []


def test_only_excluded_vendors_left_fails_the_pass(clone: Path, origin: SimpleNamespace) -> None:
    coord = FakeCoordinator(origin, exclude=["codex"])

    assert _run(coord, FakeOrchestrator(["codex"]), clone) == "failed"

    assert coord.payload("/work/complete")["error_message"] == "no eligible reviewer on this host"


def test_empty_queue_is_idle(clone: Path, origin: SimpleNamespace) -> None:
    coord = FakeCoordinator(origin, queue_empty=True)
    assert _run(coord, FakeOrchestrator(["codex"]), clone) == "idle"
    assert coord.paths() == ["/work/claim"]


def test_unknown_repository_fails_the_pass(clone: Path, origin: SimpleNamespace) -> None:
    coord = FakeCoordinator(origin)

    outcome = run_once(coord, lambda: FakeOrchestrator(["codex"]), {"other/repo": clone})

    assert outcome == "failed"
    assert coord.payload("/work/complete")["error_message"] == f"no local clone for {REPO}"


def test_dispatch_crash_still_closes_the_pass(clone: Path, origin: SimpleNamespace) -> None:
    coord = FakeCoordinator(origin)
    orch = FakeOrchestrator(["codex"])

    def boom(**_: Any) -> list[Any]:
        raise OSError("vendor exploded")

    orch.dispatch_and_wait = boom  # type: ignore[method-assign]

    assert _run(coord, orch, clone) == "failed"

    assert coord.payload("/work/complete")["error_message"] == "OSError: vendor exploded"
    assert _git(clone, "worktree", "list").count("\n") == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "https://github.com/acme/widgets.git",
    "git@github.com:acme/widgets.git",
    "https://github.com/acme/widgets",
])
def test_default_repo_dir_comes_from_the_origin_url(tmp_path: Path, url: str) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "remote", "add", "origin", url)
    assert parse_repo_dirs([], tmp_path) == {REPO: tmp_path}


def test_explicit_repo_dirs_are_parsed(tmp_path: Path) -> None:
    assert parse_repo_dirs([f"{REPO}={tmp_path}"], Path.cwd()) == {REPO: tmp_path.resolve()}
    with pytest.raises(SystemExit):
        parse_repo_dirs(["acme/widgets"], Path.cwd())
