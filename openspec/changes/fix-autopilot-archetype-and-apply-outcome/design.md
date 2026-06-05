# Design — Fix autopilot archetype mapping and apply-outcome contract

## D1. Where does the V2 fix live: `apply-outcome` impl, or sub-agent prompt scaffold?

Two layers can have caused V2:

### Layer A: `runner.py apply-outcome` itself transitions `current_phase`

If the implementation of `apply-outcome` writes `current_phase` (e.g. always sets it based on a per-phase transition table), then sub-agents calling `apply-outcome` will trip this automatically — even if their prompt told them not to.

**Fix:** remove the `current_phase` write from `apply-outcome`. Add a guard that errors if `--phase` ≠ existing `current_phase`. This makes the subcommand idempotent w.r.t. phase state and makes the orchestrator the sole `current_phase` author.

### Layer B: `apply-outcome` is innocent; the sub-agent ran it AND additionally wrote `current_phase`

The sub-agent has shell access and can `python -c` or sed-edit `loop-state.json` directly. If the prompt scaffold doesn't forbid it, a "helpful" sub-agent may take initiative and "finish the bookkeeping."

**Fix:** add an explicit guard in the write-capable phase prompt scaffolds: "DO NOT run `apply-outcome`. DO NOT edit `loop-state.json`. The orchestrator handles state transitions. Return `(outcome, handoff_id)` and exit."

### Selected approach: fix BOTH layers

The two layers are complementary, not alternative:

- Layer A protects against innocent invocations of `apply-outcome` by future tooling.
- Layer B protects against the more general class of sub-agent overreach (which `a370a9b2c533fb7a7` clearly demonstrated — it also ran `gh pr create`-adjacent bookkeeping, signaled "transition to CLEANUP," etc.).

Empirically we don't know from the audit trail alone which layer triggered V2. The commit subject `chore(autopilot): record IMPLEMENT=complete, transition to CLEANUP` matches the `apply-outcome` output format, so Layer A is suspicious. But the sub-agent could also have shell-invoked the same string. **The Task 1 audit step (read `runner.py apply-outcome`) determines whether Layer A needs the fix.** If `apply-outcome` does NOT touch `current_phase`, Task 1's outcome is "Layer A already clean; only Layer B needs work."

## D2. Picking between `runner` and a new `validator` archetype for V1

`runner` system prompt today (per memory/runner observations):

> "You execute well-defined commands. Run the requested action, report the result, exit cleanly."

This is too thin for VALIDATE: a validator agent needs to orchestrate spec/evidence/deploy/smoke/security/e2e phases via `/validate-feature`, classify results, aggregate them into a PhaseRecord, and write a handoff. The `runner` framing as "execute one command" doesn't shape that behavior; the agent would likely run *something* and stop early.

A `validator` archetype with a tailored system prompt:

```yaml
validator:
  system_prompt: |
    You are a validator. Your job is to exercise the change under test
    end-to-end and produce a structured evidence record. Run the validation
    phases as specified (spec, evidence, deploy, smoke, security, e2e),
    aggregate findings, classify each phase pass/fail/skipped, and write
    the resulting PhaseRecord handoff. You may write evidence artifacts
    (reports, logs) and the handoff JSON. You do NOT modify source code
    being validated; if a validation fails, return outcome 'failed' and
    the orchestrator will dispatch a fix.
  model: standard
```

This separates "I produce evidence artifacts" from "I modify code being validated" — both are write-capable but to different scopes.

**Selected: introduce `validator` archetype.** Update `phase_mapping.VALIDATE` and `phase_mapping.VAL_FIX` accordingly. VAL_FIX is *fixing* validation failures, which arguably needs `implementer` instead — Task 1 includes deciding the VAL_FIX target.

## D3. Why not add a custom prompt override for VALIDATE in SKILL.md instead

Operator-side workarounds:

- `AUTOPILOT_PHASE_MODEL_OVERRIDE=VALIDATE=...` — only overrides model, not system_prompt. Doesn't help.
- Editing SKILL.md to prefix the prompt with "DO write artifacts" — violates the "treat prompt as opaque" rule in the dispatch protocol.
- Operator-side prompt augmentation via the orchestrator concatenating extra context — same rule violation; also doesn't survive across the runner.py build-dispatch boundary.

None of these compose well. The archetype mapping is the right surface to fix.

## D4. Apply-outcome guard: hard-error vs warn-and-continue

