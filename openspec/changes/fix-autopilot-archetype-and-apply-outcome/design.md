# Design — Fix autopilot archetype mapping and apply-outcome contract

## Revision History

- **2026-06-05 round 2** — Round-1 multi-vendor review (`/parallel-review-plan`) surfaced two critical findings (Layer C: sub-agent direct edits; Layer D: orchestrator transition-table) and several mid-severity findings (substring brittleness, self-contradicting validator prompt, prohibition coverage gaps, missing apply-outcome failure handling). This revision expands D1 to four layers, replaces D3's substring approach with a structured `write_capable: bool` field, renames `--force` to `--allow-phase-mismatch` per D4-revised, adds D6 (audit result durability), D9 (apply-outcome failure → ESCALATE), and D10 (orchestrator transition-table audit).

## D1. Four causal layers, four targeted fixes

The V2 transition `IMPLEMENT=complete → CLEANUP` could have been produced by any of four pathways. We can't tell which from the audit trail alone, so the fix covers all four. Task 1 audits each layer; the audit's findings are recorded in a durable artifact (D6) so future debugging can locate them.

### Layer A — `runner.py apply-outcome` writes `current_phase`

If `apply-outcome` writes `current_phase` (e.g. via an internal `next_phase` lookup table), then sub-agents calling `apply-outcome` will trip this automatically — no prompt instructions can prevent it.

**Fix**: remove the `current_phase` write from `apply-outcome`. Add a phase-mismatch guard (D4) that errors if `--phase` ≠ existing `current_phase`. Add an `--allow-phase-mismatch` flag for operator recovery (D4). The guard does NOT enable `current_phase` modification — it only allows updating `last_handoff_id`/`handoff_ids`/`phase_archetype` for a non-current phase.

### Layer B — Sub-agent ran `apply-outcome` itself

The sub-agent has shell access. Even after Layer A is fixed, a "helpful" sub-agent might run `apply-outcome` to "finish the bookkeeping" — and that's a contract violation even without `current_phase` getting touched.

**Fix**: every write-capable phase's dispatch prompt scaffold appends an explicit instruction: *"DO NOT run runner.py apply-outcome. Return (outcome, handoff_id) and exit; the orchestrator runs apply-outcome."*

### Layer C — Sub-agent edited `loop-state.json` directly

Sub-agents have shell access and can `python3 -c '... json.dump(...)'` or `sed -i` directly into `loop-state.json` without invoking `apply-outcome` at all. Layer B's `apply-outcome` prohibition alone leaves this gap open.

**Fix**: the same dispatch prompt scaffold appends a stricter prohibition: *"DO NOT edit openspec/changes/<id>/loop-state.json by any means. The orchestrator owns this file."* Layer C closes the gap that pure-prompt enforcement leaves — admittedly with the same weakness (sub-agents can ignore instructions), but layered prompt + structured failure mode is the current best-effort. Structural enforcement was considered and rejected per proposal Out-of-Scope.

### Layer D — Orchestrator's own next-phase transition logic is wrong

When the orchestrator resumes after a sub-agent returns `outcome=complete`, it consults a next-phase decision (whether code-side or YAML-side) to pick what comes after IMPLEMENT. If that decision logic maps `IMPLEMENT=complete → CLEANUP` (instead of `IMPL_ITERATE`), the bug is in the orchestrator's state-machine config — not in any sub-agent behavior. The commit subject would be authored by the orchestrator AFTER the sub-agent returned, making the failure look like Layer A or B but actually being neither.

**Fix**: Task 1.5 audits the orchestrator's phase-transition logic. If a `phase_transitions` table or equivalent exists and contains the wrong mapping, fix it to match the canonical state machine in `skills/autopilot/SKILL.md` sections 4-8. Add a regression test (Task 6.7) that seeds loop-state with `current_phase=IMPLEMENT, outcome=complete` and asserts the orchestrator's next-phase decision is `IMPL_ITERATE`.

