# Rescope architecture freshness to on-demand

Architecture layer: **Governance** (drift gate), **Execution** (refresh-architecture pipeline).

## Why

The deterministic context drift gate (`add-deterministic-context-drift-gates`, "ri-10")
composes three arms and exits non-zero when any reports blocking drift. One of those arms —
architecture freshness — is structurally unable to be a cross-checkout invariant, and in
the first consumer repository to exercise the gate at a sync point it reported blocking
drift on every convergence pass for a week without a single step in the workflow that
could have cleared it.

### Measured baseline — what actually happened in `agentic-content-analyzer`

Three merge passes (2026-08-25, -26, -27) each ended in `refresh_status: degraded` with the
warning `staged architecture refresh failed (exit 2); the architecture producer will report
drift for this revision`. Root-causing that produced four independent findings, each of
which alone keeps the gate red:

1. **The refresh could not run.** `refresh_architecture.sh` treats a missing
   `MIGRATIONS_DIR` as `fail "postgres_analyzer"`, which increments `ERRORS`, which blocks
   promotion in `--staged` mode, so provenance is never written. The consumer uses
   Alembic (75 `.py` revisions, zero `.sql`), so the Postgres analyzer — which globs
   `*.sql` and exits 1 on none — failed on every run. The TypeScript analyzer *in the
   same file* already treats a missing input root as `skip`, with a comment explaining
   why silently recording zero results is worse. The two analyzers disagree about what
   "nothing to analyze" means.

2. **Provenance cannot be the committed baseline the spec requires.** The
   `architecture-refresh` spec says provenance "SHALL be tracked in version control" and
   that a clean checkout at the recorded revision is fresh. But `check_freshness` returns
   `fresh` only when *every recorded artifact is present with a matching digest*, and the
   artifacts are 36 MB (`architecture.graph.json` alone is 23 MB). The consumer gitignores
   the whole directory — provenance included — which is the only sane choice, and which
   makes freshness a **per-machine** property: fresh on the machine that ran the refresh,
   `drift` on every other clone and in every CI job. Committing provenance alone would be
   worse: a clone would then report `stale` (digests disagree) instead of the honest
   `missing`.

3. **The gate has never gated anything.** In the consumer it is wired into no CI workflow.
   It runs inside `main_convergence.py` only, whose outcome table explicitly says a
   convergence exit code "never means a merge failed". So the blocking classification
   produced a red status that blocked nothing and informed no one — the worst of both.

4. **Three enrichment layers skip silently because of an unrelated grammar.**
   `arch_utils/interpreters.py` requires *both* `tree_sitter` and `tree_sitter_sql`. The
   consumer's venv has tree-sitter with the Python and TypeScript grammars; only the SQL
   grammar is absent. Because the resolver answers one yes/no question for the whole
   pipeline, a dependency of the SQL analyzer disables `treesitter_enrichment`,
   `comment_linker`, and `pattern_reporter` for Python and TypeScript too — the layers
   that give the artifacts their analytical depth.

The spec's own rationale for the committed-baseline requirement reads: *"Without a
committed baseline the read-only check has nothing to compare against and fails closed on
every clean checkout, which makes architecture freshness unusable as a gate."* That
sentence is a correct prediction of finding 2. The premise it rests on — that the baseline
can be committed — does not hold for artifacts of this size.

### What the artifacts are for

Seven skills read `architecture.graph.json`, `architecture.summary.json`, or
`parallel_zones.json`: `explore-feature`, `plan-feature`, `validate-feature`,
`tech-debt-analysis`, `validate-flows`, `validate-packages`, and the ri-09 checkpoint. Every
one of them is a *consumer that needs the artifacts to be current when it reads them*.
None of them needs a reviewer to have been blocked at merge time. The artifacts are a
regenerable local analysis cache, and the workflow already has a home for exactly that
posture: ri-09's checkpoint, whose module docstring says *"drift is data, and turning it
into a build failure belongs to the drift-gate capability."*

## What Changes

