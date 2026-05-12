# worktree Specification

## Purpose
TBD - created by archiving change conditional-worktree-generation. Update Purpose after archive.
## Requirements
### Requirement: Worktree operations SHALL be conditional on the execution environment

The `worktree` skill SHALL expose a single detection function, `EnvironmentProfile.detect()`, that returns whether the caller's environment already provides filesystem isolation. Every `worktree.py` subcommand and `merge_worktrees.py` entrypoint SHALL consult this function before performing any git worktree mutation. When `isolation_provided` is `true`, the operation MUST NOT create, modify, or delete entries under `.git-worktrees/`; when `false`, existing behavior SHALL be preserved.

#### Scenario: Local single-agent run creates a worktree (default)

- **WHEN** `AGENT_EXECUTION_ENV` is unset AND the coordinator does not report `isolation_provided` for the current agent-id AND no container heuristics match
- **AND** the operator invokes `python3 skills/worktree/scripts/worktree.py setup <change-id>`
- **THEN** `EnvironmentProfile.detect()` returns `EnvironmentProfile(isolation_provided=false, source="default")`
- **AND** `worktree.py` SHALL create `.git-worktrees/<change-id>/` via `git worktree add`
- **AND** the command SHALL emit `WORKTREE_PATH=<path> WORKTREE_BRANCH=<branch>` on stdout for `eval`

#### Scenario: Cloud harness short-circuits setup

- **WHEN** `AGENT_EXECUTION_ENV=cloud` is set in the environment
- **AND** the operator invokes `python3 skills/worktree/scripts/worktree.py setup <change-id>`
- **THEN** `EnvironmentProfile.detect()` SHALL return `EnvironmentProfile(isolation_provided=true, source="env_var")`
- **AND** `worktree.py` MUST NOT invoke `git worktree add`
- **AND** the command SHALL emit `WORKTREE_PATH=$(git rev-parse --show-toplevel) WORKTREE_BRANCH=$(git branch --show-current)` on stdout
- **AND** the command SHALL exit 0

#### Scenario: Teardown, pin, unpin, heartbeat, and gc no-op under cloud mode

- **WHEN** `isolation_provided=true`
- **AND** the operator invokes any of `teardown`, `pin`, `unpin`, `heartbeat`, `gc`
- **THEN** `worktree.py` MUST NOT modify `.git-worktrees/` or `.git-worktrees/.registry.json`
- **AND** the command SHALL exit 0
- **AND** the command SHALL log a single line to stderr identifying the short-circuit source (e.g., `worktree: skipped teardown (isolation_provided=true, source=env_var)`)

#### Scenario: Read-only introspection continues to function

- **WHEN** `isolation_provided=true`
- **AND** the operator invokes `list`, `status`, or `resolve-branch`
- **THEN** `worktree.py` SHALL execute normally
- **AND** `status` SHALL report the in-place checkout as the current worktree (path = `git rev-parse --show-toplevel`, branch = `git branch --show-current`)
- **AND** `resolve-branch` SHALL continue to honor `OPENSPEC_BRANCH_OVERRIDE` and the `--parent` flag

### Requirement: Detection SHALL follow a documented precedence order

`EnvironmentProfile.detect()` SHALL evaluate signals in this order and return the first definitive result:

1. Explicit env var `AGENT_EXECUTION_ENV`: value `cloud` → `isolation_provided=true, source="env_var"`; value `local` → `isolation_provided=false, source="env_var"`. Legacy `CLAUDE_CODE_CLOUD=1` MUST be accepted as cloud.
2. Coordinator discovery: when the coordinator is reachable AND the current agent-id is registered, query `GET /agents/<agent-id>` (or equivalent MCP tool) for `isolation_provided`. If present, use it with `source="coordinator"`.
3. Container heuristic: `isolation_provided=true, source="heuristic"` when any of `/.dockerenv` exists, `KUBERNETES_SERVICE_HOST` is non-empty, or `CODESPACES=true`.
4. Default: `isolation_provided=false, source="default"`.

#### Scenario: Env var overrides coordinator and heuristic

- **WHEN** `AGENT_EXECUTION_ENV=local` is set
- **AND** `/.dockerenv` exists (heuristic would vote cloud)
- **AND** the coordinator reports `isolation_provided=true` for the agent-id
- **THEN** `EnvironmentProfile.detect()` SHALL return `isolation_provided=false, source="env_var"`

#### Scenario: Coordinator overrides heuristic

