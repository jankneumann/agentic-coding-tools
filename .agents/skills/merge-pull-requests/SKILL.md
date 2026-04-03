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

## Script Location

Scripts live in `<agent-skills-dir>/merge-pull-requests/scripts/`. Each agent runtime substitutes `<agent-skills-dir>` with its config directory:
- **Claude**: `.claude/skills`
- **Codex**: `.codex/skills`
- **Gemini**: `.gemini/skills`

If scripts are missing, run `skills/install.sh` to sync them from the canonical `skills/` source.

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

**Abort conditions:**
- If `gh` is not authenticated, stop and ask the user to run `gh auth login`.
- If the working directory has uncommitted changes, **stop and warn the user**. Do not run `git checkout main` with a dirty working directory — it could silently carry or lose uncommitted work. Ask the user to commit, stash, or discard changes first.
- If not on `main`, check for uncommitted changes before switching.

**Write access check:** Before proceeding, verify the token has write access:

```bash
gh api repos/{owner}/{repo} --jq '.permissions.push'
```

If this returns `false`, warn the user that merge and close operations will fail and suggest checking token scopes or requesting write access.

### 2. Pull Latest Main

```bash
git checkout main
git pull origin main
```

### 3. Discover and Classify Open PRs

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/discover_prs.py
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
- `is_fork` - Whether the PR is from a forked repository
- `auto_merge_enabled` - Whether auto-merge is already configured
- `dep_ecosystem` - For Dependabot PRs, the ecosystem (e.g. `npm_and_yarn`, `pip`)

**If no open PRs are found, stop here.**

Present the PR list as a summary table:

```
| #   | Title                          | Origin     | Branch           | Age    | Flags              |
|-----|--------------------------------|------------|------------------|--------|--------------------|
| 42  | Fix XSS in login form          | sentinel   | sentinel/fix-xss | 3 days |                    |
| 40  | Bump lodash from 4.17.19       | dependabot | dependabot/npm/… | 1 day  | auto-merge         |
| 39  | Fix typo in README             | other      | fix-typo         | 2 days | fork               |
| 38  | feat: Add user export          | openspec   | openspec/add-…   | 5 days | stacked            |
| 37  | WIP: Refactor auth module      | other      | refactor-auth    | 7 days | draft              |
```

### 4. Handle Special PR Types

#### Draft PRs

Draft PRs cannot be merged. Flag them in the summary and **skip** them during the merge workflow. If the operator wants to process a draft PR, they must first mark it as ready:

```bash
gh pr ready <pr_number>
```

#### Stacked PRs

PRs that target a branch other than `main`/`master` are part of a PR chain. **Warn the operator** before taking action on stacked PRs:
- Merging or closing the base PR may break the stacked PR
- The base PR should be merged first
- Show which branch the stacked PR targets

#### Fork PRs

PRs from forked repositories have limited permissions:
- The `--delete-branch` flag is skipped automatically (no push access to the fork remote)
- The merge itself works normally
- Flag these in the summary table as `fork`

#### Auto-Merge PRs

PRs with auto-merge already enabled will merge automatically once their conditions are met (CI passes, approvals received). **Recommend skipping** these during manual triage — they don't need intervention. If the operator wants to override, they can proceed normally.

### 5. Check Staleness for Each PR

For each non-draft PR, run staleness detection:

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/check_staleness.py <pr_number> --origin <origin>
```

The script fetches the latest remote state (`git fetch origin main`) before checking. Pay special attention to Jules automation PRs (sentinel, bolt, palette) — the script uses normalized whitespace matching to check whether the code patterns being fixed still exist on main. If not, the PR is marked `obsolete`.

Staleness levels:
- **Fresh**: No overlapping changes — safe to proceed
- **Stale**: Overlapping file changes — review needed before merge
- **Obsolete**: Fix no longer needed — recommend closing

### 6. Identify Conflicting PR Pairs

After running staleness checks for all PRs, compare their file lists to identify PR pairs that modify the same files. Warn the operator before the interactive review:

```
⚠ PRs #42 and #38 both modify src/auth.py — merging one may make the other stale.
⚠ PRs #40, #41, and #43 all touch package.json — consider merge order carefully.
```

This helps the operator decide merge order proactively rather than discovering conflicts after each merge.

### 7. Batch Close Obsolete PRs

If any PRs are classified as **obsolete**:

```bash
# Show obsolete PRs and ask for confirmation
python3 <agent-skills-dir>/merge-pull-requests/scripts/merge_pr.py batch-close <pr_numbers_comma_sep> \
  --reason "Closing as obsolete: the code patterns this PR fixes no longer exist on main. The underlying issue has been addressed by other changes."
