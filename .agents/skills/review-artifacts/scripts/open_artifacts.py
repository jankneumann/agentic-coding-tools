#!/usr/bin/env python3
"""Open review artifacts in VS Code.

Three discovery modes:

  --change-id <id>      Walk openspec/changes/<id>/ (or its archive variant)
                        in curated read-order: proposal → design → tasks →
                        spec deltas → work-packages → contracts. Then walk
                        each work-package's scope.write_allow to include the
                        implementation files.

  --git-changes         Open everything dirty + branch-local: files from
                        `git status --porcelain` plus committed files not
                        yet on the base branch (`git diff --name-only
                        <base>..HEAD`). Use --base to override the comparison
                        target (default: main).

  --paths PATH [PATH …] Explicit list. Pass-through to `code`.

Auto-detect (no mode flag): if cwd is inside a worktree whose branch matches
`openspec/<id>` AND `openspec/changes/<id>/` exists, treat as --change-id.
Otherwise fall back to --git-changes.

Worktree resolution:
  By default, paths resolve relative to the cwd's git toplevel
  (`git rev-parse --show-toplevel`), which means invoking this script
  inside any worktree opens that worktree's files.
  Pass --worktree <change-id> to explicitly target a different worktree;
  resolution goes through skills/worktree/scripts/worktree.py.

Usage:
    open_artifacts.py                           # auto-detect from cwd
    open_artifacts.py --change-id add-foo       # specific OpenSpec change
    open_artifacts.py --git-changes             # everything dirty + branch-local
    open_artifacts.py --paths a.py b.md docs/   # explicit
    open_artifacts.py --change-id add-foo --worktree add-foo   # cross-worktree

    open_artifacts.py --change-id add-foo --dry-run    # print, don't open
    open_artifacts.py --change-id add-foo --max 8      # cap the tab count

Requires the VS Code `code` CLI on PATH (install via Cmd+Shift+P → "Shell
Command: Install 'code' command in PATH" inside VS Code).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Worktree + git plumbing
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path) -> str:
    """Run `git` and return stdout. Returns "" on non-zero.

    Only trailing whitespace is stripped — leading whitespace is significant
    for `status --porcelain` output (the X column is a space for unstaged
    modifications), so callers see the raw column structure.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.rstrip() if result.returncode == 0 else ""
    except FileNotFoundError:
        return ""


def _git_toplevel(cwd: Path) -> Path | None:
    out = _git(["rev-parse", "--show-toplevel"], cwd).strip()
    return Path(out) if out else None


def _git_main_checkout(cwd: Path) -> Path | None:
    """Return the main checkout's working tree, even when called from a worktree.

    From inside a linked worktree, `git rev-parse --show-toplevel` returns the
    worktree's own path. To find sibling worktrees registered under
    `<main-checkout>/.git-worktrees/`, we need the MAIN checkout's working tree.
    Git's `--git-common-dir` always resolves to the main `.git/` directory;
    its parent is the main checkout's working tree.
    """
    common = _git(["rev-parse", "--git-common-dir"], cwd).strip()
    if not common:
        return _git_toplevel(cwd)
    common_path = Path(common)
    if not common_path.is_absolute():
        top = _git_toplevel(cwd)
        if top is None:
            return None
        common_path = (top / common_path).resolve()
    return common_path.parent


def _current_branch(cwd: Path) -> str:
    return _git(["branch", "--show-current"], cwd).strip()


