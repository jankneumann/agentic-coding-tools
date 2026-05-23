---
name: review-artifacts
description: Open the artifacts relevant to a review (OpenSpec proposal, branch changes, or explicit paths) in VS Code, in a curated read-order, in the right worktree.
category: Workflow
tags: [review, vscode, openspec, worktree, manual-review]
user_invocable: true
triggers:
  - "review artifacts"
  - "open the proposal"
  - "open in vscode"
  - "open in vs code"
  - "show me the changes"
  - "review the change"
  - "open the change"
requires:
  coordinator:
    required: []
    safety: []
    enriching: []
---

# Review Artifacts

Manual-review helper. Resolves the relevant files for a given review scope and opens them in VS Code in a single command — saving you from manually clicking through `openspec/changes/<id>/`, scrolling `git status`, or hunting through worktrees.

The skill is **read-only**. It does not modify files, run validators, or change git state. It exists to make the human review step faster.

## Three review modes

| Mode | Trigger | What gets opened |
|---|---|---|
| OpenSpec change-id | `--change-id <id>` (or auto-detected from `openspec/<id>` branch) | proposal.md → design.md → tasks.md → spec deltas → work-packages.yaml → contracts/ → implementation files from `scope.write_allow` |
| Git changes | `--git-changes` | Everything from `git status --porcelain` (uncommitted) + `git diff --name-only main..HEAD` (branch-local) |
| Explicit paths | `--paths a b c` | Pass-through |

Auto-detect (no flag): if cwd is on an `openspec/<id>` branch AND `openspec/changes/<id>/` exists, picks change-id mode; otherwise falls back to `--git-changes`.

## Worktree handling

By default, the skill resolves paths against the **cwd's git toplevel** (`git rev-parse --show-toplevel`). That means:

- Invoking it from the main checkout → opens files from main checkout.
- Invoking it from inside a worktree (`cd .git-worktrees/<id>/`) → opens that worktree's files.

To review a **different worktree** from where you are, pass `--worktree <change-id>`. Resolution goes through `skills/worktree/scripts/worktree.py list`, with a fallback to the conventional `.git-worktrees/<id>/` path.

## Prerequisites

- VS Code installed
- `code` CLI on PATH. If missing: open VS Code → `Cmd+Shift+P` → "Shell Command: Install 'code' command in PATH".
- Optional: a recent vitest/pytest run is irrelevant — this skill only reads the filesystem and git state.

## Usage

```bash
# Most common: review the OpenSpec proposal you're about to approve
python3 skills/review-artifacts/scripts/open_artifacts.py --change-id add-kanban-viz-docker-e2e

# Auto-detect from current branch (no flag — picks change-id or git-changes)
python3 skills/review-artifacts/scripts/open_artifacts.py

# Review everything you've changed on a feature branch
python3 skills/review-artifacts/scripts/open_artifacts.py --git-changes

# Compare against a non-main base branch
python3 skills/review-artifacts/scripts/open_artifacts.py --git-changes --base develop

# Pure proposal review — skip the implementation files
python3 skills/review-artifacts/scripts/open_artifacts.py --change-id add-foo --no-scope

# Review a worktree from elsewhere
python3 skills/review-artifacts/scripts/open_artifacts.py \
    --change-id add-foo --worktree add-foo

# Explicit list — pass-through to `code`
python3 skills/review-artifacts/scripts/open_artifacts.py --paths file1.py docs/foo.md

# Preview what would be opened, without opening anything
python3 skills/review-artifacts/scripts/open_artifacts.py --change-id add-foo --dry-run

# Cap the tab count (default 40) — useful for very large changes
python3 skills/review-artifacts/scripts/open_artifacts.py --change-id huge-change --max 12

# Reuse the most-recently-active window instead of opening a new one
# (this SWITCHES that window's workspace folder — can displace open files)
python3 skills/review-artifacts/scripts/open_artifacts.py --change-id add-foo --reuse-window
```

## Window behavior

By default the skill opens a **new VS Code window** (`code -n`) so your existing windows and open files are untouched. The skill is read-only on the filesystem AND on your VS Code session.

Pass `--reuse-window` to opt into the opposite behavior: VS Code's `-r` flag reuses the most-recently-active window and SWITCHES its workspace folder to the review root. That can displace files you had open in that window. Rarely what you want for a review, but useful when you're already in the right workspace and want the review tabs to land alongside what's open.

## File ordering for OpenSpec review

When reviewing a proposal by change-id, files are opened in this deliberate read-order so the most important context lands in the leftmost tab:

1. **`proposal.md`** — Why + What Changes + What Doesn't + Alternatives. Reviewer reads this first.
2. **`design.md`** — Decisions (D1, D2, …). Read second to understand *why this approach*.
3. **`tasks.md`** — What's being committed to.
4. **`specs/**/*.md`** — The actual capability changes (the source-of-truth for what the system will guarantee).
5. **`work-packages.yaml`** — Operational details: locks, scope, verification steps. Lower-priority for human review.
6. **`contracts/README.md`** then `contracts/**/*.json|*.yaml|*.md` — schema artifacts if any.
7. **Implementation files** from each work-package's `scope.write_allow` — what actually changes on disk.

Tabs after step 6 are derived from `work-packages.yaml`'s `scope.write_allow` patterns, expanded against the worktree root via glob. Patterns under `openspec/changes/<id>/**` are de-duplicated (already opened in steps 1–6).

## Steps

### 1. Discover the workspace root

```bash
# Default: cwd's git toplevel
git rev-parse --show-toplevel

# Or: explicit --worktree resolution
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" list --json
```

### 2. Discover the file list

Run the script. By default it auto-detects mode from the current branch.

```bash
python3 "<skill-base-dir>/scripts/open_artifacts.py" --change-id "$CHANGE_ID"
```

The script prints the curated file list to stderr before invoking `code`, so you can verify the discovery before VS Code opens.

### 3. (Optional) Preview without opening

```bash
python3 "<skill-base-dir>/scripts/open_artifacts.py" --change-id "$CHANGE_ID" --dry-run
```

Useful for verifying the auto-detect, `--worktree` resolution, or `scope.write_allow` glob expansion before actually opening 40 tabs.

### 4. Invoke

Without `--dry-run`, the script calls:

```bash
code -n <workspace-root> <file1> <file2> ...
```

VS Code opens a **new window** rooted at the workspace, with every file as a tab in that window. Your existing windows / open files are untouched. Pass `--reuse-window` to instead reuse the most-recently-active window (which switches its workspace folder — see "Window behavior" above).

## Worked Example: review the proposal we just created

Assume you've just had Claude generate `openspec/changes/add-kanban-viz-docker-e2e/`. Three options to review it:

**A. From the main checkout (or any cwd in the repo):**

```bash
python3 skills/review-artifacts/scripts/open_artifacts.py \
    --change-id add-kanban-viz-docker-e2e
```

This opens (in order): proposal.md → design.md → tasks.md → specs/coordinator-kanban-viz/spec.md → work-packages.yaml → contracts/README.md → all implementation files from the work-package's scope.write_allow (`docker-compose.yml`, `e2e_kanban.py`, `seed_kanban_board.py`, `Makefile`, `e2e.integration.test.tsx`).

**B. Pure proposal-doc review (no implementation files):**

```bash
python3 skills/review-artifacts/scripts/open_artifacts.py \
    --change-id add-kanban-viz-docker-e2e --no-scope
```

Just the 6 proposal-level files (about half the tabs of option A).

**C. Branch-state review (everything dirty + branch-local):**

```bash
git checkout openspec/add-kanban-viz-docker-e2e   # if you're on a feature branch
python3 skills/review-artifacts/scripts/open_artifacts.py --git-changes
```

Shows files in modification order (uncommitted first, branch-local commits second).

## Exit codes

- `0` — files opened (or dry-run completed)
- `1` — setup error: not in a git repo, no artifacts found for change-id, can't resolve worktree
- `127` — `code` CLI not found on PATH

## Limitations

- **YAML parsing is regex-based**, not via PyYAML, to keep the script stdlib-only. It handles `scope.write_allow:` blocks reliably but won't expand `&anchors`/`*aliases` or complex YAML constructs. If `scope.write_allow` patterns are missed, fall back to `--git-changes`.
- **No diff view**: the skill opens files as plain tabs, not VS Code's three-pane diff. For comparing branch state, use `Cmd+K Cmd+G` inside VS Code, or `code --diff <a> <b>` directly.
- **No remote worktrees**: cloud-harness containers won't have a local `code` CLI. This skill is for local dev only.

## Related Skills

- **`/explore-feature`** — discovers candidate proposals before drafting; complementary (this skill reviews what `/plan-feature` produces).
- **`/plan-feature`** — produces the artifacts this skill opens.
- **`/iterate-on-plan`** — the typical workflow after using this skill: open in VS Code → spot issues → invoke `/iterate-on-plan <change-id>` to refine.
- **`/parallel-review-plan`** — automated vendor-diverse review; this skill is the *human* equivalent.
