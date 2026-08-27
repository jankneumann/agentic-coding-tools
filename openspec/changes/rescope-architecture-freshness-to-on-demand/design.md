# Design — rescope-architecture-freshness-to-on-demand

Decisions are numbered D1–D8. Where a decision reverses or narrows one from
`add-deterministic-context-drift-gates` (ri-10), the ri-10 decision is named explicitly so
the supersession is visible to `docs/decisions/` readers rather than implied.

## D1 — Freshness responsibility moves to the reader, at read time

**Decision.** Architecture artifacts are a regenerable local analysis cache. The party
that needs them current is the skill about to read them, so that skill ensures freshness
immediately before reading, via `run_architecture.py --ensure`. No sync point, gate, or CI
job is responsible for keeping them fresh on anyone else's behalf.

**Why.** Every consumer identified (`explore-feature`, `plan-feature`, `validate-feature`,
`tech-debt-analysis`, `validate-flows`, `validate-packages`) reads the artifacts in the
same process that would run the refresh, on the same machine, against the same working
tree. That is the one place where "is this fresh?" has a single correct answer. A gate at
a sync point answers the question for a different machine at a different time, and — per
D2 — cannot answer it correctly at all.

**Consequence.** Freshness is guaranteed at the moment of use and asserted nowhere else.
A checkout that no skill has read from has *unverified* artifacts, and the gate says so
(D3) without failing.

## D2 — Provenance is a local baseline, not a committed one (supersedes ri-10 D4's blocking consequence)

**Decision.** `architecture.provenance.json` lives beside the artifacts it describes and
shares their version-control status. The spec stops requiring it to be committed and
stops promising that a clean checkout at the recorded revision is fresh.

**Why.** `check_freshness` returns `fresh` only when every recorded artifact is present
with a matching digest — the correct definition, and the one that makes provenance
useful. It also means provenance is only meaningful next to the artifacts. Those
artifacts are ~36 MB of regenerated JSON per source change (`architecture.graph.json`:
23 MB). No consumer will commit them, and the first consumer already made that decision
in `.gitignore` before this change existed. Committing provenance without the artifacts
(Approach C in the proposal) yields `stale` on every clone, which is *less* accurate than
`missing`.

**What survives from ri-10 D4.** The *reporting* distinction: missing or malformed
provenance is still reported as `unverifiable`, not as an absent owner, so "no baseline"
and "digests disagree" stay distinguishable. What does not survive is the *blocking*
consequence, because it blocked on a condition that is true on every clone by design.

## D3 — The gate's architecture arm is informational; the report block is unchanged in shape

**Decision.** `gate.py` continues to compute and render the `architecture` block exactly
as today — `freshness`, `provenance`, `delta`. It no longer routes an architecture result
into `blocking_drift`. Architecture drift joins `openspec.projection` in the
`informational_drift` list, and contributes nothing to the exit code.

**Why the shape is kept.** Readers of the gate report (humans, `main_convergence.py`'s
summary, the merge log) still benefit from seeing that architecture is stale on this
machine. Removing the block would trade a useful signal for a smaller schema; demoting it
keeps the signal and removes only the false consequence. `context-drift-gate.schema.json`
needs no change.

