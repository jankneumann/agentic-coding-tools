# Design: Run the GATEKEEPER as a scored decision in shadow mode

> Change ID: `run-the-gatekeeper-as-a-scored-decision-in-shadow-mode`
> Roadmap item: `ri-06` of `roadmap-jev-system-one-integration-assessment`

## Context

`skills/autopilot/scripts/autopilot.py::_phase_gatekeeper` is the autopilot loop's
entry judgment. It calls the injected `gatekeeper_fn(state) -> str | None` — today
that callback dispatches a premium-tier sub-agent whose task text (see
`phase_agent.py::_PHASE_TASKS["GATEKEEPER"]`) asks it to free-text judge
`state.gate_signals` and return one of `proceed` / `proceed_with_review` /
`escalate`. When `gatekeeper_fn` is `None`, or returns anything outside those
three literals, `_phase_gatekeeper` falls back to `_default_gate_verdict` — a
pure function of `state.gate_signals` that never escalates — and records a
`DEGRADED` `phase_history` entry via `record_degraded` so the fail-open path is
never mistaken for an actual judgment (`introduce-fitness-function-gates`,
D6).

`state.gate_signals` is populated once, at `_phase_init`, from
`complexity_gate.gather_signals()`. Confirmed by reading two real recorded
`loop-state.json` files (grounding, not aspiration):

- `openspec/changes/add-visual-code-explainer/loop-state.json`:
  `{"external_dep_count": 0, "has_broad_write_scope": false,
  "has_db_migration": false, "has_proposal": true, "has_security_signal": false,
  "has_specs": true, "has_tasks": true, "has_work_packages": true,
  "package_count": 2, "total_loc_estimate": 850}`, `gate_verdict: null` (this
  run had not yet reached a recorded verdict when snapshotted).
- `openspec/changes/archive/2026-09-13-fix-audit-choices-range-ledger-path/loop-state.json`:
  same shape with `"has_db_migration": true`, `gate_verdict: "proceed_with_review"`
  — matching `_default_gate_verdict`'s rule exactly (a risk signal present ->
  `proceed_with_review`, never `escalate`).

Both are used verbatim as the fixture-replay test's recorded `gate_signals` in
Non-goals-respecting task 3.1 below — no synthetic signal profile is invented.

`_run_phase` already resolves `change_dir` for `_phase_init`/`_phase_plan`, but
`_phase_gatekeeper` is called without it (`_run_phase(...)`:
`_phase_gatekeeper(state, gatekeeper_fn, gates)`). This item threads `change_dir`
through, since the shadow judge's state payload needs `proposal.md`, `tasks.md`,
and a `work-packages.yaml` summary that only `change_dir` can resolve.

## Real API surface (grounding, not aspiration)

`system_one_decisions.decide(state, questions, *, site, event_sink=None,
dry_run=False)` is already established by `ri-01`–`ri-05`; this item is the
first to use the `Score` primitive rather than `Noul` alone. Confirmed by
reading the installed `typesafe_sdk` (`typesafe_sdk._schemas.models`):

- `ScoreQuestion.criteria` is "Ordered descriptions of the score levels. Each
  description's position determines its score, starting at zero" — a 4-level
  score is `criteria=[level0_desc, level1_desc, level2_desc, level3_desc]`.
