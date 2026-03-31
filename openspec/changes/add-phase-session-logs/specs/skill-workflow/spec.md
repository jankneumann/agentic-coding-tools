# Delta Spec: skill-workflow — Phase Session Logs

## Modified Requirements

### Requirement: Session Log Artifact [MODIFIED]

The system SHALL provide a `session-log.md` artifact that captures a structured summary of agent decisions at each workflow phase boundary for each OpenSpec change. The artifact is a **living document** — each phase appends a dated, agent-attributed section rather than generating the file once at cleanup. The artifact SHALL focus on decision rationale, trade-offs, alternatives considered, and key discussion points — not on replicating code diffs already stored in git.

#### Scenario: Session log appended at each workflow phase
- **WHEN** any workflow skill (`/plan-feature`, `/iterate-on-plan`, `/implement-feature`, `/iterate-on-implementation`, `/validate-feature`, `/cleanup-feature`) completes its substantive work
- **THEN** the skill SHALL append a phase entry to `openspec/changes/<change-id>/session-log.md`
- **AND** the entry SHALL identify the phase name, date, agent type, and session ID
- **AND** the entry SHALL contain: Decisions, Alternatives Considered, Trade-offs, Open Questions, and Context sections

#### Scenario: Session log created on first phase
- **WHEN** the first workflow skill runs for a change and no `session-log.md` exists
- **THEN** the skill SHALL create the file with a header (`# Session Log: <change-id>` and a brief description)
- **AND** append the first phase entry

#### Scenario: Session log appended on subsequent phases
- **WHEN** a workflow skill runs and `session-log.md` already exists
- **THEN** the skill SHALL append a new phase entry separated by a horizontal rule (`---`)
- **AND** SHALL NOT modify or overwrite previous phase entries

#### Scenario: Parallel agents contributing to same change
- **WHEN** multiple agent sessions contribute to the same change (e.g., parallel implementation)
- **THEN** each agent SHALL append its own phase entry with its agent type and session ID
- **AND** the session log SHALL contain per-agent entries in chronological order

#### Scenario: No decisions to record
- **WHEN** a phase completes but the agent made no significant decisions (e.g., validation passed cleanly)
- **THEN** the phase entry SHALL still be appended with a brief Context section noting the outcome
- **AND** the Decisions section MAY state "No significant decisions required"

#### Scenario: Session log is optional
- **WHEN** a change is archived without a `session-log.md`
- **THEN** OpenSpec validation SHALL NOT report an error
- **AND** the change SHALL be considered complete

### Requirement: Session Log Content Structure [MODIFIED]

Each phase entry in `session-log.md` SHALL follow this structure:

- **Phase header**: Phase name, date (YYYY-MM-DD), agent type, and session ID
- **Decisions**: Numbered list of significant decisions with brief rationale
- **Alternatives Considered**: Alternatives discussed and why they were rejected
- **Trade-offs**: Explicit trade-offs accepted
- **Open Questions**: Unresolved questions as checklist items
- **Context**: 2-3 sentences describing the phase goal and outcome

#### Scenario: Content focuses on rationale not code
- **WHEN** a phase entry is written
- **THEN** it SHALL NOT include raw code blocks, full file contents, or diff output
- **AND** it SHALL reference files by path when relevant context requires it
- **AND** it SHALL focus on the reasoning behind decisions, not the mechanical steps taken

#### Scenario: Content is concise per phase
- **WHEN** a phase entry is written after a long session
- **THEN** the entry SHALL be a summarized distillation, not a full transcript
- **AND** each phase entry SHOULD NOT exceed 80 lines
- **AND** the total session-log.md SHOULD NOT exceed 500 lines

### Requirement: Session Log Extraction [MODIFIED]

The system SHALL use **direct agent authorship** at phase boundaries as the primary session log generation mechanism, replacing the previous 3-tier extraction strategy.

#### Scenario: Agent writes phase entry directly
- **WHEN** a workflow skill reaches its session-log step
- **THEN** the agent SHALL write the phase entry from its current context window
- **AND** SHALL NOT rely on external transcript parsing or handoff document compilation

#### Scenario: Phase entry template embedded in skill
- **WHEN** a workflow skill includes a session-log step
- **THEN** the SKILL.md SHALL contain the phase entry template with clear guidance on what to capture
- **AND** the template SHALL be consistent across all workflow skills

### Requirement: Cleanup Skill Session Log Integration [MODIFIED]

The cleanup skill SHALL append its own phase entry and ensure session-log.md is included in the archive, replacing the previous extraction-based approach.

#### Scenario: Cleanup appends final phase entry
- **WHEN** `/cleanup-feature <change-id>` reaches the session-log step
- **THEN** it SHALL append a Cleanup phase entry covering merge strategy and task migration decisions
- **AND** SHALL run sanitization on the complete session-log.md
- **AND** SHALL include the sanitized file in the archive commit

