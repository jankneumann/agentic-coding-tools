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

The IMPLEMENT sub-agent (background Agent `a370a9b2c533fb7a7`) finished its work and committed `a22a250 chore(autopilot): record IMPLEMENT=complete, transition to CLEANUP`. This had two problems:

1. **Phase-transition surface violated.** Per the autopilot dispatch protocol in `skills/autopilot/SKILL.md`, the orchestrator is the only actor that transitions `current_phase`. The sub-agent's job is to return `(outcome, handoff_id)`. `apply-outcome` is described as updating "`last_handoff_id`, `handoff_ids`, `phase_archetype`" — not `current_phase`. The IMPLEMENT sub-agent wrote `current_phase = "CLEANUP"` directly, bypassing IMPL_ITERATE → IMPL_REVIEW → VALIDATE → SUBMIT_PR.

2. **Wrong target phase.** Per SKILL.md section 4, IMPLEMENT → IMPL_ITERATE (always runs, self-review). The sub-agent's target `CLEANUP` skipped FOUR phases and is not even a state in the autopilot state machine (`CLEANUP` is a *separate user-invoked skill*, `/cleanup-feature`).

The combined effect: when the operator resumed `/autopilot extract-gen-eval-package --force` after the IMPLEMENT phase, loop-state reported `current_phase = CLEANUP` which is not a recognized autopilot state. The operator had to manually correct loop-state back to `VALIDATE` before the next phase could dispatch.

### V2 — Causal model: four candidate pathways

We cannot determine from the audit trail alone which pathway produced the bad transition. Four are possible:

- **Layer A — `apply-outcome` implementation bug**: `runner.py apply-outcome` writes `current_phase` (e.g. via an internal `next_phase` lookup table) despite the SKILL.md contract saying it shouldn't.
- **Layer B — Sub-agent ran `apply-outcome` itself**: the dispatch prompt scaffold does not forbid sub-agents from invoking `runner.py` subcommands. A "helpful" sub-agent runs `apply-outcome` to "finish the bookkeeping," with whatever phase argument it chose. Combined with Layer A, this is sufficient to produce the observed bug.
- **Layer C — Sub-agent edited `loop-state.json` directly**: the dispatch prompt prohibits nothing in particular, and shell access lets the sub-agent `python3 -c '... json.dump(...)'` directly into `loop-state.json` without invoking `apply-outcome` at all. The commit subject matching `apply-outcome`'s format is circumstantial — a sub-agent willing to skip 4 phases is also willing to hand-craft the commit message.
- **Layer D — Orchestrator's own next-phase transition table is wrong**: the autopilot orchestrator, when resuming after a sub-agent returns `outcome=complete`, consults a next-phase table to decide what comes after IMPLEMENT. If that table maps `IMPLEMENT=complete → CLEANUP` (instead of the correct `IMPL_ITERATE`), the bug is in the orchestrator's state-machine config — neither `apply-outcome` nor the sub-agent are at fault. The commit subject reflects the *orchestrator's* decision, written after the sub-agent returned.

The four layers are not mutually exclusive; the audit in Task 1 covers all four and records its finding in a durable artifact (per D6). Design Decisions D1, D2-A, and D10 specify the per-layer fix and their relationship to the audit outcome.

### Out of Scope

