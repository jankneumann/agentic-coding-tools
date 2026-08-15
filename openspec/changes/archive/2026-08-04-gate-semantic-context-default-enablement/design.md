# Design — gate-semantic-context-default-enablement (ri-13)

Every file, line, and number cited here was verified at `748af34c`.

---

## D1 — The evaluation lives in `packages/context-eval/`, a maintained package

**Decision.** The corpus, the scorers, the verdict composer, the report emitter,
and the CLI live in a new `packages/context-eval/` package. Recorded reports
live in `docs/evaluation/semantic-context/`. Neither location moves.

**Rejected: `openspec/changes/<id>/eval/`.** This is precisely how the D9 gate
died. `run_eval.py:31` computed `REPO_ROOT = HERE.parents[3]` from
`openspec/changes/<id>/eval` — correct at authoring time, wrong forever after
`openspec/changes/archive/<date>-<id>/` added a path segment. The published
baseline is not reproducible from the published artifact. An evaluation whose
own path arithmetic breaks on archival is not evidence, and this repository has
already documented the general lesson in `openspec/contracts/README.md`
("a contract outlives its change... silent archive-drift").

**Rejected: `skills/context-engineering/`.** `skills/` is an install payload —
`install.sh` copies it into `.claude/skills/` and `.agents/skills/` in every
consumer repository. Shipping a 10+-case evaluation corpus, a ripgrep baseline
producer, and a report schema into every downstream repo is the wrong payload.
The *tempting* argument for `skills/` is that `test-infra-skills` runs
`uv run pytest -v` from `skills/`, so anything under `skills/tests/` is
CI-wired for free. D14 buys that property explicitly instead of smuggling it in
through the wrong directory.

**Rejected: `agent-coordinator/evaluation/`.** That tree is gen-eval scenario
data for a deployed service. See D2.

---

## D2 — Standalone package beside gen-eval, not built on it

**Decision.** `packages/context-eval/` depends on `pyyaml` and (optionally)
`jsonschema`. It has **no** dependency on `gen-eval`.

**Rejected: build on gen-eval.** Measured against what ri-13 needs:

| ri-13 needs | gen-eval has |
|---|---|
| Two arms (semantic vs exact-search) compared per case | **Nothing.** No baseline, no A/B, no control arm anywhere in `packages/gen-eval/`. |
| Per-consumer verdicts that can each fail | `per_category` / `per_interface` / `coverage_pct` are computed and gate **nothing** (`__main__.py:395-404` gates on one global `pass_rate` float). |
| An unscorable case to be a FAIL | Invalid scenarios (`generator.py:147` returns `None`), malformed YAML, gather-exceptions, and budget exhaustion all vanish from `verdicts` **without lowering `pass_rate`**. Only `total_scenarios == 0` is guarded. |

The denominator behaviour is disqualifying, not inconvenient: a gate whose whole
thesis is *"could not measure is a FAIL"* cannot be built on a runner where
"could not measure" silently shrinks the denominator. That is filed as issue
#306 by a downstream consumer; ri-13 neither re-files it nor builds on it.

**Rejected: fork gen-eval.** Nothing in gen-eval's assertion vocabulary
(`ExpectBlock`, `SideEffectsBlock`) applies to retrieval scoring.

**Adopted from gen-eval (by imitation, not import):**

- The **versioned contract directory** discipline
  (`packages/gen-eval/src/gen_eval/contracts/` with `VERSION` and
  `CONTRACT_VERSION = 2`, drift-guarded in CI).
