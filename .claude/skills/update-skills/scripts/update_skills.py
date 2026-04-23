#!/usr/bin/env python3
"""Orchestrator for the /update-skills workflow.

Four steps:
  1. Run skills/install.sh to sync canonical skills/ into .claude/skills/
     and .agents/skills/.
  2. Run sync_agents_md.py to regenerate AGENTS.md from CLAUDE.md.
  3. Stage regenerated files. If the staged diff is empty, exit successfully
     without creating an empty commit. Otherwise commit with
     `chore(skills): sync runtime copies`.
  4. Run `git pull --rebase --autostash` then `git push origin <branch>`
     with bounded retry (3 attempts; 1s, 2s backoff).

Exit codes:
  0  success (either no-op or commit + push succeeded)
  1  any step failed (install.sh nonzero, sync_agents_md nonzero,
                      or push retry exhausted)

Outputs:
  - Normal operation: human-readable progress to stderr.
  - Push retry exhausted: machine-readable `UNPUSHED_COMMIT=<sha>` on stdout
    plus human-readable per-attempt summary on stderr.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

COMMIT_MESSAGE = "chore(skills): sync runtime copies"
BACKOFF_SECONDS = (0, 1, 2)  # attempt 1: no wait; attempt 2: 1s; attempt 3: 2s
MAX_PUSH_ATTEMPTS = 3
TRACKED_PATHS = (".claude/skills", ".agents/skills", "AGENTS.md")


class StepFailed(Exception):
    """Raised by a step to abort orchestration with a specific exit code."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _log(msg: str) -> None:
    print(f"[update-skills] {msg}", file=sys.stderr)


def _run(
    cmd: list[str], cwd: Path, *, check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess; return the completed process. Abort on nonzero when check=True."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        stderr = result.stderr if capture else ""
        raise StepFailed(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n{stderr}"
        )
    return result


def step_install(root: Path) -> None:
    """Step 1: run skills/install.sh."""
    _log("step 1/4: running skills/install.sh")
    script = root / "skills" / "install.sh"
    if not script.exists():
        raise StepFailed(f"install.sh not found at {script}")
    _run(
        ["bash", str(script), "--mode", "rsync", "--deps", "none", "--python-tools", "none"],
        cwd=root,
        capture=True,
    )


def step_sync_agents(root: Path) -> None:
    """Step 2: run sync_agents_md.py."""
    _log("step 2/4: regenerating AGENTS.md from CLAUDE.md")
    script = root / "skills" / "update-skills" / "scripts" / "sync_agents_md.py"
    _run(["python3", str(script)], cwd=root, capture=True)


def step_stage_and_commit(root: Path) -> bool:
    """Step 3: stage tracked paths, return True if a commit was created."""
    _log("step 3/4: staging regenerated files")
    existing = [p for p in TRACKED_PATHS if (root / p).exists()]
    if not existing:
        _log("no tracked paths exist yet; nothing to stage")
        return False
    _run(["git", "add", "--", *existing], cwd=root)

    diff = _run(["git", "diff", "--cached", "--quiet"], cwd=root, check=False)
    if diff.returncode == 0:
        _log("no staged changes; skipping commit (no-op)")
        return False

    _run(["git", "commit", "-m", COMMIT_MESSAGE], cwd=root, capture=True)
    _log(f"committed: {COMMIT_MESSAGE}")
    return True


def _current_branch(root: Path) -> str:
    result = _run(["git", "branch", "--show-current"], cwd=root, capture=True)
    return result.stdout.strip()


def _head_sha(root: Path) -> str:
    result = _run(["git", "rev-parse", "HEAD"], cwd=root, capture=True)
    return result.stdout.strip()


def step_push_with_retry(root: Path, *, sleep: "Callable[[float], None]" = time.sleep) -> None:
    """Step 4: push with rebase-on-rejection and bounded retry."""
    _log("step 4/4: pushing with bounded retry")
    branch = _current_branch(root)
    if not branch:
        raise StepFailed("could not resolve current branch")

    attempts: list[dict[str, str]] = []
    for attempt in range(1, MAX_PUSH_ATTEMPTS + 1):
        if attempt > 1:
            wait = BACKOFF_SECONDS[attempt - 1]
            _log(f"waiting {wait}s before attempt {attempt}")
            sleep(wait)
            # Rebase on top of the latest remote state before retrying
            rebase = subprocess.run(
                ["git", "pull", "--rebase", "--autostash", "origin", branch],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            if rebase.returncode != 0:
                attempts.append(
                    {
                        "attempt": str(attempt),
                        "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "error": f"rebase failed: {rebase.stderr.strip()}",
                    }
                )
                continue

        push = subprocess.run(
            ["git", "push", "origin", branch],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if push.returncode == 0:
            sha = _head_sha(root)
            _log(f"pushed {sha[:10]} to origin/{branch} on attempt {attempt}")
            return
        attempts.append(
            {
                "attempt": str(attempt),
                "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "error": push.stderr.strip() or push.stdout.strip(),
            }
        )

    # Exhausted: emit machine-readable UNPUSHED_COMMIT and human summary
    sha = _head_sha(root)
    print(f"UNPUSHED_COMMIT={sha}")
    for entry in attempts:
        _log(f"attempt {entry['attempt']} @ {entry['when']}: {entry['error']}")
    raise StepFailed(f"push retry exhausted after {MAX_PUSH_ATTEMPTS} attempts", exit_code=1)


def orchestrate(root: Path) -> int:
    """Run all four steps; return exit code."""
    try:
        step_install(root)
    except StepFailed as exc:
        _log(f"install.sh failed: {exc}")
        return exc.exit_code
    try:
        step_sync_agents(root)
    except StepFailed as exc:
        _log(f"sync_agents_md failed: {exc}")
        _log("install.sh changes remain staged for manual recovery")
        return exc.exit_code
    try:
        committed = step_stage_and_commit(root)
    except StepFailed as exc:
        _log(f"commit failed: {exc}")
        return exc.exit_code
    if not committed:
        _log("nothing to push; done")
        return 0
    try:
        step_push_with_retry(root)
    except StepFailed as exc:
        _log(f"{exc}")
        return exc.exit_code
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory).",
    )
    args = parser.parse_args(argv)
    return orchestrate(args.root)


if __name__ == "__main__":
    sys.exit(main())
