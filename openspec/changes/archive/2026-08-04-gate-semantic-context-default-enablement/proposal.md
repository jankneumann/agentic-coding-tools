# Change: Gate semantic context default enablement

> Parent roadmap: `project-context-refresh-lifecycle`
> Roadmap item: `ri-13`
> Change ID: `gate-semantic-context-default-enablement`
> Effort: M
> Depends on: `inject-scoped-semantic-context-into-coding-jobs` (ri-12)

## Why

ri-01 through ri-12 built and consumed semantic code retrieval. **Nobody has ever
measured whether it retrieves the right thing.** Every claim below was verified on
this branch at `748af34c`.

**The one quality gate this repo wrote for semantic search was never satisfied,
and its failure was invisible.**

`openspec/specs/code-search/spec.md:118-130` (`Requirement: Retrieval Quality
Gate`) demands hit@5 >= 7/10 including >= 2 tasks the ripgrep baseline misses,
and its scenario demands `eval/spike-report.md` carry "an explicit pass verdict".
The report that exists —
`openspec/changes/archive/2026-07-20-add-semantic-code-search/eval/spike-report.md:9-19`
— says `BLOCKED (environment) -> WAIVED (operator decision, 2026-07-19)` and
`semantic hit@5 is UNMEASURED`. Every embedding backend was 403-blocked.
`baseline-results.json` therefore has exactly one aggregate:
`{"n":10,"rg_phrase_hit_at_k":0,"rg_keyword_hit_at_k":3}` — **no semantic column
at all**. The only measured retrieval numbers this repository owns are the
exact-search floor.

The gate's own automated check could not tell the difference. The archived
`work-packages.yaml:61` verification step was:

    python3 -c "... sys.exit(0 if ('Verdict' in t and 'hit@5' in t) else 1)"

A substring check. The waived, unmeasured report passes it. (It also names the
pre-archive path, so today it would fail on a missing file rather than on the
verdict.) That is the precise failure mode ri-13 exists to make structurally
impossible.

**The runner that produced the baseline is not reproducible in place.**
`run_eval.py:31` and `index_and_query.py:31` both do
`REPO_ROOT = HERE.parents[3]` with the comment
`openspec/changes/<id>/eval -> repo root`. That arithmetic was correct only
before archival. From
`openspec/changes/archive/<date>-<id>/eval/` the same expression resolves to
`<repo>/openspec`. The published baseline cannot be re-derived from the
published artifact. Separately, `index_and_query.py` drives stock `ccc`
(cocoindex-code over sqlite-vec), **not** the Postgres/pgvector v2 path
(`packages/code-search/src/code_search_pkg/query_pg.py`) that actually serves
today — so even a successful run would have measured a stack nothing uses.

**Nothing runs any of it.** `grep` for `run_eval|spike-report|eval-set.yaml`
across `.github/`, `Makefile`, `packages/`, and `skills/` returns only prose
references (`docs/guides/code-search.md:380-386`,
`openspec/specs/code-search/spec.md:129`, `docs/decisions/code-search.md:232`).
There is no CI job, no gen-eval scenario, no skill, no test.

**Nothing measures quality anywhere in this repository.** The 13 test modules in
`skills/tests/context-engineering/` pin schema validity, trigger selection,
determinism, budget arithmetic, and rendered goldens. Every one supplies fixture
hits directly; not one asserts that a returned hit is the *right* hit. A
repo-wide search for `precision@|recall@|ndcg|relevance|utility` finds the
vocabulary nowhere outside the archived spike prose.

**Two independent switches, and ri-13 owns exactly one.**
`CODE_SEARCH_ENABLED` (`agent-coordinator/src/code_search_runtime.py:50`) gates
the coordinator's runtime; production `GET /search/code/status` returns
`{"available":false,"state":"disabled","reason":"disabled","usable_index_count":0}`
purely because it is unset — `coordination_api.py:3418` short-circuits before
touching the database or an embedder. `SEMANTIC_CONTEXT_INJECTION`
(`skills/context-engineering/scripts/semantic_context.py:555`) gates ri-12's
skill-side injection, and ri-12 rejected reusing the first for the second. ri-13
owns the **second** flag's default and nothing else.

**The measurement is newly possible, and that is a change in the world.** The
July waiver rested on `huggingface.co` returning 403. Probed from the intended
measurement host on 2026-07-27: `huggingface.co` **200**, `pypi.org` 200,
`download.pytorch.org` still 403 (torch wheels are on PyPI), `api.openai.com`
421. A pgvector-capable Postgres (`paradedb/paradedb:0.22.2-pg17`) runs healthy
locally. So the `local` / sentence-transformers provider path is *plausibly*
viable for the first time. It is not established: `sentence_transformers` and
`cocoindex` are absent from every active venv, and `packages/code-search[index]`
is not installed anywhere.

**Whether it passes is completely unknown.** No one has ever measured semantic
hit@5 on this repository. This change is designed to be equally correct if the
answer comes back 4/10.

## What Changes

- **Add `packages/context-eval/`** — a standalone, maintained evaluation package
  beside `gen-eval` and `agent-scenarios`. It owns the corpus, the deterministic
  scorers, the fail-closed verdict composer, the report emitter, and a CLI with
  meaningful exit codes. It has its own CI job.