- `ScoreAnswer` carries `.score` (float — "the probability-weighted average of
  the rubric levels; may fall between integer levels"), `.confidence`,
  `.legend` (the criteria, echoed back), and `.probabilities` (per-level
  probability dict).
- `ChoiceAnswer` carries `.choice` (the selected criterion name), `.confidence`,
  `.probabilities`.
- Both accept the plain-dict wire form
  (`{"type": "score", "instructions": "...", "criteria": [...]}` /
  `{"type": "choice", "instructions": "...", "criteria": {...}}`), so this
  item imports no `typesafe_sdk` type, satisfying
  `test_no_sdk_import_outside_package.py` exactly as `ri-04`/`ri-05` did.

`decide()` is synchronous, and every call site in `autopilot.py` is
synchronous (`_phase_gatekeeper` is a plain function, not a coroutine) — no
`asyncio.to_thread` is needed, matching `ri-05`'s D-grounding for
`consensus_synthesizer.py`.

## Decisions

### D1 — The shadow call lives inside `_phase_gatekeeper`, strictly additive

After `_phase_gatekeeper` computes `outcome` (from `gatekeeper_fn` or the
permissive fallback — unchanged), and before `return outcome`, it calls a new
helper `_shadow_gatekeeper_judgment(state, change_dir, acting_verdict=outcome)`.
That helper:

1. Builds `state_payload` from `state.gate_signals`, `proposal.md`'s and
   `tasks.md`'s text (when present under `change_dir`), and
   `_work_packages_summary(change_dir)` (D6).
2. Calls `system_one_decisions.decide(state_payload, questions, site="autopilot.gatekeeper_shadow")`
   with three questions: `Score(verifiability, 4 levels)`, `Score(risk, 4
   levels)`, `Choice(verdict, {proceed, proceed_with_review, escalate})` (D2).
3. On `None` (any of `decide()`'s four unavailability branches — module not
   installed, no API key, over budget, `TypeSafeError`) or a malformed answer
   set (missing key, non-numeric score), returns without appending anything.
   No shadow entry is better than a fabricated one — mirrors `ri-05` D3's
   "unavailable -> skip, don't fabricate."
4. Otherwise computes a **code-computed candidate verdict** from the two
   `Score` answers against configured thresholds (D3), and appends one
   `phase_history` entry (D4) carrying the candidate verdict, the `Choice`
   answer as a cross-check only, both score distributions, and the
   already-decided `acting_verdict` — all without touching `outcome`,
   `state.gate_verdict`, `state.val_review_enabled`, or any gate evaluation.

`_phase_gatekeeper`'s existing control flow (the `gates.evaluate(Gate.GATEKEEPER_ESCALATION, ...)`
branch, `enter_escalate`, `record_degraded`) is untouched — the shadow call is
inserted as one line, reading `state` and `change_dir` and writing only a new
`phase_history` entry.

