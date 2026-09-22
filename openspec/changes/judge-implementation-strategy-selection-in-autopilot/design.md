# Design: Judge implementation strategy selection in autopilot

## Context

`implementation_strategy_selector.select_strategies()` scores each work
package on four 0/1 criteria (`loc_estimate < 200`, `alternatives_count >=
2`, `package_kind in {algorithm, data_model}`, `len(available_vendors) >=
3`) and picks `"alternatives"` when the sum crosses `ALTERNATIVES_THRESHOLD
= 2.0`, else `"lead_review"`. `design_path` is already a parameter on
`select_strategies()`, documented as "reserved for future inference," but
nothing in the function body ever opens or reads it.

The `skill-workflow` capability spec's "Implementation Strategy Selection"
requirement already describes this consuming `work-packages.yaml`
metadata "falling back to description inference" when metadata is absent
-- the judged path this item adds is exactly that fallback-to-inference
case, now backed by a real mechanism instead of an unwritten one.

## D1: Vendor availability is judgment context, not a new gate

Grounding check (corrected 2026-09-18, see proposal.md): the scaffolded
acceptance outcome originally described a hard "fewer than 3 vendors
forces lead_review" pre-check as existing behavior being preserved. It
isn't -- `_compute_score` treats vendor count as one additive 0/1 term
among four, no hard floor anywhere, and two existing tests
(`test_fewer_than_3_vendors_reduces_score`,
`test_boundary_score_2_selects_alternatives`) deliberately assert
`"alternatives"` is reachable with only 2 vendors when the sum still
clears `ALTERNATIVES_THRESHOLD`. A real attempt at the literal hard-gate
reading broke both tests, confirming the contradiction the corrected
acceptance outcome now describes.

Resolution: `available_vendors` (its count) is included in the state
handed to `_classify_package()`'s judgment call -- the judgment can weigh
vendor scarcity itself, the way a human reviewer would -- but it is never
a pre-check that short-circuits before the judgment runs, and it never
touches `_compute_score`/`ALTERNATIVES_THRESHOLD` or the fallback path at
all. `_compute_score`, the fallback branch, and every existing test
(including both vendor-count boundary tests) are untouched byte for byte.

## D2: design.md section matching is new work

No code in this repo extracts "the design.md section for package X" today
-- `implement-feature`/`plan-feature`'s own `SKILL.md` reference "the
backend section" of `design.md` only as prose guidance for a human/agent
context-slicing table, not as an implemented lookup. `_design_section_for_package()`
is new: splits `design.md` on top-level markdown headings (`^#+\s+.*$`)
and returns the body of the first section whose *heading text* contains
the package's id as a case-insensitive substring, mirroring
`review_ledger.derive_spec_file()`'s established heuristic-matching shape
(explicit signal -> substring match -> `None` when nothing matches, never
raises). Returns `None` when `design_path` is `None`, the file doesn't
exist, or no heading matches -- the judged call then proceeds without a
design excerpt in its state rather than failing the package.

## D3: One `decide()` call per non-gated, metadata-bearing package

Mirrors `convergence_disposition`/`triage`'s established shape: a single
`Choice(strategy, {alternatives, lead_review})` question per package,
built from `{"metadata": <package metadata>, "design_section": <D2's
result or None>}`. `_classify_package()` returns `None` on any
unavailability (module missing, `decide()` returns no answer, or the
answer's confidence is below `load_strategy_confidence_floor()`'s
config-held value) -- callers fall back to `_compute_score()`'s existing
weighted sum, unchanged. `DEFAULT_STRATEGY_CONFIDENCE_FLOOR = 0.5`, sidecar
JSON `implementation-strategy-judgment.json`, mirroring
`gatekeeper_shadow.load_shadow_thresholds()`/`triage.load_deep_analysis_floor()`'s
precedent exactly.

## D4: Ordering inside `select_strategies()`

For each non-integration, metadata-bearing package:
1. Ask the judgment (D3), with `available_vendors` in its state (D1). A
   confident answer wins.
2. Unavailable/low-confidence -> `_compute_score()`'s existing sum,
   completely unmodified -- including its existing (non-gated) treatment
   of vendor count, so both boundary tests keep passing regardless of
   whether a judgment was attempted first.

Integration packages and metadata-less packages are untouched (still
unconditionally `"lead_review"`, exactly as today).

## Non-goals

- `select_lead_vendor()` is untouched -- a different decision (who leads),
  not in scope.
- No change to `work-packages.yaml`'s schema; `design_path` was already a
  parameter, just newly read.

## Depends on

- `ri-05`
