## ADDED Requirements

### Requirement: VALIDATE-phase Archetype Must Be Write-Capable

The autopilot `phase_mapping` for `VALIDATE` and `VAL_FIX` SHALL resolve to a write-capable archetype whose system prompt does NOT instruct the agent to behave as read-only.

A write-capable archetype's system prompt SHALL explicitly authorize producing evidence artifacts (validation reports, PhaseRecord handoffs) and SHALL NOT contain phrases that contradict the phase task body, such as "without making changes", "do not modify", "report findings only", or equivalent.

#### Scenario: Resolved VALIDATE archetype is write-capable

- **WHEN** the runner resolves the archetype for phase `VALIDATE` via `archetypes.yaml` `phase_mapping.VALIDATE`
- **THEN** the resolved archetype's `system_prompt` SHALL NOT contain the substrings `"without making changes"`, `"do not modify"`, `"without modifying"`, or `"only synthesize"`
- **AND** the rendered dispatch prompt (from `runner.py build-dispatch --phase VALIDATE`) SHALL similarly be free of those substrings

#### Scenario: Resolved VAL_FIX archetype is write-capable

- **WHEN** the runner resolves the archetype for phase `VAL_FIX` via `archetypes.yaml` `phase_mapping.VAL_FIX`
- **THEN** the resolved archetype's `system_prompt` SHALL NOT contain read-only markers (as defined above)
- **AND** the resolved archetype's system prompt SHALL be appropriate to the VAL_FIX task body (apply fixes to address validation failures)

#### Scenario: Phase mapping CI guard for read-only marker drift

- **WHEN** a CI check inspects `archetypes.yaml` `phase_mapping` entries
- **AND** any of the write-capable phases (`PLAN`, `PLAN_ITERATE`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_FIX`, `VALIDATE`, `VAL_FIX`, `VAL_REVIEW`, `PLAN_REVIEW`, `IMPL_REVIEW`) is mapped to an archetype whose `system_prompt` contains a read-only marker
- **THEN** the CI check SHALL fail with a clear message identifying the offending phase and archetype

### Requirement: `apply-outcome` Does Not Transition `current_phase`

The `runner.py apply-outcome` subcommand SHALL NOT modify `loop-state.json` `current_phase`. The orchestrator is the sole writer of `current_phase`.

`apply-outcome` SHALL update only the fields it owns: `last_handoff_id`, `handoff_ids` (append), `phase_archetype`, and an entry in `phase_history` recording the outcome.

#### Scenario: apply-outcome preserves current_phase

- **WHEN** loop-state has `current_phase = "IMPLEMENT"`
- **AND** the operator invokes `runner.py apply-outcome --change-id <id> --phase IMPLEMENT --outcome complete --handoff-id <path>`
- **THEN** after the call, `current_phase` SHALL still equal `"IMPLEMENT"`
- **AND** `last_handoff_id` SHALL equal `<path>`
- **AND** `handoff_ids` SHALL contain `<path>`
- **AND** `phase_history` SHALL contain a new entry with `phase: "IMPLEMENT"`, `outcome: "complete"`

#### Scenario: apply-outcome rejects phase mismatch

- **WHEN** loop-state has `current_phase = "IMPLEMENT"`
- **AND** the operator invokes `runner.py apply-outcome --change-id <id> --phase PLAN_REVIEW --outcome converged --handoff-id <path>` (mismatched `--phase`)
- **THEN** the command SHALL exit with a non-zero status
- **AND** SHALL emit a clear error message identifying the mismatch (expected `IMPLEMENT`, got `PLAN_REVIEW`)
- **AND** `loop-state.json` SHALL remain unchanged

#### Scenario: apply-outcome `--force` bypasses phase-mismatch guard

- **WHEN** loop-state has `current_phase = "IMPLEMENT"`
- **AND** the operator invokes `runner.py apply-outcome --change-id <id> --phase PLAN_REVIEW --outcome converged --handoff-id <path> --force`
- **THEN** the command SHALL succeed
- **AND** SHALL update `last_handoff_id`/`handoff_ids`/`phase_archetype` for the `PLAN_REVIEW` outcome
- **AND** SHALL still NOT modify `current_phase` (force bypasses the guard, not the contract)

### Requirement: Sub-Agent Dispatch Prompts Forbid Direct State Mutation

The per-phase dispatch prompts rendered by `runner.py build-dispatch` for write-capable phases SHALL include explicit instructions that the sub-agent must NOT run `apply-outcome` and must NOT edit `loop-state.json` directly. The sub-agent's contract is to return `(outcome, handoff_id)` only; the orchestrator handles all state transitions.

#### Scenario: IMPLEMENT phase prompt forbids state mutation

- **WHEN** `runner.py build-dispatch --phase IMPLEMENT --change-id <id>` is invoked
- **THEN** the rendered `prompt` field SHALL contain explicit instructions forbidding the sub-agent from running `apply-outcome`
- **AND** SHALL contain explicit instructions forbidding direct edits to `loop-state.json`
- **AND** SHALL clarify that the sub-agent returns `(outcome, handoff_id)` and the orchestrator handles state

#### Scenario: VALIDATE phase prompt forbids state mutation

- **WHEN** `runner.py build-dispatch --phase VALIDATE --change-id <id>` is invoked
- **THEN** the rendered `prompt` field SHALL contain the same state-mutation prohibitions as the IMPLEMENT phase

#### Scenario: All write-capable phases enforce the prohibition

- **WHEN** `runner.py build-dispatch` is invoked for any of `PLAN_ITERATE`, `PLAN_REVIEW`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `VALIDATE`, `VAL_REVIEW`
- **THEN** the rendered prompt SHALL contain the state-mutation prohibitions
