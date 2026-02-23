
# Project Guidelines

## Workflow

Use the 5-skill feature workflow with natural approval gates:

```
/explore-feature [focus-area] (optional)      → Candidate shortlist for next work
/plan-feature <description>                    → Proposal approval gate
  /iterate-on-plan <change-id> (optional)      → Refines plan before approval
/implement-feature <change-id>                 → PR review gate
  /iterate-on-implementation <change-id> (optional)  → Refinement complete
  /validate-feature <change-id> (optional)     → Live deployment verification (includes security scanning)
/cleanup-feature <change-id>                   → Done
```

## Python Environment

- **uv for all Python environments**: Use `uv` (not pip, pipenv, or poetry) for dependency management and virtual environments across all Python projects. CI uses `astral-sh/setup-uv@v5`.
- **agent-coordinator**: `cd agent-coordinator && uv sync --all-extras` to install. Venv at `agent-coordinator/.venv`.
- **scripts**: `cd scripts && uv sync` to install. Venv at `scripts/.venv`.
- **Running tools**: Activate the relevant venv first (`source .venv/bin/activate`) or use the venv's Python directly (e.g., `scripts/.venv/bin/python -m pytest`).

## Git Conventions

- **Branch naming**: `openspec/<change-id>` for OpenSpec-driven features
- **Commit format**: Reference the OpenSpec change-id in commit messages
- **PR template**: Include link to `openspec/changes/<change-id>/proposal.md`
- **Push plan refinement commits promptly**: `/iterate-on-plan` commits to local main. Push these to remote before other PRs merge, or they cause divergence during `/cleanup-feature`. Alternatively, make plan refinements on the feature branch.
- **Rebase ours/theirs inversion**: During `git rebase`, `--ours` = the branch being rebased ONTO (upstream), `--theirs` = the commit being replayed. This is the opposite of `git merge`. When resolving rebase conflicts to keep upstream, use `git checkout --ours`.

## Documentation

- [Lessons Learned](docs/lessons-learned.md) — Skill design patterns, parallelization, OpenSpec integration, validation, cross-skill Python patterns
- [Architecture Artifacts](docs/architecture-artifacts.md) — Auto-generated codebase analysis, key files, refresh commands
- [Skills Workflow](docs/skills-workflow.md) — Workflow guide, stage-by-stage explanation, design principles
- [Agent Coordinator](docs/agent-coordinator.md) — Architecture overview, capabilities, design pointers
