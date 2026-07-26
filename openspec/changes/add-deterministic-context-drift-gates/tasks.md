# Tasks — add-deterministic-context-drift-gates

Six phases, one per work package. Test tasks precede the implementation they verify
(TDD RED → GREEN). Sizes follow the plan-feature sizing reference; no task is XL and
exactly one is L.

Phase 6 (`wp-emitter`) was added mid-implementation after the measured baseline revealed a
false positive in the `decisions.timeline` producer — see design D12. It is appended rather
than renumbered so the already-seeded coordinator task keys stay valid; `depends_on` in
`work-packages.yaml` is the authoritative execution order, not file position.

Capability short names used in scenario references: `pcro` =
`project-context-refresh-orchestration`, `ar` = `architecture-refresh`,
`sft` = `software-factory-tooling`.

---

## Phase 1 — wp-contracts: the gate report contract

- [x] 1.1 Extend the promoted-contract byte-compare test to cover
      `context-checkpoint.schema.json` and the new `context-drift-gate.schema.json`
      **Spec scenarios**: none (repo hygiene gate, not a spec requirement)
      **Contracts**: `contracts/context-drift-gate.schema.json`
      **Design decisions**: none
      **Dependencies**: None
      **Size**: S
      **Note**: `SCHEMA_NAMES` in `skills/tests/project-context-runtime/test_promoted_contracts.py:31-35`
      currently omits `context-checkpoint.schema.json`, which is byte-identical across its
      three locations only by luck. This task must fail before 1.2 lands the new schema.

- [x] 1.2 Author `context-drift-gate.schema.json` under
      `skills/project-context-refresh/install_assets/openspec/schemas/`
      **Spec scenarios**: `pcro` — Deterministic context drift gate / Stale artifacts are named individually
      **Contracts**: `contracts/context-drift-gate.schema.json`
      **Design decisions**: D2 (four disjoint groups), D6 (`not-attempted` is not a `SemanticIndexStatus`)
      **Dependencies**: 1.1
      **Size**: S

- [x] 1.3 Promote the schema to `openspec/contracts/project-context-refresh/schemas/`,
      byte-identical to the installed copy
      **Spec scenarios**: none
      **Contracts**: `contracts/context-drift-gate.schema.json`
      **Design decisions**: none
      **Dependencies**: 1.2
      **Size**: XS
      **Note**: Promotion before archive is a hard repo rule, not bookkeeping — see
      `openspec/contracts/README.md`.

- [x] 1.4 Checkpoint: run tests, review diff, verify scope

---

## Phase 2 — wp-lifecycle: classification and the architecture fix

- [x] 2.1 Write tests for `classify_degradation` — disjoint grouping, projection is
      informational, and `decide_outcome` output is unchanged for every input
      **Spec scenarios**: `pcro` — Drift classification / Groups are disjoint; Drift classification / Existing outcome decision is unaffected; Projection drift is informational / Pending merges do not fail the gate; Projection drift is informational / Projection drift does not mask blocking drift
      **Contracts**: `contracts/context-drift-gate.schema.json`
      **Design decisions**: D2, D3
      **Dependencies**: None
      **Size**: M

- [x] 2.2 Write tests for architecture freshness fail-closed behaviour — missing and
      malformed provenance yield drift, absent owner yields not-configured
      **Spec scenarios**: `pcro` — Architecture freshness fails closed / Missing provenance blocks; Architecture freshness fails closed / Absent owner degrades without blocking; Architecture freshness fails closed / Stale architecture blocks; `ar` — Architecture provenance is a committed baseline / Missing provenance fails closed
      **Contracts**: `architecture-provenance.schema.json` (consumed)
      **Design decisions**: D4
      **Dependencies**: None
      **Size**: S
      **Note**: These must fail against current `orchestrator.py`, which reports `fresh`
      unconditionally. Confirm the RED state explicitly — a passing test here means the
      test is wrong, not that the defect is absent.

