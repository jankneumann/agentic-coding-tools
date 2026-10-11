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

import json
import ntpath
import os
import shlex
import shutil
import subprocess
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Protocol

from .gh_shim import bin_dir_for, install_gh_shim, origin_path_for, unsupported_calls
from .materialize import SkillMaterializationError, materialize_skills
from .models import AgentScenario, PRRef, RunResult, TranscriptEvent, WorkspaceState

#: Built-in hermetic denylist (design D5): config can extend it, never shrink it. Covers
#: GitHub tokens and every coordinator URL / API-key / Cloudflare-Access variable that the
#: skills (coordination_bridge.py, improve-harness) read.
HERMETIC_SCRUB: frozenset[str] = frozenset(
    {
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GH_ENTERPRISE_TOKEN",
        "GITHUB_ENTERPRISE_TOKEN",
        "COORDINATION_API_KEY",
        "COORDINATOR_API_KEY",
        "COORDINATOR_URL",
        "COORDINATOR_HTTP_URL",
        "AGENT_COORDINATOR_API_URL",
        "AGENT_COORDINATOR_HTTP_URL",
        "AGENT_COORDINATOR_REST_PORT",
        "CF_ACCESS_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
    }
)
#: Forced into every vendor subprocess: the discard port, accepted by the bridge as loopback,
#: so detection never falls back to ``http://localhost:3000`` (the live coordinator).
COORDINATION_URL_SENTINEL = "http://127.0.0.1:9"
COORDINATION_URL_VAR = "COORDINATION_API_URL"


def build_vendor_env(
    base_env: Mapping[str, str],
    *,
    env_scrub: Iterable[str] = (),
    env_set: Mapping[str, str] | None = None,
    always_scrub: Iterable[str] = (),
    path_prepend: Path | None = None,
) -> dict[str, str]:
    """Compute the hermetic environment for a vendor subprocess.

    Scrub = ``HERMETIC_SCRUB`` ∪ ``env_scrub`` ∪ ``always_scrub``; then ``env_set`` is applied;
    the coordinator sentinel is forced last so no ``env_set`` can re-open the live path.
    With both ``env_scrub`` and ``env_set`` empty the built-in denylist still applies.
    """
    scrub = HERMETIC_SCRUB | set(env_scrub) | set(always_scrub)
    env = {k: v for k, v in base_env.items() if k not in scrub}
    for key, value in (env_set or {}).items():
        if key in scrub:
            continue  # config validation rejects this; belt and braces
        env[key] = value
    env[COORDINATION_URL_VAR] = COORDINATION_URL_SENTINEL
    if path_prepend is not None:
        env["PATH"] = f"{path_prepend}{os.pathsep}{env.get('PATH', '')}"
    return env


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

    if fx.local_remote:
        if not fx.git_init:
            raise FixtureError("fixture 'local_remote' requires 'git_init'")
        origin = origin_path_for(workdir)
        if origin.exists():
            shutil.rmtree(origin)
        _run_checked(["git", "init", "-q", "--bare", "-b", fx.base_branch, str(origin)], workdir)
        _run_checked(["git", "remote", "add", "origin", str(origin)], workdir)
        _run_checked(["git", "push", "-q", "origin", fx.base_branch], workdir)

    for cmd in fx.commands:
        _run_checked(cmd, workdir)

    for pr in fx.prs:
        _run_checked(["git", "push", "-q", "origin", pr.head], workdir)

    return WorkspaceState(root=str(workdir), working_branch=working_branch, base_sha=base_sha)


