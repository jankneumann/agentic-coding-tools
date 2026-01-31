---
name: merge-pull-requests
description: Triage, review, and merge open pull requests from multiple sources (OpenSpec, Jules, Codex, manual)
category: Git Workflow
tags: [pr, merge, triage, jules, codex, openspec, review]
triggers:
  - "merge pull requests"
  - "review pull requests"
  - "triage PRs"
  - "merge PRs"
  - "check open PRs"
---

# Merge Pull Requests

Discover, triage, and merge open pull requests from multiple sources. Handles OpenSpec PRs, Jules automation PRs (Sentinel/Bolt/Palette), Codex PRs, and manual PRs with staleness detection and review comment analysis.

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
- `codex` - Created by Codex
- `other` - Manual or unrecognized

**If no open PRs are found, stop here.**

Present the PR list as a summary table:

```
| #   | Title                          | Origin   | Branch           | Age    |
|-----|--------------------------------|----------|------------------|--------|
| 42  | Fix XSS in login form          | sentinel | sentinel/fix-xss | 3 days |
| 38  | feat: Add user export          | openspec | openspec/add-... | 5 days |
```

### 4. Check Staleness for Each PR

For each discovered PR, run staleness detection:

```bash
python skills/merge-pull-requests/scripts/check_staleness.py <pr_number> --origin <origin>
```

Pay special attention to Jules automation PRs (sentinel, bolt, palette) — the script checks whether the code patterns being fixed still exist on main. If not, the PR is marked `obsolete`.

Staleness levels:
- **Fresh**: No overlapping changes — safe to proceed
- **Stale**: Overlapping file changes — review needed before merge
- **Obsolete**: Fix no longer needed — recommend closing

### 5. Batch Close Obsolete PRs

If any PRs are classified as **obsolete**:

```bash
# Show obsolete PRs and ask for confirmation
python skills/merge-pull-requests/scripts/merge_pr.py batch-close <pr_numbers_comma_sep> \
  --reason "Closing as obsolete: the code patterns this PR fixes no longer exist on main. The underlying issue has been addressed by other changes."
```

Present the list of obsolete PRs and confirm with the operator before closing. Skip this step if no PRs are obsolete.

### 6. Analyze Review Comments

For remaining PRs (non-obsolete), check for unresolved review comments:

```bash
python skills/merge-pull-requests/scripts/analyze_comments.py <pr_number>
```

This surfaces:
- Unresolved comment threads with file, line, reviewer, and summary
- Review approval state per reviewer

### 7. Interactive PR Review

Process each remaining PR one at a time. For each PR, present:
- Classification and staleness status
- Unresolved comments (if any)
- CI and approval status

Then offer actions:

1. **Merge** - Merge the PR (squash by default)
2. **Skip** - Move to the next PR
3. **Close** - Close the PR with a comment
4. **Address comments** - Work through unresolved review feedback

#### Merge a PR

```bash
python skills/merge-pull-requests/scripts/merge_pr.py merge <pr_number> --strategy squash
```

The script validates CI status and mergeability before merging.

For **OpenSpec PRs**: After merge, note the change-id and recommend:
```
Run /cleanup-feature <change-id> to archive the OpenSpec proposal.
```

#### Close a PR

```bash
python skills/merge-pull-requests/scripts/merge_pr.py close <pr_number> --reason "<explanation>"
```

#### Address Comments

For PRs with unresolved comments:
1. Present each comment thread
2. Check out the PR branch: `git checkout <branch>`
3. Make the requested changes
4. Commit and push
5. Return to the PR review workflow

### 8. Summary

After processing all PRs, present a summary:

```
## PR Triage Summary
- Merged: #42, #38
- Closed (obsolete): #35, #33
- Skipped: #40
- Comments addressed: #38
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
| #   | Title              | Origin   | Staleness | Comments | CI     |
|-----|--------------------|----------|-----------|----------|--------|
| 42  | Fix XSS in login   | sentinel | obsolete  | 0        | pass   |
| 38  | feat: Add export   | openspec | fresh     | 2        | pass   |
```

## Output

- PRs merged, closed, or skipped with reasons
- Obsolete PRs batch-closed with explanatory comments
- OpenSpec change-ids flagged for `/cleanup-feature`
- Summary of all actions taken

## Error Handling

- **gh not authenticated**: Stop and ask user to run `gh auth login`
- **Merge conflicts**: Flag as stale, recommend manual resolution
- **CI failing**: Show failing checks, recommend fixing before merge
- **API rate limits**: Scripts use `gh` CLI which handles token refresh; if rate-limited, wait and retry
