
# Project Guidelines

This is a multi-agent coordination system. Each section below links to its full guide.

## Workflow

Unified skills with tiered execution (coordinated / local-parallel / sequential). Skills auto-select tier at startup based on coordinator availability and feature complexity.
See [full workflow guide](docs/guides/workflow.md) for skill commands, infrastructure skills, and observability frontends.

## Python Environment

Use `uv` for all Python environments. Two venvs: `agent-coordinator/.venv` and `skills/.venv`.
See [Python environment guide](docs/guides/python-environment.md) for install commands and running tools.

## Git Conventions

Branch naming: `openspec/<change-id>`. Commit format: conventional commits with `feat(scope):` prefixes. Hybrid merge strategy (rebase for agent PRs, squash for deps/automation).
See [git conventions guide](docs/guides/git-conventions.md) for save-point pattern, change summary template, and merge details.

## Skills

Canonical source: `skills/` at repo root. Runtime copies (`.claude/skills/`, `.agents/skills/`) are overwritten by `install.sh`. Tests go in `skills/tests/<skill-name>/`.
See [skills guide](docs/guides/skills.md) for sync commands and conventions.

## Worktree Management

Every mutating skill works in a managed worktree, never the shared checkout. Cloud-harness environments short-circuit worktree ops. Branch naming uses `--` separator.
See [worktree management guide](docs/guides/worktree-management.md) for commands, sync-point skills, and execution-environment detection.

## Documentation

Foundational docs (read before contributing), discovery and reference, setup and deployment, coordination reference, and subdirectory index.
See [documentation guide](docs/guides/documentation.md) for the full categorized link list.

## Landing the Plane (Session Completion)

Work is NOT complete until `git push` succeeds. Seven-step mandatory workflow: file issues, run quality gates, update status, push, clean up, verify, hand off.
See [session completion guide](docs/guides/session-completion.md) for the full checklist and critical rules.
