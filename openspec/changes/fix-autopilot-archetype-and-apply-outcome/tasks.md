# Tasks — Fix autopilot archetype mapping and apply-outcome contract

## 1. Audit current implementation (determines V2 fix scope across all 4 layers)

- [ ] 1.1 Read `agent-coordinator/archetypes.yaml` and record the current `phase_mapping.VALIDATE` and `phase_mapping.VAL_FIX` archetype names.
- [ ] 1.2 Read the resolved archetypes' `system_prompt` fields. Record whether they would currently fail the V1 check (writing-task assigned to read-only-prompted archetype).
- [ ] 1.3 **Layer A audit**: Read `skills/autopilot/scripts/runner.py` `apply-outcome` subcommand. Determine whether it writes `current_phase`. Determine whether it appends `phase_history`. Determine whether the `--phase` argument is currently validated against loop-state `current_phase`.
- [ ] 1.4 **Layer A audit (continued)**: Read `skills/autopilot/scripts/phase_agent.py` (or wherever `apply_phase_outcome` lives) for the same audit. Look for any code path that mutates `current_phase` outside the orchestrator's run-loop.
- [ ] 1.5 **Layer D audit**: Read `skills/autopilot/scripts/runner.py` `run-loop` (or equivalent orchestrator entry point). Identify how it computes the next phase after a sub-agent returns. Specifically check: (a) is there a `phase_transitions` table (YAML/dict)? (b) if so, what does it produce for `(IMPLEMENT, complete)`? (c) if no table, is the logic distributed across `if/elif` branches that need manual reconstruction? Record findings.
- [ ] 1.6 **Layer B/C audit**: Read the rendered prompt for `IMPLEMENT` and `VALIDATE` from `runner.py build-dispatch`. Confirm the absence of state-mutation prohibitions today.
- [ ] 1.7 **Write `openspec/changes/fix-autopilot-archetype-and-apply-outcome/audit-result.md`** with per-layer findings (Layer A status, Layer B/C current prompt content, Layer D logic location and current mapping). Each layer entry includes the empirical finding, the fix decision (required vs. no-op), and a link to the task(s) that act on it. This file is referenced from design.md and proposal.md as the authoritative record of audit outcomes.

## 2. V1 fix: introduce `write_capable` field, `validator` archetype, re-map VALIDATE/VAL_FIX

- [ ] 2.1 Add a `write_capable: bool` field to every archetype entry in `agent-coordinator/archetypes.yaml`. Each existing archetype gets an explicit value based on its current role (analyst→false; runner→false-by-default-or-true-per-audit; implementer→true; architect→true; reviewer→true).
- [ ] 2.2 Add a new archetype `validator` with `write_capable: true` and the write-capable system prompt described in design D2. Do NOT include "you do NOT modify source code being validated" or similar self-contradicting phrases. Tier: `standard`.
- [ ] 2.3 Decide VAL_FIX target per design D2 (default: `implementer`, since VAL_FIX fixes code). Update `phase_mapping.VAL_FIX` accordingly.
- [ ] 2.4 Update `phase_mapping.VALIDATE` to `validator`.
- [ ] 2.5 Update the runner's archetype resolver (`runner.py build-dispatch` or wherever archetype is read) to enforce `write_capable: true` for write-capable phases at resolution time, not just at build-time CI. If the resolution finds a `phase_mapping` entry whose target archetype has `write_capable: false`, fail fast with a clear error.
- [ ] 2.6 Run `runner.py build-dispatch --phase VALIDATE --change-id <any-test-change>` and confirm the rendered metadata reports `archetype: validator` with `write_capable: true`. The system_prompt no longer contains read-only markers.
- [ ] 2.7 Update the JSON schema at `openspec/schemas/archetypes.schema.json` (if present) to require the `write_capable` field on every archetype.

## 3. V2 Layer A fix: `apply-outcome` must not transition `current_phase`

