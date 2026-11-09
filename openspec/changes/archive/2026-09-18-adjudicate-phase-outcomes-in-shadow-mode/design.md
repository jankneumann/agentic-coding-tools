# Design: Adjudicate phase outcomes in shadow mode

> Change ID: `adjudicate-phase-outcomes-in-shadow-mode`
> Roadmap item: `ri-07` of `roadmap-jev-system-one-integration-assessment`

## Context

`skills/autopilot/scripts/phase_agent.py::apply_phase_outcome` is called by
`runner.py apply-outcome` at step 3 of every write-capable phase's dispatch
protocol (`SKILL.md`'s "Per-Phase Sub-Agent Dispatch Protocol"): the sub-agent
returns `(outcome, handoff_id)`, and `apply_phase_outcome` records
`last_handoff_id`/`handoff_ids`/`phase_archetype` and a bare `phase_history`
entry `{"phase", "outcome", "at"}` — **it never checks whether the evidence
supports the claimed outcome.** `transition()` (`autopilot.py`) then moves
`current_phase` purely off that claimed string.

`ri-06` already put a shadow-recording architecture into this exact module,
revised after a real Codex-caught gap: the shadow call must live where
production actually calls it (`apply_phase_outcome`), not only in a
Python-level convenience wrapper (`_phase_gatekeeper`) that the real
`SKILL.md`-driven dispatch protocol never invokes. This item is the second
consumer of that lesson, applied from the start rather than discovered by
review.

## Real API surface (grounding, not aspiration)

- **`expected_outcomes`** already exists:
  `phase_agent._expected_outcomes_for_phase(phase)` returns the allowed
  outcome list per phase (`{"GATEKEEPER": [...], "IMPLEMENT": ["complete",
  "failed"], ...}`), and is the exact same source `build_phase_dispatch_kwargs`
  already puts in `build-dispatch`'s JSON output. `autopilot.TRANSITIONS`
  encodes the same information a second time (pre-existing duplication,
  out of scope to unify here) — this item reads only the `phase_agent.py`
  copy, since that is the one already colocated with `apply_phase_outcome`.
- **The coordinator has no read-by-`handoff_id` lookup.** Confirmed by
  reading `coordination_bridge.try_handoff_read` — it takes `agent_id`/
  `session_id`/`limit`, not a specific id. A specific `PhaseRecord` is
  therefore only reliably readable from the **local-fallback file**
  `openspec/changes/<change-id>/handoffs/<phase-slug>-<n>.json`, written by
  `PhaseRecord._write_local_fallback` only when the coordinator write
  itself failed. `_phase_slug()` is `phase_name.lower().replace(" ", "-")`;
  `apply_phase_outcome`'s own `phase` argument (e.g. `"IMPLEMENT"`) lowers to
  the same slug a sub-agent's own `PhaseRecord(phase_name=phase)` call would
  produce, under the working assumption that a sub-agent's `phase_name`
  matches the driver's `phase` string — the only coupling between the two
  sides today, and already implicit in the existing coordinator path (`D-`
  below spells out the fallback when this assumption doesn't hold).
- **No existing "worktree diff stat" or "test-output tail" capture
  convention.** Confirmed by grep across `skills/autopilot/` and
  `skills/validate-feature/` — this item introduces both, deliberately
  minimal: `git diff --stat` against `.git-worktrees/<change-id>/`'s merge
  base with `main` (the feature-level worktree path convention confirmed in
  `skills/worktree/scripts/worktree.py::_worktree_path`'s own docstring:
  `.git-worktrees/<change-id>/` with no agent suffix, no prefix — the
  orchestrator-level dispatch this call runs at), and the tail of
  `openspec/changes/<change-id>/validation-report.md` when present (the one
  test-output artifact that already exists in this codebase, from the
  VALIDATE phase). Both are best-effort: a missing worktree or missing
  report simply omits that signal, never fabricates one.
- `system_one_decisions.decide()`'s `Score`/`Choice`/`Noul` plain-dict wire
  form, the guarded-import stubbing rule, and the synchronous call site are
  all already established by `ri-01`–`ri-06`; no new API surface to confirm.

## Decisions

### D1 — The adjudication call lives inside `apply_phase_outcome`, on the real production path

Mirroring `ri-06`'s Codex-revised architecture exactly (applied here from the
start): `build_outcome_adjudication_entry(*, phase, claimed_outcome,
expected_outcomes, handoff_record, diff_stat, test_output_tail) -> dict |
None` is a pure function with no `LoopState` dependency, living in a new
sibling module `phase_outcome_shadow.py`. `apply_phase_outcome` calls it on
the non-replay path — the same branch `ri-06` hooked GATEKEEPER's shadow
entry into — gathering `handoff_record`/`diff_stat`/`test_output_tail`
itself (each independently best-effort) and appending the returned entry to
its own `history` list before the same `_save_state` call. Skipped entirely
on the replay path, so a retried `apply-outcome` call costs no extra
`decide()` call and produces no duplicate entry — identical reasoning to
`ri-06`'s own replay-safety fix.

### D2 — Question shape

```python
questions = {
    "outcome": {
        "type": "choice",
        "instructions": "Which of this phase's allowed outcomes does the "
                         "evidence actually support?",
        "criteria": {o: o for o in expected_outcomes},  # names carry the
                                                          # meaning; phase-
                                                          # specific descriptions
                                                          # would need a second
                                                          # per-phase table this
                                                          # item does not add
    },
    "evidence_supports_outcome": {
        "type": "noul",
        "instructions": f"The evidence supports the claimed outcome "
                         f"{claimed_outcome!r}.",
    },
}
```

One `decide()` call per phase transition, spanning both questions.

### D3 — Signal gathering is independently best-effort per signal

`_git_diff_stat(worktree_path)`, `_test_output_tail(change_dir)`, and
`_read_local_handoff(change_dir, phase, handoff_id)` each return `None` on
any failure (missing path, subprocess error, file not found, JSON parse
error) rather than raising — the adjudication call proceeds with whatever
subset of signals is available, and if `decide()` itself is unavailable (or
every signal is `None` and there is nothing to adjudicate), the whole step
records nothing. No shadow entry is better than a fabricated one — the same
principle `ri-05`'s Jaccard fallback and `ri-06`'s unavailability branches
already established.

**Revised after Codex review (PR #592, both P2):**

- `_read_local_handoff`'s glob prefix originally lowercased the raw phase
  constant (`"IMPLEMENT"` → `"implement"`). Codex read the real handoff
  writer (`handoff_builder._phase_name_for`, which maps `"IMPLEMENT"` to
  the human-readable `"Implementation"` before `PhaseRecord._phase_slug()`
  lowercases it) and found the actual files are named
  `"implementation-<n>.json"`, `"validation-<n>.json"`, etc. — the naive
  slug never matched any real local-fallback file for IMPLEMENT,
  IMPL_REVIEW, VALIDATE, VAL_REVIEW, PLAN_ITERATE, or IMPL_ITERATE. Fixed
  by importing `handoff_builder._BASE_PHASE_NAMES`/`_ITERATION_PHASES`
  directly and deriving the glob prefix from the same mapping the writer
  uses (`_handoff_slug_prefix`), rather than duplicating it.
- `_expected_outcomes_for_phase("VAL_REVIEW")` was missing `"max_iter"`,
  even though `autopilot.TRANSITIONS["VAL_REVIEW"]` has always allowed it
  — a pre-existing bug in a dict this item is the first to treat as an
  exhaustive Choice criteria set. A real `max_iter` claim had no matching
  criterion, forcing an artificial disagreement. Fixed directly in
  `_expected_outcomes_for_phase`.

### D4 — Shared shadow-record envelope, reused from `ri-06`

`gatekeeper_shadow.record_shadow_judgment`'s envelope
(`phase`/`at`/`kind`/`acting_outcome`/`judged_outcome`/`judgment`) is reused
verbatim by importing it, rather than duplicating the shape: this item's
entry has `phase="PHASE_OUTCOME_SHADOW"`, `acting_outcome=claimed_outcome`,
`judged_outcome=<the Choice answer's outcome>`, and
`judgment={"outcome_distribution": ..., "evidence_noul": ..., "phase":
<real phase name>}` (the real phase name goes inside `judgment` since the
envelope's own `phase` field is the synthetic marker, exactly as `ri-06`'s
design documented for this reuse). `transition()` and the claimed
`outcome` string handed to it are never touched.

### D5 — Disagreement attribution: mechanism now, real-sprint data later

`phase_outcome_shadow_report.py` (mirroring `gatekeeper_shadow_report.py`'s
shape) extracts every `"PHASE_OUTCOME_SHADOW"` entry from one or more
`loop-state.json` files and computes the disagreement rate the same way
`ri-06`'s report does. Attribution — *which side a later review round
vindicated* — needs a second signal this item does not yet have: whether
the next `IMPL_REVIEW`/`VAL_REVIEW` round (or a human) later found the
claimed outcome wrong. `attribute_disagreements(entries, review_findings)`
takes that as an explicit second argument (a caller-supplied mapping from
phase-transition to "was the claimed outcome later found wrong") rather than
inventing a way to infer it — the acceptance outcome's own correction
(`refine-roadmap`, this item) defers wiring a real reviewer-finding source
to whenever a real sprint of shadow data exists; the function itself is
fully testable today against a constructed fixture.

### D6 — No `record_degraded` reuse

`record_degraded` marks the **acting** GATEKEEPER decision as unchecked —
a fundamentally different signal from "the shadow adjudication for this
phase transition was unavailable." Reusing it here would put a
`DEGRADED`-outcome entry into `phase_history` for a phase transition whose
*acting* outcome was never in question, corrupting any consumer that reads
`DEGRADED` entries as "this real decision did not get judged" (`goal_gate.py`
does exactly this for VALIDATE). Unavailability here means *no shadow entry
at all* (D3), matching `ri-06`'s own precedent — the roadmap's scaffolded
acceptance outcome naming `record_degraded` was corrected via `refine-roadmap`
before implementation started (see the roadmap's own refinement history for
`ri-07`).

## Non-goals (out of scope for this item)

- Attributing real disagreements over a full sprint of production autopilot
  runs (D5) — no such data exists in this repo yet.
- Promoting the judged outcome to the acting one, or changing `transition()`.
- A coordinator-side lookup of a handoff record by `handoff_id` (does not
  exist today).
- Fabricating `worktree diff stat` / `test-output tail` when the underlying
  artifact is missing.
- Unifying `phase_agent._expected_outcomes_for_phase` with
  `autopilot.TRANSITIONS` (pre-existing duplication, unrelated to this item).
