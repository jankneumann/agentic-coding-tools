# Parallel Git Configuration

Configuration guide for running multiple AI agents in parallel worktrees.

## Quick Setup

```bash
# Apply all parallel-friendly git settings
bash scripts/git-parallel-setup.sh

# Or via the Makefile
make -C agent-coordinator git-setup
```

## What Gets Configured

| Setting | Value | Purpose |
|---------|-------|---------|
| `rerere.enabled` | `true` | Cache conflict resolutions. When Agent A resolves a conflict, Agent B gets the same resolution automatically via shared `.git/rr-cache/`. |
| `rerere.autoUpdate` | `true` | Auto-stage files resolved by rerere (no manual `git add` needed). |
| `merge.conflictStyle` | `zdiff3` | Show the base version alongside ours/theirs in conflict markers, giving agents better context for resolution. |
| `diff.algorithm` | `histogram` | Better diffs for code with repetitive structure (boilerplate endpoints, test cases). Already the default for `git merge` with the ort strategy, but this makes it consistent for `git diff` too. |
| `rebase.updateRefs` | `true` | Automatically update stacked branch pointers during rebase. Free stack management without external tools. |

All settings use `git config --local` — they only affect this repository, not your global config.

## Worktree Bootstrap

When creating a new worktree via `skills/worktree/scripts/worktree.py setup`, the bootstrap script automatically:

1. Copies `.env` and `.secrets.yaml` from the main repo
2. Runs `uv sync --all-extras` in `agent-coordinator/`
3. Runs `uv sync` in `skills/`
4. Syncs skills via `skills/install.sh`
5. Shares the uv cache across worktrees (`UV_CACHE_DIR`)

To skip bootstrapping (e.g., for doc-only changes):

```bash
python3 skills/worktree/scripts/worktree.py setup my-feature --no-bootstrap
```

## GitHub Merge Queue

The merge queue prevents broken `main` when multiple agent PRs merge concurrently. Without it, PR B (tested against `main@sha1`) can merge after PR A changes `main`, potentially breaking the build.

### How It Works

1. A PR passes CI and is approved
2. Author clicks "Merge when ready" (or `gh pr merge <number>`, which enqueues when the branch requires a queue)
3. GitHub creates a temporary branch combining `main` + all queued PRs + this PR
4. CI runs against this combined state
5. If CI passes, the PR merges; if it fails, the PR is ejected

### Enabling Merge Queue

1. Go to **Settings > Rules > Rulesets** and add a rule for `main` (the merge-pull-requests skill detects queues configured as a ruleset `merge_queue` rule)
2. Enable **Require merge queue**
3. Set build concurrency to match your typical parallel agent count (3-5)
4. Set min group size = 1 (don't batch — agent PRs are independent)

The CI workflow already includes the `merge_group` trigger, so CI will run on merge queue validation branches automatically.

### Verifying It Works

```bash
# Check CI triggers include merge_group
grep -A 5 '^on:' .github/workflows/ci.yml

# Merge a PR via the queue
gh pr merge <number>   # no strategy flag; the queue's settings choose the method
```

## .gitattributes

The `.gitattributes` file defines custom merge strategies for lock files:

- `uv.lock` — union merge (combines both sides, avoids false conflicts)
- `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` — binary merge (flags conflict, pick one side)

## Verifying Configuration

```bash
# Check all parallel settings are active
git config --local --list | grep -E 'rerere|merge.conflict|diff.algo|rebase.update'

# Verify rerere cache location (shared across worktrees)
ls -la .git/rr-cache/ 2>/dev/null || echo "No cached resolutions yet"
```
