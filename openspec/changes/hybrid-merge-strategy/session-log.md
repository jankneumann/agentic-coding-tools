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