**The architecture arm of the drift gate moves from blocking to informational, and
freshness becomes ensure-on-demand at the consumers.** The gate keeps blocking on the arms
that check *committed* derived artifacts — `docs/decisions`, the OpenSpec projection, the
API contracts inventory, the documentation inventory, and work-package context impact —
because staleness there is a repository-visible inconsistency that every clone sees
identically. Architecture is reclassified because staleness there is machine-local by
construction.

Concretely:

1. **`run_architecture.py --ensure`** — a new mode composing the two that exist: run
   `--check`; if not `fresh`, run `--staged`. Exit 0 when the artifacts are current on
   return, whichever path was taken. Byte-stable when already fresh (no write, no
   provenance change). This is the entrypoint consumers call.
2. **Consumers call `--ensure` before reading.** The seven skills above gain one call at
   the top of their artifact-reading step. `checkpoint.py` keeps its read-only posture
   (D3 of ri-09) and does not call it.
3. **The gate reports architecture as informational, never blocking.** The
   `architecture` block in the gate report is retained unchanged in shape — freshness,
   provenance state, delta — so a reader can still see it is stale; it simply no longer
   contributes to `blocking_drift` or to exit code 2. Provenance missing/malformed is
   still surfaced as `unverifiable`, keeping "no baseline" distinguishable from "digests
   disagree" (ri-10 D4's *reporting* distinction survives; its *blocking* consequence
   does not).
4. **The committed-baseline requirement is rewritten as a local-baseline requirement.**
   Provenance lives beside the artifacts it describes and shares their tracking status;
   the spec stops requiring it to be committed and stops promising that a clean checkout
   is fresh. A clean checkout is *unverified* until `--ensure` runs, which is the truth.
5. **Inapplicable analyzer input is a skip, not a failure.** The Postgres analyzer adopts
   the TypeScript analyzer's verdict for a missing or empty input root: warn loudly, skip,
   write no artifact. This alone lets the staged refresh promote in Alembic repositories.
6. **Optional-tool resolution is per-analyzer.** `interpreters.py` reports which grammars
   an interpreter can import, and each stage requires only its own: the SQL analyzer needs
   `tree_sitter_sql`; the Python/TypeScript enrichment stages need `tree_sitter_python`
   and `tree_sitter_typescript`. Provenance records the per-grammar identity so the
   ri-10 D14 invariant — pipeline and provenance cannot disagree — is preserved at finer
   grain.
7. **An ORM schema source for the SQL analyzer.** Repositories whose migrations are code
   (Alembic) get `SCHEMA_SOURCE=sqlalchemy`: a small dumper emits `CreateTable` DDL for
   every table in the declared `MetaData` into the staging directory, and the existing SQL
   analyzers consume it unchanged. Measured in the consumer: 40 tables, 35 KB, no database
   connection. Migration-chain replay (`alembic upgrade --sql`) was evaluated and
   rejected — 16 of 75 historical migrations read query results inside `upgrade()`, which
   is illegal in offline mode, and patching history for a side tool is the wrong trade.

**Not BREAKING** for consumers of the gate's exit code in the direction that matters: a
gate that exited 2 solely on architecture drift will now exit 0. Anything that exited 0
before still does. The report schema is unchanged; the `blocking_drift` list simply never
contains `architecture`.

### Decided at discovery

