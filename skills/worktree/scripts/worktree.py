#!/usr/bin/env python3
"""Git worktree lifecycle helper for OpenSpec skills.

Manages worktree creation, teardown, status, detection, heartbeat,
pin/unpin, list, and garbage collection. Outputs machine-parseable
KEY=VALUE lines for shell eval.

Usage:
    python3 "<skill-base-dir>/scripts/worktree.py" setup <change-id> [options]
    python3 "<skill-base-dir>/scripts/worktree.py" teardown <change-id> [options]
    python3 "<skill-base-dir>/scripts/worktree.py" status [<change-id>] [options]
    python3 "<skill-base-dir>/scripts/worktree.py" detect
    python3 "<skill-base-dir>/scripts/worktree.py" heartbeat <change-id> [options]
    python3 "<skill-base-dir>/scripts/worktree.py" list
    python3 "<skill-base-dir>/scripts/worktree.py" pin <change-id> [options]
    python3 "<skill-base-dir>/scripts/worktree.py" unpin <change-id> [options]
    python3 "<skill-base-dir>/scripts/worktree.py" gc [options]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Import the shared environment profile helper. Added to sys.path so the
# import works whether worktree.py is invoked from the main repo, a
# .git-worktrees/ entry, or as a shipped copy under .claude/skills/.
# install.sh syncs skills/shared/ alongside skill dirs (see SHARED_LIBS).
# The ModuleNotFoundError fallback below is defensive — only triggered if
# shared/ is missing from the runtime layout (e.g. an out-of-tree install
# or stripped environment).
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from shared.environment_profile import EnvironmentProfile, detect  # noqa: E402
    from shared import worktree_lifecycle as lifecycle  # noqa: E402
except ModuleNotFoundError:
    from dataclasses import dataclass, field

    @dataclass(frozen=True)
    class EnvironmentProfile:  # type: ignore[no-redef]
        isolation_provided: bool = False
        source: str = "unavailable"
        details: dict = field(default_factory=dict)

    def detect(agent_id: str | None = None, **_kw: object) -> EnvironmentProfile:  # type: ignore[no-redef]
        return EnvironmentProfile()

    lifecycle = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Environment-aware short-circuit
# ---------------------------------------------------------------------------


def _short_circuit_if_isolated(op: str, agent_id: str | None = None) -> EnvironmentProfile | None:
    """Return the detected profile if the caller already has isolation.

    Callers check for a non-None return and emit operation-appropriate
    success output before exiting. A None return means no short-circuit
    applies — proceed with the original behavior.

    Args:
        op: Name of the worktree operation (for diagnostic output).
        agent_id: Optional agent ID to pass to coordinator detection layer.
    """
    profile = detect(agent_id=agent_id)
    if profile.isolation_provided:
        print(
            f"worktree: skipped {op} (isolation_provided=true, source={profile.source})",
            file=sys.stderr,
        )
        return profile
    return None


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def run_git(*args: str, cwd: str | None = None, check: bool = True) -> str:
    """Run a git command and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        # Include git's stderr in the exception so the caller sees the real error
        msg = f"git {' '.join(args)} failed (exit {result.returncode})"
        if result.stderr.strip():
            msg += f": {result.stderr.strip()}"
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            result.stdout,
            result.stderr,
        )
    return result.stdout.strip()