### Why fix all four, not pick one

The four layers are not mutually exclusive and aren't observable from the bug's symptom alone. Fixing only the suspected layer (A) leaves three escape hatches; sub-agents have demonstrated initiative-taking behavior. Defense in depth is cheap (each fix is small) and the alternative is iterative bug-chasing after each future autopilot run produces a different layer's variant.

## D2. Picking between `runner` and a new `validator` archetype for V1

`runner` system prompt today:

> "You execute well-defined commands. Run the requested action, report the result, exit cleanly."

Too thin for VALIDATE: a validator agent needs to orchestrate spec/evidence/deploy/smoke/security/e2e phases via `/validate-feature`, classify results, aggregate them into a PhaseRecord, and write a handoff. The "execute one command" framing doesn't shape that behavior.

A `validator` archetype with a tailored system prompt:

```yaml
validator:
  write_capable: true
  system_prompt: |
    You are a validator. Your job is to exercise the change under test
    end-to-end and produce a structured evidence record. Run the validation
    phases as specified (spec, evidence, deploy, smoke, security, e2e),
    aggregate findings, classify each phase pass/fail/skipped, and write
    the resulting PhaseRecord handoff. You produce evidence artifacts
    (reports, logs) and the handoff JSON. If a validation fails, return
    outcome 'failed' and the orchestrator will dispatch a fix.
  model: standard
```

**Important change vs round-1 draft**: the round-1 prompt included the line *"You do NOT modify source code being validated"*, which a parallel-review reviewer (codex) flagged as self-contradicting — the validator IS write-capable per the schema, but that line frames it as not-modifying, which inherits the same role-confusion that V1 introduced. Scope guidance ("don't touch source code being validated") belongs in task descriptions, not role system prompts. The revised prompt above omits it.

**Selected: introduce `validator` archetype.** `VAL_FIX` maps to `implementer` (also write-capable) because VAL_FIX is *fixing* code, not *producing* evidence.

## Glossary — Canonical Lists

To eliminate the duplication-drift risk surfaced in round-2 review, these lists are defined here once and referenced from proposal.md, spec.md, and tasks.md:

- **Write-capable phases** (11): `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`.
- **State-only phases** (2): `INIT`, `SUBMIT_PR`.
- **Terminal phases** (2): `DONE`, `ESCALATE`.