def _resolve_worktree(change_id: str, cwd: Path) -> Path | None:
    """Locate the worktree path for a change-id via worktree.py list.

    Looks up worktrees registered under the MAIN checkout (not the local
    worktree, which only sees itself). Falls back to
    `<main-checkout>/.git-worktrees/<change-id>/` when the helper is
    unavailable or returns no match.
    """
    main = _git_main_checkout(cwd)
    if not main:
        return None

    worktree_helper = main / "skills" / "worktree" / "scripts" / "worktree.py"
    if worktree_helper.exists():
        try:
            out = subprocess.run(
                ["python3", str(worktree_helper), "list", "--json"],
                cwd=str(main),
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if out.returncode == 0 and out.stdout.strip():
                import json
                data = json.loads(out.stdout)
                entries = data if isinstance(data, list) else data.get("worktrees", [])
                for entry in entries:
                    cid = entry.get("change_id") or entry.get("id")
                    path = entry.get("path") or entry.get("worktree_path")
                    if cid == change_id and path:
                        return Path(path)
        except (subprocess.TimeoutExpired, ValueError):
            pass

    # Fallback: convention-based path under the main checkout
    candidate = main / ".git-worktrees" / change_id
    if candidate.is_dir():
        # Single-agent worktree
        if (candidate / ".git").exists():
            return candidate
        # Parallel: pick the first agent subdir that's an actual worktree
        for sub in sorted(candidate.iterdir()):
            if sub.is_dir() and (sub / ".git").exists():
                return sub
    return None


# ---------------------------------------------------------------------------
# Discovery: OpenSpec change-id
# ---------------------------------------------------------------------------


# Curated read-order for proposal review: each entry is a path glob relative
# to the change directory. Files matching earlier patterns appear in earlier
# tabs.
_PROPOSAL_READ_ORDER = (
    "proposal.md",
    "design.md",
    "tasks.md",
    "specs/**/*.md",
    "work-packages.yaml",
    "contracts/README.md",
    "contracts/**/*.json",
    "contracts/**/*.yaml",
    "contracts/**/*.md",
)


def _resolve_change_dir(root: Path, change_id: str) -> Path | None:
    """Find openspec/changes/<id>/ or archive equivalent under root."""
    active = root / "openspec" / "changes" / change_id
    if active.is_dir():
        return active
    archive = root / "openspec" / "changes" / "archive"
    if archive.is_dir():
        # Archive names are <YYYY-MM-DD>-<change-id>
        matches = sorted(archive.glob(f"*-{change_id}"))
        if matches:
            return matches[-1]  # most recent if multiple
    return None


def _scope_paths_from_work_packages(change_dir: Path) -> list[Path]:
    """Best-effort: parse work-packages.yaml's scope.write_allow entries.

    Uses a minimal YAML-aware regex parser to avoid a PyYAML dependency.
    Glob patterns are expanded against the repo root.
    """
    wp_file = change_dir / "work-packages.yaml"
    if not wp_file.is_file():
        return []

    # Parse without PyYAML: look for `write_allow:` blocks and grab the
    # following list-item lines until indent drops. This is intentionally
    # lossy — we accept missed entries over importing yaml.
    raw = wp_file.read_text(encoding="utf-8").splitlines()
    patterns: list[str] = []
    in_block = False
    block_indent = -1
    for line in raw:
        stripped = line.rstrip()
        if not stripped:
            continue
        # Detect block start
        if "write_allow:" in stripped and not in_block:
            in_block = True
            block_indent = len(line) - len(line.lstrip())
            continue
        if in_block:
            cur_indent = len(line) - len(line.lstrip())
            if cur_indent <= block_indent:
                in_block = False
                continue
            # Expect a list item: "- ..."
            t = line.lstrip()
            if t.startswith("- "):
                val = t[2:].strip().strip('"').strip("'")
                if val:
                    patterns.append(val)

    # Expand patterns against the repo root (two levels up: change_dir is
    # openspec/changes/<id>/, so repo root is change_dir.parent.parent.parent).
    repo_root = change_dir.parent.parent.parent
    resolved: list[Path] = []
    seen: set[Path] = set()
    for pat in patterns:
        # Skip the openspec/changes/<id>/** patterns since we open those
        # directly via _PROPOSAL_READ_ORDER.
        if pat.startswith(f"openspec/changes/{change_dir.name}"):
            continue
        for match in sorted(repo_root.glob(pat)):
            if match.is_file() and match not in seen:
                seen.add(match)
                resolved.append(match)
    return resolved


def discover_change_artifacts(
    change_id: str,
    workspace_root: Path,
    include_scope: bool = True,
) -> list[Path]:
    """Return the curated list of files to open for a change-id review.

    Order: proposal → design → tasks → spec deltas → work-packages →
    contracts → (optionally) scope.write_allow implementation files.
    Files that don't exist are skipped.
    """
    change_dir = _resolve_change_dir(workspace_root, change_id)
    if change_dir is None:
        return []

    ordered: list[Path] = []
    seen: set[Path] = set()
    for pat in _PROPOSAL_READ_ORDER:
        for match in sorted(change_dir.glob(pat)):
            if match.is_file() and match not in seen:
                seen.add(match)
                ordered.append(match)

    if include_scope:
        for match in _scope_paths_from_work_packages(change_dir):
            if match not in seen:
                seen.add(match)
                ordered.append(match)

    return ordered


# ---------------------------------------------------------------------------
# Discovery: git state
# ---------------------------------------------------------------------------


# Paths under these prefixes are generated mirrors (per feedback_canonical_skills.md
# in user memory). They're regenerated by `skills/install.sh` and should not be
# surfaced for review — drift in mirrors isn't meaningful, the canonical
# `skills/` source is the only thing worth editing.
_MIRROR_PREFIXES = (".claude/skills/", ".agents/skills/", ".gemini/skills/")

# Substrings inside paths that mark them as build/cache artifacts no operator
# would want to review. Conservative — we only filter the obvious offenders.
_NOISE_SUBSTRINGS = (
    "/__pycache__/",
    "/.pytest_cache/",
    "/node_modules/",
    "/.venv/",
    "/dist/",
    "/build/",
    ".DS_Store",
)


def _is_mirror_path(rel: str) -> bool:
    if any(rel.startswith(p) for p in _MIRROR_PREFIXES):
        return True
    rel_with_slash = "/" + rel
    return any(s in rel_with_slash for s in _NOISE_SUBSTRINGS) or rel.endswith(".pyc")


def _expand_path(path: Path, workspace_root: Path, max_per_dir: int = 30) -> list[Path]:
    """Expand a path to file(s): files pass through, directories recurse.

    Caps recursion at max_per_dir files per directory to keep an untracked
    node_modules-like blow-up from opening 10k tabs.
    """
    if path.is_file():
        return [path]
    if path.is_dir():
        # Sorted breadth-first walk, capping the total.
        out: list[Path] = []
        for child in sorted(path.rglob("*")):
            if child.is_file():
                # Skip mirrors when expanding (consistent with porcelain filter)
                try:
                    rel = child.relative_to(workspace_root).as_posix()
                except ValueError:
                    rel = str(child)
                if _is_mirror_path(rel):
                    continue
                out.append(child)
                if len(out) >= max_per_dir:
                    break
        return out
    return []


def discover_git_changes(workspace_root: Path, base: str = "main") -> list[Path]:
    """Return uncommitted changes + branch-local commits' touched files.

    Uses `git status --porcelain` for working-tree + index, and
    `git diff --name-only <base>..HEAD` for branch-local committed files.
    Deduplicates while preserving "uncommitted first" order so the operator
    sees their current work-in-progress before historical commits.

    Filters:
      - mirror paths under .claude/skills/, .agents/skills/, .gemini/skills/
        are dropped (regenerated by install.sh; reviewing them is meaningless)
      - directories listed in porcelain (fully-untracked dirs) are expanded
        to their constituent files, capped at 30 files per directory
    """
    files: list[Path] = []
    seen: set[Path] = set()

    def _add(rel_path: str) -> None:
        if not rel_path or _is_mirror_path(rel_path):
            return
        candidate = (workspace_root / rel_path).resolve()
        if not candidate.exists():
            return
        for f in _expand_path(candidate, workspace_root):
            if f not in seen:
                seen.add(f)
                files.append(f)

    # Uncommitted (working tree + index)
    porcelain = _git(["status", "--porcelain"], workspace_root)
    for line in porcelain.splitlines():
        # Porcelain format: "XY <path>" or "XY <old> -> <new>" for renames
        if len(line) < 4:
            continue
        rest = line[3:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        # Strip optional surrounding quotes (git quotes paths with special chars)
        rest = rest.strip().strip('"')
        _add(rest)

    # Branch-local committed
    diff = _git(["diff", "--name-only", f"{base}..HEAD"], workspace_root)
    for line in diff.splitlines():
        _add(line.strip())

    return files


# ---------------------------------------------------------------------------
# Auto-detect
# ---------------------------------------------------------------------------


def auto_detect_mode(workspace_root: Path) -> tuple[str, str | None]:
    """Pick a mode for the no-arg case.

    If current branch is openspec/<id> AND that change dir exists, return
    ("change-id", <id>). Otherwise return ("git-changes", None).
    """
    branch = _current_branch(workspace_root)
    if branch.startswith("openspec/"):
        candidate_id = branch.removeprefix("openspec/").split("--", 1)[0]
        if _resolve_change_dir(workspace_root, candidate_id):
            return ("change-id", candidate_id)
    return ("git-changes", None)


# ---------------------------------------------------------------------------
# VS Code invocation
# ---------------------------------------------------------------------------


def open_in_vscode(
    workspace_root: Path,
    files: list[Path],
    reuse_window: bool = False,
    dry_run: bool = False,
) -> int:
    """Invoke `code <workspace_root> <file1> <file2> ...`.

    By default opens a NEW VS Code window (`code -n`) so the operator's
    existing windows / open files are untouched — the skill is read-only
    for the filesystem AND for the user's VS Code session.

    Pass reuse_window=True for the legacy "switch the existing window's
    workspace to this one" behavior (rarely what you want for review).

    Returns the exit code from the `code` CLI (or 0 on dry-run, 127 if the
    `code` CLI is not on PATH).
    """
    cmd: list[str] = ["code"]
    cmd.append("-r" if reuse_window else "-n")
    cmd.append(str(workspace_root))
    cmd.extend(str(f) for f in files)

    if dry_run:
        print("Would run:")
        print(f"  {cmd[0]} {' '.join(cmd[1:])}")
        return 0

    if shutil.which("code") is None:
        print(
            "ERROR: `code` CLI not found on PATH. Open VS Code, run "
            "Cmd+Shift+P → 'Shell Command: Install code command in PATH', "
            "then try again.",
            file=sys.stderr,
        )
        return 127

    result = subprocess.run(cmd, check=False)
    return result.returncode


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--change-id",
        help="Open OpenSpec proposal artifacts for this change-id (curated order)",
    )
    mode_group.add_argument(
        "--git-changes",
        action="store_true",
        help="Open uncommitted files + files committed on this branch but not on --base",
    )
    mode_group.add_argument(
        "--paths",
        nargs="+",
        help="Explicit list of paths to open (pass-through to `code`)",
    )

    parser.add_argument(
        "--worktree",
        help=(
            "Resolve paths inside the worktree for this change-id, not the "
            "cwd's git root. Use when reviewing a worktree from elsewhere."
        ),
    )
    parser.add_argument(
        "--base",
        default="main",
        help="Base branch for --git-changes comparison (default: main)",
    )
    parser.add_argument(
        "--no-scope",
        action="store_true",
        help=(
            "(change-id mode) Skip implementation files derived from "
            "work-packages.yaml scope.write_allow; open only the proposal "
            "artifacts. Use when you want a pure proposal-doc review."
        ),
    )
    parser.add_argument(
        "--max",
        type=int,
        default=40,
        help=(
            "Maximum number of files to open as tabs (default: 40). The "
            "workspace folder is always added in addition to this count."
        ),
    )
    parser.add_argument(
        "--reuse-window",
        action="store_true",
        help=(
            "Reuse the most-recently-active VS Code window instead of "
            "opening a new one. This SWITCHES that window's workspace folder "
            "to the review root, which can displace files you had open — "
            "only use when you specifically want that behavior. Default is "
            "to open a new window so existing work stays untouched."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the `code` invocation that would run, then exit 0.",
    )
    args = parser.parse_args(argv)

    cwd = Path(os.getcwd())

    # Resolve workspace root (default: cwd's git toplevel; override: --worktree)
    if args.worktree:
        wt = _resolve_worktree(args.worktree, cwd)
        if wt is None:
            print(
                f"ERROR: could not resolve worktree for change-id {args.worktree!r}",
                file=sys.stderr,
            )
            return 1
        workspace_root = wt
    else:
        top = _git_toplevel(cwd)
        if top is None:
            print(
                "ERROR: not inside a git repository (and --worktree not "
                "given). Run from a worktree, or pass --worktree <id>.",
                file=sys.stderr,
            )
            return 1
        workspace_root = top

    # Resolve mode
    if args.paths:
        files = [Path(p).resolve() for p in args.paths]
        existing = [p for p in files if p.exists()]
        missing = [p for p in files if not p.exists()]
        for m in missing:
            print(f"  warn: skipping non-existent path {m}", file=sys.stderr)
        files = existing
    elif args.change_id:
        files = discover_change_artifacts(
            args.change_id,
            workspace_root,
            include_scope=not args.no_scope,
        )
        if not files:
            print(
                f"ERROR: no artifacts found for change-id {args.change_id!r} "
                f"under {workspace_root}/openspec/changes/",
                file=sys.stderr,
            )
            return 1
    elif args.git_changes:
        files = discover_git_changes(workspace_root, base=args.base)
        if not files:
            print(
                f"No uncommitted changes and no commits ahead of {args.base!r}.",
                file=sys.stderr,
            )
            return 0
    else:
        # Auto-detect
        mode, payload = auto_detect_mode(workspace_root)
        if mode == "change-id" and payload:
            print(f"[review-artifacts] auto-detected change-id: {payload}", file=sys.stderr)
            files = discover_change_artifacts(payload, workspace_root, include_scope=True)
        else:
            print(
                f"[review-artifacts] auto-detect → git-changes (base={args.base})",
                file=sys.stderr,
            )
            files = discover_git_changes(workspace_root, base=args.base)
        if not files:
            print("Nothing to review.", file=sys.stderr)
            return 0

    # Cap by --max but always preserve the curated order
    if len(files) > args.max:
        print(
            f"  note: capping at {args.max} files (use --max N to raise); "
            f"truncated {len(files) - args.max} files",
            file=sys.stderr,
        )
        files = files[: args.max]

    # Print the list so the operator sees what's coming
    print(f"Opening {len(files)} file(s) in workspace {workspace_root}:", file=sys.stderr)
    for f in files:
        try:
            rel = f.relative_to(workspace_root)
        except ValueError:
            rel = f
        print(f"  • {rel}", file=sys.stderr)

    return open_in_vscode(
        workspace_root,
        files,
        reuse_window=args.reuse_window,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
