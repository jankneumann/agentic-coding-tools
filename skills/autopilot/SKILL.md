---
name: autopilot
description: "Orchestrate the full plan-review-implement-validate-PR lifecycle with multi-vendor review convergence"
category: Git Workflow
tags: [automation, lifecycle, multi-vendor, review, convergence]
triggers:
  - "autopilot"
  - "auto dev loop"
  - "run dev loop"
  - "full lifecycle"
---

# Autopilot

Orchestrate the full plan-review-implement-validate-PR lifecycle with multi-vendor review convergence. For simple features, runs fully automatically from proposal to PR. Stops at merge for human approval.

## Arguments

`<change-id or description>` - Either an existing OpenSpec change-id or a feature description in quotes.

Optional flags:
- `--force` — Skip the GATEKEEPER judge entirely (operator override of the
  verifiability/risk gate). Also bypasses the scope-safety floor.
- `--val-review` — Force VAL_REVIEW phase even for simple features
- `--no-review` — Skip multi-vendor review phases (PLAN_REVIEW, IMPL_REVIEW); iterate phases still run

## Prerequisites

- OpenSpec CLI installed (v1.0+)
- At least 2 vendor CLIs available (claude, codex, gemini) for multi-vendor convergence
- Coordinator recommended (degrades to linear workflow without it)

## Coordinator Capability Check

At skill start, run the coordinator detection script:

```bash
python3 "<skill-base-dir>/../coordination-bridge/scripts/check_coordinator.py" --json
```

If coordinator is unavailable, emit a warning and fall back to sequential skill invocation:
1. `/plan-feature` (if description provided)
2. `/iterate-on-plan` (always runs — self-review)
3. `/parallel-review-plan` (CLI only — single pass, no convergence loop)
4. `/implement-feature`
5. `/iterate-on-implementation` (always runs — self-review)
6. `/parallel-review-implementation` (CLI only — single pass, no convergence loop)
7. `/validate-feature`
8. Create PR manually

## Steps

### 0. Parse Arguments and Check for Resume

Parse the argument to determine:
- If it matches an existing change-id in `openspec/changes/`: load that change
- Otherwise: treat as a feature description for the PLAN phase

Check for existing loop state:
```bash
LOOP_STATE="openspec/changes/<change-id>/loop-state.json"
if [ -f "$LOOP_STATE" ]; then
    # Resume from saved state — report current phase and offer to continue
fi
```

If `loop-state.json` exists and `current_phase == "ESCALATE"`:
- Report the escalation reason and blocking findings
- Ask if the issue has been resolved
- If yes: re-evaluate the gate check for `previous_phase`

### 1. INIT Phase

**Detect CLI mode** — check whether multi-vendor review is available:

```bash
# CLI mode: vendor CLIs are available for multi-vendor review dispatch
CLI_REVIEW_ENABLED=true
if [[ "$ARGUMENTS" == *"--no-review"* ]]; then
  CLI_REVIEW_ENABLED=false
fi
# Also disable if no vendor CLIs are installed (non-interactive/cloud environment)
python3 "<skill-base-dir>/../parallel-infrastructure/scripts/review_dispatcher.py" --check-vendors
if [[ $? -ne 0 ]]; then
  CLI_REVIEW_ENABLED=false
  echo "[autopilot] No vendor CLIs detected — multi-vendor review disabled"
fi
```

Pass `cli_review_enabled` to `run_loop()`. When False, PLAN_ITERATE and IMPL_ITERATE still run (self-review is always valuable), but PLAN_REVIEW and IMPL_REVIEW are skipped.

Run the entry gate:
```python
from complexity_gate import assess_complexity
result = assess_complexity(work_packages_path, proposal_path, force=<--force flag>)
```

The gate no longer blocks on size. It does two cheap, deterministic things and
records the result in `loop-state.json`:

1. **Gather the signal profile** — `result.signals` is a risk + verifiability
   profile (package count, LOC estimate, external deps, db/security flags, write
   scope, and verifiability facts `has_specs` / `has_tasks` / `has_proposal`).
   Persist it to `state.gate_signals`; the GATEKEEPER judge consumes it.
