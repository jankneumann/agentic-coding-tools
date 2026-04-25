# skill-workflow Specification Delta — Phase Record Compaction

**Spec ID**: skill-workflow
**Change ID**: phase-record-compaction
**Status**: Draft

## ADDED Requirements

### Requirement: Phase Record Data Model

The system SHALL provide a unified `PhaseRecord` data model in `skills/session-log/scripts/phase_record.py` that captures all information about a workflow phase boundary in a single structured object renderable to both markdown (for `session-log.md`) and JSON (for coordinator `handoff_documents`).

The `PhaseRecord` dataclass SHALL contain at minimum the following fields:
- `change_id: str`
- `phase_name: str` (e.g., `"Plan"`, `"Implementation Iteration 2"`)
- `agent_type: str`
- `session_id: str | None`
- `summary: str` (2-3 sentence overview)
- `decisions: list[Decision]`
- `alternatives: list[Alternative]`
- `trade_offs: list[TradeOff]`
- `open_questions: list[str]`
- `completed_work: list[str]`
- `in_progress: list[str]`
- `next_steps: list[str]`
- `relevant_files: list[FileRef]`

The `Decision` sub-dataclass SHALL contain `title: str`, `rationale: str`, `capability: str | None` (kebab-case capability identifier matching `openspec/specs/<capability>/`), and `supersedes: str | None` (`<change-id>#D<n>` reference).

The `FileRef` sub-dataclass SHALL contain `path: str` and `description: str` (≤120 chars).

#### Scenario: Round-trip equality through markdown
- **WHEN** a `PhaseRecord` is rendered via `render_markdown()` to a string `S`
- **AND** the string `S` is parsed back into a `PhaseRecord` via `parse_markdown(S)`
- **THEN** the resulting `PhaseRecord` SHALL equal the original (field-by-field equality)
- **AND** all `Decision.capability` and `Decision.supersedes` values SHALL be preserved without loss

#### Scenario: Round-trip equality through handoff payload
- **WHEN** a `PhaseRecord` is rendered via `to_handoff_payload()` to a `dict`
- **AND** the dict is constructed back into a `PhaseRecord` via `from_handoff_payload(d)`
- **THEN** the resulting `PhaseRecord` SHALL equal the original (field-by-field equality)

#### Scenario: Empty optional sections render compactly
- **WHEN** a `PhaseRecord` is rendered to markdown with empty `alternatives`, `trade_offs`, `open_questions`, `completed_work`, or `relevant_files`
- **THEN** the rendered markdown SHALL omit those sections entirely (no empty headers)
- **AND** the `summary`, `decisions` (if non-empty), and section header SHALL still be present

### Requirement: Phase Record Persistence Pipeline

The `PhaseRecord.write_both()` method SHALL persist the record through a three-step pipeline in this fixed order: (1) append the rendered markdown to `openspec/changes/<change-id>/session-log.md`, (2) run `sanitize_session_log.py` in-place on the file, (3) write the structured payload to the coordinator via `HandoffService.write(...)` or fall back to a local file.

Each step SHALL be best-effort with independent failure handling. A failure in any step SHALL log a warning to stderr and SHALL NOT raise an exception. The method SHALL return a `PhaseWriteResult` dataclass containing `markdown_path: Path | None`, `sanitized: bool`, `handoff_id: str | None`, `handoff_local_path: Path | None`, and `warnings: list[str]`.

When the coordinator write fails (returns `success=False`, raises, or times out), `write_both()` SHALL write the same payload as JSON to `openspec/changes/<change-id>/handoffs/<phase-slug>-<N>.json` where `<phase-slug>` is `phase_name.lower().replace(" ", "-")` and `<N>` auto-increments per phase using the same counting logic as `count_phase_iterations`.

#### Scenario: All three steps succeed
- **WHEN** `PhaseRecord(...).write_both()` is called with coordinator available
- **THEN** the markdown SHALL be appended to `session-log.md`
- **AND** the sanitizer SHALL run in-place and exit zero
- **AND** the coordinator SHALL receive a `write_handoff` call returning `success=True`
- **AND** the result SHALL contain `handoff_id` and `markdown_path`, with `warnings = []`

