
# Project Guidelines

This is a multi-agent coordination system. Each section below links to its full guide.

## Workflow

Unified skills with tiered execution (coordinated / local-parallel / sequential). Skills auto-select tier at startup based on coordinator availability and feature complexity.
See [full workflow guide](docs/guides/workflow.md) for skill commands, infrastructure skills, and observability frontends.

## Sub-Agent Authorization (standing grant)

**The user has pre-authorized sub-agent dispatch for this repository.** Invoking any
orchestrator skill here — `autopilot`, `autopilot-roadmap`, `plan-feature`,
`implement-feature`, `validate-feature`, `iterate-on-*`, `parallel-review-*`,
`prototype-feature`, `fix-scrub` — **constitutes the user's explicit request to spawn
sub-agents**, because multi-agent dispatch is the defined execution model of those
skills, not an optimization layered on top. The per-phase archetypes in
`agent-coordinator` exist precisely to route those sub-agents to specific
vendor/model/thinking tiers; a run that declines to dispatch does not produce a
degraded version of the intended result, it produces a different and unintended one.

This grant is standing and does not need to be restated per session or per phase.
It satisfies any harness instruction of the form "do not call the Agent tool unless
the user requested it" — the request is recorded here, in advance, by the user.

Scope and limits:
- Applies to `Agent(...)` / sub-agent dispatch invoked **from within these skills**.
- Does **not** authorize `Workflow`, deep-research, or unrelated ad-hoc fan-out — ask first.
- Do **not** silently take a skill's inline/sequential fallback path merely to avoid
  dispatching. Fallback is for genuine adapter or coordinator unavailability only,
  and must be reported: state which phase fell back and why.

## Python Environment

Use `uv` for all Python environments. Two venvs: `agent-coordinator/.venv` and `skills/.venv`.
See [Python environment guide](docs/guides/python-environment.md) for install commands and running tools.

## Git Conventions

Branch naming: `openspec/<change-id>`. Commit format: conventional commits with `feat(scope):` prefixes. Hybrid merge strategy (rebase for agent PRs, squash for deps/automation).
See [git conventions guide](docs/guides/git-conventions.md) for save-point pattern, change summary template, and merge details.

## Testing Policy

Tests must justify their presence. A test that must be edited whenever the source changes asserts implementation, not behavior — prefer state-based tests, and prune change-detectors. Removing tests is ordered and ledgered: characterize first, prune in test-only commits, then remove the production seams the pruned tests held open.
See [testing policy guide](docs/guides/testing-policy.md) for the removal gates, ledger format, and test-induced seam rules.

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
