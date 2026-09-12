## ADDED Requirements

### Requirement: Review Packet As Default Input

The dispatcher and `converge()` SHALL build a review packet before dispatch
containing: the schema-derived prompt contract, a unified or last-fix diff,
traced spec excerpts, and open ledger items when a ledger exists. The packet
SHALL be written to the round directory with a checksum. When the packet is
under the contracted size budget, the prompt SHALL tell the reviewer the
packet is complete and not to explore the repo for missing artifacts.

#### Scenario: Packet includes diff and schema contract

- **WHEN** a review round is dispatched
- **THEN** the round directory SHALL contain a packet file whose body includes
  a diff hunk header or an explicit empty-diff marker
- **AND** includes the required finding fields from the canonical schema

#### Scenario: Missing ledger still builds a packet

- **WHEN** `.review-ledger/` is absent
- **THEN** the packet SHALL still be built from diff, specs, and schema
  contract
- **AND** dispatch SHALL proceed

#### Scenario: Over-budget packet sets tools overflow

- **WHEN** the packet body exceeds the contracted size budget
- **THEN** the packet metadata SHALL set `tools_overflow` true
- **AND** the prompt SHALL allow Read/Grep to recover truncated context

### Requirement: Verify-Then-Wire Structured Output

A vendor's review-mode CLI SHALL gain structured-output / JSON-schema flags
only after an empirical probe recorded in this change's contracts marks that
vendor `verified`. Unprobed or absent flags SHALL leave the vendor on the
phase-1 prompt path. The dispatcher SHALL NOT guess flags.

#### Scenario: Grok remains schema-injected

- **WHEN** a grok review is dispatched
- **THEN** the command SHALL include `--json-schema` with the canonical
  schema sentinel or its injected value

#### Scenario: Unprobed vendor is not given Grok's flags

- **WHEN** a vendor whose structured-output row is `unprobed` or `absent`
  is dispatched
- **THEN** the command SHALL NOT include Grok's `--json-schema` sentinel
  unless that vendor's own probe recorded `verified`

## MODIFIED Requirements

### Requirement: Parallel Review Dispatch

The `ReviewDispatcher` SHALL execute vendor reviews in parallel (concurrent
subprocess invocation). Wall-clock time for a round SHALL be dominated by
the slowest vendor, not the sum of vendors. Async submit+poll vendors SHALL
be submitted concurrently, then polled. Review cwd SHALL be read-only; if a
vendor CLI fails because of concurrent git access, the dispatcher SHALL
retry that vendor on a detached snapshot worktree.

#### Scenario: Parallel dispatch to multiple vendors

- **GIVEN** Codex and grok are both available
- **WHEN** the dispatcher dispatches reviews
- **THEN** both vendor subprocesses are started concurrently
- **AND** results are collected as each completes
- **AND** a test with two 2-second stub processes SHALL finish in under 3
  seconds

#### Scenario: Sequential dispatch is a bug

- **GIVEN** two stub vendors that each sleep 2 seconds
- **WHEN** `dispatch_and_wait` runs
- **THEN** elapsed time SHALL be less than 4 seconds
