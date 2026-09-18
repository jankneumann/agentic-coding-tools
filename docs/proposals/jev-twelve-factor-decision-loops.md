# Jev as the switch in a 12-factor agent loop

**Status**: Design note (2026-09-18). Companion to
[`jev-system-one-integration-assessment.md`](jev-system-one-integration-assessment.md), which
lists call sites. This note is about the *shape* of the loop: how the 12-factor-agents
principles (humanlayer/12-factor-agents) apply to this repo's orchestrators, and where a
System One decision replaces the part of each loop that today is either a hard-coded table or
a frontier model grading its own work.

## The claim in one paragraph

A 12-factor agent is a `while` loop: build a compact state snapshot, ask a model
`determine_next_step(state) -> intent`, `switch` on the intent, run deterministic code for that
branch, append the result to the state, repeat, and `break` when the intent is "ask a human" or
"done." Tool calling in that model is two separable acts: **classification** (which intent) and
**action** (execute it). Today this repo does the action half with LLM sub-agents and the
classification half either with the *same* sub-agent's self-reported outcome string or with a
fixed table. Jev is a model whose entire output space is "which intent, with what probability."
It fits the classification half exactly, is stateless like the reducer, and returns a
distribution rather than a label, which is what lets the `switch` be *smart*: the code can route
by confidence, not just by label. The action half stays where it is. Jev cannot invent tool
parameters, so it should drive the **orchestration** loops, whose menus are small and closed,
and never the inner tool loop of a coding sub-agent, whose arguments are free text.

## This repo already is a 12-factor agent

Before proposing anything, it is worth recording that the autopilot is already built the way
the twelve factors recommend. That is why Jev slots in cleanly rather than requiring a rewrite.

| Factor | Where the repo already does it |
|---|---|
| 4 — Tools are structured outputs | Phase sub-agents return only `(outcome, handoff_id)`; `phase_agent.py` forbids them from touching orchestrator state. Review vendors return schema-validated findings. |
| 5 — Unify execution and business state | `loop-state.json` is authoritative; the coordinator work queue is a projection (`docs/guides/work-queue-truth-projection.md`). |
| 6 — Launch / pause / resume | `--resume` from `loop-state.json` and `checkpoint.json`; `harden-the-resume-contract` is making it a tested contract. |
| 7 — Contact humans with tool calls | `ESCALATE` is a phase, not an exception. `GATE_PENDING` parks the loop. The supervise gate router and the email relay are the human channel. |
| 8 — Own your control flow | `autopilot.TRANSITIONS` is an explicit table; `EscalationHandler` maps each escalation type to "exactly one handling procedure." |
| 9 — Compact errors into context | `handoff_builder` phase records; `review_ledger.compact`; roadmap learning-log compaction at 50 entries. |
| 10 — Small, focused agents | One archetype per phase (`archetypes.yaml`), 3–4 fix rounds max, `converge()` bounded by `max_rounds`. |
| 12 — Stateless reducer | `transition(state, outcome) -> phase` is a pure function; `apply_phase_outcome` is the reducer step. |

What is *not* 12-factor about it is narrower than it looks: **the outcome labels that drive the
switch are produced by the actor, not by a judge of the state.** An implementer sub-agent says
`complete`; a fixer says `fixed` or `stuck`; the GATEKEEPER says `proceed`. Each is a
single-token decision made by the most expensive model in the roster, with no probability
attached, and the reducer trusts it. Where the repo did not want to trust an actor it wrote a
table instead (`EscalationHandler`, `rework_report`'s action precedence, the stall rule
`trend[-1] >= trend[-stall_window]`). Both are the same gap from opposite sides: no calibrated
judge sits between state and switch.

## The primitive: a decision step

One shared helper, proposed in the companion assessment as the installable package
`packages/system-one-decisions` (a package rather than a `skills/shared/` module because the
skills venv, gen-eval, and the coordinator image each install their own dependencies), with one
loop-oriented entry point:

```python
@dataclass(frozen=True)
class Decision:
    intent: str                    # the label the switch runs on
    p: float                       # probability of that label
    distribution: dict[str, float] # every label's probability
    degraded: bool                 # True when the rule fallback produced this
    evidence_class: str = "judgment"

def decide_intent(
    state: dict,                        # compact snapshot, ≤ 32K tokens
    intents: dict[str, str],            # label -> one-sentence description
    *,
    fallback: Callable[[dict], str],    # the rule this replaces
    human_intent: str = "escalate",
    act_floor: float = 0.6,             # below this, route to human_intent
    irreversible: frozenset[str] = frozenset(),
    approve_floor: float = 0.9,         # irreversible intents need this much
    site: str,
) -> Decision:
```