2. **Scope-safety floor** — the ONLY remaining hard block. A package that can
   write the whole repository (`**`, `*`, `.`) defeats worktree isolation, so
   `result.force_required` is set; without `--force`, `result.allowed == False`
   → report warnings and stop (suggest `--force`).

Then:
- If `result.val_review_enabled` (db-migration / security signals): record it.
- If `result.warnings`: report them but continue.
- If `result.checkpoints`: log injected scheduling checkpoints
  (`wave-validation`, `limit-concurrency`, `dependency-review`,
  `db-migration-review`, `security-review`).

Gate policy:
- LOC, package count, and external-dependency counts are **signals, not
  blocks**. Large but well-decomposed work is fine; high counts only emit
  scheduling checkpoints so the DAG paces itself.
- Database-migration and security signals (`auth`, `crypto`, `secret`,
  `token`) enable validation review without blocking automation.
- The only deterministic hard block is a broad repository write scope, which
  still requires `--force`.
- Everything else — *can outcomes be verified? is the risk acceptable?* — is
  delegated to the GATEKEEPER judge sub-agent (Step 1.5), which weighs the
  signals against autopilot's downstream safeguards (review convergence,
  validation, and the mandatory human merge gate).

**Record INIT phase archetype** (state-only resolver — D9). After loop-state.json
is written, shell out to record `phase_archetype` for INIT so observability
covers all 14 non-terminal phases, not just the 8 dispatching phases:

```bash
python3 "<skill-base-dir>/scripts/runner.py" record-state-only-archetype \
  --change-id <change-id> --phase INIT
```

Failure here is non-fatal — the helper logs a warning and writes
`phase_archetype = null` if the coordinator is unreachable.

### 1.5. GATEKEEPER Phase (Judge)

Replaces deterministic complexity blocking with a model-based judgment of
whether the change can run autonomously. **Skipped entirely when `--force` is
set** (operator override → transitions straight to PLAN).

The GATEKEEPER judge sub-agent reads `state.gate_signals` plus the available
plan artifacts and evaluates two things — NOT raw size:

1. **Verifiability** — can the intended outcomes be objectively checked?
   WHEN/THEN specs, a task breakdown, and testable acceptance criteria make
   outcomes verifiable; a bare description does not.
2. **Risk** — blast radius and reversibility if a slice goes wrong (db
   migrations, security surfaces, external deps, write scope).

The judge explicitly accounts for autopilot's downstream safeguards
(multi-vendor PLAN/IMPL review convergence, the VALIDATE phase, and a mandatory
human merge gate) and biases toward letting verifiable work proceed — large but
well-specified changes are acceptable.

Dispatch protocol (3 steps — same provider-neutral path as other phases; read
-only, so `isolation` is not `worktree`):

1. Build kwargs:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" build-dispatch \
     --phase GATEKEEPER --change-id <change-id>
   ```
2. Call the dispatch adapter with `prompt` / `model` (treat `prompt` as opaque).
   Parse the agent's last message for `(outcome, handoff_id)`. Outcome is one of
   `proceed`, `proceed_with_review`, or `escalate`.
3. Apply the outcome:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" apply-outcome \
     --change-id <change-id> --phase GATEKEEPER \
     --outcome <outcome> --handoff-id <handoff_id>
   ```

**Fallback (permissive)**: If `build-dispatch` returns `archetype: null` OR no
dispatch adapter is available (headless CI, coordinator down), do NOT block —
derive a permissive verdict from `state.gate_signals`: `proceed_with_review`
when any risk signal (db migration, security, broad scope) is present,
otherwise `proceed`. Record `phase_archetype = null` via `apply-outcome`.

**If `proceed`**: transition to PLAN.
**If `proceed_with_review`**: set `state.val_review_enabled = true`, transition to PLAN.
**If `escalate`**: transition to ESCALATE (the change is judged unverifiable or
too risky for autonomous execution; resolve and resume, or re-run with `--force`).

### 2. PLAN Phase

**Record PLAN phase archetype** (state-only resolver — D9 / VAL_REVIEW G-V-001).
PLAN dispatches via the `/plan-feature` slash command rather than the
provider-neutral dispatch adapter, so it doesn't go through `runner.py build-dispatch`. To
keep observability uniform across all 14 non-terminal phases, shell out:

```bash
python3 "<skill-base-dir>/scripts/runner.py" record-state-only-archetype \
  --change-id <change-id> --phase PLAN
```

Failure here is non-fatal — the helper logs a warning and writes
`phase_archetype = null` if the coordinator is unreachable.

If argument was a description (no existing change-id):
- Invoke `/plan-feature <description>` (tier auto-detected based on coordinator availability)
- **Before showing/answering the proposal approval gate prompt**, invoke `/review-artifacts <change-id>` to open proposal/design/spec/tasks artifacts in a new VS Code review session
- Wait for proposal approval before continuing

If argument was an existing change-id:
- Verify proposal artifacts exist (proposal.md, design.md, specs/, tasks.md)
- Skip to PLAN_REVIEW

### Per-Phase Sub-Agent Dispatch Protocol

The following 8 phases (GATEKEEPER, PLAN_ITERATE, PLAN_REVIEW, IMPLEMENT,
IMPL_ITERATE, IMPL_REVIEW, VALIDATE, VAL_REVIEW) dispatch through the
provider-neutral dispatch adapter when an adapter is available. Claude Code adapters may
internally call the Claude harness `Agent(...)` tool; Codex and Gemini/Jules
use their configured provider adapter or fall through to the inline path.
Each block follows the same 3-step protocol:

1. **Build dispatch kwargs** by shelling out to `runner.py build-dispatch`.
   The runner queries the coordinator for the resolved archetype, builds
   the per-phase prompt scaffold, folds `system_prompt` into `prompt`
   with the literal separator `\n\n---\n\n`, and writes a per-run
   resolution cache. JSON output: `{prompt, model, system_prompt,
   isolation, archetype, provider, phase, expected_outcomes}`.
2. **Invoke the provider-neutral dispatch adapter** with the JSON values.
   Claude Code's adapter may translate this to `Agent(...)` internally.
   **Treat `prompt` as opaque — do not concatenate, do not prepend, do
   not split on the separator.** SKILL.md never folds; folding lives
   inside `build_phase_dispatch_kwargs` (single source of truth).
3. **Apply the outcome** by shelling out to `runner.py apply-outcome`,
   passing the `(outcome, handoff_id)` returned by the sub-agent. This
   updates `loop-state.json` (`last_handoff_id`, `handoff_ids`,
   `phase_archetype`) and consumes the cache file.

**Fallback (D5)**: If `runner.py build-dispatch` returns `archetype: null`
(coordinator unreachable or fallback), OR if no provider-neutral dispatch
adapter is exposed in the current orchestrator session, the dispatch block
falls through to the inline-prose path (the slash-command invocation), and
`apply-outcome` records `phase_archetype = null`.

The dispatch invocation uses paths relative to the autopilot skill dir.
Substitute `<skill-base-dir>` with the autopilot skill's actual location
(typically `.claude/skills/autopilot/` or `.agents/skills/autopilot/`).

### 2.5. PLAN_ITERATE Phase (Always Runs)

Self-review and refinement of plan artifacts. This phase always runs regardless of CLI mode.

Goal: refine the proposal across completeness, clarity, feasibility, scope,
consistency, testability, parallelizability, and assumptions axes.

Dispatch protocol (3 steps):

1. Build kwargs:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" build-dispatch \
     --phase PLAN_ITERATE --change-id <change-id>
   ```
   Parse the JSON output. Capture `prompt`, `model`, `isolation`.

2. Call the provider-neutral dispatch adapter with those values, treating
   `prompt` as opaque (no concatenation). Claude adapter internal example:
   ```
   result = Agent(prompt=<dispatch.prompt>, model=<dispatch.model>,
                  isolation=<dispatch.isolation>)
   ```
   Parse the agent's last message for `(outcome, handoff_id)` per the
   protocol in `phase_agent._validate_result`. Outcome is `"complete"`
   on settled refinement, `"failed"` otherwise.

3. Apply the outcome:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" apply-outcome \
     --change-id <change-id> --phase PLAN_ITERATE \
     --outcome <outcome> --handoff-id <handoff_id>
   ```