- [x] 2.3 Write the check-mode read-only assertion over every producer from
      `list_producers()`, digesting tracked *and* untracked paths
      **Spec scenarios**: `pcro` — Check-mode read-only behaviour is asserted / A writing producer is caught; / Untracked writes are caught; / Newly registered producers are covered
      **Contracts**: none
      **Design decisions**: D8
      **Dependencies**: None
      **Size**: M
      **Note**: Verify by mutation — temporarily add a producer that writes in check mode
      and confirm the assertion fails. ri-09 established that a test which cannot be shown
      to fail is not evidence.

- [x] 2.4 Checkpoint: run tests, review diff, verify scope

- [x] 2.5 Implement `DegradationBreakdown` and `classify_degradation` in `orchestrator.py`
      **Spec scenarios**: `pcro` — Drift classification (all scenarios); Projection drift is informational (all scenarios)
      **Contracts**: `contracts/context-drift-gate.schema.json`
      **Design decisions**: D2, D3
      **Dependencies**: 2.1
      **Size**: M
      **Note**: Additive only. `decide_outcome`, `OperationState`, and the operation and
      manifest schemas must not change — ri-06 records are durable and ri-07 D9 makes them
      immutable.

- [x] 2.6 Replace `build_provenance` with `check_freshness` in
      `_default_architecture_producer`, mapping unverifiable provenance to drift
      **Spec scenarios**: `pcro` — Architecture freshness fails closed (all scenarios)
      **Contracts**: `architecture-provenance.schema.json` (consumed)
      **Design decisions**: D4
      **Dependencies**: 2.2
      **Size**: M

- [x] 2.7 Checkpoint: run tests, review diff, verify scope

---

## Phase 3 — wp-gate: composition, rendering, entry points

- [ ] 3.1 Write tests for gate composition and the four exit-code conditions
      **Spec scenarios**: `pcro` — Gate exit codes / Failure outranks drift; / Absent optional owner alone passes; / Existing entry points keep their codes
      **Contracts**: `contracts/context-drift-gate.schema.json`
      **Design decisions**: D5
      **Dependencies**: None
      **Size**: M

- [ ] 3.2 Write tests for report conformance and the precise artifact list
      **Spec scenarios**: `pcro` — Deterministic context drift gate / Stale artifacts are named individually; / Gate leaves the checkout unchanged; Semantic index status / No probe is performed; / Semantic status never gates
      **Contracts**: `contracts/context-drift-gate.schema.json`
      **Design decisions**: D1, D6
      **Dependencies**: None
      **Size**: S
      **Note**: Assert against the schema, and assert no indexer is constructed even when
      full semantic configuration is present in the environment.

- [ ] 3.3 Write tests for context-impact scoping and usage-error mapping
      **Spec scenarios**: `pcro` — Context-impact validation / Unchanged packages are not reported; / Legacy packages without declarations pass; / Validator usage error is an apparatus failure
      **Contracts**: none
      **Design decisions**: D7
      **Dependencies**: None
      **Size**: S
      **Note**: Assert `--strict-legacy` is never passed. Measured baseline: 4 of 70
      work-package files declare a block; 65 fail under that flag.

- [ ] 3.4 Checkpoint: run tests, review diff, verify scope

- [ ] 3.5 Implement `gate.py` composition — run producers in check mode, invoke architecture
      freshness, invoke the context-impact validator over changed work-package files
      **Spec scenarios**: `pcro` — Deterministic context drift gate / Gate leaves the checkout unchanged; Context-impact validation (all scenarios)
      **Contracts**: `contracts/context-drift-gate.schema.json`
      **Design decisions**: D1, D5, D7
      **Dependencies**: 2.5, 2.6, 3.1, 3.3
      **Size**: L
      **Note**: The only L in this plan. Decomposition was attempted and rejected:
      splitting composition from classification would put the exit-code derivation in a
      package that cannot test it end to end, and splitting per-arm would triple the
      fixture setup. Flagged rather than silently kept.

