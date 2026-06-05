# Fix autopilot archetype mapping and apply-outcome contract

## Why

Two distinct autopilot contract violations surfaced during the `/autopilot extract-gen-eval-package --force` run (2026-05-30 → 2026-06-01). Both are isolated, both are reproducible, both block the autopilot loop from completing cleanly without operator intervention.

### V1 — VALIDATE phase maps to read-only `analyst` archetype

The runner-resolved archetype for the VALIDATE phase is `analyst`. The `analyst` system prompt explicitly declares the role read-only:

> "You are a codebase analyst. Read thoroughly, synthesize findings concisely, and identify patterns, gaps, and conflicts. **Report structured findings without making changes.**"

But the VALIDATE phase task body says:

> "Run validation phases (spec, evidence, deploy, smoke, security, e2e) per validate-feature. **Aggregate results into a PhaseRecord.** Return outcome 'passed' on PASS, 'failed' on FAIL."

`/validate-feature` writes evidence artifacts (spec/evidence/deploy/smoke/security/e2e reports), and the PhaseRecord itself is a written handoff JSON. A sub-agent loaded with the `analyst` system prompt cannot perform the task because the instructions contradict each other. Empirically, the 2026-06-02 run produced a stream-watchdog stall at 600s with the sub-agent's final message: *"I'm a codebase analyst and cannot make changes."*

### V2 — IMPLEMENT sub-agent transitioned `current_phase` via `apply-outcome`

The IMPLEMENT sub-agent (background Agent `a370a9b2c533fb7a7`) finished its work and ran `runner.py apply-outcome` itself, producing commit `a22a250 chore(autopilot): record IMPLEMENT=complete, transition to CLEANUP`. This had two problems:

1. **Phase-transition surface violated.** Per the autopilot dispatch protocol in `skills/autopilot/SKILL.md`, the orchestrator is the only actor that transitions `current_phase`. The sub-agent's job is to return `(outcome, handoff_id)`. `apply-outcome` is described as updating "`last_handoff_id`, `handoff_ids`, `phase_archetype`" — not `current_phase`. The IMPLEMENT sub-agent wrote `current_phase = "CLEANUP"` directly, bypassing IMPL_ITERATE → IMPL_REVIEW → VALIDATE → SUBMIT_PR.

2. **Wrong target phase.** Per SKILL.md section 4, IMPLEMENT → IMPL_ITERATE (always runs, self-review). The sub-agent's target `CLEANUP` skipped FOUR phases and is not even a state in the autopilot state machine (`CLEANUP` is a *separate user-invoked skill*, `/cleanup-feature`).

The combined effect: when the operator resumed `/autopilot extract-gen-eval-package --force` after the IMPLEMENT phase, loop-state reported `current_phase = CLEANUP` which is not a recognized autopilot state. The operator had to manually correct loop-state back to `VALIDATE` before the next phase could dispatch.

Either the sub-agent has agency to run arbitrary `runner.py` subcommands (and our archetype prompts don't constrain that), OR `apply-outcome` itself was implemented to transition `current_phase` despite the SKILL.md contract. The fix differs depending on which — see Design D1.

### Out of Scope

- The harness silent-no-op pattern (Agent(isolation=worktree) using orchestrator's branch). Already documented in `memory/feedback_harness_worktree_silent_noop.md`. Distinct failure mode.
- The phase-boundary `/compact` hook false positives. Already filed as `fix-compact-hook-phase-boundary-detection`.
- The `git commit -m` index-sweep foot-gun. Already documented in `memory/feedback_git_commit_sweeps_pre_staged.md`.
- Detection logic for the harness reporting `isolation_provided=true` while committing to the orchestrator branch. Separate concern; mentioned in `docs/parallel-agentic-development.md` but not enforced.

## What Changes

### V1: re-map VALIDATE archetype to a write-capable role

- In `agent-coordinator/archetypes.yaml`, the `phase_mapping` entry for `VALIDATE` (and `VAL_FIX`) MUST resolve to a write-capable archetype.
- Two options (D2 picks one): (a) keep the existing `runner` archetype (already used for `INIT`/`SUBMIT_PR`), or (b) introduce a new `validator` archetype with a write-capable system prompt tailored to validation work. The recommendation is (b): the `runner` system prompt is too thin for the multi-phase validation task, but introducing a `validator` archetype keeps the mapping table semantically clean.
- The new `validator` archetype's system prompt must explicitly state that it produces evidence artifacts (PhaseRecords, validation reports), not just findings.

### V2: enforce the apply-outcome contract

- `runner.py apply-outcome` MUST NOT modify `current_phase`. The implementation must be audited and any `current_phase` write must be removed. Only the orchestrator transitions phases.
- The `apply-outcome` subcommand's `--phase` argument is currently used to identify which phase's outcome is being recorded. It must stay; what changes is that `--phase` MUST equal the loop-state's existing `current_phase` (a guard rail — apply-outcome for a non-current phase is a programming error and should error out).
- Sub-agents MUST be instructed (in their dispatch prompt scaffold) that they return `(outcome, handoff_id)` only; they do not run `apply-outcome` themselves. The orchestrator runs it. This constraint goes in the IMPLEMENT (and other write-capable phase) task body, not just SKILL.md prose — the prompt scaffold is what the sub-agent actually reads.

### Validation

- Unit tests for `apply-outcome` covering: (a) `--phase` equals `current_phase` succeeds and updates `last_handoff_id`/`handoff_ids`/`phase_archetype` only; (b) `--phase` mismatch errors out with a clear message; (c) loop-state's `current_phase` is unchanged after apply-outcome.
- A coordinator-side test asserting `archetypes.yaml` resolves VALIDATE to a write-capable archetype.
- A manual smoke pass: synthesize a VALIDATE dispatch via `runner.py build-dispatch --phase VALIDATE` and assert the rendered `system_prompt` does not contain "without making changes" or equivalent read-only language.
