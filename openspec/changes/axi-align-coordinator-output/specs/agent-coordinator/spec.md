## ADDED Requirements

### Requirement: AXI-Aligned List Output Contract

`coordination-cli` commands that return a collection of rows SHALL emit an
agent-ergonomic envelope rather than a bare JSON array, so that an agent can
act on a single response without a defensive follow-up call. The envelope
SHALL carry, at minimum, the row count, an explicit truncation flag, and the
rows themselves.

This applies to: `feature list`, `merge-queue status`, `lock status`,
`handoff read`, `memory query`, and `audit query`.

The envelope SHALL contain:

- `count` — the number of rows returned (an integer; `0` for an empty result).
- `truncated` — a boolean that is `true` only when a `--limit` cut the result
  short, i.e. more rows exist than were returned.
- `items` — the array of row objects, each retaining its existing per-row
  schema.
- `hint` (present only when `truncated` is `true`) — a human-readable string
  telling the agent how to retrieve more rows.
- `next_steps` (optional) — an array of suggested follow-up command strings.

#### Scenario: Non-empty list returns an envelope

- **WHEN** an agent runs a list command (e.g. `coordination-cli --json feature list`) that has matching rows
- **THEN** the CLI SHALL print a JSON object whose `count` equals the number of rows
- **AND** whose `items` is the array of row objects
- **AND** whose `truncated` is `false`
- **AND** the process SHALL exit `0`

#### Scenario: Empty result is definitive

- **WHEN** an agent runs a list command that has no matching rows
- **THEN** the CLI SHALL print an envelope with `count` equal to `0` and `items` equal to `[]`
- **AND** SHALL NOT print a bare `[]`
- **AND** the process SHALL exit `0`

#### Scenario: Truncated result flags more data and how to page

- **WHEN** an agent runs a limited list command (`audit query`, `memory query`, or `handoff read`) with `--limit N`
- **AND** more than `N` rows match
- **THEN** the CLI SHALL return exactly `N` rows in `items`
- **AND** `truncated` SHALL be `true`
- **AND** the envelope SHALL include a `hint` referencing `--limit`

#### Scenario: Exact-limit result is not falsely truncated

- **WHEN** an agent runs a limited list command with `--limit N`
- **AND** exactly `N` rows match
- **THEN** `truncated` SHALL be `false`
- **AND** the envelope SHALL NOT include a `hint`

#### Scenario: Truncation detection uses the limit+1 probe

- **WHEN** the CLI services a limited list command with `--limit N`
- **THEN** it SHALL request `N + 1` rows from the service layer
- **AND** SHALL report `truncated` as `true` if more than `N` rows are returned
- **AND** SHALL trim the response back to `N` rows before printing

#### Scenario: Contextual next steps are surfaced in-band

- **WHEN** an agent runs a list command that defines follow-up actions
- **THEN** the envelope SHALL include a `next_steps` array of suggested command strings

### Requirement: AXI-Aligned HTTP List Output

HTTP API endpoints that return a collection of rows SHALL augment their
response with the same AXI signals as the CLI, but **additively** — the
existing named array key (e.g. `features`, `entries`, `memories`, `handoffs`)
SHALL be preserved so existing clients continue to work, and the `count`,
`truncated`, and (when applicable) `hint` and `next_steps` fields SHALL be
added as sibling keys.

This applies to `GET /features/active`, `GET /merge-queue`, `GET /audit`,
`POST /memory/query`, and `POST /handoffs/read`.

#### Scenario: HTTP list response preserves its named array key

- **WHEN** a client calls a list endpoint (e.g. `GET /features/active`)
- **THEN** the response SHALL still contain the endpoint's existing named array key holding the row objects
- **AND** SHALL additionally contain a `count` equal to the number of rows
- **AND** SHALL contain a boolean `truncated`

#### Scenario: HTTP empty result is definitive

- **WHEN** a client calls a list endpoint that matches no rows
- **THEN** the named array key SHALL hold `[]`
- **AND** `count` SHALL be `0`
- **AND** `truncated` SHALL be `false`

#### Scenario: HTTP limited endpoint flags truncation

- **WHEN** a client calls a limited endpoint (`GET /audit`, `POST /memory/query`, or `POST /handoffs/read`) whose result exceeds the requested `limit`
- **THEN** the endpoint SHALL request `limit + 1` rows from the service layer to detect truncation
- **AND** SHALL return exactly `limit` rows under the named key
- **AND** `truncated` SHALL be `true` with a `hint` describing how to page

#### Scenario: Handoff rows avoid the next_steps key collision

- **WHEN** a client calls `POST /handoffs/read`
- **THEN** each handoff row MAY include its own semantic `next_steps` field
- **AND** the response SHALL NOT add a top-level `next_steps` command-suggestion key

## MODIFIED Requirements

### Requirement: CLI Entry Point

The coordinator SHALL provide a `coordination-cli` command-line entry point with subcommand groups for all coordinator capabilities.

#### Scenario: CLI feature list with JSON output

- WHEN a user runs `coordination-cli --json feature list`
- THEN the CLI SHALL print a JSON object containing an `items` array of active features, a `count`, and a `truncated` flag to stdout and exit 0

#### Scenario: CLI help text

- WHEN a user runs `coordination-cli --help`
- THEN the CLI SHALL print usage information including all subcommand groups

#### Scenario: CLI merge-queue enqueue

- WHEN a user runs `coordination-cli merge-queue enqueue --feature-id X`
- THEN the CLI SHALL delegate to `MergeQueueService.enqueue()` and print the result

#### Scenario: CLI with database unavailable

- WHEN a user runs any CLI command and the database is unreachable
- THEN the CLI SHALL print an error message to stderr and exit with non-zero code
