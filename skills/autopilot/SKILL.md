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
2. `/parallel-review-plan` (single pass, no convergence loop)
3. `/implement-feature`
4. `/validate-feature`
5. Create PR manually

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

### 3. PLAN_REVIEW Phase (Convergence Loop)

Invoke the convergence loop with `fix_mode="inline"`:

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

**If converged**: Report findings summary, transition to IMPLEMENT.
**If not converged**: Report reason (max_rounds, stalled, quorum_lost, disagreement), transition to ESCALATE.

For **inline plan fixes** (PLAN_FIX): Read the blocking findings, edit the relevant plan files directly (proposal.md, design.md, specs, work-packages.yaml), re-validate with `openspec validate`.

### 4. IMPLEMENT Phase

Invoke implementation using existing skills:
- Invoke `/implement-feature <change-id>` (tier auto-detected based on coordinator + work-packages.yaml)

Record `package_authors` from the implementation results (which vendor implemented each package).

### 5. IMPL_REVIEW Phase (Convergence Loop)

Invoke the convergence loop with `fix_mode="targeted"`:

For **targeted implementation fixes** (IMPL_FIX): Look up the lead vendor from `package_authors`, use `CliVendorAdapter.dispatch()` directly to send the fix to that specific vendor, scoped to the package's `write_allow` paths.

### 6. VALIDATE Phase

Invoke validation:
- Invoke `/validate-feature <change-id>` (tier auto-detected)

**If passed**: Check `val_review_enabled` — if true, go to VAL_REVIEW; otherwise skip to SUBMIT_PR.
**If failed**: Transition to VAL_FIX.

### 7. VAL_REVIEW Phase (Optional)

Only runs if enabled by complexity gate or `--val-review` flag. Same convergence loop pattern as PLAN_REVIEW but reviewing validation evidence.

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
[autopilot] Phase: PLAN_REVIEW → IMPLEMENT (converged in 2 rounds)
[autopilot] Finding trend: [8, 2, 0]
[autopilot] Vendor participation: claude ✓, codex ✓, gemini ✗
```

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