- **The harness silent-no-op pattern** (Agent(isolation=worktree) using orchestrator's branch). Already documented in `memory/feedback_harness_worktree_silent_noop.md`. Distinct failure mode.
- **The phase-boundary `/compact` hook false positives.** Already filed as `fix-compact-hook-phase-boundary-detection`.
- **The `git commit -m` index-sweep foot-gun.** Already documented in `memory/feedback_git_commit_sweeps_pre_staged.md`.
- **Detection logic for the harness reporting `isolation_provided=true` while committing to the orchestrator branch.** Separate concern; mentioned in `docs/parallel-agentic-development.md` but not enforced.
- **Structural enforcement of the loop-state.json contract via filesystem permissions, pre-write git hooks, or syscall interception.** This was considered as a stronger alternative to Layer B+C prompt-based prohibitions. We're rejecting it for this change because: (a) the harness worktree's filesystem permissions are set by Claude Code's container runtime and are not under our control, (b) a git pre-commit hook scoped to "sub-agent identity" requires a reliable identity signal that doesn't exist (the harness presents the orchestrator's git identity), and (c) syscall interception is over-engineered for the observed failure surface. A follow-up change could revisit if Layer B+C prompt enforcement proves insufficient empirically. Until then, the prompt-based fix is the right scope.

## What Changes

### V1: re-map VALIDATE archetype to a write-capable role; codify capability as a structured field

- Add a structured `write_capable: bool` field to each archetype definition in `agent-coordinator/archetypes.yaml`. The runner's archetype resolver enforces this field directly — no substring matching over `system_prompt` text. This replaces the brittle "look for read-only marker substrings" approach (originally proposed; rejected per D3-revised after parallel-review-plan round 1 surfaced multiple findings on substring brittleness).
- In `agent-coordinator/archetypes.yaml`, the `phase_mapping` entries for `VALIDATE` and `VAL_FIX` MUST resolve to archetypes where `write_capable: true`.
- Introduce a new `validator` archetype with `write_capable: true` and a system prompt tailored to validation work (produces evidence artifacts and PhaseRecords). Do NOT include phrases like "do not modify source code" in the validator prompt — that is out-of-scope guidance that confuses the role definition (also surfaced by parallel-review-plan). Scope guidance belongs in task descriptions, not in the role's system prompt.
- VAL_FIX maps to `implementer` (also `write_capable: true`) because VAL_FIX is invoked to fix code-level validation failures, not to author validation artifacts.

### V2: enforce the apply-outcome contract; cover all four causal pathways

- **Layer A** — `runner.py apply-outcome` MUST NOT modify `current_phase`. The implementation must be audited (Task 1) and any `current_phase` write must be removed. Only the orchestrator transitions phases.
- **Layer A continued** — Add a phase-mismatch guard: if `--phase` ≠ `current_phase`, exit non-zero with an error message that mentions the `--allow-phase-mismatch` escape hatch (so operators can find it). The flag's narrow semantics are documented in D4-revised.
- **Layer B** — The dispatch prompt scaffold for every write-capable phase (PLAN, PLAN_ITERATE, PLAN_REVIEW, PLAN_FIX, IMPLEMENT, IMPL_ITERATE, IMPL_REVIEW, IMPL_FIX, VALIDATE, VAL_REVIEW, VAL_FIX) MUST instruct sub-agents that they return `(outcome, handoff_id)` only; they MUST NOT run `runner.py apply-outcome`.
- **Layer C** — The same dispatch prompt scaffolds MUST also forbid direct edits to `loop-state.json` (e.g. via `python3 -c`, `sed`, `jq`, or any other shell tool). Layer C closes the gap that Layer B's `apply-outcome`-only prohibition would leave open: a sub-agent willing to skip phases is also willing to bypass the subcommand.
- **Layer D** — Audit the autopilot orchestrator's own next-phase transition logic (Task 1.5). If a `phase_transitions` table or equivalent maps `IMPLEMENT=complete → CLEANUP` (or any non-state-machine target), the table itself is the bug. Fix the table to match the canonical state machine in `skills/autopilot/SKILL.md` sections 4-8.
- **apply-outcome failure handling**: when `apply-outcome` exits non-zero after a fix lands, the orchestrator MUST detect the failure, retain the un-applied handoff file, and transition to `ESCALATE`. A silent failure is worse than the bug this change fixes.

### Validation

- Unit tests for `apply-outcome` covering: (a) `--phase` equals `current_phase` succeeds and updates `last_handoff_id`/`handoff_ids`/`phase_archetype` only; (b) `--phase` mismatch errors out with a clear message that mentions `--allow-phase-mismatch`; (c) loop-state's `current_phase` is unchanged after any `apply-outcome` call regardless of `--allow-phase-mismatch`; (d) the orchestrator transitions to ESCALATE if `apply-outcome` exits non-zero.
- A coordinator-side test asserting `archetypes.yaml`'s `phase_mapping` entries for all write-capable phases resolve to archetypes with `write_capable: true`.
- A manual smoke pass: synthesize a VALIDATE dispatch via `runner.py build-dispatch --phase VALIDATE` and assert the rendered prompt includes the Layer B+C prohibitions and the validator system prompt doesn't contain self-contradicting "do not modify" framing.
- A regression test simulating Layer D: seed loop-state with `current_phase=IMPLEMENT, outcome=complete` and verify the orchestrator's next-phase decision is `IMPL_ITERATE`, not `CLEANUP`.
