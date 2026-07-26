# Design — add-deterministic-context-drift-gates

Selected approach: **A — composed `gate` subcommand, thin CI wrapper** (Gate 1, no
modifications requested).

The gate composes three existing checks and adds the one thing none of them can express
today: a classification that separates *deterministic drift you must fix* from *state
that is merely pending* and *services that were never attempted*.

---

## D1 — The gate is a Python module with a CLI seam, not CI YAML

`skills/project-context-refresh/scripts/gate.py` owns composition and classification.
`cli.py gate` is a thin argument-parsing wrapper; the CI job is a thin `make` call.

Rationale: the acceptance outcome "CI fails with a **precise artifact list**" is a
rendering requirement, and rendering assembled by shell over job output is untestable.
Putting it in Python means the artifact list is unit-tested, and `make context-drift-gate`
reproduces a CI failure verbatim — which matters because the three checks it composes have
three different invocation styles today (a Makefile target, a Python CLI, and a
`git diff --exit-code` shell idiom inside `ci.yml`).

Secondary rationale: `.github/workflows/ci.yml` is contended. `extract-gen-eval-package`
lists it in `write_allow` for three packages and
`gate-drift-with-mirrors-hooks-and-blocking-ci` plans another job in it. Keeping the YAML
delta to one short job minimises the conflict surface.

## D2 — Classification is additive; no enum or schema changes

`decide_outcome` (`orchestrator.py:271-308`) maps deterministic drift, a
`not-configured` optional producer, and a non-succeeded semantic index all onto
`OperationState.DEGRADED`. The fix is **not** to add enum members.

`OperationState` is pinned by `context-refresh-operation.schema.json` (`state` enum) and
`context-refresh-manifest.schema.json` (`refresh_status`). Widening it would be a breaking
contract change for ri-06 records that are already durable and, per ri-07 D9, immutable.

Instead add a pure function alongside `decide_outcome`:

```python
def classify_degradation(
    producer_results: tuple[ProducerResult, ...],
    semantic_index: SemanticIndexReference | None,
    *,
    informational_producer_ids: frozenset[str] = INFORMATIONAL_PRODUCERS,
) -> DegradationBreakdown: ...
```

`DegradationBreakdown` is a frozen dataclass with four disjoint tuples plus the semantic
reference: `blocking_drift`, `informational_drift`, `not_configured`, `failed`. It is
IO-free and total, exactly like `decide_outcome`, and derives entirely from fields that
already exist on `ProducerResult`.

