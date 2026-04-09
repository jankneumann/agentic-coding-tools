# Agent Coordinator — Progressive Discovery Help System

**Change ID**: `cli-help-discovery`

## ADDED Requirements

### Requirement: Progressive Discovery Help

The coordinator SHALL provide a help system that enables agents to discover capabilities on-demand using a two-tier progressive disclosure model, rather than requiring all tool schemas to be loaded upfront.

- The help system SHALL expose a compact overview listing all capability groups with one-line summaries
- The help system SHALL expose detailed per-topic guides including workflow steps, best practices, and code examples
- The help system SHALL be available on all three coordinator transports: MCP, HTTP, and CLI
- The help content SHALL be transport-agnostic — identical content regardless of the caller's transport
- The help system SHALL show all capability topics regardless of which capabilities are currently available
- The help system SHALL NOT require authentication on any transport
- The help system SHALL support future runtime extension without breaking the existing interface

#### Scenario: Agent requests capability overview

- **WHEN** an agent calls `help()` with no topic argument (MCP) or `GET /help` (HTTP) or `coordination-cli help` (CLI)
- **THEN** the system SHALL return a structured overview containing all capability groups
- **AND** each group SHALL include a `topic` name, `summary` description, and `tools_count`
- **AND** the overview SHALL include a `usage` hint explaining how to drill into specific topics
- **AND** the response SHALL include a `version` field matching the coordinator version

#### Scenario: Agent requests detailed topic help

- **WHEN** an agent calls `help(topic="locks")` (MCP) or `GET /help/locks` (HTTP) or `coordination-cli help locks` (CLI)
- **THEN** the system SHALL return a detailed guide for the specified topic
- **AND** the guide SHALL include: `topic`, `summary`, `description`, `tools` (list), `workflow` (ordered steps), `best_practices` (list), `examples` (list with `description` and `code`), and `related_topics` (list)

#### Scenario: Agent requests unknown topic

- **WHEN** an agent calls `help(topic="nonexistent")` (MCP) or `GET /help/nonexistent` (HTTP)
- **THEN** the system SHALL return an error response indicating the topic was not found
- **AND** the response SHALL include the list of available topic names
- **AND** the HTTP transport SHALL return status code 404

#### Scenario: Help available without authentication

- **WHEN** an agent calls `GET /help` or `GET /help/{topic}` without an `X-API-Key` header
- **THEN** the system SHALL return the help content with status code 200 (or 404 for unknown topics)
- **AND** the system SHALL NOT return 401 Unauthorized

#### Scenario: Help overview is context-efficient

- **WHEN** an agent requests the help overview
- **THEN** the serialized JSON response SHALL be compact enough to consume less than 500 estimated tokens (approximately 2000 characters)
- **AND** the overview MUST NOT include detailed workflow steps, examples, or best practices (those belong in per-topic detail)

#### Scenario: Help covers all coordinator capability groups

- **WHEN** an agent requests the help overview
- **THEN** the response SHALL include topics for at minimum: `locks`, `work-queue`, `issues`, `handoffs`, `memory`, `discovery`, `guardrails`, `profiles`, `policy`, `audit`, `features`, `merge-queue`, `approvals`, `ports`, `status`

#### Scenario: Related topics reference valid topics

- **WHEN** an agent requests detailed help for any topic
- **THEN** every entry in `related_topics` SHALL correspond to a valid topic name that exists in the help registry

#### Scenario: CLI human-readable output

- **WHEN** a user runs `coordination-cli help` without `--json`
- **THEN** the output SHALL be formatted for human readability with aligned columns
- **AND** the output SHALL include a usage hint for drilling into topics

#### Scenario: CLI JSON output

- **WHEN** a user runs `coordination-cli --json help locks`
- **THEN** the output SHALL be valid JSON matching the same schema as the MCP and HTTP responses
