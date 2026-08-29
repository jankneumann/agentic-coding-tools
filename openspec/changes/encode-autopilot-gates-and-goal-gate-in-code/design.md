# Design — encode autopilot gates and goal gate in code

## Context

ri-04 shipped the posture contract (`skills/shared/trust_posture.py`), ri-05 shipped the
interviewer (`skills/shared/approval_gate.py`), and neither has a consumer. `autopilot.py`
runs to terminal states with every human gate living as prose in `SKILL.md`. This change is
the wiring ri-05's learning log promised: call sites, a console path so interactive runs do
not regress, a structural goal gate at DONE, and the first real producer/consumer of
`replan_required`. Approach 1 (Gate 1) — thin call sites, no new phases.

## D1 — One `GateEvaluator` seam, injected, defaulting to `build_default_gate()`

**Decision.** `run_loop(..., gate_evaluator: GateEvaluator | None = None)`. `GateEvaluator`
is a `Protocol` with `evaluate(gate, context) -> ApprovalDecision`. When `None`, the loop
lazily builds `approval_gate.build_default_gate(agent_id=..., repo_root=...)` on first use.
`runner.py` passes nothing (default), tests pass a `FakeGateEvaluator` scripted per gate.

**Why.** The existing loop already injects every side effect (`dispatch_fn`,
`submit_pr_fn`, `memory_fn`, `status_fn`, `gate_check_fn`); gates follow the same shape, so
`test_autopilot.py`'s ~60 tests keep running without a coordinator. Lazy default keeps
`autopilot.py` importable when `coordination_bridge` is absent (the runner already tolerates
that for handoffs).

**Rejected**: module-level global evaluator. Hidden state across `run_loop` calls breaks the
resume tests that construct two loops in one process.

## D2 — Each gate has exactly one call site, inside the handler that owns its context

| Gate | Site | Context threaded |
|---|---|---|
| `gatekeeper_escalation` | `_phase_gatekeeper`, on verdict `escalate` | `gate_verdict`, `gate_signals` summary |
| `proposal_approval` | `_phase_plan`, after `exists`/`created` | proposal path, approach name |
| `plan_review_convergence_failure` | `_run_phase` when PLAN_REVIEW yields `max_iter` or PLAN_FIX yields `stuck` | convergence reason, round count |
| `validation_failure` | `_run_phase` when VALIDATE yields `failed` or VAL_FIX yields `stuck` | failing report section |
| `escalate_resume` | `_phase_escalate` | `escalation_reason`, `previous_phase` |
| `pr_creation` | `_phase_submit_pr`, before `submit_pr_fn` | branch, change-id |
| `merge` | `_phase_submit_pr`, after `submit_pr_fn` returns `created` | PR URL |
| `replan_required` | `autopilot-roadmap/orchestrator.py`, after `fail_item` | failed item, dependents |

**Why one site each.** The acceptance grep ("no gate whose only enforcement is prose") is
verifiable only if a test can enumerate `Gate` and find one `evaluate(Gate.X` per member.
`test_gate_call_sites.py` asserts exactly that structurally (AST over `autopilot.py` +
`orchestrator.py`), so a ninth gate added to the enum without a site fails CI.

**Why in handlers, not in `transition()`.** `transition()` is pure `(state, outcome) -> str`
and `test_phase_transitions.py` guards that it is the single centralised table. Gate context
(PR URL, proposal path) exists only inside the handler. Approach 3 was rejected for this.

**Semantics of PROCEED/BLOCKED per gate.** The escalation-flavoured gates
(`gatekeeper_escalation`, `plan_review_convergence_failure`, `validation_failure`) wrap an
edge that already exists; PROCEED takes the existing edge (ESCALATE / VAL_FIX), BLOCKED means
"a human wants to look before we even escalate" and surfaces `gate_pending`. `merge` PROCEED
records `{"merge_authorized": true, "pr_url": ...}` in `LoopState.goal_gate.evidence` and
transitions to DONE; it never calls `gh pr merge` — ri-12 owns headless merge, and
`/cleanup-feature` remains the merge executor.

## D3 — `gate_pending` is an outcome, not a phase; the console ask lives in the host

**Decision.** A BLOCKED decision with `resolution=posture_block` under the host-assisted
path sets `LoopState.pending_gate = GateRequest(...)` and makes the handler return the
outcome `gate_pending`. `_run_phase` treats `gate_pending` like `None` (stay in phase, save,
return to caller) — the same mechanism ESCALATE uses to park — **but** the loop reports
`status: gate_pending, gate: <name>` instead of `escalated`, and `runner.py` exposes:

```
runner.py gate-check  <change-id>                      # prints GateRequest JSON; exit 0 pending / 3 none
runner.py gate-answer <change-id> --gate G --decision approved|rejected [--note TEXT]
```

`gate-answer` appends a decision record with `resolution=console_approved|console_rejected`,
clears `pending_gate`, and re-runs the edge: approved → the target transition; rejected →
`enter_escalate(reason=f"{gate}: rejected — {note}")`.

**Why this is "enforced in code".** The loop cannot advance while `pending_gate` is set:
`_apply_transition` refuses (D6), `apply-outcome` refuses, and `run_loop` on re-entry
reports the pending gate and returns. The *ask* is host-executed because the host-assisted
invariant forbids autopilot scripts from talking to an LLM or a TTY-driving UI; the
*enforcement* is that no phase moves without a recorded `ApprovalDecision`.

**Why `posture_block` only.** `notify_with_timeout` already blocks synchronously inside
`ApprovalGate._notify` (polling with the injected clock); its BLOCKED resolutions
(`timeout_default_block`, `rejected`, `coordinator_unreachable`) mean a human was consulted
or could not be — the loop parks as ESCALATE does today. Only `posture_block` means "nobody
was asked yet", which is the interactive case.

**Rejected**: TTY detection (`sys.stdin.isatty()`). Cloud harnesses and `claude -p` runs
have no TTY but do have a host that can ask; the runner path is the reliable signal.

## D4 — The two console resolutions are added to `approval_gate.Resolution`

**Decision.** `Resolution.CONSOLE_APPROVED = "console_approved"` (a PROCEED resolution) and
`Resolution.CONSOLE_REJECTED = "console_rejected"` are added to `skills/shared/approval_gate.py`,
with `_PROCEED_RESOLUTIONS` extended. `to_audit_record()` is unchanged.

**Why.** Audit records must stay one shape whether the decision came from the coordinator or
the console; a second record type would give the supervisor (supervisor roadmap ri-04, ri-06)
two things to parse. `ApprovalGate.evaluate()` never *returns* a console resolution — only
`gate-answer` constructs one — so the four tested disposition paths are untouched.

## D5 — Goal gate is a pure function over two pieces of evidence

**Decision.** `skills/autopilot/scripts/goal_gate.py`:

```python
@dataclass(frozen=True)
class GoalGateVerdict:
    verdict: Literal["passed", "refused", "abandoned"]
    reason: str
    evidence: dict[str, Any]

def check_goal_gate(state: LoopState, change_dir: Path, *, now: Callable[[], datetime] = ...) -> GoalGateVerdict
```

Condition (a): `gate_logic.check_phase_status(report, section) == "pass"` for every
section returned by `gate_logic.resolve_required_phases(config_path, ...)` — the same call
`gate_logic.pre_merge_gate` makes, so the goal gate and `/cleanup-feature` cannot disagree — plus the Validation Review section when
`state.val_review_enabled`. Condition (b): the latest `phase_history` entry with
`phase == "VALIDATE"` has `outcome == "passed"` and `at >= mtime(validation-report.md)`.

**Why both.** The report is the durable artifact (`validate-feature-ephemeral`: only durable
artifacts survive) and is what `/cleanup-feature` already gates on; but a report can be
left over from a previous run of the same change. The `phase_history` entry is written by
`apply_phase_outcome` in *this* run; requiring it to postdate the report proves the report
belongs to this run's VALIDATE. `phase_history` alone (option B in discovery) trusts the
sub-agent's self-report; a `PhaseRecord.status` field (option C) is a cross-skill schema
change the supervisor-record work may still want, but it is not needed to make DONE
structurally gated.

**Why mtime, not git.** `validate-feature` writes the report inside an ephemeral worktree
and copies it back; the copy's mtime is the moment it became visible to this loop, which is
the comparison that matters. A git timestamp would require the report to be committed first.

## D6 — `_apply_transition` is the single enforcement point for DONE and for pending gates

**Decision.** `_apply_transition(state, outcome, status_fn)` gains two checks before
mutating `current_phase`: (1) if `state.pending_gate` is set → raise `GatePending`; (2) if
the resolved target is `DONE` and the edge is not `ESCALATE/abandoned` → run
`check_goal_gate`; on `refused` → raise `GoalGateRefused(reason)`. `run_loop` catches
`GoalGateRefused` and calls `enter_escalate(state, f"goal gate refused: {reason}")`, so
refusal is observable as an ESCALATE with a named reason, never a silent stop.
`ESCALATE/abandoned` records `goal_gate={"verdict": "abandoned"}` and proceeds.

