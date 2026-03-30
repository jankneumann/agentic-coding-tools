# skill-workflow Delta Spec: interactive-plan-feature

## ADDED Requirements

### Requirement: Interactive Discovery Phase

The `/plan-feature` skill SHALL present discovered context and ask 2-5 clarifying questions (5-8 in `--explore` mode) using AskUserQuestion after gathering codebase context and BEFORE generating any proposal artifacts.

#### Scenario: Discovery questions after context exploration
- **WHEN** the plan-feature skill completes context exploration (Step 2)
- **THEN** the skill SHALL present a structured summary of related specs, code, conflicts, and constraints
- **AND** ask MIN_QUESTIONS to MAX_QUESTIONS clarifying questions across scope, trade-offs, constraints, decisions, and success criteria categories
- **AND** STOP and wait for user responses before proceeding to artifact generation

#### Scenario: Questions reference specific discoveries
- **WHEN** generating discovery questions
- **THEN** each question MUST reference at least one specific discovery from the context exploration
- **AND** questions about scope, trade-offs, or decisions SHALL use AskUserQuestion with preset options
- **AND** questions about constraints or success criteria SHALL use open-ended AskUserQuestion

#### Scenario: AskUserQuestion unavailable
- **WHEN** AskUserQuestion is not available in the current runtime
- **THEN** the skill SHALL present questions as a numbered list in regular output
- **AND** instruct the user to respond inline

### Requirement: Mandatory Approaches Considered

The `/plan-feature` skill SHALL generate 2-3 distinct approaches (3-5 in `--explore` mode) in the proposal's "Approaches Considered" section, each with description, pros, cons, and effort estimate.

#### Scenario: Proposal includes approaches
- **WHEN** the skill generates proposal.md
- **THEN** the proposal MUST include an "Approaches Considered" section
- **AND** each approach SHALL have a descriptive name, 1-2 sentence description, bullet-list pros and cons, and effort estimate (S/M/L)
- **AND** one approach SHALL be marked as "Recommended" with rationale

#### Scenario: Approaches are genuinely distinct
- **WHEN** generating approaches
- **THEN** each approach MUST represent a meaningfully different way to solve the problem
- **AND** approaches SHALL NOT be minor variations of the same solution

### Requirement: Two-Gate Approval

The `/plan-feature` skill SHALL implement two approval gates: Gate 1 (direction selection after proposal) and Gate 2 (plan approval after all artifacts).

#### Scenario: Gate 1 direction approval
- **WHEN** proposal.md is generated with approaches
- **THEN** the skill SHALL present the proposal and use AskUserQuestion to ask the user to select an approach
- **AND** offer options for each approach, plus "Modify approaches" and "Need more detail"
- **AND** STOP and wait for the user's selection before generating specs, tasks, or design

#### Scenario: Gate 1 revision loop
- **WHEN** the user selects "Modify approaches" or "Need more detail" at Gate 1
- **THEN** the skill SHALL gather feedback or ask follow-up questions
- **AND** loop back to regenerate the proposal with revised approaches

#### Scenario: Gate 1 selection recorded
- **WHEN** the user selects an approach at Gate 1
- **THEN** the skill SHALL update proposal.md with a "Selected Approach" subsection
- **AND** the selected approach MUST drive all subsequent artifact content

#### Scenario: Gate 2 plan approval
- **WHEN** all artifacts are generated and validated
- **THEN** the skill SHALL present the complete plan and use AskUserQuestion with options: "Approve", "Revise tasks", "Revise approach", "Reject"
- **AND** STOP and wait for the user's decision

#### Scenario: Gate 2 revision options
- **WHEN** the user selects "Revise tasks" at Gate 2
- **THEN** the skill SHALL loop back to artifact generation (Step 6)
- **WHEN** the user selects "Revise approach" at Gate 2
- **THEN** the skill SHALL loop back to proposal generation (Step 4)

### Requirement: Explore Mode

The `/plan-feature` skill SHALL support an `--explore` flag that enables deep-dive planning mode.

#### Scenario: Explore mode activation
- **WHEN** `$ARGUMENTS` contains `--explore`
- **THEN** the skill SHALL set MIN_QUESTIONS=5, MAX_QUESTIONS=8, MIN_APPROACHES=3, MAX_APPROACHES=5
- **AND** emit "Mode: explore" in the tier notification

#### Scenario: Explore mode prior art
- **WHEN** `--explore` is active and web search is available
- **THEN** the skill SHALL include a "Prior Art" section in the context presentation
- **AND** include prior art references in approach descriptions where relevant

#### Scenario: Explore mode web search unavailable
- **WHEN** `--explore` is active but web search is unavailable
- **THEN** the skill SHALL skip the prior art search and note this limitation

### Requirement: Assumption Surfacing in Plan Iteration

The `/iterate-on-plan` skill SHALL include "assumptions" as a finding type and surface assumption findings interactively.

#### Scenario: Assumptions detected during iteration
- **WHEN** the iterate-on-plan analysis identifies an implicit assumption that could reasonably go multiple ways
- **THEN** the finding SHALL be classified as type "assumptions"
- **AND** assumption findings that affect scope or technology choice SHALL be classified as high criticality

#### Scenario: Assumptions surfaced interactively
- **WHEN** implementing improvements for assumption-type findings
- **THEN** the skill SHALL use AskUserQuestion to present the assumption and its alternatives
- **AND** wait for the user's response
- **AND** update the relevant document to convert the assumption into an explicit, documented decision

#### Scenario: Assumption as plan smell
- **WHEN** checking for plan smells
- **THEN** the skill SHALL check for "Unstated assumption" — a plan that proceeds on an assumption about scope, technology choice, or constraint that was never confirmed with the user

## MODIFIED Requirements

### Requirement: Proposal Template Structure

The `openspec/schemas/feature-workflow/templates/proposal.md` template SHALL include an "Approaches Considered" section between "What Changes" and "Impact", with sub-sections for each approach and a "Selected Approach" placeholder.

#### Scenario: Template sections present
- **WHEN** a new proposal is created from the template
- **THEN** the proposal SHALL contain sections: Why, What Changes, Approaches Considered, Selected Approach, Impact

### Requirement: Plan Findings Type List

The plan-findings artifact instruction in `schema.yaml` SHALL include "assumptions" in the Types list alongside completeness, clarity, feasibility, scope, consistency, testability, and parallelizability.

#### Scenario: Assumptions in findings schema
- **WHEN** plan findings are generated
- **THEN** the Types list SHALL include "assumptions"
- **AND** assumption findings that could go either way MUST be surfaced to the user via AskUserQuestion