- **This is a sibling of `rescope-context-drift-enforcement` (PR #426), not a
  duplicate.** #426 makes the gate *attributable* — pinning the base ref, classifying
  committed-artifact drift as inherited or introduced, and making the blocking verdict
  event-aware — so that it can be promoted to a required check. It modifies four
  requirements in `project-context-refresh-orchestration` and leaves *Architecture
  freshness fails closed on unverifiable provenance* untouched. This change modifies
  exactly that requirement and nothing #426 modifies. The two are complementary, and
  #426 corroborates this one twice: its dependabot auto-remediation job excludes the
  `architecture` producer by name ("it needs tree-sitter and writes megabytes"), and its
  §3 establishes that a whole-tree freshness claim is only well-defined at `main`'s tip —
  which for architecture, whose baseline lives on one machine, means it is not
  well-defined on any other checkout at all.
- **Sequencing: this lands after #426.** Both touch `gate.py`; #426's diff there is
  +621 lines and this one is a classification change of a few lines. Rebasing the small
  change onto the large one is the cheap direction.
- The consumer-side make targets (`architecture-refresh`, `context-drift-gate`,
  `decisions`) and the consumer's local copy of the Postgres-skip fix are already in
  `agentic-content-analyzer` PR #512. Item 5 upstreams that fix so the installer stops
  overwriting it. Items 1–4, 6, and 7 have no consumer-side counterpart yet.

## Approaches Considered

### Approach A — Reclassify architecture as informational; ensure-on-demand at consumers — **Recommended**

Described above. Keeps every ri-10 mechanism (check mode, staged promotion, provenance
digests, the report block) and changes only *who is responsible for freshness*: the reader,
at read time, instead of the gate, at merge time.

### Approach B — Commit the artifacts so the baseline really is committed

Makes the existing spec true. Rejected: 36 MB of regenerated JSON on every source change
is not a diff anyone reviews, `architecture.graph.json` would dominate the repository's
history within weeks, and the consumer already made the opposite call in `.gitignore`
with the comment "regenerate via /refresh-architecture".

### Approach C — Commit provenance only, gitignore the artifacts

Rejected on the evidence in finding 2: `check_freshness` needs the artifacts to be present
to verify digests, so a clone with provenance and no artifacts reports `stale`, which is a
*less* accurate signal than `missing`.

### Approach D — Keep architecture blocking; fix only the pipeline defects (items 5–7)

Would make the gate go green on the one machine that runs the refresh and stay red
everywhere else. That is finding 2 restated; it does not address the moving target.

## Impact

| Capability | Delta | Change |
|---|---|---|
| `project-context-refresh-orchestration` | `specs/project-context-refresh-orchestration/spec.md` | MODIFIED: *Architecture freshness fails closed on unverifiable provenance* → informational. ADDED: *Architecture freshness is ensured by consumers on demand* |
| `architecture-refresh` | `specs/architecture-refresh/spec.md` | MODIFIED: *Architecture provenance is a committed baseline* → local baseline. ADDED: *Ensure mode*, *Inapplicable analyzer input skips*, *Per-analyzer optional-tool resolution*, *ORM schema source* |

Code touched (all under `skills/`): `project-context-refresh/scripts/gate.py`,
`refresh-architecture/scripts/run_architecture.py`,
`refresh-architecture/scripts/refresh_architecture.sh`,
`refresh-architecture/scripts/arch_utils/interpreters.py`,
`refresh-architecture/scripts/arch_utils/provenance.py`, a new
`refresh-architecture/scripts/dump_sqlalchemy_schema.py`, and one call site in each of the
seven consumer skills.

Supersedes ri-10 **D4** (blocking consequence only) and narrows **D13/D14** (per-analyzer
tool identity). Does not touch ri-09; the checkpoint's advisory posture is the model this
change generalizes.

## Known conflicts

- **`rescope-context-drift-enforcement` (PR #426, open, 51/51 tasks).** Overlaps on
  `skills/project-context-refresh/scripts/gate.py` and on the
  `project-context-refresh-orchestration` spec, but on disjoint requirements (see
  *Decided at discovery*). Resolution: this change lands second and is rebased onto #426.
  If #426's inherited/introduced attribution is in place first, architecture drift simply
  never reaches the attribution step, because it is never in `blocking_drift`.
- `add-cross-harness-flow-display` and `add-atomic-harness` are active and touch skills;
  neither touches these files.

## Out of Scope

- Wiring `context-drift-gate` into any CI workflow. It is not wired today; this change
  makes the remaining (committed-artifact) arms *worth* wiring, and leaves that decision
  to the consumer.
- Making the consumer's `alembic check` a CI job. The ORM schema source (item 7) reads the
  *intended* schema; `alembic check` is what makes it trustworthy. Consumer concern.
- Any change to ri-09 checkpoint semantics.
