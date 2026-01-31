---
name: merge-pull-requests
description: Triage, review, and merge open pull requests from multiple sources (OpenSpec, Jules, Codex, Dependabot, manual)
category: Git Workflow
tags: [pr, merge, triage, jules, codex, openspec, review, dependabot]
triggers:
  - "merge pull requests"
  - "review pull requests"
  - "triage PRs"
  - "merge PRs"
  - "check open PRs"
---

# Merge Pull Requests

Discover, triage, and merge open pull requests from multiple sources. Handles OpenSpec PRs, Jules automation PRs (Sentinel/Bolt/Palette), Codex PRs, Dependabot/Renovate PRs, and manual PRs with staleness detection and review comment analysis.

## Arguments

`$ARGUMENTS` - Optional flags: `--dry-run` (report only, no mutations)

## Prerequisites

- `gh` CLI authenticated (`gh auth status`)
- Repository has a remote configured
- On `main` branch with clean working directory

## Steps

### 1. Verify Environment

```bash
gh auth status
git status
```

Ensure `gh` is authenticated and working directory is clean.

### 2. Pull Latest Main

```bash
git checkout main
git pull origin main
```

### 3. Discover and Classify Open PRs

```bash
python skills/merge-pull-requests/scripts/discover_prs.py
```

This outputs a JSON array of PRs classified by origin:
- `openspec` - Branch matches `openspec/*` or body contains `Implements OpenSpec:`
- `sentinel` - Jules Sentinel (security fixes)
- `bolt` - Jules Bolt (performance fixes)
- `palette` - Jules Palette (UX fixes)
- `jules` - Jules automation (type not determined)
- `codex` - Created by Codex
- `dependabot` - Dependabot dependency updates
- `renovate` - Renovate dependency updates
- `other` - Manual or unrecognized

Each PR also includes:
- `is_draft` - Whether the PR is a draft (cannot be merged)
- `is_stacked` - Whether the PR targets a branch other than main/master (part of a PR chain)

**If no open PRs are found, stop here.**

Present the PR list as a summary table:

```
| #   | Title                          | Origin     | Branch           | Age    | Flags         |
|-----|--------------------------------|------------|------------------|--------|---------------|
| 42  | Fix XSS in login form          | sentinel   | sentinel/fix-xss | 3 days |               |
| 40  | Bump lodash from 4.17.19       | dependabot | dependabot/npm/… | 1 day  |               |
| 38  | feat: Add user export          | openspec   | openspec/add-…   | 5 days | stacked       |
| 37  | WIP: Refactor auth module      | other      | refactor-auth    | 7 days | draft         |
```

### 4. Handle Draft PRs

Draft PRs cannot be merged. Flag them in the summary and **skip** them during the merge workflow. If the operator wants to process a draft PR, they must first mark it as ready:

```bash
gh pr ready <pr_number>
```

### 5. Handle Stacked PRs

PRs that target a branch other than `main`/`master` are part of a PR chain. **Warn the operator** before taking action on stacked PRs:
- Merging or closing the base PR may break the stacked PR
- The base PR should be merged first
- Show which branch the stacked PR targets

### 6. Check Staleness for Each PR

For each non-draft PR, run staleness detection:

```bash
python skills/merge-pull-requests/scripts/check_staleness.py <pr_number> --origin <origin>
```

The script fetches the latest remote state (`git fetch origin main`) before checking. Pay special attention to Jules automation PRs (sentinel, bolt, palette) — the script uses normalized whitespace matching to check whether the code patterns being fixed still exist on main. If not, the PR is marked `obsolete`.

Staleness levels:
- **Fresh**: No overlapping changes — safe to proceed
- **Stale**: Overlapping file changes — review needed before merge
- **Obsolete**: Fix no longer needed — recommend closing

### 7. Batch Close Obsolete PRs

If any PRs are classified as **obsolete**:

```bash
# Show obsolete PRs and ask for confirmation
python skills/merge-pull-requests/scripts/merge_pr.py batch-close <pr_numbers_comma_sep> \
  --reason "Closing as obsolete: the code patterns this PR fixes no longer exist on main. The underlying issue has been addressed by other changes."
```

Present the list of obsolete PRs and confirm with the operator before closing. Skip this step if no PRs are obsolete.

### 8. Analyze Review Comments

For remaining PRs (non-obsolete, non-draft), check for unresolved review comments:

```bash
python skills/merge-pull-requests/scripts/analyze_comments.py <pr_number>
```

This uses the GitHub GraphQL API to get accurate thread resolution status:
- `is_resolved` - Whether the thread has been marked resolved
- `is_outdated` - Whether the comment is on outdated code
- Unresolved thread details: file path, line, reviewer, comment summary
- Review approval state per reviewer

### 9. Determine Merge Order