#### Scenario: Coordinator unavailable triggers local-file fallback
- **WHEN** `PhaseRecord(...).write_both()` is called and the coordinator returns `success=False` or raises
- **THEN** the markdown append and sanitization SHALL still complete
- **AND** the JSON payload SHALL be written to `openspec/changes/<change-id>/handoffs/<phase-slug>-<N>.json`
- **AND** the result SHALL contain `handoff_local_path` set to the JSON file path
- **AND** the result SHALL contain a warning describing the coordinator failure
- **AND** no exception SHALL be raised

#### Scenario: Sanitizer failure does not block coordinator write
- **WHEN** `PhaseRecord(...).write_both()` is called and the sanitizer exits non-zero
- **THEN** the markdown append SHALL still complete
- **AND** the coordinator write SHALL still proceed using the unsanitized in-memory payload
- **AND** the result SHALL contain `sanitized=False` and a warning describing the sanitizer failure

#### Scenario: Markdown append failure does not block coordinator write
- **WHEN** `PhaseRecord(...).write_both()` is called and the markdown append fails (e.g., disk full, permission denied)
- **THEN** the coordinator write SHALL still proceed
- **AND** the result SHALL contain `markdown_path=None` and a warning describing the append failure

### Requirement: Phase-Boundary Skill PhaseRecord Adoption

All six phase-boundary skills (`plan-feature`, `iterate-on-plan`, `implement-feature`, `iterate-on-implementation`, `validate-feature`, `cleanup-feature`) SHALL invoke `PhaseRecord(...).write_both()` at their phase-boundary write step in place of the previous `append_phase_entry(...)` call.

Each skill's "Append Session Log" step (or equivalently named step) SHALL construct a `PhaseRecord` with at least the `change_id`, `phase_name`, `agent_type`, `summary`, and at least one of `decisions` or a `summary` containing "No significant decisions required" before calling `write_both()`.

The legacy `append_phase_entry()` function in `skills/session-log/scripts/extract_session_log.py` SHALL remain available as a deprecation-warned compatibility shim that internally constructs a minimal `PhaseRecord` and calls `write_both()`. Calls to the shim SHALL emit a `DeprecationWarning`.

#### Scenario: A skill produces matching session-log and coordinator content
- **WHEN** any of the six phase-boundary skills runs to completion in coordinated tier
- **THEN** the resulting `session-log.md` entry for the phase SHALL contain the same `summary`, `decisions`, and `relevant_files` content as the corresponding row in `handoff_documents` (read back via `read_handoff`)
- **AND** the entry's structured fields SHALL be derivable from each other (round-trip)

#### Scenario: Legacy append_phase_entry callers continue working
- **WHEN** any caller (including out-of-tree scripts) invokes `append_phase_entry(change_id, phase_name, content)`
- **THEN** the call SHALL succeed
- **AND** a `DeprecationWarning` SHALL be emitted via the standard `warnings` module
- **AND** the markdown content SHALL be appended to `session-log.md`
- **AND** if the coordinator is available, a handoff row SHALL be written

### Requirement: Coordinator Handoff Population at Autopilot Phase Boundaries

The autopilot state machine in `skills/autopilot/scripts/autopilot.py` SHALL populate structured `PhaseRecord` payloads at each of the boundaries enumerated in `_HANDOFF_BOUNDARIES`. The `_maybe_handoff(prev_phase, next_phase, state, handoff_fn)` dispatch SHALL call `handoff_fn(state, build_phase_record(state, prev_phase, next_phase))` instead of passing a transition-description string.

The autopilot driver SHALL append the returned `handoff_id` to `LoopState.handoff_ids: list[str]` and set `LoopState.last_handoff_id: str | None`. The `LoopState` schema version SHALL increment to reflect the addition of `last_handoff_id`. Existing snapshots (without `last_handoff_id`) SHALL load successfully with `last_handoff_id=None`.

A new module `skills/autopilot/scripts/handoff_builder.py` SHALL expose `build_phase_record(state: LoopState, prev_phase: str, next_phase: str) -> PhaseRecord` and per-phase builder helpers that extract relevant `LoopState` fields into `PhaseRecord` content.

#### Scenario: Handoff is populated on each defined boundary
- **WHEN** autopilot transitions across any pair in `_HANDOFF_BOUNDARIES`
- **THEN** `_maybe_handoff` SHALL call `handoff_fn` with a `PhaseRecord` instance
- **AND** the `PhaseRecord` SHALL contain at minimum `change_id`, `phase_name=next_phase`, `agent_type="autopilot"`, and a non-empty `summary`
- **AND** the returned `handoff_id` SHALL be appended to `state.handoff_ids`
- **AND** `state.last_handoff_id` SHALL be updated to the returned id