`decide_outcome` keeps its current signature and behaviour. Every existing consumer
(ri-07's `generate`, ri-09's checkpoint, ri-11's future convergence) is unaffected;
callers that want the breakdown ask for it.

## D3 — `openspec.projection` is informational, and that is a normative statement

`openspec.projection` reports 37 failed validations on unmodified `main` — 12
"has a pending merge", 25 "would be created" — tracing to the 31 active changes in
`openspec/changes/`. Its own remediation is "Archive the active change(s) through
cleanup-feature", and its fallback reason says "Projection only: this producer never
writes canonical specs; the sync-point owner performs the merge."

So its `degraded` status does not mean "committed output is stale". It means "an active
change has an unmerged spec delta", which is the correct state for in-flight work. A
repository with zero active changes is the exception, not the rule.

`INFORMATIONAL_PRODUCERS = frozenset({OPENSPEC_PROJECTION})`. Its drift lands in
`informational_drift` and never contributes to a non-zero exit code.

This is written as a spec requirement rather than a constant with a comment, because the
alternative reading — "the gate should fail when specs are unmerged" — is superficially
plausible and would be a reasonable-looking future "fix" that breaks every PR. The
requirement records *why* the classification is what it is.

**Cost, stated plainly.** A genuinely stale committed spec — one that diverges for a
capability with no active change pending — is invisible to this gate. Detecting that needs
correlation between projected capabilities and active changes, which is the reasoning
`cleanup-feature` already owns at archive time. Recorded as out of scope, not as solved.

## D4 — Architecture freshness compares against committed provenance, and fails closed

Two coupled defects:

1. `docs/architecture-analysis/architecture.provenance.json` is neither tracked nor
   gitignored, so there is no committed baseline. `make architecture-check` correctly
   reports `{"status": "invalid", "reasons": [{"code": "PROVENANCE_MISSING"}]}`, exit 1.
2. `_default_architecture_producer` (`orchestrator.py:187-189`) calls
   `provenance.build_provenance(repository, mode="full")` — which *builds* provenance from
   the working tree — then returns `architecture_result_fresh(doc)` unconditionally. It
   reports `fresh` for the same tree `make architecture-check` calls `invalid`.

Fix both:

- Track `architecture.provenance.json` as a committed artifact. The `architecture-refresh`
  spec already requires provenance to be *written* ("Architecture Provenance Evidence");
  this change adds the requirement that it is *committed*, which is what makes a
  revision-based comparison possible instead of an mtime-based one.
- Replace `build_provenance` with `arch_utils.provenance.check_freshness`, mapping
  `fresh → R.fresh`, `stale → R.drift`, and `invalid`/missing → **`R.drift`, not
  `R.not_configured`**.

The last mapping is the load-bearing one. `not-configured` is an *optional owner absent*
signal that the gate must not fail on (D6). Missing or malformed provenance is not an
absent owner — it is an unverifiable claim, and the `architecture-refresh` spec already
has a "Invalid provenance fails closed" scenario. Routing it to `not_configured` would
reintroduce the fail-open behaviour through the classifier instead of the producer.

`refresh-architecture` genuinely not being importable stays `not-configured`. That
distinction is the whole point: absent tooling degrades, unverifiable evidence blocks.

## D5 — Exit codes derive from the breakdown, not from `OperationState`

| Condition | Exit |
|---|---|
| any `failed` producer, or a drifted producer whose finding names no artifact | `1` |
| any `blocking_drift`, no failures — **including unverifiable architecture provenance** | `2` |
| only `informational_drift` and/or `not_configured` | `0` |
| all fresh | `0` |

**Corrected during implementation.** This table originally routed unverifiable
architecture provenance to `1`, which contradicted both D4 (missing or malformed
provenance maps to `R.drift`) and the spec scenario *"Missing provenance blocks"*, which
requires the drift exit code. The spec is normative and the behaviour it describes is the
right one: a missing baseline is fixed by regenerating and committing provenance, which is
drift remediation, not an apparatus repair. Exit `1` is reserved for a producer that
reached **no verdict at all**.

The report keeps `architecture.freshness: "unverifiable"` distinct from `"stale"`, so "no
baseline exists" and "digests disagree" remain separable even though both exit `2`.

**A drifted finding that names no artifact is an apparatus failure.** The requirement
"name every stale artifact by repository-relative path" cannot be satisfied by a finding
that names nothing. Such a result falls back to the producer's registry-declared managed
outputs; with neither available it is reported under `failed` and exits `1`, rather than
being reported as drift with an empty list.

This reconciles an existing inconsistency rather than inheriting it: per-producer
`_exit_code` (`cli.py:78-83`) maps `NOT_CONFIGURED → 1` while `decide_outcome` folds the
same status into `DEGRADED → 2`. Neither is right for a gate. `run_producer`'s
`_enforce_policy` (`registry.py:214-239`) already rewrites a *required* producer's
`not-configured` to `failed`, so a surviving `not-configured` can only come from an
*optional* producer — i.e. external degradation, which by decision must not block.

Both existing entry points keep their current exit codes. The gate is a third caller with
its own documented mapping; it does not redefine theirs.

## D6 — Semantic index is reported as `not-attempted`, a value distinct from `not-configured`

Acceptance outcome #3 asks CI to report semantic unavailability as explicit
external-service degradation. ri-07 D4 and `orchestrator.check()` deliberately never
attempt the index, so that `refresh-check` is green in CI without a database.

Reporting `not-configured` would be a false claim — it asserts a probe found no
configuration. The gate emits a fourth value:

```json
"semantic": { "status": "not-attempted",
              "reason": "deterministic-only gate; semantic availability is not deterministic drift" }
```

`not-attempted` exists only in the gate report schema, never in `SemanticIndexStatus`
(which describes actual probe outcomes). This satisfies "without treating stale semantic
results as current" by construction: the gate makes no currency claim at all.

No Postgres or embedder is added to CI. `openspec/project.md` records that CI excludes
`integration` and `e2e` markers because they need a running DB; a gate that required one
would be the first required check to do so.

## D7 — Context-impact validation is scoped to changed work-package files, never `--strict-legacy`

Measured on `main`: **4 of 70** `work-packages.yaml` files declare a `context_impact`
block. All 70 pass the detector by default; **65 fail under `--strict-legacy`**.

So the gate invokes `validate_context_impact.py` **without** `--strict-legacy`, and only
over `work-packages.yaml` files changed in the diff under test. Two reasons:

- `--strict-legacy` would make the gate red on 65 files on arrival. ri-08's progressive
  enforcement — keyed on whether the block exists — is deliberate, and `--strict-legacy`
  is documented there as the one-flag closer for a *later* migration.
- Repo-wide invocation would report on packages the diff never touched, which is noise a
  blocking gate cannot afford.

**Stated honestly: this arm is currently low-yield.** With 4 declarations in the tree it
can only catch `undeclared` (a package that declared a block but omitted a surface it
touched) and `spurious_rationale`. It is wired because ri-08's learning entry asks ri-10
to wire it and because yield rises monotonically as packages migrate — not because it will
catch much on day one.

One exit-code trap to handle: `validate_context_impact.py` returns `2` for *usage* errors
(missing file, unloadable rules — `validate_context_impact.py:218`, `:224`), which collides
with the drift convention where `2` means drift. The gate must map its `2` to the gate's
`1` (apparatus failure), not pass it through.

## D8 — Read-only-ness is asserted by digesting the checkout, not enforced at runtime

ri-09 D3: "`registry.run_producer` does not *structurally* prevent a `check`-mode adapter
from writing … ri-10 in particular should assert read-only-ness rather than assume it."

A runtime guard (sandbox, read-only bind mount, path allow-list in `run_producer`) was
considered and rejected: it changes the seam every producer and both existing entry points
already depend on, for a property that no current adapter violates. That is a larger
blast radius than the risk warrants, and it belongs to `registry.py`'s own proposal if
ever wanted.

Instead, a test that enumerates `list_producers()` — so it covers producers registered
*after* this change, including ri-07's unbuilt capability producer — and for each one:

1. digests every tracked and untracked path in a fixture checkout,
2. runs the producer in `check` mode against a deliberately dirty worktree,
3. asserts the digest set is byte-identical.

This is strictly stronger than ri-09's version, which asserted the mode argument was
passed and that the *tracked* tree was unchanged. Digesting untracked paths too closes the
hole where a producer writes a scratch file outside its managed outputs.

The test is the enforcement mechanism, and the spec requirement says so, so a future
reader does not mistake the absence of a runtime guard for an oversight.

## D9 — `validate-decision-index` is retired, not duplicated

The existing job (`ci.yml:105-141`) regenerates `docs/decisions/` and runs
`git diff --exit-code`. The `decisions.timeline` producer delegates to the same emitter
(`archive_index.emit_decisions_from_archive`), so keeping both means two freshness
authorities that can disagree — the duplication this change exists to remove.

**One capability must be preserved.** `software-factory-tooling`'s "Per-Capability
Decision Index Emitter" requirement records a blind spot: an orphaned `<capability>.md`
whose content is unchanged is invisible to `git diff` (it is the *presence* that is
stale), which is why the emitter deletes such files. The producer path uses
`tree_diff.diff_trees` with a `deleted` bucket (`tree_diff.py:33-65`), so it detects the
orphan directly rather than relying on the emitter's deletion. A test pins this, because
removing the old job without proving the replacement covers its blind spot would be a
silent regression.

The emitter requirement itself is unchanged — it describes the emitter, not which job runs
it — so no `MODIFIED` delta is needed against `software-factory-tooling`.

**Conditional on D12.** Retirement is only safe once the producer stops reporting a false
positive. Measured on `main`, `validate-decision-index` passes while the producer claims 17
stale files; retiring the correct check in favour of the broken one would trade a green gate
for a permanently red one. D9 and D12 ship together, and the orphan-detection proof (task
4.1) runs against the *fixed* producer.

## D10 — Existing staleness is remediated in an isolated commit

Two artifacts are genuinely stale on `main`: `skills-inventory.md` and
`contracts-inventory.md`. `docs/decisions/` is **not** — it is byte-identical to a fresh
render (18 files, `diff -rq` exit 0), and the producer's claim otherwise is D12's false
positive. Additionally `architecture.provenance.json` must begin being tracked (D4).

They ship in this change as **one commit containing only regenerated output**, separate
from every commit that touches gate code. Rationale: reviewing a generated diff
interleaved with new logic is how generated noise hides real changes, and the roadmap's
fourth acceptance outcome — "a clean checkout at the recorded revision passes regeneration
checks with no diff" — is verifiable only if there is a commit at which that is true.

`docs/decisions/` is regenerated too, **after** D12's emitter fix, and the expected result
is a no-op. Committing a no-op regeneration sounds pointless but it is the positive
demonstration that the fixed emitter and the fixed producer now agree — the alternative is
asserting agreement without ever running it.

Ordering matters: the remediation commit must land **after** D4's producer fix and D12's
emitter fix, because both change what the producers report.

## D12 — The decisions false positive is fixed at the emitter, not the caller

`decisions.timeline` reports 17 stale files on a tree where `docs/decisions/` is provably
fresh. Cause: `emit_decisions_from_archive` interpolates the `archive_root` it was given
directly into every rendered `Source:` back-reference. The CLI resolves `--repo` to an
absolute path before the producer runs, so the rendered output embeds the checkout's
absolute path:

```diff
-- Source: [openspec/changes/archive/2026-05-20-…/session-log.md](/openspec/changes/…) (D1)
+- Source: [/Users/…/agentic-coding-tools/openspec/changes/archive/…](//Users/…) (D1)
```

Measured: relative root → 0 artifacts, absolute root → 17.

**Fix at the emitter**, in `skills/explore-feature/scripts/archive_index.py`: render
`Source:` links relative to the repository root regardless of how `archive_root` was
passed.

A narrower alternative — have `producer_decisions.py` pass a relative `archive_root` — was
rejected on two grounds. It leaves the underlying footgun intact, so
`make decisions --archive-root <absolute>` would still write machine-specific paths into a
*committed* artifact. And it depends on the process cwd being the repository root, which
nothing in the producer contract guarantees; `run_producer` is handed a `repository` path
precisely so it need not care about cwd.

This is why D9's retirement of `validate-decision-index` is conditional on D12 landing:
retiring a correct gate in favour of a producer with a false positive would replace a
passing check with a permanently failing one. The two decisions ship together.

**Generalisation worth recording.** `tree_diff` carries an unstated precondition — the
renderer's output must not depend on its input paths — and nothing enforces it. The
marker-block producers satisfy it structurally. A test asserting that a producer's report
is identical for relative and absolute repository paths would catch this class of bug for
any future tempdir-diff producer, and is cheaper than auditing each renderer.

## D11 — The required-check promotion is a documented manual step, not a claimed one

Branch protection on `main` requires exactly `test`, `test-infra-skills`, `test-skills`,
`validate-specs`, `check-docker-imports`, `secret-scan`. Adding a seventh context is an
admin operation on the repository settings; a PR cannot perform it.

The change therefore ships the job plus the exact `gh api` invocation in
`docs/guides/session-completion.md`, and `tasks.md` carries it as an explicit
**manual** task. Until applied, the gate is "blocking job, not a required context" — the
posture `validate-decision-index` had, which is precisely how `docs/decisions/` drifted
in the first place. Recorded as a known gap rather than described as done.

---

## D13 — The architecture analyzers were repaired, because provenance could not be written otherwise

Added during integration. Task 5.3 could not complete: `make architecture-refresh` failed
before promotion on every run, so no provenance could be written, so the architecture arm
of the gate could never leave `unverifiable`.

Three pre-existing defects, none of them ri-10's doing:

- `MIGRATIONS_DIR` pointed at `agent-coordinator/supabase/migrations`, removed when the
  coordinator moved to ParadeDB. The postgres analyzer errored on every run.
- `TS_SRC_DIR` defaulted to `web`, a directory that has never existed in this repository.
  TypeScript lives under `apps/`.
- The runner was `npx ts-node`, which couples the analyzer to whichever `typescript`
  resolves. There is no root `package.json`, so `node_modules` is unmanaged, and ts-node
  10.9.2 against the resolved typescript 7.0.2 dies inside its own config loader.

**Writing provenance without fixing these was considered and rejected.**
`build_provenance` records `input_fingerprint`, a digest of the *current* sources. Writing
it over artifacts the failing analyzers own — `ts_analysis.json` last regenerated
2026-02-23 — would have bound today's sources to five-month-old output, and
`check_freshness` would then report `fresh`. That is manufacturing a false green: the exact
fail-open behaviour D4 exists to remove, reintroduced by the change that removes it.

**Portability.** The two path corrections live in the repository-specific root `Makefile`,
which `install-manifest.json` does not distribute; the skill keeps its generic defaults
(`src` / `web` / `database/migrations`) and reads env overrides. The runner change and the
new validation live in the skill, so every consuming repository gets them.

**The validation is the durable part.** `analyze_typescript.ts` exits 0 on a missing
directory and writes `Modules: 0, Components: 0, Functions: 0` — indistinguishable from a
repository that genuinely has no TypeScript. That silence is why an all-zeros artifact sat
committed for five months. A configured input root that is absent is now a loud skip that
writes *no* artifact. Recording zero modules from a missing directory misreports a
configuration error as a result, which is the same category of defect as the fail-open
architecture producer — a green signal for work never done.

A repository-level config file (`.architecture.toml`, or a section in an existing config)
would be a tidier home for these three variables than `?=` in a Makefile, and would let the
skill validate them itself. It is not proposed here: it would not have prevented this bug,
since all three mechanisms fail identically without the validation above.

## D14 — Provenance records the roots it analyzed, and the producer and gate share one interpreter

Added after the gate's first CI run. The job went red with `architecture: unverifiable`
while the same tree was `fresh` locally. Two independent defects, both surfaced only
because the gate finally ran somewhere other than the machine that wrote the provenance.

**Defect 1 — the recorded input roots were never the analyzed ones (silent, fail-open).**
The committed provenance read `"input_roots": ["database/migrations", "src", "web"]`. None
of those exist in this repository; they are the fallback defaults in
`default_input_roots()`. `run_architecture.py` builds the `--python-src-dir` /
`--ts-src-dir` / `--migrations-dir` overrides into a **child** environment dict and never
touches `os.environ`, while `build_provenance` read the ambient environment — a flag/env
impedance mismatch across a single function boundary.

This is not cosmetic. `compute_input_fingerprint` hashes the files discovered under the
recorded roots; over roots that do not exist it hashes a constant. Every source edit in the
repository would have left the fingerprint untouched, so the input-change arm of
`check_freshness` could never fire. D13 fixed the *analyzers* while this left the
*freshness check* fail-open — the same defect class, one layer down.

The fix is to pass the resolved roots explicitly: `default_input_roots(env)` now accepts the
mapping the caller owns, and defaults to `os.environ` so existing callers are unchanged.
`test_provenance_input_roots.py` pins the wiring, and separately asserts the repository
invariant that **no recorded root may be missing** — a fingerprint over a missing root is
inert, so a missing root is a blind gate.

**Defect 2 — freshness depended on which interpreter asked (loud, environment-scoped).**
`detect_optional_tools()` reports whether `tree_sitter` is importable *by the calling
process*. `make architecture-refresh` defaulted to `PYTHON ?= python3`; CI runs the gate
with `PYTHON=skills/.venv/bin/python`. Provenance was therefore stamped
`tree-sitter: available=false` and checked against `available=true` — a guaranteed,
permanent disagreement that no amount of regeneration could settle.

The check itself is semantically right: if this environment would regenerate different
bytes, the committed artifacts are not reproducible here, and that *is* drift. What was
wrong is that the producer ran outside the repository's declared toolchain. So the binding
is now explicit — `PYTHON` defaults to `skills/.venv/bin/python` when it exists, falling
back to `python3` on a bare checkout. All 23 `$(PYTHON)` uses in the Makefile are the
architecture pipeline and the context-refresh CLI, i.e. exactly the producer/gate pair that
must agree, so the default is coherent rather than a blanket change.

`skills/uv.lock` pins `tree-sitter==0.25.2` exactly, so local and CI resolve the same
identity. The alternative — dropping tree-sitter from producer identity — was rejected: it
is genuinely output-affecting (`treesitter_enrichment.json`), and removing it would trade a
false positive for a false negative.

**Why this was invisible until CI.** Every prior verification ran the producer and the gate
on one machine, under one interpreter, from one checkout. Both defects are differences
*between* environments, and a single-environment test cannot express them. That is the
argument for the gate being a CI job rather than a local convention.

## Risks and Open Questions

- **A genuinely stale committed spec is invisible** (D3's stated cost). Correlating
  projected capabilities against active changes would catch it; that reasoning lives in
  `cleanup-feature` and is out of scope here.
- **The context-impact arm is near-inert today** (D7) — 4 of 70 packages declare a block.
  Yield depends on a migration this change does not perform.
- **`make architecture-check` runtime in CI is unmeasured.** The check is
  provenance-comparison only, not regeneration, so it should be fast — but it has never
  run in CI. If it proves slow, the fallback is to gate architecture on the committed
  provenance digest alone, which is a narrower comparison.
- **Semantic namespace retention/GC remains open** (ri-09's question). Explicitly declined
  here and left to ri-11, where convergence owns index lifecycle.
- **Two unmerged spec deltas upstream.** ri-05 and ri-09 are `✓ Complete` but unarchived,
  so this change's `project-context-refresh-orchestration` delta is authored against a
  spec whose checkpoint requirements exist only in ri-09's delta. If ri-09 archives first,
  re-verify the delta still applies cleanly.

## Test Strategy

One named invariant per decision, following ri-09's pattern:

| Decision | Invariant | Level |
|---|---|---|
| D2 | `classify_degradation` partitions results into four disjoint buckets; `decide_outcome`'s output is unchanged for every input | unit |
| D3 | `openspec.projection` drift alone yields exit `0` and appears under `informational_drift` | unit |
| D4 | missing/malformed provenance yields `drift` (exit 2), not `not-configured`; absent `refresh-architecture` yields `not-configured` (exit 0) | unit |
| D5 | each of the four exit conditions maps to its documented code | unit |
| D6 | the report's `semantic.status` is `not-attempted` and no indexer is constructed | unit |
| D7 | detector exit `2` (usage error) maps to gate exit `1`; `--strict-legacy` is never passed | unit |
| D8 | every producer from `list_producers()` leaves a dirty checkout byte-identical in check mode, tracked and untracked | integration |
| D9 | an orphaned `docs/decisions/<capability>.md` with unchanged content is detected as drift | integration |
| D10 | at the remediation commit, `gate` exits `0` on a clean checkout | integration |

The gate must **fail on an unmodified pre-remediation tree and pass after remediation**;
a gate that cannot be shown to fail is decoration.

## Task Decomposition Notes

23 sized tasks plus 6 checkpoints across 5 phases: 1 L, 9 M, 10 S, 3 XS, no XL.

**Splits that were performed.** "Track provenance and fix the fail-open producer" became
two tasks (2.6 and 5.3) — they share a dependency but have independent completion criteria
and land in different packages.

**Surviving `and` conjunctions — all eight, each checked against the splitting
heuristic:**

| Task | Verdict |
|---|---|
| 2.5 `DegradationBreakdown` **and** `classify_degradation` | **Keep.** One outcome: the dataclass is the classifier's return type. Splitting yields a type with no constructor. |
| 3.1 gate composition **and** the four exit-code conditions | **Keep.** One test module asserting one behaviour — exit codes *are* composition's observable output. |
| 3.2 report conformance **and** the precise artifact list | **Keep.** The artifact list is the schema field under test; two names for one assertion. |
| 3.3 context-impact scoping **and** usage-error mapping | **Keep.** Both are properties of the same validator invocation, tested from the same fixture. |
| 3.7 `gate` subcommand **and** Makefile target | **Keep.** Two lines of wiring over one function; splitting adds coordination cost exceeding the work. |
| 4.2 add the CI job **and** remove `validate-decision-index` | **Keep, load-bearing.** Splitting creates an intermediate commit with *no* decision-index gate at all. |
| 5.1 merge worktrees **and** run the suite | **Keep.** The merge is not done until the merged tree is green; a merge with a red suite is not a completed task. |
| 5.3 track provenance **and** regenerate stale artifacts | **Keep.** Both must land in the same commit for acceptance outcome #4 to be verifiable — a commit where regeneration produces no diff. |

**Checkpoint cadence deviation.** Phases 4 and 5 carry four tasks before their checkpoint
rather than three. In Phase 4 the interior tasks are XS/S wiring with no shared state to
verify midway; in Phase 5 tasks 5.2–5.4 form one indivisible fail-then-fix-then-pass
sequence whose only meaningful verification point is the end. Recorded rather than
silently taken.