**Fallback**: If step 1 returned `archetype: null` OR the dispatch adapter is
unavailable, run the inline path: invoke `/iterate-on-plan <change-id>`
directly. After the slash command returns, run `apply-outcome` so
`phase_archetype = null` is recorded for this phase.

**If complete**: Transition to PLAN_REVIEW (CLI mode) or IMPLEMENT (non-CLI mode).
**If failed**: Transition to ESCALATE.

### 3. PLAN_REVIEW Phase (Convergence Loop — CLI Only)

**Skipped when `cli_review_enabled=false`** — transitions directly to IMPLEMENT.

Multi-vendor plan review with convergence — outcome is `"converged"` if
no blocking findings, `"not_converged"` otherwise, `"max_iter"` once
`max_phase_iterations` is exhausted.

Dispatch protocol (3 steps):

1. Build kwargs:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" build-dispatch \
     --phase PLAN_REVIEW --change-id <change-id>
   ```

2. Call `Agent(prompt=<dispatch.prompt>, model=<dispatch.model>,
   isolation=<dispatch.isolation>)`. Treat `prompt` as opaque. Parse
   the agent's last message for `(outcome, handoff_id)`.

3. Apply the outcome:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" apply-outcome \
     --change-id <change-id> --phase PLAN_REVIEW \
     --outcome <outcome> --handoff-id <handoff_id>
   ```

**Fallback**: If `archetype: null` OR the dispatch adapter is unavailable, run the
inline path — invoke the convergence loop directly:

```python
from convergence_loop import converge
result = converge(
    change_id=change_id,
    review_type="plan",
    artifacts_dir=change_dir,
    worktree_path=worktree_path,
    agents_yaml_path=agents_yaml_path,
    max_rounds=3,
    min_quorum=2,
    fix_mode="inline",
    fix_callback=apply_plan_fixes_inline,
    memory_callback=write_memory,
)
```

Then run `apply-outcome` to record `phase_archetype = null`.

**If converged**: Report findings summary, transition to IMPLEMENT.
**If not converged**: Report reason (max_rounds, stalled, quorum_lost, disagreement), transition to ESCALATE.

For **inline plan fixes** (PLAN_FIX, NOT a sub-agent dispatch): Read the
blocking findings, edit the relevant plan files directly (proposal.md,
design.md, specs, work-packages.yaml), re-validate with `openspec
validate`. PLAN_FIX inherits `phase_archetype` from the preceding
PLAN_REVIEW — convergence_loop never overwrites the field.

#### Convergence Durability Contract

`converge()` writes per-vendor findings AND a manifest to `<artifacts_dir>/.review-cache/round-N/` BEFORE invoking the consensus synthesizer. If synthesis raises (e.g. the `consensus_synthesizer.py:59` `line_range` parser bug), the original exception propagates to the caller and the persisted findings remain on disk for postmortem analysis. **This is durability, not automatic recovery** — the proposal does not introduce subprocess fallback; recovery awaits a separate parser-fix proposal.

`ConvergenceResult.checkpoint_dir: Path | None` points at the most-recent round's checkpoint directory. Recovery-aware callers read this field to locate persisted findings; existing callers ignore it (defaults to `None` for backward compatibility).

**Operator-monitored log entries** (Python `logging`, level ERROR, structured via `extra={"event": ..., ...}`):

- `convergence.synthesis_failed_with_checkpoint` — synthesis (or upstream `Finding.from_dict()`) raised. Payload includes `checkpoint_dir` for manual recovery.
- `convergence.checkpoint_write_failed` — OSError/PermissionError during checkpoint write. Original exception still propagates.

Synthesis failures will continue to surface to the autopilot caller. The value of this contract is durability for postmortem and manual recovery, not automatic recovery — see [docs/parallel-agentic-development.md](../../docs/parallel-agentic-development.md) Section 8 for the manual-invocation procedure.

### 3.5. Write-Capable Phase Isolation

In local CLI execution, the shared checkout is read-only. Every autopilot phase
that may create, modify, delete, format, commit, push, or persist artifacts runs
with `isolation="worktree"` from `runner.py build-dispatch`.