- [ ] 3.1 If the audit (Task 1.3/1.4 outcome recorded in audit-result.md) found that `apply-outcome` writes `current_phase`, remove that write. Otherwise document in commit that Layer A was already clean and 3.1 was a no-op.
- [ ] 3.2 Add a phase-mismatch guard: if `--phase` ≠ loop-state's `current_phase`, exit non-zero with a clear error message.
- [ ] 3.3 The error message MUST explicitly mention `--allow-phase-mismatch` as the escape hatch (so operators can find it without reading the help text).
- [ ] 3.4 Add `--allow-phase-mismatch` flag to bypass the guard for operator-conscious recovery. `--allow-phase-mismatch` does NOT enable `current_phase` modification — it only allows `last_handoff_id`/`handoff_ids`/`phase_archetype` updates for a non-current phase.
- [ ] 3.5 Update the `apply-outcome` CLI help text to document `--allow-phase-mismatch` and the no-transition contract.
- [ ] 3.6 Codify the `phase_history` append behavior in the implementation (which the audit may have already confirmed) so downstream consumers can rely on it.

## 4. V2 Layer B + C fix: dispatch prompts forbid state mutation via TWO paths

- [ ] 4.1 In the prompt-scaffold helper (`build_phase_dispatch_kwargs` or equivalent), append to all write-capable phase prompts BOTH lines:
  - Layer B: `DO NOT run runner.py apply-outcome or any other runner.py subcommand that modifies orchestrator state.`
  - Layer C: `DO NOT edit openspec/changes/<id>/loop-state.json by any means (python3 -c, sed, jq, or any other shell tool). The orchestrator owns this file.`