**Why here.** Every path into DONE — `run_loop`, `runner.py apply-outcome`, a hand-edited
`current_phase` — goes through `_apply_transition`. Putting the check in `_phase_submit_pr`
would leave `apply-outcome` unguarded, and `apply_phase_outcome` in `phase_agent.py` must
call `_apply_transition` rather than assigning `current_phase` directly (it already
delegates; this change asserts it with a test).

## D7 — Loop state v5

`LoopState.schema_version = 5` adds `gate_decisions: list[dict]`, `pending_gate: dict | None`,
`goal_gate: dict | None`. `load_state` supplies defaults for missing fields, as it did for
v2→v4. `apply_outcome_or_escalate` operates on the raw dict and must copy the three new keys
through (test: `test_apply_outcome_contract` gains a v5 case).

## D8 — `replan_required` is produced only on an explicit signal, consumed through a file

**Decision.** `fail_item(..., *, replan: bool = False)`; the orchestrator passes
`replan=bool(outcome.get("replan"))` from the item's result payload. After `fail_item`, the
orchestrator collects items now in `replan_required`, evaluates `Gate.REPLAN_REQUIRED` once
per failure (not per dependent), and on PROCEED writes `<workspace>/replan-request.json`
(contract: `replan-request.schema.json`) and returns summary status `replan_requested`. The
host reads the summary and runs `/plan-roadmap --replan <roadmap-id>`.

`decomposer.py replan-scope <workspace>` is the deterministic half of replan mode: it prints
the affected subgraph (every `replan_required` item + transitive non-completed dependents).
The LLM half (re-decomposing that subgraph against the source proposal and the failed item's
learning entry) is host-executed per `plan-roadmap/SKILL.md`. Replan mode ends by setting the
re-decomposed items to `approved`, deleting the request file, and running
`decomposer.py validate`.

**Why explicit signal.** The roadmap-orchestration spec's "blocked if hard, replan_required
if workaround-able" needs a classifier nobody has designed; ri-06's acceptance needs only
that the status, once present, is acted on. An explicit `replan: true` in the failure
payload keeps the classification with the agent that saw the failure. The spec text is
amended to say so rather than leaving a promise the code does not keep.

**Why a file, not a coordinator issue.** The host-assisted invariant test forbids network in
`autopilot-roadmap/scripts/`; the workspace is already the durable handoff medium
(`checkpoint.json`, `learnings/`). `coordination-bridge` may mirror it later.

## D9 — SKILL.md is de-prosed and a test keeps it that way

The four prose gates in `skills/autopilot/SKILL.md` become one protocol block each:

```
python3 <skill-base-dir>/scripts/runner.py gate-check <change-id>
# exit 0 → ask the operator the printed `prompt` (AskUserQuestion), then:
python3 <skill-base-dir>/scripts/runner.py gate-answer <change-id> --gate <gate> --decision <approved|rejected>
```

`test_prose_free_gates.py` asserts: every `Gate` value that appears in `SKILL.md` appears
inside a `gate-check`/`gate-answer` fenced block; none of the three retired phrases appears;
the VALIDATE outcomes documented equal `TRANSITIONS["VALIDATE"].keys()`. `install.sh`
resyncs the mirrors; the mirror-drift CI gate (in-flight change) will enforce that going
forward, and the integration package runs `install.sh` explicitly until it does.

## Sequencing against in-flight changes

- `fix-autopilot-archetype-and-apply-outcome` (54/59): D6 honours "orchestrator is the only
  actor that transitions `current_phase`" — `gate-answer` calls `_apply_transition`.
- `fix-compact-hook-phase-boundary-detection` (22/25): `last_handoff_id` is still written by
  `apply-outcome` at phase boundaries; `gate_pending` does not fire a handoff (no boundary was
  crossed), so the compact hook's assumption holds.
- `collapse-mechanical-preamble-session-start`: edits `SKILL.md` §0; `wp-skill-docs` edits
  §2, §8, §9 and the resume block in §0 — rebase the later one; no semantic overlap.

## Task sizing notes

No task is L or XL. The two M tasks (2.5/2.6 the eight call sites; 3.6 replan-scope +
`--replan` parsing) were considered for splitting: 2.5/2.6 split by gate would produce eight
XS tasks that each touch the same `_run_phase` dispatcher and would conflict inside one
package, so they stay one M with a checkpoint after; 3.6 stays M because the flag parsing is
ten lines and the scope walk is the real work.