- [ ] 3.6 Implement report rendering — join producer results with registry owners, sort for
      byte stability, emit the semantic `not-attempted` block
      **Spec scenarios**: `pcro` — Deterministic context drift gate / Stale artifacts are named individually; Semantic index status / No probe is performed
      **Contracts**: `contracts/context-drift-gate.schema.json`
      **Design decisions**: D1, D6
      **Dependencies**: 1.2, 3.2, 3.5
      **Size**: M
      **Note**: `ProducerResult` has no `owner` field — recover it from the registry
      `ProducerSpec`, as ri-07's summary does.

- [ ] 3.7 Add the `gate` subcommand to `cli.py` and the `context-drift-gate` Makefile target
      **Spec scenarios**: `pcro` — Deterministic context drift gate / Gate reproduces locally
      **Contracts**: none
      **Design decisions**: D1, D5
      **Dependencies**: 3.5, 3.6
      **Size**: S
      **Note**: Do not change `_exit_code` or the existing `refresh-check` mapping; the gate
      is a third caller with its own documented codes.

- [ ] 3.8 Checkpoint: run tests, review diff, verify scope

---

## Phase 4 — wp-ci: wiring and the retirement

- [ ] 4.1 Write the orphaned-capability-file detection test
      **Spec scenarios**: `pcro` — The gate is the single freshness authority / Orphaned capability file is detected
      **Contracts**: none
      **Design decisions**: D9
      **Dependencies**: None
      **Size**: M
      **Note**: This is the blind spot the retired job could not see — an orphan's *content*
      is unchanged, so `git diff` misses it. Removing the old job without proving the
      replacement covers this would be a silent regression.

- [ ] 4.2 Add the blocking CI job and remove `validate-decision-index`
      **Spec scenarios**: `pcro` — The gate is the single freshness authority / Only one decision freshness check exists
      **Contracts**: none
      **Design decisions**: D9, D11
      **Dependencies**: 3.7, 4.1
      **Size**: M
      **Note**: Deliberately one task, not two — splitting leaves an intermediate commit
      with no decision-index gate at all. Name the job so it does not read as skill-mirror
      drift; `gate-drift-with-mirrors-hooks-and-blocking-ci` is a different, unrelated
      change that also edits this file.

- [ ] 4.3 Declare the `project-context-refresh → validate-packages` cross-skill dependency
      in `skills/install-manifest.json`
      **Spec scenarios**: none
      **Contracts**: none
      **Design decisions**: D7
      **Dependencies**: 3.5
      **Size**: XS
      **Note**: Undeclared sibling references fail `install.sh --check`, which fails the
      **required** `test-infra-skills` job. This bit ri-09 and is not reachable by running
      pytest on the suites this change touches.

- [ ] 4.4 Document the branch-protection promotion as an explicit manual follow-up
      **Spec scenarios**: none
      **Contracts**: none
      **Design decisions**: D11
      **Dependencies**: 4.2
      **Size**: S
      **Note**: **MANUAL** — a PR cannot edit branch protection. Record the exact `gh api`
      call and state that until it is applied the gate is "blocking job, not a required
      context", which is how `docs/decisions/` drifted in the first place.

- [ ] 4.5 Checkpoint: run tests, review diff, verify scope

---

## Phase 5 — wp-integration: remediation and proof

- [ ] 5.1 Merge the package worktrees and run the full suite plus `bash install.sh --check`
      and `ruff check .` from `skills/`
      **Spec scenarios**: none
      **Contracts**: none
      **Design decisions**: none
      **Dependencies**: 1.4, 2.7, 3.8, 4.5
      **Size**: S

