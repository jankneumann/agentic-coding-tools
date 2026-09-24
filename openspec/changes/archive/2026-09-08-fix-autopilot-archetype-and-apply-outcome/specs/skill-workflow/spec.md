## ADDED Requirements

### Requirement: Archetypes Declare Write-Capability via a Structured Field

Every archetype entry in `agent-coordinator/archetypes.yaml` SHALL include a boolean `write_capable` field. The runner's archetype resolver SHALL enforce that all `phase_mapping` entries for write-capable phases resolve to an archetype with `write_capable: true`.

Write-capable phases are: `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`. State-only phases (`INIT`, `SUBMIT_PR`) MAY map to archetypes with `write_capable: false`.

The capability check SHALL be enforced via the structured field. It SHALL NOT rely on substring matching over the archetype's `system_prompt` text — that approach was considered and rejected (per Design D3) because it is brittle to rephrasing and silently fails on synonymous wording.

#### Scenario: VALIDATE archetype is write-capable via structured field

- **WHEN** the runner resolves the archetype for phase `VALIDATE` via `archetypes.yaml` `phase_mapping.VALIDATE`
- **THEN** the resolved archetype's `write_capable` field SHALL be `true`
- **AND** the rendered dispatch prompt (from `runner.py build-dispatch --phase VALIDATE`) SHALL include a `write_capable: true` indicator in its archetype metadata

#### Scenario: VAL_FIX archetype is write-capable via structured field

- **WHEN** the runner resolves the archetype for phase `VAL_FIX` via `archetypes.yaml` `phase_mapping.VAL_FIX`
- **THEN** the resolved archetype's `write_capable` field SHALL be `true`
- **AND** the resolved archetype SHALL be `implementer` (per design D2 — VAL_FIX fixes code, not artifacts)

#### Scenario: CI guard enforces write_capable for all write-capable phases

- **WHEN** a CI check inspects `archetypes.yaml` `phase_mapping` entries
- **AND** iterates the canonical write-capable phase list (per the requirement above)
- **THEN** every resolved archetype's `write_capable` field SHALL be `true`
- **AND** any phase whose resolved archetype has `write_capable: false` or omits the field SHALL cause the check to fail with a clear message identifying the offending phase and archetype

#### Scenario: validator archetype system prompt is free of role-confusion phrasing

- **WHEN** the validator archetype is defined in `archetypes.yaml`
- **THEN** its `system_prompt` SHALL NOT contain the substrings "do not modify source code", "without making changes", "without modifying", "only synthesize"
- **AND** this check serves as a secondary defense-in-depth guard against the role's own framing drifting toward read-only; the primary capability gate remains the structured `write_capable` field

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

#### Scenario: apply-outcome rejects phase mismatch with mention of `--allow-phase-mismatch`

- **WHEN** loop-state has `current_phase = "IMPLEMENT"`
- **AND** the operator invokes `runner.py apply-outcome --change-id <id> --phase PLAN_REVIEW --outcome converged --handoff-id <path>` (mismatched `--phase`)
- **THEN** the command SHALL exit with a non-zero status
- **AND** SHALL emit a clear error message identifying the mismatch (expected `IMPLEMENT`, got `PLAN_REVIEW`)
- **AND** the error message SHALL explicitly mention the `--allow-phase-mismatch` flag as the escape hatch
- **AND** `loop-state.json` SHALL remain unchanged

#### Scenario: `--allow-phase-mismatch` bypasses the guard but does not modify current_phase

- **WHEN** loop-state has `current_phase = "IMPLEMENT"`
- **AND** the operator invokes `runner.py apply-outcome --change-id <id> --phase PLAN_REVIEW --outcome converged --handoff-id <path> --allow-phase-mismatch`
- **THEN** the command SHALL succeed
- **AND** SHALL update `last_handoff_id`/`handoff_ids`/`phase_archetype` for the `PLAN_REVIEW` outcome
- **AND** SHALL NOT modify `current_phase` (the flag bypasses the guard, not the no-transition contract — per design D4)

#### Scenario: apply-outcome failure transitions orchestrator to ESCALATE