#### Scenario: Existing autopilot snapshots load without migration
- **WHEN** an existing `LoopState` JSON snapshot lacking `last_handoff_id` is loaded
- **THEN** the load SHALL succeed
- **AND** `state.last_handoff_id` SHALL be `None`
- **AND** `state.handoff_ids` SHALL be an empty list (or its prior value if previously populated)

### Requirement: Autopilot Phase Sub-Agent Isolation

The autopilot driver SHALL invoke the three heaviest phases (`IMPLEMENT`, `IMPL_REVIEW`, `VALIDATE`) as ephemeral sub-agents via the `Agent` tool. The sub-agent prompt SHALL include: (1) an artifacts manifest listing relevant file paths with short descriptions, (2) the incoming `PhaseRecord` from the previous phase rendered as JSON, and (3) phase-specific task instructions.

The sub-agent SHALL return exactly two pieces of information to the driver: an `outcome: str` (matching the existing phase-callback outcome vocabulary) and a `handoff_id: str` referencing the structured `PhaseRecord` written at exit. The driver SHALL NOT consume any other content from the sub-agent's transcript.

A new module `skills/autopilot/scripts/phase_agent.py` SHALL expose `run_phase_subagent(phase: str, state: LoopState, incoming_handoff: PhaseRecord | None) -> tuple[str, str]` and SHALL apply `isolation: "worktree"` only when `phase == "IMPLEMENT"`.

The `IMPL_REVIEW` and `VALIDATE` sub-agents SHALL run in the shared checkout (no worktree isolation).

#### Scenario: Sub-agent return surfaces only outcome and handoff_id
- **WHEN** a Layer 2 phase sub-agent returns to the driver
- **THEN** the driver's `LoopState` delta SHALL be exactly `{handoff_ids: append(handoff_id), last_handoff_id: handoff_id, current_phase: <next>}` plus phase-specific outcome counters
- **AND** the driver's conversation context SHALL NOT contain the sub-agent's transcript content
- **AND** the driver SHALL update `state.last_handoff_id` to the returned id

#### Scenario: IMPLEMENT runs in worktree isolation
- **WHEN** the driver invokes `run_phase_subagent("IMPLEMENT", ...)`
- **THEN** the underlying `Agent(...)` call SHALL include `isolation="worktree"`
- **AND** the sub-agent's file mutations SHALL occur in the worktree, not the shared checkout

#### Scenario: IMPL_REVIEW and VALIDATE run in shared checkout
- **WHEN** the driver invokes `run_phase_subagent("IMPL_REVIEW", ...)` or `run_phase_subagent("VALIDATE", ...)`
- **THEN** the underlying `Agent(...)` call SHALL NOT include `isolation="worktree"`
- **AND** any artifacts produced (review-findings JSON, validation-report.md) SHALL be written to the shared checkout

### Requirement: Phase Sub-Agent Crash Recovery

When a Layer 2 phase sub-agent crashes (non-zero exit), times out, or returns malformed output, the driver SHALL retry the invocation with the same `(artifacts manifest, incoming PhaseRecord)` prompt up to 3 attempts (initial + 2 retries). Each retry SHALL be a fresh sub-agent (no transcript inheritance).

After the third failure, the driver SHALL write a `phase-failed` `PhaseRecord` containing the failing phase name and last-attempt error context, then raise `PhaseEscalationError(phase_name, attempts, last_error)` to the operator.

The retry contract SHALL document that phase sub-agents must be idempotent for irreversible side effects (e.g., `git push`, `gh pr merge`).

#### Scenario: First attempt succeeds, no retry
- **WHEN** a Layer 2 phase sub-agent returns a valid `(outcome, handoff_id)` on the first attempt
- **THEN** the driver SHALL accept the result without retrying
- **AND** the retry counter for the phase SHALL be 0

#### Scenario: Retry on malformed output
- **WHEN** a Layer 2 phase sub-agent returns output that does not parse as `(outcome, handoff_id)`
- **THEN** the driver SHALL retry up to 2 more times
- **AND** each retry SHALL receive the same incoming `PhaseRecord` and artifacts manifest
- **AND** if the third attempt also fails, the driver SHALL raise `PhaseEscalationError`