Write-capable phases are `PLAN`, `PLAN_ITERATE`, checkpoint-writing
`PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`,
checkpoint-writing `IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, artifact-writing
`VAL_REVIEW`, and `VAL_FIX`. `INIT` and `SUBMIT_PR` are state-only transitions.

Sub-agents still invoke the phase skill (`/plan-feature`, `/iterate-on-plan`,
`/implement-feature`, `/validate-feature`, etc.) as their first write-capable
step so the skill can call `worktree.py setup` and then verify the resulting
checkout with:

```bash
skills/.venv/bin/python skills/shared/checkout_policy.py require-mutation
```

### 4. IMPLEMENT Phase

Implement the next slice of work per `tasks.md`. IMPLEMENT is one of the
write-capable phases that runs with `isolation="worktree"` — sub-agent commits
land on a sibling worktree branch and merge back at completion.

**Claude harness worktree caveat**: Claude Code's `Agent(isolation="worktree")`
may create the harness worktree from the default branch (`main`), not from the
orchestrator's current feature branch. The sub-agent MUST run `/implement-feature
<change-id>` as its first write-capable step so `worktree.py setup` can adopt
the resolved feature parent branch and create/check out the agent child branch.
Do not merge the feature branch into a main-rooted harness checkout to get
context; if branch adoption fails, return `"failed"` and let the orchestrator
fix the branch/override state.

Dispatch protocol (3 steps):

1. Build kwargs:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" build-dispatch \
     --phase IMPLEMENT --change-id <change-id>
   ```

2. Call `Agent(prompt=<dispatch.prompt>, model=<dispatch.model>,
   isolation=<dispatch.isolation>)`. The `isolation` value will be
   `"worktree"` for IMPLEMENT. Treat `prompt` as opaque. Parse the
   agent's last message for `(outcome, handoff_id)`. Outcome is
   `"complete"` on success, `"failed"` (or `"escalate"`) on
   unrecoverable error.

3. Apply the outcome:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" apply-outcome \
     --change-id <change-id> --phase IMPLEMENT \
     --outcome <outcome> --handoff-id <handoff_id>
   ```

**Fallback**: If `archetype: null` OR the dispatch adapter is unavailable, run the
inline path — invoke `/implement-feature <change-id>` (tier
auto-detected based on coordinator + work-packages.yaml). Record
`package_authors` from the implementation results. After completion,
run `apply-outcome` to record `phase_archetype = null`.

### 4.5. IMPL_ITERATE Phase (Always Runs)

Self-review and refinement of implementation. This phase always runs
regardless of CLI mode. Reads proposal, design, and all changed source
files. Identifies bugs, security issues, edge cases, performance
problems. Outcome is `"complete"` when refinements settle, `"failed"`
otherwise.

Dispatch protocol (3 steps):

1. Build kwargs:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" build-dispatch \
     --phase IMPL_ITERATE --change-id <change-id>
   ```

2. Call `Agent(prompt=<dispatch.prompt>, model=<dispatch.model>,
   isolation=<dispatch.isolation>)`. Treat `prompt` as opaque. Parse
   the agent's last message for `(outcome, handoff_id)`.

3. Apply the outcome:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" apply-outcome \
     --change-id <change-id> --phase IMPL_ITERATE \
     --outcome <outcome> --handoff-id <handoff_id>
   ```

**Fallback**: If `archetype: null` OR the dispatch adapter is unavailable, run the
inline path — invoke `/iterate-on-implementation <change-id>`. Then run
`apply-outcome` so `phase_archetype = null` is recorded.

**If complete**: Transition to IMPL_REVIEW (CLI mode) or VALIDATE (non-CLI mode).
**If failed**: Transition to ESCALATE.

### 5. IMPL_REVIEW Phase (Convergence Loop — CLI Only)

**Skipped when `cli_review_enabled=false`** — transitions directly to VALIDATE.

Multi-vendor implementation review with `fix_mode="targeted"`. Outcome
is `"converged"` if no blocking findings, `"not_converged"` otherwise.

Dispatch protocol (3 steps):

1. Build kwargs:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" build-dispatch \
     --phase IMPL_REVIEW --change-id <change-id>
   ```

2. Call `Agent(prompt=<dispatch.prompt>, model=<dispatch.model>,
   isolation=<dispatch.isolation>)`. Treat `prompt` as opaque. Parse
   the agent's last message for `(outcome, handoff_id)`.

