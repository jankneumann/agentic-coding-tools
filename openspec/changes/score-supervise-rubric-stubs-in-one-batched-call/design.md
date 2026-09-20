# Design: Score supervise rubric stubs in one batched call

## Context

Grounding this item overturned several of its own scaffolded claims. The "analyst-archetype
rubric dispatch" is not Python code at all -- it is host-orchestration prose in
`skills/supervise/SKILL.md` and `templates/rubric-prompt.md` that instructs the host to
dispatch a sub-agent. `digest.py`'s own docstring states it is "deliberately host assisted:
it validates and transforms files, but never calls a model, a network service, or a roadmap
writer," and an enforced test (`TestHostAssistedInvariant` in `test_cycle_state.py`) scans
every script in `skills/supervise/scripts/` for LLM-SDK imports. `system_one_decisions` is
not in that forbidden list (the same is true for every other judged skill in this roadmap),
so a new script may use it, but `digest.py` itself must not become the one that does.

`justification` is genuinely required today in `rubric-score.schema.json`'s `factor`
definition, confirmed by two tests deleting it and expecting `ValidationError`. There is no
"Score legend" renderer anywhere in the codebase, and no existing fixture pair or live data
to measure an "agreement rate" against -- both are addressed below (D4/D8) as things this
item builds from scratch or explicitly narrows, not things it extends.

## Decisions

### D1: The judged scorer is a new sibling script, not a change to `digest.py`

`skills/supervise/scripts/rubric_score.py` is the only file in this skill that imports
`system_one_decisions`. `digest.py` never imports it, so its own "never calls a model"
docstring claim stays literally true. This mirrors `ri-05`'s "judged batching lives beside
`match_score`, not inside it" and `ri-13`'s identical precedent for `classify.py`.

### D2: Batching granularity is one `decide()` call per rubric cycle

`rubric_score.score_batch(repo_root, manifest, dry_run=False)` asks one `Score` question
per `(stub_key, factor)` pair, all in a single `decide()` call -- up to 100 questions for
20 stubs x 5 factors, matching the acceptance outcome's "up to 100 Score questions... in a
single call."

### D3: All-or-nothing degradation, not per-item fallback

Every other judged item in this roadmap (`ri-11`, `ri-12`, `ri-15`, `ri-16`) degrades
per-item on a partial answer, discarding only the affected item. This item does not,
deliberately: `digest.py`'s `_validate_score_join` already rejects a scores document that
is missing even one requested `stub_key` -- inherited directly from the sub-agent path's
own pre-existing "missing, partial, invalid, or late output is rejected rather than
repaired" policy (`templates/rubric-prompt.md`'s host-dispatch contract). A partially-scored
document from `rubric_score.py` would be rejected by that existing, unmodified validation
anyway, so `score_batch` returns `None` for the *whole* call when even one stub/factor is
missing or malformed, rather than a partial `scores` array `rank_candidates` would just
reject. This is a faithful application of the existing contract, not a new one.

### D4: `justification` becomes optional; the digest renders a Score legend label instead