def _git_ref_exists(main_repo: Path, ref: str) -> bool:
    """Return true when a git ref exists in the repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=str(main_repo),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _local_branch_exists(main_repo: Path, branch: str) -> bool:
    return _git_ref_exists(main_repo, f"refs/heads/{branch}")


def _remote_branch_exists(main_repo: Path, branch: str) -> bool:
    return _git_ref_exists(main_repo, f"refs/remotes/origin/{branch}")


def _existing_branch_start_point(main_repo: Path, branch: str) -> str | None:
    """Return the best existing start point for a branch name."""
    if _local_branch_exists(main_repo, branch):
        return branch
    if _remote_branch_exists(main_repo, branch):
        return f"origin/{branch}"
    return None


def _invoking_feature_branch(cwd: str | None, exclude: set[str]) -> str | None:
    """Return the invoking checkout's current branch if it is a viable parent.

    In the coordinated workflow, ``worktree.py setup`` is invoked from the
    feature-branch worktree, so its current branch is the real parent that agent
    branches must start from (its HEAD is the base to preserve). Returns None
    when the checkout is on ``main``, detached, or already on one of the
    ``exclude`` branches (the agent branch itself or the computed parent name),
    leaving the caller to fall back to ``main`` — the correct base for a
    genuinely fresh feature with no prior work.
    """
    if not cwd:
        return None
    try:
        current = (run_git("branch", "--show-current", cwd=cwd) or "").strip()
    except subprocess.CalledProcessError:
        return None
    if not current or current == "main" or current in exclude:
        return None
    return current


def _branch_creation_start_point(
    main_repo: Path,
    change_id: str,
    branch: str,
    agent_id: str | None = None,
    prefix: str | None = None,
    explicit: str | None = None,
    branch_prefix: str | None = None,
    invoking_cwd: str | None = None,
) -> tuple[str, str]:
    """Choose the start point for a newly-created worktree branch.

    Agent branches are integration children, so when the parent feature/session
    branch already exists locally or on origin, the child must start there. This
    prevents merging an agent branch back into the feature branch from dragging
    unrelated commits from main into the feature.
    """
    explicit_branch = (explicit or "").strip()

    existing_same_name = _existing_branch_start_point(main_repo, branch)
    if existing_same_name:
        return existing_same_name, "remote" if existing_same_name.startswith("origin/") else "local"

    if agent_id and branch_prefix != PROTOTYPE_BRANCH_PREFIX:
        parent = resolve_parent_branch(change_id, prefix=prefix)
        parent_start = _existing_branch_start_point(main_repo, parent)
        if parent_start:
            return parent_start, "parent"

        if not explicit_branch:
            # The named parent ref doesn't exist. Fabricating it from main would
            # give the agent branch a stale base and drag main-only commits into
            # the feature PR on merge-back. Prefer the feature branch the operator
            # is actually on (the invoking checkout's HEAD): in the coordinated
            # workflow setup runs from the feature-branch worktree. Fall back to
            # main only when that checkout is on main/detached.
            feature_branch = _invoking_feature_branch(invoking_cwd, exclude={branch, parent})
            base = feature_branch or "main"
            source = "parent-created-from-feature" if feature_branch else "parent-created"
            run_git("branch", parent, base, cwd=str(main_repo))
            print(f"PARENT_BRANCH_CREATED={parent} (from {base})", file=sys.stderr)
            return parent, source

    return "main", "main"


def _adopt_branch_in_isolated_checkout(
    args: argparse.Namespace, cwd: str
) -> tuple[str, str] | None:
    """Move a harness-provided checkout onto the branch setup would have made.

    Cloud/harness worktrees are already filesystem-isolated, so we do not create
    nested ``.git-worktrees``. Some harnesses, however, create that isolated
    checkout from ``main``. For agent-scoped implementation work, that is not a
    valid base: the child branch must start at the feature/session parent.
    """
    main_repo = resolve_main_repo(cwd)
    change_id: str = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)
    prefix: str | None = getattr(args, "prefix", None)
    branch_prefix: str | None = getattr(args, "branch_prefix", None)
    explicit: str | None = getattr(args, "branch", None)
    branch = resolve_branch(
        change_id,
        agent_id,
        prefix,
        explicit=explicit,
        branch_prefix=branch_prefix,
    )
    current_branch = run_git("branch", "--show-current", cwd=cwd)
    override = os.environ.get("OPENSPEC_BRANCH_OVERRIDE", "").strip()
    explicit_branch = (explicit or "").strip()

    if not agent_id and not explicit_branch and not override and branch_prefix is None:
        return current_branch, None

    if current_branch == branch:
        return branch, None

    start_point = _existing_branch_start_point(main_repo, branch)
    if start_point:
        run_git("checkout", "-B", branch, start_point, cwd=cwd)
        return branch, f"existing:{start_point}"

    if agent_id and branch_prefix != PROTOTYPE_BRANCH_PREFIX:
        parent = resolve_parent_branch(change_id, prefix=prefix)
        parent_start = _existing_branch_start_point(main_repo, parent)
        if parent_start is None:
            if explicit_branch:
                # Explicit branch workflows outside OpenSpec feature branches
                # may not have a resolvable parent; keep backward-compatible
                # behavior and create from the current checkout below.
                pass
            else:
                print(
                    f"ERROR: isolated checkout is on '{current_branch}', but agent branch "
                    f"'{branch}' must start from parent feature branch '{parent}', which "
                    "does not exist locally or at origin.",
                    file=sys.stderr,
                )
                print(
                    "Hint: push/fetch the feature branch before dispatching sub-agents, "
                    "or set OPENSPEC_BRANCH_OVERRIDE to the actual feature branch.",
                    file=sys.stderr,
                )
                return None
        else:
            if _local_branch_exists(main_repo, branch):
                run_git("checkout", branch, cwd=cwd)
                return branch, "existing-agent"
            run_git("checkout", "-B", branch, parent_start, cwd=cwd)
            return branch, f"parent:{parent_start}"

    if current_branch:
        run_git("checkout", "-B", branch, cwd=cwd)
        return branch, "current"

    return current_branch, None


def resolve_main_repo(cwd: str | None = None) -> Path:
    """Resolve the main repository path, even from inside a worktree."""
    git_common = run_git("rev-parse", "--git-common-dir", cwd=cwd)
    if git_common == ".git":
        return Path(run_git("rev-parse", "--show-toplevel", cwd=cwd))
    # In a worktree: git-common-dir returns /path/to/main/.git
    main_git = git_common.split("/.git")[0]
    return Path(main_git)


# ---------------------------------------------------------------------------
# Path computation
# ---------------------------------------------------------------------------


def worktree_path(
    main_repo: Path,
    change_id: str,
    agent_id: str | None = None,
    prefix: str | None = None,
    sibling: bool = False,
) -> Path:
    """Compute the worktree path under .git-worktrees/.

    Default patterns:
      .git-worktrees/<change-id>/                        (no agent, no prefix)
      .git-worktrees/<change-id>--<agent-id>/             (agent, no prefix)
      .git-worktrees/<prefix>/<change-id>/               (no agent, prefix)
      .git-worktrees/<prefix>/<change-id>--<agent-id>/    (agent + prefix)

    Sibling patterns (sibling=True — agent worktree placed next to <change-id>
    instead of inside it, mirroring the '--' separator used in branch names):
      .git-worktrees/<change-id>--<agent-id>/            (agent, no prefix)
      .git-worktrees/<prefix>/<change-id>--<agent-id>/   (agent + prefix)

    Agent worktrees are always siblings. A nested checkout would appear as an
    untracked directory in the parent feature checkout and make safe teardown
    impossible. ``sibling`` remains accepted as a compatibility no-op.

    sibling=True with no agent_id is silently a no-op — there is nothing to
    place as a sibling — and falls through to the default change-id path.
    """
    base = main_repo / ".git-worktrees"
    if prefix:
        base = base / prefix

    if sibling and agent_id:
        return base / f"{change_id}--{agent_id}"

    base = base / change_id
    if agent_id:
        base = base / agent_id
    return base


def default_branch(
    change_id: str,
    agent_id: str | None = None,
    prefix: str | None = None,
) -> str:
    """Compute the default branch name.

    Uses '--' separator between change-id and agent-id to avoid a git
    ref storage limitation: git cannot have both ``refs/heads/a/b`` (a
    branch) and ``refs/heads/a/b/c`` (a sub-path) simultaneously.
    Using '/' would make the feature branch ``openspec/<change-id>``
    conflict with agent branches ``openspec/<change-id>/<agent-id>``.

    Patterns:
      openspec/<change-id>                   (no agent, no prefix)
      openspec/<change-id>--<agent-id>       (agent, no prefix)
      <prefix>/<change-id>                   (no agent, prefix)
      <prefix>/<change-id>--<agent-id>       (agent, prefix)
    """
    if prefix:
        base = f"{prefix}/{change_id}"
    else:
        base = f"openspec/{change_id}"
    if agent_id:
        return f"{base}--{agent_id}"
    return base


PROTOTYPE_BRANCH_PREFIX = "prototype"
_VALID_BRANCH_PREFIXES = frozenset({PROTOTYPE_BRANCH_PREFIX})


def resolve_branch(
    change_id: str,
    agent_id: str | None = None,
    prefix: str | None = None,
    explicit: str | None = None,
    env: dict[str, str] | None = None,
    branch_prefix: str | None = None,
) -> str:
    """Resolve the branch name a caller should use, applying override precedence.

    Resolution proceeds in three steps:

    1. **Explicit override** (highest precedence):
       - ``explicit`` — if passed, used verbatim as the final branch and returned
         immediately, even when ``branch_prefix`` is also set. Useful for callers
         that pre-compose their own fully-qualified task branches and need them
         passed through untouched.

    2. **Branch-prefix scheme** (for prototype variants):
       - When ``branch_prefix='prototype'``, the result is
         ``prototype/<change-id>/<agent-id>`` (with '/' separator, not '--').
         The prototype workflow never creates a parent ``prototype/<change-id>``
         branch, so the git ref-storage limitation that forces '--' for the
         openspec/<change-id> case doesn't apply. ``OPENSPEC_BRANCH_OVERRIDE``
         is intentionally ignored here — the operator's session branch governs
         the parent feature branch (see ``resolve_parent_branch``), but the
         variants still need to land on prototype/* so cleanup-feature can
         find and delete them by pattern.

    3. **Base resolution + agent suffix** (the original two-layer logic):
       - ``OPENSPEC_BRANCH_OVERRIDE`` env var — operator-mandated base branch
         (e.g. Claude cloud harness sets ``claude/fix-branch-mismatch-9P9o1``).
         When set, it replaces the ``openspec/<change-id>`` default as the base.
       - ``default_branch`` namespace — ``<prefix>/<change-id>`` or
         ``openspec/<change-id>``.
       - When ``agent_id`` is provided, ``--<agent-id>`` is appended to the base
         (the '--' separator is required because git cannot have both
         ``refs/heads/a/b`` and ``refs/heads/a/b/c`` simultaneously).

    Passing empty/whitespace strings is treated as "not set" and falls through
    to the next layer. Unknown ``branch_prefix`` values raise ``ValueError``;
    argparse blocks them at the CLI layer via ``choices=`` but library callers
    deserve a loud failure too.
    """
    # Explicit caller-composed branch wins verbatim (skips all composition)
    if explicit:
        return explicit

    if branch_prefix is not None and branch_prefix not in _VALID_BRANCH_PREFIXES:
        raise ValueError(
            f"Unknown branch_prefix={branch_prefix!r}. "
            f"Allowed: {sorted(_VALID_BRANCH_PREFIXES)} or None."
        )

    if branch_prefix == PROTOTYPE_BRANCH_PREFIX:
        # Variants under prototype/<change>/<agent>. '/' is safe here because
        # no parent ``prototype/<change>`` ref is ever created.
        if agent_id:
            return f"{PROTOTYPE_BRANCH_PREFIX}/{change_id}/{agent_id}"
        return f"{PROTOTYPE_BRANCH_PREFIX}/{change_id}"

    environ = env if env is not None else os.environ
    override = (environ.get("OPENSPEC_BRANCH_OVERRIDE") or "").strip()

    # Determine the base branch (the parent feature/session branch)
    if override:
        base = override
    elif prefix:
        base = f"{prefix}/{change_id}"
    else:
        base = f"openspec/{change_id}"

    # Append agent-id suffix for parallel disambiguation (same convention as
    # default_branch — see module docstring for the git ref storage rationale).
    if agent_id:
        return f"{base}--{agent_id}"
    return base


def resolve_parent_branch(
    change_id: str,
    prefix: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Resolve the parent (feature/session) branch WITHOUT an agent suffix.

    This is the branch that agent-scoped sub-branches merge back into. Used by
    ``merge_worktrees.py`` and by ``cleanup-feature`` when it needs to refer to
    the feature branch (for ``gh pr merge``, ``git branch -d``, etc.) as
    distinct from its own ``--cleanup`` agent worktree branch.
    """
    return resolve_branch(change_id, agent_id=None, prefix=prefix, env=env)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY_FILENAME = ".registry.json"


def _registry_path(main_repo: Path) -> Path:
    return main_repo / ".git-worktrees" / REGISTRY_FILENAME


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry(main_repo: Path) -> dict[str, Any]:
    """Load and normalize registry v1/v2 without rewriting it."""
    if lifecycle is None:  # pragma: no cover - stripped install guard
        raise RuntimeError("shared.worktree_lifecycle is required")
    return lifecycle.read_registry(main_repo)  # type: ignore[no-any-return]


def save_registry(main_repo: Path, registry: dict[str, Any]) -> None:
    """Write canonical schema v2 under the lifecycle lock."""
    if lifecycle is None:  # pragma: no cover - stripped install guard
        raise RuntimeError("shared.worktree_lifecycle is required")
    lifecycle.write_registry(main_repo, registry)


def find_entry(
    registry: dict[str, Any],
    change_id: str,
    agent_id: str | None = None,
) -> dict[str, Any] | None:
    """Find a registry entry by (change_id, agent_id)."""
    for entry in registry["entries"]:
        if entry["change_id"] == change_id and entry.get("agent_id") == agent_id:
            return entry  # type: ignore[no-any-return]
    return None


def remove_entry(
    registry: dict[str, Any],
    change_id: str,
    agent_id: str | None = None,
) -> bool:
    """Remove a registry entry. Returns True if found and removed."""
    before = len(registry["entries"])
    registry["entries"] = [
        e
        for e in registry["entries"]
        if not (e["change_id"] == change_id and e.get("agent_id") == agent_id)
    ]
    return len(registry["entries"]) < before


# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------


def parse_duration_hours(duration: str) -> float:
    """Parse a duration string like '24h', '48h', '7d' into hours."""
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(h|d|m)$", duration.strip().lower())
    if not m:
        raise ValueError(f"Invalid duration format: {duration!r}. Use e.g. 24h, 7d, 30m")
    value = float(m.group(1))
    unit = m.group(2)
    if unit == "h":
        return value
    if unit == "d":
        return value * 24
    if unit == "m":
        return value / 60
    raise ValueError(f"Unknown unit: {unit}")  # pragma: no cover


def _durability_target(
    main_repo: Path,
    remote: str | None,
    ref: str | None,
) -> dict[str, str] | None:
    """Build a bound durability target without persisting remote credentials."""
    if bool(remote) != bool(ref):
        raise lifecycle.LifecycleError(
            "--durability-remote and --durability-ref must be supplied together"
        )
    if not remote or not ref:
        return None
    urls = run_git("config", "--get-all", f"remote.{remote}.url", cwd=str(main_repo)).splitlines()
    if len(urls) != 1:
        raise lifecycle.LifecycleError(
            f"durability remote {remote!r} must have exactly one fetch URL"
        )
    return lifecycle.make_durability_target(remote, ref, urls[0])


def _compatibility_entry(
    *,
    change_id: str,
    agent_id: str | None,
    branch: str,
    wt_path: Path,
    created_at: str,
    retained: bool,
    durability_target: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "change_id": change_id,
        "agent_id": agent_id,
        "branch": branch,
        "worktree_path": str(wt_path),
        "created_at": created_at,
        "entry_generation": uuid.uuid4().hex,
        "setup_id": None,
        "durability_target": durability_target,
        "last_heartbeat": created_at,
        "retained": retained,
        "retention_reason": "prototype" if retained else None,
        "recovery_required": False,
        "recovery_reason": None,
        "recovery_context": None,
        "activity_lease": None,
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_setup(args: argparse.Namespace) -> int:
    """Create a worktree for the given change-id.

    Branch resolution precedence (highest to lowest):
      1. ``--branch`` CLI flag (explicit caller override)
      2. ``OPENSPEC_BRANCH_OVERRIDE`` environment variable (operator mandate,
         e.g. when the Claude cloud harness injects a specific branch name)
      3. ``default_branch(change_id, agent_id, prefix)`` — the computed default

    The env var lets operator-mandated branches flow through to every caller of
    ``worktree.py setup`` without each skill needing to know about the override.

    When ``EnvironmentProfile.detect()`` reports ``isolation_provided=True``
    (e.g. a cloud harness ephemeral container), setup short-circuits: it
    emits ``WORKTREE_PATH`` and ``WORKTREE_BRANCH`` pointing at the
    current checkout and skips ``.git-worktrees/`` creation entirely.
    """
    if _short_circuit_if_isolated("setup", agent_id=getattr(args, "agent_id", None)):
        # Emit the in-place checkout values so downstream `eval` + `cd` is a
        # no-op. If the harness created this checkout from main, move it onto
        # the branch setup would have created locally before returning.
        cwd = os.getcwd()
        toplevel = run_git("rev-parse", "--show-toplevel", cwd=cwd)
        adopted = _adopt_branch_in_isolated_checkout(args, cwd)
        if adopted is None:
            return 1
        current_branch, adopted_source = adopted
        print(f"WORKTREE_PATH={toplevel}")
        print(f"WORKTREE_BRANCH={current_branch}")
        if adopted_source:
            print(f"BRANCH_ADOPTED_FROM={adopted_source}", file=sys.stderr)
        print("ISOLATION_PROVIDED=true", file=sys.stderr)
        return 0

    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    lifecycle.read_registry(main_repo)
    change_id: str = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)
    prefix: str | None = args.prefix
    branch_prefix: str | None = getattr(args, "branch_prefix", None)
    sibling: bool = bool(getattr(args, "sibling", False))

    branch = resolve_branch(
        change_id,
        agent_id,
        prefix,
        explicit=args.branch,
        branch_prefix=branch_prefix,
    )
    if not args.branch and branch != default_branch(change_id, agent_id, prefix):
        # Emit diagnostic so operators can confirm which override took effect
        source = "branch-prefix" if branch_prefix else "env"
        print(f"BRANCH_OVERRIDE_SOURCE={source}", file=sys.stderr)
        print(f"BRANCH_OVERRIDE_VALUE={branch}", file=sys.stderr)

    # Worktree path layout is unaffected by branch_prefix — prototype variants
    # live at .git-worktrees/<change>/<agent>/, the same shape that work-package
    # agents use. The prototype namespace lives only in the branch name.
    # `sibling=True` opts agent worktrees into a peer path next to the change
    # dir; see worktree_path() docstring for the rationale.
    wt_path = worktree_path(
        main_repo, change_id, agent_id, prefix, sibling=sibling or agent_id is not None
    )

    # Check if already in the target worktree
    try:
        current_toplevel = Path(run_git("rev-parse", "--show-toplevel", cwd=cwd))
        if current_toplevel == wt_path:
            print(f"WORKTREE_PATH={wt_path}")
            print("ALREADY_EXISTS=true", file=sys.stderr)
            return 0
    except subprocess.CalledProcessError:
        pass

    # Create parent directory
    wt_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure we have latest main
    run_git("fetch", "origin", "main", cwd=str(main_repo), check=False)

    # Create branch if it doesn't exist. Agent-scoped branches are created from
    # their parent feature branch when available, not from main.
    if not _local_branch_exists(main_repo, branch):
        start_point, start_source = _branch_creation_start_point(
            main_repo,
            change_id,
            branch,
            agent_id=agent_id,
            prefix=prefix,
            explicit=args.branch,
            branch_prefix=branch_prefix,
            invoking_cwd=cwd,
        )
        run_git("branch", branch, start_point, cwd=str(main_repo))
        print(f"BRANCH_CREATED={branch}", file=sys.stderr)
        print(f"BRANCH_START_POINT={start_point}", file=sys.stderr)
        print(f"BRANCH_START_SOURCE={start_source}", file=sys.stderr)

    # Prune stale worktree entries (e.g., directory was deleted but git still tracks it)
    run_git("worktree", "prune", cwd=str(main_repo), check=False)

    # Create worktree (or reuse)
    already_exists = False
    if wt_path.is_dir():
        already_exists = True
        print("ALREADY_EXISTS=true", file=sys.stderr)
    else:
        try:
            run_git("worktree", "add", str(wt_path), branch, cwd=str(main_repo))
        except subprocess.CalledProcessError as exc:
            # Surface git's actual error message for diagnosis
            stderr = exc.stderr.strip() if exc.stderr else ""
            print(f"ERROR: git worktree add failed: {stderr}", file=sys.stderr)
            raise
        print("CREATED=true", file=sys.stderr)

    now = _utcnow_iso()
    # Prototype worktrees auto-pin per D4: they must survive the 24h GC timer
    # because /cleanup-feature is the only thing that should delete them, and
    # the gap between dispatch and cleanup can span days while humans iterate.
    auto_pin = branch_prefix == PROTOTYPE_BRANCH_PREFIX
    target = _durability_target(
        main_repo,
        getattr(args, "durability_remote", None),
        getattr(args, "durability_ref", None),
    )

    def publish_compatibility(registry: dict[str, Any]) -> dict[str, Any]:
        existing = find_entry(registry, change_id, agent_id)
        if existing:
            if existing["branch"] != branch or existing["worktree_path"] != str(wt_path):
                raise lifecycle.RecoveryRequired("existing entry identity differs from setup")
            existing["last_heartbeat"] = now
            if auto_pin:
                existing["retained"] = True
                existing["retention_reason"] = "prototype"
            return existing
        entry = _compatibility_entry(
            change_id=change_id,
            agent_id=agent_id,
            branch=branch,
            wt_path=wt_path,
            created_at=now,
            retained=auto_pin,
            durability_target=target,
        )
        registry["entries"].append(entry)
        return entry

    entry = lifecycle.mutate_registry(main_repo, publish_compatibility)
    if auto_pin:
        print("AUTO_PINNED=true (branch-prefix=prototype)", file=sys.stderr)

    # Bootstrap the worktree (copy .env, install deps, sync skills)
    bootstrapped = False
    if not args.no_bootstrap and not already_exists:
        # Resolve the co-installed helper from this skill's own directory.  In
        # consumers the skills may live under .claude/skills or .agents/skills,
        # and the main repository need not contain a canonical skills/ tree.
        bootstrap_script = _installed_bootstrap_script()
        if bootstrap_script.is_file():
            print("Bootstrapping worktree...", file=sys.stderr)
            env = os.environ.copy()
            if agent_id:
                env["AGENT_ID"] = agent_id
            result = subprocess.run(
                ["bash", str(bootstrap_script), str(wt_path), str(main_repo)],
                capture_output=False,
                check=False,
                env=env,
            )
            bootstrapped = result.returncode == 0
        else:
            print("No bootstrap script found, skipping", file=sys.stderr)

    if getattr(args, "json_output", False):
        print(
            json.dumps(
                {
                    "change_id": change_id,
                    "agent_id": agent_id,
                    "branch": branch,
                    "worktree_path": str(wt_path),
                    "entry_generation": entry["entry_generation"],
                    "durability_target": entry["durability_target"],
                    "created": not already_exists,
                },
                sort_keys=True,
            )
        )
    else:
        print(f"WORKTREE_PATH={wt_path}")
        print(f"WORKTREE_BRANCH={branch}")
        print(f"ENTRY_GENERATION={entry['entry_generation']}")
        print(f"BOOTSTRAPPED={'true' if bootstrapped else 'false'}")
    return 0


def _installed_bootstrap_script() -> Path:
    """Return the bootstrap script co-installed with this module."""
    return Path(__file__).resolve().with_name("worktree-bootstrap.sh")


def _deinit_submodules(wt_path: Path) -> None:
    """Deinit any initialized submodules inside a worktree.

    This is the clean path before ``git worktree remove``. Git refuses to
    remove worktrees that have initialized submodule checkouts, so we
    deinit them first. If deinit fails (e.g., no submodules), we silently
    continue — the caller will handle removal errors.
    """
    try:
        run_git(
            "submodule",
            "deinit",
            "-f",
            "--all",
            cwd=str(wt_path),
            check=True,
        )
        print("Deinitialized submodules in worktree", file=sys.stderr)
    except subprocess.CalledProcessError:
        pass  # No submodules or deinit failed — proceed to removal


_SUBMODULE_REMOVE_ERROR = "working trees containing submodules cannot be moved or removed"


def cmd_teardown(args: argparse.Namespace) -> int:
    """Remove a worktree for the given change-id.

    If the worktree contains initialized submodules, deinit them first.
    If plain removal still fails with the git-specific "working trees
    containing submodules" error, fall back to ``--force``. Other removal
    errors (dirty tree, conflicting edits) are NOT force-overridden unless
    ``--force`` is explicitly passed.

    ``--force``: Remove the registry entry and best-effort ``git worktree
    remove`` even if the worktree path is dirty, missing, or already deleted.
    Used by ``POST /agents/{id}/kick`` to clear stale entries regardless of
    worktree state.

    Short-circuits to a silent no-op when the caller already has
    filesystem isolation (see ``EnvironmentProfile.detect``).
    """
    if _short_circuit_if_isolated("teardown", agent_id=getattr(args, "agent_id", None)):
        print("REMOVED=skipped")
        return 0

    if bool(getattr(args, "force", False)):
        print(
            "ERROR: teardown --force is no longer an automatic disposal path; "
            "use recovery force-teardown with exact generation and confirmations",
            file=sys.stderr,
        )
        return 1

    fence = (
        getattr(args, "owner", None),
        getattr(args, "lease_id", None),
        getattr(args, "controller_instance_id", None),
        getattr(args, "entry_generation", None),
    )
    if any(fence):
        if not all(fence):
            print(
                "ERROR: teardown requires the complete owner/lease/controller/generation fence",
                file=sys.stderr,
            )
            return 1
        return _cmd_fenced_teardown(args)

    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id: str = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)
    prefix: str | None = args.prefix
    sibling: bool = bool(getattr(args, "sibling", False))
    force = False

    wt_path = worktree_path(
        main_repo, change_id, agent_id, prefix, sibling=sibling or agent_id is not None
    )

    # Tolerate setups that created the worktree in the OPPOSITE layout.
    # Without this, an operator who set up nested but tears down with
    # --sibling (or vice-versa) would get "No worktree found" and have to
    # manually clean up. Search for the alternate layout when the primary
    # path is missing.
    if not wt_path.is_dir() and agent_id:
        alt_path = worktree_path(
            main_repo,
            change_id,
            agent_id,
            prefix,
            sibling=False,
        )
        if alt_path.is_dir():
            wt_path = alt_path

    if not wt_path.is_dir():
        if force:
            # --force: registry entry may still exist even if the worktree
            # directory is gone (e.g. after a manual rm). Clear it.
            registry = load_registry(main_repo)
            remove_entry(registry, change_id, agent_id)
            save_registry(main_repo, registry)
            print("REMOVED=true")
            print(f"REMOVED_PATH={wt_path}")
            return 0
        print(
            f"No worktree found for {change_id}" + (f" (agent: {agent_id})" if agent_id else ""),
            file=sys.stderr,
        )
        print("REMOVED=false")
        return 1

    # Deinit submodules first — the clean path when it works
    _deinit_submodules(wt_path)

    # Must run from main repo to remove worktree
    try:
        git_remove_args = ["worktree", "remove"]
        if force:
            git_remove_args.append("--force")
        git_remove_args.append(str(wt_path))
        run_git(*git_remove_args, cwd=str(main_repo))
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        if _SUBMODULE_REMOVE_ERROR in stderr:
            # Submodule metadata persists despite deinit — safe to force
            # because teardown only runs after the worktree's branch is
            # already pushed/merged.
            print(
                f"Plain removal blocked by submodule metadata; falling back to --force: {stderr}",
                file=sys.stderr,
            )
            run_git(
                "worktree",
                "remove",
                "--force",
                str(wt_path),
                cwd=str(main_repo),
            )
        elif force:
            # --force: log but continue to clear the registry entry
            print(
                f"git worktree remove --force failed (ignored by --force): {stderr}",
                file=sys.stderr,
            )
        else:
            raise  # Other errors deserve operator attention

    # Update registry
    registry = load_registry(main_repo)
    remove_entry(registry, change_id, agent_id)
    save_registry(main_repo, registry)

    print("REMOVED=true")
    print(f"REMOVED_PATH={wt_path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """List active worktrees or check a specific one."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id: str | None = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)

    if change_id:
        if agent_id:
            # Check specific agent worktree
            wt_path = worktree_path(main_repo, change_id, agent_id, sibling=True)
            if not wt_path.is_dir():
                wt_path = worktree_path(main_repo, change_id, agent_id, sibling=False)
            if wt_path.is_dir():
                print("EXISTS=true")
                print(f"WORKTREE_PATH={wt_path}")
            else:
                print("EXISTS=false")
                return 1
        else:
            # Check change-level (single agent or list agents)
            wt_path = worktree_path(main_repo, change_id)
            if wt_path.is_dir():
                print("EXISTS=true")
                print(f"WORKTREE_PATH={wt_path}")
            else:
                # Check if any agent worktrees exist under this change
                change_dir = main_repo / ".git-worktrees" / change_id
                if change_dir.is_dir():
                    agents = [d.name for d in change_dir.iterdir() if d.is_dir()]
                    if agents:
                        print("EXISTS=true")
                        print(f"WORKTREE_PATH={change_dir}")
                        print(f"AGENTS={','.join(agents)}")
                    else:
                        print("EXISTS=false")
                        return 1
                else:
                    print("EXISTS=false")
                    return 1
    else:
        output = run_git("worktree", "list", cwd=str(main_repo))
        print(output)
    return 0


def cmd_detect(_args: argparse.Namespace) -> int:
    """Detect if running in a worktree and output context variables."""
    cwd = os.getcwd()
    try:
        git_common = run_git("rev-parse", "--git-common-dir", cwd=cwd)
    except subprocess.CalledProcessError:
        print("IN_WORKTREE=false")
        print(f"MAIN_REPO={cwd}")
        print("OPENSPEC_PATH=openspec")
        return 0

    if git_common == ".git":
        main_repo = run_git("rev-parse", "--show-toplevel", cwd=cwd)
        print("IN_WORKTREE=false")
        print(f"MAIN_REPO={main_repo}")
        print("OPENSPEC_PATH=openspec")
    else:
        main_git = git_common.split("/.git")[0]
        print("IN_WORKTREE=true")
        print(f"MAIN_REPO={main_git}")
        print(f"OPENSPEC_PATH={main_git}/openspec")

    return 0


def cmd_heartbeat(args: argparse.Namespace) -> int:
    """Update the last_heartbeat timestamp for a registered worktree.

    No-op when the caller already has filesystem isolation.
    """
    if _short_circuit_if_isolated("heartbeat", agent_id=getattr(args, "agent_id", None)):
        return 0

    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id: str = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)

    when = lifecycle.utc_now()

    def heartbeat(registry: dict[str, Any]) -> None:
        entry = find_entry(registry, change_id, agent_id)
        if entry is None:
            raise lifecycle.LifecycleError(
                f"No registry entry for {change_id}" + (f" (agent: {agent_id})" if agent_id else "")
            )
        lease = entry.get("activity_lease")
        if lease is not None:
            if lease["phase"] != "LEGACY" or lease["controller_instance_id"] is not None:
                raise lifecycle.FenceConflict(
                    "heartbeat cannot renew a v2 automatic lease; use lease renew"
                )
            if (
                getattr(args, "owner", None) != lease["owner"]
                or getattr(args, "lease_id", None) != lease["lease_id"]
            ):
                raise lifecycle.FenceConflict(
                    "legacy heartbeat requires its exact synthetic owner and lease id"
                )
            lease["last_heartbeat"] = when.isoformat()
            lease["expires_at"] = (when + timedelta(seconds=3600)).isoformat()
        entry["last_heartbeat"] = when.isoformat()

    try:
        lifecycle.mutate_registry(main_repo, heartbeat)
    except lifecycle.LifecycleError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List all registered worktrees with staleness and pin indicators."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    registry = load_registry(main_repo)

    json_output = getattr(args, "json_output", False)
    now = datetime.now(timezone.utc)
    stale_threshold_hours = 1.0

    if json_output:
        out = []
        for entry in registry["entries"]:
            heartbeat = entry.get("last_heartbeat") or entry.get("created_at")
            hb = datetime.fromisoformat(heartbeat)
            age_hours = (now - hb).total_seconds() / 3600
            out.append(
                {
                    "change_id": entry["change_id"],
                    "agent_id": entry.get("agent_id"),
                    "branch": entry["branch"],
                    "worktree_path": entry["worktree_path"],
                    "last_heartbeat": entry["last_heartbeat"],
                    "pinned": bool(entry.get("retained")),
                    "retained": bool(entry.get("retained")),
                    "is_stale": age_hours > stale_threshold_hours,
                    "age_hours": round(age_hours, 2),
                }
            )
        print(json.dumps(out, indent=2))
        return 0

    if not registry["entries"]:
        print("No active worktrees registered.")
        return 0

    # Header
    print(f"{'CHANGE_ID':<30} {'AGENT_ID':<15} {'BRANCH':<40} {'STATUS':<20} {'PATH'}")
    print("-" * 130)

    for entry in registry["entries"]:
        heartbeat = entry.get("last_heartbeat") or entry.get("created_at")
        hb = datetime.fromisoformat(heartbeat)
        age_hours = (now - hb).total_seconds() / 3600
        status_parts = []
        if entry.get("retained"):
            status_parts.append("[retained]")
        if age_hours > stale_threshold_hours:
            status_parts.append(f"[stale {age_hours:.1f}h]")
        else:
            status_parts.append("[active]")
        status = " ".join(status_parts)

        print(
            f"{entry['change_id']:<30} "
            f"{(entry.get('agent_id') or '-'):<15} "
            f"{entry['branch']:<40} "
            f"{status:<20} "
            f"{entry['worktree_path']}"
        )

    return 0


def cmd_pin(args: argparse.Namespace) -> int:
    """Mark a worktree as protected from garbage collection.

    No-op when the caller already has filesystem isolation.
    """
    if _short_circuit_if_isolated("pin", agent_id=getattr(args, "agent_id", None)):
        return 0

    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id: str = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)

    try:
        lifecycle.set_retention(main_repo, change_id, agent_id, reason="compatibility-pin")
    except lifecycle.LifecycleError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(f"Pinned: {change_id}" + (f"/{agent_id}" if agent_id else ""), file=sys.stderr)
    return 0


def cmd_unpin(args: argparse.Namespace) -> int:
    """Remove garbage collection protection from a worktree.

    No-op when the caller already has filesystem isolation.
    """
    if _short_circuit_if_isolated("unpin", agent_id=getattr(args, "agent_id", None)):
        return 0

    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id: str = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)

    try:
        lifecycle.clear_retention(main_repo, change_id, agent_id)
    except lifecycle.LifecycleError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(f"Unpinned: {change_id}" + (f"/{agent_id}" if agent_id else ""), file=sys.stderr)
    return 0


def cmd_resolve_branch(args: argparse.Namespace) -> int:
    """Print the resolved branch for a change-id without creating a worktree.

    Branch resolution precedence (same as ``cmd_setup``):
      1. ``--branch`` explicit override
      2. Registry entry for (change_id, agent_id) if one exists — preferred,
         because this reflects what was ACTUALLY used at setup time
      3. ``OPENSPEC_BRANCH_OVERRIDE`` env var composed with ``--agent-id`` suffix
      4. ``default_branch(change_id, agent_id, prefix)``

    With ``--parent``, the agent suffix is stripped and the parent (feature /
    session) branch is returned instead. This is what ``cleanup-feature`` uses
    to target ``gh pr merge`` and ``git branch -d`` at the feature branch
    rather than its own ``--cleanup`` worktree sub-branch.

    Shell callers should ``eval`` the output to get ``BRANCH=<value>`` exported.
    """
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id: str = args.change_id
    agent_id: str | None = getattr(args, "agent_id", None)
    prefix: str | None = args.prefix
    want_parent: bool = getattr(args, "parent", False)

    # --parent means "ignore agent_id, give me the feature/session branch"
    lookup_agent_id: str | None = None if want_parent else agent_id

    # Registry wins when present — it records the truth of what setup used.
    branch: str | None = None
    source = "default"
    if args.branch:
        branch = args.branch
        source = "explicit"
    else:
        registry = load_registry(main_repo)
        entry = find_entry(registry, change_id, lookup_agent_id)
        if entry and entry.get("branch"):
            branch = entry["branch"]
            source = "registry"
        else:
            # Fall back to the same precedence cmd_setup would apply
            branch = resolve_branch(change_id, lookup_agent_id, prefix)
            source = "env" if os.environ.get("OPENSPEC_BRANCH_OVERRIDE", "").strip() else "default"

    print(f"BRANCH={branch}")
    print(f"BRANCH_SOURCE={source}")
    return 0


def cmd_gc(args: argparse.Namespace) -> int:
    """Remove stale worktrees based on heartbeat age and pin status.

    No-op when the caller already has filesystem isolation — the
    ephemeral container/harness manages its own lifecycle.
    """
    if _short_circuit_if_isolated("gc", agent_id=getattr(args, "agent_id", None)):
        return 0

    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    force: bool = args.force
    stale_hours = parse_duration_hours(args.stale_after)

    return _locked_gc(main_repo, force=force, stale_hours=stale_hours)


def _locked_gc(main_repo: Path, *, force: bool, stale_hours: float) -> int:
    """Collect compatibility entries while excluding fenced lifecycle state."""
    now = datetime.now(timezone.utc)
    removed: list[str] = []
    with lifecycle.registry_lock(main_repo, exclusive=True):
        registry = lifecycle._read_unlocked(main_repo)
        kept: list[dict[str, Any]] = []
        for entry in registry["entries"]:
            # Automatic setup receipts, every lease (including expired), and
            # recovery quarantine are never generic-GC candidates. Expiry is
            # coordination state, not deletion authority.
            if (
                entry.get("setup_id") is not None
                or entry.get("activity_lease") is not None
                or entry.get("recovery_required")
            ):
                kept.append(entry)
                continue
            heartbeat = entry.get("last_heartbeat") or entry.get("created_at")
            parsed = lifecycle.parse_timestamp(heartbeat)
            if parsed is None:
                kept.append(entry)
                continue
            age_hours = (now - parsed).total_seconds() / 3600
            wt = Path(entry["worktree_path"])
            if age_hours <= stale_hours:
                kept.append(entry)
                continue
            if entry.get("retained") and not force:
                print(f"Skipping retained: {entry['change_id']}", file=sys.stderr)
                kept.append(entry)
                continue
            if wt.is_dir():
                try:
                    run_git("worktree", "remove", str(wt), cwd=str(main_repo))
                except subprocess.CalledProcessError:
                    try:
                        run_git("worktree", "remove", "--force", str(wt), cwd=str(main_repo))
                    except subprocess.CalledProcessError as exc:
                        print(f"Failed to remove {wt}: {exc}", file=sys.stderr)
                        kept.append(entry)
                        continue
            removed.append(str(wt))
        registry["entries"] = kept
        lifecycle._write_unlocked(main_repo, registry)
    print(f"REMOVED_COUNT={len(removed)}")
    if removed:
        print(f"REMOVED_PATHS={','.join(removed)}")
    return 0

    # Legacy implementation retained below for source-level compatibility;
    # all v2 execution returns through _locked_gc above.
    registry = load_registry(main_repo)
    now = datetime.now(timezone.utc)
    removed: list[str] = []
    kept: list[dict[str, Any]] = []

    for entry in registry["entries"]:
        heartbeat = entry.get("last_heartbeat") or entry.get("created_at")
        hb = datetime.fromisoformat(heartbeat)
        age_hours = (now - hb).total_seconds() / 3600
        wt = Path(entry["worktree_path"])

        # Orphaned registry entry (directory gone) — always remove
        if not wt.is_dir():
            print(
                f"Removing orphaned entry: {entry['change_id']}"
                + (f"/{entry.get('agent_id', '')}" if entry.get("agent_id") else ""),
                file=sys.stderr,
            )
            removed.append(str(wt))
            continue

        # Not stale — keep
        if age_hours <= stale_hours:
            kept.append(entry)
            continue

        # Pinned and not forced — keep
        if entry.get("retained") and not force:
            print(
                f"Skipping pinned: {entry['change_id']}"
                + (f"/{entry.get('agent_id', '')}" if entry.get("agent_id") else ""),
                file=sys.stderr,
            )
            kept.append(entry)
            continue

        # Stale (and unpinned, or forced) — remove
        label = entry["change_id"] + (
            f"/{entry.get('agent_id', '')}" if entry.get("agent_id") else ""
        )
        print(f"Removing stale worktree: {label} (age: {age_hours:.1f}h)", file=sys.stderr)
        try:
            run_git("worktree", "remove", str(wt), cwd=str(main_repo))
        except subprocess.CalledProcessError:
            # Force remove if normal remove fails
            try:
                run_git("worktree", "remove", "--force", str(wt), cwd=str(main_repo))
            except subprocess.CalledProcessError as e:
                print(f"Failed to remove {wt}: {e}", file=sys.stderr)
                kept.append(entry)
                continue

        removed.append(str(wt))

        # Prune branch if fully merged
        branch = entry["branch"]
        try:
            run_git(
                "branch",
                "-d",
                branch,
                cwd=str(main_repo),
                check=True,
            )
            print(f"Pruned merged branch: {branch}", file=sys.stderr)
        except subprocess.CalledProcessError:
            pass  # Branch not fully merged or doesn't exist — leave it

    registry["entries"] = kept
    save_registry(main_repo, registry)

    print(f"REMOVED_COUNT={len(removed)}")
    if removed:
        print(f"REMOVED_PATHS={','.join(removed)}")
    return 0


# ---------------------------------------------------------------------------
# Registry-v2 lease and recovery commands
# ---------------------------------------------------------------------------


def _emit(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, sort_keys=True)
        elif value is None:
            value = ""
        elif isinstance(value, bool):
            value = str(value).lower()
        print(f"{key.upper()}={value}")


def _short_circuit_json(args: argparse.Namespace, operation: str) -> int | None:
    if not _short_circuit_if_isolated(operation, getattr(args, "agent_id", None)):
        return None
    _emit(
        {"operation": operation, "skipped": True, "isolation_provided": True},
        json_output=bool(getattr(args, "json_output", False)),
    )
    return 0


def _target_observation(main_repo: Path, entry: dict[str, Any]) -> str:
    target = entry.get("durability_target")
    if target is None:
        raise lifecycle.RecoveryRequired("durability target is not bound")
    remote = target["remote_name"]
    urls = run_git("config", "--get-all", f"remote.{remote}.url", cwd=str(main_repo)).splitlines()
    if (
        len(urls) != 1
        or lifecycle.remote_url_digest(urls[0]) != target["canonical_remote_url_sha256"]
    ):
        raise lifecycle.RecoveryRequired("durability remote identity changed")
    expected_prefix = f"refs/remotes/{remote}/"
    if not target["ref_name"].startswith(expected_prefix):
        raise lifecycle.RegistryCorrupt("durability remote/ref mismatch")
    run_git("fetch", remote, cwd=str(main_repo))
    return run_git("rev-parse", target["ref_name"], cwd=str(main_repo))


def _checkout_is_clean(entry: dict[str, Any]) -> bool:
    path = Path(entry["worktree_path"])
    if not path.is_dir():
        return True
    return not run_git(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        cwd=str(path),
    )


def _head_is_durable(entry: dict[str, Any], observed_tip: str) -> bool:
    path = Path(entry["worktree_path"])
    if not path.is_dir():
        return True
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "HEAD", observed_tip],
        cwd=str(path),
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _evidence_state(main_repo: Path, entry: dict[str, Any], lease: dict[str, Any]) -> str:
    try:
        evidence = lifecycle.read_process_evidence(
            main_repo,
            change_id=entry["change_id"],
            agent_id=entry.get("agent_id"),
            entry_generation=entry["entry_generation"],
            lease_id=lease["lease_id"],
            owner=lease["owner"],
            controller_instance_id=lease["controller_instance_id"],
        )
    except lifecycle.RecoveryRequired:
        return "indeterminate"
    return lifecycle.classify_process_evidence(evidence)


def _quarantine_exact(
    main_repo: Path,
    change_id: str,
    agent_id: str | None,
    *,
    source: str,
    reason: str,
) -> None:
    now = lifecycle.utc_now()

    def apply(registry: dict[str, Any]) -> None:
        entry = lifecycle.find_entry(registry, change_id, agent_id)
        if entry is None:
            raise lifecycle.LifecycleError("registry entry disappeared")
        lifecycle._quarantine(entry, source=source, reason=reason, now=now, clear_lease=True)

    lifecycle.mutate_registry(main_repo, apply)


def _assess_takeover(main_repo: Path, entry: dict[str, Any]) -> None:
    lease = entry.get("activity_lease")
    if lease is None:
        _quarantine_exact(
            main_repo,
            entry["change_id"],
            entry.get("agent_id"),
            source="legacy-adoption",
            reason="pre-existing-unleased-state",
        )
        raise lifecycle.RecoveryRequired("pre-existing unleased state was quarantined")
    observed = _target_observation(main_repo, entry)
    if not _checkout_is_clean(entry) or not _head_is_durable(entry, observed):
        _quarantine_exact(
            main_repo,
            entry["change_id"],
            entry.get("agent_id"),
            source="expired-takeover",
            reason="dirty-or-non-durable-checkout",
        )
        raise lifecycle.RecoveryRequired("unsafe expired checkout was quarantined")
    state = _evidence_state(main_repo, entry, lease)
    if state != "stale":
        _quarantine_exact(
            main_repo,
            entry["change_id"],
            entry.get("agent_id"),
            source="expired-takeover",
            reason=f"process-evidence-{state}",
        )
        raise lifecycle.RecoveryRequired(f"process evidence is {state}; checkout quarantined")


def cmd_setup_and_acquire(args: argparse.Namespace) -> int:
    short = _short_circuit_json(args, "setup-and-acquire")
    if short is not None:
        return short
    main_repo = resolve_main_repo(os.getcwd())
    change_id = args.change_id
    agent_id = args.agent_id
    branch = resolve_branch(change_id, agent_id)
    wt_path = worktree_path(main_repo, change_id, agent_id, sibling=agent_id is not None)
    registry = lifecycle.read_registry(main_repo)
    completed = lifecycle.find_entry(registry, change_id, agent_id)
    if completed is not None and completed.get("setup_id") == args.setup_id:
        stored = completed.get("durability_target") or {}
        if (
            stored.get("remote_name") != args.durability_remote
            or stored.get("ref_name") != args.durability_ref
        ):
            raise lifecycle.FenceConflict("completed setup durability identity differs")
        replay = lifecycle.completed_setup_replay(
            main_repo,
            setup_id=args.setup_id,
            change_id=change_id,
            agent_id=agent_id,
            entry_generation=completed["entry_generation"],
            durability_target=completed["durability_target"],
            owner=args.owner,
            lease_id=args.lease_id,
            controller_instance_id=args.controller_instance_id,
        )
        _emit({**replay, "acquired": True}, json_output=args.json_output)
        return 0
    target = _durability_target(main_repo, args.durability_remote, args.durability_ref)
    assert target is not None
    run_git("fetch", args.durability_remote, cwd=str(main_repo))
    observed_tip = run_git("rev-parse", target["ref_name"], cwd=str(main_repo))
    reservation = lifecycle.find_reservation(registry, args.setup_id)
    generation = reservation["entry_generation"] if reservation else uuid.uuid4().hex
    intent = {
        "owner": args.owner,
        "lease_id": args.lease_id,
        "controller_instance_id": args.controller_instance_id,
        "session_id": args.session_id,
        "phase": args.phase,
        "reason": args.reason,
        "lifecycle_mode": args.mode,
        "ttl_seconds": args.ttl_seconds,
    }
    reservation = lifecycle.reserve_setup(
        main_repo,
        setup_id=args.setup_id,
        change_id=change_id,
        agent_id=agent_id,
        branch=branch,
        worktree_path=str(wt_path),
        entry_generation=generation,
        durability_target=target,
        lease_intent=intent,
        ttl_seconds=args.setup_reservation_ttl_seconds,
    )
    if not _local_branch_exists(main_repo, branch):
        start, _source = _branch_creation_start_point(
            main_repo,
            change_id,
            branch,
            agent_id=agent_id,
            prefix=None,
            explicit=None,
            branch_prefix=None,
            invoking_cwd=os.getcwd(),
        )
        run_git("branch", branch, start, cwd=str(main_repo))
    run_git("worktree", "prune", cwd=str(main_repo), check=False)
    if not wt_path.is_dir():
        wt_path.parent.mkdir(parents=True, exist_ok=True)
        run_git("worktree", "add", str(wt_path), branch, cwd=str(main_repo))
    reservation = lifecycle.advance_reservation(
        main_repo, args.setup_id, generation, "checkout-created"
    )
    if not _head_is_durable(
        {"worktree_path": str(wt_path)},
        observed_tip,
    ):
        raise lifecycle.RecoveryRequired(
            "new checkout HEAD is not reachable from the bound durability target"
        )
    lifecycle.write_process_evidence(
        main_repo,
        change_id=change_id,
        agent_id=agent_id,
        entry_generation=generation,
        lease_id=args.lease_id,
        owner=args.owner,
        controller_instance_id=args.controller_instance_id,
    )
    lifecycle.advance_reservation(main_repo, args.setup_id, generation, "evidence-created")
    entry = lifecycle.publish_reservation(main_repo, args.setup_id, generation)
    _emit({**entry, "acquired": True}, json_output=args.json_output)
    return 0


def cmd_lease_acquire(args: argparse.Namespace) -> int:
    short = _short_circuit_json(args, "lease-acquire")
    if short is not None:
        return short
    main_repo = resolve_main_repo(os.getcwd())
    entry = lifecycle.find_entry(lifecycle.read_registry(main_repo), args.change_id, args.agent_id)
    if entry is None:
        raise lifecycle.LifecycleError("registry entry not found")
    lease = entry["activity_lease"]
    if lease is None or not lifecycle.lease_is_live(lease):
        _assess_takeover(main_repo, entry)
    result = lifecycle.acquire_lease(
        main_repo,
        args.change_id,
        args.agent_id,
        owner=args.owner,
        lease_id=args.lease_id,
        controller_instance_id=args.controller_instance_id,
        session_id=args.session_id,
        phase=args.phase,
        reason=args.reason,
        mode=args.mode,
        ttl_seconds=args.ttl_seconds,
        allow_unleased=True,
    )
    lifecycle.write_process_evidence(
        main_repo,
        change_id=args.change_id,
        agent_id=args.agent_id,
        entry_generation=result["entry_generation"],
        lease_id=args.lease_id,
        owner=args.owner,
        controller_instance_id=args.controller_instance_id,
    )
    _emit(
        {
            **result["activity_lease"],
            "change_id": args.change_id,
            "agent_id": args.agent_id,
            "acquired": True,
        },
        json_output=args.json_output,
    )
    return 0


def cmd_lease_renew(args: argparse.Namespace) -> int:
    short = _short_circuit_json(args, "lease-renew")
    if short is not None:
        return short
    main_repo = resolve_main_repo(os.getcwd())
    result = lifecycle.renew_lease(
        main_repo,
        args.change_id,
        args.agent_id,
        owner=args.owner,
        lease_id=args.lease_id,
        controller_instance_id=args.controller_instance_id,
        phase=args.phase,
        ttl_seconds=args.ttl_seconds,
    )
    lifecycle.write_process_evidence(
        main_repo,
        change_id=args.change_id,
        agent_id=args.agent_id,
        entry_generation=result["entry_generation"],
        lease_id=args.lease_id,
        owner=args.owner,
        controller_instance_id=args.controller_instance_id,
    )
    _emit(
        {
            **result["activity_lease"],
            "change_id": args.change_id,
            "agent_id": args.agent_id,
            "renewed": True,
        },
        json_output=args.json_output,
    )
    return 0


def cmd_lease_assert(args: argparse.Namespace) -> int:
    main_repo = resolve_main_repo(os.getcwd())
    result = lifecycle.assert_owned(
        main_repo,
        args.change_id,
        args.agent_id,
        owner=args.owner,
        lease_id=args.lease_id,
        controller_instance_id=args.controller_instance_id,
    )
    lease = result["activity_lease"]
    _emit(
        {
            "change_id": args.change_id,
            "agent_id": args.agent_id,
            "owner": args.owner,
            "lease_id": args.lease_id,
            "controller_instance_id": args.controller_instance_id,
            "owned": True,
            "expires_at": lease["expires_at"],
        },
        json_output=args.json_output,
    )
    return 0


def cmd_lease_release(args: argparse.Namespace) -> int:
    short = _short_circuit_json(args, "lease-release")
    if short is not None:
        return short
    main_repo = resolve_main_repo(os.getcwd())
    entry = lifecycle.find_entry(lifecycle.read_registry(main_repo), args.change_id, args.agent_id)
    present = bool(entry and Path(entry["worktree_path"]).is_dir())
    result = lifecycle.release_lease(
        main_repo,
        args.change_id,
        args.agent_id,
        owner=args.owner,
        lease_id=args.lease_id,
        controller_instance_id=args.controller_instance_id,
        checkout_present=present,
        recovery_reason=args.recovery_reason or "explicit-lease-release",
    )
    _emit(
        {
            "change_id": args.change_id,
            "agent_id": args.agent_id,
            "owner": args.owner,
            "lease_id": args.lease_id,
            "controller_instance_id": args.controller_instance_id,
            "released": result["released"],
            "recovery_required": result["recovery_required"],
        },
        json_output=args.json_output,
    )
    return 0


def cmd_lease_release_matching(args: argparse.Namespace) -> int:
    operation = "lease-release-owner" if getattr(args, "owner", None) else "lease-release-session"
    short = _short_circuit_json(args, operation)
    if short is not None:
        return short
    main_repo = resolve_main_repo(os.getcwd())
    released = lifecycle.release_matching(
        main_repo,
        owner=getattr(args, "owner", None),
        session_id=getattr(args, "session_id", None),
    )
    payload = {
        "released_count": len(released),
        "quarantined_count": len(released),
        "released_entries": [
            {"change_id": e["change_id"], "agent_id": e.get("agent_id")} for e in released
        ],
    }
    payload["owner" if getattr(args, "owner", None) else "session_id"] = getattr(
        args, "owner", None
    ) or getattr(args, "session_id", None)
    _emit(payload, json_output=args.json_output)
    return 0


def cmd_lease_status(args: argparse.Namespace) -> int:
    profile = detect(agent_id=getattr(args, "agent_id", None))
    if profile.isolation_provided:
        root = run_git("rev-parse", "--show-toplevel", cwd=os.getcwd())
        branch = run_git("branch", "--show-current", cwd=os.getcwd())
        _emit(
            {
                "schema_version": 2,
                "inspected_at": lifecycle.utc_now().isoformat(),
                "entries": [
                    {
                        "change_id": args.change_id,
                        "agent_id": args.agent_id,
                        "branch": branch,
                        "worktree_path": root,
                        "active": False,
                        "activity_lease": None,
                        "repository_owned": False,
                        "isolation_provided": True,
                    }
                ],
            },
            json_output=args.json_output,
        )
        return 0
    main_repo = resolve_main_repo(os.getcwd())
    inspected = lifecycle.utc_now()
    registry = lifecycle.read_registry(main_repo)
    entries = []
    for entry in registry["entries"]:
        if args.change_id and entry["change_id"] != args.change_id:
            continue
        if args.agent_id is not None and entry.get("agent_id") != args.agent_id:
            continue
        lease = entry["activity_lease"]
        live = lifecycle.lease_is_live(lease, now=inspected)
        if lease and not live and not args.include_expired:
            lease = None
        entries.append({**entry, "activity_lease": lease, "active": live})
    _emit(
        {"schema_version": 2, "inspected_at": inspected.isoformat(), "entries": entries},
        json_output=args.json_output,
    )
    return 0


def cmd_retention(args: argparse.Namespace) -> int:
    short = _short_circuit_json(args, f"retention-{args.retention_command}")
    if short is not None:
        return short
    main_repo = resolve_main_repo(os.getcwd())
    if args.retention_command == "set":
        entry = lifecycle.set_retention(
            main_repo,
            args.change_id,
            args.agent_id,
            reason=args.reason,
        )
    else:
        entry = lifecycle.clear_retention(main_repo, args.change_id, args.agent_id)
    _emit(
        {
            "change_id": args.change_id,
            "agent_id": args.agent_id,
            "retained": entry["retained"],
            "retention_reason": entry["retention_reason"],
        },
        json_output=args.json_output,
    )
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    profile = detect(agent_id=getattr(args, "agent_id", None))
    if profile.isolation_provided:
        root = run_git("rev-parse", "--show-toplevel", cwd=os.getcwd())
        branch = run_git("branch", "--show-current", cwd=os.getcwd())
        _emit(
            {
                "schema_version": 2,
                "inspected_at": lifecycle.utc_now().isoformat(),
                "entries": [
                    {
                        "change_id": None,
                        "agent_id": None,
                        "branch": branch,
                        "worktree_path": root,
                        "active": False,
                        "activity_lease": None,
                        "repository_owned": False,
                        "isolation_provided": True,
                    }
                ],
                "setup_reservations": [],
                "recovery_audit": [],
            },
            json_output=args.json_output,
        )
        return 0
    main_repo = resolve_main_repo(os.getcwd())
    registry = lifecycle.read_registry(main_repo)
    now = lifecycle.utc_now()
    entries = [
        {**entry, "active": lifecycle.lease_is_live(entry["activity_lease"], now=now)}
        for entry in registry["entries"]
    ]
    _emit(
        {
            "schema_version": 2,
            "inspected_at": now.isoformat(),
            "entries": entries,
            "setup_reservations": registry["setup_reservations"],
            "recovery_audit": registry["recovery_audit"],
        },
        json_output=args.json_output,
    )
    return 0


def cmd_migration_report(args: argparse.Namespace) -> int:
    main_repo = resolve_main_repo(os.getcwd())
    path = lifecycle.registry_path(main_repo)
    if not path.exists():
        raw: dict[str, Any] = {
            "schema_version": 2,
            "entries": [],
            "setup_reservations": [],
            "recovery_audit": [],
        }
    else:
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise lifecycle.RegistryCorrupt(str(exc)) from exc
    normalized = lifecycle.normalize_registry(raw)
    mappings = []
    for source, target in zip(raw.get("entries", []), normalized["entries"]):
        diagnostics = []
        if (
            raw.get("version") == 1
            and source.get("last_heartbeat") is not None
            and lifecycle.parse_timestamp(source.get("last_heartbeat")) is None
        ):
            diagnostics.append("invalid legacy heartbeat; normalized idle")
        mappings.append(
            {
                "change_id": target["change_id"],
                "agent_id": target.get("agent_id"),
                "entry_generation": target["entry_generation"],
                "retained": target["retained"],
                "activity_source": ("legacy-heartbeat" if target["activity_lease"] else "none"),
                "diagnostics": diagnostics,
            }
        )
    _emit(
        {
            "source_schema": 1 if raw.get("version") == 1 else 2,
            "target_schema": 2,
            "mappings": mappings,
        },
        json_output=args.json_output,
    )
    return 0


def cmd_lease_resume(args: argparse.Namespace) -> int:
    short = _short_circuit_json(args, "lease-resume")
    if short is not None:
        return short
    main_repo = resolve_main_repo(os.getcwd())
    entry = lifecycle.find_entry(lifecycle.read_registry(main_repo), args.change_id, args.agent_id)
    if entry is None or entry["activity_lease"] is None:
        raise lifecycle.FenceConflict("prior lease is absent")
    old = entry["activity_lease"]
    lifecycle._exact_fence(old, args.owner, args.prior_lease_id, args.prior_controller_instance_id)
    if lifecycle.lease_is_live(old):
        raise lifecycle.FenceConflict("prior lease remains live")
    if (
        args.lease_id == args.prior_lease_id
        or args.controller_instance_id == args.prior_controller_instance_id
    ):
        raise lifecycle.FenceConflict("resume must rotate lease and controller identity")
    _assess_takeover(main_repo, entry)
    now = lifecycle.utc_now()

    def rotate(registry: dict[str, Any]) -> dict[str, Any]:
        current = lifecycle.find_entry(registry, args.change_id, args.agent_id)
        if current is None or current["activity_lease"] is None:
            raise lifecycle.FenceConflict("prior lease disappeared")
        lifecycle._exact_fence(
            current["activity_lease"],
            args.owner,
            args.prior_lease_id,
            args.prior_controller_instance_id,
        )
        current["activity_lease"] = lifecycle.new_lease(
            owner=args.owner,
            lease_id=args.lease_id,
            controller_instance_id=args.controller_instance_id,
            session_id=args.session_id,
            phase=args.phase,
            reason=args.reason,
            mode=current["activity_lease"]["lifecycle_mode"],
            ttl_seconds=args.ttl_seconds,
            now=now,
        )
        return current.copy()

    result = lifecycle.mutate_registry(main_repo, rotate)
    lifecycle.write_process_evidence(
        main_repo,
        change_id=args.change_id,
        agent_id=args.agent_id,
        entry_generation=result["entry_generation"],
        lease_id=args.lease_id,
        owner=args.owner,
        controller_instance_id=args.controller_instance_id,
    )
    _emit(
        {
            "change_id": args.change_id,
            "agent_id": args.agent_id,
            "owner": args.owner,
            "prior_lease_id": args.prior_lease_id,
            "prior_controller_instance_id": args.prior_controller_instance_id,
            "lease_id": args.lease_id,
            "controller_instance_id": args.controller_instance_id,
            "resumed": True,
            "recovery_required": False,
        },
        json_output=args.json_output,
    )
    return 0


def _prior_identity(entry: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    context = entry.get("recovery_context") or {}
    return (
        context.get("prior_owner"),
        context.get("prior_lease_id"),
        context.get("prior_controller_instance_id"),
        context.get("process_evidence_key"),
    )


def cmd_recovery_adopt(args: argparse.Namespace) -> int:
    operation = "recovery-force-adopt" if args.force else "recovery-adopt"
    short = _short_circuit_json(args, operation)
    if short is not None:
        return short
    main_repo = resolve_main_repo(os.getcwd())
    entry = lifecycle.find_entry(lifecycle.read_registry(main_repo), args.change_id, args.agent_id)
    if entry is None or not entry["recovery_required"]:
        raise lifecycle.RecoveryRequired("entry is not in recovery quarantine")
    prior_owner, prior_lease, prior_controller, evidence_key = _prior_identity(entry)
    evidence_state = "indeterminate"
    if prior_lease and prior_owner:
        try:
            evidence = lifecycle.read_process_evidence(
                main_repo,
                change_id=entry["change_id"],
                agent_id=entry.get("agent_id"),
                entry_generation=entry["entry_generation"],
                lease_id=prior_lease,
                owner=prior_owner,
                controller_instance_id=prior_controller,
            )
            evidence_state = lifecycle.classify_process_evidence(evidence)
        except lifecycle.RecoveryRequired:
            pass
    if evidence_state == "live":
        raise lifecycle.RecoveryRequired("prior controller is locally live")
    if not args.force and evidence_state != "stale":
        raise lifecycle.RecoveryRequired("normal adoption requires stale same-host evidence")
    if args.force and not args.confirm_terminated:
        raise lifecycle.LifecycleError("force-adopt requires --confirm-terminated")
    established = None
    if entry["durability_target"] is None:
        established = _durability_target(main_repo, args.durability_remote, args.durability_ref)
        if established is None and not args.force:
            raise lifecycle.RecoveryRequired("normal adoption requires a durability target")
        if established is not None:
            run_git("fetch", established["remote_name"], cwd=str(main_repo))
            run_git("rev-parse", established["ref_name"], cwd=str(main_repo))
    elif args.durability_remote or args.durability_ref:
        raise lifecycle.FenceConflict("existing durability target cannot be replaced")
    process_start_token = lifecycle._process_start_token(os.getpid())
    when = lifecycle.utc_now()

    def adopt(registry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        current = lifecycle.find_entry(registry, args.change_id, args.agent_id)
        if (
            current is None
            or not current["recovery_required"]
            or current["entry_generation"] != entry["entry_generation"]
        ):
            raise lifecycle.FenceConflict("recovery entry changed during assessment")
        if established is not None:
            current["durability_target"] = established
        current["recovery_required"] = False
        current["recovery_reason"] = None
        current["recovery_context"] = None
        current["activity_lease"] = lifecycle.new_lease(
            owner=args.owner,
            lease_id=args.lease_id,
            controller_instance_id=args.controller_instance_id,
            session_id=args.session_id,
            phase="RECOVERY",
            reason=args.reason,
            mode="manual",
            ttl_seconds=args.ttl_seconds,
            now=when,
        )
        audit = None
        if args.force:
            audit = lifecycle.append_audit(
                registry,
                {
                    "event": "force-adopted",
                    "recorded_at": when.isoformat(),
                    "change_id": args.change_id,
                    "agent_id": args.agent_id,
                    "entry_generation": current["entry_generation"],
                    "actor": args.actor,
                    "rationale": args.reason,
                    "prior_owner": prior_owner,
                    "prior_lease_id": prior_lease,
                    "prior_controller_instance_id": prior_controller,
                    "new_owner": args.owner,
                    "new_lease_id": args.lease_id,
                    "new_controller_instance_id": args.controller_instance_id,
                    "process_evidence_key": evidence_key,
                    "established_durability_target": established,
                    "termination_confirmed": True,
                },
            )
        return current.copy(), audit

    # Revalidate the quarantine fence, establish evidence, and publish the new
    # authority under one exclusive registry lock. This prevents a competing
    # adopter from overwriting the winning fence's evidence between the two
    # durable writes. Evidence still lands first, so a failed evidence write
    # leaves the on-disk registry quarantined and exactly retryable.
    with lifecycle.registry_lock(main_repo, exclusive=True):
        registry = lifecycle._read_unlocked(main_repo)
        result, audit = adopt(registry)
        lifecycle.write_process_evidence(
            main_repo,
            change_id=args.change_id,
            agent_id=args.agent_id,
            entry_generation=result["entry_generation"],
            lease_id=args.lease_id,
            owner=args.owner,
            controller_instance_id=args.controller_instance_id,
            process_start_token=process_start_token,
        )
        lifecycle._write_unlocked(main_repo, registry)
    _emit(
        {
            "change_id": args.change_id,
            "agent_id": args.agent_id,
            **result["activity_lease"],
            "adopted": True,
            "recovery_required": False,
            **({"recovery_audit_event": audit} if args.force else {}),
        },
        json_output=args.json_output,
    )
    return 0


def cmd_recovery_bind_target(args: argparse.Namespace) -> int:
    short = _short_circuit_json(args, "recovery-bind-target")
    if short is not None:
        return short
    main_repo = resolve_main_repo(os.getcwd())
    entry = lifecycle.find_entry(lifecycle.read_registry(main_repo), args.change_id, args.agent_id)
    if entry is None or entry["entry_generation"] != args.entry_generation:
        raise lifecycle.FenceConflict("entry generation mismatch")
    if entry["durability_target"] is not None:
        raise lifecycle.FenceConflict("durability target is already bound")
    lease = entry["activity_lease"]
    if lease is None or lease["phase"] != "RECOVERY" or lease["lifecycle_mode"] != "manual":
        raise lifecycle.FenceConflict("bind-target requires a manual RECOVERY lease")
    lifecycle._exact_fence(lease, args.owner, args.lease_id, args.controller_instance_id)
    target = _durability_target(main_repo, args.durability_remote, args.durability_ref)
    assert target is not None
    observed = run_git("fetch", args.durability_remote, cwd=str(main_repo), check=True)
    del observed
    tip = run_git("rev-parse", target["ref_name"], cwd=str(main_repo))
    if not _head_is_durable(entry, tip):
        raise lifecycle.RecoveryRequired("checkout HEAD is not reachable from durability target")

    def bind(registry: dict[str, Any]) -> dict[str, Any]:
        current = lifecycle.find_entry(registry, args.change_id, args.agent_id)
        if (
            current is None
            or current["entry_generation"] != args.entry_generation
            or current["durability_target"] is not None
        ):
            raise lifecycle.FenceConflict("entry changed during durability assessment")
        lifecycle._exact_fence(
            current["activity_lease"], args.owner, args.lease_id, args.controller_instance_id
        )
        current["durability_target"] = target
        return current.copy()

    result = lifecycle.mutate_registry(main_repo, bind)
    _emit(
        {
            "change_id": args.change_id,
            "agent_id": args.agent_id,
            "entry_generation": args.entry_generation,
            "owner": args.owner,
            "lease_id": args.lease_id,
            "controller_instance_id": args.controller_instance_id,
            "durability_target": result["durability_target"],
            "bound": True,
        },
        json_output=args.json_output,
    )
    return 0


def cmd_setup_reconcile(args: argparse.Namespace) -> int:
    short = _short_circuit_json(args, "setup-reconcile")
    if short is not None:
        return short
    if not args.confirm_terminated:
        raise lifecycle.LifecycleError("setup reconcile requires --confirm-terminated")
    main_repo = resolve_main_repo(os.getcwd())
    registry = lifecycle.read_registry(main_repo)
    reservation = lifecycle.find_reservation(registry, args.setup_id)
    if reservation is None or reservation["entry_generation"] != args.entry_generation:
        raise lifecycle.FenceConflict("setup reservation fence mismatch")
    if lifecycle.parse_timestamp(reservation["expires_at"]) >= lifecycle.utc_now():
        raise lifecycle.FenceConflict("unexpired reservation remains reserved for exact retry")
    path = Path(reservation["worktree_path"])
    evidence = lifecycle.evidence_path(
        main_repo,
        reservation["change_id"],
        reservation.get("agent_id"),
        reservation["entry_generation"],
        reservation["lease_intent"]["lease_id"],
    )
    has_side_effects = path.exists() or evidence.exists()
    when = lifecycle.utc_now()

    def reconcile(current: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        item = lifecycle.find_reservation(current, args.setup_id)
        if item is None or item["entry_generation"] != args.entry_generation:
            raise lifecycle.FenceConflict("setup reservation changed")
        entry = None
        outcome = "removed-empty-side-effects"
        if has_side_effects:
            outcome = "quarantined-entry"
            intent = item["lease_intent"]
            entry = {
                "change_id": item["change_id"],
                "agent_id": item["agent_id"],
                "branch": item["branch"],
                "worktree_path": item["worktree_path"],
                "created_at": item["created_at"],
                "entry_generation": item["entry_generation"],
                "setup_id": item["setup_id"],
                "durability_target": item["durability_target"],
                "retained": False,
                "retention_reason": None,
                "recovery_required": True,
                "recovery_reason": "setup-failure",
                "recovery_context": {
                    "source": "setup-failure",
                    "prior_owner": intent["owner"],
                    "prior_lease_id": intent["lease_id"],
                    "prior_controller_instance_id": intent["controller_instance_id"],
                    "process_evidence_key": lifecycle.process_evidence_key(
                        item["change_id"],
                        item["agent_id"],
                        item["entry_generation"],
                        intent["lease_id"],
                    )
                    if evidence.exists()
                    else None,
                    "quarantined_at": when.isoformat(),
                },
                "activity_lease": None,
            }
            current["entries"].append(entry)
        current["setup_reservations"].remove(item)
        audit = lifecycle.append_audit(
            current,
            {
                "event": "setup-reconciled",
                "recorded_at": when.isoformat(),
                "setup_id": item["setup_id"],
                "change_id": item["change_id"],
                "agent_id": item["agent_id"],
                "entry_generation": item["entry_generation"],
                "actor": args.actor,
                "rationale": args.reason,
                "prior_owner": item["lease_intent"]["owner"],
                "prior_lease_id": item["lease_intent"]["lease_id"],
                "prior_controller_instance_id": item["lease_intent"]["controller_instance_id"],
                "process_evidence_key": lifecycle.process_evidence_key(
                    item["change_id"],
                    item["agent_id"],
                    item["entry_generation"],
                    item["lease_intent"]["lease_id"],
                )
                if evidence.exists()
                else None,
                "termination_confirmed": True,
                "outcome": outcome,
            },
        )
        return entry, audit

    entry, audit = lifecycle.mutate_registry(main_repo, reconcile)
    _emit(
        {
            "setup_id": args.setup_id,
            "change_id": reservation["change_id"],
            "agent_id": reservation["agent_id"],
            "entry_generation": args.entry_generation,
            "reconciled": True,
            "outcome": audit["outcome"],
            "recovery_required": entry is not None,
            "recovery_audit_event": audit,
        },
        json_output=args.json_output,
    )
    return 0


def _remove_evidence(main_repo: Path, entry: dict[str, Any], lease_id: str | None) -> None:
    if not lease_id:
        return
    path = lifecycle.evidence_path(
        main_repo,
        entry["change_id"],
        entry.get("agent_id"),
        entry["entry_generation"],
        lease_id,
    )
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _cmd_fenced_teardown(args: argparse.Namespace) -> int:
    main_repo = resolve_main_repo(os.getcwd())
    observed_entry = lifecycle.find_entry(
        lifecycle.read_registry(main_repo),
        args.change_id,
        args.agent_id,
    )
    if observed_entry is None:
        _emit(
            {
                "change_id": args.change_id,
                "agent_id": args.agent_id,
                "entry_generation": args.entry_generation,
                "owner": args.owner,
                "lease_id": args.lease_id,
                "controller_instance_id": args.controller_instance_id,
                "removed": False,
                "recovery_required": False,
                "reason": "already-absent",
            },
            json_output=args.json_output,
        )
        return 0
    if observed_entry["entry_generation"] != args.entry_generation:
        raise lifecycle.FenceConflict("entry generation mismatch")
    lease = observed_entry["activity_lease"]
    if lease is None:
        raise lifecycle.FenceConflict("automatic teardown requires a live lease")
    lifecycle._exact_fence(lease, args.owner, args.lease_id, args.controller_instance_id)
    if not lifecycle.lease_is_live(lease):
        raise lifecycle.FenceConflict("automatic teardown lease expired")
    try:
        observed_tip = _target_observation(main_repo, observed_entry)
    except lifecycle.LifecycleError:
        observed_tip = ""
    safe = (
        bool(observed_tip)
        and _checkout_is_clean(observed_entry)
        and _head_is_durable(observed_entry, observed_tip)
    )
    if not safe:
        _quarantine_exact(
            main_repo,
            args.change_id,
            args.agent_id,
            source="unsafe-finalization",
            reason="dirty-non-durable-or-indeterminate",
        )
        _emit(
            {
                "change_id": args.change_id,
                "agent_id": args.agent_id,
                "entry_generation": args.entry_generation,
                "owner": args.owner,
                "lease_id": args.lease_id,
                "controller_instance_id": args.controller_instance_id,
                "removed": False,
                "recovery_required": True,
                "reason": "dirty-non-durable-or-indeterminate",
            },
            json_output=args.json_output,
        )
        return lifecycle.RecoveryRequired.exit_code
    wt_path = Path(observed_entry["worktree_path"])
    with lifecycle.registry_lock(main_repo, exclusive=True):
        registry = lifecycle._read_unlocked(main_repo)
        entry = lifecycle.find_entry(registry, args.change_id, args.agent_id)
        if entry is None:
            return 0
        if entry["entry_generation"] != args.entry_generation:
            raise lifecycle.FenceConflict("entry changed during teardown")
        lifecycle._exact_fence(
            entry["activity_lease"], args.owner, args.lease_id, args.controller_instance_id
        )
        if wt_path.is_dir():
            run_git("worktree", "remove", str(wt_path), cwd=str(main_repo))
        registry["entries"].remove(entry)
        lifecycle._write_unlocked(main_repo, registry)
    _remove_evidence(main_repo, observed_entry, args.lease_id)
    _emit(
        {
            "change_id": args.change_id,
            "agent_id": args.agent_id,
            "entry_generation": args.entry_generation,
            "owner": args.owner,
            "lease_id": args.lease_id,
            "controller_instance_id": args.controller_instance_id,
            "removed": True,
            "recovery_required": False,
            "reason": "safe-durable",
        },
        json_output=args.json_output,
    )
    return 0


def cmd_recovery_teardown(args: argparse.Namespace) -> int:
    operation = "recovery-force-teardown" if args.force else "recovery-teardown"
    short = _short_circuit_json(args, operation)
    if short is not None:
        return short
    if not args.confirm_terminated:
        raise lifecycle.LifecycleError("recovery teardown requires --confirm-terminated")
    if args.force and not args.confirm_discard:
        raise lifecycle.LifecycleError("force-teardown requires --confirm-discard")
    main_repo = resolve_main_repo(os.getcwd())
    observed = lifecycle.find_entry(
        lifecycle.read_registry(main_repo), args.change_id, args.agent_id
    )
    if observed is None or observed["entry_generation"] != args.entry_generation:
        raise lifecycle.FenceConflict("entry generation mismatch")
    lease = observed["activity_lease"]
    if lease is not None:
        if not args.force:
            raise lifecycle.FenceConflict("safe recovery teardown requires a lease-free entry")
        controller = args.controller_instance_id
        if controller is None and not (
            lease["phase"] == "LEGACY"
            and lease["lifecycle_mode"] == "manual"
            and lease["controller_instance_id"] is None
        ):
            raise lifecycle.FenceConflict("leased force teardown requires exact controller")
        lifecycle._exact_fence(lease, args.owner, args.lease_id, controller)
    prior_owner, prior_lease, prior_controller, evidence_key = _prior_identity(observed)
    evidence_lease = lease or (
        {
            "owner": prior_owner,
            "lease_id": prior_lease,
            "controller_instance_id": prior_controller,
        }
        if prior_lease and prior_owner
        else None
    )
    if evidence_lease:
        try:
            evidence = lifecycle.read_process_evidence(
                main_repo,
                change_id=observed["change_id"],
                agent_id=observed.get("agent_id"),
                entry_generation=observed["entry_generation"],
                lease_id=evidence_lease["lease_id"],
                owner=evidence_lease["owner"],
                controller_instance_id=evidence_lease["controller_instance_id"],
            )
            if lifecycle.classify_process_evidence(evidence) == "live":
                raise lifecycle.RecoveryRequired("matching process evidence remains live")
        except lifecycle.RecoveryRequired as exc:
            if "remains live" in str(exc):
                raise
    path = Path(observed["worktree_path"])
    if path.is_dir() and not args.force:
        tip = _target_observation(main_repo, observed)
        if not _checkout_is_clean(observed) or not _head_is_durable(observed, tip):
            raise lifecycle.RecoveryRequired("safe recovery teardown requires clean durable state")
    outcome = (
        "removed-explicit-discard"
        if args.force
        else "removed-missing-checkout"
        if not path.is_dir()
        else "removed-clean-durable"
    )
    when = lifecycle.utc_now()
    audit: dict[str, Any]
    with lifecycle.registry_lock(main_repo, exclusive=True):
        registry = lifecycle._read_unlocked(main_repo)
        entry = lifecycle.find_entry(registry, args.change_id, args.agent_id)
        if entry is None or entry["entry_generation"] != args.entry_generation:
            raise lifecycle.FenceConflict("entry changed during recovery teardown")
        if entry.get("activity_lease") != observed.get("activity_lease"):
            raise lifecycle.FenceConflict("lease changed during recovery teardown")
        if entry.get("recovery_required") != observed.get("recovery_required") or entry.get(
            "durability_target"
        ) != observed.get("durability_target"):
            raise lifecycle.FenceConflict("recovery state changed during teardown")
        if not args.force and path.is_dir():
            current_tip = run_git(
                "rev-parse", entry["durability_target"]["ref_name"], cwd=str(main_repo)
            )
            if (
                current_tip != tip
                or not _checkout_is_clean(entry)
                or not _head_is_durable(entry, current_tip)
            ):
                raise lifecycle.FenceConflict("teardown safety observation changed")
        if path.is_dir():
            git_args = ["worktree", "remove"]
            if args.force:
                git_args.append("--force")
            git_args.append(str(path))
            run_git(*git_args, cwd=str(main_repo))
        audit = lifecycle.append_audit(
            registry,
            {
                "event": "recovery-torn-down",
                "recorded_at": when.isoformat(),
                "change_id": args.change_id,
                "agent_id": args.agent_id,
                "entry_generation": args.entry_generation,
                "actor": args.actor,
                "rationale": args.reason,
                "prior_owner": lease["owner"] if lease else prior_owner,
                "prior_lease_id": lease["lease_id"] if lease else prior_lease,
                "prior_controller_instance_id": lease["controller_instance_id"]
                if lease
                else prior_controller,
                "process_evidence_key": evidence_key,
                "termination_confirmed": True,
                "discard_confirmed": bool(args.force),
                "outcome": outcome,
            },
        )
        registry["entries"].remove(entry)
        lifecycle._write_unlocked(main_repo, registry)
    _remove_evidence(main_repo, observed, (lease or {}).get("lease_id") or prior_lease)
    _emit(
        {
            "change_id": args.change_id,
            "agent_id": args.agent_id,
            "entry_generation": args.entry_generation,
            "removed": True,
            "discard_confirmed": bool(args.force),
            "reason": args.reason,
            "recovery_audit_event": audit,
        },
        json_output=args.json_output,
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _add_agent_id_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agent-id",
        dest="agent_id",
        default=None,
        help="Agent identifier for parallel disambiguation",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Git worktree lifecycle helper for OpenSpec skills"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # setup
    setup_parser = subparsers.add_parser("setup", help="Create a worktree")
    setup_parser.add_argument("change_id", help="Change ID or identifier")
    _add_agent_id_flag(setup_parser)
    setup_parser.add_argument(
        "--branch",
        help=(
            "Branch name override. Precedence: --branch > OPENSPEC_BRANCH_OVERRIDE "
            "env var > openspec/<change-id> default."
        ),
    )
    setup_parser.add_argument("--prefix", help="Path prefix (e.g., fix-scrub)")
    setup_parser.add_argument(
        "--branch-prefix",
        dest="branch_prefix",
        choices=sorted(_VALID_BRANCH_PREFIXES),
        default=None,
        help=(
            "Alternate branch namespace. Currently 'prototype' is the only "
            "supported value: it produces 'prototype/<change-id>/<agent-id>' "
            "branches (with '/' separator) and auto-pins the worktree so it "
            "survives the 24h GC timer until /cleanup-feature deletes it. "
            "Wins over OPENSPEC_BRANCH_OVERRIDE for the variant branch but "
            "leaves the parent feature branch untouched."
        ),
    )
    setup_parser.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Skip environment bootstrap (deps, .env copy, skills sync)",
    )
    setup_parser.add_argument(
        "--sibling",
        action="store_true",
        help=(
            "Place the agent worktree as a peer of the change-id dir "
            "(.git-worktrees/<change-id>--<agent-id>/) instead of inside "
            "it. Use for sync-point worktrees like cleanup-feature whose "
            "nested layout would otherwise pollute the parent worktree's "
            "git status with an untracked subdirectory. Requires --agent-id."
        ),
    )
    setup_parser.add_argument("--durability-remote")
    setup_parser.add_argument("--durability-ref")
    setup_parser.add_argument("--json", action="store_true", dest="json_output")
    setup_parser.set_defaults(func=cmd_setup)

    setup_acquire = subparsers.add_parser(
        "setup-and-acquire",
        help="Atomically publish a worktree with its first lease",
    )
    setup_acquire.add_argument("change_id")
    _add_agent_id_flag(setup_acquire)
    setup_acquire.add_argument("--setup-id", required=True)
    setup_acquire.add_argument("--durability-remote", required=True)
    setup_acquire.add_argument("--durability-ref", required=True)
    setup_acquire.add_argument("--owner", required=True)
    setup_acquire.add_argument("--lease-id", required=True)
    setup_acquire.add_argument("--controller-instance-id", required=True)
    setup_acquire.add_argument("--session-id")
    setup_acquire.add_argument("--phase", required=True)
    setup_acquire.add_argument("--reason", required=True)
    setup_acquire.add_argument("--mode", choices=("standalone", "continuous"), default="standalone")
    setup_acquire.add_argument("--ttl-seconds", type=int, default=1800)
    setup_acquire.add_argument("--setup-reservation-ttl-seconds", type=int, default=1800)
    setup_acquire.add_argument("--json", action="store_true", dest="json_output")
    setup_acquire.set_defaults(func=cmd_setup_and_acquire)

    setup_group = subparsers.add_parser("setup-recovery", help="Setup reservation recovery")
    setup_group.add_argument("setup_id")
    setup_group.add_argument("--entry-generation", required=True)
    setup_group.add_argument("--actor", required=True)
    setup_group.add_argument("--reason", required=True)
    setup_group.add_argument("--confirm-terminated", action="store_true")
    setup_group.add_argument("--json", action="store_true", dest="json_output")
    setup_group.set_defaults(func=cmd_setup_reconcile, agent_id=None)

    # teardown
    teardown_parser = subparsers.add_parser("teardown", help="Remove a worktree")
    teardown_parser.add_argument("change_id", help="Change ID or identifier")
    _add_agent_id_flag(teardown_parser)
    teardown_parser.add_argument("--prefix", help="Path prefix (e.g., fix-scrub)")
    teardown_parser.add_argument(
        "--sibling",
        action="store_true",
        help=(
            "Match the layout used at setup time. Teardown automatically "
            "falls back to the alternate layout if the primary path is "
            "missing, so this flag is informational unless you have both "
            "layouts coexisting for the same agent-id."
        ),
    )
    teardown_parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Remove the registry entry and best-effort git worktree remove "
            "even if the worktree path is dirty, missing, or already deleted. "
            "Used by POST /agents/{id}/kick to clear stale entries."
        ),
    )
    teardown_parser.add_argument("--owner")
    teardown_parser.add_argument("--lease-id")
    teardown_parser.add_argument("--controller-instance-id")
    teardown_parser.add_argument("--entry-generation")
    teardown_parser.add_argument("--json", action="store_true", dest="json_output")
    teardown_parser.set_defaults(func=cmd_teardown)

    lease_parser = subparsers.add_parser("lease", help="Activity lease operations")
    lease_commands = lease_parser.add_subparsers(dest="lease_command", required=True)

    def add_fence(command: argparse.ArgumentParser, *, controller_required: bool = True) -> None:
        command.add_argument("change_id")
        _add_agent_id_flag(command)
        command.add_argument("--owner", required=True)
        command.add_argument("--lease-id", required=True)
        command.add_argument("--controller-instance-id", required=controller_required)
        command.add_argument("--json", action="store_true", dest="json_output")

    acquire = lease_commands.add_parser("acquire")
    add_fence(acquire)
    acquire.add_argument("--session-id")
    acquire.add_argument("--phase", required=True)
    acquire.add_argument("--reason", required=True)
    acquire.add_argument(
        "--mode", choices=("standalone", "continuous", "manual"), default="standalone"
    )
    acquire.add_argument("--ttl-seconds", type=int, default=1800)
    acquire.set_defaults(func=cmd_lease_acquire)

    resume = lease_commands.add_parser("resume")
    resume.add_argument("change_id")
    _add_agent_id_flag(resume)
    resume.add_argument("--owner", required=True)
    resume.add_argument("--prior-lease-id", required=True)
    resume.add_argument("--prior-controller-instance-id", required=True)
    resume.add_argument("--lease-id", required=True)
    resume.add_argument("--controller-instance-id", required=True)
    resume.add_argument("--session-id")
    resume.add_argument("--phase", required=True)
    resume.add_argument("--reason", required=True)
    resume.add_argument("--ttl-seconds", type=int, default=1800)
    resume.add_argument("--json", action="store_true", dest="json_output")
    resume.set_defaults(func=cmd_lease_resume)

    renew = lease_commands.add_parser("renew")
    add_fence(renew)
    renew.add_argument("--phase")
    renew.add_argument("--ttl-seconds", type=int, default=1800)
    renew.set_defaults(func=cmd_lease_renew)

    release = lease_commands.add_parser("release")
    add_fence(release, controller_required=False)
    release.add_argument("--recovery-reason")
    release.set_defaults(func=cmd_lease_release)

    assertion = lease_commands.add_parser("assert-owned")
    add_fence(assertion)
    assertion.set_defaults(func=cmd_lease_assert)

    release_owner = lease_commands.add_parser("release-owner")
    release_owner.add_argument("--owner", required=True)
    release_owner.add_argument("--json", action="store_true", dest="json_output")
    release_owner.set_defaults(func=cmd_lease_release_matching, agent_id=None)

    release_session = lease_commands.add_parser("release-session")
    release_session.add_argument("--session-id", required=True)
    release_session.add_argument("--json", action="store_true", dest="json_output")
    release_session.set_defaults(func=cmd_lease_release_matching, agent_id=None, owner=None)

    lease_status = lease_commands.add_parser("status")
    lease_status.add_argument("change_id", nargs="?")
    _add_agent_id_flag(lease_status)
    lease_status.add_argument("--include-expired", action="store_true")
    lease_status.add_argument("--json", action="store_true", dest="json_output")
    lease_status.set_defaults(func=cmd_lease_status)

    recovery = subparsers.add_parser("recovery", help="Explicit operator recovery")
    recovery_commands = recovery.add_subparsers(dest="recovery_command", required=True)

    def add_adopt(command: argparse.ArgumentParser, *, force: bool) -> None:
        command.add_argument("change_id")
        _add_agent_id_flag(command)
        command.add_argument("--owner", required=True)
        command.add_argument("--lease-id", required=True)
        command.add_argument("--controller-instance-id", required=True)
        command.add_argument("--session-id")
        command.add_argument("--reason", required=True)
        command.add_argument("--ttl-seconds", type=int, default=1800)
        command.add_argument("--durability-remote")
        command.add_argument("--durability-ref")
        command.add_argument("--json", action="store_true", dest="json_output")
        command.set_defaults(func=cmd_recovery_adopt, force=force)
        if force:
            command.add_argument("--actor", required=True)
            command.add_argument("--confirm-terminated", action="store_true")
        else:
            command.set_defaults(actor=None, confirm_terminated=False)

    add_adopt(recovery_commands.add_parser("adopt"), force=False)
    add_adopt(recovery_commands.add_parser("force-adopt"), force=True)

    bind = recovery_commands.add_parser("bind-target")
    add_fence(bind)
    bind.add_argument("--entry-generation", required=True)
    bind.add_argument("--durability-remote", required=True)
    bind.add_argument("--durability-ref", required=True)
    bind.add_argument("--actor", required=True)
    bind.add_argument("--reason", required=True)
    bind.set_defaults(func=cmd_recovery_bind_target)

    def add_recovery_teardown(command: argparse.ArgumentParser, *, force: bool) -> None:
        command.add_argument("change_id")
        _add_agent_id_flag(command)
        command.add_argument("--entry-generation", required=True)
        command.add_argument("--actor", required=True)
        command.add_argument("--reason", required=True)
        command.add_argument("--confirm-terminated", action="store_true")
        command.add_argument("--confirm-discard", action="store_true")
        command.add_argument("--owner")
        command.add_argument("--lease-id")
        command.add_argument("--controller-instance-id")
        command.add_argument("--json", action="store_true", dest="json_output")
        command.set_defaults(func=cmd_recovery_teardown, force=force)

    add_recovery_teardown(recovery_commands.add_parser("teardown"), force=False)
    add_recovery_teardown(recovery_commands.add_parser("force-teardown"), force=True)

    retention = subparsers.add_parser("retention", help="Garbage-collection retention")
    retention_commands = retention.add_subparsers(dest="retention_command", required=True)
    retention_set = retention_commands.add_parser("set")
    retention_set.add_argument("change_id")
    _add_agent_id_flag(retention_set)
    retention_set.add_argument("--reason", required=True)
    retention_set.add_argument("--json", action="store_true", dest="json_output")
    retention_set.set_defaults(func=cmd_retention)
    retention_clear = retention_commands.add_parser("clear")
    retention_clear.add_argument("change_id")
    _add_agent_id_flag(retention_clear)
    retention_clear.add_argument("--json", action="store_true", dest="json_output")
    retention_clear.set_defaults(func=cmd_retention)

    inspect_parser = subparsers.add_parser("inspect", help="Read lifecycle categories")
    inspect_parser.add_argument("--json", action="store_true", dest="json_output")
    inspect_parser.set_defaults(func=cmd_inspect, agent_id=None)
    migration_parser = subparsers.add_parser("migration-report", help="Preview v1 normalization")
    migration_parser.add_argument("--json", action="store_true", dest="json_output")
    migration_parser.set_defaults(func=cmd_migration_report, agent_id=None)

    # status
    status_parser = subparsers.add_parser("status", help="Check worktree status")
    status_parser.add_argument("change_id", nargs="?", help="Change ID to check")
    _add_agent_id_flag(status_parser)
    status_parser.set_defaults(func=cmd_status)

    # detect
    detect_parser = subparsers.add_parser("detect", help="Detect worktree context")
    detect_parser.set_defaults(func=cmd_detect)

    # resolve-branch
    resolve_parser = subparsers.add_parser(
        "resolve-branch",
        help="Print resolved branch for a change-id (honors registry + env override)",
    )
    resolve_parser.add_argument("change_id", help="Change ID or identifier")
    _add_agent_id_flag(resolve_parser)
    resolve_parser.add_argument("--branch", help="Explicit branch name (bypasses resolution)")
    resolve_parser.add_argument("--prefix", help="Path prefix (e.g., fix-scrub)")
    resolve_parser.add_argument(
        "--parent",
        action="store_true",
        help="Resolve the parent (feature/session) branch, stripping any --agent-id suffix",
    )
    resolve_parser.set_defaults(func=cmd_resolve_branch)

    # heartbeat
    hb_parser = subparsers.add_parser("heartbeat", help="Update heartbeat timestamp")
    hb_parser.add_argument("change_id", help="Change ID")
    _add_agent_id_flag(hb_parser)
    hb_parser.add_argument("--owner")
    hb_parser.add_argument("--lease-id")
    hb_parser.set_defaults(func=cmd_heartbeat)

    # list
    list_parser = subparsers.add_parser("list", help="List registered worktrees")
    list_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help=(
            "Emit a JSON array of registry entries instead of the human-readable "
            "table. Each entry includes change_id, agent_id, branch, "
            "worktree_path, last_heartbeat, pinned, and is_stale."
        ),
    )
    list_parser.set_defaults(func=cmd_list)

    # pin
    pin_parser = subparsers.add_parser("pin", help="Pin worktree (protect from GC)")
    pin_parser.add_argument("change_id", help="Change ID")
    _add_agent_id_flag(pin_parser)
    pin_parser.set_defaults(func=cmd_pin)

    # unpin
    unpin_parser = subparsers.add_parser("unpin", help="Unpin worktree")
    unpin_parser.add_argument("change_id", help="Change ID")
    _add_agent_id_flag(unpin_parser)
    unpin_parser.set_defaults(func=cmd_unpin)

    # gc
    gc_parser = subparsers.add_parser("gc", help="Remove stale worktrees")
    gc_parser.add_argument(
        "--stale-after", default="24h", help="Duration threshold (e.g., 24h, 48h, 7d)"
    )
    gc_parser.add_argument("--force", action="store_true", help="Remove pinned worktrees too")
    gc_parser.set_defaults(func=cmd_gc)

    argv = sys.argv[1:]
    if argv[:2] == ["setup", "reconcile"]:
        argv = ["setup-recovery", *argv[2:]]
    parsed = parser.parse_args(argv)
    return parsed.func(parsed)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except lifecycle.LifecycleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(exc.exit_code)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        cmd_str = " ".join(str(a) for a in exc.cmd) if isinstance(exc.cmd, list) else str(exc.cmd)
        print(f"Error: {cmd_str} failed (exit {exc.returncode})", file=sys.stderr)
        if stderr:
            print(f"  {stderr}", file=sys.stderr)
        sys.exit(exc.returncode)