- [ ] 5.2 Verify the gate FAILS on the merged, pre-remediation tree
      **Spec scenarios**: `pcro` — Deterministic context drift gate / Stale artifacts are named individually
      **Contracts**: `contracts/context-drift-gate.schema.json`
      **Design decisions**: D10
      **Dependencies**: 5.1, 6.4
      **Size**: S
      **Note**: Expected: exit 2, naming `skills-inventory.md`, `contracts-inventory.md`,
      and missing `architecture.provenance.json`. **Not** `docs/decisions/*.md` — those were
      D12's false positive and must be absent from the report once 6.x lands; their presence
      means the emitter fix is incomplete. A gate that cannot be shown to fail is
      decoration — capture the output as evidence.

- [ ] 5.3 Track `architecture.provenance.json` and regenerate the stale artifacts as one
      commit containing only generated output
      **Spec scenarios**: `ar` — Architecture provenance is a committed baseline / Regeneration updates the committed baseline
      **Contracts**: `architecture-provenance.schema.json`
      **Design decisions**: D4, D10, D12
      **Dependencies**: 5.2
      **Size**: M
      **Note**: Must land after 2.6 and 6.x — both change what the producers report. Also
      re-run `make decisions` and commit the result; a **no-op is the expected outcome** and
      is the positive demonstration that the fixed emitter and fixed producer agree. Keep
      isolated from every commit that touches gate code.

- [ ] 5.4 Verify the gate PASSES on a clean checkout at the recorded revision, with no diff
      **Spec scenarios**: `ar` — Architecture provenance is a committed baseline / Clean checkout at the recorded revision is fresh; `pcro` — Projection drift is informational / Pending merges do not fail the gate
      **Contracts**: `contracts/context-drift-gate.schema.json`
      **Design decisions**: D3, D10
      **Dependencies**: 5.3
      **Size**: S
      **Note**: This is roadmap acceptance outcome #4. Projection drift will still be
      present and reported — assert it does not affect the exit code.

- [ ] 5.5 Checkpoint: run tests, review diff, verify scope, confirm contracts promoted
      **Dependencies**: 5.4
      **Size**: XS

---

## Phase 6 — wp-emitter: fix the decisions false positive at its root

**Execution order note:** phases are presentational; `work-packages.yaml` `depends_on` is
authoritative. `wp-emitter` has no dependencies and runs in parallel with `wp-gate`;
`wp-integration` depends on it, so Phase 6 lands *before* Phase 5's tasks 5.2-5.4.

- [ ] 6.1 Write a test proving a producer's report is identical for relative and absolute
      repository paths
      **Spec scenarios**: `sft` — Decision index rendering is path-independent / Rendered links do not embed the archive root
      **Contracts**: none
      **Design decisions**: D12
      **Dependencies**: None
      **Size**: S
      **Note**: Must fail before 6.3. Measured baseline: relative root yields 0 artifacts,
      absolute yields 17. Write it over `list_producers()` so it guards *every* current and
      future tempdir-diff producer, not just this one — the generalisation D12 records as
      cheaper than auditing each renderer.

- [ ] 6.2 Write a test that rendered `Source:` links are repository-relative
      **Spec scenarios**: `sft` — Decision index rendering is path-independent / Rendered links do not embed the archive root
      **Contracts**: none
      **Design decisions**: D12
      **Dependencies**: None
      **Size**: S
      **Note**: Assert on the rendered bytes, not on the diff count, so the test names the
      actual defect rather than a symptom of it.

- [ ] 6.3 Render `Source:` links relative to the repository root in
      `emit_decisions_from_archive`
      **Spec scenarios**: `sft` — Decision index rendering is path-independent (all scenarios)
      **Contracts**: none
      **Design decisions**: D12
      **Dependencies**: 6.1, 6.2
      **Size**: M
      **Note**: Fix the emitter, not the caller. A relative-path fix in
      `producer_decisions.py` would leave `make decisions --archive-root <absolute>` able to
      write machine paths into a committed artifact, and would depend on cwd, which the
      producer contract does not guarantee. Committed output must stay byte-identical to
      today's — this removes a phantom diff, it does not introduce a real one.

- [ ] 6.4 Checkpoint: run tests, review diff, verify scope, confirm `docs/decisions/`
      renders byte-identically to the committed tree
