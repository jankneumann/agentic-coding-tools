## ADDED Requirements
### Requirement: Proposal Prioritization Skill
The system SHALL provide a `prioritize-proposals` skill that evaluates all active OpenSpec change proposals and produces a prioritized “what to do next” order for the agentic development pipeline.

The skill SHALL accept the following arguments:
- `--change-id <id>[,<id>]` (optional; limit analysis to specific change IDs)
- `--since <git-ref>` (optional; default: `HEAD~50`; analyze commits since ref for relevance)
- `--format <md|json>` (optional; default: `md`)

#### Scenario: Prioritized report generation
- **WHEN** the user invokes `/prioritize-proposals`
- **THEN** the skill SHALL analyze all active proposals under `openspec/changes/`
- **AND** produce an ordered list of proposals with a rationale for the ranking
- **AND** identify candidate next steps for the top-ranked proposal

#### Scenario: Scoped change-id analysis
- **WHEN** the user invokes `/prioritize-proposals --change-id add-foo,update-bar`
- **THEN** the skill SHALL limit analysis to the specified change IDs
- **AND** still provide relevance, refinement, and conflict assessments for each

### Requirement: Proposal Relevance and Refinement Analysis
The `prioritize-proposals` skill SHALL evaluate each proposal against recent commits and code changes to determine relevance, required refinements, and potential conflicts.

#### Scenario: Proposal already addressed by recent commits
- **WHEN** recent commits touch the same files and requirements as a proposal
- **THEN** the skill SHALL mark the proposal as likely addressed or needing verification
- **AND** recommend whether to archive, update, or re-scope the proposal

#### Scenario: Proposal needs refinement due to code drift
- **WHEN** a proposal’s target files or assumptions have changed since it was authored
- **THEN** the skill SHALL flag it as requiring refinement
- **AND** suggest which proposal documents to update (proposal.md, tasks.md, or spec deltas)

### Requirement: Conflict-Aware Prioritization Output
The `prioritize-proposals` skill SHALL rank proposals by factoring in estimated file conflicts and dependency ordering to minimize collisions for parallel agent work.

#### Scenario: Conflict-aware ordering
- **WHEN** two proposals modify overlapping files or specs
- **THEN** the skill SHALL order them to minimize merge conflicts
- **AND** explain the detected overlap in the report

#### Scenario: Conflict-free parallel suggestions
- **WHEN** proposals are independent and touch distinct files
- **THEN** the skill SHALL identify them as parallelizable workstreams
- **AND** include that suggestion in the output report

### Requirement: Prioritization Report Persistence
The skill SHALL write the prioritization report to `openspec/changes/prioritized-proposals.md` and update it on each run.

#### Scenario: Report saved for pipeline consumption
- **WHEN** the skill finishes its analysis
- **THEN** it SHALL persist the report to `openspec/changes/prioritized-proposals.md`
- **AND** include a timestamp and analyzed git range in the report header