**Interaction with `rescope-context-drift-enforcement` (#426).** #426 classifies each
*blocking* finding as inherited or introduced before deciding whether it blocks on a given
event. Architecture never enters `blocking_drift` after this change, so it never reaches
attribution and needs no inherited/introduced rule of its own. That is the correct
outcome: attribution answers "which branch caused this drift on the shared tree", and
architecture drift is not a property of the shared tree.

**Why not remove the arm entirely.** The ri-10 D1 rationale — one command, one report, a
CI failure reproducible verbatim in a checkout — still holds for the committed arms. The
architecture arm is the same one-liner it was; it just stops being load-bearing.

## D4 — `--ensure` composes `--check` and `--staged`; it introduces no third path

**Decision.** `--ensure` is: run the read-only check; if the result is `fresh`, exit 0
having written nothing; otherwise run the staged refresh and exit with its code. It
shares every code path with the two modes it composes.

**Why.** Both constituent modes are specified, tested, and byte-stable
(`architecture-refresh.7`, `.8`, `.9`). A third implementation of "is it fresh?" would be
a third place for the ri-10 D14 invariant (pipeline and provenance agree on tool
identity) to break. Composition keeps one resolver, one digest routine, one promotion
routine.

**Idempotence.** Two consecutive `--ensure` runs with no intervening source change: the
second is a pure check, writes nothing, and changes no provenance. This is the property
consumers rely on to call it unconditionally.

## D5 — Inapplicable analyzer input is a skip (narrows ri-10 D13)

**Decision.** In `refresh_architecture.sh`, a missing `MIGRATIONS_DIR`, or one containing
no `*.sql`, results in `skip "postgres_analyzer"` with loud warnings and no artifact
written — the verdict the TypeScript analyzer already applies to a missing `TS_SRC_DIR`,
for the reason recorded in its comment: zero results from a missing input misreport as
analysis.

**Why this is not a workaround.** ri-10 D13 repaired the analyzers "because provenance
could not be written otherwise". This is the same motivation applied to an input the
analyzer was never designed for: it parses numbered `.sql` files, and a repository whose
migrations are Python has nothing for it to parse. `fail` is the wrong classification of
"nothing to do", and its consequence — `ERRORS` incremented, promotion blocked, provenance
never written — is exactly the failure mode D13 set out to eliminate.

**Consistency.** After this change the Postgres and TypeScript analyzers reach the same
verdict for the same condition. A misconfigured-but-present root is still a loud warning
in both.

## D6 — Optional-tool resolution is per-analyzer (narrows ri-10 D14)

**Decision.** `interpreters.py` reports, for a candidate interpreter, the set of
importable grammars from `{tree_sitter, tree_sitter_sql, tree_sitter_python,
tree_sitter_typescript}`. Each pipeline stage declares the grammars it requires and runs
when its own set is satisfied. Provenance's `optional_tools` records the per-grammar
availability, so the ri-10 D14 invariant — the pipeline and the provenance record cannot
disagree about tool identity — holds at grammar granularity rather than as one boolean.

**Why.** `REQUIRED_MODULES = ("tree_sitter", "tree_sitter_sql")` made the SQL grammar a
precondition for every tree-sitter stage. In the measured consumer, that one absent
grammar disabled `treesitter_enrichment`, `comment_linker`, and `pattern_reporter` for
Python and TypeScript — three of the pipeline's eleven stages, and the ones that give the
graph its comment links and pattern annotations. Coupling unrelated analyzers through a
single resolver answer is what D14 accidentally introduced while fixing the previous
two-resolver disagreement; this keeps D14's single resolver and removes the coupling.

## D7 — An ORM schema source, not migration-chain replay

**Decision.** `SCHEMA_SOURCE=sqlalchemy` (opt-in, default unchanged) runs
`dump_sqlalchemy_schema.py`, which imports the configured `MetaData` and emits one
`schema.sql` of `CreateTable` DDL into the staging directory; `MIGRATIONS_DIR` is pointed
at that directory for the run, and the existing regex and tree-sitter SQL analyzers
consume it unchanged.

**Why not `alembic upgrade base:head --sql`.** Offline mode was measured: it stopped after
4 tables because a historical migration calls `.fetchone()` inside `upgrade()`, and 16 of
75 migrations in the consumer do the same. Patching migration history to serve an
analysis tool is the wrong trade, and the output would still be the *history* of the
schema when the analyzer wants its *state*.

**What the ORM source is and is not.** It is the *intended* schema. The *actual* schema
is whatever the migrations produce, and the two agree only if `alembic check` says so.
That check needs a live database and is a consumer CI concern, named in the proposal's
Out of Scope. This change does not claim the ORM source is authoritative; it claims it is
parseable, database-free, and correct whenever the repository's own tooling keeps models
and migrations aligned.

## D8 — Consumers ensure; the checkpoint does not

**Decision.** The seven artifact consumers call `--ensure` before reading. `checkpoint.py`
does not: it keeps ri-09 D3's read-only posture and continues to report architecture
freshness and delta as *findings*.

**Why.** The checkpoint's value is that it is a report of what a branch invalidated,
produced without touching anything. Having it regenerate artifacts would make it a writer,
which ri-09 D1/D10 forbid for the operation ledger and which would make its report
non-reproducible. It already says the right thing: drift is data.

## Risks and Open Questions

- **Consumers that read artifacts in a read-only context** (e.g. a review skill running
  against a detached HEAD, per the `merge-pull-requests` HEAD-mutation guard) will now
  write into `docs/architecture-analysis/` when stale. That directory is gitignored in the
  consumer, so no tracked file changes, but the mutation guard should be checked for
  whether it digests ignored paths. — *Task 3.4 verifies this before any consumer call
  site lands.*
- **Per-grammar provenance changes `optional_tools` shape.** Existing provenance records
  a single `tree-sitter` entry; the new shape records one entry per grammar. A
  `producer_version` bump makes old provenance report `PRODUCER_IDENTITY_MISMATCH` once,
  which `--ensure` resolves by regenerating. Acceptable; noted so the first run after
  upgrade is not read as a regression.
- **`SCHEMA_SOURCE=sqlalchemy` requires importing the consumer's models**, which may have
  import-time side effects (settings loading, provider selection). The dumper runs in a
  subprocess with the repository root on `sys.path` and passes `_env_file=None`-style
  isolation where the consumer supports it. If a consumer's models cannot be imported
  without infrastructure, the source is inapplicable and the analyzer skips per D5.