**Revised after Codex review (PR #591, P1 and P2):**

- **P1 (real gap) — the shadow call must not live only in `_phase_gatekeeper`.**
  Codex read `skills/autopilot/SKILL.md`'s own Step 1.5 and found that the
  real, host-driven GATEKEEPER dispatch protocol never calls
  `_run_phase`/`_phase_gatekeeper` at all: it shells out to `runner.py
  build-dispatch` (to build the sub-agent prompt), dispatches the sub-agent
  itself via the harness's own `Agent(...)` call, then records the result
  with `runner.py apply-outcome` → `phase_agent.apply_phase_outcome`. That
  function works on a raw state *dict*, not a `LoopState`, and until this
  fix never built a shadow record at all — so every real autopilot run
  would have produced zero `"GATEKEEPER_SHADOW"` entries, leaving `ri-08`'s
  disagreement report with no production data. The fix: `build_shadow_entry`
  is a pure function (`gate_signals: dict, change_dir, *, acting_verdict) ->
  dict | None`) with no `LoopState` dependency at all;
  `shadow_gatekeeper_judgment` (the `_phase_gatekeeper` path) is now a thin
  wrapper over it, and `apply_phase_outcome` calls the same pure function
  directly on its own raw-dict state, appending the result to the same
  `history` list it already builds — before the same `_save_state` call,
  and only on the non-replay path (a retried `apply-outcome` call for the
  same `handoff_id` returns early before reaching the shadow block, so a
  replay costs no extra `decide()` call and produces no duplicate entry).
  `runner.py`'s `_cmd_apply_outcome` now passes `change_dir=_change_dir(args.change_id)`.
- **P2 (real bug) — the escalation gate's BLOCKED early return skipped the
  shadow call.** The first cut placed the shadow call immediately before
  `return outcome`, at the very end of `_phase_gatekeeper`. But the
  `escalate` branch can itself return early, via `gates.park(...)`, when the
  `Gate.GATEKEEPER_ESCALATION` approval gate is BLOCKED (the default when no
  `TRUST_POSTURE.md` exists) — that early return skipped the shadow call
  entirely for every escalated-and-parked run, exactly the runs a
  disagreement report most needs data from. Fixed by moving the shadow call
  to immediately after `state.gate_verdict = outcome` is set, strictly
  before the `proceed_with_review`/`escalate` branching that can return
  early. Regression test:
  `test_shadow_entry_recorded_even_when_escalation_gate_parks`.
- **P2 (real bug) — a malformed sidecar could turn a shadow-config typo into
  a real GATEKEEPER phase exception.** `load_shadow_thresholds` originally
  called `raw.get(...)` and `float(...)` unguarded; a syntactically valid
  sidecar with the wrong shape (`[]`) or a non-numeric field
  (`{"risk_escalate": "high"}`) raised `AttributeError`/`ValueError`
  uncaught, which `_phase_gatekeeper` does not isolate — violating the
  design's own safety property that shadow configuration can never affect
  acting behavior. Fixed by validating `isinstance(raw, dict)` and wrapping
  each field's `float(...)` coercion so any failure degrades to that
  field's default rather than raising.

### D2 — Question shape

```python
questions = {
    "verifiability": {
        "type": "score",
        "instructions": "How verifiable are this change's outcomes from its "
                         "artifacts — can they be objectively checked?",
        "criteria": [
            "Unverifiable: no testable acceptance criteria.",
            "Weakly verifiable: some criteria, but mostly a free-text description.",
            "Verifiable: WHEN/THEN scenarios and a task breakdown exist.",
            "Strongly verifiable: WHEN/THEN scenarios, a task breakdown, and a "
            "work-packages plan all exist and agree.",
        ],
    },
    "risk": {
        "type": "score",
        "instructions": "How risky is this change if a slice of it goes wrong "
                         "-- blast radius and reversibility?",
        "criteria": [
            "Low: narrow write scope, no migration or security signal.",
            "Moderate: broader write scope or one risk signal present.",
            "High: a db migration or security signal, or several external "
            "dependencies.",
            "Critical: multiple risk signals together, or an unbounded write "
            "scope.",
        ],
    },
    "verdict": {
        "type": "choice",
        "instructions": "Given the above, which outcome would you choose?",
        "criteria": {
            "proceed": "Verifiable and low risk enough to automate.",
            "proceed_with_review": "Automate, but schedule the extra "
                                    "validation-review checkpoint.",
            "escalate": "Unverifiable outcomes or unacceptable risk -- stop "
                        "for a human.",
        },
    },
}
```

One `decide()` call per GATEKEEPER run, spanning all three questions — matching
the acceptance outcome's "a shadow record **per gatekeeper run**" (singular).

### D3 — Thresholds read from config, not literals

`skills/autopilot/scripts/gatekeeper_shadow.py` gets
`DEFAULT_RISK_ESCALATE_LEVEL = 2.5`, `DEFAULT_RISK_REVIEW_LEVEL = 1.5`,
`DEFAULT_VERIFIABILITY_ESCALATE_LEVEL = 0.5`,
`DEFAULT_VERIFIABILITY_REVIEW_LEVEL = 1.5` as the default layer, and a
`load_shadow_thresholds() -> ShadowThresholds` function that reads an optional
sidecar `skills/autopilot/scripts/gatekeeper-shadow.json` — the same
default-plus-sidecar shape `review_rules.py` established for
`parallel-infrastructure` (`ri-05` D5), scoped to `autopilot` since no
equivalent config file existed here before. There is deliberately no
project-override layer (a second, repo-root JSON) — nothing in this item's
acceptance outcomes asks for one, and inventing one would be scope creep past
"thresholds read from config."

`compute_candidate_verdict(risk_score: float, verifiability_score: float, thresholds) -> str`
is a pure function:

1. `risk_score >= thresholds.risk_escalate` or
   `verifiability_score <= thresholds.verifiability_escalate` -> `"escalate"`.
2. Else `risk_score >= thresholds.risk_review` or
   `verifiability_score <= thresholds.verifiability_review` -> `"proceed_with_review"`.
3. Else -> `"proceed"`.

This never runs today — it is called only from the shadow path — so choosing
these particular default levels does not change any behavior; they exist to
be *measured* against the acting verdict over the shadow period, and adjusted
before `ri-08` ever considers promoting them.

### D4 — Shadow record shape, reusable by `ri-07`

A new small helper, `record_shadow_judgment`, appends a structured entry to
`state.phase_history` with an envelope both this item and `ri-07`
("Adjudicate phase outcomes in shadow mode" — its own shadow record for a
different phase-transition point) can share:

```python
{
    "phase": "GATEKEEPER_SHADOW",   # never "GATEKEEPER" -- must not be
                                     # matched by goal_gate's exact-phase
                                     # filters or any other phase_history
                                     # consumer that keys on the real phase
    "at": "<iso8601>",
    "kind": "shadow",
    "acting_outcome": acting_verdict,      # what the loop actually did
    "judged_outcome": candidate_verdict,   # code-computed from the two Scores
    "judgment": {
        "verifiability": {"score": ..., "confidence": ..., "probabilities": {...}},
        "risk": {"score": ..., "confidence": ..., "probabilities": {...}},
        "choice_cross_check": {"choice": ..., "confidence": ..., "probabilities": {...}},
    },
}
```

`ri-07` is free to reuse `record_shadow_judgment(state, *, phase, acting_outcome,
judged_outcome, judgment)` with its own `phase` and `judgment` payload shape
(a `Choice(outcome)` + `Noul(evidence)` pair per its own description) — the
envelope's `phase`/`kind`/`acting_outcome`/`judged_outcome` keys are the part
this item commits to for reuse; `judgment`'s inner shape is deliberately
free-form per caller.

Confirmed safe by reading every `phase_history` consumer in the repo
(`goal_gate.py::_latest_validate_entry`, `runner.py::apply_phase_outcome`):
all of them filter by exact `entry["phase"] == "..."` string match, so a
`"GATEKEEPER_SHADOW"` entry is inert to every existing consumer.

### D5 — `_work_packages_summary`: a summary, not a raw dump

The acceptance outcome says "the work-packages **summary**," not "the
work-packages file." `_work_packages_summary(change_dir) -> dict | None`
reads `work-packages.yaml` when present and returns
`{"package_count": N, "package_ids": [...], "has_dependencies": bool}` —
mirroring `complexity_gate.gather_signals()`'s own philosophy of handing the
judge a compact profile rather than a raw file dump. `decide()` already
enforces its own 32K-token budget and returns `None` over budget (unavailable
branch 3) — no separate truncation logic is needed for `proposal.md`/
`tasks.md`'s raw text; a payload that is too large simply degrades to "no
shadow entry this run," identically to every other unavailability branch.

### D6 — `change_dir` threading

`_run_phase`'s `GATEKEEPER` dispatch line changes from
`_phase_gatekeeper(state, gatekeeper_fn, gates)` to
`_phase_gatekeeper(state, gatekeeper_fn, gates, change_dir=change_dir)`.
`change_dir` is already a required parameter of `_run_phase` (used by
`_phase_init`/`_phase_plan`), so this is a plumbing-only change with no new
parameter at the `_run_phase`/`run_loop` boundary. The direct-helper unit
tests (`test_gatekeeper_degraded.py`) that call `_phase_gatekeeper(state, fn)`
positionally continue to work unmodified because `change_dir` defaults to
`None` (shadow judgment is skipped entirely when `change_dir` is `None`,
which also covers every existing call site that never had a change dir to
give).

### D7 — Reporting script

`skills/autopilot/scripts/gatekeeper_shadow_report.py` — a small, fully
deterministic CLI (no LLM calls, satisfying the autopilot host-assisted
invariant test `test_host_assisted_invariant.py`) that accepts one or more
`loop-state.json` paths (or a glob), extracts every
`phase_history` entry with `phase == "GATEKEEPER_SHADOW"`, and prints the
disagreement rate: `count(judged_outcome != acting_outcome) / count(entries)`,
plus a per-outcome-pair breakdown for operator visibility. This is the
reporting surface `ri-08`'s "recorded shadow disagreement rate" acceptance
outcome reads from later.

## Non-goals (out of scope for this item)

- No change to the acting verdict, `state.gate_verdict`, or
  `state.val_review_enabled` from the shadow judgment — `ri-08` is the item
  that flips any of this to act.
- No change to `--force` or the scope-safety floor in `_phase_init` — both are
  covered by existing tests that must keep passing unmodified.
- No retirement of the premium-tier `gatekeeper_fn` dispatch — it keeps
  running exactly as today, in parallel with (not instead of) the shadow
  judge. `ri-08`'s own acceptance outcomes name that retirement explicitly.
- No project-override config layer for the shadow thresholds beyond the one
  default-plus-sidecar file (D3).
- No vindication-attribution logic (which side a later review round agreed
  with) — that is `ri-07`'s acceptance outcome, not this item's.
