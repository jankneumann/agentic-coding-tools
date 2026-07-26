# Add deterministic context drift gates

**Roadmap**: `project-context-refresh-lifecycle` item **ri-10** (priority 10, effort M)
**Depends on**: ri-04, ri-05, ri-07 (all merged); consumes ri-08 and ri-09 output

## Why

Every piece of check machinery this change needs already exists, and none of it is
connected to anything that can fail a build.

- `make context-refresh-check`, `make refresh-project-context-check`, and
  `make architecture-check` all exist (`Makefile:425`, `:432`, `:140`) with a settled
  exit-code convention — `0` fresh, `2` drift, `1` failed. **`grep` over `.github/`
  returns zero references to any of them.**
- `orchestrator.check()`'s docstring
  (`skills/project-context-refresh/scripts/orchestrator.py:510-518`) names "the ri-10
  gate" as its consumer. The consumer was never built.
- ri-08's detector `skills/validate-packages/scripts/validate_context_impact.py` is,
  in its own learning entry's words, "runnable but enforced nowhere today."
- ri-09 exits `0` on drift deliberately (`checkpoint.py:459-461`, design D8) because
  "ri-10 owns turning drift into a CI or merge failure. Shipping a gate here would give
  ri-10 a gate to rework rather than a signal to consume."

So the committed artifacts under `docs/architecture-analysis/`, `docs/decisions/`, and
the projected `openspec/specs/` can go stale on `main` and nothing notices — except
`validate-decision-index`, a bespoke regenerate-and-diff job covering exactly one
producer's output, which is **not a required check** (branch protection requires only
`test`, `test-infra-skills`, `test-skills`, `validate-specs`, `check-docker-imports`,
`secret-scan`).

### Measured baseline — the gate is red on `main` today

Running `make refresh-project-context-check` against unmodified `main` exits `2`. All
four deterministic producers report drift, and one of them reports it permanently:

