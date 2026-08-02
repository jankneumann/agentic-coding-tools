# Semantic-context evaluation

This directory is the durable home of the evaluation that decides whether
semantic context injection may be enabled by default.

One file lives here when a measurement has been taken: `report.json`, conforming
to
[`context-eval-report.schema.json`](../../../openspec/contracts/semantic-context-evaluation/schemas/context-eval-report.schema.json).
It is the only artifact that may authorize enabling the injection default, and
the only artifact the enablement gate reads.

`report.json` records a `fail` verdict. Enablement is therefore unauthorized and
`INJECTION_DEFAULT_ENABLED` stays `False` — because the evidence says no, not
because evidence is absent. See
[The recorded measurement](#the-recorded-measurement) for what was and was not
measured.

## Why the report lives here

A change directory moves. `openspec/changes/<id>/` becomes
`openspec/changes/archive/<date>-<id>/` on archival, and every reference into it
eventually 404s — including the change's own path arithmetic.

The previous attempt demonstrated both halves of that. Its report was written to
`openspec/changes/add-semantic-code-search/eval/spike-report.md`, and the
`code-search` spec required it "in the change directory"; archival moved it. Its
runner computed `REPO_ROOT = HERE.parents[3]`, correct from
`openspec/changes/<id>/eval/` and wrong forever after archival added a path
segment, so the published baseline could not be re-derived from the published
artifact.

This directory is outside every change directory. Specs, guides, gates, and CI
reference it by a path that does not move (design decision D1).

## What a report is, and what it cannot say

| Property | Value |
|---|---|
| Verdict vocabulary | `pass` \| `fail`. Closed, exactly two members. |
| Values that do not exist | `skip`, `blocked`, `waived`, `partial`, `unmeasured`, `n/a`, `pending` |
| Waiver field | None. Not in the schema, not in the CLI, not in the corpus. |
| "Could not measure" | `{"verdict": "fail", "fail_reasons": ["unmeasured"]}` — the only representation |
| A failing verdict | Must carry at least one `fail_reasons` entry from a closed vocabulary |
| A passing verdict | Must carry no `fail_reasons`, and every declared gate must be present and passing |

An operator who believes a threshold is wrong changes the threshold in
`packages/context-eval/corpus/manifest.yaml`. That is a reviewable diff, and it
moves the corpus digest, which invalidates every report recorded against the
previous corpus. There is no path from "I disagree with this result" to an
authorized enablement that does not pass through a new measurement.

**A `fail` verdict is a correct and complete outcome.** No task in
`gate-semantic-context-default-enablement` requires `verdict == "pass"`; the
measurement phase succeeds by recording what was measured, whatever it says.
Semantic hit@5 has never been measured on this repository, and this apparatus is
designed to be equally correct at 4/10.

## The recorded measurement

Taken 2026-08-01 (`as_of: 2026-08-01T00:00:00Z`) against
`748af34c4268e768f0e3a7e7cdbe64c02835b7b6`, corpus digest
`6417066963927e0f1009a1b10fa49e6be6e11da3f7991290657b2adbbb7a0f56`,
harness `context-eval 0.1.0`, harness source digest `d8bcd8ea…`. The CLI
exited `2`.

**Verdict: `fail`** — `["unmeasured", "denominator_mismatch",
"index_tier_insufficient"]`.

| Gate | Min tier | Verdict | Measured against threshold |
|---|---|---|---|
| `retrieval_quality` | `live` | **fail** | nothing measured; `unmeasured`, `index_tier_insufficient` |
| `coding_context_utility` | `live` | **fail** | 0 cases scored across 5 utility-applicable consumers; `unmeasured`, `index_tier_insufficient` |
| `scope_compliance` | `none` | **pass** | 0 rendered violations vs `max 0`; outbound fidelity `1.0` vs `min 1.0` — over non-empty adversarial arms, see below |
| `fail_closed_regression` | `none` | **pass** | expectation match rate **1.0 (7/7)** vs `min 1.0` |

`cases_declared: 19`, `cases_scored: 7` — hence `denominator_mismatch`. The
twelve unscored cases are recorded individually with `unscored_reason:
producer_error`, not dropped.

This report was re-derived on 2026-08-01 from its own recorded inputs, and it is
not the artifact committed on 2026-07-31. The first one was produced before
`ddc30be2` implemented `_ResolvedScope.allows()`, and the harness at HEAD no
longer reproduces it: two of its four gate rows change. It was regenerated rather
than annotated, because a published artifact the committed code cannot re-derive
is precisely the failure [Why the report lives here](#why-the-report-lives-here)
says this directory exists to end. Nothing was tuned and nothing was re-run
selectively: the index tier is still `none`, the corpus and its thresholds are
untouched, and the top-level verdict is still `fail` for the same three reasons.
That drift was invisible to the expiry conditions of the day — the corpus digest
and the declared harness version were both unchanged — which is why
`harness.fingerprint` now exists.

**`harness.fingerprint` has been re-derived twice since this report was
recorded, on 2026-08-01 and again on 2026-08-02, and nothing else was.** The
enablement gate's own source changed after the measurement — the verdict is now
re-derived from the body rather than read, the digest now covers `*.py` rather
than everything in the directory, and that re-derivation now reads the
`environment` block as well as the rows — and a change to the measuring code
invalidates its own evidence by construction, whether or not it touched a scorer.
What the field should say was established rather than assumed, the same way both
times: the harness at the previous commit and the harness at this one were both
run over this same tree with this report's own recorded inputs, and the two
documents differ in **exactly one field**, `harness.fingerprint`. Every gate row,
every consumer row, every case result and both arms of all nineteen cases are
byte-identical, which is what "the measurement path is untouched" has to mean if
it is to be checkable. Re-running the harness *here* instead would have changed
three further fields — `cases[17]`'s baseline arm picks up whichever
`openspec/changes/*/design.md` the working tree currently holds, because the
exact-search baseline reads the working tree rather than
`repository.evaluated_revision` — and importing that drift while claiming to
refresh a fingerprint is the artifact-drift this directory exists to end.

**The index tier was `none`, and that is the headline.** `index_repo` never
produced a `ready` index: five attempts, each after a documented change to the
scope or the source tree, all exited `1`. Three independent defects in
`packages/code-search` are responsible and none of them is a threshold anyone
could argue about:

1. `indexer_pg.py:211` requires `<repo-root>/.cocoindex_code/settings.yml`. No
   such file exists in this repository, `index_repo` does not create one, and
   the indexing procedure in [`code-search.md`](../../guides/code-search.md)
   does not mention it. The documented write path cannot complete here at any
   scale.
2. `cli_runtime.py:108` builds `LocalSecretScanner()` with the default 30-second
   *operation* deadline. That deadline is set at the first scanned file and
   never reset, and the same scanner instance is reused for source-manifest
   planning and for the per-chunk scan at `indexer_pg.py:205` — so it is spent
   on model loading and embedding, work the scanner does not do. Scanning all
   1367 eligible files takes 0.44 s; the real run raised `scanner_timeout` after
   456 files and 46.1 s. The bound is not reachable from the CLI.
3. The `credential_assignment` rule matches identifier text such as
   `token = authorization.partition(" ")` and `api_key = api_key_resolver.resolve(`.
   Seven tracked files are unindexable without an explicit `--exclude`; none is
   a target of any corpus case.

**`scope_compliance` passed over arms that are not empty, which is what makes it
evidence.** The earlier artifact recorded this same `pass` vacuously: the
harness's scope stand-in supplied `read_allow` and `deny` but not `allows()`, so
every case reaching ri-12's `ready` path raised
`AttributeError: '_ResolvedScope' object has no attribute 'allows'` at
`semantic_context.py:454`, was swallowed by ri-12's never-raises guarantee, and
came back as `unavailable`/`unknown_state` with nothing rendered. A gate counting
rendered violations over three empty arms counts zero — the exact tautology
design D8 introduced those cases to prevent. `ddc30be2` implemented `allows()` on
`_ResolvedScope` by delegating to the shared read-scope semantics, and the
regenerated report shows the difference:

| Adversarial case | Then | Now |
|---|---|---|
| `ADV-LEAKED-HIT` | `unavailable`/`unknown_state`, 0 files | **injected**, 2 files, 4 lines, 0 violations |
| `ADV-DENY-PRECEDENCE` | `unavailable`/`unknown_state`, 0 files | **injected**, 1 file, 2 lines, 0 violations |
| `ADV-ALL-HITS-FILTERED` | `unavailable`/`unknown_state`, 0 files | `out_of_scope`/`all_hits_scope_filtered`, 0 files |

Each of the three recorded responses carries a hit outside the declared scope.
Two now render the in-scope remainder with the out-of-scope hit filtered out, and
the third renders nothing *for the declared reason* — its every hit was filtered,
which is `all_hits_scope_filtered`, not an apparatus failure wearing a fallback's
clothes. The gate is therefore measuring ri-12's client-side deny re-check rather
than measuring an empty section. It still covers only the 7 scored cases of 19.

Removing that same `AttributeError` is also what moves `fail_closed_regression`
from 0.571 (4/7) to **1.0 (7/7)**. The four genuinely non-`ready` responses
(`not_indexed`, `revision_mismatch`, `scope_rejected`,
`reindexing_in_background`) each produced exactly the trigger/reason pair they
declare, as they always did; the three `ready` adversarial cases previously
failed because they never got far enough to honour or violate anything, and now
reach their declared outcome. **The 4/7 recorded on 2026-07-31 was an artefact of
the harness, not a behavioural failure of ri-12** — the gate row asserted a
3-of-7 fail-closed regression that did not happen.

Two further cases — `FC-QUICK-TASK-NO-DECLARED-SCOPE` and
`FC-DEBUG-ADHOC-NO-SCOPE` — are unscorable for an unrelated reason: they declare
an empty read scope, so ri-12 short-circuits before the search seam and they
need no recorded response, but `SemanticRuntimeProducer.render` refuses any case
with `response is None` outside `--live` before running ri-12 at all.

No operator decision was applied to this outcome and none was available to
apply. The measurement was attempted, most of it did not run, and the report
says so in the only vocabulary the schema offers.

## Reproducing a measurement

### Preconditions

Each of these is recorded in the report's `environment` block rather than
assumed, because a measurement taken in the wrong state measured something other
than what it claims.

| Precondition | Required | If wrong |
|---|---|---|
| `CODE_SEARCH_ENABLED` | set | `GET /search/code/status` short-circuits before touching the database or an embedder. The retrieval gate fails with `service_disabled_during_measurement`. |
| `COORDINATION_TRANSPORT` | `http` | Injection is HTTP-only ([`semantic-context-injection.md:104`](../../guides/semantic-context-injection.md)). Under `mcp` or `none` every case returns `transport_unsupported` **by construction** — an unmeasurable environment that would read as a measured failure. |
| Working tree | clean, at a revision the index was built from | A dirty tree short-circuits to `stale` before any query is sent. |
| Scope adapter | resolved | `_normalize_read_scope` (`skills/context-engineering/scripts/semantic_context.py:919`) is not injectable and falls back to unnormalized globs when its sibling skill is absent. A `degraded` adapter is an `apparatus_failure`, never a silent pass. |
| Index tier | `live` for the retrieval and semantic-utility gates | A seeded or fixture index fails those gates with `index_tier_insufficient`. Scope-compliance and fail-closed-regression gates need no index at all. |

### Steps

1. **Install the indexing extra and provision a scratch database.**
   `uv pip install -e "packages/code-search[index]"`, then apply migrations
   `028_code_search_registry.sql`, `029_revision_aware_code_search_indexes.sql`,
   and `030_incremental_code_search_indexes.sql` to a database this measurement
   owns. Do not point the run at a shared or another project's Postgres.
2. **Build a real index at the exact evaluated revision** with `index_repo`, as
   documented under [Indexing (write path)](../../guides/code-search.md). Its
   exit codes are `ready: 0`, `failed: 1`, `not_configured: 2`, `conflict: 3`. A
   non-zero exit is recorded as `unmeasured`, not retried into silence.
3. **Run the harness** from [`packages/context-eval/`](../../../packages/context-eval)
   across every declared gate and consumer. The CLI is built by phase 4 of
   `gate-semantic-context-default-enablement`; read that package's entry point
   rather than assuming a command line from this page. The harness takes its
   timestamp as an explicit `as_of` input and records it verbatim — nothing in
   the scoring path reads a clock.
4. **Commit the report to this directory**, whatever it says. If any earlier step
   failed, the report is committed with `verdict: "fail"` and the reasons that
   apply. That is the recorded outcome, not a blocked task.

Both arms are rendered under one shared context budget, so the exact-search
baseline is comparable rather than an unbounded dump. The budget is declared in
the corpus manifest and copied into the report.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Pass. A schema-valid report exists on disk and its verdict is `pass`. |
| `1` | Apparatus failure. The harness could not run correctly. |
| `2` | Gate failure. The measurement ran and a declared gate did not meet its threshold. |
| `3` | The report is absent, stale, or schema-invalid. |

The rule those codes exist to enforce: **nothing exits `0` without a schema-valid
passing report on disk.** "Failed" and "did not run" are different facts and are
never collapsed into one code.

## When existing evidence expires

A passing report authorizes enablement only while it still describes the current
system. The enablement gate treats a report as **absent** — and therefore treats
enablement as unauthorized — when any of these hold (design decision D12):

| Condition | Why it invalidates the evidence |
|---|---|
| `harness.corpus_digest` differs from the recomputed digest of `packages/context-eval/corpus/` | A case or a threshold changed; the report was judged against different evidence. |
| `harness.version` differs from the installed harness version | The report was produced by software nobody has anymore. |
| `harness.fingerprint` differs from the digest of `packages/context-eval/src/context_eval/` | The code that measured this has changed, whatever version it still calls itself. `version` is a string a person writes into `pyproject.toml` — the one condition here an operator could satisfy by assertion, and the reason a report HEAD could no longer reproduce once counted as current evidence. |
| `index.embedder.fingerprint` differs from the configured embedding contract's fingerprint | A model, dimension, or indexing-parameter change invalidates the measurement. A matching model name alone does not restore it. |
| `index.indexed_revision` is not reachable from the evaluated tree | The measurement describes a tree this one does not descend from. |
| The report fails schema validation | It is not a report. |
| The report's body does not account for every declared case, gate, and consumer | Provenance says the evidence is *current*; only the body says it is *about anything*. A document carrying the right digest, the right harness identity, a matching fingerprint, a reachable revision and a `pass` verdict, with `gates: []` and `cases: []`, is green because it is empty. |
| The report's `verdict` is not the one its own body composes to | Accounting for the whole corpus is not the same as agreeing with it. `compose_verdict()` returns `pass` only when every declared case was scored, every required gate passed and every precondition held, so a `pass` recorded over failing gates, failing consumers, unscored cases, or a gate that passed below the index tier it declares describes a run that cannot have happened. |
| `verdict` is not `pass` | It never authorized anything. |

Any one of these requires the injection default to stay disabled. This is what
"a later regression disables semantic injection" means at the level ri-12's
per-request fallbacks cannot see: ri-12 already fails closed for every non-ready
service state, but it cannot notice that the *justification* for enablement has
gone stale.

### Running the check

```bash
make semantic-enablement-gate
# optionally, the JSON EmbeddingContract the tree is configured with:
make semantic-enablement-gate EMBEDDING_CONTRACT=/path/to/contract.json
```

It compares the single `INJECTION_DEFAULT_ENABLED` declaration in
`skills/context-engineering/scripts/semantic_context.py` against the report
above, and names every condition it finds unmet. Its exit codes are the
harness's, read against this question:

| Code | Meaning |
|---|---|
| `0` | Authorized — or nothing is claimed, because the default is disabled. |
| `1` | The gate could not read what it needed to decide. |
| `2` | The evidence is current and schema-valid, and its verdict is not a `pass`. |
| `3` | The evidence is absent or has expired. |

**A disabled default passes, and that is the mechanism, not a loophole.** A
default that claims nothing needs no evidence, so disabling it always restores
the check to passing — which is exactly what "stale evidence withdraws
authorization" has to mean if it is to have a remedy. The corollary is that this
gate is correctly green on a tree where nobody enabled anything and cannot be
watched failing there; `packages/context-eval/tests/test_enablement_gate_mutation.py`
is the substitute, constructing an enabled default against a report that is
absent, stale by each condition above, failing, and schema-invalid, and asserting
a non-zero exit for each.

It mutates the report's **body** as well as its provenance, and the second family
exists because the first was not enough. Perturbing where a report came from
never catches a report that came from the right place and says nothing: a
hand-written document carrying the current digest, the current harness version, a
matching fingerprint, a reachable revision and `verdict: "pass"`, with
`gates: []`, `per_consumer: []`, `cases: []` and `cases_declared: 0`, was accepted
as schema-valid and authorized an enabled default with seven conditions printed
as met. Two layers close it. The report contract sets `minItems` on `gates`,
`per_consumer` and `cases` and a lower bound of 1 on the declared counts, so the
empty body is unwritable; `report_describes_corpus` re-derives the declared
denominator from the file on disk, so a schema-valid report that omits a declared
gate, consumer, or case — which no schema can detect, because it is a comparison
between two documents — is treated as absent evidence.

A third family closes the same error one layer further in, and it exists because
the second was not enough either. Accounting for the corpus is not agreeing with
it: a **three-field** edit of the report below — `verdict` `fail` to `pass`,
`fail_reasons` deleted, `indexed_revision` filled with any reachable commit,
which a live run populates anyway — printed **nine** met conditions on its way to
exit `0`, over a body still recording two required gates failing, five of six
consumers failing, seven of nineteen cases scored, and `index.tier: "none"`
against two gates declaring `min_index_tier: "live"`. Every condition
interrogated what surrounded the conclusion; nothing derived the conclusion. Two
layers again. The report contract refuses a `pass` that reports a failing gate, a
failing consumer, or an unscored case; `verdict_consistent` re-derives the
composer's whole invariant from the artifact, including the two comparisons a
schema cannot make — `cases_scored` against `cases_declared`, which is a sibling
comparison, and `index.tier` against each gate's `min_index_tier`, which is an
ordered one over an enum — and the `environment` block, whose `scope_adapter`
and `code_search_enabled` are the composer's `apparatus_failure` and
`service_disabled_during_measurement`. The derivation is one-way: a recorded
`fail` over a body with nothing visibly wrong is legitimate, because
`missing_required_gate` and a case the corpus never declared are decided against
the corpus rather than against the document, and `report_describes_corpus` is
what catches those. A degraded scope adapter is not one of them, though it was
cited as one for a round: it is recorded in the report and required by the
contract, so a `pass` over `scope_adapter: "degraded"` — a document the composer
cannot produce, and honest drift rather than forgery — read as self-consistent
to both consumers until the environment block was derived too.

Without `EMBEDDING_CONTRACT` the embedding fingerprint has nothing to be compared
against, and that is an unmet condition rather than a skipped one: an unchecked
fingerprint is not a matching one. It is optional only because the default is
off.

### What this check does not detect

A report whose numbers were **invented rather than measured** — every declared
case `scored` with fabricated arms, every gate passing with fabricated `measured`
values, every consumer passing with fabricated metrics, at tier `live` with a
reachable revision — is schema-valid, self-consistent, and **authorizes**. That
document was built by hand and watched exiting `0`; it is recorded here rather
than left for a reader to discover.

Every condition above compares the artifact against something else that is also
in this repository: the corpus, the harness's source, git, a supplied contract.
Anyone who can edit the report can compute all of them, so no condition of that
shape can distinguish a measurement from a claim about one.

What the conditions do buy is worth stating precisely, because it is not nothing.
They raise the cost from *editing three fields of a committed failure* to
*forging an entire coherent measurement*, and they make honest drift impossible
to mistake for evidence — a corpus that moved, a scorer that changed, an index
built from a revision this tree does not descend from. That drift is the failure
that actually happens here, and it is the one that went undetected in July 2026.
Deliberate forgery is not something a build gate can close. The construction that
would is the gate re-running the harness over the report's own recorded inputs
and comparing the composed document against the committed one; that is a separate
change, and it needs the exact-search baseline pinned to
`repository.evaluated_revision` first, because the baseline arm currently reads
the working tree.

## What this supersedes

[`openspec/changes/archive/2026-07-20-add-semantic-code-search/eval/spike-report.md:9-19`](../../../openspec/changes/archive/2026-07-20-add-semantic-code-search/eval/spike-report.md)
records `BLOCKED (environment) → WAIVED (operator decision, 2026-07-19)` and
`semantic hit@5 is UNMEASURED`. Every embedding backend returned 403; the
baseline it did produce covers only the exact-search floor
(`{"n": 10, "rg_phrase_hit_at_k": 0, "rg_keyword_hit_at_k": 3}`, measured on the
tree of 2026-07-19).

Its automated check was a substring test — `'Verdict' in t and 'hit@5' in t` —
which the waived, unmeasured report passes.

That artifact is history, not evidence. Its ten hand-labeled tasks are rescued
into the corpus with their identity and provenance preserved; its runner is not
carried forward.

## See also

- [Code search](../../guides/code-search.md) — the query service, the index
  lifecycle, and the retrieval-quality gate this report closes.
- [Semantic context injection](../../guides/semantic-context-injection.md) — the
  flag, the triggers, the budget, and the HTTP-only constraint.
- [`openspec/contracts/semantic-context-evaluation/schemas/`](../../../openspec/contracts/semantic-context-evaluation/schemas)
  — the published report, corpus, and case schemas.
- `openspec/specs/code-search/spec.md` — `Requirement: Retrieval Quality Gate`.
- `openspec/specs/semantic-context-evaluation/spec.md` — the evaluation's own
  requirements, once this change is archived.
