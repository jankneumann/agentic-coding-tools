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

`$ARGUMENTS` supports two modes:

- Interactive analysis/triage: optional `--dry-run` (report only, no mutations).
- Fresh-context plan execution: `--execute <merge-plan.json> --pr <number>`, with
  optional `--approve-gate` only after the operator explicitly approves that node's
  surfaced human gates, and optional `--claim-id <stable-attempt-id>` only when
  resuming the same recorded attempt. OpenSpec proposal-acceptance gates cannot be
  released by `--approve-gate`.

## Script Location

Scripts live in `<agent-skills-dir>/merge-pull-requests/scripts/`. Each agent runtime substitutes `<agent-skills-dir>` with its config directory:
- **Claude**: `.claude/skills`
- **Codex**: `.codex/skills`
- **Gemini**: `.gemini/skills`

If scripts are missing, re-run the installer from a separate
`agentic-coding-tools` source checkout; the installer is not shipped inside a
consumer skill payload.

## Prerequisites

- `gh` CLI authenticated (`gh auth status`)
- Repository has a remote configured
- On `main` branch with clean working directory

## Active-Agent Guard (Sync-Point Skill)

Before any other work, verify exclusive access — this skill merges into `main` and must not race other agents:

```bash
python3 "<skill-base-dir>/../shared/active_agents.py"
```

