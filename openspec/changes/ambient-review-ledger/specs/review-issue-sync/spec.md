## ADDED Requirements

### Requirement: Confirmed findings filed as issues

The system SHALL file confirmed or blocking ledger findings as GitHub issues via
the existing GitHub MCP tools, with deduplication so a finding is filed at most
once.

#### Scenario: Blocking finding becomes an issue

- **WHEN** the ledger contains an `open` finding whose criticality is blocking
  (medium or higher) and that is confirmed
- **THEN** the system SHALL create a GitHub issue describing the finding,
  including its file path, line range, and recommended disposition
- **AND** the system SHALL record the issue number against the ledger finding

#### Scenario: No duplicate issue for an already-filed finding

- **WHEN** issue sync runs again and a finding already has a recorded issue
  number
- **THEN** the system SHALL NOT create a second issue for that finding

### Requirement: Auto-close issues on retire

The system SHALL close the GitHub issue associated with a ledger finding when
that finding transitions to `retired` by the `compact` re-verification pass.

#### Scenario: Retired finding closes its issue

- **WHEN** `compact` transitions a finding with an associated issue number to
  `retired`
- **THEN** the system SHALL close the corresponding GitHub issue with a comment
  noting the finding was resolved/no-longer-applicable
- **AND** the ledger SHALL record the closure

#### Scenario: Issue sync is opt-in safe

- **WHEN** GitHub credentials or MCP tools are unavailable
- **THEN** issue sync SHALL no-op with a warning and SHALL NOT fail the ledger or
  review pipeline
