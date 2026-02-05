# skill-workflow Spec Delta

## MODIFIED Requirements

### Requirement: Iterative Refinement Skill

**MODIFIED**: Add parallel execution for quality checks.

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

## ADDED Requirements

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