`rubric-score.schema.json`'s `factor.required` drops `justification` (`["score"]` only).
A live `Score` answer has no free-text field to populate it with (`ScoreAnswer` carries
`.score`/`.confidence`/`.probabilities`/`.legend`, no justification string), so
`rank_candidates`'s `justifications` dict comprehension (`digest.py`) now substitutes a
static, per-factor, per-score-level label (`_FACTOR_LEVEL_LABELS[factor][score - 1]`,
duplicated in `rubric_score.py`'s `_FACTOR_CRITERIA` -- not imported, to preserve D1) when a
factor's `justification` is absent. `supervise-digest.schema.json`'s own pre-existing
`justifications` requirement (all 5 keys, non-empty strings) needs no change: the
digest-level field is always populated, either with the real justification or the
legend-derived label.

### D5: This change becomes the new steward of the rubric/digest schema contracts

`test_digest_schemas.py`'s `CHANGE_SCHEMA_DIR` pinned the byte-identity check to the
original archived change (`add-supervisor-candidate-work-digest`) that first defined these
schemas. Archived changes are a record and should not be written into (mirroring `ri-12`'s
identical precedent for `backfill_decision_tags.py`'s CLI default), so this change adds its
own `contracts/schemas/{rubric-score,digest}.schema.json` copies and repoints
`CHANGE_SCHEMA_DIR` here via the same `change_dir()` helper -- preserving the
OpenSpec-path-stability guard (AGENTS.md) so a future archival of *this* change does not
break the test either.

### D6: Score-to-schema mapping

Each factor's `Score` criteria is a 5-element ordered list; `criteria[i]` describes schema
score `i + 1`. `risk`'s criteria are inverted so `criteria[4]` describes the safest,
highest-scoring level, matching the schema's documented "risk 5 = safest" convention.
`ScoreAnswer.score` is a 0-indexed, possibly-fractional position ("the probability-weighted
average of the rubric levels; may fall between integer levels," per
`run-the-gatekeeper-as-a-scored-decision-in-shadow-mode/design.md`); this item maps it into
the schema's required `integer, 1-5` range via `max(1, min(5, round(raw_score) + 1))`.

### D7: Two-tier dispatch order in `SKILL.md`

The host now tries `rubric_score.py score-batch` first; only when it exits nonzero
(module unavailable, live judgment unreachable, or any structural defect) does it dispatch
the sub-agent analyst archetype, exactly as before. `rank_candidates` needs no change to
accept either source: `_validate_score_join` already treats any conforming scores document
identically regardless of who produced it, which is precisely why "the analyst-archetype
dispatch remains the fallback" is achievable without weakening any existing validation.

### D8: The "agreement rate over an archived analyst output" acceptance outcome has no data to build from -- scope narrowed, not silently dropped

Grounding found no manifest fixture and no archived analyst output anywhere in this
codebase to measure agreement from. The only rubric fixture (`rubric-valid.json`) is a
2-stub hand-authored document used purely for schema-validity tests. The only precedent for
an agreement/disagreement metric in this roadmap, `ri-06`'s `gatekeeper_shadow_report.py`,
computes its rate from *live, accumulated production shadow-mode recordings over calendar
time* -- not a static fixture pair -- and `ri-08` (which would consume that data) remains
durably deferred until real shadow data exists.

This item ships `compute_agreement()`, the report function itself (mirroring
`disagreement_report`'s shape: per-factor and overall agreement counts/rates over two
rubric-score documents), with unit tests against an explicitly synthetic fixture pair
proving the function is correct. It does **not** claim a real agreement rate in this PR or
in the change artifacts -- fabricating an "archived analyst output" fixture and measuring
against it would produce a number that looks like empirical validation but measures
nothing real. A genuine agreement-rate measurement requires a live shadow-mode period
(mirroring `ri-06`'s pattern exactly) generating real comparable data over time, which is
out of scope here. This mirrors the ri-05 precedent: "ship the closest faithful
approximation and document the gap explicitly in design.md rather than silently narrowing
scope."

### D9 (documented, not fixed): the shared token-budget estimator undercounts large batches

`system_one_decisions/_core.py`'s `_estimate_tokens` sums state size plus only the single
longest question's size, not all questions summed -- accurate enough for every prior
call site's 2-3 questions, but untested at this item's 100-question scale. Not fixed here:
it is a pre-existing gap in a shared primitive, out of scope for a single roadmap item, and
`decide()`'s own contract ("never raises... returns `None` on... SDK error") means a real
oversized-payload rejection from the live API still degrades gracefully into this item's
existing all-or-nothing fallback (D3) -- only the pre-check's precision is imperfect, not
this item's correctness.

### D10 (post-review fixes): full stub content in the scoring state, and Jev provenance in the digest

Two Codex findings on this PR, both confirmed against real code before fixing:

- **P1**: the scoring state sent only each stub's `title`, omitting `description`,
  `rationale`, `effort`, and `depends_on` -- the fields that actually say what the work is,
  why it matters, its size, and its prerequisites. Without them the judgment could not
  meaningfully assess `value`, `readiness`, `scope_fit`, or `risk`. Fixed by including the
  full bounded stub payload in `state["candidates"][key]`.
- **P2**: no `evidence_class`/probability reached `digest.json`, violating the parent
  proposal's explicit provenance rule ("Every Jev-derived value that reaches a report
  carries `evidence_class: judgment` and the probability"). Fixed by adding optional
  `evidence_class`/`probability` fields to `rubric-score.schema.json`'s `factor` (populated
  only by `rubric_score.py`, since the analyst sub-agent's output is not a Jev-derived
  value) and a new optional `scoring_provenance` field on `supervise-digest.schema.json`'s
  `rankedStub`, populated by `rank_candidates` only for factors that carry it -- a factor
  scored by the sub-agent has no entry there.

## Non-goals

- Changing `_is_ruff_fixable`-style deterministic logic -- not applicable here, but for
  clarity: `_validate_score_join`, the ranking formula, and all source-based routing in
  `rank_candidates` are unchanged.
- Building a real "Score legend" rendering subsystem beyond the digest's existing
  `justifications` field -- there is no separate human-facing renderer to extend (rendering
  is host-executed `SKILL.md` prose); the legend substitution happens where `justifications`
  is already assembled.
- A live TypeSafe SDK installation (see the parent proposal's Non-Goals).
- A real, cited agreement-rate measurement (D8) -- ships the report function and its tests
  only; the measurement itself needs a live shadow-mode period out of scope here.
- Fixing `system_one_decisions/_core.py`'s token-budget estimator (D9).