Semantics, in the order the code checks them:

1. `system_one` unavailable, key absent, or state over budget → `fallback(state)`,
   `degraded=True`. The rule you had is the rule you keep.
2. `max(distribution) < act_floor` → `intent = human_intent`. This is factor 7 with a number
   on it: the model did not choose to ask a human, the *code* did, because the model was unsure.
3. `intent in irreversible and p < approve_floor` → return the intent but flag
   `needs_approval=True`. This is factor 8's "interrupt between tool selection and tool
   invocation," applied only where the action cannot be undone.
4. Otherwise return the intent.

Every `Decision` is appended to the loop's event log (`loop-state.json` `phase_history`,
`review-ledger`, or the roadmap checkpoint) with its distribution. That makes three things
free: replay (`build-task-replay-runner` can re-run recorded states through the current model
and diff the decisions), regression (`convert-failure-record-to-regression-scenarios` gets
labelled cases for nothing), and calibration monitoring (compare `p` with realised outcomes,
the same measurement `calibrate-llm-judge-against-human-labels` performs by hand).

Thresholds live in config beside the rule they replace and never in the scoring module, per the
repo's existing convention.

## Where the switch statements are, and what Jev asks at each

### 1. Phase outcome adjudication (factors 4 and 12)

`autopilot.apply_phase_outcome` runs `transition(state, outcome)` on an outcome the sub-agent
chose for itself. Insert a decision step between the sub-agent's return and the reducer:

- **State**: the handoff record, the phase's `expected_outcomes`, the diff stat of the
  worktree, the tail of the test or validation output, the sub-agent's claimed outcome.
- **Questions**: `Choice(outcome, allowed outcomes for this phase)` and
  `Noul("the evidence supports the sub-agent's claimed outcome")`.
- **Switch**: claimed and judged agree with `p ≥ act_floor` → reducer proceeds as today. They
  disagree → the *judged* label wins if `p ≥ approve_floor`, otherwise `escalate` with both
  labels in the evidence. This closes the hole where a fixer says `fixed` and the next review
  round discovers otherwise; today that costs a full review dispatch to find out.

### 2. Review convergence (factor 8)

`convergence_loop.converge` stops on three conditions: zero blocking findings, `max_rounds`, or
the stall rule that the post-compact blocking count did not strictly decrease over a window of 2.
The stall rule fires on a round that fixed three findings and surfaced two new ones; it also
fails to fire when a fixer keeps "addressing" the same finding in ways reviewers keep rejecting.

- **State**: the ledger trend, the last fix diff, the blocking items with their history of
  `mark_addressed` / `reject_out_of_scope_fix`.
- **Questions**: `Noul("another fix round is likely to reduce blocking findings")`,
  and per blocking finding `Choice(disposition, {fix_now, defer_to_followup,
  reject_out_of_scope, needs_human})`.
- **Switch**: `fix_now` items go to `fix_callback`; `defer` and `reject` update the ledger
  through the existing `park_item` / `reject_out_of_scope_fix`; `needs_human` parks a
  disagreement. The round-level `Noul` replaces the stall rule as the *primary* signal, with
  `max_rounds` kept as the hard ceiling. This is the per-finding intent classification the
  fixer tool needs, made before the expensive action instead of discovered after it.

### 3. Escalation handling (factor 8)

`EscalationHandler` maps six escalation types to prescribed actions with "no conversational
decision-making." That was correct when the alternative was a chat model improvising. With a
calibrated `Choice(action, EscalationAction values)` over the escalation summary, impact set,
and attempt history, the prescribed mapping becomes the `fallback` and the floor:
`REQUIRE_HUMAN` stays mandatory wherever the table says so, and Jev may only choose *among*
the recoverable actions for the types the table already treats as recoverable.

### 4. Roadmap item failure (factors 8 and 10)

`orchestrator._handle_failure` records the failure and, when the dispatcher signalled a
replan, asks the gate once. The `replan` boolean itself comes from `_normalize_outcome`. A
decision step over the failure reason, the item's acceptance outcomes, and the attempt history
answers `Choice(next, {retry_same_vendor, retry_other_vendor, skip_item, request_replan,
escalate})`. `request_replan` still goes through the existing `REPLAN_REQUIRED` gate; nothing
here bypasses a human gate, it only decides which one to reach for.

