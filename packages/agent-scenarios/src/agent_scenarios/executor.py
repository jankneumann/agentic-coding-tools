"""Per-vendor executors — the injection seam for running an agent headless.

The runner depends only on the :class:`ScenarioExecutor` protocol, so the
framework is **structurally multi-vendor**: swapping a real CLI adapter for a
fake, or one vendor for another, is a constructor argument, not a code change.

Two implementations ship:

* :class:`CLIVendorExecutor` — the real adapter. It materializes the fixture,
  shells to a per-vendor CLI (``claude -p`` / ``codex exec`` / ``agy --prompt`` /
  ``grok`` / ``pi`` …),
  and normalizes the emitted transcript via ``collect-transcripts``. It is
  *wired but not live-tested in-container* (no vendor CLIs or keys here); it is
  exercised for real on the GX10.
* :class:`FakeExecutor` — a scripted executor used by the test suite to prove
  the runner loop, the scorer, and the findings emitter end-to-end without any
  vendor.
"""

from __future__ import annotations

import ntpath
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Protocol

from .models import AgentScenario, PRRef, RunResult, WorkspaceState


class ScenarioExecutor(Protocol):
    """Runs one scenario against one vendor and returns a :class:`RunResult`.

    Implementations own workspace materialization; the runner only orchestrates
    the loop and scoring.
    """

    def run(self, scenario: AgentScenario, vendor: str, workdir: Path) -> RunResult: ...


class FixtureError(RuntimeError):
    """Raised when fixture materialization (git init / setup / commands) fails.

    Carries the failed command, exit code, and captured output so the caller can
    surface a meaningful ``RunResult`` error instead of silently scoring against a
    broken workspace.
    """


def _run_checked(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a fixture-setup command and fail loudly on a non-zero exit."""
    proc = _run(cmd, cwd)
    if proc.returncode != 0:
        raise FixtureError(
            f"fixture command failed (exit {proc.returncode}): {' '.join(cmd)}\n"
            f"stdout: {proc.stdout.strip()[:500]}\nstderr: {proc.stderr.strip()[:500]}"
        )
    return proc


def materialize_fixture(scenario: AgentScenario, workdir: Path) -> WorkspaceState:
    """Write the fixture files and initialize git, returning the initial state.

    Shared by every executor so fixture semantics are identical across vendors
    (a prerequisite for meaningful parity comparison). Raises :class:`FixtureError`
    if any git-init / setup / fixture command fails, so callers never run a vendor
    or the scorer against a half-built workspace.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    fx = scenario.fixture

    workdir_resolved = workdir.resolve()
    for rel, content in fx.files.items():
        # Guard against path traversal / absolute paths: a fixture file must stay
        # inside the throwaway workspace, never write to `../` or an absolute path.
        if PurePosixPath(rel).is_absolute() or ntpath.isabs(rel):
            raise FixtureError(f"fixture file path must be relative, got {rel!r}")
        target = (workdir / rel).resolve()
        if not target.is_relative_to(workdir_resolved):
            raise FixtureError(f"fixture file path escapes the workspace: {rel!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    working_branch = fx.base_branch
    base_sha: str | None = None
    if fx.git_init:
        _run_checked(["git", "init", "-q", "-b", fx.base_branch], workdir)
        _run_checked(["git", "config", "user.email", "harness@agent-scenarios.local"], workdir)
        _run_checked(["git", "config", "user.name", "agent-scenarios"], workdir)
        _run_checked(["git", "add", "-A"], workdir)
        _run_checked(
            ["git", "commit", "-q", "-m", "fixture: initial state", "--allow-empty"], workdir
        )
        base_sha = _run_checked(["git", "rev-parse", "HEAD"], workdir).stdout.strip() or None

    for cmd in fx.commands:
        _run_checked(cmd, workdir)

    return WorkspaceState(root=str(workdir), working_branch=working_branch, base_sha=base_sha)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)


def _fixture_error_result(
    scenario: AgentScenario, vendor: str, workdir: Path, exc: FixtureError
) -> RunResult:
    """Surface a fixture-materialization failure as an error RunResult (not a crash)."""
    return RunResult(
        scenario_id=scenario.id,
        vendor=vendor,
        workspace=WorkspaceState(root=str(workdir)),
        exit_code=1,
        error=f"fixture materialization failed: {exc}",
    )


class CLIVendorExecutor:
    """Real adapter that shells to a per-vendor coding-agent CLI.

    ``vendor_commands`` maps a vendor id to an argv *template*. The template may
    contain ``{prompt}`` and ``{skill}`` placeholders, filled per scenario. The
    command is run inside the materialized workspace; on the GX10 the CLI edits
    the workspace in place, and this adapter then collects the transcript and
    resolves any PR via ``gh``.

    This class is intentionally not exercised against a live CLI in-container;
    ``run`` degrades to an error :class:`RunResult` when the CLI is absent so a
    misconfigured vendor never crashes the parity loop.
    """

    def __init__(
        self,
        vendor_commands: dict[str, str],
        *,
        transcript_normalizer: Callable[[Path, str], list[dict]] | None = None,
        timeout_seconds: int = 1800,
    ) -> None:
        self._vendor_commands = vendor_commands
        # Injected so this package does not hard-depend on the collect-transcripts
        # skill layout; on the GX10 the caller wires normalize.normalize_file.
        self._normalize = transcript_normalizer
        self._timeout = timeout_seconds

    def run(self, scenario: AgentScenario, vendor: str, workdir: Path) -> RunResult:
        try:
            state = materialize_fixture(scenario, workdir)
        except FixtureError as exc:
            return _fixture_error_result(scenario, vendor, workdir, exc)
        template = self._vendor_commands.get(vendor)
        if template is None:
            return RunResult(
                scenario_id=scenario.id,
                vendor=vendor,
                workspace=state,
                exit_code=127,
                error=f"no CLI command configured for vendor {vendor!r}",
            )

        argv = [
            part.format(prompt=scenario.task_prompt, skill=scenario.skill_under_test)
            for part in shlex.split(template)
        ]
        try:
            proc = subprocess.run(
                argv,
                cwd=str(workdir),
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return RunResult(
                scenario_id=scenario.id,
                vendor=vendor,
                workspace=state,
                exit_code=127,
                error=f"vendor CLI unavailable/failed: {exc}",
            )

        state = self._observe_post_run(scenario, workdir, state)
        events = self._collect_transcript(workdir, vendor)
        return RunResult(
            scenario_id=scenario.id,
            vendor=vendor,
            workspace=state,
            transcript_events=events,
            exit_code=proc.returncode,
            error=None if proc.returncode == 0 else proc.stderr.strip()[:500] or None,
        )

    def _observe_post_run(
        self, scenario: AgentScenario, workdir: Path, state: WorkspaceState
    ) -> WorkspaceState:
        """Resolve the working branch and any PR the agent created."""
        head = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], workdir)
        branch = head.stdout.strip() or state.working_branch
        created_pr: PRRef | None = None
        pr = _run(["gh", "pr", "view", "--json", "number,url,headRefName,title"], workdir)
        if pr.returncode == 0 and pr.stdout.strip():
            import json

            try:
                data = json.loads(pr.stdout)
                created_pr = PRRef(
                    number=data.get("number"),
                    head=data.get("headRefName"),
                    url=data.get("url"),
                    title=data.get("title"),
                )
            except (json.JSONDecodeError, TypeError):
                created_pr = None
        return state.model_copy(update={"working_branch": branch, "created_pr": created_pr})

    def _collect_transcript(self, workdir: Path, vendor: str) -> list[dict]:
        if self._normalize is None:
            return []
        # The CLI writes its transcript to a vendor-specific location; the GX10
        # wiring passes a normalizer that knows where. Failures are non-fatal.
        try:
            return self._normalize(workdir, vendor)
        except Exception:
            return []