Before the interactive review, sort remaining PRs for optimal merge order:

1. **Security fixes first** (sentinel origin) — critical fixes shouldn't wait
2. **Non-overlapping PRs** (fresh staleness) — safe to merge without conflict risk
3. **Dependency updates** (dependabot/renovate) — low-risk, well-tested
4. **Stale PRs last** — require manual review of overlapping changes

This ordering minimizes the chance that merging one PR invalidates another.

### 10. Interactive PR Review

Process each remaining PR one at a time **in the order determined above**. For each PR, present:
- Classification and staleness status
- Unresolved comments (if any) — distinguished from resolved threads
- CI and approval status (noting pending vs failed checks)
- Whether checks are still running (offer to wait)

Then offer actions:

1. **Merge** - Merge the PR (squash by default)
2. **Skip** - Move to the next PR
3. **Close** - Close the PR with a comment
4. **Address comments** - Work through unresolved review feedback
5. **Wait** - (if checks pending) Wait for CI to complete, then re-validate

#### Merge a PR

```bash
python skills/merge-pull-requests/scripts/merge_pr.py merge <pr_number> --strategy squash
```

The script validates CI status (distinguishing failed from pending), draft status, and mergeability before merging. If the merge succeeds but branch deletion fails, the script detects this and reports a warning rather than a false failure.

**After every merge, update local state:**
```bash
git pull origin main
```

This ensures subsequent staleness checks and merges operate on the current main.

For **OpenSpec PRs**: After merge, note the change-id and recommend:
```
Run /cleanup-feature <change-id> to archive the OpenSpec proposal.
```

#### Re-check Staleness After Merge

After merging a PR, the staleness assessment for remaining PRs may be outdated. **Re-run staleness detection** for the next PR before presenting it:

```bash
python skills/merge-pull-requests/scripts/check_staleness.py <next_pr_number> --origin <origin>
```

If a previously fresh PR is now stale (due to overlapping with the just-merged PR), update the assessment before offering actions.

#### Close a PR

```bash
python skills/merge-pull-requests/scripts/merge_pr.py close <pr_number> --reason "<explanation>"
```

#### Address Comments

For PRs with unresolved comments:
1. Present each unresolved thread (skip resolved/outdated ones)
2. Check out the PR branch: `git checkout <branch>`
3. Make the requested changes
4. Commit and push
5. Return to main: `git checkout main`
6. Return to the PR review workflow

### 11. Summary

After processing all PRs, present a summary:

```
## PR Triage Summary
- Merged: #42, #38
- Closed (obsolete): #35, #33
- Skipped: #40
- Skipped (draft): #37
- Comments addressed: #38
- OpenSpec cleanup needed: /cleanup-feature add-user-export
```

## Dry-Run Mode

When invoked with `--dry-run`, the skill runs all discovery and analysis steps but performs no mutations (no merges, no closes, no comments). Pass `--dry-run` to each script:

```bash
python skills/merge-pull-requests/scripts/discover_prs.py --dry-run
python skills/merge-pull-requests/scripts/check_staleness.py <pr> --origin <type> --dry-run
python skills/merge-pull-requests/scripts/analyze_comments.py <pr> --dry-run
```

Output a full report:

```
## Dry-Run Report
| #   | Title              | Origin     | Staleness | Unresolved | CI      | Flags   |
|-----|--------------------|------------|-----------|------------|---------|---------|
| 42  | Fix XSS in login   | sentinel   | obsolete  | 0          | pass    |         |
| 40  | Bump lodash        | dependabot | fresh     | 0          | pass    |         |
| 38  | feat: Add export   | openspec   | fresh     | 2          | pass    |         |
| 37  | WIP: Refactor auth | other      | —         | 1          | pending | draft   |
| 35  | Fix slow query     | bolt       | stale     | 0          | pass    | stacked |
```

## Output

- PRs merged, closed, or skipped with reasons
- Obsolete PRs batch-closed with explanatory comments
- OpenSpec change-ids flagged for `/cleanup-feature`
- Draft PRs flagged (not processed)
- Stacked PRs warned about dependency chain
- Summary of all actions taken

## Error Handling

- **gh not installed**: Scripts detect this and exit with a clear error message
- **gh not authenticated**: Stop and ask user to run `gh auth login`
- **Merge conflicts**: Flag as stale, recommend manual resolution
- **CI checks pending**: Distinguish from failed — offer to wait
- **CI checks failed**: Show failing checks, recommend fixing before merge
- **Branch deletion failure**: Detect and report as warning (merge still succeeded)
- **Subprocess timeout**: All `gh`/`git` calls have timeouts (30-60s) to prevent hangs
- **API rate limits**: Scripts use `gh` CLI which handles token refresh; if rate-limited, wait and retry
- **Stacked PRs**: Warn about dependency chain before allowing close/merge