| Producer | Status | Stale artifacts | Nature |
|---|---|---|---|
| `documentation.inventory` | degraded | 1 — `docs/architecture-analysis/skills-inventory.md` | genuine staleness |
| `api.contracts` | degraded | 1 — `docs/architecture-analysis/contracts-inventory.md` | genuine staleness |
| `decisions.timeline` | degraded | 18 — `docs/decisions/*.md` | genuine staleness |
| `openspec.projection` | degraded | 37 — 12 "pending merge" + 25 "would be created" | **structural, not staleness** |
| `architecture` | **fresh** | — | **false negative** (see defect #4) |

Two consequences shape the design:

- **`openspec.projection` measures pending archival, not staleness.** Its 37 failed
  validations trace to the 31 active changes in `openspec/changes/`, and its own
  remediation is "Archive the active change(s) through cleanup-feature." A repository
  always has active changes, so this producer reports drift permanently. It cannot
  contribute to a failing exit code without blocking every PR forever.
- **`docs/decisions/` is stale on `main` despite `validate-decision-index` existing.**
  The job is not a required check, so the drift landed. That is the empirical case for
  the required-check posture.

Four concrete defects block a gate from being built naively on top of what exists:

1. **The architecture gate has no committed baseline.** 21 artifacts under
   `docs/architecture-analysis/` are tracked, but
   `docs/architecture-analysis/architecture.provenance.json` — the file
   `make architecture-check` compares against — is neither tracked nor gitignored.
   The `architecture-refresh` spec already requires provenance to be *written*
   ("Architecture Provenance Evidence"); it never required it to be *committed*.
2. **`decide_outcome()` flattens three distinct conditions into one bucket.**
   `orchestrator.py:271-308` maps deterministic drift, a `not-configured` optional
   producer, and a non-succeeded semantic index all onto `OperationState.DEGRADED`
   with no discriminator. A gate built on that exit code cannot report external-service
   degradation separately from real drift, which is acceptance outcome #3.
3. **Check-mode read-only-ness is convention, not a guarantee.** ri-09's design D3
   says so explicitly: "`registry.run_producer` does not *structurally* prevent a
   `check`-mode adapter from writing … **ri-10 in particular should assert
   read-only-ness rather than assume it.**" There is no filesystem guard anywhere in
   `registry.py:159-211`.
4. **The architecture producer is fail-open.** `_default_architecture_producer`
   (`orchestrator.py:187-189`) calls `provenance.build_provenance(repository,
   mode="full")` — which *builds* provenance from the working tree — and then returns
   `architecture_result_fresh(doc)` unconditionally. It never calls `check_freshness`
   and never compares against a committed baseline, so it reports `fresh` whenever
   `refresh-architecture` is importable. On the very same tree,
   `make architecture-check` correctly fails closed with
   `{"status": "invalid", "reasons": [{"code": "PROVENANCE_MISSING"}]}` and exit `1`.
   The producer's own docstring names ri-10 as the owner of the fix.

## What Changes

- Add a composed **drift gate** entry point that runs the deterministic producer check,
  architecture provenance freshness, and ri-08 context-impact validation, and emits one
  structured report with a **precise stale-artifact list** and a **discriminated
  outcome**.
- Give the refresh outcome a discriminator so deterministic drift, optional-producer
  non-configuration, and semantic-index status are reported as distinct facts rather
  than collapsed into `DEGRADED`.
- Track `docs/architecture-analysis/architecture.provenance.json` so the architecture
  freshness check has a committed baseline, satisfying "drift decisions use source
  revision and producer inputs rather than file modification time."
- Add a **blocking CI job** that fails on deterministic drift, and retire
  `validate-decision-index` in favour of it so there is one freshness authority.
- **Assert** check-mode read-only-ness with a test that fails if any registered producer
  writes to the checkout in check mode.
- Fix the fail-open architecture producer so it compares against committed provenance via
  `check_freshness` instead of rebuilding provenance and declaring itself fresh.
- Classify `openspec.projection` as informational-only in the gate, since its drift
  signals pending archival rather than staleness.
- Regenerate and commit the 20 artifacts that are stale on `main` today, so the gate is
  green on arrival.
- Close the promoted-contract gap: add `context-checkpoint.schema.json` to the
  byte-compare test, which currently passes only by luck.

### Decided at discovery

| Question | Decision |
|---|---|
| Gate posture | Blocking CI job **and** a required branch-protection context. Adding the context is an admin action outside this repo — recorded as an explicit manual follow-up, not silently assumed. |
| Architecture baseline | Commit `architecture.provenance.json` and gate on it, rather than regenerating and diffing 21 artifacts in CI. |
| Semantic degradation reporting | Split the outcome into discriminated fields; do **not** add a Postgres/embedder probe to CI. The gate reports semantic as "not attempted — deterministic-only" with an explicit reason. |
| Scope absorbed | Replace `validate-decision-index`; wire `validate_context_impact.py` into CI; fix the promoted-contract test gap. |
| `openspec.projection` in the gate | Runs and is **reported informationally**; its drift never contributes to a failing exit code, because "pending merge" means an active change exists, not that anything is stale. Stated as a normative requirement rather than left implicit. |
| Existing staleness on `main` | Regenerated and committed **inside this change**, as its own isolated commit, so the gate is green the moment it lands. |
| Architecture fail-open | Fixed here — `check_freshness` replaces `build_provenance`, pairing with the decision to commit provenance. |
| Scope declined | Semantic index namespace retention/GC — left to ri-11, where convergence owns index lifecycle. |

### Explicit assumption carried from discovery

Making the new job a **required** check requires editing branch protection on `main`,
which this change cannot do from within a PR. The change ships the job and documents the
exact `gh api` call; a human or admin-scoped automation must apply it. Until then the
gate behaves as "blocking job, not a required context" — the same posture
`validate-decision-index` has today. This is stated so the gap is visible rather than
discovered later.

## Approaches Considered

### Approach A — Composed `gate` subcommand, thin CI wrapper — **Recommended**

Add a `gate` subcommand to `skills/project-context-refresh/scripts/cli.py` that composes
the three checks, renders one structured report (precise artifact list + discriminated
outcome), and returns a single exit code. The CI job is a thin caller; `make
context-drift-gate` is the identical local command.

**Pros**
- One freshness authority; the same command runs locally and in CI, so "reproduce the CI
  failure" is one line rather than reading YAML.
- The precise-artifact-list requirement is satisfied by code that can be unit-tested,
  not by shell `grep` over job output.
- The `DEGRADED` discriminator lands in the lifecycle where every other consumer
  (ri-11's convergence, the ri-09 checkpoint) benefits from it.
- Keeps CI YAML minimal, which matters because `ci.yml` is contended — both
  `extract-gen-eval-package` and `gate-drift-with-mirrors-hooks-and-blocking-ci` also
  edit it.

**Cons**
- New CLI surface to maintain and version.
- Three checks behind one exit code; a single red job is less granular than three.
  Mitigated by the structured report naming which check failed and why.

**Effort**: M

### Selected Approach

**Approach A — Composed `gate` subcommand, thin CI wrapper.** Selected at Gate 1 with no
modifications requested.

It is the only option that fixes defect #2, and defect #2 is what stands between the
existing machinery and acceptance outcome #3. The gate emits a single structured report:

```json
{ "outcome": "drift",
  "deterministic": { "drift": ["docs/decisions/skill-workflow.md",
                              "docs/architecture-analysis/skills-inventory.md"] },
  "architecture":   { "freshness": "stale" },
  "context_impact": { "status": "declared" },
  "semantic":       { "status": "not-attempted",
                      "reason": "deterministic-only gate" } }
```

exiting `2`. `make context-drift-gate` reproduces the CI failure verbatim.

### Alternatives considered and rejected

- **Approach B — separate CI jobs per check, composed in YAML** (effort S). Three jobs,
  each invoking an existing Make target. Smallest diff, no new CLI surface, granular
  red/green, each independently promotable to a required context. Rejected because it
  leaves defect #2 unfixed: each job inherits the ambiguous `DEGRADED` exit code, so none
  of them can distinguish drift from external degradation, and acceptance outcome #3 goes
  unmet. It also pushes the precise-artifact-list assembly into shell over job output.
- **Approach C — extend the ri-09 checkpoint into a merge-time gate** (effort M). Add
  `--gate` to `checkpoint.py` flipping its exit codes and invoke it from
  `run_pre_merge_checks`. Reuses the promoted report contract and is merge-scoped.
  Rejected on granularity and contract-timing: a checkpoint requires `--change-id` and
  `--package-id` (`cli.py:252-286`) and is per-work-package, so a repo-wide PR gate has
  neither; it would modify the requirement "Checkpoint reporting is advisory" one change
  after it landed, which is exactly what D8 was written to prevent; `run_pre_merge_checks`
  (`merge_queue.py:260-347`) only inspects coordinator registry state and never touches
  the repository; and non-OpenSpec PRs would get no gate at all.

## Impact

**Affected specs**
- `project-context-refresh-orchestration` — ADDED: drift gate composition, outcome
  discrimination, check-mode read-only assertion, single freshness authority.
- `architecture-refresh` — ADDED: provenance is a committed baseline artifact.

**Affected code**
- `skills/project-context-refresh/scripts/gate.py` — new module: composition,
  classification, report rendering.
- `skills/project-context-refresh/scripts/cli.py` — new `gate` subcommand.
- `skills/project-context-refresh/scripts/orchestrator.py` — degradation classifier;
  fix `_default_architecture_producer` to use `check_freshness`.
- `.github/workflows/ci.yml` — new blocking job; remove `validate-decision-index`.
- `Makefile` — `context-drift-gate` target.
- `skills/tests/project-context-runtime/test_promoted_contracts.py` — add
  `context-checkpoint.schema.json` to `SCHEMA_NAMES`.
- `skills/install-manifest.json` — `cross_skill_dependencies` entry for
  `project-context-refresh → validate-packages`.

**Newly committed artifacts**
- `docs/architecture-analysis/architecture.provenance.json` — newly tracked baseline.
- Regenerated: `docs/architecture-analysis/skills-inventory.md`,
  `docs/architecture-analysis/contracts-inventory.md`, and 18 `docs/decisions/*.md`.

**Not affected**
- `checkpoint.py` — consumed, not modified. D8 stands.
- The four producer adapters — the gate calls them through the existing
  `run_producer` seam; none of their check-mode logic changes.
- `OperationState` / `ProducerStatus` enums and the ri-06 operation and manifest
  schemas — the classifier is additive and derives from existing fields.
- Semantic indexing configuration — CI stays deterministic-only.

## Known conflicts

- **`ci.yml` is contended.** `extract-gen-eval-package` lists it in `write_allow` for
  three packages; `gate-drift-with-mirrors-hooks-and-blocking-ci` plans another
  drift-check job there. Name this job so it does not read as skill-mirror drift —
  that change is about `.claude/skills/` mirrors, a different roadmap, zero overlap.
- **ri-05 and ri-09 spec deltas are unmerged.** Both are `✓ Complete` but unarchived, so
  this change's `project-context-refresh-orchestration` delta is written against a spec
  whose checkpoint requirements exist only in ri-09's delta.
- **`install.sh --check` and the `skills/` ruff gate** both bit ri-09 and are not
  reachable by running pytest on the suites this change touches.

## Out of Scope

- Semantic index namespace retention/GC — ri-09 left this open for ri-10/ri-11; it
  belongs with convergence (ri-11), not with a drift gate.
- Running context convergence after a merge and committing the result — ri-11.
- Semantic context injection into coding jobs — ri-12/ri-13.
- Widening `checkout_policy` to reason about the git-common-dir — ri-09 D10 records
  that this needs its own proposal.
- Applying the branch-protection change itself; the change documents it as a manual
  follow-up.
