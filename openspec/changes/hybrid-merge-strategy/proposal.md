# Proposal: Hybrid Merge Strategy for Agentic Workflows

## Why

Squash merge was designed to reduce cognitive clutter for human developers scanning `git log`. In agentic coding workflows, this benefit is diminished — AI assistants can process granular commit history and extract richer context from it. Meanwhile, squash merge introduces operational costs:

1. **Lost granular history**: `git blame` points to the PR, not the specific sub-change that introduced a line. `git bisect` can only pinpoint at PR granularity, not individual commits.
2. **Broken branch detection**: `git branch --merged` cannot detect squash-merged branches, causing stale branch accumulation (observed during cleanup on 2026-04-02 — 23 stale branches, 15 stale worktrees).
3. **Lost reasoning arc**: Agent commit sequences (interface → implementation → tests) encode design intent that squash erases.

However, not all PRs benefit from preserved history. Dependabot bumps, single-commit fixes, and noisy WIP histories are better squashed.

## What Changes

Adopt a **hybrid merge strategy** where the merge method varies by PR origin and commit quality:

- **Rebase-merge** for agent-authored PRs (OpenSpec, Codex) with clean commit histories — preserves granular context
- **Squash-merge** for dependency updates (Dependabot, Renovate) and noisy histories — keeps main clean
- **Commit quality enforcement** in `/implement-feature` — agents must produce logical, conventional commits (one per task)
- **Repo settings** updated to allow both rebase-merge and squash-merge methods

### Scope

**In scope:**
- Update `merge_pr.py` default strategy selection to be origin-aware
- Update `/merge-pull-requests` SKILL.md to document hybrid strategy
- Update `/cleanup-feature` SKILL.md merge examples
- Update `/implement-feature` SKILL.md commit quality guidance
- Update `CLAUDE.md` git conventions section
- Update `docs/skills-workflow.md` with merge strategy rationale
- Update GitHub repo settings to allow rebase-merge
- Add merge strategy rationale to `docs/lessons-learned.md`

**Out of scope:**
- Changes to `skill-workflow` spec (merge strategy is documented in skill docs, not formalized as workflow requirements)
- Automated commit quality linting (future work)
- Changes to merge queue configuration

## Impact

- **merge-pull-requests**: Modified — adds origin-aware strategy selection requirement with 5 scenarios

## Approaches Considered

### Approach A: Per-Origin Strategy Defaults (**Recommended**)

Modify `merge_pr.py` to select strategy based on PR origin classification. The origin is already computed by `discover_prs.py`, so this is a natural extension point.

**Strategy mapping:**

| Origin | Default Strategy | Rationale |
|--------|-----------------|-----------|
| `openspec` | rebase | Agent PRs with structured commits — preserve history |
| `codex` | rebase | Same as OpenSpec — agent-generated, structured |
| `sentinel`, `bolt`, `palette` | squash | Jules automation — typically single-purpose fixes |
| `dependabot`, `renovate` | squash | Dependency bumps — one logical change |
| `other` | squash | Manual PRs — unknown commit quality, safe default |

The operator can always override via the interactive review step.

- **Pros**: Leverages existing origin classification; no new infrastructure; operator override preserved; gradual — only agent PRs change behavior
- **Cons**: Origin is a proxy for commit quality, not a direct measure; operator must remember the defaults
- **Effort**: S

### Approach B: Commit Quality Auto-Detection

Add a pre-merge analysis step that examines commit messages and diff sizes to determine strategy automatically:
- All commits follow conventional format → rebase-merge
- Any commits with "wip", "fixup", "temp" → squash
- Single commit → squash (nothing to preserve)

- **Pros**: Strategy decision is based on actual commit quality, not origin proxy; works for any PR origin
- **Cons**: More complex; requires new analysis code; edge cases (what about "fix: typo" repeated 5 times?); slower merge workflow
- **Effort**: M

### Approach C: Always Rebase-Merge with Pre-Merge Cleanup

Switch entirely to rebase-merge as default. Add a pre-merge cleanup step to `/cleanup-feature` and `/merge-pull-requests` that runs `git rebase -i` to squash fixup commits before merging.

- **Pros**: Consistent strategy; commit history is always clean; no proxy-based decisions
- **Cons**: Interactive rebase is complex to automate; risks introducing conflicts; adds a mandatory step to every merge; `git rebase -i` is not supported in non-interactive agent contexts
- **Effort**: L

### Selected Approach

**Approach A: Per-Origin Strategy Defaults** — selected because it's the simplest change that delivers the core benefit (preserving agent commit history) while maintaining squash for origins where it's clearly better. The origin classification already exists and is reliable. Approach B's auto-detection could be added later as a refinement.

## Dependencies

- None — all changes are within existing skills and documentation

## Risks

- **Merge conflicts on rebase**: Rebase-merge can fail if the branch has conflicts with main. Mitigation: the merge script already detects conflicts and surfaces them; the operator can fall back to squash.
- **Noisy agent commits on main**: If an agent produces poor commits, rebase-merge preserves them. Mitigation: commit quality enforcement in `/implement-feature` prevents this at the source.
