# observability Specification (delta)

## MODIFIED Requirements

### Requirement: Claude Code Session Tracing Hook

The system SHALL provide a Claude Code Stop hook (`skills/langfuse/scripts/langfuse_hook.py`) that
sends session usage to Langfuse incrementally as a secondary view of the same normalized events the
usage ledger ingests.

- The hook SHALL only run when `LANGFUSE_ENABLED=true` and both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set
- The hook SHALL parse transcripts through the `collect-transcripts` Claude Code adapter, which understands the real transcript shape (`{"type": "assistant", "message": {"role": ..., "model": ..., "usage": ...}}`); the hook SHALL NOT keep a private transcript parser
- The hook SHALL process the parent transcript and every `subagents/agent-*.jsonl` sidechain transcript for the session
- The hook SHALL track processing state per file in `~/.claude/state/langfuse_state_<hash>.json`
- The hook SHALL advance the state cursor by **lines consumed** (not messages parsed) to handle blank and invalid JSON lines correctly
- The hook SHALL create one Langfuse trace per session per run, with one `generation` observation per assistant message carrying `model`, `usage_details` (`input`, `output`, `cache_read`, `cache_creation`, and `thinking` when present), and metadata `effort`, `agent_id`, `change_id`, and `phase` when a dispatch record is known locally
- Tool calls SHALL be nested as `tool` observations under the generation that issued them
- The hook SHALL sanitize all text via the `collect-transcripts` sanitizer before sending to Langfuse, redacting API keys, Langfuse keys, Supabase keys, JWT tokens, bearer tokens, and generic key=value secret patterns
- Sanitization patterns SHALL be ordered from most specific to most general to preserve descriptive redaction markers
- The hook SHALL create the Langfuse client with `timeout=5` to limit blocking when the server is unreachable
- The hook SHALL handle client creation failures gracefully (log warning, return 0)
- The hook SHALL advance the cursor even when no assistant messages are found (to avoid re-reading orphan lines)
- The coordinator-side `langfuse_middleware.py` and `langfuse_tracing.py` helpers are known to call the v2 SDK API against the pinned v4 SDK and emit nothing; this requirement does not cover them, and their repair is owned by `add-cross-harness-flow-display`

#### Scenario: Real transcript shape produces generations

- **WHEN** the hook runs over a transcript whose lines are `{"type": "assistant", "message": {...}}` records
- **THEN** it SHALL emit one `generation` observation per assistant record
- **AND** each generation's `usage_details.input` SHALL equal that record's `message.usage.input_tokens`

#### Scenario: Incremental transcript processing

- **WHEN** the hook runs and the transcript has 10 new lines since last run, 2 of which are blank
- **THEN** the hook processes 8 valid records
- **AND** advances the cursor by 10 (lines consumed, not messages parsed)

#### Scenario: Secret sanitization

- **WHEN** a tool output contains `sk-lf-local-coding-agents` and `password=secret123`
- **THEN** the Langfuse observation input/output contains `LF-KEY-REDACTED` and `password=REDACTED`
- **AND** the original secret values do not appear in the Langfuse trace

#### Scenario: Langfuse server unreachable

- **WHEN** `LANGFUSE_ENABLED=true` but the Langfuse server at `LANGFUSE_HOST` is not reachable
- **THEN** the hook logs a warning and returns without sending traces
- **AND** the state cursor is NOT advanced (so records will be retried on next run)

#### Scenario: Langfuse computes cost from usage details

- **GIVEN** a generation observation with `model = "claude-opus-5"` and populated `usage_details`
- **WHEN** Langfuse ingests it
- **THEN** the observation SHALL show a non-null calculated cost in the Langfuse UI for a model Langfuse prices