- [ ] 4.2 Confirm via `runner.py build-dispatch --phase <X>` that BOTH instructions appear in the rendered prompt for every write-capable phase: `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`.
- [ ] 4.3 Read-only phases (`INIT`, `SUBMIT_PR`) — leave their prompts unchanged. The prohibition is not required (they don't need it) but may be added if helpful for consistency.

## 5. V2 Layer D fix: orchestrator next-phase decision is centralized and correct

- [ ] 5.1 Based on the Task 1.5 audit, decide between (a) the orchestrator already uses a single `phase_transitions` table → only fix wrong mappings, or (b) the logic is distributed → extract into a single table per design D10.
- [ ] 5.2 If (b): extract the next-phase logic into a `phase_transitions` table (YAML, JSON, or Python dict) covering every `(current_phase, outcome)` pair. Match the canonical state machine in `skills/autopilot/SKILL.md` sections 4-8.
- [ ] 5.3 Audit the table for the `(IMPLEMENT, complete)` mapping. The result MUST be `IMPL_ITERATE`. Fix if wrong.
- [ ] 5.4 Audit every other `(phase, outcome)` mapping against SKILL.md. Fix anything that doesn't match. Examples to verify: `(IMPL_ITERATE, complete) → IMPL_REVIEW if cli_review_enabled else VALIDATE`, `(VALIDATE, passed) → VAL_REVIEW if val_review_enabled else SUBMIT_PR`, `(SUBMIT_PR, complete) → DONE`.
- [ ] 5.5 Add an `apply-outcome-failure` transition: when the orchestrator detects a non-zero exit from `apply-outcome`, the next phase is `ESCALATE` per design D9.

## 6. CI checks and regression tests

- [ ] 6.1 Add a coordinator-side test (`agent-coordinator/tests/test_archetypes_yaml.py`) that loads `archetypes.yaml`, iterates the write-capable phases listed in design D7's compatibility matrix, and asserts each resolved archetype has `write_capable: true`. No substring matching.
- [ ] 6.2 Add a test asserting every archetype in `archetypes.yaml` declares `write_capable` (no missing field).
- [ ] 6.3 Add a defense-in-depth secondary test: the validator archetype's `system_prompt` does NOT contain "do not modify source code", "without making changes", or equivalent read-only-marker phrases.
- [ ] 6.4 Add the tests to the agent-coordinator pytest run.
- [ ] 6.5 Add a test that the orchestrator's `phase_transitions` table (if centralized per 5.2) maps `(IMPLEMENT, complete) → IMPL_ITERATE`.
- [ ] 6.6 Add a Layer D regression test in `skills/tests/autopilot/test_phase_transitions.py`: seed a synthetic `loop-state.json` with `current_phase=IMPLEMENT` and `phase_history` ending in `outcome=complete`; invoke the orchestrator's next-phase decision; assert result is `IMPL_ITERATE`.
- [ ] 6.7 Verify all tests pass locally before commit.

## 7. Unit tests for `apply-outcome` contract

- [ ] 7.1 Create `skills/tests/autopilot/test_apply_outcome_contract.py`.
- [ ] 7.2 Test: `apply-outcome --phase X` while `current_phase=X` succeeds, updates `last_handoff_id` only (NOT `current_phase`).
- [ ] 7.3 Test: `apply-outcome --phase X` while `current_phase=Y` (X≠Y) exits non-zero, error message mentions `--allow-phase-mismatch`, loop-state untouched.
- [ ] 7.4 Test: `apply-outcome --phase X --allow-phase-mismatch` while `current_phase=Y` exits zero, updates `last_handoff_id`, leaves `current_phase=Y`.
- [ ] 7.5 Test: `apply-outcome` for any phase never modifies `current_phase` (parameterized over all write-capable phases, with and without `--allow-phase-mismatch`).
- [ ] 7.6 Test (D9): when `apply-outcome` is invoked from a fixture that simulates a non-zero exit (e.g. via monkeypatched subprocess), the orchestrator's wrapper SHALL transition `current_phase` to `ESCALATE` and retain the un-applied handoff file.
- [ ] 7.7 Run `skills/.venv/bin/python -m pytest skills/tests/autopilot/test_apply_outcome_contract.py -v` — all tests pass.

## 8. Manual smoke

- [ ] 8.1 Create a temporary test change-id with a minimal `loop-state.json` (`current_phase = IMPLEMENT`).
- [ ] 8.2 Run `runner.py apply-outcome --change-id <test> --phase IMPLEMENT --outcome complete --handoff-id /tmp/fake.json`. Confirm exit zero, loop-state `current_phase` unchanged.
- [ ] 8.3 Run `runner.py apply-outcome --change-id <test> --phase VALIDATE --outcome failed --handoff-id /tmp/fake2.json` (mismatch). Confirm exit non-zero, error message mentions `--allow-phase-mismatch`, loop-state unchanged.
- [ ] 8.4 Run with `--allow-phase-mismatch` and confirm `last_handoff_id` updates but `current_phase` stays.
- [ ] 8.5 Run `runner.py build-dispatch --phase VALIDATE --change-id <test>`. Confirm rendered metadata shows `archetype: validator` with `write_capable: true`. Confirm rendered prompt contains BOTH Layer B ("DO NOT run runner.py apply-outcome") and Layer C ("DO NOT edit openspec/changes/<id>/loop-state.json") prohibitions.
- [ ] 8.6 Repeat 8.5 for `--phase IMPLEMENT`, `--phase PLAN`, `--phase PLAN_FIX`, `--phase IMPL_FIX`, `--phase VAL_FIX` to confirm prohibition coverage for ALL write-capable phases.
- [ ] 8.7 Smoke test D9: simulate `apply-outcome` failure by passing a corrupted `loop-state.json`; verify orchestrator detects, retains handoff, transitions to ESCALATE.
- [ ] 8.8 Clean up the test change-id.

## 9. Sync runtime mirrors

- [ ] 9.1 Run `bash skills/install.sh --mode rsync --deps none --python-tools none` from the repo root to propagate the runner.py, prompt-scaffold, and archetypes.yaml changes to `.claude/skills/`, `.agents/skills/`, and the agent-coordinator runtime.
- [ ] 9.2 Verify `diff` shows the runtime copies are byte-identical to the canonical source.

## 10. Validate and commit

- [ ] 10.1 Run `openspec validate fix-autopilot-archetype-and-apply-outcome --strict`. Must pass.
- [ ] 10.2 Confirm the change has the expected requirements under `skill-workflow` capability.
- [ ] 10.3 Commit on `openspec/fix-autopilot-archetype-and-apply-outcome` with subject `fix(autopilot): introduce validator archetype + write_capable field + apply-outcome no-transition guard + Layer C/D coverage`.
- [ ] 10.4 Push to origin.

## 11. Post-merge follow-up

- [ ] 11.1 (Out of scope for the change; done after merge:) update `docs/parallel-agentic-development.md` with the new dispatch-prompt prohibitions and the `write_capable` archetype field convention.
- [ ] 11.2 (Out of scope:) consider whether structural enforcement of the loop-state.json contract (filesystem permissions, git hooks) wants its own follow-up change if Layer B+C prompt enforcement proves insufficient empirically.
- [ ] 11.3 (Out of scope:) consider whether harness-silent-no-op detection (separate failure mode noted in proposal "Out of Scope") wants its own change.
