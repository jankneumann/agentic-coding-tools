# skill-workflow Specification

## Purpose
TBD - created by archiving change add-iterate-on-implementation-skill. Update Purpose after archive.
## Requirements
### Requirement: Iterative Refinement Skill
The system SHALL provide an `iterate-on-implementation` skill that performs structured iterative refinement of a feature implementation after `/implement-feature` completes and before `/cleanup-feature` runs.

The skill SHALL accept the following arguments:
- Change-id (required; or detected from current branch name `openspec/<change-id>`)
- Max iterations (optional; default: 5)
- Criticality threshold (optional; default: "medium"; values: "critical", "high", "medium", "low")

#### Scenario: Basic iterative refinement
- **WHEN** the user invokes `/iterate-on-implementation <change-id>`
- **THEN** the skill SHALL review the proposal, design, tasks, and current implementation code
- **AND** produce a structured improvement analysis for each iteration
- **AND** implement all findings at or above the criticality threshold
- **AND** commit the iteration's changes as a separate commit
- **AND** update documentation (CLAUDE.md, AGENTS.md, or docs/) with new lessons learned
- **AND** repeat until max iterations reached or only findings below threshold remain

#### Scenario: Early termination when only low-criticality findings remain
- **WHEN** an iteration's analysis produces only findings below the criticality threshold
- **THEN** the skill SHALL stop iterating and present a summary of all completed iterations
- **AND** report the remaining low-criticality findings for optional manual review

#### Scenario: Max iterations reached
- **WHEN** the configured max iterations have been completed
- **THEN** the skill SHALL stop iterating and present a summary
- **AND** report any remaining findings that were not addressed

#### Scenario: Out-of-scope findings
- **WHEN** an iteration identifies an issue that requires design changes beyond the current proposal scope
- **THEN** the skill SHALL flag the finding as "out of scope"
- **AND** recommend creating a new OpenSpec proposal for it
- **AND** NOT attempt to implement the out-of-scope change

#### Scenario: Parallel quality check execution
- **WHEN** the skill runs quality checks (pytest, mypy, ruff, openspec validate)
- **THEN** the skill SHALL execute all quality checks concurrently using Task(Bash) with run_in_background=true
- **AND** collect all results before reporting
- **AND** report all failures together rather than fail-fast on first error

#### Scenario: Quality check partial failure
- **WHEN** one or more quality checks fail while others succeed
- **THEN** the skill SHALL report all check results (both passing and failing)
- **AND** indicate which specific checks failed
- **AND** continue with iteration if fixes are possible

### Requirement: Structured Improvement Analysis
Each iteration SHALL produce a structured analysis where every finding contains:
- **Type**: One of bug, edge-case, workflow, performance, UX
- **Criticality**: One of critical, high, medium, low
- **Description**: What the issue is and why it matters
- **Proposed fix**: How to address the finding

#### Scenario: Analysis covers all improvement categories
- **WHEN** the skill reviews the current implementation
- **THEN** it SHALL evaluate for bugs, unhandled edge cases, workflow improvements, performance issues, and UX issues (where applicable)
- **AND** classify each finding by type and criticality

#### Scenario: Analysis is reproducible and auditable
- **WHEN** an iteration completes
- **THEN** the findings and actions taken SHALL be recorded in the commit message for that iteration

### Requirement: Iteration Commit Convention
Each iteration SHALL produce exactly one commit on the current feature branch with a message following this format:
```
refine(<scope>): iteration <N> - <summary>

Iterate-on-implementation: <change-id>, iteration <N>/<max>

Findings addressed:
- [<criticality>] <type>: <description>

Co-Authored-By: Claude <noreply@anthropic.com>
```

#### Scenario: Commit per iteration
- **WHEN** an iteration implements improvements
- **THEN** all changes for that iteration SHALL be staged and committed as a single commit
- **AND** the commit message SHALL list the findings addressed with their criticality and type

### Requirement: Documentation Update Per Iteration
Each iteration SHALL review whether genuinely new patterns, lessons, or gotchas were discovered and, if so, update the relevant documentation files.

Documentation updates SHALL follow the existing convention:
- Update CLAUDE.md or AGENTS.md directly if they are under 300 lines each
- If either file exceeds 300 lines, refactor into focused documents in docs/ and reference them

#### Scenario: New lesson discovered during iteration
- **WHEN** an iteration reveals a pattern or gotcha not already documented
- **THEN** the skill SHALL add the lesson to CLAUDE.md, AGENTS.md, or the appropriate docs/ file
- **AND** include the documentation change in the iteration's commit

#### Scenario: No new lessons in an iteration
- **WHEN** an iteration's findings are variations of already-documented patterns
- **THEN** the skill SHALL NOT add redundant documentation

### Requirement: OpenSpec Document Update Per Iteration
Each iteration SHALL review whether the current OpenSpec documents (proposal.md, design.md, spec deltas) accurately reflect the refined implementation. When findings reveal spec drift, incorrect assumptions, or missing requirements, the relevant OpenSpec documents SHALL be updated.