```

Present the list of obsolete PRs and confirm with the operator before closing. Skip this step if no PRs are obsolete.

### 8. Analyze Review Comments

For remaining PRs (non-obsolete, non-draft), check for unresolved review comments:

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/analyze_comments.py <pr_number>
```

This uses the GitHub GraphQL API to get accurate thread resolution status:
- `is_resolved` - Whether the thread has been marked resolved
- `is_outdated` - Whether the comment is on outdated code
- Unresolved thread details: file path, line, reviewer, comment summary
- Review approval state per reviewer

### 9. Conditional Multi-Vendor Review

For PRs that lack detailed reviews and are large enough to warrant automated analysis, dispatch multi-vendor reviews using the review infrastructure from `parallel-implement-feature`.

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/vendor_review.py <pr_number> \
  --origin <origin> --reviews-json <comments_output_path> [--dry-run]
```

**Review is dispatched when ALL conditions are met:**
- Origin is `openspec`, `codex`, or `other` (non-trivial PRs)
- PR is not a draft
- No existing fresh approvals
- No outstanding `CHANGES_REQUESTED` reviews
- PR is non-trivial: more than 50 changed lines OR more than 3 changed files

**Review is skipped when ANY condition is met:**
- Origin is `sentinel`, `bolt`, `palette`, `jules`, `dependabot`, or `renovate` (scoped automation or dependency updates)
- PR already has 1+ approval
- PR is small (≤50 changed lines AND ≤3 files)
- `--dry-run` mode is active (reports eligibility only)

The script:
1. Computes PR size (additions, deletions, file count)
2. Checks eligibility against the rules above
3. If eligible, dispatches to available vendor CLIs (Codex, Gemini) in read-only mode
4. Synthesizes a consensus report from vendor findings
5. Outputs JSON with eligibility status and review findings

**Present findings to the operator** alongside the existing comment analysis in the interactive review step:

```
🔍 Vendor Review (2 vendors):
  ✓ Confirmed (2 vendors agree): 3 findings
    - [HIGH/security] Missing input validation on /api/users endpoint
    - [MEDIUM/correctness] Off-by-one error in pagination logic
    - [LOW/style] Inconsistent naming in helper functions
  ⚠ Unconfirmed (1 vendor only): 1 finding
    - [LOW/performance] Consider caching for repeated lookups
  Blocking: 1 (confirmed fix findings)