- **WHEN** `AGENT_EXECUTION_ENV` is unset
- **AND** the coordinator reports `isolation_provided=false` for the agent-id
- **AND** `/.dockerenv` exists
- **THEN** `EnvironmentProfile.detect()` SHALL return `isolation_provided=false, source="coordinator"`

#### Scenario: Heuristic fires when env var and coordinator are silent

- **WHEN** `AGENT_EXECUTION_ENV` is unset
- **AND** the coordinator is unreachable OR does not report `isolation_provided` for the agent-id
- **AND** `KUBERNETES_SERVICE_HOST=svc.cluster.local` is set
- **THEN** `EnvironmentProfile.detect()` SHALL return `isolation_provided=true, source="heuristic"`
- **AND** the detector SHALL log one line to stderr identifying the heuristic used

### Requirement: `OPENSPEC_BRANCH_OVERRIDE` SHALL remain orthogonal to the new signal

The detection function MUST NOT consult `OPENSPEC_BRANCH_OVERRIDE`. The branch override continues to control the branch name that `worktree.py setup` resolves; the new signal controls whether a separate worktree is created at all. The two concepts compose but do not imply each other.

#### Scenario: Branch override without cloud signal still creates a worktree

- **WHEN** `OPENSPEC_BRANCH_OVERRIDE=claude/review-branch` is set
- **AND** `AGENT_EXECUTION_ENV` is unset AND no coordinator/heuristic signal fires
- **AND** the operator invokes `python3 skills/worktree/scripts/worktree.py setup <change-id>`
- **THEN** `worktree.py` SHALL create `.git-worktrees/<change-id>/` with branch `claude/review-branch`

#### Scenario: Cloud signal without branch override short-circuits

- **WHEN** `AGENT_EXECUTION_ENV=cloud` is set
- **AND** `OPENSPEC_BRANCH_OVERRIDE` is unset
- **AND** the operator invokes `python3 skills/worktree/scripts/worktree.py setup <change-id>`
- **THEN** `worktree.py` SHALL emit `WORKTREE_BRANCH=$(git branch --show-current)` (whatever the harness checked out)
- **AND** SHALL NOT create `.git-worktrees/<change-id>/`

### Requirement: `merge_worktrees.py` SHALL short-circuit under cloud mode

When `isolation_provided=true`, `merge_worktrees.py` SHALL exit 0 without attempting to resolve per-package branch paths, run `git merge`, or write to `.git-worktrees/.registry.json`. It SHALL emit a single guidance line to stderr explaining that integration happens via PR in cloud mode and that the caller should use the feature branch's pull request instead.

#### Scenario: Cloud merge short-circuits with guidance

- **WHEN** `AGENT_EXECUTION_ENV=cloud` is set
- **AND** the operator invokes `python3 skills/worktree/scripts/merge_worktrees.py <change-id> wp-backend wp-frontend`
- **THEN** the script MUST NOT invoke `git merge` or read package branch registry entries
- **AND** SHALL exit 0
- **AND** SHALL print to stderr: `merge_worktrees: skipped (isolation_provided=true, source=env_var); use PR-based integration`

### Requirement: Backward compatibility SHALL be preserved for existing local workflows

All existing local single-agent and local-parallel workflows SHALL observe identical behavior to pre-change releases when none of the detection signals fire.

#### Scenario: Existing local single-agent plan-feature run is unchanged

- **WHEN** a fresh local checkout with no coordinator running and no cloud env vars set
- **AND** the operator invokes `/plan-feature <change-id>` which calls `eval "$(worktree.py setup <change-id>)"`
- **THEN** `.git-worktrees/<change-id>/` SHALL be created exactly as before
- **AND** `WORKTREE_PATH` and `WORKTREE_BRANCH` SHALL point at the new worktree (not the shared checkout)
- **AND** no new stderr output SHALL be emitted (unchanged log surface)

#### Scenario: Existing local-parallel implement-feature run is unchanged

- **WHEN** a local coordinator is running AND `AGENT_EXECUTION_ENV` is unset
- **AND** the coordinator reports `isolation_provided=false` (or omits the field) for the dispatched agent-id
- **AND** the operator invokes `/implement-feature <change-id>` which dispatches parallel work-package agents with `--agent-id`
- **THEN** each agent SHALL create its own `.git-worktrees/<change-id>/<agent-id>/` worktree on branch `<parent>--<agent-id>`
- **AND** `merge_worktrees.py` SHALL integrate the package branches into the feature branch exactly as before

