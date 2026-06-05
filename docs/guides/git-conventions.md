# Git Conventions

- **Branch naming**: `openspec/<change-id>` for OpenSpec-driven features
- **Commit format**: Reference the OpenSpec change-id in commit messages
- **Commit quality**: Agent-authored PRs use rebase-merge (commits appear individually on main). Write logical, conventional commits — one per task, no WIP fragments. Use `feat(scope):`, `fix(scope):`, `test(scope):`, `docs(scope):` prefixes.
- **Merge strategy (hybrid)**: Strategy varies by PR origin. Agent PRs (`openspec`, `codex`) default to **rebase-merge** to preserve granular history. Dependency updates (`dependabot`, `renovate`) and automation PRs (`sentinel`, `bolt`, `palette`) default to **squash-merge**. Manual PRs default to squash. Operator can override per-PR via `--strategy` flag.
- **PR template**: Include link to `openspec/changes/<change-id>/proposal.md`
- **Plan refinement branches**: `/iterate-on-plan` commits to the proposal/feature branch from a managed worktree. Planning artifacts land on main only through PR review and a sync-point merge.
- **Rebase ours/theirs inversion**: During `git rebase`, `--ours` = the branch being rebased ONTO (upstream), `--theirs` = the commit being replayed. This is the opposite of `git merge`. When resolving rebase conflicts to keep upstream, use `git checkout --ours`.

## Save Point Pattern and Change Summary Template

**Save Point Pattern**: While iterating on a complex change, commit at each working slice (use `wip:` prefix). Squash before final merge. Lets you revert to a known-good state without losing progress.

**Change Summary template**: Include in every agent-authored PR description:

```
CHANGES MADE: <bullet list>
DIDN'T TOUCH: <out-of-scope items intentionally not addressed>
CONCERNS: <known issues, follow-ups, things reviewers should challenge>
```

For the full pattern, see `skills/merge-pull-requests/SKILL.md`.