3. Apply the outcome:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" apply-outcome \
     --change-id <change-id> --phase IMPL_REVIEW \
     --outcome <outcome> --handoff-id <handoff_id>
   ```

**Fallback**: If `archetype: null` OR the dispatch adapter is unavailable, run the
inline path — invoke the convergence loop with `fix_mode="targeted"`
and a `post_fix_validator` callback for scoped pytest/mypy/openspec
checks. Then run `apply-outcome` to record `phase_archetype = null`.

For **targeted implementation fixes** (IMPL_FIX, NOT a sub-agent
dispatch): Look up the lead vendor from `package_authors`, use
`CliVendorAdapter.dispatch()` to send the fix to that specific vendor,
scoped to the package's `write_allow` paths. IMPL_FIX inherits
`phase_archetype` from the preceding IMPL_REVIEW.

### 6. VALIDATE Phase

Run validation phases (spec, evidence, deploy, smoke, security, e2e)
per validate-feature. Aggregate results into a PhaseRecord. Outcome is
`"continue"` on PASS, `"escalate"` on FAIL.

Dispatch protocol (3 steps):

1. Build kwargs:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" build-dispatch \
     --phase VALIDATE --change-id <change-id>
   ```

2. Call `Agent(prompt=<dispatch.prompt>, model=<dispatch.model>,
   isolation=<dispatch.isolation>)`. Treat `prompt` as opaque. Parse
   the agent's last message for `(outcome, handoff_id)`.

3. Apply the outcome:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" apply-outcome \
     --change-id <change-id> --phase VALIDATE \
     --outcome <outcome> --handoff-id <handoff_id>
   ```

**Fallback**: If `archetype: null` OR the dispatch adapter is unavailable, run the
inline path — invoke `/validate-feature <change-id>` (tier
auto-detected). Then run `apply-outcome` to record `phase_archetype = null`.

**If passed**: Check `val_review_enabled` — if true, go to VAL_REVIEW; otherwise skip to SUBMIT_PR.
**If failed**: Transition to VAL_FIX.

### 7. VAL_REVIEW Phase (Optional)

Only runs if enabled by complexity gate or `--val-review` flag. Reviews
validation evidence — outcome is `"converged"` if validation passes
critique, `"not_converged"` otherwise.

Dispatch protocol (3 steps):

1. Build kwargs:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" build-dispatch \
     --phase VAL_REVIEW --change-id <change-id>
   ```

2. Call `Agent(prompt=<dispatch.prompt>, model=<dispatch.model>,
   isolation=<dispatch.isolation>)`. Treat `prompt` as opaque. Parse
   the agent's last message for `(outcome, handoff_id)`.

3. Apply the outcome:
   ```bash
   python3 "<skill-base-dir>/scripts/runner.py" apply-outcome \
     --change-id <change-id> --phase VAL_REVIEW \
     --outcome <outcome> --handoff-id <handoff_id>
   ```

**Fallback**: If `archetype: null` OR the dispatch adapter is unavailable, run the
inline path — invoke the convergence loop with `review_type="implementation"`
and `fix_mode="targeted"`, scoped to the validation evidence. Then run
`apply-outcome` to record `phase_archetype = null`.

### 8. SUBMIT_PR Phase

**Record SUBMIT_PR phase archetype** (state-only resolver — D9). Before
running `gh pr create`, populate `phase_archetype` for SUBMIT_PR so the
PR-creation phase is visible in observability dashboards alongside the
dispatching phases:

```bash
python3 "<skill-base-dir>/scripts/runner.py" record-state-only-archetype \
  --change-id <change-id> --phase SUBMIT_PR
```

Failure here is non-fatal (writes `phase_archetype = null` and continues).

Create a pull request with full evidence trail:

```bash
gh pr create --title "feat(<change-id>): <summary from proposal>" --body "$(cat <<'EOF'
## Summary
[From proposal.md]

## Evidence Trail
- Plan reviews: X rounds, Y vendors, Z blocking findings resolved
- Implementation: N packages (strategy per package)
- Impl reviews: X rounds, Y vendors, Z blocking findings resolved
- Validation: passed/failed (test counts)
- Validation review: skipped | X rounds
- Total convergence rounds: N
- Total duration: Xm Ys

## Convergence Report
See loop-state.json for full state history.

Generated by /autopilot — awaiting human approval for merge.
EOF
)"
```

