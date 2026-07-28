# Semantic-context evaluation

This directory is the durable home of the evaluation that decides whether
semantic context injection may be enabled by default.

One file lives here when a measurement has been taken: `report.json`, conforming
to
[`context-eval-report.schema.json`](../../../openspec/contracts/semantic-context-evaluation/schemas/context-eval-report.schema.json).
It is the only artifact that may authorize enabling the injection default, and
the only artifact the enablement gate reads.

**There is no `report.json` here right now.** That is not a missing file. Absent
is the fail-closed default state: with no report, enablement is unauthorized, and
that is the correct answer until a measurement has actually been taken.

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
| `index.embedder.fingerprint` differs from the configured embedding contract's fingerprint | A model, dimension, or indexing-parameter change invalidates the measurement. A matching model name alone does not restore it. |
| `index.indexed_revision` is not reachable from the evaluated tree | The measurement describes a tree this one does not descend from. |
| The report fails schema validation | It is not a report. |
| `verdict` is not `pass` | It never authorized anything. |

Any one of these requires the injection default to stay disabled. This is what
"a later regression disables semantic injection" means at the level ri-12's
per-request fallbacks cannot see: ri-12 already fails closed for every non-ready
service state, but it cannot notice that the *justification* for enablement has
gone stale.

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