- **Rescue the D9 corpus, retire the D9 runner.** The ten hand-labeled tasks
  T1-T10 move into `packages/context-eval/corpus/` as schema-versioned case
  files with their ids, categories, rationales, and provenance preserved (all 13
  expected files still exist at `748af34c` — verified). `run_eval.py` and
  `index_and_query.py` are not carried forward: one has the `parents[3]` defect
  and hardcodes its thresholds as Python literals (`run_eval.py:159-161`), the
  other measures the wrong backend.
- **Extend the corpus with the labels the new gates need**: `must_touch` files,
  `evidence_spans`, a declared `read_allow`/`deny` scope per case, an owning
  `consumer` from ri-12's six, and expectation records for fail-closed
  regression cases.
- **Add three deterministic scorers**: retrieval relevance (hit@k and
  must-touch coverage against a budget-equalized exact-search baseline), scope
  compliance (zero-tolerance), and coding-context utility (answer coverage,
  evidence density, steps-to-evidence — measured per consumer, with a
  do-no-harm clause).
- **Publish three contracts** —
  `context-eval-report.schema.json`, `context-eval-corpus.schema.json`,
  `context-eval-case.schema.json` — and promote them to
  `openspec/contracts/semantic-context-evaluation/schemas/` **inside this
  change**. The report contract has a closed two-value verdict enum
  (`pass` | `fail`). There is no `skip`, no `blocked`, no `waived`, no
  `unmeasured` verdict. "Could not measure" is representable only as
  `verdict: "fail"` with `fail_reasons: ["unmeasured"]`.
- **Add a blocking Enablement Consistency Gate** (`make semantic-enablement-gate`,
  CI job) that enforces one implication: *the injection default may be enabled
  only if a valid, current, passing report exists at the durable path.*
- **Declare the default explicitly.** `INJECTION_DEFAULT_ENABLED: bool = False`
  becomes a named constant in `semantic_context.py`, so "the default" is one
  reviewable line the gate can read instead of an emergent property of an env
  lookup.
- **Reconcile the unsatisfiable spec requirement.** `code-search`'s
  `Retrieval Quality Gate` is REMOVED and replaced by the ADDED
  `Semantic Context Enablement Gate`, which points at the durable report
  location and the closed verdict enum, and states that a waived, blocked, or
  unmeasured evaluation is not a pass. (Expressed as REMOVED + ADDED rather
  than MODIFIED because the old scenario mandating a change-directory path is
  intentionally dropped, and the successor gates default enablement, not the
  original adoption spike.)
- **Attempt the measurement, and record whatever it says.** One work package
  provisions the environment, builds a real index at an exact revision, runs the
  harness, and commits the report — or commits the recorded apparatus failure.
  A FAIL is a successful outcome of this change.

## What Does Not Change

- **ri-12's runtime behaviour.** `collect_semantic_context` already fails closed
  per request for every non-`ready` state
  (`semantic_context.py:534-545`, `:1296-1300`), already never raises
  (`:1334-1336`), and already renders an exact-search fallback. ri-13 adds
  **zero** runtime code paths to it and duplicates none of its guarantees. The
  only edit to that module is the extracted default constant.
- **`CODE_SEARCH_ENABLED`.** It remains the coordinator's operational switch,
  owned by ri-03. ri-13 records its value at measurement time as a report field
  (a measurement taken with the service disabled measured nothing) but never
  sets, reads at runtime, or gates on it.
- **`SEMANTIC_CONTEXT_INJECTION`'s value.** ri-13 does not flip it. It builds
  the authorization a flip would need.
- **ri-03's HTTP contract.** `openspec/contracts/code-search/v2.yaml` is
  untouched.
- **gen-eval.** No dependency, no new scenario, no threshold change. Issue #306
  (silent denominator shrink) is not fixed here and not built upon.

## Impact

**Affected specs**

- `semantic-context-evaluation` (new capability) — ADDED: the corpus contract,
  deterministic scoring, fail-closed verdict composition, the recorded report,
  per-consumer measurement, scope compliance, and index-tier requirements.
- `code-search` — REMOVED: `Retrieval Quality Gate`; ADDED:
  `Semantic Context Enablement Gate` (its successor, reconciled to a durable,
  machine-checkable report), evaluation provenance, and evidence expiry.
- `skill-workflow` — ADDED: the enablement condition on the injection default,
  and evidence expiry.

**Affected code**

- `packages/context-eval/` (new package, corpus, tests)
- `openspec/contracts/semantic-context-evaluation/schemas/` (three promoted schemas)
- `docs/evaluation/semantic-context/` (durable report location + README)
- `skills/context-engineering/scripts/semantic_context.py` (one extracted constant)
- `.github/workflows/ci.yml`, `Makefile`
- `docs/guides/code-search.md`, `docs/guides/semantic-context-injection.md`

**Explicitly out of scope**

- Flipping `SEMANTIC_CONTEXT_INJECTION` to on. See D11.
- Per-consumer enablement. The flag is global; a per-consumer FAIL blocks global
  enablement. Splitting the flag is a separate change if measurement ever
  justifies it.
- Wiring `work_package_resolver` into `CodeSearchRuntime.create()` (issue #308).
- Fixing gen-eval issue #306.
- Pinning CI's `openspec` version (issue #318).
- Any production deployment or index build in the production coordinator.
- Token-cost measurement beyond the rendered-line proxy. ri-12 chose lines over
  tokens deliberately; ri-13 keeps that unit so the two are comparable.
