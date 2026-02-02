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

