# Delta Spec: skill-workflow — Phase Session Logs

## Modified Requirements

### Requirement: Session Log Artifact [MODIFIED]

The system SHALL provide a `session-log.md` artifact that captures a structured summary of agent decisions at each workflow phase boundary for each OpenSpec change. The artifact is a **living document** — each phase appends a dated, agent-attributed section rather than generating the file once at cleanup. The artifact SHALL focus on decision rationale, trade-offs, alternatives considered, and key discussion points — not on replicating code diffs already stored in git.

#### Scenario: Session log appended at each workflow phase
- **WHEN** any workflow skill (`/plan-feature`, `/iterate-on-plan`, `/implement-feature`, `/iterate-on-implementation`, `/validate-feature`, `/cleanup-feature`) completes its substantive work
- **THEN** the skill SHALL append a phase entry to `openspec/changes/<change-id>/session-log.md`
- **AND** the entry SHALL identify the phase name, date, agent type, and session ID (if available; omit or write "N/A" when the runtime does not expose a session identifier)
- **AND** the entry SHALL contain: Decisions, Alternatives Considered, Trade-offs, Open Questions, and Context sections

#### Scenario: Session log created on first phase
- **WHEN** the first workflow skill runs for a change and no `session-log.md` exists
- **THEN** the skill SHALL create the file with a header (`# Session Log: <change-id>` and a brief description)
- **AND** SHALL create the parent directory (`openspec/changes/<change-id>/`) if it does not exist
- **AND** append the first phase entry

#### Scenario: Session log appended on subsequent phases
- **WHEN** a workflow skill runs and `session-log.md` already exists
- **THEN** the skill SHALL append a new phase entry separated by a horizontal rule (`---`)
- **AND** SHALL NOT modify or overwrite previous phase entries

#### Scenario: Parallel agents contributing to same change
- **WHEN** multiple agent sessions contribute to the same change (e.g., parallel implementation)
- **THEN** each agent SHALL append its own phase entry in its own worktree branch
- **AND** session-log.md merge conflicts SHALL be resolved during the integration merge step (append-only files merge cleanly in most cases; manual resolution uses chronological ordering by phase entry date)

#### Scenario: No decisions to record
- **WHEN** a phase completes but the agent made no significant decisions (e.g., validation passed cleanly)
- **THEN** the phase entry SHALL still be appended with a Context section noting the outcome
- **AND** the Decisions section MAY state "No significant decisions required"
- **AND** the Alternatives Considered, Trade-offs, and Open Questions sections MAY be omitted

#### Scenario: Session log is optional for archival
- **WHEN** a change is archived without a `session-log.md` (e.g., change abandoned mid-workflow, or pre-existing change from before this feature)
- **THEN** OpenSpec validation SHALL NOT report an error
- **AND** the change SHALL be considered complete

### Requirement: Session Log Content Structure [MODIFIED]

Each phase entry in `session-log.md` SHALL follow this structure:

- **Phase header**: Phase name, date (YYYY-MM-DD), agent type, and session ID (if available)
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
- **AND** each phase entry SHALL NOT exceed 80 lines
- **AND** the total session-log.md SHALL NOT exceed 500 lines unless the agent documents a rationale for exceeding the limit in the entry itself

#### Scenario: Template consistency across skills
- **WHEN** multiple workflow skills include session-log steps
- **THEN** all skills SHALL use identical section names (Decisions, Alternatives Considered, Trade-offs, Open Questions, Context)
- **AND** skill-specific guidance (e.g., "focus on architecture decisions" for plan-feature) MAY vary in the SKILL.md instructions
- **AND** the rendered output structure SHALL be identical across all skills

### Requirement: Session Log Extraction [MODIFIED]

The system SHALL use **direct agent authorship** at phase boundaries as the primary session log generation mechanism. This replaces the previous 3-tier extraction strategy. The following legacy scenarios are RETIRED: "Claude Code session extraction" (Tier 1 transcript parsing), "Handoff documents as fallback source" (Tier 2 handoff compilation), and "Manual session log" (Tier 3 agent prompt). Direct agent authorship subsumes all three — the agent writes from its context window at each phase boundary.

#### Scenario: Agent writes phase entry directly
- **WHEN** a workflow skill reaches its session-log step
- **THEN** the agent SHALL write the phase entry from its current context window
- **AND** SHALL NOT rely on external transcript parsing or handoff document compilation

#### Scenario: Phase entry template embedded in skill
- **WHEN** a workflow skill includes a session-log step
- **THEN** the SKILL.md SHALL contain the phase entry template with clear guidance on what to capture for that specific phase
- **AND** the template SHALL use the same section names as defined in Session Log Content Structure

### Requirement: Cleanup Skill Session Log Integration [MODIFIED]

The cleanup skill SHALL append its own phase entry and ensure session-log.md is included in the archive, replacing the previous extraction-based approach.

#### Scenario: Cleanup appends final phase entry
- **WHEN** `/cleanup-feature <change-id>` reaches the session-log step
- **THEN** it SHALL append a Cleanup phase entry covering merge strategy and task migration decisions
- **AND** SHALL run sanitization on the complete session-log.md
- **AND** SHALL include the sanitized file in the archive commit