A future change adding a new write-capable phase MUST update this list AND any place that mechanically enumerates it (Task 6.1's CI guard, Task 4.2's coverage smoke, the spec's "phase coverage" scenarios).

## D3. Capability check: structured field, not substring matching

The round-1 design used substring matching over `system_prompt` text to detect read-only archetypes — checking for phrases like "without making changes", "do not modify", "report findings only". Two reviewers (claude_code + gemini) independently flagged this as brittle: any future rephrasing ("report only", "no modifications", "analyze without writing") passes the check while violating intent. The confirmed finding moved the design.

**Selected approach** (revised): add a structured `write_capable: bool` field to every archetype entry in `archetypes.yaml`. The runner's archetype resolver enforces directly on this field. The check is unambiguous, can't drift over time, and is mechanically verifiable.

```yaml
archetypes:
  analyst:
    write_capable: false
    system_prompt: "You are a codebase analyst..."
  validator:
    write_capable: true
    system_prompt: "You are a validator..."
  implementer:
    write_capable: true
    system_prompt: "You are a focused implementer..."
  # ... etc
```

The CI guard (Task 5) iterates the canonical write-capable phases list (Glossary above) and asserts each resolved archetype has `write_capable: true`. No string matching.

The original substring-based scenarios in the spec are replaced with structured-field-based scenarios (see spec.md round 2).

### D3.1. Resolver behavior on missing `write_capable` field

If a future archetype entry omits `write_capable`, the resolver MUST fail-loud with a clear error identifying the offending archetype name and the required field. Fail-loud (not fail-closed-as-false) is the safer choice: it prevents an entire class of "accidentally added write-capable archetype with no declaration" silent bugs, at the cost of forcing every archetype author to make an explicit choice. The migration path is: Task 2.1 adds the field to every existing archetype; the resolver enforces presence from then on. There is no implicit default.

### D3.2. Migration concerns (round-2 finding)

Adding `write_capable` to `archetypes.yaml` is a backward-incompatible schema change. Other consumers of `archetypes.yaml` (if any) that don't know about the new field will not break unless they validate against the schema strictly. Task 2.7 updates the JSON schema; Task 1 (audit) identifies other consumers in the repo and the audit-result.md captures any that need updating. No external consumers outside this repo are currently known.

## D4. Phase-mismatch guard: rename `--force` to `--allow-phase-mismatch`

Round-1 design called the escape-hatch flag `--force`. A reviewer (claude_code) flagged this as misleading — operators expect `--force` to be the most-permissive escape hatch, but in this design `--force` only bypasses the phase-mismatch guard; it explicitly does NOT enable `current_phase` modification. The narrower semantics deserve a narrower name.

**Selected**: rename to `--allow-phase-mismatch`. Operators reading the CLI help see the exact thing the flag allows, with no ambiguity.

```bash
# Default: error if --phase doesn't match loop-state's current_phase
runner.py apply-outcome --change-id X --phase IMPLEMENT --outcome complete --handoff-id ...
# Error: --phase IMPLEMENT does not match current_phase=PLAN_REVIEW. Use --allow-phase-mismatch to apply anyway (current_phase will not be modified).

# With --allow-phase-mismatch: applies anyway, current_phase still untouched
runner.py apply-outcome --change-id X --phase IMPLEMENT --outcome complete --handoff-id ... --allow-phase-mismatch
```

The error message MUST mention `--allow-phase-mismatch` so operators can find the escape hatch without reading the help text. (Gemini-surfaced finding.)

### D4.1. Rename vs. deprecation alias

The audit (Task 1.3) determines whether `--force` exists in `apply-outcome` today:

- **If `--force` does NOT exist** (likely, since the no-transition guard itself is being newly added by this change): the new flag is named `--allow-phase-mismatch` from the start. No deprecation needed.
- **If `--force` DOES exist** (e.g. via a partial earlier implementation): Task 3.5 adds `--force` as a deprecation alias for `--allow-phase-mismatch`. The alias emits a stderr warning and is removed after one release. No hard-break of existing callers.

The audit-result.md (Task 1.7) records which path applies.

## D5. Test plan — V1 capability check

| Case | Setup | Expected |
|---|---|---|
| `phase_mapping.VALIDATE` resolves to `write_capable: true` | parse YAML, look up `phase_mapping.VALIDATE` → archetype name → `archetypes.<name>.write_capable` | `True` |
| `phase_mapping.VAL_FIX` resolves to `write_capable: true` | same | `True` |
| All write-capable phases resolve to `write_capable: true` | iterate write-capable-phases list (per D7), assert each maps to `write_capable: true` | all pass |
| `build-dispatch --phase VALIDATE` uses validator archetype | shell out to runner.py | `archetype` field in JSON output is `validator` |
| Validator system_prompt does not self-contradict | inspect `archetypes.yaml validator.system_prompt` | does NOT contain "do not modify", "without modifying", "without making changes" or equivalent (we still enforce this for the system_prompt text as a *secondary check* — defense in depth against future drift in the role's prompt itself, not as the primary capability gate) |

## D6. Audit result durability artifact

Task 1 is an audit step whose outcome determines whether Layer A actually requires changes vs. is already clean (`apply-outcome` doesn't write `current_phase` today). A reviewer flagged that recording the audit finding "in the commit message" is informal and not searchable later.

**Selected**: write the audit outcome to `openspec/changes/fix-autopilot-archetype-and-apply-outcome/audit-result.md`. The file MUST contain, per layer:

- The empirical finding (e.g. "Layer A: `apply-outcome` does/does NOT write `current_phase`. Evidence: line X of runner.py.")
- The decision (e.g. "Layer A fix required" or "Layer A already clean; no code change needed")
- The link to the task(s) that act on the finding

Subsequent design.md, spec changes, and implementation tasks refer to `audit-result.md` for the load-bearing layer-by-layer findings. This makes the audit's conclusions discoverable from the change-id itself, not from git log archaeology.

## D7. Backward compatibility

| Surface | Before | After |
|---|---|---|
| `apply-outcome` CLI interface | `--change-id --phase --outcome --handoff-id` | unchanged + `--allow-phase-mismatch` added |
| `apply-outcome` `current_phase` write | possibly (Task 1 audit determines) | never |
| `apply-outcome` `phase_history` append | already happening | unchanged, but now codified as a spec requirement |
| `apply-outcome` non-zero exit behavior | implementation-dependent | orchestrator MUST detect and transition to ESCALATE (D9) |
| `archetypes.yaml` `phase_mapping.VALIDATE` | `analyst` | `validator` (new archetype) |
| `archetypes.yaml` `phase_mapping.VAL_FIX` | `analyst` (presumed) | `implementer` |
| `archetypes.yaml` `archetypes.*` entries | each has `system_prompt` and `model` | each adds `write_capable: bool` (required for all archetypes) |
| Dispatch prompt scaffold for write-capable phases | no state-mutation prohibition | includes Layer B + C prohibitions |
| Dispatch prompt scaffold for read-only phases | no state-mutation prohibition | unchanged (state-only phases don't need it) |
| Existing autopilot runs in flight | loop-state with `current_phase=VALIDATE` recorded with old archetype | next dispatch reads new archetype from YAML; recorded `phase_archetype` in loop-state stays as-is |

Existing OpenSpec changes (including extract-gen-eval-package, whose VALIDATE failed for exactly the V1 reason) don't need retroactive fixes — that PR's substantive work was completed via the Option-A skip-to-SUBMIT_PR path. The fix prevents recurrence on the NEXT autopilot run.

## D8. Edge cases

- **E1: Sub-agent running `apply-outcome` in a future runtime where it's been blocked**. Sub-agent receives exit-non-zero, retries, fails again. Sub-agent should treat this as a structural problem and return `outcome=failed`. The prompt scaffold's Layer B prohibition guards against the attempt in the first place; this is the fallback safety net.

- **E2: Operator manually running `apply-outcome` to recover from a crash mid-transition**. They want to record an outcome for a phase whose handoff was written but whose state never updated. Use `--allow-phase-mismatch` (D4). The runner's CLI help text and the phase-mismatch error message both document this.

- **E3: A future archetype mapping update introduces `write_capable: false` for a write-capable phase**. The CI check (Task 5) catches it before merge by failing the test.

- **E4: `apply-outcome --phase X` for a phase that isn't in the state machine** (e.g. `CLEANUP`). Already errors out on `--phase` validity per the existing CLI surface. The phase-mismatch guard is an additional check on top.

- **E5: Sub-agent obeys Layer B (doesn't run `apply-outcome`) but writes `loop-state.json` directly (Layer C violation)**. Layer C's prohibition is the prompt-level discouragement. If the sub-agent ignores both prompts, the orchestrator's next dispatch reads the corrupted state and the V2 failure recurs. This is acknowledged in proposal Out-of-Scope as the residual risk of prompt-based enforcement; structural enforcement is a future change if this proves insufficient.

## D9. `apply-outcome` failure handling: orchestrator transitions to ESCALATE

A reviewer (claude_code + codex) flagged that after the V2 fix lands, `apply-outcome` becomes the sole writer of `last_handoff_id`/`handoff_ids`/`phase_archetype`. A silent `apply-outcome` failure (disk full, lock contention, malformed loop-state, transient FS error) leaves loop-state inconsistent with the just-written handoff — and the next dispatch reads stale state.

**Selected**: when `apply-outcome` exits non-zero, the orchestrator MUST:

1. Detect the non-zero exit code.
2. Retain the un-applied handoff file in `openspec/changes/<id>/handoffs/` (do not delete it).
3. Append a `phase_history` entry recording the apply-outcome failure (writing this directly via a small helper is OK because the orchestrator owns `phase_history` writes too).
4. Transition `current_phase` to `ESCALATE` with `previous_phase` set to the failing phase.

This makes apply-outcome failures a first-class state in the autopilot state machine. The operator resumes via `/autopilot <change-id> --force` after addressing the underlying cause (free disk space, restart the FS, etc.) — the orchestrator reads the retained handoff and re-applies.

### D9.1. Double-failure handling: what if ESCALATE-write also fails?

A round-2 finding (gemini) and a related codex finding asked: if `apply-outcome` fails because `loop-state.json` is corrupt or the FS is read-only, can the orchestrator even write the `ESCALATE` transition that D9 requires?

Resolution:

- **Best-effort transition**: the orchestrator attempts to write the `phase_history` entry and update `current_phase = ESCALATE`. If THAT write also fails, the orchestrator falls back to emitting a structured log line (stderr, level CRITICAL, with the handoff path and the underlying cause) AND exits non-zero.
- **The retained handoff file is the durable record**: regardless of whether the ESCALATE write succeeds, the handoff file written by the sub-agent stays in place. On operator resume (after fixing the disk/FS), the orchestrator reads the handoff and applies it.
- **No silent data loss**: the worst case is an orchestrator exit with a CRITICAL log line and a handoff on disk. The operator has both the symptom (exit + log) and the recovery path (the handoff). No state is lost.

This is acknowledged as best-effort, not guaranteed-atomic. Atomic state-transition guarantees would require a transactional store (SQLite, etc.), which is over-scope for this change.

## D10. Orchestrator transition-table audit (Layer D)

Task 1.5 audits the autopilot orchestrator's next-phase decision logic. The audit asks:

- Does the orchestrator consult a `phase_transitions` table (YAML/JSON config, hardcoded dict, or generated from SKILL.md state diagram)?
- For each `(current_phase, outcome)` pair on the state machine, what next-phase does the table produce?
- For `(IMPLEMENT, complete)`, the answer MUST be `IMPL_ITERATE`. For `(IMPL_ITERATE, complete)`, `IMPL_REVIEW` if `cli_review_enabled` else `VALIDATE`. Etc.
- Any mismatch is the Layer D bug.

If the audit finds Layer D is the bug (or contributes to it), the fix is to correct the transition table to match SKILL.md sections 4-8.

### D10.1. Scope decision: in-place fix vs. structural extraction

A round-2 finding (claude_code, gemini) flagged that "extract distributed logic into a single table" (Task 5.2 in the round-1 plan) is a structural refactor that may exceed the bug-fix scope of this change. The scope decision is made conditional on the audit:

- **If Task 1.5 finds the orchestrator already uses a centralized table** (a single dict, YAML config, or equivalent): Task 5.2 only updates wrong mappings. In-place fix, small scope.
- **If Task 1.5 finds the orchestrator's next-phase logic is distributed** across multiple `if/elif` branches: the targeted fix (correcting any wrong branches that map IMPLEMENT-complete→CLEANUP) lands in this change. The structural extraction (consolidating into a single table) is committed to as a **follow-up change** rather than absorbed silently here. The follow-up's change-id is recorded in `audit-result.md` so the commitment is durable.

This split keeps the current change focused on bug-fixing while making the structural-refactor commitment explicit. The Layer D regression test (Task 6.6) runs against whichever shape the orchestrator has post-fix.

Add a regression test (Task 6.6): seed `loop-state.json` with `current_phase=IMPLEMENT, last_handoff_id=...` and `phase_history` ending in `outcome=complete`; invoke the orchestrator's next-phase decision; assert the result is `IMPL_ITERATE` (or whatever SKILL.md prescribes).
