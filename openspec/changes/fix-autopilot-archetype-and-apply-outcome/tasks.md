# Tasks — Fix autopilot archetype mapping and apply-outcome contract

## 1. Audit current implementation (determines V2 fix scope)

- [ ] 1.1 Read `agent-coordinator/archetypes.yaml` and record the current `phase_mapping.VALIDATE` and `phase_mapping.VAL_FIX` archetype names.
- [ ] 1.2 Read the resolved archetypes' `system_prompt` fields and confirm they contain read-only markers (per the V1 finding).
- [ ] 1.3 Read `skills/autopilot/scripts/runner.py` `apply-outcome` subcommand. Determine whether it writes `current_phase`. Record finding in commit message.
- [ ] 1.4 Read `skills/autopilot/scripts/phase_agent.py` (or wherever `apply_phase_outcome` lives) for the same audit.
- [ ] 1.5 Read the rendered prompt for `IMPLEMENT` and `VALIDATE` from `runner.py build-dispatch` and confirm the absence of state-mutation prohibitions.

## 2. V1 fix: introduce `validator` archetype, re-map VALIDATE/VAL_FIX

- [ ] 2.1 In `agent-coordinator/archetypes.yaml`, add a new archetype `validator` with the write-capable system prompt described in design D2. Tier: `standard`.
- [ ] 2.2 Decide VAL_FIX target. If the audit shows VAL_FIX is invoked when validation has *failed* (i.e. fixing source code), map it to `implementer`. If it's invoked to fix only the evidence artifacts (less common), map to `validator`. Default per design: `implementer`.
- [ ] 2.3 Update `phase_mapping.VALIDATE` to `validator` and `phase_mapping.VAL_FIX` to the chosen target.
- [ ] 2.4 Run `runner.py build-dispatch --phase VALIDATE --change-id <any-test-change>` and confirm the rendered `system_prompt` no longer contains read-only markers.

## 3. V2 fix Layer A: `apply-outcome` must not transition `current_phase`

- [ ] 3.1 If the audit (Task 1.3) found that `apply-outcome` writes `current_phase`, remove that write. Otherwise document in commit that Layer A was already clean.
- [ ] 3.2 Add a phase-mismatch guard: if `--phase` ≠ loop-state's `current_phase`, exit non-zero with a clear error message (per design D4).
- [ ] 3.3 Add `--force` flag to bypass the guard for operator-conscious recovery. `--force` does NOT enable `current_phase` modification — it only allows `last_handoff_id`/`handoff_ids`/`phase_archetype` updates for a non-current phase.
- [ ] 3.4 Update the `apply-outcome` CLI help text to document `--force` and the no-transition contract.

## 4. V2 fix Layer B: dispatch prompts forbid state mutation

- [ ] 4.1 In the prompt-scaffold helper (`build_phase_dispatch_kwargs` or equivalent), append to all write-capable phase prompts the line: `DO NOT run runner.py apply-outcome. DO NOT edit loop-state.json directly. Return (outcome, handoff_id) and exit; the orchestrator handles state.`
- [ ] 4.2 Confirm via `runner.py build-dispatch --phase <X>` that the new instruction appears in the rendered prompt for every write-capable phase: `PLAN_ITERATE`, `PLAN_REVIEW`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `VALIDATE`, `VAL_REVIEW`.
- [ ] 4.3 Do NOT add this line to read-only phase prompts (`INIT`, `SUBMIT_PR` state-only) — keep the scope tight.

## 5. CI check for archetype drift

- [ ] 5.1 Add a coordinator-side test (`agent-coordinator/tests/test_archetypes_yaml.py`) that loads `archetypes.yaml`, iterates the write-capable phases listed in design D7's compatibility matrix, and asserts each resolved archetype's `system_prompt` does NOT contain read-only markers.
- [ ] 5.2 Add the test to the agent-coordinator pytest run.
- [ ] 5.3 Verify the test passes locally before commit.

## 6. Unit tests for `apply-outcome`

- [ ] 6.1 Create `skills/tests/autopilot/test_apply_outcome_contract.py`.
- [ ] 6.2 Test: `apply-outcome --phase X` while `current_phase=X` succeeds, updates `last_handoff_id` only.
- [ ] 6.3 Test: `apply-outcome --phase X` while `current_phase=Y` (X≠Y) exits non-zero, leaves loop-state untouched.
- [ ] 6.4 Test: `apply-outcome --phase X --force` while `current_phase=Y` exits zero, updates `last_handoff_id`, leaves `current_phase=Y`.
- [ ] 6.5 Test: `apply-outcome` for any phase never modifies `current_phase` (parameterized over all write-capable phases).
- [ ] 6.6 Run `skills/.venv/bin/python -m pytest skills/tests/autopilot/test_apply_outcome_contract.py -v` — all tests pass.

## 7. Manual smoke

- [ ] 7.1 Create a temporary test change-id with a minimal `loop-state.json` (`current_phase = IMPLEMENT`).
- [ ] 7.2 Run `runner.py apply-outcome --change-id <test> --phase IMPLEMENT --outcome complete --handoff-id /tmp/fake.json`. Confirm exit zero, loop-state `current_phase` unchanged.
- [ ] 7.3 Run `runner.py apply-outcome --change-id <test> --phase VALIDATE --outcome failed --handoff-id /tmp/fake2.json` (mismatch). Confirm exit non-zero, loop-state unchanged.
- [ ] 7.4 Run with `--force` and confirm `last_handoff_id` updates but `current_phase` stays.
- [ ] 7.5 Run `runner.py build-dispatch --phase VALIDATE --change-id <test>`. Confirm rendered `system_prompt` no longer contains "without making changes".
- [ ] 7.6 Clean up the test change-id.

## 8. Sync runtime mirrors

- [ ] 8.1 Run `bash skills/install.sh --mode rsync --deps none --python-tools none` from the repo root to propagate the runner.py and prompt-scaffold changes to `.claude/skills/` and `.agents/skills/`.
- [ ] 8.2 Verify `diff` shows the runtime copies are byte-identical to the canonical source.

## 9. Validate and commit

- [ ] 9.1 Run `openspec validate fix-autopilot-archetype-and-apply-outcome --strict`. Must pass.
- [ ] 9.2 Confirm the change has the expected requirements under `skill-workflow` capability.
- [ ] 9.3 Commit on `openspec/fix-autopilot-archetype-and-apply-outcome` with subject `fix(autopilot): introduce validator archetype + apply-outcome no-transition guard`.
- [ ] 9.4 Push to origin.

## 10. Post-merge follow-up

- [ ] 10.1 (Out of scope for the change; done after merge:) update `docs/parallel-agentic-development.md` with the new dispatch-prompt prohibitions if they prove to be a recurring debugging touchstone.
- [ ] 10.2 (Out of scope:) consider whether harness-silent-no-op detection (separate failure mode noted in proposal "Out of Scope") wants its own change.