```

If vendor review produces **blocking findings** (confirmed issues with disposition=fix), recommend the operator skip or address the issues before merging.

If vendor CLIs are unavailable or all vendors fail, proceed without vendor review and note the gap.

### 9.5. Merge-Time Validation Gate for OpenSpec PRs

For OpenSpec PRs (`openspec/*` branch), check whether Docker-dependent validation has been run. Cloud-created PRs typically pass environment-safe checks (pytest, mypy, ruff, openspec validate) during implementation but lack deployment-based validation.

**Triggers when ALL conditions are met:**
- PR origin is `openspec`
- PR is not a draft
- No `validation-report.md` exists at `openspec/changes/<change-id>/`, OR the existing report is missing deploy/smoke/security/e2e phases

**Skip when ANY condition is met:**
- `validation-report.md` exists with all phases completed
- `--dry-run` mode is active
- Docker is not available (`docker info` fails)

**Action**: Delegate to `/validate-feature` with the Docker-dependent phases only:

```
/validate-feature <change-id> --phase deploy,smoke,security,e2e
```

This runs the canonical validation skill targeting only the phases that require local infrastructure. The skill handles worktree isolation, service lifecycle, report generation, and teardown. The resulting `validation-report.md` is committed to the PR branch so subsequent triage sessions skip this step.

**Present findings** in the interactive review step alongside vendor review results:

```
Merge-Time Validation (OpenSpec: <change-id>):
  ✓ Deploy: Services started (3 containers)
  ✓ Smoke: 5/5 health checks passed
  ○ Security: Skipped (Java not available)
  ○ E2E: Skipped (no tests/e2e/ directory)
  Result: PASS (2 passed, 2 skipped)
```

If any phase **fails**, flag the PR with a warning but do not hard-block — the operator decides whether to merge, fix, or skip. Critical failures (deploy crash, smoke test failures) should be highlighted prominently.

### 10. Determine Merge Order

Before the interactive review, sort remaining PRs for optimal merge order:

1. **Security fixes first** (sentinel origin) — critical fixes shouldn't wait
2. **Non-overlapping PRs** (fresh staleness) — safe to merge without conflict risk
3. **Dependency updates** (dependabot/renovate) — low-risk, well-tested
4. **Stale PRs last** — require manual review of overlapping changes

Within the dependency updates group, consider grouping by ecosystem (e.g. all `npm_and_yarn` bumps together) — if one fails, it may indicate an ecosystem-wide issue.

This ordering minimizes the chance that merging one PR invalidates another.

### 11. Interactive PR Review

Process each remaining PR one at a time **in the order determined above**. Skip PRs with `auto_merge_enabled` unless the operator explicitly wants to review them. For each PR, present:
- Classification and staleness status
- Unresolved comments (if any) — distinguished from resolved threads
- **Vendor review findings** (if dispatched in Step 9) — confirmed, unconfirmed, and blocking findings
- CI and approval status (noting pending vs failed checks)
- Whether checks are still running (offer to wait)
- Whether the PR is from a fork (note: branch won't be deleted)
- Whether approval may be stale (commits pushed after last approval)
- Pending reviewers (CODEOWNERS or manually requested) — even if `reviewDecision` is APPROVED, pending reviewers may indicate a missing required review

Then offer actions:

1. **Merge** - Merge the PR (strategy selected by origin — see table below)
2. **Skip** - Move to the next PR
3. **Close** - Close the PR with a comment
4. **Address comments** - Work through unresolved review feedback
5. **Wait** - (if checks pending) Wait for CI to complete, then re-validate
6. **Re-run CI** - (if checks failed) Re-run failed workflow runs

#### Merge Strategy Selection

The merge strategy is selected based on PR origin to balance history preservation with cleanliness:

| Origin | Default Strategy | Rationale |
|--------|-----------------|-----------|
| `openspec`, `codex` | **rebase** | Agent PRs with structured commits — preserve granular history for `git blame`/`bisect` |
| `sentinel`, `bolt`, `palette` | squash | Jules automation — typically single-purpose fixes |
| `dependabot`, `renovate` | squash | Dependency bumps — one logical change |
| `other` | squash | Manual PRs — unknown commit quality, safe default |

The operator can override any default by passing `--strategy <squash|merge|rebase>`.

#### Merge a PR

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/merge_pr.py merge <pr_number> --origin <origin>
```

Pass `--origin` using the `origin` field from `discover_prs.py` output so the script selects the appropriate strategy automatically. To override:

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/merge_pr.py merge <pr_number> --origin <origin> --strategy squash
```

The script validates CI status (distinguishing failed from pending), draft status, merge conflicts, and mergeability before merging. It handles:
- **Fork PRs**: Automatically skips `--delete-branch`
- **Merge queue repos**: If direct merge fails because a merge queue is required, automatically retries with `--merge-queue`
- **Branch deletion failure**: Detects when merge succeeded but branch deletion failed, reports as warning
- **Merge conflicts**: Surfaces `CONFLICTING` status with specific guidance to rebase or merge the base branch
- **Stale approvals**: Warns if commits were pushed after the last approval
- **Pending reviewers**: Shows which reviewers (including CODEOWNERS teams) haven't reviewed yet

**After every merge, update local state:**
```bash
git pull origin main
```

This ensures subsequent staleness checks and merges operate on the current main.

For **OpenSpec PRs**: After merge, note the change-id and recommend:
```
Run /cleanup-feature <change-id> to archive the OpenSpec proposal.
```

#### Re-run Failed CI Checks

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/merge_pr.py rerun-checks <pr_number>
```

This finds failed workflow runs on the PR's branch and re-runs only the failed jobs. After re-running, offer to **Wait** for the checks to complete.

#### Re-check Staleness After Merge

After merging a PR, the staleness assessment for remaining PRs may be outdated. **Re-run staleness detection** for the next PR before presenting it:

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/check_staleness.py <next_pr_number> --origin <origin>
```

If a previously fresh PR is now stale (due to overlapping with the just-merged PR), update the assessment before offering actions.

#### Close a PR

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/merge_pr.py close <pr_number> --reason "<explanation>"
```

#### Address Comments

For PRs with unresolved comments:
1. Present each unresolved thread (skip resolved/outdated ones)
2. Check out the PR branch: `git checkout <branch>`
3. Make the requested changes
4. Commit and push
5. Return to main: `git checkout main`
6. Return to the PR review workflow

### 12. Summary

After processing all PRs, present a summary:

```
## PR Triage Summary
- Merged: #42, #38
- Queued (merge queue): #45
- Closed (obsolete): #35, #33
- Skipped: #40
- Skipped (draft): #37
- Skipped (auto-merge): #41
- CI re-run: #39
- Comments addressed: #38
- OpenSpec cleanup needed: /cleanup-feature add-user-export
- Merge-time validation: #38 (deploy: pass, smoke: pass, security: skip, e2e: skip)
```

### 13. Append Merge Log

Write a merge-log entry to `docs/merge-logs/YYYY-MM-DD.md` capturing the triage decisions, vendor review findings, and user steering from this session.

**Create directory if needed:**

```bash
mkdir -p docs/merge-logs
touch docs/merge-logs/.gitkeep
```

**Merge-log entry template:**

```markdown
---

## Session: <HH:MM> (<agent-type>)

### PRs Processed

| PR | Origin | Action | Rationale |
|----|--------|--------|-----------|
| #<number> | <origin> | <merged/closed/skipped> | <brief rationale> |

### Vendor Review Findings
- <PR #N>: <N> confirmed findings (<disposition>), <N> unconfirmed (<disposition>)

### User Decisions
- <User steering decisions captured during the session>

### Observations
- <Cross-PR patterns, recurring issues, notable observations>
```

**Focus on**: Cross-PR reasoning (why PRs were processed in this order, how they relate), user steering decisions, vendor review outcomes, and observations about patterns.

**Sanitize-then-verify:**

```bash
python3 "<skill-base-dir>/../session-log/scripts/sanitize_session_log.py" \
  "docs/merge-logs/<date>.md" \
  "docs/merge-logs/<date>.md"
```

Read the sanitized output and verify: (1) all sections present, (2) no incorrect `[REDACTED:*]` markers, (3) markdown intact. If over-redacted, rewrite without secrets, re-sanitize (one attempt max). If sanitization exits non-zero, skip merge log and proceed.

**Commit and push:**

```bash
git add docs/merge-logs/
git commit -m "chore: merge-log <YYYY-MM-DD>"
git push
```

## Dry-Run Mode

When invoked with `--dry-run`, the skill runs all discovery and analysis steps but performs no mutations (no merges, no closes, no comments). Pass `--dry-run` to each script:

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/discover_prs.py --dry-run
python3 <agent-skills-dir>/merge-pull-requests/scripts/check_staleness.py <pr> --origin <type> --dry-run
python3 <agent-skills-dir>/merge-pull-requests/scripts/analyze_comments.py <pr> --dry-run
python3 <agent-skills-dir>/merge-pull-requests/scripts/vendor_review.py <pr> --origin <type> --dry-run
```

Output a full report:

```
## Dry-Run Report
| #   | Title              | Origin     | Staleness | Unresolved | CI      | Vendor Review      | Flags              |
|-----|--------------------|------------|-----------|------------|---------|--------------------|--------------------
| 42  | Fix XSS in login   | sentinel   | obsolete  | 0          | pass    | skip (origin)      |                    |
| 41  | Bump axios         | dependabot | fresh     | 0          | pass    | skip (origin)      | auto-merge         |
| 40  | Bump lodash        | dependabot | fresh     | 0          | pass    | skip (origin)      |                    |
| 39  | Fix typo           | other      | fresh     | 0          | fail    | skip (small)       | fork               |
| 38  | feat: Add export   | openspec   | fresh     | 2          | pass    | 3 findings (1 fix) |                    |
| 37  | WIP: Refactor auth | other      | —         | 1          | pending | skip (draft)       | draft              |
| 35  | Fix slow query     | bolt       | stale     | 0          | pass    | skip (origin)      | stacked            |
```

## Output

- PRs merged, closed, or skipped with reasons
- PRs added to merge queue (for repos that use it)
- Obsolete PRs batch-closed with explanatory comments
- OpenSpec change-ids flagged for `/cleanup-feature`
- Draft PRs flagged (not processed)
- Fork PRs handled (no branch deletion)
- Auto-merge PRs noted (recommended to skip)
- Stacked PRs warned about dependency chain
- Conflicting PR pairs warned about before merge
- **Vendor review findings** for eligible PRs (confirmed, unconfirmed, blocking)
- Failed CI re-runs triggered
- Summary of all actions taken

## Error Handling

- **gh not installed**: Scripts detect this and exit with a clear error message
- **gh not authenticated**: Stop and ask user to run `gh auth login`
- **No write access**: Detected early via `permissions.push` check — warn before attempting mutations
- **Dirty working directory**: Abort before `git checkout main` to prevent losing uncommitted work
- **Merge conflicts**: Surface `CONFLICTING` status with guidance to rebase or merge base branch
- **CI checks pending**: Distinguish from failed — offer to wait
- **CI checks failed**: Show failing checks, offer to re-run failed workflow runs
- **Merge queue required**: Automatically retry with `--merge-queue` when direct merge is rejected
- **Branch deletion failure**: Detect and report as warning (merge still succeeded)
- **Fork PRs**: Automatically skip `--delete-branch` (no push access to fork remote)
- **Stale approvals**: Warn when commits were pushed after the last review approval
- **Pending reviewers (CODEOWNERS)**: Surface pending reviewer requests even when `reviewDecision` shows APPROVED
- **Subprocess timeout**: All `gh`/`git` calls have timeouts (30-60s) to prevent hangs
- **API rate limits**: Scripts use `gh` CLI which handles token refresh; if rate-limited, wait and retry
- **Stacked PRs**: Warn about dependency chain before allowing close/merge