### 5. Merge plan execution (factor 8)

`execute_plan.execute_node` is already a sequence of named gates (`staleness_gate`,
`security_gate`, `live_state_gate`, `delegate_comments`, `vendor_review_gate`). Most are
facts and should stay deterministic. Two are judgments:

- `delegate_comments`: whether unresolved review threads need a code change. Per thread,
  `Choice(thread, {needs_code_change, needs_reply_only, already_addressed, outdated})` over the
  thread text and the current diff of the file it points at.
- `vendor_review_gate`: whether to dispatch multi-vendor review, covered in the companion
  assessment (A4).

### 6. Task routing (factor 1)

`implement-the-task-router-vendor-x-location-x-model` wants deterministic, explainable routing
from a **task routing profile** (duration, scope, interactivity, secret needs, parallelism).
The rules should stay deterministic; that proposal is right. What produces the profile from a
task description today is nothing, or an LLM. Factor 1 is "natural language to structured
data," and that is a Jev call: `Score(duration, [minutes, an hour, a day, longer])`,
`Noul("needs interactive human input")`, `Noul("needs a secret or credential")`,
`Choice(scope, {single_file, package, cross_package, repo_wide})`. The router then switches on
typed fields with rules versioned in `routing.yaml`, exactly as proposed, and the routing
audit event carries the probabilities.

### 7. Human replies as intents (factor 7)

Factor 7 says the human channel is a tool call in both directions. Outbound, `escalate` is
already an intent. Inbound, `relay.parse_reply` classifies a reply by its first word. The
companion assessment flags this as a security item, not a quick win: keep the sender allowlist,
require `distribution["approve"] ≥ 0.97` for approval, treat everything else as `guidance`.

### 8. Error compaction and retry (factor 9)

Factor 9's canonical example counts consecutive errors and escalates after N. `phase_fixer` and
the roadmap dispatcher retry on a count. Two `Noul`s make the count smart:
`"this error is the same failure as the previous attempt"` and `"this error is transient and
retrying without change is likely to succeed"`. Same-and-not-transient → stop retrying now,
not after N. The repo's `failure_type` enum (`scope_violation`, `timeout`, …) is the
`Choice` that compacts the error into the vocabulary the improve-harness pipeline already
mines.

## What Jev must not be asked to do in these loops

- **Emit parameters.** A `Choice` picks a label. Where the switch needs arguments (which files
  to edit, what to write), they must come from the state (a finding's `allowed_paths`, a
  package's scope) or from the LLM action handler. If a branch needs free-form arguments, the
  intent is the branch and the LLM is the action.
- **Drive a coding sub-agent's inner tool loop.** Read / Edit / Bash with arbitrary arguments is
  factor 4 as the harness vendors implement it. Leave it to them.
- **Override a deterministic gate.** Scope-safety floor, `context_eval.verdict`, guardrail blocks,
  Claude Approvals, the human merge gate. A decision step routes *toward* gates; it never
  routes *around* one. Every `Decision` carries `evidence_class: judgment` for this reason.
- **Decide without a fallback.** Every site keeps the rule it replaces as `fallback`, and a
  degraded decision is recorded as `DEGRADED` in the phase history, mirroring
  `autopilot.record_degraded`.

## Order of work

1. Land the `decide_intent` helper with the `fallback`-only path and the event-log write, no
   network. This alone makes every existing rule decision replayable.
2. Phase outcome adjudication (§1) in shadow mode: log the judged outcome next to the claimed
   one for a sprint, do not act on it. Measure disagreement rate and which side was right at the
   next review round.
3. Convergence dispositions (§2), because the per-finding `Choice` removes the most wasted fix
   dispatches.
4. Task-profile extraction (§6) when the task router lands, so the router never needs an LLM.
5. Escalation, roadmap failure, merge threads (§3–5) as independent small changes.

## Sources

- humanlayer/12-factor-agents: README, factor 4 (tools are structured outputs), factor 7
  (contact humans with tool calls), factor 8 (own your control flow), factor 9 (compact errors),
  factor 10 (small focused agents), factor 12 (stateless reducer). Read from GitHub 2026-09-18.
- Jev contract and limits: see the companion assessment's Sources section.
