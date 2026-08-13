# harness-engineering — delta for add-atomic-harness

Adds transcript mining coverage for the atomic harness's session store.

## ADDED Requirements

### Requirement: Atomic Session Transcript Adapter

The transcript collection system SHALL provide an `atomic_cli` adapter
(`HARNESS_ID="atomic_cli"`, `SCHEMA_VERSION="atomic-jsonl-v3"`) that discovers Atomic
sessions under `~/.atomic/agent/sessions/<cwd-slug>/` (files named
`<ISO-timestamp>_<uuid>.jsonl` with a `{"type":"session","version":3}` header line) and
normalizes them to the common event schema, following the same fail-soft contract as
other harness adapters.

The adapter SHALL document that headless workflow-only runs (no model stages) may
produce no session file, and SHALL treat that gap as an empty result rather than an
error.

#### Scenario: Atomic sessions are discovered and normalized

- **GIVEN** at least one Atomic session file exists under the session store
- **WHEN** `/collect-transcripts` runs with the `atomic_cli` adapter selected
- **THEN** the adapter SHALL enumerate the session files and emit normalized events per session conforming to the common event schema
- **AND** the assistant/user role mapping SHALL account for Atomic echoing the prompt back as a user message in its event stream

#### Scenario: Missing session store fails soft

- **GIVEN** `~/.atomic/agent/sessions/` does not exist
- **WHEN** the `atomic_cli` adapter runs
- **THEN** it SHALL log a structured warning identifying the harness and reason
- **AND** exit with a non-fatal status that does not block other adapters