### 9. DONE Phase

Write final strategic memory summarizing:
- Total rounds across all phases
- Vendor effectiveness (findings raised, confirmed, fixes authored per vendor)
- Convergence pattern (fast/slow/stalled)
- Implementation strategies used per package

Write final handoff document.

**STOP — Await human approval for merge via `/cleanup-feature <change-id>`.**

Before presenting merge-approval questions, automatically invoke `/review-artifacts <change-id>` so the reviewer has the relevant artifacts open prior to choosing gate outcomes.

## Progress Reporting

At each state transition, report:
```
[autopilot] Phase: PLAN_ITERATE → PLAN_REVIEW (self-review complete, 3 findings fixed)
[autopilot] Phase: PLAN_REVIEW → IMPLEMENT (converged in 2 rounds)
[autopilot] Finding trend: [8, 2, 0]
[autopilot] Vendor participation: claude ✓, codex ✓, gemini ✗
[autopilot] CLI review: enabled | disabled (--no-review or no vendor CLIs)
```

## Per-Phase Archetype Resolution

Each non-terminal phase resolves an archetype (e.g. `architect`, `implementer`,
`reviewer`, `analyst`, `runner`) before the sub-agent dispatches. The resolved
archetype determines both the logical model tier (`premium`/`standard`/
`economy`, with legacy Claude aliases still accepted for Claude Code) and the
system prompt the sub-agent runs with. Provider-specific model mapping lives
coordinator-side at `agent-coordinator/archetypes.yaml` under `model_aliases`;
phase-to-archetype mapping lives under `phase_mapping`.

**Default mapping** (per design D11; tunable in `archetypes.yaml`):

| Phases | Archetype | Default tier |
|---|---|---|
| `PLAN`, `PLAN_ITERATE`, `PLAN_FIX` | `architect` | premium |
| `PLAN_REVIEW`, `IMPL_REVIEW`, `VAL_REVIEW` | `reviewer` | premium |
| `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_FIX` | `implementer` | standard (escalates to premium on size signals) |
| `VALIDATE`, `VAL_FIX` | `analyst` | standard |
| `GATEKEEPER` | `gatekeeper` | premium |
| `INIT`, `SUBMIT_PR` | `runner` | economy |

**Operator override** — force a specific model for one or more phases via the
`AUTOPILOT_PHASE_MODEL_OVERRIDE` env var. Format:
`<PHASE>=<model>[,<PHASE>=<model>]*`. Example:

```bash
export AUTOPILOT_PHASE_MODEL_OVERRIDE="PLAN=gpt-5.5,IMPL_REVIEW=gpt-5.4,VALIDATE=gpt-5.4-mini"
```

Override sets `options["model"]` only; the `system_prompt` is left to the
provider adapter default to keep override behavior predictable. Unknown phase
names are warned and ignored; unknown model names pass through to the selected
provider adapter for validation.

**Failure mode** — if the coordinator endpoint is unreachable or returns an
error, the bridge logs a structured warning and the phase dispatches with the
provider adapter or inline fallback default model. `LoopState.phase_archetype`
is recorded as `null` for such phases so observability dashboards can flag
default-fallback runs.

**Observability** — `LoopState.phase_archetype` (schema_version=3) is
persisted in `loop-state.json` and (when wired) emitted in
`POST /status/report` payloads alongside the `phase` field.

See `docs/autopilot-phase-archetype-resolution.md` for the full operator guide.

## Output

- `openspec/changes/<change-id>/loop-state.json` — Full loop state (resumable)
- `openspec/changes/<change-id>/reviews/round-N/` — Per-round CLI-dispatched review artifacts (PLAN_REVIEW, IMPL_REVIEW, VAL_REVIEW)
- `openspec/changes/<change-id>/.review-cache/round-N/` — Per-round in-process `converge()` checkpoints (durability path)
- Pull request with evidence trail
- Coordinator memory entries (episodic)
- Coordinator handoff documents

## Next Step

After human approval:
```
/cleanup-feature <change-id>
```