- The **vacuous-pass guard** (`__main__.py:389-397`: "A run that evaluated
  nothing is never a pass"). D3 generalizes it from "zero scenarios" to "any
  declared case that was not scored".

**Precedent followed: `packages/agent-scenarios`.** It was built *beside*
gen-eval with its own scenario schema, its own deterministic scorer, an
injectable LLM judge that never overrides the deterministic verdict, and a
findings emitter — path-depending on gen-eval only for `ExpectBlock`. ri-13
follows the placement and the judge rule (D15) and drops even the path
dependency.

**Precedent's warning, also followed:** `grep -n agent-scenarios
.github/workflows/*.yml Makefile` returns **nothing**. The precedent package has
no CI job. Building beside gen-eval without wiring CI reproduces the D9 decay
one level up. D14 makes the CI job a required, verified task rather than an
implied consequence.

---

## D3 — Fail-closed is enforced by the report contract, not by convention

This is the change's load-bearing decision. Five structural mechanisms, each in
the schema or the composer, none in prose:

**1. The verdict enum has exactly two members.**
`context-eval-report.schema.json` declares `verdict: {"enum": ["pass", "fail"]}`.
There is no `skip`, `blocked`, `waived`, `partial`, `unmeasured`, or `n/a`. A
report that could not measure anything is **representable only** as
`{"verdict": "fail", "fail_reasons": ["unmeasured"]}`. The D9 report's actual
shape — `BLOCKED (environment) -> WAIVED (operator decision)` — is
unrepresentable. `fail_reasons` is `required` when `verdict == "fail"` with
`minItems: 1`, so a fail always says why.

**2. The denominator is declared, not derived.**
`corpus.cases_declared` comes from the corpus manifest digest; `cases_scored`
comes from the run. The composer fails with `denominator_mismatch` when they
differ. Every case that raised, timed out, or found no index becomes an
**unscored case** carrying `unscored_reason` — it does not disappear. This is
the direct structural fix for the gen-eval failure mode in D2, applied to
ri-13's own harness rather than to gen-eval.

**3. The gate list is declared, not discovered.**
The corpus manifest names the required gates. The composer takes
`verdict = "pass"` iff **every declared gate is present in the report and every
present gate passed**. A gate that never ran is `missing_required_gate`, a fail.
Every gate object carries `"required": {"const": true}` — the schema makes an
optional gate unwritable.

**4. There is no waiver field.** Not in the schema, not in the CLI, not in the
corpus. An operator who concludes the threshold is wrong must change the
threshold in the corpus manifest — a reviewable diff that the gate's own
`corpus_digest` invalidates the existing report against (D12). The D9 waiver
took one sentence in a markdown file and left every automated check green.

**5. Exit codes distinguish "failed" from "did not run".**
`0` pass, `1` apparatus failure, `2` gate fail, `3` report absent / stale /
schema-invalid. Nothing exits `0` without a schema-valid passing report on disk.

**Rejected: an `--allow-unmeasured` escape hatch.** Every escape hatch in this
repository's history was eventually taken. D9 had one and it was used within
24 hours of the gate being written.

**Rejected: recording the waiver as a first-class outcome for auditability.**
The audit trail is the committed report history plus the git log of the corpus
manifest. Making "waived" a value the machine can read is making it a value the
machine can accept.

---

## D4 — The harness's input contract is ri-12's promoted section schema

**Decision.** `context-eval` scores documents conforming to
`openspec/contracts/code-search/schemas/semantic-context-section.schema.json`
(ri-12's `SemanticContextResult`). It never constructs a `CodeSearchRequest`,
never imports `coordination_bridge`, and never talks to a coordinator.

This gives three properties at once:

- **Decoupling.** The harness scores what a coding job actually receives — after
  local deny re-check, dedup, and budget — rather than what the server returned.
  Scope compliance measured on the raw server response would miss ri-12's own
  defense-in-depth layer, which is the layer that actually protects the agent.
- **Tier independence (D9).** The same scorer scores a live run, a recorded run,
  and a hand-written fixture. Only the *producer* differs.
- **No dependency-direction violation.** `packages/` does not import `skills/`.
  The live producer is one isolated module,
  `context_eval/producers/semantic_runtime.py`, which loads
  `semantic_context.py` via `importlib.util.spec_from_file_location` with the
  path supplied by configuration. One file knows about `skills/`; everything
  else consumes documents.

**Rejected: driving `POST /search/code` directly.** That would measure the
service, not the injected context. Acceptance outcome 1 says "context utility",
and the context is ri-12's rendered section.

---

## D5 — The exact-search baseline is rendered under ri-12's identical budget

**Decision.** Both arms are budget-equalized. The baseline arm runs the fair
keyword-ripgrep algorithm (query tokenized, stopwords dropped, files ranked by
distinct-term coverage then match frequency — the algorithm from
`run_eval.py:86-104`, reimplemented), then renders the top files under the
**same** `ContextBudget` ri-12 applies: `max_hits=8`, `max_files=5`,
`max_total_lines=240`, `max_hit_lines=40`, resolved from the corpus manifest.

**Why.** Comparing an unbounded `rg -l` dump against a section capped at 5 files
and 240 lines measures the cap, not the retrieval. The D9 spike compared
top-5-files to top-5-files, which is fair for hit@k but not for utility, where
"how much irrelevant material did the agent have to read" is the point. A single
declared budget applied to both arms makes evidence density (D7) meaningful.

**The naive phrase baseline is retained** (`rg -il '<query>'`, measured 0/10)
as a third, non-gating column. It documents "the first thing an agent tries" and
is the honest floor, but gating against 0/10 would be trivially winnable.

**Rejected: `rg` invoked through a shell with the query interpolated.** The
producer uses `subprocess.run` with an argument list and `--`, as `run_eval.py`
already did correctly.

---

## D6 — Retrieval-relevance metrics, with thresholds in the corpus, never in code

**Decision.** Three per-case measures, all against hand labels:

| Measure | Definition |
|---|---|
| `hit_at_k` | any labeled `expected_files` entry in the arm's top-k file list. k from the manifest (5). Preserves D9's definition exactly, so the rescued cases stay comparable. |
| `must_touch_coverage` | `\|rendered_files ∩ must_touch\| / \|must_touch\|`. Stronger than hit@k: a task needing three files is not solved by finding one. |
| `wins_over_baseline` | the case is a semantic hit and a baseline keyword miss. This is the spec's "tasks the ripgrep baseline misses" clause, computed, not labeled. |

**Thresholds live in `corpus/manifest.yaml`**, under `gates[].thresholds`, and
are copied into the report's `gates[].thresholds` so a report is
self-describing. `run_eval.py:159-161` hardcoded `>= 7` and `>= 2` as Python
literals; a threshold that lives in code cannot be reviewed as a diff against
the evidence it gates.

**Important nuance on the `>= 2` clause.** `run_eval.py:161` computes
`semantic_wins_over_keyword` as *measured* baseline misses, while
`eval-set.yaml`'s header comment describes it as `category=semantic-win`, a
hand-applied *label*. The two definitions disagree; the spec text
(`code-search/spec.md:122`, "tasks the ripgrep baseline misses") agrees with the
code. The corpus manifest resolves this explicitly: the gate uses the
**measured** definition, and the label is retained as descriptive metadata only.

**No model-id literal appears anywhere.** The embedder identity in the report is
read from the `EmbeddingContract` the run was configured with
(`packages/code-search/src/code_search_pkg/embedding_config.py`) and from
`CodeSearchResponse.index`. Tests assert the fields are *present and
consistent*, never that they equal a particular string.

---

## D7 — "Coding-context utility" is three deterministic per-case measures plus a per-consumer do-no-harm verdict

Acceptance outcome 1 names "context utility" without defining it. Here is the
definition, chosen to be deterministic, per-consumer, and baseline-relative.

**Per case, per arm** (both budget-equalized per D5):

1. **`answer_coverage`** — fraction of the case's labeled `must_touch` files
   present in the arm's rendered file set. *Did the agent get everything it
   needs?*
2. **`evidence_density`** — `useful_lines / rendered_lines`, where `useful_lines`
   are rendered lines falling inside a labeled `evidence_spans` entry. *How much
   of what it got was worth reading?* This is where a right-but-bloated section
   loses, and it is only comparable because of D5.
3. **`steps_to_evidence`** — walking the arm's own ordering, the 1-based index of
   the first rendered hit intersecting an `evidence_span`. If no rendered hit
   ever does, the value is **censored to `max_files + 1`**, never null. *How many
   files must be opened before the answer appears?* Lower is better. A null here
   would be a silent skip, which D3 forbids.

All three are integer/rational arithmetic over sorted sequences. No wall clock,
no `random`, no set iteration in any ranking or scoring path — the ordering key
is a total order over `(-score, file_path, start_line, end_line, content_digest)`,
mirroring ri-12's `rank_key` (`semantic_context.py:235`).

**Per consumer** (ri-12's six: `implement-feature`, `quick-task`,
`iterate-on-implementation`, `debugging-and-error-recovery`, `validate-feature`,
`parallel-review-implementation`), over that consumer's declared case slice, the
verdict is `pass` iff **all** hold:

- `mean(answer_coverage_semantic) >= mean(answer_coverage_baseline) + coverage_margin`
- `mean(steps_to_evidence_semantic) <= mean(steps_to_evidence_baseline)`
- `mean(evidence_density_semantic) >= mean(evidence_density_baseline)`
- `count(cases where semantic covers a must_touch file the baseline misses) >= min_wins`

**Do-no-harm is separate and absolute.** No consumer may regress: if any
consumer's semantic `answer_coverage` is strictly below its baseline, that
consumer fails with `consumer_regression`, and the composed verdict fails. There
is no averaging across consumers. ri-12 kept the `consumer` field precisely so
ri-13 could say "injection helps debugging, hurts review"; averaging would throw
that away on the one metric where it matters most.

**Consequence for `quick-task`.** Its SKILL.md documents that it has no
`change_id`/`package_id`, so every request returns
`out_of_scope`/`no_declared_scope` and no section. Its declared cases are
therefore **fail-closed regression cases**, not utility cases: they assert the
expected fallback and are scored under the scope-compliance gate. Its utility
slice declares zero utility cases and is explicitly marked
`utility_applicable: false` in the manifest — declared absence, not silent
absence. `debugging-and-error-recovery` gets both kinds, because its SKILL.md
documents both the packaged and the ad-hoc path.

**Rejected: a single blended utility score.** A weighted sum lets a coverage
regression hide behind a density improvement. Three independent conditions all
of which must hold cannot.

**Rejected: measuring task success by running an agent.** That is
`packages/agent-scenarios`' job, it requires live vendor CLIs, and it is
non-deterministic. ri-13 measures the *context*, not the agent. If someone later
wants trajectory evidence, it belongs in agent-scenarios with ri-13's report as
an input.

---

## D8 — Scope compliance is a zero-tolerance deterministic gate

Acceptance outcome 1 names scope compliance explicitly. Four measures, all at
index tier 0 (no index, no embedder, no database):

| Measure | Rule |
|---|---|
| `outbound_scope_fidelity` | The request body ri-12 builds carries exactly the case's declared `read_allow`/`deny`. Asserted against `build_request_body` output (`semantic_context.py:1120`). |
| `rendered_scope_violations` | Count of rendered `hits[].file_path` failing the declared scope under `ReadScope` deny-precedence semantics. **MUST be 0.** Not a threshold — any violation fails the gate. |
| `deny_precedence` | For a path matching both an allow glob and a deny glob, the hit is absent from `hits` and present in `omissions` with `reason: "scope_filtered"`. |
| `rejection_honored` | For a case whose declared scope is empty or self-cancelling, or whose recorded response state is `scope_rejected`, the result is `status: "fallback"`, `fallback.trigger: "out_of_scope"`, and `hits: []`. |

**These are measured on adversarial recorded responses.** The corpus includes
responses that *contain an out-of-scope hit* — a hypothetical server leak — so
the gate proves ri-12's local re-check actually fires rather than proving the
server happened to behave. That is measurable only because ri-12 made `search`
an injectable field of `SemanticContextRuntime` (`semantic_context.py:955`) and
existing tests already drive all seven fields
(`skills/tests/context-engineering/test_no_context_trigger.py:84` `_wire()`).

**Known constraint, stated not hidden.** `_normalize_read_scope`
(`semantic_context.py:919`) and `_work_package_namespace` (`:941`) hard-import
`semantic_adapter` via `sys.path` mutation and are **not** injectable. The
scope-compliance producer therefore runs against a real checkout with those
sibling skills present, and the harness records `scope_adapter: "resolved" |
"degraded"` from whether the import succeeded. A `degraded` value is a
`fail_reason` (`apparatus_failure`), not a silent pass — the fallback branch at
`:934-938` returns unnormalized globs, which would make a compliance measurement
mean something different from what it claims.

---

## D9 — Index tier per gate

Three tiers exist in this repository. Each gate names the minimum it needs; a
report produced at a lower tier than a gate declares fails with
`index_tier_insufficient`.

| Gate | Minimum tier | Why |
|---|---|---|
| **Retrieval quality** | **Tier 1 — real index** (`index_repo` console script, `packages/code-search/src/code_search_pkg/cli.py`, against Postgres + a reachable embedder; exit codes `{ready:0, not_configured:2, conflict:3, failed:1}`) | hit@5 over a seeded index with a hand-written 3-dim vector is arithmetic about a fixture, not evidence about retrieval. There is no honest shortcut here. |
| **Coding-context utility (semantic arm)** | **Tier 1** | Utility measures what an agent actually receives; receiving requires real retrieval. |
| **Coding-context utility (baseline arm)** | **Tier 0 — none** | Ripgrep over the checkout. Always runs, always blocking. |
| **Scope compliance** | **Tier 0 — recorded responses** (the `search` seam, or the recorded wire bodies pattern of `skills/tests/coordination-bridge/test_try_code_search.py:60-108`) | Scope is a client-side decision over a response document. |
| **Fail-closed regression** | **Tier 0**, with an optional **Tier 2** confirmation | Tier 2 = `_seed_ready_index` (`agent-coordinator/tests/integration/postgres/test_code_search_v2.py:138-234`), which satisfies every clause of `_USABLE_INDEX_COUNT_SQL` with no embedder contacted. |
| **Enablement consistency** | **Tier 0**, no database | It reads a committed report and a source constant. |

**Provisioning is the plan's own responsibility.** `sentence_transformers` and
`cocoindex` are absent from every active venv and `packages/code-search[index]`
is installed nowhere. The measurement package installs the extra itself and
provisions its own scratch database, following
`packages/code-search/tests/conftest.py:132` (`index_e2e_case`), which copies a
fixture repo, git-inits it, and applies migrations 028/029/030 itself. **It must
not touch the running `paradedb` container** — that belongs to another project's
test tiers, and `localhost:54322` (this repo's documented DSN) is closed.

---

## D10 — Rescue the corpus, retire the runner

**Decision.** The ten hand-labeled tasks are genuinely valuable and their 13
expected files all still exist at `748af34c` (verified individually). They move
to `packages/context-eval/corpus/cases/T1.yaml` … `T10.yaml`, preserving
`case_id`, `query`, `expected_files`, `category`, `rationale`, and the
`ripgrep_baseline` command string, plus a `provenance` block naming the archived
origin. Each is then **extended** with `must_touch`, `evidence_spans`, `scope`,
and `consumer`.

`run_eval.py` and `index_and_query.py` are **not** carried forward:

- `run_eval.py` has the `parents[3]` defect (D1) and hardcodes its thresholds
  (D6). Its *algorithm* is worth keeping and is reimplemented in
  `context_eval/producers/exact_search.py` with the repository root injected as a
  parameter, never derived from `__file__`.
- `index_and_query.py` drives stock `ccc` over sqlite-vec. The v2
  Postgres/pgvector path (`query_pg.py`, migrations 028-030) is what serves
  today. Numbers from the retired path would describe a stack nothing uses.

**Honest limit, and it changes a task.** The recorded aggregate
`{"n":10,"rg_phrase_hit_at_k":0,"rg_keyword_hit_at_k":3}` was measured on the
tree of 2026-07-19. The tree has moved. **Keyword hit@5 has NOT been re-verified
at `748af34c`, and the plan must not assert it.** So the pinning test is split
in two:

1. **Algorithm pinning** (`test_exact_search_algorithm.py`) — runs the keyword
   ranker over a tiny checked-in fixture tree with hand-computed expected output.
   Deterministic, tree-independent, and the real guard against silent
   regressions in the baseline.
2. **Baseline recording** — the run over the actual repository at HEAD writes its
   number into the report as the current baseline. Drift is visible as a report
   diff, not as a test failure. Asserting a number nobody re-measured would be
   exactly the sin this change exists to correct.

---

## D11 — ri-13 builds the authorization; it does not flip the flag

Three questions, kept strictly separate, because conflating them is how a
measurement becomes a formality:

1. **Can the gate be run at all?** For the first time, evidence says probably
   yes. The July waiver rested on `huggingface.co` 403; it now returns 200, and a
   pgvector Postgres runs locally. `download.pytorch.org` is still 403 but torch
   wheels are on PyPI (200). `api.openai.com` returns 421, so the
   `openai_compatible` provider is not a clean path. **Probably viable, must be
   proven by an actual run.**
2. **Does it pass?** **Completely unknown.** Semantic hit@5 has never been
   measured on this repository. The plan is designed to be equally correct at
   4/10.
3. **Does ri-13 flip the flag?** **No.**

**Decision.** ri-13 ships with `INJECTION_DEFAULT_ENABLED = False` and the
Enablement Consistency Gate that makes a future flip safe. Flipping is a
separate, one-line change that the gate will reject unless a valid passing
report exists.

**The change is mergeable with a FAIL.** No verification step, no work-package
`result_key`, and no acceptance criterion anywhere in this plan requires
`report.verdict == "pass"`. The `wp-measure` package's success condition is *"a
schema-valid report exists at the durable path, recording whatever was
measured"*. A change whose acceptance depends on a favourable measurement is a
change that pressures the measurement — and this repository has already run that
experiment once.

**The default becomes an explicit declaration.** Today "default off" is emergent
from `injection_enabled()` returning `env.get(...) in TRUTHY_VALUES`
(`semantic_context.py:579`). ri-13 extracts
`INJECTION_DEFAULT_ENABLED: bool = False` as a module constant and makes
`injection_enabled()` fall back to it when the variable is unset. Behaviour is
byte-identical while the constant is `False`, and the gate now has one
reviewable line to read.

**Rejected: `flags.yaml`.** The registry at repo root is coordinator-side and is
resolved by `agent-coordinator/src/feature_flags.py` via `FF_<NAME>`. Injection
is a skill-side switch with a different owner and a different resolution order.
Two registries with one flag is worse than one constant.

**Rejected: ri-13 also owning `CODE_SEARCH_ENABLED`.** See D17.

---

## D12 — Regression and re-disable: runtime is ri-12's, evidence expiry is ri-13's

Acceptance outcome 4 reads *"a later regression or unavailable exact-revision
index disables semantic injection and restores explicit exact-search fallback."*
That is two different mechanisms and only one of them is new.

**Runtime: already guaranteed by ri-12, and ri-13 adds nothing.** Verified in
source:

- `STATE_FALLBACKS` (`semantic_context.py:534-545`) maps `not_indexed` →
  `("stale", "revision_not_indexed")` and `revision_mismatch` →
  `("mismatched", "index_revision_differs")`.
- `UNKNOWN_STATE_FALLBACK` (`:545`) makes the mapping **total**: a seventh state
  a future coordinator adds degrades to `unavailable`, never to injection.
- `collect_semantic_context` catches everything (`:1334-1336`) and returns a
  fallback rather than raising.
- `skills/tests/coordination-bridge/test_try_code_search.py` already asserts the
  mapping is total over the coordinator's `CodeSearchState` enum.

Adding a second runtime re-disable path would create two authorities for one
decision. ri-13 **cites** these guarantees and **proves** them from the corpus
(fail-closed regression cases assert the exact trigger/reason pair and zero
hits), but implements no new runtime behaviour.

**Evidence expiry: genuinely new, and ri-13's alone.** What ri-12 cannot notice
is that the *justification* for enablement has gone stale. The Enablement
Consistency Gate treats a report as **absent** — and therefore treats enablement
as unauthorized — when any of these hold:

- `report.harness.corpus_digest` != the recomputed digest of `corpus/`
  (the corpus or a threshold changed)
- `report.harness.version` != the installed harness version
- `report.index.embedder.fingerprint` != the fingerprint of the currently
  configured embedding contract (a model or dimension change invalidates the
  measurement — `code-search`'s spec already holds that "a model-name match
  alone is insufficient")
- `report.index.indexed_revision` is not reachable from the evaluated tree
- the report fails schema validation
- `report.verdict != "pass"`

Any of these ⇒ the gate requires `INJECTION_DEFAULT_ENABLED is False`. That is
what "a later regression disables semantic injection" means at the level ri-12
cannot see.

---

## D13 — Reconcile the spec rather than leave an unsatisfiable requirement

`openspec/specs/code-search/spec.md:118-130` is currently unsatisfiable in place:

- Its scenario triggers on *"any task from the vendored-backend work packages
  starts"* — those packages are in
  `openspec/changes/archive/2026-07-20-add-semantic-code-search/`. The trigger
  can never fire again.
- It requires `eval/spike-report.md` "in the change directory" with "an explicit
  pass verdict". Archival moved the directory; the report says `WAIVED`.

**Decision: MODIFY it.** The replacement keeps the substantive threshold (hit@5
>= 7/10 including >= 2 measured baseline misses), moves the artifact to the
durable report path, binds it to the closed pass/fail verdict, and states
plainly that a waived, blocked, or unmeasured evaluation is not a pass and does
not authorize enablement. The trigger moves from "backend work starts" to
"default enablement is claimed" — the decision that is actually still ahead.

`docs/guides/code-search.md`'s `## Retrieval-quality gate` section and
`docs/guides/semantic-context-injection.md` are updated to point at the durable
procedure in the same change. (Cited by heading, not by line range: the edit
that rewrites the section is itself what invalidates any line number written
here.)

`docs/decisions/code-search.md:232` is **not** edited, and that is deliberate.
It is a derived artifact, regenerated by `make decisions` from
`openspec/changes/archive/`, so a direct edit is silently overwritten — the
drift tracked as issue #157. Its defect is worse than staleness: it claims
"a non-PASS holds the gate" while its own source (`spike-report.md:13-14`)
records that the gate was waived and implementation proceeded. Correcting it
requires a superseding decision or a fix to the archived source, which is
outside this change.

**Rejected: leave it and add a parallel requirement.** Two gates for one
question, one of them permanently unsatisfied, is how `docs/decisions/` drifted.

**Rejected: REMOVE it.** The threshold is good and was independently reasoned.
Deleting the only quality bar this repository ever wrote for semantic search,
in the change whose job is to enforce it, would be indefensible.

---

## D14 — CI wiring: what blocks, what is advisory, and what each fails on

Four checks. The constraint *"every new check must FAIL on an unmodified tree"*
is honoured literally where it can be and answered explicitly where it cannot.

| Check | Blocking? | Fails on an unmodified tree today? |
|---|---|---|
| **A. `context-eval` package tests** (new CI job) | Yes | **Yes.** Includes `test_spec_gate_artifact.py`, which resolves the artifact the `code-search` Retrieval Quality Gate requirement points at and asserts a machine-readable verdict from the closed enum. Today it resolves to an archived markdown file whose verdict is `WAIVED`/`UNMEASURED`. |
| **B. Baseline reproducibility** (part of A) | Yes | **Yes.** `test_repo_root_resolution.py` asserts the baseline producer's repository root contains `.git` and `openspec/`. Run against the archived layout the D9 arithmetic produced (`parents[3]` → `<repo>/openspec`), it fails. It is the executable form of the defect in D1. |
| **C. Corpus integrity** (part of A) | Yes | **Yes.** Asserts every declared consumer has a declared case slice with an explicit `utility_applicable` value, and every labeled path exists. Zero of ri-12's six consumers are covered by anything today. |
| **D. Enablement Consistency Gate** (new CI job + `make semantic-enablement-gate`) | Yes | **No, and deliberately so.** Its job is to fail when someone enables injection without evidence. On a tree where nobody enabled anything it is correctly green. **The substitute is a mutation proof, not an observation:** `test_enablement_gate_mutation.py` constructs the tree state (constant `True`, no report / stale report / failing report / schema-invalid report) and asserts the gate exits non-zero for each. That is a test that fails if the gate is decoration. |

**Blocking-vs-advisory sequencing.** Jobs A and D are added as blocking jobs in
this change; adding them to branch protection's required contexts is a
repository-settings operation a PR cannot perform. Following
`docs/guides/session-completion.md:47-67` and the `add-skills-lint-ci-gate`
precedent ("fix the tree, then gate blocking"), the plan records the exact
one-shot `gh api` call as a **manual** verification step and states that until it
is applied these are "blocking jobs, not required contexts".

**Version pinning.** Both new jobs pin the versions of anything they install, so
their semantics arrive from a reviewable diff rather than from a registry's
`latest`. This repository already has one gate that does not
(`ci.yml:92` installs `@fission-ai/openspec` unpinned, issue #318) and one that
learned the lesson the hard way (`skills/pyproject.toml`'s explicit ruff
`select`). The new jobs follow the second.

**The live measurement is never a CI job.** It needs a real embedder, a real
database, and minutes of indexing. It runs out-of-band and its *output* — the
committed report — is what CI reads.

---

## D15 — An LLM judge is admissible, and structurally cannot affect the verdict

**Decision.** The report schema permits an optional `judge` block: an advisory
qualitative review of a rendered section. It follows `agent-scenarios`'
judge-backend shape — `is_available()` / `complete(prompt, system)` — and skips
cleanly when no backend is injected.

**Stronger than "never overrides".** `agent-scenarios`' rule is that the judge
never overrides the deterministic verdict. ri-13 makes that structural: the
verdict composer's input type has **no judge field at all**. `compose_verdict()`
receives the scored cases and the declared gates; the judge block is attached to
the report *after* the verdict is computed, by the emitter. It is impossible to
write code that lets the judge change the outcome without changing the
composer's signature — a reviewable diff.

An absent judge is never a fail reason. It is not a gate.

---

## D16 — Determinism obligations, enforced by test

Every ranking and scoring path is a pure function of `(documents, corpus,
thresholds)`:

- **No wall clock.** The report's only timestamp is an explicit `--as-of` input
  recorded verbatim; nothing branches on it. `test_no_wallclock.py` greps the
  scoring modules for `datetime.now`, `time.time`, and `date.today`.
- **No `random`.** Asserted by import inspection over `context_eval.scoring.*`.
- **No set iteration.** All ordering is by explicit sort key, mirroring ri-12's
  `rank_key` total order. `test_determinism.py` follows ri-12's method rather
  than the weak "run it twice" form: a fixture with deliberate ties (equal
  scores, same file, reversed input) is asserted against a hand-derived expected
  order, then shuffled with a seeded RNG and asserted to produce the identical
  output.
- **No model-id literals.** Asserted by `test_no_model_literals.py`. Identity is
  always read from the embedding contract or the response.

---

## D17 — `CODE_SEARCH_ENABLED` is a recorded precondition, not ri-13's to own

**Decision.** ri-13 constrains only `SEMANTIC_CONTEXT_INJECTION`. It never sets,
gates on, or changes the default of `CODE_SEARCH_ENABLED`.

**Why they must stay separate.** ri-12 rejected reusing the coordinator flag for
injection because enabling the service would necessarily enable injection into
every coding job — exactly the coupling ri-13 exists to break. Taking ownership
of both flags in ri-13 would re-create that coupling from the other end.
Enabling injection while the service is disabled is already harmless: ri-12
returns `unavailable`/`capability_absent` and the job proceeds by exact search.

**But it is a recorded precondition of the measurement.** Production
`GET /search/code/status` returns
`{"available":false,"state":"disabled","reason":"disabled","usable_index_count":0}`
purely because the variable is unset — `coordination_api.py:3418` short-circuits
before touching the database or an embedder. A retrieval measurement taken in
that state measured nothing at all. So the report carries
`environment.code_search_enabled`, and the composer fails the retrieval gate with
`service_disabled_during_measurement` when it is false. This is a fail-closed
clause, not a flag ri-13 owns.

---

## Recorded outcome — phase 6, 2026-07-31 (D11)

> **Superseded in part on 2026-08-01.** Two of the four gate rows below describe
> an artifact HEAD no longer reproduces, and defect 4 has since been fixed. Read
> [Amendment — 2026-08-01](#amendment--2026-08-01-the-report-regenerated-at-head)
> with this section; the corrections are inline and flagged where they apply.

D11 said the answer to *"does it pass?"* was **completely unknown** and that the
plan was designed to be equally correct at 4/10. The answer is now recorded, and
it is not a number.

**Verdict: `fail`.** `fail_reasons: ["unmeasured", "denominator_mismatch",
"index_tier_insufficient"]`, at `docs/evaluation/semantic-context/report.json`,
against `748af34c`, corpus digest `64170669…`, harness `context-eval 0.1.0`,
CLI exit `2`. `INJECTION_DEFAULT_ENABLED` stays `False`, which is where ri-13
always intended to leave it.

**D11's first question — "can the gate be run at all?" — is answered NO, and the
reasons are specific.** The July 2026 blocker is genuinely gone: `huggingface.co`
served `sentence-transformers/all-MiniLM-L6-v2`, `torch` resolved from PyPI, the
`local` provider was constructed and produced a real contract fingerprint
(`f5ae15d3…`), and a scratch ParadeDB took migrations 028/029/030 without
complaint. Every one of D11's environmental doubts cleared. What blocks the
measurement is five defects in this repository's own code, four of which no
amount of environment would have fixed.

**Semantic hit@5 remains unmeasured, and the honest statement is that it has
never been measured on this repository.** It was not measured and found wanting,
and no operator judgement was substituted for the missing number — the retrieval
and utility gates never had an index to query.
`retrieval_quality` and `coding_context_utility` both declare `min_index_tier:
live` and both received `none`.

### What was measured

One thing, and it held. The four corpus cases carrying a genuinely non-`ready`
recorded response — `not_indexed`, `revision_mismatch`, `scope_rejected`,
`reindexing_in_background` — each produced exactly the `(trigger, reason)` pair
they declare and rendered zero hits. That is D12's claim about ri-12's runtime
("already guaranteed by ri-12, and ri-13 adds nothing") verified from the corpus
rather than cited from source, including the total-mapping property: an
unrecognized seventh state degraded to `unavailable`/`unknown_state`.

`fail_closed_regression` still fails at 0.571 against a threshold of 1.0. Its
denominator is all seven scored cases; the three that failed are the `ready`
adversarial cases, which failed for the apparatus reason below rather than
because any fail-closed guarantee broke.

> **Corrected 2026-08-01.** With defect 4 fixed, this gate measures **1.0 (7/7)**
> and passes. The 0.571 was an artefact of the harness and never a behavioural
> failure of ri-12 — the sentence above already said the three failures were not
> a broken guarantee, and the regenerated report now records that fact as a
> number rather than as a caveat.

### The five defects, and what each would take

None is a threshold anyone could argue about, and none is in `wp-measure`'s
`write_allow`. Listed in the order they block a measurement.

1. **`.cocoindex_code/settings.yml` is required and does not exist.**
   `indexer_pg.py:211` calls `load_project_settings(project_root)`, which raises
   `FileNotFoundError` for `<repo-root>/.cocoindex_code/settings.yml`. Nothing in
   this repository tracks that file, `index_repo` does not create one, and
   `docs/guides/code-search.md`'s indexing procedure does not mention it. *Would
   take*: either a checked-in project settings file with a documented schema, or
   `index_repo` synthesizing settings from the CLI flags it already takes. Until
   then the documented write path cannot complete here at any scale, and every
   `packages/code-search` test that exercises it is either mocked or marked
   `requires_embedder`.
2. **The secret scanner's operation deadline is spent on work it does not do.**
   `cli_runtime.py:108` builds `LocalSecretScanner()` with the default
   `operation_timeout_seconds=30.0`; `_operation_deadline` is set at the first
   `scan_bytes` and never reset, and one instance serves both source-manifest
   planning and the per-chunk scan at `indexer_pg.py:205`, i.e. it spans model
   loading and embedding. Measured: 0.44 s to scan all 1367 eligible files
   directly, versus `scanner_timeout` after 456 files and 46.1 s in the real
   run. *Would take*: a deadline per scanning *phase* rather than per scanner
   instance, or a scanner whose clock only advances while it is scanning. Not
   reachable from the CLI, so there is no operator workaround.
3. **`credential_assignment` matches identifier text.** The rule fires on
   `token = authorization.partition(" ")` and `api_key = api_key_resolver.resolve(`
   — seven tracked files, none of them a corpus target. *Would take*: an
   entropy or charset condition on the matched value, or an allowlist. Low
   severity relative to 1 and 2, but it is a fail-closed rule that a repository
   cannot satisfy without enumerating exclusions by hand.
4. **[FIXED by `ddc30be2`] The harness's scope stand-in does not implement
   ri-12's scope protocol.**
   `producers/semantic_runtime.py:117-123` defines `_ResolvedScope` with
   `read_allow` and `deny`; `semantic_context.py:454` calls
   `scopes.allows(hit.file_path)`. Every case reaching the `ready` path raises
   `AttributeError`, is swallowed by ri-12's never-raises guarantee
   (`semantic_context.py:1355-1356`), and is recorded as
   `unavailable`/`unknown_state`. **This is why `scope_compliance` reports a
   pass that is not evidence**: the three adversarial responses render nothing,
   and a gate counting rendered violations counts zero — the exact tautology D8
   introduced those cases to prevent. *Would take*: `_ResolvedScope`
   implementing `allows()` by delegating to ri-09's `ReadScope`, plus a test
   that asserts a rendered arm is non-empty for `ADV-LEAKED-HIT` before the
   violation count is read. A gate that can only be satisfied by an empty arm
   should not be satisfiable at all.
5. **Two structurally scorable cases are unscorable.**
   `FC-QUICK-TASK-NO-DECLARED-SCOPE` and `FC-DEBUG-ADHOC-NO-SCOPE` declare an
   empty read scope precisely so ri-12 short-circuits at
   `out_of_scope`/`no_declared_scope` before the search seam, so they need no
   recorded response — but `SemanticRuntimeProducer.render` rejects any case
   with `response is None` outside `--live` before running ri-12. *Would take*:
   deciding on the case's declared scope rather than on the presence of a
   recorded response.

Two adjacent observations, neither a defect with an owner yet. `--live` is a
per-*producer* switch rather than per-case, so a live run puts the six cases
whose entire content is a recorded response onto the wire too; there is no
configuration of the current CLI that measures T1-T10 live while keeping the
fail-closed and adversarial cases on their fixtures. And every recorded response
hard-codes `source_revision: 748af34c`, so a run declaring any other evaluated
revision turns all three adversarial cases into `mismatched` fallbacks — which
silently produces the same vacuous `scope_compliance` pass by a second,
independent route.

### What this outcome does not license

It does not license re-running until the numbers improve. Every gate above
failed for a named structural reason, and no repetition of the same command
changes any of them. It does not license relaxing a threshold: no threshold was
approached, let alone missed by a margin. And it does not license enabling the
default — the Enablement Consistency Gate reads `verdict != "pass"` as an
expiry condition (D12), so this report withdraws authorization rather than
granting it, exactly as designed.

The plan said the change is mergeable with a `fail`, and it is. What ri-13
shipped is the apparatus that makes the next attempt legible: the failure above
is a list of five citable defects instead of one sentence in a markdown file.

---

## Amendment — 2026-08-01: the report regenerated at HEAD

The artifact committed on 2026-07-31 was produced before `ddc30be2` implemented
`_ResolvedScope.allows()`. HEAD does not reproduce it. Re-running from the
report's own recorded inputs — index tier `none`, evaluated revision `748af34c`,
the recorded embedder identity; no live index, no database, no embedder — moves
two of the four gate rows:

| Gate | 2026-07-31 | 2026-08-01 |
|---|---|---|
| `retrieval_quality` | fail, nothing measured | unchanged |
| `coding_context_utility` | fail, 0 cases over 5 consumers | unchanged |
| `scope_compliance` | pass, over three EMPTY adversarial arms | pass, over two injected arms (2 files / 1 file) and one `all_hits_scope_filtered` fallback |
| `fail_closed_regression` | **fail, 0.571 (4/7)** | **pass, 1.0 (7/7)** |

The top-level verdict, its three `fail_reasons`, `cases_declared: 19`,
`cases_scored: 7` and the index tier are all unchanged, so the enablement
decision is unaffected: `INJECTION_DEFAULT_ENABLED` stays `False` because the
recorded verdict is `fail`, and D11's second question is still unanswered because
semantic hit@5 still has no index to be measured against.

**Regenerated, not annotated.** Two of the committed rows were false statements
about ri-12: a 3-of-7 fail-closed behavioural failure that did not happen, and a
`scope_compliance` pass whose own README described it as vacuous. Leaving a
published artifact the committed code cannot re-derive is the failure the
evaluation README's *"Why the report lives here"* exists to end, and annotating
would have preserved it with a footnote. Nothing was tuned, no run was repeated
selectively, and no threshold or corpus case was touched.

**Why nothing caught this, and what now does.** Both the corpus digest and the
declared harness version were unchanged across `ddc30be2`, so every D12 expiry
condition of the day reported the evidence as current. That gap was issue #337:
the harness version is a string somebody writes into `pyproject.toml`, and it was
the only expiry condition an operator could satisfy by assertion. The report now
carries `harness.fingerprint`, a digest over the harness's own source built
exactly as `corpus_digest` is built over the corpus, and the gate compares it as
`harness_fingerprint_current`. A behavioural change to the measuring code now
invalidates its own evidence, which is what D12 always claimed.

**A note on the baseline arm.** `rendered_files` differ slightly from the
previous artifact for a second, unrelated reason: the exact-search arm reads the
working tree rather than `--evaluated-revision`, so files this change itself added
enter the baseline. That is a separately recorded finding about overstated
provenance, not an effect of the fix above. `--searcher` is not recorded in the
report; `ripgrep` and `tracked` were both run and produce byte-identical results
for all seven scored cases, so the unrecorded choice is immaterial to the
recorded content.
