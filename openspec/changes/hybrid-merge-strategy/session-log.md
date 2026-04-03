---

## Phase: Plan (2026-04-02)

**Agent**: claude | **Session**: N/A

### Decisions
1. **Per-origin strategy defaults** — Selected over auto-detection (Approach B) and always-rebase (Approach C) because it leverages existing origin classification with minimal complexity
2. **Commit quality enforcement at implementation time** — Rather than cleaning up history at merge time, require agents to produce clean conventional commits during `/implement-feature`
3. **Doc-only approach** — Minimal delta spec added for merge strategy selection; no heavy formal spec changes
4. **Repo settings update included** — Enable rebase-merge alongside squash in GitHub repo settings via `gh api`

### Alternatives Considered
- Commit quality auto-detection: rejected because origin is a reliable enough proxy and avoids new analysis code
- Always rebase-merge: rejected because `git rebase -i` is not supported in non-interactive agent contexts
- Formal spec requirements: rejected because the change is primarily workflow policy, not behavioral contracts

### Trade-offs
- Accepted origin-as-proxy over direct commit analysis because simplicity outweighs precision for this use case
- Accepted that manual PRs (`other` origin) default to squash even though some may have clean history — operator can override

### Open Questions
- [ ] Should we add a commit quality pre-merge check as a future refinement (Approach B as follow-up)?
- [ ] Should the strategy mapping be configurable per-repo or hardcoded?

### Context
The planning session originated from a merge-pull-requests triage where 23 stale branches and 15 stale worktrees were discovered — all caused by squash-merge breaking `git branch --merged` detection. The discussion identified that squash-merge's primary benefit (cognitive clutter reduction) doesn't apply to AI assistants, while its costs (lost history, broken branch detection) are amplified in agentic workflows.

---

## Phase: Plan Iteration 1 (2026-04-02)

**Agent**: claude | **Session**: N/A

### Decisions
1. **Expanded spec coverage** — Added scenarios for all origin groups (agent, dependency, automation), conflict failure, and CLI override. Original spec only covered openspec and dependabot.
2. **Explicit parallelizability annotation** — Added parallelizability section to tasks.md showing 4-wide parallel potential
3. **Corrected function references** — Fixed `merge()` → `merge_pr()` to match actual codebase (line 354)

### Alternatives Considered
- Auto-fallback to squash on rebase conflict: rejected — operator should decide, not the tool

### Trade-offs
- Added 2 more scenarios (5 total) for completeness at the cost of slightly more implementation work in tests

### Open Questions
- None new

### Context
9 findings identified (2 high, 5 medium, 2 low). All high and medium findings addressed: missing failure scenario, missing codex coverage, wrong function name, missing Impact section, incorrect spec references in tasks, missing parallelizability assessment. Low findings (help text wording, scenario WHEN precision) also addressed.

---

## Phase: Implementation (2026-04-02)

**Agent**: claude | **Session**: N/A

### Decisions
1. **Strategy resolution at CLI level** — `resolve_strategy()` runs in `main()` before calling `merge_pr()`, keeping the core function signature unchanged. This is the least invasive change.
2. **None sentinel for --strategy** — Changed default from `"squash"` to `None` so the code can distinguish "operator didn't specify" from "operator chose squash"
3. **No repo settings change needed** — `allow_rebase_merge` was already `true` in the GitHub repo settings. Task 4.1 became a verification-only step.

### Alternatives Considered
- Passing origin into `merge_pr()` function: rejected because it would change the function signature and affect all callers. CLI-level resolution is cleaner.

### Trade-offs
- Kept the pre-existing lint issues in merge_pr.py untouched (unused `safe_author` import, unused `raw` variable) to minimize diff scope

### Open Questions
- None

### Context
Implementation followed the plan exactly. Three commits: core script change with tests (16 tests, all pass), documentation updates across 6 files, and a lint fix for the test file. All quality checks pass (pytest, openspec validate, ruff on new code).

---

## Phase: Implementation Iteration 1 (2026-04-02)

**Agent**: claude | **Session**: N/A

### Decisions
1. **Use args.origin directly** — Removed unnecessary `getattr()` wrapper since the argument is always defined via `add_argument`
2. **Connect origin to discovery output** — Added note in SKILL.md linking `--origin` to `discover_prs.py` output field
3. **Fix test docstring grouping** — Converted bare string literals to comments for clarity

### Alternatives Considered
- Adding origin parameter to `merge_pr()` function signature: rejected to minimize scope — CLI-level resolution is sufficient

### Trade-offs
- Left 2 pre-existing lint issues untouched (unused `safe_author` import, unused `raw` variable) to keep diff focused

### Open Questions
- None

### Context
5 findings (3 medium, 2 low). All addressed: removed defensive getattr, clarified SKILL.md origin source, cleaned up test organization. 16 tests still pass.