def _run(
    cmd: list[str], cwd: Path, env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, check=False,
        env=dict(env) if env is not None else None,
    )


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
        transcript_normalizer: Callable[[Path, str], list[TranscriptEvent]] | None = None,
        timeout_seconds: int = 1800,
        skills_root: Path | None = None,
        env_scrub: Iterable[str] = (),
        env_set: Mapping[str, str] | None = None,
        always_scrub: Iterable[str] = (),
    ) -> None:
        self._vendor_commands = vendor_commands
        self._skills_root = Path(skills_root) if skills_root is not None else None
        self._env_scrub = tuple(env_scrub)
        self._env_set = dict(env_set or {})
        self._always_scrub = tuple(always_scrub)
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

        skills_sha: str | None = None
        if self._skills_root is not None:
            try:
                skills_sha = materialize_skills(
                    self._skills_root, scenario.skill_under_test, workdir
                )
            except SkillMaterializationError as exc:
                return RunResult(
                    scenario_id=scenario.id,
                    vendor=vendor,
                    workspace=state,
                    exit_code=1,
                    error=f"skill materialization failed: {exc}",
                )

        shim_dir = install_gh_shim(scenario, workdir, origin_path_for(workdir))
        env = build_vendor_env(
            os.environ,
            env_scrub=self._env_scrub,
            env_set=self._env_set,
            always_scrub=self._always_scrub,
            path_prepend=shim_dir,
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
                env=env,
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                scenario_id=scenario.id,
                vendor=vendor,
                workspace=state,
                exit_code=124,
                error=f"vendor CLI timed out after {self._timeout}s",
                skills_sha=skills_sha,
            )
        except FileNotFoundError as exc:
            return RunResult(
                scenario_id=scenario.id,
                vendor=vendor,
                workspace=state,
                exit_code=127,
                error=f"vendor CLI unavailable: {exc}",
                skills_sha=skills_sha,
            )

        state = self._observe_post_run(scenario, workdir, state, env)
        events = self._collect_transcript(workdir, vendor)
        exit_code = proc.returncode
        error = None if proc.returncode == 0 else proc.stderr.strip()[:500] or None
        bad_calls = unsupported_calls(bin_dir_for(workdir))
        if bad_calls:
            exit_code = exit_code or 1
            error = f"gh shim: unsupported call {bad_calls[0]!r} ({len(bad_calls)} total)"
        return RunResult(
            scenario_id=scenario.id,
            vendor=vendor,
            workspace=state,
            transcript_events=events,
            exit_code=exit_code,
            error=error,
            skills_sha=skills_sha,
        )

    def _observe_post_run(
        self,
        scenario: AgentScenario,
        workdir: Path,
        state: WorkspaceState,
        env: Mapping[str, str],
    ) -> WorkspaceState:
        """Resolve the working branch and any PR the agent created."""
        head = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], workdir)
        branch = head.stdout.strip() or state.working_branch
        created_pr: PRRef | None = None
        pr = _run(
            ["gh", "pr", "view", "--json", "number,url,headRefName,title"], workdir, env=env
        )
        if pr.returncode == 0 and pr.stdout.strip():
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

    def _collect_transcript(self, workdir: Path, vendor: str) -> list[TranscriptEvent]:
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

    def __init__(
        self,
        script: dict[tuple[str, str] | str, Outcome | Callable[[Path], Outcome]],
        *,
        skills_root: Path | None = None,
    ) -> None:
        self._script = script
        self._skills_root = Path(skills_root) if skills_root is not None else None

    def run(self, scenario: AgentScenario, vendor: str, workdir: Path) -> RunResult:
        try:
            state = materialize_fixture(scenario, workdir)
        except FixtureError as exc:
            return _fixture_error_result(scenario, vendor, workdir, exc)
        skills_sha: str | None = None
        if self._skills_root is not None:
            try:
                skills_sha = materialize_skills(
                    self._skills_root, scenario.skill_under_test, workdir
                )
            except SkillMaterializationError as exc:
                return RunResult(
                    scenario_id=scenario.id,
                    vendor=vendor,
                    workspace=state,
                    exit_code=1,
                    error=f"skill materialization failed: {exc}",
                )
        outcome = self._script.get((scenario.id, vendor)) or self._script.get(scenario.id)
        if callable(outcome):
            # A callable sees the workspace (e.g. to read the materialized SKILL.md).
            outcome = outcome(workdir)
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
            skills_sha=skills_sha,
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
        events: list[TranscriptEvent] | None = None,
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

    def transcript(self, scenario: AgentScenario, vendor: str) -> list[TranscriptEvent]:
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
