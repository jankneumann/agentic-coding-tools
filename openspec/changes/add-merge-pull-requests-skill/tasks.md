## 1. Skill Foundation
- [x] 1.1 Create `skills/merge-pull-requests/SKILL.md` with frontmatter and step-by-step workflow
- [x] 1.2 Create `skills/merge-pull-requests/scripts/` directory

## 2. PR Discovery
- [x] 2.1 Create `scripts/discover_prs.py` - Classify open PRs by origin (OpenSpec, Jules/Sentinel/Bolt/Palette, Codex, manual/other)
- [x] 2.2 Output structured JSON with PR metadata: number, title, author, origin classification, branch, created date, labels

## 3. Staleness Detection
- [x] 3.1 Create `scripts/check_staleness.py` - For a given PR, compare its diff against current main
- [x] 3.2 Detect files modified by the PR that have since changed on main
- [x] 3.3 Categorize staleness: fresh (no conflicts), stale (overlapping changes), obsolete (fix already applied)
- [x] 3.4 Special handling for Jules automation PRs: check if the security/performance/UX issue the PR addresses has already been fixed by other changes

## 4. Review Comment Analysis
- [x] 4.1 Create `scripts/analyze_comments.py` - Fetch unresolved review comments for a PR
- [x] 4.2 Summarize each comment thread: file, line, reviewer, status (resolved/unresolved), summary

## 5. Merge Execution
- [x] 5.1 Create `scripts/merge_pr.py` - Pre-merge validation (CI status, approval status, staleness check)
- [x] 5.2 Support merge strategies: squash (default), merge commit, rebase
- [x] 5.3 Handle OpenSpec PRs: trigger `/cleanup-feature` integration if change-id detected

## 6. Batch Close Obsolete PRs
- [x] 6.1 Add batch-close support to `scripts/merge_pr.py` - close multiple PRs with obsolescence comments
- [x] 6.2 Integrate batch-close step into SKILL.md workflow after staleness detection

## 7. Dry-Run Mode
- [x] 7.1 Add `--dry-run` flag handling to all scripts (report-only, no mutations)
- [x] 7.2 Define dry-run output format: full report with classifications, staleness, and comments

## 8. Skill Workflow Integration
- [x] 8.1 Wire all scripts into SKILL.md step-by-step workflow
- [x] 8.2 Define interactive decision points (skip/merge/close per PR)
- [x] 8.3 Document prerequisites and error handling
