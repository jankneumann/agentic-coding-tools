# skill-workflow Delta Spec — store-conversation-history

## ADDED

### Requirement: Session Log Artifact

The system SHALL provide a `session-log.md` artifact that captures a structured summary of the agent conversation/session history for each OpenSpec change. The artifact SHALL focus on decision rationale, trade-offs, alternatives considered, and key discussion points — not on replicating code diffs already stored in git.

#### Scenario: Session log generated during cleanup
- **WHEN** `/cleanup-feature <change-id>` or `/linear-cleanup-feature <change-id>` executes
- **AND** agent session context is available (conversation history, handoff documents, or session transcript)
- **THEN** the skill SHALL generate `openspec/changes/<change-id>/session-log.md`
- **AND** the artifact SHALL contain structured sections: Summary, Key Decisions, Alternatives Considered, Trade-offs, Open Questions, and Session Metadata

#### Scenario: Session log generated during parallel cleanup
- **WHEN** `/parallel-cleanup-feature <change-id>` executes
- **AND** multiple agent sessions contributed to the change
- **THEN** the skill SHALL generate a consolidated `session-log.md` combining context from all contributing agent sessions
- **AND** each entry SHALL identify the originating agent/session

#### Scenario: No session context available
- **WHEN** cleanup executes but no agent session context is accessible (e.g., session expired, agent type doesn't support history export)
- **THEN** the skill SHALL skip session log generation with an informational message
- **AND** cleanup SHALL proceed without error

#### Scenario: Session log is optional
- **WHEN** a change is archived without a `session-log.md`
- **THEN** OpenSpec validation SHALL NOT report an error
- **AND** the change SHALL be considered complete

### Requirement: Session Log Content Structure

The `session-log.md` artifact SHALL follow a structured format with the following sections:

- **Summary**: 2-3 sentence overview of what was discussed and decided during the session(s)
- **Key Decisions**: Numbered list of significant decisions with brief rationale for each
- **Alternatives Considered**: For each key decision, alternatives that were discussed and why they were rejected
- **Trade-offs**: Explicit trade-offs accepted in the implementation (e.g., "chose simplicity over performance because...")
- **Open Questions**: Unresolved questions or concerns raised during the session that may need future attention
- **Session Metadata**: Agent type, session ID(s), date range, number of interactions

#### Scenario: Content focuses on rationale not code
- **WHEN** the session log is generated
- **THEN** it SHALL NOT include raw code blocks, full file contents, or diff output
- **AND** it SHALL reference files by path when relevant context requires it
- **AND** it SHALL focus on the reasoning behind decisions, not the mechanical steps taken

#### Scenario: Content is concise
- **WHEN** the session log is generated from a long conversation
- **THEN** the artifact SHALL be a summarized distillation, not a full transcript
- **AND** the total length SHOULD NOT exceed 500 lines

### Requirement: Session Log Sanitization

All session log content SHALL be sanitized before being committed to git to prevent accidental exposure of secrets or sensitive information.

#### Scenario: Secrets detected and redacted
- **WHEN** the session log content contains patterns matching known secret formats (API keys, tokens, passwords, connection strings, private keys, AWS credentials, environment variable values)
- **THEN** the sanitization script SHALL replace each detected secret with `[REDACTED:<type>]` (e.g., `[REDACTED:api-key]`, `[REDACTED:password]`)
- **AND** SHALL log a warning indicating the number and types of redactions performed

#### Scenario: High-entropy strings detected
- **WHEN** the session log content contains strings with high Shannon entropy (>4.5 bits/char) that are longer than 20 characters and not obviously code identifiers
- **THEN** the sanitization script SHALL flag them for review
- **AND** SHALL redact them by default with `[REDACTED:high-entropy]`

#### Scenario: Environment-specific paths redacted
- **WHEN** the session log contains user home directory paths, absolute system paths, or hostnames that could reveal infrastructure details
- **THEN** the sanitization script SHALL normalize them (e.g., `/home/user/...` → `~/.../`, hostnames → `[HOST]`)

#### Scenario: Sanitization script exit codes
- **WHEN** the sanitization script runs
- **THEN** it SHALL exit 0 if no secrets were found or all were successfully redacted
- **AND** it SHALL exit 1 if sanitization encountered an error that could allow secrets through
- **AND** cleanup SHALL abort committing the session log if the script exits non-zero

#### Scenario: No false positives on common patterns
- **WHEN** the session log contains UUIDs, git SHAs, OpenSpec change-ids, or file paths
- **THEN** these SHALL NOT be redacted as they are common development identifiers

### Requirement: Session Log Extraction

The system SHALL support extracting session context from multiple agent types using a provider-agnostic approach.

#### Scenario: Claude Code session extraction
- **WHEN** the active agent is Claude Code
- **THEN** the extraction script SHALL attempt to read the session transcript from Claude Code's local session storage
- **AND** SHALL extract key decisions, user confirmations, and rationale discussions
- **AND** SHALL summarize the conversation into the structured session-log format

#### Scenario: Handoff documents as fallback source
- **WHEN** direct session transcript access is not available
- **AND** `CAN_HANDOFF=true` and handoff documents exist for the change
- **THEN** the extraction script SHALL compile session context from handoff document history (summary, decisions, completed_work fields)
- **AND** SHALL note in Session Metadata that the log was derived from handoff documents

#### Scenario: Manual session log
- **WHEN** automated extraction is not possible (unsupported agent type, no handoff documents)
- **THEN** the cleanup skill SHALL prompt the agent to generate a session log from its current context window
- **AND** the agent SHALL produce the structured summary from its available conversation memory

### Requirement: Cleanup Skill Session Log Integration

The cleanup skills SHALL integrate session log generation as a step before archiving.

#### Scenario: Linear cleanup generates session log
- **WHEN** `/linear-cleanup-feature <change-id>` reaches the archive step
- **THEN** it SHALL first attempt to generate `session-log.md` via the extraction and sanitization pipeline
- **AND** SHALL commit the session log with the archive commit
- **AND** the session log SHALL be included in the archived change directory

#### Scenario: Parallel cleanup consolidates session logs
- **WHEN** `/parallel-cleanup-feature <change-id>` reaches the archive step
- **AND** multiple agent worktrees contributed to the implementation
- **THEN** it SHALL collect session context from each agent's handoff documents
- **AND** consolidate into a single `session-log.md` with per-agent sections
- **AND** commit and archive as with linear cleanup

#### Scenario: Session log generation failure does not block cleanup
- **WHEN** session log generation or sanitization fails
- **THEN** the cleanup skill SHALL log a warning
- **AND** SHALL proceed with archive without the session log
- **AND** SHALL NOT retry or block the cleanup workflow
