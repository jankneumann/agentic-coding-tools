## Context

Multiple AI coding agents create PRs against the same repo. Jules automations (Sentinel, Bolt, Palette) create fix PRs that may become stale. OpenSpec-driven PRs may have review comments that need addressing. Manual/Codex PRs need standard review. The skill needs to handle all these cases in a single triage workflow.

## Goals / Non-Goals

- **Goals:**
  - Discover and classify all open PRs by origin
  - Detect stale automated PRs where fixes are no longer relevant
  - Surface unresolved review comments that need attention
  - Provide an interactive merge workflow with per-PR decisions
  - Integrate with existing OpenSpec cleanup workflow for OpenSpec PRs

- **Non-Goals:**
  - Automatic merging without human/agent review (always interactive)
  - Creating PRs (that's `/implement-feature`'s job)
  - Resolving merge conflicts automatically (flag and surface, don't auto-resolve)
  - CI pipeline management

## Decisions

### Python for helper scripts
- **Decision**: Use Python for all scripts over 50 lines; keep simple shell one-liners in SKILL.md
- **Rationale**: Per project guidelines, Python preferred over bash for maintainability. Scripts use `subprocess` to call `gh` and `git` CLI tools, plus JSON parsing which is cleaner in Python.

### PR Classification by heuristics
- **Decision**: Classify PRs using branch name patterns, author, labels, and PR body content
- **Heuristics**:
  - OpenSpec: branch matches `openspec/*` or body contains `Implements OpenSpec:`
  - Jules/Sentinel: author is Jules bot OR labels contain `sentinel`/`security`, branch contains `sentinel`
  - Jules/Bolt: similar pattern with `bolt`/`performance`
  - Jules/Palette: similar pattern with `palette`/`ux`
  - Codex: author is Codex bot OR branch contains `codex`
  - Other: everything else
- **Alternatives**: Could use GitHub App installation metadata, but heuristics are simpler and don't require API auth beyond standard `gh`

### Staleness detection approach
- **Decision**: Compare PR's changed files against `git log --name-only main..HEAD` since PR creation date
- **Three staleness levels**:
  1. **Fresh**: No overlapping file changes on main since PR creation
  2. **Stale**: Same files modified on main, but changes don't conflict semantically
  3. **Obsolete**: The specific issue the PR fixes has already been addressed (detected by checking if the PR's diff hunks apply cleanly and whether the "before" state still exists)
- **For Jules PRs**: Extra check - does the problematic code pattern the PR fixes still exist on main? If not, the fix is obsolete.

### Interactive workflow
- **Decision**: Present a summary table, then process PRs one at a time with actions: merge, skip, close, address-comments
- **Rationale**: Fully automatic merging is risky. The skill orchestrates but the operator (human or Claude session) makes decisions per PR.

## Risks / Trade-offs

- **Heuristic misclassification** → Mitigation: Show classification in output, allow override
- **Staleness false positives** → Mitigation: Show detailed file overlap, let operator decide
- **gh CLI rate limits** → Mitigation: Batch API calls where possible, cache PR data locally during session
- **Jules automation format changes** → Mitigation: Heuristics are configurable patterns, easy to update

## Resolved Questions

- **Batch-closing obsolete PRs**: Yes. After the discovery/staleness phase, the skill offers to batch-close all PRs classified as obsolete in one step before proceeding to interactive per-PR review.
- **Dry-run mode**: Yes. When `--dry-run` is passed as an argument, the skill runs discovery, classification, staleness detection, and comment analysis, then outputs a full report without offering any merge/close actions.