#### Scenario: Escalation writes phase-failed handoff
- **WHEN** all 3 retry attempts for a Layer 2 phase fail
- **THEN** the driver SHALL write a `PhaseRecord` with `summary` describing the failure and the last attempt's error
- **AND** the `phase_name` field SHALL be `<original-phase> (failed)`
- **AND** `PhaseEscalationError` SHALL be raised with `(phase_name, attempts=3, last_error=...)`

### Requirement: Context Window Token Instrumentation

Autopilot SHALL record token-count measurements at each phase boundary to support the success criterion of ≥30% peak-context-window reduction. A new module `skills/autopilot/scripts/phase_token_meter.py` SHALL expose `measure_context(messages: list[dict]) -> int`.

The meter SHALL use `anthropic.messages.count_tokens(...)` when the `anthropic` SDK is importable and the `ANTHROPIC_API_KEY` environment variable is set. Otherwise, it SHALL fall back to a transcript-length proxy: `sum(len(json.dumps(msg)) for msg in messages) // 4`.

The meter SHALL be no-op when the environment variable `AUTOPILOT_TOKEN_PROBE=disabled` is set, returning `-1` to indicate measurement was skipped.

At each `_HANDOFF_BOUNDARIES` transition, autopilot SHALL emit two coordinator audit-trail entries: `phase_token_pre` and `phase_token_post`, with `agent_id`, `change_id`, `phase_name`, `token_count`, and `meter_source` (one of `"anthropic_sdk"`, `"proxy"`, `"disabled"`).

#### Scenario: Meter uses SDK when available
- **WHEN** the `anthropic` SDK is importable and `ANTHROPIC_API_KEY` is set
- **AND** `measure_context(messages)` is called with a non-empty list
- **THEN** the meter SHALL call `anthropic.messages.count_tokens(...)` and return the result
- **AND** the audit entry SHALL have `meter_source="anthropic_sdk"`

#### Scenario: Meter falls back to proxy when SDK unavailable
- **WHEN** the `anthropic` SDK is not importable or `ANTHROPIC_API_KEY` is not set
- **AND** `measure_context(messages)` is called
- **THEN** the meter SHALL compute `sum(len(json.dumps(msg)) for msg in messages) // 4`
- **AND** the audit entry SHALL have `meter_source="proxy"`

#### Scenario: Meter is disabled when env flag set
- **WHEN** `AUTOPILOT_TOKEN_PROBE=disabled` is set in the environment
- **AND** `measure_context(messages)` is called
- **THEN** the meter SHALL return `-1` without invoking the SDK or computing the proxy
- **AND** the audit entry SHALL have `meter_source="disabled"`

### Requirement: PhaseRecord Markdown Round-Trip Preserves Decision Index Tags

The `PhaseRecord.render_markdown()` method SHALL preserve the inline backtick-delimited spans `` `architectural: <capability>` `` and `` `supersedes: <change-id>#D<n>` `` in their original format and position (between the decision title and the `—` rationale delimiter), so that the existing `make decisions` regenerator continues to parse them without modification.

The `parse_markdown()` (or equivalent) function SHALL extract these spans into `Decision.capability` and `Decision.supersedes` fields, with no other modifications to the surrounding content.

#### Scenario: Decision index regenerator output is unchanged
- **WHEN** `make decisions` is run before this change against a corpus of session-log entries
- **AND** the same corpus is rendered via `PhaseRecord.render_markdown()` after this change
- **AND** `make decisions` is run again
- **THEN** the regenerated `docs/decisions/<capability>.md` files SHALL be byte-identical (modulo timestamps in headers, if any)

#### Scenario: Capability tag survives round-trip
- **WHEN** a `PhaseRecord` containing a `Decision(capability="software-factory-tooling", ...)` is rendered to markdown
- **AND** the markdown is parsed back into a `PhaseRecord`
- **THEN** the resulting `Decision.capability` SHALL equal `"software-factory-tooling"`
- **AND** the inline span `` `architectural: software-factory-tooling` `` SHALL appear in the markdown text

#### Scenario: Supersedes tag survives round-trip
- **WHEN** a `PhaseRecord` containing a `Decision(supersedes="2026-01-15-old-change#D2", ...)` is rendered to markdown
- **AND** the markdown is parsed back
- **THEN** the resulting `Decision.supersedes` SHALL equal `"2026-01-15-old-change#D2"`
- **AND** the inline span `` `supersedes: 2026-01-15-old-change#D2` `` SHALL appear in the markdown text