If `apply-outcome --phase X` is invoked while `current_phase = Y` where Y ≠ X, options:

- **Hard error.** Exit non-zero, refuse the update. Safe but breaks rare legitimate cases (e.g. operator manually recovering from a crash mid-transition).
- **Warn and continue.** Log a warning, do the update. Permissive but defeats the guard's purpose.
- **Hard error with `--force` escape hatch.** Default to refusal; allow `--force` for operator-conscious overrides.

**Selected: hard error with `--force` escape hatch.** Matches the broader autopilot pattern (complexity gate uses the same flag; sync-point skills use the same escape hatch). Operator has a clear signal when the contract is being violated and a clean way to override when they know what they're doing.

## D5. Test plan — V1

| Case | Setup | Expected |
|---|---|---|
| `archetypes.yaml` VALIDATE resolves write-capable | parse YAML, look up `phase_mapping.VALIDATE` → archetype name → `archetypes.<name>.system_prompt` | system_prompt does not contain "read-only", "without making changes", "report findings", "analyst" or other read-only markers |
| `build-dispatch --phase VALIDATE` renders write-capable prompt | shell out to runner.py | rendered `system_prompt` field passes the same check as above |
| `build-dispatch --phase VAL_FIX` renders write-capable prompt | shell out to runner.py | same |

## D6. Test plan — V2

| Case | Setup | Expected |
|---|---|---|
| `apply-outcome` does not transition `current_phase` | seed loop-state with `current_phase=IMPLEMENT`; run `apply-outcome --phase IMPLEMENT --outcome complete --handoff-id …`; re-read loop-state | `current_phase` still `IMPLEMENT`; `last_handoff_id`/`handoff_ids`/`phase_archetype` updated |
| `apply-outcome --phase X` errors when `current_phase=Y, X≠Y` | seed loop-state with `current_phase=IMPLEMENT`; run `apply-outcome --phase PLAN_REVIEW …` | exit non-zero with clear error message; loop-state untouched |
| `apply-outcome --phase X --force` overrides mismatch | seed loop-state with `current_phase=IMPLEMENT`; run `apply-outcome --phase PLAN_REVIEW --force …` | exit zero; `last_handoff_id` updated; `current_phase` STILL unchanged (force only bypasses the guard, doesn't add transition) |
| Write-capable phase prompt forbids running `apply-outcome` | `build-dispatch --phase IMPLEMENT` | rendered prompt body contains "DO NOT run apply-outcome" or equivalent |

## D7. Backward compatibility

| Surface | Before | After |
|---|---|---|
| `apply-outcome` CLI interface | `--change-id --phase --outcome --handoff-id` | unchanged + `--force` added |
| `apply-outcome` `current_phase` write | possibly (Task 1 audit determines) | never |
| `archetypes.yaml` `phase_mapping.VALIDATE` | `analyst` | `validator` (new) |
| `archetypes.yaml` `phase_mapping.VAL_FIX` | `analyst` (presumed) | TBD by Task 1 — either `validator` or `implementer` |
| Existing autopilot runs in flight | loop-state with `current_phase=VALIDATE` and archetype `analyst` recorded | next dispatch reads new archetype from YAML; recorded `phase_archetype` in loop-state stays as-is (historical record) |

Existing OpenSpec changes (including extract-gen-eval-package whose VALIDATE failed for this exact reason) DON'T need retroactive fixes — the substantive work was already done and the PR was created via the Option A skip-to-SUBMIT_PR path. The fix prevents recurrence on the NEXT autopilot run.

## D8. Edge cases

- **E1: Sub-agent running `apply-outcome` in a future runtime where it's been blocked.** Sub-agent receives exit-non-zero, retries, fails again. Sub-agent should treat this as a structural problem and return `outcome=failed`. Acceptable behavior; the prompt scaffold guards against the attempt in the first place (Layer B fix).

- **E2: Operator manually running `apply-outcome` to recover from a crash mid-transition.** They want to "complete" a phase whose handoff was written but whose state never updated. Use `--force` (D4). Document this in the runner's CLI help text.

- **E3: A future archetype mapping update introduces a read-only role for a write-capable phase.** Add a CI check (Task 4): grep `phase_mapping.<write-capable phases>` and assert their archetypes' system_prompts don't contain read-only markers.

- **E4: `apply-outcome --phase X` for a phase that isn't in the state machine** (e.g. `CLEANUP`). Already errors out on the validity of `--phase` per the existing CLI. Unchanged.
