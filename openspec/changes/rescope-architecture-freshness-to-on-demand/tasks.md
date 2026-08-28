# Tasks — rescope-architecture-freshness-to-on-demand

Five phases. Test tasks precede the implementation they verify (TDD RED → GREEN). Phases
1–3 are independent of each other and of #426; Phase 4 is the only phase that touches
`gate.py` and MUST be rebased onto `rescope-context-drift-enforcement` (#426) before it
lands. Phase 5 depends on Phase 2.

Capability short names used in scenario references: `pcro` =
`project-context-refresh-orchestration`, `ar` = `architecture-refresh`.

---

## Phase 1 — wp-pipeline: inapplicable input skips, per-analyzer tool resolution

- [x] 1.1 Test: `refresh_architecture.sh` with `MIGRATIONS_DIR` absent records
      `postgres_analyzer` as SKIP, leaves `ERRORS` at 0, writes no `pg_analysis` artifact
      **Spec scenarios**: ar *Missing input root is a warning, not an error*
      **Design decisions**: D5
      **Dependencies**: None — **Size**: S
- [x] 1.2 Test: `MIGRATIONS_DIR` present with zero `*.sql` → SKIP with the
      "non-SQL migration tool" warning; present with `*.sql` and analyzer exit 1 → FAIL
      **Spec scenarios**: ar *Repository without SQL migrations promotes*,
      *Present input still fails loudly on analyzer error*
      **Design decisions**: D5
      **Dependencies**: None — **Size**: S
- [x] 1.3 Implement the Postgres analyzer skip branch, mirroring the TypeScript analyzer's
      missing-root handling and comment
      **Spec scenarios**: ar *Repository without SQL migrations promotes*
      **Design decisions**: D5
      **Dependencies**: 1.1, 1.2 — **Size**: S
- [x] 1.4 Test: `interpreters.py` reports per-grammar importability for a candidate
      interpreter; an interpreter with `tree_sitter_python` but not `tree_sitter_sql`
      is reported as satisfying the enrichment stages and not the SQL stage
      **Spec scenarios**: ar *SQL grammar absence does not disable Python enrichment*,
      *No grammars available skips all tree-sitter stages*
      **Design decisions**: D6
      **Dependencies**: None — **Size**: M
- [x] 1.5 Implement per-grammar resolution: `REQUIRED_MODULES` becomes a per-stage
      requirement table; `check_treesitter` takes a stage name; the resolver output is a
      JSON map consumed by both the shell pipeline and provenance
      **Spec scenarios**: ar *Provenance and pipeline agree per grammar*
      **Design decisions**: D6
      **Dependencies**: 1.4 — **Size**: M
- [x] 1.6 Test: provenance `optional_tools` records one entry per grammar; a stage
      recorded as run has every required grammar recorded as available
      **Spec scenarios**: ar *Provenance and pipeline agree per grammar*
      **Design decisions**: D6
      **Dependencies**: 1.5 — **Size**: S
- [x] 1.7 Bump `PRODUCER_VERSION`; document in the design's Risks that the first
      post-upgrade run reports `PRODUCER_IDENTITY_MISMATCH` once
      **Spec scenarios**: none (identity bookkeeping)
      **Design decisions**: D6
      **Dependencies**: 1.6 — **Size**: S

## Phase 2 — wp-ensure: the `--ensure` mode

- [x] 2.1 Test: `--ensure` on a fresh checkout writes nothing, changes no provenance
      byte, exits 0
      **Spec scenarios**: ar *Fresh artifacts are left untouched*, *Ensure is idempotent*
      **Design decisions**: D4
      **Dependencies**: None — **Size**: S
- [x] 2.2 Test: `--ensure` on stale/missing provenance runs the staged refresh; a
      subsequent `--check` is fresh; a staged failure preserves last known-good and
      exits non-zero
      **Spec scenarios**: ar *Stale artifacts are regenerated*,
      *Failed regeneration preserves last known-good*
      **Design decisions**: D4
      **Dependencies**: None — **Size**: M
- [x] 2.3 Implement `--ensure` in `run_architecture.py` as a composition of the existing
      `--check` and `--staged` branches; no new digest or promotion code
      **Spec scenarios**: all four *Ensure mode* scenarios
      **Design decisions**: D4
      **Dependencies**: 2.1, 2.2 — **Size**: S

## Phase 3 — wp-schema-source: ORM metadata as a SQL schema source

- [x] 3.1 Test: `dump_sqlalchemy_schema.py` given an importable `MetaData` target emits one
      DDL file with a `CREATE TABLE` per declared table, in a subprocess, opening no
      database connection
      **Spec scenarios**: ar *Alembic repository gets a SQL schema analysis*
      **Design decisions**: D7
      **Dependencies**: None — **Size**: M
- [x] 3.2 Test: an unimportable target is recorded as a skip with the import error, and
      the pipeline promotes; `SCHEMA_SOURCE` unset leaves `MIGRATIONS_DIR` handling
      byte-identical
      **Spec scenarios**: ar *Unimportable metadata skips the source*, *Default is unchanged*
      **Design decisions**: D5, D7
      **Dependencies**: None — **Size**: S
- [x] 3.3 Implement `dump_sqlalchemy_schema.py` and the `SCHEMA_SOURCE=sqlalchemy` branch
      in `refresh_architecture.sh` that points `MIGRATIONS_DIR` at the staging output
      **Spec scenarios**: all three *ORM metadata* scenarios
      **Design decisions**: D7
      **Dependencies**: 3.1, 3.2, 1.3 — **Size**: M
- [x] 3.4 Verify the `merge-pull-requests` HEAD-mutation guard does not digest ignored
      paths, so a consumer `--ensure` under a detached-HEAD review cannot trip it; record
      the finding in the design's Risks
      **Spec scenarios**: none (risk verification)
      **Design decisions**: D1, D8
      **Dependencies**: 2.3 — **Size**: S

## Phase 4 — wp-gate: architecture arm becomes informational (rebase onto #426 first)

- [x] 4.1 Test: with provenance missing and no other drift, the report has
      `architecture.freshness == "unverifiable"`, `architecture` in `informational_drift`,
      and exit 0; with provenance stale, the same with `"stale"`
      **Spec scenarios**: pcro *Missing provenance is reported but does not block*,
      *Stale architecture is reported but does not block*
      **Design decisions**: D2, D3
      **Dependencies**: #426 merged — **Size**: M
      **Base correction:** the worktree was first created from the pre-merge branch ref,
      40 commits behind main and missing #425/#426. Phase 4 refused to commit onto it,
      built against a reproduction of main, and the branch was rebased before the patch
      was applied. Verified after: 457 passed, schema byte-identical to main.
- [x] 4.2 Test: with provenance missing AND `decisions.timeline` drifted, exit 2 and
      `blocking_drift` contains `decisions.timeline` but not `architecture`
      **Spec scenarios**: pcro *Architecture drift never masks committed-artifact drift*
      **Design decisions**: D3
      **Dependencies**: #426 merged — **Size**: S
- [x] 4.3 Implement the reclassification in `gate.py`: route the architecture result to
      `informational_drift`; keep the `architecture` report block byte-identical in shape
      **Spec scenarios**: all four MODIFIED-requirement scenarios
      **Design decisions**: D2, D3
      **Dependencies**: 4.1, 4.2 — **Size**: S
- [x] 4.4 Update the `gate.py` module docstring's "Missing architecture provenance exits 2"
      reconciliation paragraph, which will be false after 4.3
      **Spec scenarios**: none (docstring truth)
      **Design decisions**: D2
      **Dependencies**: 4.3 — **Size**: S
- [x] 4.5 Confirm `context-drift-gate.schema.json` needs no change (report shape is
      unchanged) with the existing promoted-contract byte-compare test
      **Spec scenarios**: none (contract hygiene)
      **Design decisions**: D3
      **Dependencies**: 4.3 — **Size**: S

## Phase 5 — wp-consumers: ensure-on-demand at the seven readers

- [x] 5.1 Test: a consumer skill's artifact-reading step invokes `--ensure` before its
      first read, and `checkpoint.py` never does
      **Spec scenarios**: pcro *Consumer regenerates stale artifacts before reading*,
      *Checkpoint reports rather than ensures*
      **Design decisions**: D1, D8
      **Dependencies**: 2.3 — **Size**: M
  **Scope exception (accepted):** `skills/install-manifest.json` was edited outside the
  phase's file scope. The six new call sites create a real cross-skill dependency on
  `refresh-architecture`, and `install.sh` validates the manifest before writing anything —
  without the four declarations it refuses to install any skill. Four lines, all of them
  declarations of a dependency the code now genuinely has.

- [x] 5.2 Add the `--ensure` call to `explore-feature`, `plan-feature`, `validate-feature`,
      `tech-debt-analysis`, `validate-flows`, and `validate-packages` at the top of their
      artifact-reading step (SKILL.md instruction + script call where a script reads)
      **Spec scenarios**: pcro *Consumer reads fresh artifacts without regeneration*
      **Design decisions**: D1
      **Dependencies**: 5.1, 3.4 — **Size**: M
- [x] 5.3 Update `refresh-architecture/SKILL.md`, `project-context-refresh/SKILL.md`, and
      `cleanup-feature` Step 4 to describe ensure-on-demand and the local (not committed)
      baseline
      **Spec scenarios**: none (documentation)
      **Design decisions**: D1, D2
      **Dependencies**: 5.2 — **Size**: S
- [x] 5.4 Regenerate `docs/decisions/` so the D2/D5/D6 supersessions of ri-10 D4/D13/D14
      are visible in the timeline
      **Spec scenarios**: none (derived artifact)
      **Design decisions**: D2, D5, D6
      **Dependencies**: 5.3 — **Size**: S