- **WHEN** the orchestrator invokes `runner.py apply-outcome` and the command exits non-zero (disk full, lock contention, malformed loop-state, transient FS error)
- **THEN** the orchestrator SHALL detect the non-zero exit code
- **AND** SHALL retain the un-applied handoff file at its existing path under `openspec/changes/<id>/handoffs/`
- **AND** SHALL append a `phase_history` entry recording the apply-outcome failure
- **AND** SHALL transition `current_phase` to `ESCALATE` with `previous_phase` set to the failing phase
- **AND** the failure SHALL surface to the operator so the underlying cause can be addressed before resume

### Requirement: Sub-Agent Dispatch Prompts Forbid State Mutation by Two Paths

The per-phase dispatch prompts rendered by `runner.py build-dispatch` for write-capable phases SHALL include two explicit prohibitions:

1. **Subcommand prohibition (Layer B)**: the sub-agent MUST NOT run `runner.py apply-outcome` (or any other `runner.py` subcommand that modifies orchestrator state).
2. **Direct-edit prohibition (Layer C)**: the sub-agent MUST NOT edit `openspec/changes/<id>/loop-state.json` by any means (`python3 -c`, `sed`, `jq`, or any other shell tool).

The sub-agent's contract is to return `(outcome, handoff_id)` only; the orchestrator handles all state transitions.

The prohibitions SHALL appear in the dispatch prompt for every write-capable phase: `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`.

#### Scenario: IMPLEMENT phase prompt includes Layer B + Layer C prohibitions

- **WHEN** `runner.py build-dispatch --phase IMPLEMENT --change-id <id>` is invoked
- **THEN** the rendered `prompt` field SHALL contain an explicit instruction forbidding the sub-agent from running `runner.py apply-outcome`
- **AND** SHALL contain an explicit instruction forbidding direct edits to `openspec/changes/<id>/loop-state.json` via any shell tool
- **AND** SHALL clarify that the sub-agent returns `(outcome, handoff_id)` and the orchestrator handles state transitions

#### Scenario: All write-capable phase prompts include the prohibitions

- **WHEN** `runner.py build-dispatch` is invoked for any of: `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`
- **THEN** the rendered prompt SHALL contain both Layer B (subcommand) and Layer C (direct-edit) prohibitions

#### Scenario: Read-only phase prompts do not include the prohibitions

- **WHEN** `runner.py build-dispatch` is invoked for `INIT` or `SUBMIT_PR`
- **THEN** the rendered prompt MAY or MAY NOT contain the prohibitions (they are state-only phases that don't need them; adding them is harmless but not required)

### Requirement: Orchestrator's Next-Phase Decision Matches the Canonical State Machine

The autopilot orchestrator's next-phase decision logic (whether a `phase_transitions` table, hardcoded dict, branched control flow, or any equivalent) SHALL produce a next-phase that matches the canonical state machine documented in `skills/autopilot/SKILL.md` sections 4-8.

The decision logic SHALL be implemented as a single auditable structure (table, dict, or equivalent), not distributed across multiple control-flow branches that would require manual reconstruction to audit.

#### Scenario: IMPLEMENT=complete transitions to IMPL_ITERATE

- **WHEN** loop-state has `current_phase = "IMPLEMENT"` and the most recent `phase_history` entry has `outcome = "complete"` for IMPLEMENT
- **AND** the orchestrator computes the next phase
- **THEN** the orchestrator's next-phase decision SHALL be `IMPL_ITERATE`
- **AND** the decision SHALL NOT be `CLEANUP` (CLEANUP is not a state in the autopilot state machine; it is a separate user-invoked skill)

#### Scenario: IMPL_ITERATE=complete transitions per cli_review_enabled

- **WHEN** loop-state has `current_phase = "IMPL_ITERATE"` and the most recent `phase_history` entry has `outcome = "complete"`
- **AND** `cli_review_enabled = true` in loop-state
- **THEN** the orchestrator's next-phase decision SHALL be `IMPL_REVIEW`
- **AND** if `cli_review_enabled = false`, the next-phase decision SHALL be `VALIDATE`

#### Scenario: Next-phase decision logic is centralized

- **WHEN** the orchestrator's next-phase decision is invoked
- **THEN** the underlying implementation SHALL be a single auditable structure (e.g. a YAML `phase_transitions` table, a Python dict)
- **AND** SHALL NOT be distributed across multiple control-flow branches that require manual reconstruction to audit