#### Scenario: OpenSpec document update on spec drift
- **WHEN** an iteration reveals that the proposal, design, or spec deltas contain assumptions or requirements that don't match the refined implementation
- **THEN** the skill SHALL update the relevant OpenSpec documents to reflect the actual state
- **AND** include those changes in the iteration's commit

#### Scenario: OpenSpec documents still accurate
- **WHEN** an iteration's changes are consistent with the existing OpenSpec documents
- **THEN** the skill SHALL NOT make unnecessary changes to OpenSpec documents

### Requirement: Skill Workflow Position
The `iterate-on-implementation` skill SHALL fit into the feature development workflow as an optional step between `/implement-feature` and `/cleanup-feature`:

```
/plan-feature → /implement-feature → /iterate-on-implementation (optional) → /cleanup-feature
```

#### Scenario: Workflow integration
- **WHEN** the user completes `/implement-feature` and has a PR ready for review
- **THEN** they MAY invoke `/iterate-on-implementation` to refine the implementation before requesting review
- **AND** the skill SHALL operate on the existing feature branch without creating new branches

### Requirement: Parallel Task Implementation Pattern
The `implement-feature` and `iterate-on-implementation` skills SHALL support parallel Task() subagents for implementing independent tasks or fixes concurrently.

#### Scenario: Spawn parallel implementation agents
- **WHEN** the skill identifies independent tasks (no shared files) that can be parallelized
- **THEN** it MAY spawn Task(general-purpose) agents with run_in_background=true
- **AND** scope each agent's prompt to specific files/modules
- **AND** NOT create git worktrees for agent isolation

#### Scenario: Agent file scope enforcement
- **WHEN** multiple agents are spawned for parallel implementation
- **THEN** each agent's prompt SHALL explicitly list which files/modules are in scope
- **AND** tasks with overlapping file scope SHALL be executed sequentially, not in parallel

#### Scenario: Result collection and integration
- **WHEN** all parallel agents complete their tasks
- **THEN** the orchestrator SHALL collect results using TaskOutput
- **AND** verify each agent's work before committing
- **AND** create a single commit integrating all agent work (or separate commits if appropriate)

#### Scenario: Agent failure recovery
- **WHEN** a background agent fails during execution
- **THEN** the orchestrator SHALL report the failure with context
- **AND** MAY attempt recovery using the Task resume parameter
- **AND** SHALL NOT commit partial work from failed agents without user confirmation

### Requirement: Parallel Context Exploration Pattern
Skills that gather context (plan-feature, iterate-on-plan) SHALL support parallel Task(Explore) agents for faster context collection when multiple independent sources need analysis.

#### Scenario: Parallel exploration execution
- **WHEN** a skill needs to gather context from multiple sources (specs, code, in-progress changes)
- **THEN** it MAY spawn multiple Task(Explore) agents concurrently
- **AND** synthesize the results after all agents complete

#### Scenario: Exploration is read-only
- **WHEN** Task(Explore) agents are used for context gathering
- **THEN** they SHALL NOT modify any files
- **AND** they SHALL return analysis results to the orchestrator for synthesis

### Requirement: Worktree Isolation Pattern

The `implement-feature`, `iterate-on-implementation`, and `cleanup-feature` skills SHALL support per-feature git worktree isolation to enable concurrent CLI sessions working on different features.

Worktrees SHALL be created at `../<repo-name>.worktrees/<change-id>/` relative to the main repository.

#### Scenario: Worktree creation on implement-feature
- **WHEN** the user invokes `/implement-feature <change-id>`
- **THEN** the skill SHALL create a worktree at `../<repo-name>.worktrees/<change-id>/`
- **AND** create the feature branch `openspec/<change-id>` if it doesn't exist
- **AND** change the working directory to the worktree
- **AND** continue implementation in the worktree

#### Scenario: Skip worktree creation when already in worktree
- **WHEN** the user invokes `/implement-feature <change-id>`
- **AND** the current working directory is already the worktree for that change-id
- **THEN** the skill SHALL skip worktree creation
- **AND** continue with implementation

#### Scenario: Worktree detection in iterate-on-implementation
- **WHEN** the user invokes `/iterate-on-implementation <change-id>`
- **AND** the current working directory is a git worktree
- **THEN** the skill SHALL detect the main repository path
- **AND** resolve OpenSpec files from the main repository
- **AND** operate normally on implementation files in the worktree

#### Scenario: Worktree cleanup on cleanup-feature
- **WHEN** the user invokes `/cleanup-feature <change-id>`
- **AND** a worktree exists for that change-id
- **THEN** the skill SHALL remove the worktree after archiving
- **AND** NOT remove the worktree if cleanup is aborted

### Requirement: OpenSpec File Access in Worktrees

Skills running in worktrees SHALL access OpenSpec files from the main repository, not from the worktree.

#### Scenario: OpenSpec path resolution in worktree
- **WHEN** a skill needs to read OpenSpec files (proposal.md, tasks.md, design.md, specs/)
- **AND** the skill is running in a worktree
- **THEN** it SHALL resolve the path relative to the main repository using git-common-dir
- **AND** NOT expect OpenSpec files to exist in the worktree

