# Contracts: semantic context evaluation (ri-13)

Three JSON Schemas describe the evidence that may authorize enabling semantic
context injection by default.

| Schema | Describes |
|---|---|
| `schemas/context-eval-report.schema.json` | One evaluation run — verdict, gates, per-consumer results, per-case results, and provenance |
| `schemas/context-eval-corpus.schema.json` | The corpus manifest — declared cases, gates, thresholds, consumers, and budget |
| `schemas/context-eval-case.schema.json` | One evaluation case — query, labels, scope, consumer, and expectation |

## The contract is the fail-closed mechanism

This is the point of the whole change, so it is enforced by the schema rather
than described in prose.

**`verdict` has exactly two members: `pass` and `fail`.** There is no `skip`,
`blocked`, `waived`, `partial`, `unmeasured`, `n/a`, or `pending`. There is no
waiver field, no override field, and no comment field a machine reads.

The report this replaces is
`openspec/changes/archive/2026-07-20-add-semantic-code-search/eval/spike-report.md:9-19`,
which reads:

> **BLOCKED (environment) → WAIVED (operator decision, 2026-07-19).** … semantic
> hit@5 is UNMEASURED.

That document shape is unwritable here. The same facts are representable only as:

```json
{"verdict": "fail", "fail_reasons": ["unmeasured"]}
```

`fail_reasons` is required whenever `verdict` is `fail`, with `minItems: 1` and a
closed enum, so a failure always says which clause failed.

`gates[].required` is `{"const": true}`. An optional gate cannot be authored, so
"we didn't gate on that one" is not expressible.

## The denominator is declared, not derived

`corpus.cases_declared` comes from the manifest; `corpus.cases_scored` comes from
the run; both are required. The composer fails with `denominator_mismatch` when
they differ, and every case that raised, timed out, or found no index appears in
`cases[]` with `scored: false` and an `unscored_reason`.

This is deliberately the opposite of the behaviour that disqualified `gen-eval`
as a host for this gate (design D2): there, an invalid scenario
(`generator.py:147` returns `None`), a malformed YAML file, a gather-exception,
and an exhausted budget all vanish from `verdicts` **without lowering
`pass_rate`**, and only `total_scenarios == 0` is guarded. A gate whose thesis is
"could not measure is a FAIL" cannot inherit a denominator that shrinks silently.

## What these are *not*

They do not describe the coordinator's HTTP surface — that is ri-03's
`openspec/contracts/code-search/v2.yaml`, unchanged here. They do not describe
the injected section — that is ri-12's
`openspec/contracts/code-search/schemas/semantic-context-section.schema.json`,
which is this harness's **input** contract (design D4). These three describe the
evidence produced by scoring those sections.

## Field derivation, not assertion

`index.embedder.model_id`, `.dimension`, `.provider_kind`, and `.fingerprint` are
derived from the configured `EmbeddingContract`
(`packages/code-search/src/code_search_pkg/embedding_config.py`) and from
`CodeSearchResponse.index`. No component of the harness contains a model
identifier as a literal, and a test enforces that. `code-search`'s own spec
already holds that a model-name match alone is insufficient; the fingerprint is
what makes evidence expiry (design D12) decidable.

## Closed enums

`verdict` — `pass`, `fail`. Two values, permanently.

`fail_reasons[]` — `unmeasured`, `retrieval_gate_below_threshold`,
`utility_gate_below_threshold`, `consumer_regression`, `scope_violation`,
`denominator_mismatch`, `missing_required_gate`, `index_tier_insufficient`,
`corpus_digest_mismatch`, `revision_mismatch`,
`service_disabled_during_measurement`, `apparatus_failure`. Twelve values.

`gates[].kind` — `retrieval_quality`, `coding_context_utility`,
`scope_compliance`, `fail_closed_regression`. Four values.

`index.tier` — `none`, `seeded`, `live`. A gate declaring `live` and receiving
`seeded` or `none` fails with `index_tier_insufficient`. The three tiers are the
three that exist in this repository: no index at all (recorded responses), a
seeded registry row satisfying `_USABLE_INDEX_COUNT_SQL` with no embedder
contacted, and a real index from `index_repo`.

`cases[].unscored_reason` — `apparatus_failure`, `invalid_document`,
`no_index_at_revision`, `producer_error`, `timeout`. Five values, every one a
failure; none is a skip.

`per_consumer[].utility_applicable` — a required boolean, not an optional one.
`quick-task` declares `false` (its SKILL.md documents that it has no declared
read scope and therefore always falls back to `out_of_scope` /
`no_declared_scope`). Declared absence is auditable; silent absence is not.

## Determinism obligations the schema cannot express

Three properties are producer obligations, checked by the harness's own tests
rather than here, because JSON Schema cannot express them:

- `cases_scored <= cases_declared` (a sibling-property comparison).
- `steps_to_evidence` is censored to `max_files + 1` rather than null when no
  rendered hit intersects labeled evidence — a null would be a silent skip.
- The advisory `judge` block is attached only after `compose_verdict()` returns.
  The composer's signature has no judge parameter at all, which is a stronger
  guarantee than the "never overrides" convention `packages/agent-scenarios`
  established, and is enforced by `test_judge_isolation.py`.

## Promotion

All three schemas are promoted to
`openspec/contracts/semantic-context-evaluation/schemas/` **inside this change**,
before archival, per `openspec/contracts/README.md`. Tests, the Makefile target,
and the CI gate load them from that stable path, never from
`openspec/changes/<id>/contracts/`.

Because `$id` names the promoted location, the report schema's relative `$ref` to
the case schema resolves to its promoted sibling. A change-local `$id` would send
that reference into the directory archival moves — which is precisely the class
of defect that made the D9 evaluation unreproducible
(`run_eval.py:31`: `REPO_ROOT = HERE.parents[3]`, correct only before archival
added a path segment).

| Test | Fails when |
|---|---|
| `packages/context-eval/tests/test_promoted_contracts.py` | a schema is authored but never promoted, the copies drift by a byte, a promoted schema declares a change-local `$id`, the verdict enum gains a third member, or a waiver-shaped field appears |
| `packages/context-eval/tests/test_verdict_failclosed.py` | any of the five fail-closed clauses stops failing closed |
| `packages/context-eval/tests/test_judge_isolation.py` | `compose_verdict()` grows a parameter that could carry a qualitative review |