- Exit `0`: no active agents → proceed.
- Exit `1`: one or more active agents hold worktrees → **stop**, surface the list to the operator (the script's stdout already prints it), and ask whether to wait or pass `--force`. Never auto-force.

An entry is "active" when it is pinned OR its `last_heartbeat` is within 1 hour. See the co-installed `../shared/active_agents.py` helper and the consumer repository's coordination guidance for the contract.

## Merge Backend Selection

The skill automatically selects a merge backend based on environment capabilities:

| Priority | Backend | Condition | Behavior |
|----------|---------|-----------|----------|
| 1 | **Coordinator Train** | Coordinator available + `CAN_QUEUE_WORK` | Speculative parallel testing via `compose_train` |
| 2 | **GitHub Merge Queue** | GitHub merge queue enabled | Batched merging via `gh pr merge --merge-queue` |
| 3 | **Direct Merge** | Fallback | Single PR via `gh pr merge` (existing behavior) |

Detection is automatic via `detect_merge_backend()` in `merge_backend.py`. Solo-dev repos without coordinator or GitHub queue use Direct Merge — all existing behavior is preserved.

## Merge Metrics (always on)

Every successful merge appends a structured event to
`docs/merge-logs/metrics.jsonl` — `merge_pr()` does this itself, so a plain
`merge` is recorded exactly like a `--pipeline` one. `merge_metrics.py` reduces
that log to merge/revert/rebase counts, revert rate, backend breakdown and
duration percentiles.

Recording is best-effort and never fails a merge: if the append raises, the
result carries `event_emitted: false` and `event_error`, and the merge still
reports success. The merge already happened on GitHub by that point, so
reporting it as failed over a local write would be strictly worse than losing
the row.

This used to be hook 1 of the post-merge pipeline below, which meant it was
gated behind `--pipeline` alongside two hooks that mutate other people's PRs.
Nobody passes that flag just to get a metrics row, so nothing was ever
recorded — the log held zero `merge` events until 2026-08-25.

## Post-Merge Pipeline

After each successful merge (when the `--pipeline` flag is used), two composable hooks run independently:

1. **Auto Cascading Rebase**: Refresh up to 5 queued PRs with file overlap via GitHub Update Branch API (configurable via `MERGE_AUTO_REBASE_LIMIT`)
2. **Auto Rollback**: Monitor main CI for 15 minutes; if failure overlaps with merged files, create and auto-merge a revert PR (configurable via `ROLLBACK_MONITOR_MINUTES`)

Both reach outside this repository, which is why they stay opt-in. A failure in one hook does not block the others.

## Background Merge Watcher

For continuous monitoring without operator invocation:

```bash
# Single pass (for Claude /loop)
python merge_watcher.py tick

# Polling loop (standalone)
python merge_watcher.py run --interval 60
```

When the coordinator is available, the watcher runs as a background asyncio task (disable via `MERGE_WATCHER_DISABLED=1`).

## Durable Merge Plan and Fresh-Context Execution

The analysis round can persist its joined `discover_prs.py`,
`check_staleness.py`, and `analyze_comments.py` outputs as a durable plan. Save
those outputs as JSON, then run the producer from the canonical skill tree:

```bash
python3 "<skill-base-dir>/scripts/build_plan.py" \
  --prs /tmp/discovered-prs.json \
  --staleness /tmp/staleness.json \
  --comments /tmp/comments.json \
  --output merge-plan.json
```

The command validates and writes both authoritative `merge-plan.json` and its
pure `merge-plan.md` projection. The plan records definition fields (topology,
strategies, and gates) separately from live execution state. File-overlap and
stacked-base relationships become dependency edges; the Markdown projection
surfaces those edges plus live CI, staleness, comment, and blocking state. JSON
is the commit marker for the two-file bundle; loading the file store repairs a
missing or interrupted Markdown projection from authoritative JSON.

To process one PR with a clean context, start a new session and provide only the
plan plus the target number:

```bash
python3 "<skill-base-dir>/scripts/execute_plan.py" \
  --execute merge-plan.json --pr 42
```

Execution runs the active-agent sync-point guard, re-checks live PR, CI, and
staleness state, refreshes stale or invalidated nodes, runs eligible vendor
review, and delegates the actual merge to the existing `merge_pr.py` safety
path. Eligible review fails closed on dispatch error or a missing verdict. Before
refresh/review/merge side effects it atomically persists `outcome=in_progress` and a
same-host file-tier claim. Every file-tier mutation shares that lock; stale whole-plan
revisions and unexpected node outcomes are rejected instead of overwriting a claim. A
retry reconciles live merged/closed state before human or
sync-point gates and refuses an unowned in-flight claim rather than replaying the merge.
A successful merge persists `outcome=merged` and sets `needs_revalidation=true` on every
transitive dependant. The next executor refreshes and re-checks any flagged node before
it may merge. Because historical file overlap can remain `stale` after refresh, the
post-refresh decision requires a current CI merge base, fresh passing CI, and live
mergeability instead of requiring the overlap label to become `fresh`.

Human gates are fail-closed. If `auto_executable` is false or the plan carries a
gate, the command stops and prints the gate. Only after explicit operator
approval may the operator re-run the same command with `--approve-gate`. That
flag never bypasses OpenSpec proposal acceptance, required security checks, or
GitHub's merge protections.

When unresolved comments are found, execution records their summary in the
plan and returns hand-off commands for `iterate-on-implementation` and
`quick-task`; it never edits the PR branch. A caller that discovers a new
cross-PR blocker may use `merge_plan.amend_plan()` to append a prerequisite,
its reason, and dependency edges. Existing nodes are preserved and the amended
DAG is revalidated before persistence.

Phase 1 uses `merge-plan.json` as the authority when coordinator queue
capabilities are unavailable. Coordinator-backed live plan state is an explicit
Phase-2 `NotImplementedError` seam; do not imply multi-host safety until that
follow-on lands. Plan-driven helpers resolve through canonical
`skills/merge-pull-requests/scripts` from the repository root, never
`.agents/skills`, `.claude/skills`, or another runtime mirror.

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

### 5b. Classify CI Failures

For PRs with failing CI, determine the failure class before choosing a fix strategy:

| Failure Class | Symptoms | Fix Strategy |
|---------------|----------|-------------|
| **Transient** | Flaky test, network timeout, OOM, runner issue | `rerun-checks` — same code should pass on retry |
| **PR-specific** | Lint/test error in files the PR modified | Fix the code, commit, push (triggers fresh CI) |
| **Stale merge** | Error in files the PR did NOT modify; same error across multiple unrelated PRs | `refresh-branch` or rebase onto main |

**How to detect stale-merge failures**: If the same CI check fails identically on 3+ unrelated PRs, and the failing files are not in those PRs' change sets, it is almost certainly a stale merge commit. `gh run rerun` will NOT fix this — it replays the workflow against the same merge commit snapshot, not a fresh one.

To refresh the merge commit without a local rebase:

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/merge_pr.py refresh-branch <pr_number>
```

This calls the GitHub Update Branch API to merge the current base into the PR branch, producing a new merge commit that triggers fresh CI automatically. For PRs that will be squash-merged, the merge commit is discarded at merge time.

The `check_staleness.py` script includes a `ci_merge_base_stale` field that compares the PR's merge base with the current base branch HEAD. When `ci_merge_base_stale` is `true` and CI is failing, prefer `refresh-branch` over `rerun-checks`.

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
3. If eligible, checks for OpenSpec planning artifacts (contracts, work-packages) in the change directory:
   - If artifacts exist: includes contract and scope information in the review prompt for richer vendor context
   - If artifacts are missing (legacy PRs, external contributions, non-OpenSpec PRs): proceeds with PR diff and metadata only — review does not fail or skip due to missing artifacts
4. Dispatches to available vendor CLIs (Codex, Gemini) in read-only mode
5. Synthesizes a consensus report from vendor findings
6. Outputs JSON with eligibility status and review findings

**HEAD-mutation guard (issue #349):** vendor CLIs run against the shared
working tree and have detached HEAD mid-dispatch (`checkout FETCH_HEAD`).
The script snapshots HEAD before dispatch, verifies it afterwards, restores
the original branch on drift, and exits with code 2 whenever drift was
detected — even if restored. On exit 2, stop and re-verify any local state
gathered during the dispatch before continuing. `merge_pr.py` independently
refuses to merge while the checkout is on a detached HEAD
(`"reason": "detached_head"`).

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

In interactive triage, if vendor CLIs are unavailable or all vendors fail,
proceed without vendor review and note the gap. Plan-driven execution is stricter:
when its eligibility decision requires review, an unavailable dispatcher, all
failed vendors, or a missing consensus verdict blocks the node.

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

### 9.6. Check Holdout Gate (OpenSpec PRs Only)

If `openspec/changes/<change-id>/rework-report.json` exists, check whether holdout scenario failures block the merge:

```bash
REWORK_REPORT="openspec/changes/$CHANGE_ID/rework-report.json"
if [[ -f "$REWORK_REPORT" ]]; then
  HAS_BLOCKING=$(python3 -c "
import json
data = json.load(open('$REWORK_REPORT'))
print(data.get('summary', {}).get('has_blocking_holdout', False))
")
  if [[ "$HAS_BLOCKING" == "True" ]]; then
    echo "WARNING: Holdout scenario failures detected in rework report"
    echo "The rework report indicates blocking holdout failures."
    echo "Consider running /iterate-on-implementation and /validate-feature before merge."
  fi
fi
```

Holdout gate status is presented as a **warning** during the interactive review — it does not auto-block. The operator decides whether the holdout failures are acceptable for this merge or need resolution first.

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

#### Save Point Pattern

When iterating on a complex merge resolution (rebase conflicts, repeated CI fixes, multi-step "address comments" passes), **commit at every working slice** with a `wip:` prefix. Squash before final merge.

```bash
# After each working slice (tests pass, lint passes, the change makes sense in isolation):
git add -A
git commit -m "wip: <description of the slice that just started working>"

# Before opening / re-opening for review, squash the wip commits into logical units:
git rebase -i <base-branch>     # mark wip: commits as `s` (squash) into a parent
# OR if the operator prefers a single squashed commit at merge:
gh pr merge --squash             # GitHub squashes them at merge time
```

**Why this matters:** A complex merge resolution often takes 5-30 incremental fixes. Without save points, a single mistake can lose all the prior progress. With `wip:` save points you can `git reset --hard <last-wip-sha>` to return to the most recent known-good state without re-doing everything. The squash step at the end keeps the public history clean.

The `wip:` prefix is the agreed signal: any commit starting with `wip:` is **assumed to be squashed before merge** and should never appear on `main`. This skill's pre-merge gate refuses to merge a PR whose head commit message starts with `wip:` unless `--strategy squash` is in effect.

#### Change Summary template

Every PR ready-for-review MUST include the following template in its description. Reviewers depend on it; the bot scaffolds it; the skill's gate checks for it.

```
CHANGES MADE:
- <bullet list of what this PR actually does>

DIDN'T TOUCH:
- <out-of-scope items intentionally not addressed — name them so reviewers don't ask>

CONCERNS:
- <known issues, follow-ups, things reviewers should challenge>
```

**Why all three sections matter:**
- `CHANGES MADE` forces the author to enumerate the actual changes (not just link the title) — exposes scope creep early.
- `DIDN'T TOUCH` pre-empts the most common reviewer round-trip ("why didn't you also fix X?"). Naming the boundary up front saves a review cycle.
- `CONCERNS` is the author's invitation to be challenged. A PR with `CONCERNS: none` after a non-trivial change is a **red flag**: real changes always have at least one open question.

If a PR is missing this section, this skill flags it as `description-incomplete` during the interactive review and offers to scaffold the template into the body before merging.

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
- **Conditional approval gate**: Probes the base branch's protection rules and only requires approval when GitHub itself would (i.e., `required_approving_review_count >= 1`). Solo repos and unprotected branches merge without an approval check, the same way `gh pr merge` would allow. Pass `--force-approval` to force-bypass even when protection requires approval (admin overrides, or when probing protection failed and the gate fell back to strict mode).

**After every merge, update local state:**
```bash
git pull origin main
```

This ensures subsequent staleness checks and merges operate on the current main.

For **OpenSpec PRs**: After a successful merge, record the PR number, head branch, and change-id for the final post-merge cleanup approval step. Do not run `/cleanup-feature` immediately inside the per-PR merge loop.

Example record shape:

```json
{
  "pr_number": 42,
  "origin": "openspec",
  "change_id": "add-user-export",
  "branch": "openspec/add-user-export",
  "success": true,
  "status": "merged"
}
```

Keep these records scoped to PRs merged during this invocation only. They are the input to Step 11.5.

#### Re-run Failed CI Checks

> **Important**: `rerun-checks` replays the workflow against the **same merge commit**. It does NOT pick up changes to the base branch. Use this only for **transient** failures (flaky tests, timeouts, OOM). For failures caused by stale base-branch code, use `refresh-branch` or rebase instead. See Step 5b for the diagnostic flowchart.

```bash
# Transient failure — replay same merge commit:
python3 <agent-skills-dir>/merge-pull-requests/scripts/merge_pr.py rerun-checks <pr_number>

# Stale merge commit — merge current base into PR branch for fresh CI:
python3 <agent-skills-dir>/merge-pull-requests/scripts/merge_pr.py refresh-branch <pr_number>
```

`rerun-checks` finds failed workflow runs on the PR's branch and re-runs only the failed jobs. `refresh-branch` calls the GitHub Update Branch API to merge the base branch into the PR branch, producing a new merge commit. Both trigger CI; after either, offer to **Wait** for the checks to complete.

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

### 11.5. Post-Merge OpenSpec Cleanup Approval

After the PR review loop completes, prepare a single post-merge cleanup prompt for any **local OpenSpec** PRs merged during this invocation.

**Do not run this step in `--dry-run` mode.** In dry-run mode, report which cleanup commands would be offered for approval.

Use the merged PR records collected during Step 11:

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/post_merge_cleanup.py \
  --merged-json <merged_prs_this_pass.json>
```

The helper is non-mutating. It filters to merged OpenSpec PRs whose `openspec/changes/<change-id>/` directory exists locally, checks local worktree registry and branch remnants, and renders an approval prompt like:

```text
Merged local OpenSpec PRs eligible for post-merge cleanup:

| PR | Change ID | Branch | Local remnants | Command |
|----|-----------|--------|----------------|---------|
| #42 | add-user-export | openspec/add-user-export | 2 worktree registry entries, 3 local branches | `/cleanup-feature add-user-export --post-merge --pr 42` |

Before asking the operator to approve, invoke `/review-artifacts <change-id>` for each listed change-id so review artifacts are open in VS Code first.
Ask the operator: Proceed with post-merge cleanup for these changes?
Only run the listed cleanup commands after explicit approval.
```

This step establishes **approval and order only**. It runs no cleanup command
itself. If the operator approves, the approved list — in the approved order — is
executed as phase 1 of Step 11.6, which appends `--defer-commit` so that one
commit carries every change's cleanup output together with the refresh output.

```bash
# Executed in Step 11.6, phase 1 — not here:
/cleanup-feature <change-id> --post-merge --pr <pr_number> --defer-commit
```

The `--post-merge` cleanup mode must:
- Confirm the PR is already merged.
- Skip the PR merge and pre-merge validation stages.
- Archive the OpenSpec change, sync specs, and validate.
- Land that work on `main` — committed and pushed by the cleanup itself in the default mode, or staged for the single convergence commit under `--defer-commit` (see `cleanup-feature` §1.6).
- Delete the local feature branch and release its locks for that change (`cleanup-feature` Step 8), in both modes.
- Treat dirty worktrees or branch deletion failures as operator-attention items, not silent force deletions.

If the operator declines, do not clean up local remnants. Record the declined cleanup commands in the summary and merge log.

If a post-merge cleanup command fails, stop the cleanup pass, preserve the error output in the summary, and do not proceed to the next cleanup command until the operator decides how to continue.

### 11.6. Main Context Convergence

This skill is the authoritative synchronization point for `main`, so it is also
where derived context is brought back into agreement with the tree that the merge
pass produced.

Convergence runs **once per invocation pass, not once per pull request**. A pass
that merges k pull requests produces exactly one resulting main state, so it gets
exactly one convergence: one commit, one record, one index request. This is
deliberately *not* part of the per-PR post-merge pipeline
(`scripts/post_merge_pipeline.py`), which runs k times — placing it there would
produce k commits racing each other for the same tip and k index requests for
revisions that are stale the moment the next PR lands.

If the pass merged nothing (k = 0), Step 11.6 is a read of `main`, not a write:
the driver reports `no-merges`, writes no commit and no record, and exits 0.

#### Phases

The three phases run in a fixed order, and the order is load-bearing.

**Phase 1 — OpenSpec cleanup, for every merged change, before any refresh.** Run
the list the operator approved in Step 11.5, in the approved order, with
`--defer-commit` appended:

```bash
/cleanup-feature <change-id> --post-merge --pr <pr_number> --defer-commit
```

Cleanup archives, merges the spec delta, regenerates the decision index, and
**stages** the result without committing (see `cleanup-feature` §1.6). The
`openspec.projection` and `decisions.timeline` producers read the archive, so a
refresh that ran first would be stale the instant the archive moved.

**Phases 2 and 3 — refresh and land, through the driver:**

```bash
python3 <agent-skills-dir>/merge-pull-requests/scripts/main_convergence.py \
  --merged-json <merged_prs_this_pass.json> \
  --merged-revision <full SHA of main after every merge in the pass>
```

The merged-PR records are the ones collected during Step 11 and shared with Step
11.5's approval helper. Without `--merged-json` the driver sees zero merges and
reports `no-merges` for a pass that merged something.

Architecture artifacts are refreshed with **`make architecture-refresh`**, the
staged target. Only that target writes provenance, and ri-10's producer routes
missing provenance to *drift* rather than to `not-configured` — so the bare
target would regenerate artifacts and still leave the gate red.

A pass with **no OpenSpec merge at all** — a dependabot or dependency-only pass —
still runs phases 2 and 3, through the same single operation (phase 1 is simply
empty). Skipping it would leave the context-drift gate red with no step anywhere
in the workflow that would ever fix it.

#### Guards, in enforcement order

1. **Active-agent guard.** Re-checked here, not inherited from the start of the
   pass: an agent may have set up a worktree during the merge loop.
2. **Coordinator lock** `sync-point:main-convergence`, held for all of Step 11.6.
   Coordinator **contention** — another writer holds the sync point — blocks.
   Coordinator **absence** or unavailability degrades to layers 1 and 3 with a
   warning; this repo runs solo often enough that a coordinator-only guard would
   be missing exactly when it matters.
3. **Pre-push compare-and-swap** against `origin/main`. This is the only layer a
   process that never asked for a lock cannot bypass.

**Never force a losing push.** Not `--force`, and not `--force-with-lease`
either: a lease that succeeds still overwrites the other writer's commit. At a
sync point, losing the race is information, not an obstacle. A lost race leaves
the operation **resumable** with nothing staged discarded — re-running Step 11.6
against the new tip picks up where it stopped.

#### Identity and idempotence

The operation is keyed on the **merged main SHA**. Keying on the set of merged PR
numbers is not stable across a retry, and a per-invocation UUID would defeat
resume entirely.

Two independent checks detect a prior convergence:

- the ri-06 **operation record**, which exists before the commit lands, and
- the `Context-Refresh-Operation:` **commit trailer**, which survives a fresh
  clone where local operation state does not.

If either finds one, the driver reports **already-converged** with the existing
identity and does nothing further.

**Set `PROJECT_CONTEXT_REPO_ID` in any environment that converges this repository
from more than one checkout path.** The operation id is
`sha256(domain \0 repository_id \0 merged_revision)`, and `repository_id` falls
back to the *repository directory name*. Two clones in differently named
directories therefore compute different ids for the same merged revision, and
neither finds the other's trailer — CI and a developer machine would each
believe they were first. The pre-push compare-and-swap still blocks the second
one (`push_race_lost`, exit 2, nothing pushed, resumable), so this degrades
safely rather than duplicating; but setting the variable is what makes the
trailer check work as intended. The ri-07 orchestrator honors the same variable,
so one value keeps both in agreement.

#### Outcomes

No convergence outcome reverts a merge. Merges are terminal by the time this step
runs: Step 11.6 **never un-merges**, never reverts, and never closes or re-opens a
pull request. Step 12 and Step 13 run regardless of the outcome — suppressing the
merge log because a derived artifact failed would lose the more valuable record.

| `refresh_status` | Meaning | Commit | Exit |
|---|---|---|---|
| `succeeded` | Cleanup and refresh both landed | convergence commit | 0 |
| `degraded` | Deterministic output landed; an optional producer degraded | convergence commit | 2 |
| `failed` | The refresh failed after cleanup staged its output | **cleanup-only** commit | 1 |
| `not-run` | Nothing to refresh, or the pass was blocked | cleanup-only, or none | 0 / 2 |

`degraded` is the **normal** outcome whenever the semantic index is deferred, and
`not-run` records a cleanup-only commit. Collapsing either into `failed` would
make a successful partial convergence indistinguishable from a crash. A failed
refresh still commits what cleanup staged, rather than discarding an archive that
already succeeded.

An **exit code from this step describes derived context only and never means a merge failed.**

#### Semantic index

The index is enqueued for the **final pushed revision** — the convergence commit,
not the merged revision, because the convergence commit changes main's tip and an
index for the merged revision would be stale on arrival. It is recorded as
`pending`; `semantic_index=None` would report a clean `succeeded` while making no
currency claim at all. It is **never awaited**: blocking a sync point on a
30-minute index rebuild would make the index a hard dependency of merging.

#### What lands, and what stays untracked

The tracked record is appended to **`docs/merge-logs/context-convergence.jsonl`**.
It pins the refresh manifest by path and `sha256` digest — that is what "the
manifest is committed" means in git-native form. The manifest itself stays in
`.git-context/` and stays **gitignored**; tracking it would reintroduce the
repository diff that ri-07 D6 exists to prevent.

#### Ownership boundary

Step 11.6 sequences and commits. It **never archives**, never performs the
spec-delta merge, and never migrates a task — those stay with `cleanup-feature`.
Duplicating archive logic across two skills would make the first divergence
silent spec corruption.

**Step 8 (local branch deletion and lock release) stays with
`cleanup-feature`, in both modes.** `cleanup-feature` §1.6 names only Step 8.5
(worktree removal) and Step 9 (clean-tree verification) as skipped under
`--defer-commit`; Step 8 is not skipped. The reason is lock release: it is
owner-scoped, and only the cleanup invocation knows which agent/session holds the
locks for that feature branch's files. The sync point mechanically cannot perform
it. Branch deletion travels with lock release rather than being split from it.

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
- Post-merge OpenSpec cleanup: #38 add-user-export (approved, completed)
- Post-merge OpenSpec cleanup declined: #44 improve-validation-flow
- Merge-time validation: #38 (deploy: pass, smoke: pass, security: skip, e2e: skip)
- Auto-rebase: refreshed #45, #47 (2 overlapping PRs)
- Auto-rollback: monitoring #42 (stable after 5 min)

## Merge Metrics
| Metric | Value |
|--------|-------|
| Merges | 2 |
| Reverts | 0 |
| Rebases | 2 |
| Success Rate | 100% |
| Backends | direct: 2 |

## Context Convergence
| Field | Value |
|-------|-------|
| Merged SHA | `<full SHA of main after every merge in the pass>` |
| Convergence commit | `<SHA of the single follow-up commit, or "none">` |
| Context-refresh SHA | `<final pushed revision on main>` |
| Refresh status | `succeeded` / `degraded` / `failed` / `not-run` |
| Semantic index | `pending` for `<final pushed revision>` / `not-configured` / `none` |
| Operation | `<identity>` (`converged` / `already-converged` / `no-merges` / `blocked` / `dry-run`) |
```

The merged SHA, the context-refresh SHA, and the semantic-index status are all
reported **for the final pushed revision** — that is the state a reader has to be
able to reason about, and it is not the merged revision whenever a convergence
commit landed on top of it.

When Step 11.6 reports `blocked` or a `failed` refresh, report it here and
continue: the merge results above are unaffected, and a non-zero convergence exit
never means a merge failed.

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

### Post-Merge Cleanup
- <OpenSpec cleanup approvals/declines/failures and commands run>

### Context Convergence
- Merged SHA: `<sha>` → convergence commit: `<sha or "none">` → pushed: `<sha>`
- Refresh status: `<succeeded|degraded|failed|not-run>` (`degraded` is normal when the index is deferred)
- Semantic index: `<pending for <sha> | not-configured | none>` — enqueued, never awaited
- Record: appended to `docs/merge-logs/context-convergence.jsonl` (manifest pinned by `sha256`)
- Guards: `<active-agent ok | coordinator lock held/degraded/contended | compare-and-swap ok/lost>`

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
python3 <agent-skills-dir>/merge-pull-requests/scripts/post_merge_cleanup.py --merged-json <merged_prs_this_pass.json>
python3 <agent-skills-dir>/merge-pull-requests/scripts/main_convergence.py --merged-json <merged_prs_this_pass.json> --dry-run
```

**Step 11.6 under `--dry-run` (D12)** converges nothing: no cleanup runs, no
refresh runs, no commit, no push, no record, no index request. It still reports
what a real pass would have done — the identity it *would* have used, whether a
convergence already exists for that identity, and a read-only drift assessment
from the check-mode gate. That combination is what makes the dry run useful: an
operator can see both that the pass would converge and what it would fix, without
a dry run ever being the thing that mutates `main`.

A dry run always exits 0, because "would have converged" is not a failure.

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

- `merge-plan.json` plus its non-mutating `merge-plan.md` projection when plan
  output is requested
- One-node execution results with persisted outcomes, blocking reasons,
  delegation hand-offs, and downstream revalidation flags
- PRs merged, closed, or skipped with reasons
- PRs added to merge queue (for repos that use it)
- Obsolete PRs batch-closed with explanatory comments
- OpenSpec change-ids offered for post-merge `/cleanup-feature --post-merge` approval
- Post-merge cleanup approvals, declines, completions, and failures
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
- **Post-merge cleanup declined**: Leave local OpenSpec worktrees/branches intact and record the declined cleanup command in the merge log
- **Post-merge cleanup failure**: Stop the cleanup pass and surface the failure; do not continue deleting local remnants for later changes without operator direction
- **Fork PRs**: Automatically skip `--delete-branch` (no push access to fork remote)
- **Stale approvals**: Warn when commits were pushed after the last review approval
- **Pending reviewers (CODEOWNERS)**: Surface pending reviewer requests even when `reviewDecision` shows APPROVED
- **Subprocess timeout**: All `gh`/`git` calls have timeouts (30-60s) to prevent hangs
- **API rate limits**: Scripts use `gh` CLI which handles token refresh; if rate-limited, wait and retry
- **Stacked PRs**: Warn about dependency chain before allowing close/merge
- **Convergence lock contention**: Another writer holds `sync-point:main-convergence` — block and report. Do not proceed without the lock; two convergences racing for the same tip is the failure the lock exists to prevent
- **Coordinator unavailable at convergence**: Degrade to the active-agent guard and the pre-push compare-and-swap, and warn. Absence is not contention, and a coordinator-only guard would be missing exactly when this repo runs solo
- **Convergence push race lost**: The compare-and-swap saw `origin/main` move. Never force and never `--force-with-lease`; the operation stays resumable with nothing staged discarded, so re-run Step 11.6 against the new tip
- **Deterministic producer failure during convergence**: Commit what cleanup already staged as a cleanup-only commit, report `refresh_status=failed` (exit 1), and continue to Steps 12 and 13. Never un-merge, never revert, never re-open a PR
- **Semantic index unavailable**: Record the index as `pending` or `not-configured` and continue. The index is enqueued for the final pushed revision and never awaited
- **Prior convergence found**: Either the ri-06 operation record or a `Context-Refresh-Operation:` trailer matched the merged main SHA — report `already-converged` with the existing identity and write nothing

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "I'll skip the Change Summary — the PR title is self-explanatory" | Titles compress; summaries enumerate. Reviewers waste time inferring scope from diffs when `DIDN'T TOUCH` would have answered the question in one line. |
| "`wip:` save points clutter history — I'll just be careful and not break anything" | Careful is a plan that fails the first time. Save points are insurance; squashing at merge erases the clutter. The cost is zero, the upside is recovering hours of lost progress. |
| "All my CONCERNS are minor — I'll write `CONCERNS: none`" | Non-trivial changes always have at least one open question. `none` signals either the author hasn't thought hard enough, or is hiding doubts to get the PR through. |
| "Auto-merge is on; I don't need to triage" | Auto-merge merges when checks pass — it doesn't catch obsolete fixes, conflicting PR pairs, or stale base-branch failures. Triage is the layer above auto-merge, not redundant with it. |
| "CI is flaky, just rerun" | `rerun-checks` replays the SAME merge commit. If the failure is a stale-base issue, rerun is theatre — `refresh-branch` is the real fix. See Step 5b. |
| "Nothing OpenSpec merged this pass, so there's nothing to converge" | Dependency and dependabot merges change the tree the deterministic producers read. Skipping convergence leaves the context-drift gate red with no step anywhere in the workflow that would ever fix it (D11). |
| "I'll converge per PR — it's the same work, just spread out" | k merges produce ONE resulting main state. Per-PR convergence produces k commits racing for the same tip and k index requests for revisions that are stale the moment the next PR lands (D1, D8). |
| "The push race is a transient — I'll just `--force-with-lease`" | A lease that succeeds still overwrites the other writer's commit. At a sync point, losing the race is information, not an obstacle: another writer converged, and re-running against the new tip is correct (D5). |
| "The refresh failed, so I should revert the merge to keep main clean" | Merges are terminal by the time Step 11.6 runs. A derived artifact is not a reason to un-merge reviewed, CI-green code — commit what cleanup staged and report the failure (D6). |
| "I'll wait for the semantic index so the summary can report it green" | Blocking a sync point on an index rebuild makes the index a hard dependency of merging. `pending` is the honest status; `succeeded` with no index is not (D7). |
| "`degraded` looks like a failure — I'll report it as failed" | `degraded` is the NORMAL outcome whenever the index is deferred. Collapsing it into `failed` makes a successful partial convergence indistinguishable from a crash. |

## Red Flags

- A merged PR's description has no `CHANGES MADE / DIDN'T TOUCH / CONCERNS` block.
- A PR's head commit starts with `wip:` and is being merged with `--rebase` (the wip commit will land on main).
- The same CI check fails identically across 3+ unrelated PRs but the operator keeps clicking "Re-run failed jobs" instead of refreshing branches.
- An obsolete-classified PR was merged anyway because "the diff looked harmless".
- The merge log for the day is empty even though PRs were merged (decision history lost).
- A stacked PR's base PR was closed without warning the operator about the chain.
- PRs were merged but the summary has no Context Convergence block (either the step was skipped, or its result was dropped).
- `docs/merge-logs/context-convergence.jsonl` has no entry for a pass that merged something and did not report `already-converged`.
- A convergence commit landed without a `Context-Refresh-Operation:` trailer — the next pass's idempotence check will not see it after a fresh clone.
- The convergence commit contains an archive but no regenerated `docs/decisions/` (cleanup deferred the commit but the regen was deferred with it).
- `.git-context/` appears in `git status` as tracked, or in a convergence commit's diff.
- A pass reported `succeeded` while the semantic index was never enqueued.

## Verification

1. The merge log entry for today (`docs/merge-logs/<YYYY-MM-DD>.md`) lists every PR processed with its origin, action, and rationale — not just the merged ones.
2. For every merged PR with a non-trivial diff (>50 lines or >3 files), the PR description contained the Change Summary template before merge (check via `gh pr view <pr> --json body`).
3. No commit on `main` has a message starting with `wip:` after this skill ran (`git log main --since=<start-time> --pretty=%s | grep -i ^wip:` returns empty).
4. Stale-base CI failures were resolved with `refresh-branch`, not repeated `rerun-checks` (the merge log records which strategy was used and why).
5. Obsolete PRs were closed with the explanatory comment (not silently), and the close reason is recorded in the merge log.
6. For every local OpenSpec PR merged during the pass, the summary and merge log record whether post-merge cleanup was approved, declined, skipped, or failed.
