# Design: Judge fix-tier classification in fix-scrub

## Context

`classify_finding` (`skills/fix-scrub/scripts/classify.py`) routes each finding
to an `auto` / `agent` / `manual` fix tier. Two of its gates are string tests
dressed as judgments: `_marker_has_sufficient_context` (>=10 characters follow
a TODO/FIXME marker) and `_deferred_has_proposed_fix` (the deferred finding's
detail contains the substring `"proposed fix"` or `"resolution"`). Both
mis-tier real findings — a ten-word TODO with no actionable content passes the
character-count gate, and a terse but genuinely actionable one can fail it.
`_is_ruff_fixable` (ruff rule-prefix matching) and all source-based routing
(`ruff` / `mypy` / `markers` / `deferred:*` / `architecture` / `security` /
unknown) are unaffected — they stay fully deterministic.

## Decisions

### D1: One batched `decide()` call per `classify()` invocation, not per finding

`classify()` already receives the whole findings list for one fix-scrub run.
A new `_judge_fix_tier_gates(findings, dry_run=False)` filters to only the
`markers` and `deferred:*` findings that would otherwise hit a content
heuristic, and asks one `Noul` question per such finding in a single `decide()`
call, keyed by list index. `_is_ruff_fixable`, `mypy`, `architecture`/`security`,
and unknown-source routing never enter the judgeable set, so a findings list
containing only those never calls `decide()` at all — verified by a call-count
test per the roadmap item's own acceptance outcome.

### D2: Two different Noul propositions, one shared call

- `markers` findings: `Noul("Could an agent act on this marker without asking
  a human?")`, replacing `_marker_has_sufficient_context`.
- `deferred:*` findings: `Noul("Does this finding include a concrete,
  applicable fix?")`, replacing `_deferred_has_proposed_fix`.

Both question types can share one `decide()` call (heterogeneous per-item
questions in one batch is the existing `consensus_synthesizer._judge_pairs`
pattern — same `{"type": "noul", "instructions": ...}` shape, no `criteria`
key, since `Noul`'s yes/no proposition is fully carried by `instructions`).

### D3: `classify_finding` takes an optional `judged_hint: bool | None`

Rather than have `classify_finding` call `decide()` itself (it operates on one
finding with no visibility into the batch), it gains a `judged_hint`
parameter. `classify()` computes the batch once via `_judge_fix_tier_gates`
and passes each finding's result (or `None`) through. `judged_hint=None`
(the default) makes `classify_finding` fall back to the original heuristic
exactly as before — every pre-existing call site and test in
`skills/fix-scrub/tests/test_classify.py` calls `classify_finding(finding)`
with no second argument, so all 20 pass unmodified.

### D4: Threshold is a plain module constant, not a config-loadable floor

`DEFAULT_FIX_TIER_NOUL_THRESHOLD = 0.5` (`noul >= threshold` -> True). Unlike
`ri-16`'s capability-gap recall floor, nothing in this item's rationale calls
for an asymmetric precision/recall skew, and the roadmap item is Effort: S —
a `load_..._threshold(config_path=None)` sidecar-JSON loader (the pattern
`gatekeeper_shadow`, `vendor_review`, `fact_check`, and `audit_triage`
established) would be unused generality for a threshold nothing here needs to
tune. Not adding one.

### D5: A malformed or missing per-finding answer falls back individually

`_judge_fix_tier_gates` returns a `dict[int, bool]` covering only the findings
that got a usable answer (present, numeric `noul` field). A finding whose
answer is missing or malformed falls back to its own original heuristic; it
does not force sibling findings in the same batch to fall back too. Whole-batch
unavailability (module missing, `decide()` returns a falsy value) is the same
code path with an empty dict, so every finding falls back — this is the
ri-15/ri-16/ri-12 partial-answer lesson applied from the start.

### D6: No `dry_run` threading — fix-scrub's own `--dry-run` flag already means something else

Every other judged item this roadmap has landed threads a `dry_run` flag from
its script's own CLI into `decide(dry_run=...)`. fix-scrub's `main.py` already
has a `--dry-run` flag (`run(..., dry_run: bool)`), but it means "plan only,
apply no fixes" — an unrelated, pre-existing concept unwired to `classify()`
entirely (`classify(findings, severity_filter=severity)` is called before the
dry-run branch even exists). Reusing that name for "skip the live judgment
call" would conflate two different meanings of the same flag in the same
module. `_judge_fix_tier_gates` still accepts a `dry_run` parameter (threaded
to `decide()`) so it matches the shared testing/stubbing convention and the
`system_one_decisions.decide()` contract, but nothing in fix-scrub's CLI wires
a flag to it — this is a documented gap, not an oversight, and no acceptance
outcome calls for one.

### D7: Test-location correction — `skills/fix-scrub/tests/`, not `skills/tests/fix-scrub/`

The roadmap item's own scaffolded acceptance outcome says "covered by
fixtures in skills/tests/fix-scrub," matching this repo's *general*
`skills/tests/<skill-name>/` convention (AGENTS.md). But
`skills/tests/ci_coverage/test_ci_test_coverage.py`'s own `_EXEMPT` dict
explicitly carves out `"fix-scrub/tests": "run by the test-skills job"` —
fix-scrub's tests are co-located at `skills/fix-scrub/tests/` (where
`test_classify.py` already lives) and run by ci.yml's separate `test-skills`
job (`agent-coordinator/.venv/bin/python -m pytest skills/bug-scrub/tests/
skills/fix-scrub/tests/ -v`), not the `skills/tests/`-rooted `test-infra-skills`
job. A `skills/tests/fix-scrub/` directory would not be reached by any CI job
today. New tests go to `skills/fix-scrub/tests/test_classify_judgment.py`
instead, matching the file they test and the CI job that already covers it.

## Non-goals

- Changing `_is_ruff_fixable`, mypy routing, architecture/security routing, or
  the default-manual-for-unknown-source path.
- A live TypeSafe SDK installation (see the parent proposal's Non-Goals).
- A config-loadable threshold (D4) or CLI-wired dry-run (D6) — no acceptance
  outcome or rationale text calls for either.
