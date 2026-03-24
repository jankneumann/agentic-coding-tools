## ADDED Requirements

### Requirement: Launcher Invariant (All Write Skills)

Every skill that modifies git state (commit, branch checkout, merge) SHALL operate in a worktree, never on the shared checkout. The shared checkout is a read-only launcher.

- The launcher invariant SHALL apply to: `parallel-plan-feature`, `linear-plan-feature`, `parallel-implement-feature`, `linear-implement-feature`, `parallel-cleanup-feature`, `linear-cleanup-feature`
- The launcher invariant SHALL NOT apply to read-only skills: `*-explore-feature`, `*-review-*`, `*-validate-feature`
- Skills SHALL call `scripts/worktree.py setup <change-id>` (feature-level) or `scripts/worktree.py setup <change-id> --agent-id <id>` (package-level) as their first write-capable step
- No skill SHALL run `git add`, `git commit`, `git checkout`, or `git merge` in the shared checkout directory

#### Scenario: Two planning sessions from same checkout
- **WHEN** terminal 1 runs `/parallel-plan-feature` for change `feature-a` and terminal 2 runs `/parallel-plan-feature` for change `feature-b` from the same checkout
- **THEN** terminal 1 creates worktree `.git-worktrees/feature-a/` on branch `openspec/feature-a`
- **AND** terminal 2 creates worktree `.git-worktrees/feature-b/` on branch `openspec/feature-b`
- **AND** both commit their planning artifacts to their respective branches
- **AND** the shared checkout is never modified

#### Scenario: Planning worktree reused by implementation
- **WHEN** `/parallel-plan-feature` completes and pins its worktree
- **AND** user approves and runs `/parallel-implement-feature` for the same change
- **THEN** implementation reuses the existing feature branch (with planning artifacts)
- **AND** creates sub-worktrees for each package from that branch

---

### Requirement: Planning Skills Use Feature-Level Worktrees

`parallel-plan-feature` and `linear-plan-feature` SHALL create a feature-level worktree for artifact creation, committing planning artifacts to the feature branch.

- Planning skills SHALL call `worktree.py setup <change-id>` (no agent-id) at skill start
- All artifact creation (`openspec new change`, writing proposal/design/specs/tasks/work-packages) SHALL happen inside the worktree
- Planning skills SHALL commit artifacts to branch `openspec/<change-id>` and push
- Planning skills SHALL pin the worktree after completion (for reuse by implementation)

#### Scenario: Parallel plan feature uses worktree
- **WHEN** user runs `/parallel-plan-feature "add user auth"` with change-id `add-user-auth`
- **THEN** skill creates worktree `.git-worktrees/add-user-auth/` on branch `openspec/add-user-auth`
- **AND** all OpenSpec artifacts are created inside that worktree
- **AND** artifacts are committed and pushed on `openspec/add-user-auth`
- **AND** worktree is pinned for reuse

---

### Requirement: Cleanup Skills Use Worktrees

`parallel-cleanup-feature` and `linear-cleanup-feature` SHALL perform merge, archive, and branch operations inside a worktree.

- Cleanup skills SHALL call `worktree.py setup <change-id> --agent-id cleanup` at skill start
- All merge (`gh pr merge`), archive (`openspec archive`), and branch operations SHALL happen inside the cleanup worktree
- After cleanup completes, the skill SHALL teardown all remaining worktrees for the change-id and run `worktree.py gc`

#### Scenario: Parallel cleanup uses worktree
- **WHEN** user runs `/parallel-cleanup-feature add-user-auth`
- **THEN** skill creates worktree `.git-worktrees/add-user-auth/cleanup/`
- **AND** performs merge and archive operations inside that worktree
- **AND** tears down all worktrees for `add-user-auth` after completion

---

### Requirement: Implementation Orchestrator Worktree Setup

The `parallel-implement-feature` orchestrator SHALL create a dedicated worktree for every work package — including root packages — before implementation begins.

- The orchestrator SHALL call `scripts/worktree.py setup <change-id> --agent-id <package-id>` for every package (root and parallel) before implementation
- The orchestrator SHALL NEVER modify the shared checkout directly — it is a read-only launcher
- The orchestrator SHALL implement root packages (no dependencies) sequentially in their own worktrees, merging each into the feature branch before parallel dispatch
- The orchestrator SHALL pin all parallel worktrees during execution to prevent GC reclamation
- The orchestrator SHALL record worktree paths and branches in the agent dispatch context
- The orchestrator SHALL teardown all worktrees after integration completes or on failure

#### Scenario: Orchestrator creates worktrees for parallel packages
- **WHEN** orchestrator dispatches 3 parallel packages (wp-backend, wp-frontend, wp-tests) for change `add-auth`
- **THEN** `.git-worktrees/add-auth/wp-backend/`, `.git-worktrees/add-auth/wp-frontend/`, `.git-worktrees/add-auth/wp-tests/` exist
- **AND** branches `openspec/add-auth/wp-backend`, `openspec/add-auth/wp-frontend`, `openspec/add-auth/wp-tests` exist
- **AND** all three worktrees are registered in `.git-worktrees/.registry.json`
- **AND** all three are pinned