class FakeExecutor:
    """Scripted executor for tests — no vendor, fully deterministic.

    ``script`` maps ``(scenario_id, vendor)`` (or ``scenario_id`` alone as a
    fallback) to an :class:`Outcome` describing what the "agent" did: files to
    write/delete, a branch to create, a commit to make, an optional PR, and a
    synthetic normalized transcript. This lets the test suite exercise the full
    runner → scorer → judge → emitter path across multiple vendors.
    """

    def __init__(self, script: dict[tuple[str, str] | str, Outcome]) -> None:
        self._script = script

    def run(self, scenario: AgentScenario, vendor: str, workdir: Path) -> RunResult:
        try:
            state = materialize_fixture(scenario, workdir)
        except FixtureError as exc:
            return _fixture_error_result(scenario, vendor, workdir, exc)
        outcome = self._script.get((scenario.id, vendor)) or self._script.get(scenario.id)
        if outcome is None:
            return RunResult(
                scenario_id=scenario.id,
                vendor=vendor,
                workspace=state,
                exit_code=1,
                error=f"no scripted outcome for ({scenario.id}, {vendor})",
            )
        state = outcome.apply(workdir, state)
        return RunResult(
            scenario_id=scenario.id,
            vendor=vendor,
            workspace=state,
            transcript_events=outcome.transcript(scenario, vendor),
            exit_code=outcome.exit_code,
            error=outcome.error,
        )


class Outcome:
    """A scripted agent outcome applied to a fixture workspace by FakeExecutor."""

    def __init__(
        self,
        *,
        write_files: dict[str, str] | None = None,
        delete_files: list[str] | None = None,
        new_branch: str | None = None,
        commit_message: str | None = None,
        pr: PRRef | None = None,
        artifacts: dict[str, str] | None = None,
        exit_code: int = 0,
        error: str | None = None,
        events: list[dict] | None = None,
    ) -> None:
        self.write_files = write_files or {}
        self.delete_files = delete_files or []
        self.new_branch = new_branch
        self.commit_message = commit_message
        self.pr = pr
        self.artifacts = artifacts or {}
        self.exit_code = exit_code
        self.error = error
        self._events = events

    def apply(self, workdir: Path, state: WorkspaceState) -> WorkspaceState:
        if self.new_branch:
            _run(["git", "checkout", "-q", "-b", self.new_branch], workdir)
        for rel, content in self.write_files.items():
            target = workdir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        for rel in self.delete_files:
            target = workdir / rel
            if target.exists():
                target.unlink()
        if self.commit_message:
            _run(["git", "add", "-A"], workdir)
            _run(["git", "commit", "-q", "-m", self.commit_message, "--allow-empty"], workdir)
        branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], workdir).stdout.strip()
        return state.model_copy(
            update={
                "working_branch": branch or state.working_branch,
                "created_pr": self.pr,
                "artifacts": self.artifacts,
            }
        )

    def transcript(self, scenario: AgentScenario, vendor: str) -> list[dict]:
        if self._events is not None:
            return self._events
        # Minimal normalized transcript (collect-transcripts event shape).
        return [
            {
                "event_id": f"{scenario.id}-{vendor}-0",
                "session_id": f"{scenario.id}-{vendor}",
                "sequence_number": 0,
                "role": "user",
                "content": [{"type": "text", "text": scenario.task_prompt}],
                "harness": vendor,
            },
            {
                "event_id": f"{scenario.id}-{vendor}-1",
                "session_id": f"{scenario.id}-{vendor}",
                "sequence_number": 1,
                "role": "assistant",
                "content": [{"type": "text", "text": "Completed the task."}],
                "harness": vendor,
            },
        ]