#### Scenario: Cleanup without prior session-log
- **WHEN** `/cleanup-feature <change-id>` runs and no `session-log.md` exists from prior phases
- **THEN** it SHALL create the file with the header and append a Cleanup phase entry
- **AND** the entry SHALL summarize the change from the agent's available context

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
- **THEN** the skill SHALL run `sanitize_session_log.py` on the file (in-place: same path for input and output)
- **AND** the agent SHALL read the sanitized output and verify: (1) all phase entry sections are present and non-empty or intentionally omitted, (2) no `[REDACTED:*]` markers appear in narrative prose where the original content contained no secrets, (3) the markdown structure is intact

#### Scenario: Over-redaction detected
- **WHEN** the agent reads the sanitized output and finds meaningful content was incorrectly redacted (e.g., a technical term flagged as high-entropy)
- **THEN** the agent SHALL rewrite the affected section to convey the same information without including the triggering pattern
- **AND** SHALL re-run sanitization on the corrected content
- **AND** SHALL make at most one rewrite attempt; if sanitization still flags the rewrite, the skill SHALL proceed without the session log for that phase

#### Scenario: Sanitization failure on any skill
- **WHEN** `sanitize_session_log.py` exits non-zero during any workflow skill (not just cleanup)
- **THEN** the skill SHALL NOT commit the session-log.md
- **AND** SHALL log a warning and proceed without the session log for that phase
- **AND** SHALL NOT block the workflow

### Requirement: Merge Log Artifact

The `/merge-pull-requests` skill SHALL produce a dated merge log capturing cross-PR triage reasoning, user decisions, and observations.

#### Scenario: Merge log written to dated file
- **WHEN** `/merge-pull-requests` completes a merge session
- **THEN** it SHALL write to `docs/merge-logs/YYYY-MM-DD.md` (using the current date)
- **AND** the entry SHALL contain: session timestamp (HH:MM), agent type, PR triage table (PR number, origin, action, rationale), vendor review findings, user decisions, and observations

#### Scenario: Merge log directory auto-creation
- **WHEN** `/merge-pull-requests` attempts to write the merge log and `docs/merge-logs/` does not exist
- **THEN** the skill SHALL create the directory before writing
- **AND** the repository SHALL contain `docs/merge-logs/.gitkeep` to ensure directory persistence after initial setup

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

#### Scenario: Vendor review incomplete or timed out
- **WHEN** vendor reviews were dispatched but one or more vendors did not respond or timed out
- **THEN** the merge log SHALL note which vendors responded and which timed out
- **AND** SHALL record findings from responding vendors only

#### Scenario: PR comments for contributor visibility
- **WHEN** a PR is closed or skipped during merge triage
- **THEN** the skill SHALL still post a brief PR comment explaining the action
- **AND** the detailed rationale SHALL be in the merge log, not duplicated in the PR comment

#### Scenario: Merge log sanitization
- **WHEN** a merge-log entry is written
- **THEN** the skill SHALL run `sanitize_session_log.py` on the file before committing
- **AND** the agent SHALL verify the sanitized output using the same criteria as session-log verification

### Requirement: Phase Names for Session Log Entries

Each workflow skill SHALL use a consistent phase name when appending to session-log.md.

#### Scenario: Phase name mapping
- **WHEN** a workflow skill appends a session-log entry
- **THEN** it SHALL use the following phase names:
  - `/plan-feature` → `Plan`
  - `/iterate-on-plan` → `Plan Iteration <N>`
  - `/implement-feature` → `Implementation`
  - `/iterate-on-implementation` → `Implementation Iteration <N>`
  - `/validate-feature` → `Validation`
  - `/cleanup-feature` → `Cleanup`
  - `/merge-pull-requests` → (uses merge-log, not session-log)

#### Scenario: Iteration number auto-increment
- **WHEN** a skill uses an iteration phase name (`Plan Iteration <N>` or `Implementation Iteration <N>`)
- **THEN** it SHALL determine N by counting existing `## Phase: <exact-prefix>` headers in session-log.md (e.g., count `## Phase: Plan Iteration` headers for Plan Iteration, count `## Phase: Implementation Iteration` headers for Implementation Iteration — each prefix counted independently) and adding 1
- **AND** if no prior iteration entries exist for that prefix, N SHALL be 1
- **AND** iteration numbering SHALL be scoped to the change-id (not per-agent or per-branch)

### Requirement: Session Log Committed with Phase Artifacts

Session log updates SHALL be committed alongside other phase artifacts, not in separate commits.

#### Scenario: Skills that commit artifacts
- **WHEN** a skill already commits artifacts (plan-feature, implement-feature, cleanup-feature, iterate-on-plan, iterate-on-implementation)
- **THEN** the session-log.md SHALL be included in the same commit via `git add`
- **AND** SHALL NOT require a separate commit

#### Scenario: Skills that don't normally commit
- **WHEN** a skill does not normally commit artifacts but updates session-log.md (validate-feature)
- **THEN** the skill SHALL commit the session-log.md update as a small dedicated commit
- **AND** SHALL push to the feature branch
