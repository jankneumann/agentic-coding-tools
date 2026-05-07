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
- `--force` — Bypass complexity gate thresholds
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

Run the complexity gate:
```python
from complexity_gate import assess_complexity
result = assess_complexity(work_packages_path, proposal_path, force=<--force flag>)
```

- If `result.allowed == False`: report warnings and stop (suggest `--force`)
- If `result.val_review_enabled`: record in loop state
- If `result.warnings`: report them but continue
- If `result.checkpoints`: log injected checkpoints

### 2. PLAN Phase

If argument was a description (no existing change-id):
- Invoke `/plan-feature <description>` (tier auto-detected based on coordinator availability)
- Wait for proposal approval before continuing

If argument was an existing change-id:
- Verify proposal artifacts exist (proposal.md, design.md, specs/, tasks.md)
- Skip to PLAN_REVIEW

### Per-Phase Sub-Agent Dispatch Protocol

The following 7 phases (PLAN_ITERATE, PLAN_REVIEW, IMPLEMENT, IMPL_ITERATE,
IMPL_REVIEW, VALIDATE, VAL_REVIEW) dispatch to a sub-agent via the harness
`Agent(...)` tool. Each block follows the same 3-step protocol:

1. **Build dispatch kwargs** by shelling out to `runner.py build-dispatch`.
   The runner queries the coordinator for the resolved archetype, builds
   the per-phase prompt scaffold, folds `system_prompt` into `prompt`
   with the literal separator `\n\n---\n\n`, and writes a per-run
   resolution cache. JSON output: `{prompt, model, system_prompt,
   isolation, archetype}`.
2. **Invoke the harness `Agent(...)` tool** with the JSON values.
   **Treat `prompt` as opaque — do not concatenate, do not prepend, do
   not split on the separator.** SKILL.md never folds; folding lives
   inside `build_phase_dispatch_kwargs` (single source of truth).
3. **Apply the outcome** by shelling out to `runner.py apply-outcome`,
   passing the `(outcome, handoff_id)` returned by the sub-agent. This
   updates `loop-state.json` (`last_handoff_id`, `handoff_ids`,
   `phase_archetype`) and consumes the cache file.

**Fallback (D5)**: If `runner.py build-dispatch` returns `archetype: null`
(coordinator unreachable or fallback), OR if the harness `Agent(...)`
tool is not exposed in the current orchestrator session, the dispatch
block falls through to the inline-prose path (the slash-command
invocation), and `apply-outcome` records `phase_archetype = null`.

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

2. Call the harness `Agent(...)` tool with those values, treating `prompt`
   as opaque (no concatenation):
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

**Fallback**: If step 1 returned `archetype: null` OR `Agent(...)` is
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

**Fallback**: If `archetype: null` OR `Agent(...)` unavailable, run the
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

### 4. IMPLEMENT Phase

Implement the next slice of work per `tasks.md`. The IMPLEMENT phase is
the only phase that runs with `isolation="worktree"` — sub-agent commits
land on a sibling worktree branch and merge back at completion.

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

**Fallback**: If `archetype: null` OR `Agent(...)` unavailable, run the
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

**Fallback**: If `archetype: null` OR `Agent(...)` unavailable, run the
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

**Fallback**: If `archetype: null` OR `Agent(...)` unavailable, run the
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

**Fallback**: If `archetype: null` OR `Agent(...)` unavailable, run the
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

**Fallback**: If `archetype: null` OR `Agent(...)` unavailable, run the
inline path — invoke the convergence loop with `review_type="implementation"`
and `fix_mode="targeted"`, scoped to the validation evidence. Then run
`apply-outcome` to record `phase_archetype = null`.

### 8. SUBMIT_PR Phase

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
archetype determines both the model (`opus`/`sonnet`/`haiku`) and the system
prompt the sub-agent runs with. Mapping lives coordinator-side at
`agent-coordinator/archetypes.yaml` under `phase_mapping`.

**Default mapping** (per design D11; tunable in `archetypes.yaml`):

| Phases | Archetype | Default model |
|---|---|---|
| `PLAN`, `PLAN_ITERATE`, `PLAN_FIX` | `architect` | opus |
| `PLAN_REVIEW`, `IMPL_REVIEW`, `VAL_REVIEW` | `reviewer` | opus |
| `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_FIX` | `implementer` | sonnet (escalates to opus on size signals) |
| `VALIDATE`, `VAL_FIX` | `analyst` | sonnet |
| `INIT`, `SUBMIT_PR` | `runner` | haiku |

**Operator override** — force a specific model for one or more phases via the
`AUTOPILOT_PHASE_MODEL_OVERRIDE` env var. Format:
`<PHASE>=<model>[,<PHASE>=<model>]*`. Example:

```bash
export AUTOPILOT_PHASE_MODEL_OVERRIDE="PLAN=opus,IMPL_REVIEW=sonnet,VALIDATE=haiku"
```

Override sets `options["model"]` only; the `system_prompt` is left to the
harness default to keep override behavior predictable. Unknown phase names
are warned and ignored; unknown model names pass through (validated by the
harness).

**Failure mode** — if the coordinator endpoint is unreachable or returns an
error, the bridge logs a structured warning and the phase dispatches with the
harness default model. `LoopState.phase_archetype` is recorded as `null` for
such phases so observability dashboards can flag default-fallback runs.

**Observability** — `LoopState.phase_archetype` (schema_version=3) is
persisted in `loop-state.json` and (when wired) emitted in
`POST /status/report` payloads alongside the `phase` field.

See `docs/autopilot-phase-archetype-resolution.md` for the full operator guide.

## Output

- `openspec/changes/<change-id>/loop-state.json` — Full loop state (resumable)
- `openspec/changes/<change-id>/reviews/round-N/` — Per-round review artifacts
- Pull request with evidence trail
- Coordinator memory entries (episodic)
- Coordinator handoff documents

## Next Step

After human approval:
```
/cleanup-feature <change-id>
```