#### Scenario: Root packages implemented in worktrees, not shared checkout
- **WHEN** DAG has root package `wp-contracts` (no deps) and parallel packages depending on it
- **THEN** orchestrator creates worktree `.git-worktrees/add-auth/wp-contracts/`
- **AND** implements `wp-contracts` in that worktree
- **AND** merges `wp-contracts` branch into feature branch
- **AND** tears down the root worktree
- **AND** parallel package worktrees are created from the updated feature branch
- **AND** the shared checkout is never modified

#### Scenario: Multiple orchestrators on same checkout do not conflict
- **WHEN** terminal 1 runs `/parallel-implement-feature feature-a` and terminal 2 runs `/parallel-implement-feature feature-b` from the same checkout
- **THEN** terminal 1 creates worktrees under `.git-worktrees/feature-a/`
- **AND** terminal 2 creates worktrees under `.git-worktrees/feature-b/`
- **AND** the shared checkout remains unchanged
- **AND** no git staging, branch switching, or file contention occurs between the two

#### Scenario: Worktrees cleaned up after completion
- **WHEN** integration merge completes successfully
- **THEN** orchestrator calls `worktree.py teardown` for each package worktree
- **AND** worktrees are removed from the registry

---

### Requirement: Agent Dispatch with Worktree Context

The orchestrator SHALL include worktree path and branch information in every parallel agent dispatch, and use vendor isolation when available as a safety net.

- For vendors supporting agent isolation (e.g., Claude Code `isolation: "worktree"`), the dispatch SHALL use the vendor isolation mechanism as a safety net
- For vendors without isolation support, the agent prompt SHALL instruct the agent to `cd` into the worktree path as its first action
- The dispatch prompt SHALL include `WORKTREE_PATH`, `BRANCH`, `CHANGE_ID`, and `PACKAGE_ID` for every parallel agent
- The agent SHALL verify it is operating in the correct worktree before modifying files

#### Scenario: Claude Code agent dispatched with vendor isolation
- **WHEN** orchestrator dispatches a parallel package to a Claude Code agent
- **THEN** Agent tool call includes `isolation: "worktree"` parameter
- **AND** agent prompt includes the worktree path and branch from our registry
- **AND** agent commits to the registered branch name

#### Scenario: Non-isolating vendor agent dispatched with cd instruction
- **WHEN** orchestrator dispatches a parallel package to an agent without isolation support
- **THEN** agent prompt begins with `cd <worktree-path>` instruction
- **AND** agent operates exclusively within that directory
- **AND** agent commits to the registered branch name

#### Scenario: Agent worktree verification
- **WHEN** agent begins work on a package
- **THEN** agent verifies `git rev-parse --show-toplevel` matches the expected worktree path
- **AND** agent verifies `git branch --show-current` matches the expected branch name
- **AND** if verification fails, agent reports error rather than proceeding in wrong directory

---

### Requirement: Integration Merge Protocol

After all parallel packages complete, an integration agent SHALL merge per-package branches into the feature branch with conflict detection.

- The integration merge SHALL use `git merge --no-ff` for each package branch to preserve per-package commit history
- Merge conflicts SHALL be treated as scope overlap violations and reported as errors
- The integration agent SHALL run the full verification suite after merging all branches
- The integration agent SHALL operate in its own worktree (`--agent-id integrator`)

#### Scenario: Clean integration merge
- **WHEN** all 3 parallel packages complete with non-overlapping changes
- **THEN** integrator merges `openspec/add-auth/wp-backend`, `openspec/add-auth/wp-frontend`, `openspec/add-auth/wp-tests` into `openspec/add-auth`
- **AND** each merge uses `--no-ff` creating a merge commit
- **AND** full test suite passes on the merged result

#### Scenario: Merge conflict detected
- **WHEN** two packages modified the same file (scope violation)
- **THEN** integrator reports the conflict as a SCOPE_VIOLATION escalation
- **AND** identifies the conflicting files and packages
- **AND** does NOT attempt automatic conflict resolution

---

### Requirement: Vendor-Agnostic Isolation Strategy

The worktree isolation approach SHALL work across agent vendors without requiring vendor-specific code paths in the core orchestration logic.

- The orchestrator's worktree management (Layer 1) SHALL be identical regardless of agent vendor
- Vendor-specific isolation (Layer 2) SHALL be configured via the agent profile in `agents.yaml`, not hardcoded
- The `agents.yaml` schema SHALL support an optional `isolation` field per agent type
- When vendor isolation is unavailable, the system SHALL degrade to cd-based worktree access with a logged warning

#### Scenario: Agent profile declares isolation capability
- **WHEN** `agents.yaml` declares `claude-code-local` with `isolation: worktree`
- **THEN** orchestrator uses `Agent(isolation="worktree")` when dispatching to that agent
- **AND** also sets up our Layer 1 worktree for registry/lifecycle tracking

#### Scenario: Agent profile without isolation capability
- **WHEN** `agents.yaml` declares `codex-local` without an `isolation` field
- **THEN** orchestrator dispatches without vendor isolation
- **AND** agent prompt includes explicit `cd <worktree-path>` instruction
- **AND** a warning is logged that vendor isolation is unavailable