#### Scenario: Session log generation failure does not block cleanup
- **WHEN** session log append or sanitization fails
- **THEN** the cleanup skill SHALL log a warning
- **AND** SHALL proceed with archive without the session log
- **AND** SHALL NOT retry or block the cleanup workflow

## New Requirements

### Requirement: Sanitize-Then-Verify Flow

After every session-log append, the workflow SHALL run sanitization and agent verification to catch both secret leaks and over-redaction.

#### Scenario: Sanitization runs after every append
- **WHEN** an agent appends a phase entry to session-log.md or a merge-log entry
- **THEN** the skill SHALL run `sanitize_session_log.py` on the file
- **AND** the agent SHALL read the sanitized output and verify it is coherent

#### Scenario: Over-redaction detected
- **WHEN** the agent reads the sanitized output and finds meaningful content was incorrectly redacted
- **THEN** the agent SHALL rewrite the affected section without including the actual secret
- **AND** SHALL re-run sanitization on the corrected content

#### Scenario: Sanitization failure
- **WHEN** `sanitize_session_log.py` exits non-zero
- **THEN** the skill SHALL NOT commit the session-log.md
- **AND** SHALL log a warning and proceed without the session log for that phase

### Requirement: Merge Log Artifact

The `/merge-pull-requests` skill SHALL produce a dated merge log capturing cross-PR triage reasoning, user decisions, and observations.

#### Scenario: Merge log written to dated file
- **WHEN** `/merge-pull-requests` completes a merge session
- **THEN** it SHALL write to `docs/merge-logs/YYYY-MM-DD.md` (using the current date)
- **AND** the entry SHALL contain: session timestamp, agent type, PR triage table, vendor review findings, user decisions, and observations

#### Scenario: Multiple merge sessions on same day
- **WHEN** multiple merge sessions occur on the same day
- **THEN** each session SHALL append to the existing day's file separated by a horizontal rule
- **AND** each entry SHALL include its own session timestamp

#### Scenario: Merge log captures cross-PR reasoning
- **WHEN** merge triage decisions span multiple PRs
- **THEN** the merge log SHALL capture the reasoning that connects them (e.g., "merged A and B together because related", "skipped C due to conflict with A")
- **AND** SHALL record user steering decisions (e.g., "user requested skipping all Renovate PRs")

#### Scenario: Merge log captures vendor review findings
- **WHEN** vendor reviews were dispatched during the merge session
- **THEN** the merge log SHALL summarize confirmed findings, unconfirmed findings, and blocking issues per PR

#### Scenario: PR comments for contributor visibility
- **WHEN** a PR is closed or skipped during merge triage
- **THEN** the skill SHALL still post a brief PR comment explaining the action
- **AND** the detailed rationale SHALL be in the merge log, not duplicated in the PR comment

#### Scenario: Merge log sanitization
- **WHEN** a merge-log entry is written
- **THEN** the skill SHALL run `sanitize_session_log.py` on the file before committing
- **AND** the agent SHALL verify the sanitized output

#### Scenario: Merge log directory exists
- **THEN** the repository SHALL contain `docs/merge-logs/.gitkeep` to ensure the directory exists
- **AND** the directory SHALL be committed to the repository

### Requirement: Phase Names for Session Log Entries

Each workflow skill SHALL use a consistent phase name when appending to session-log.md.

#### Scenario: Phase name mapping
- **WHEN** a workflow skill appends a session-log entry
- **THEN** it SHALL use the following phase names:
  - `/plan-feature` → `Plan`
  - `/iterate-on-plan` → `Plan Iteration <N>` (where N is the iteration number)
  - `/implement-feature` → `Implementation`
  - `/iterate-on-implementation` → `Implementation Iteration <N>`
  - `/validate-feature` → `Validation`
  - `/cleanup-feature` → `Cleanup`
  - `/merge-pull-requests` → (uses merge-log, not session-log)

### Requirement: Session Log Committed with Phase Artifacts

Session log updates SHALL be committed alongside other phase artifacts, not in separate commits.

#### Scenario: Skills that commit artifacts
- **WHEN** a skill already commits artifacts (plan-feature, implement-feature, cleanup-feature)
- **THEN** the session-log.md SHALL be included in the same commit via `git add`
- **AND** SHALL NOT require a separate commit

#### Scenario: Skills that don't normally commit
- **WHEN** a skill does not normally commit (iterate-on-plan, iterate-on-implementation, validate-feature)
- **THEN** the skill SHALL commit the session-log.md update as a small dedicated commit
- **AND** SHALL push to the feature branch
