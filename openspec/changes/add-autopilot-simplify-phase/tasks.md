# Tasks — add-autopilot-simplify-phase

Six phases, one per work package, plus a sequencing precheck inside the autopilot package.
Test tasks precede the implementation they verify (TDD RED → GREEN). Sizes per the
plan-feature Task Sizing Reference; no task is L or XL.

Capability short name: `sw` = `skill-workflow`.
Contracts: `contracts/events/simplify-review.schema.json` (+ two fixtures).

---

## Phase 1 — wp-contracts: freeze the artifact and every enum

- [x] 1.1 Test: `simplify-review.schema.json` is a valid JSON Schema 2020-12 document;
      `fixtures/simplify-review.valid.json` validates against it **and** the canonical
      review-findings schema (registry with both `$id`s); `simplify-review.invalid.json` is
      rejected on the `covered_by: null` rule; a seam finding with non-empty
      `consumer.specified` and `disposition: fix` is rejected — **S**
      **Spec scenarios**: sw *Valid fixture passes both schemas*, *Coverage-required prune
      without covered_by is rejected*, *Specified consumer forces keep*, *Simplify findings validate*
      **Contracts**: `contracts/events/simplify-review.schema.json`
      **Design decisions**: D2
      **Dependencies**: None

- [x] 1.2 Test: `type` and `review_type` enums are identical across canonical,
      install mirror, both `consensus-report` copies, and `vendor_review._FALLBACK_ENUMS`,
      and include `test_quality`, `simplification`, `simplify`; every pre-existing value
      still present — **XS**
      **Spec scenarios**: sw *type and review_type enums identical across all copies*,
      *Existing schema fields preserved*
      **Design decisions**: D9, D10
      **Dependencies**: None

- [x] 1.3 Implement the contract: confirm `simplify-review.schema.json`'s conditional rules (including
      the `consumer` → `keep` rule) against 1.1 and finalize the two fixtures — **S**
      **Spec scenarios**: all scenarios under 1.1
      **Contracts**: `contracts/events/simplify-review.schema.json`
      **Design decisions**: D2
      **Dependencies**: 1.1

- [x] 1.4 Implement the enum additions in all five copies (adding `behavioral_failure` to
      `consensus-report` where missing, per D10); update the enum list in
      `skills/validate-feature/scripts/tests/test_linters.py` — **S**
      **Spec scenarios**: all scenarios under 1.2
      **Design decisions**: D9, D10
      **Dependencies**: 1.2

- [x] Checkpoint: `skills/tests/parallel-infrastructure/test_review_findings_schema.py`,
      the new contract test, `skills/tests/merge-pull-requests/test_vendor_review_prompt.py`,
      and `test_linters.py` green; confirm only `wp-contracts.write_allow` changed

## Phase 2 — wp-simplify-skill: Review / Apply roles and the rendering helper

- [x] 2.1 Test: `simplify_review.py validate` exits 0 on the valid fixture, 2 on the
      invalid fixture naming the failing finding id, 1 on a missing file or missing
      `jsonschema`; `--json` emits the error list — **S**
      **Spec scenarios**: sw *Invalid artifact is rejected*
      **Design decisions**: D3
      **Dependencies**: None

- [x] 2.2 Test: round-trip on a synthetic git repo — `render-ledger` from an artifact with
      one `self-mocking` and one `change-detector` (with `covered_by`) finding produces a
      ledger that `check_test_prune.py --base B0 --head B1` accepts (exit 0) after those two
      tests are removed; findings with `disposition: accept` produce no ledger entry — **S**
      **Spec scenarios**: sw *Ledger rendered from the artifact is accepted by the prune gate*
      **Design decisions**: D3
      **Dependencies**: None

- [x] 2.3 Implement `skills/simplify-implementation/scripts/simplify_review.py` with
      `validate` and `render-ledger` subcommands (stdlib + `jsonschema`, resolving the
      canonical schema via `review_findings_schema.find_schema_path()` with an
      `install_assets` fallback) — **S**
      **Spec scenarios**: all scenarios under 2.1–2.2
      **Design decisions**: D3
      **Dependencies**: 2.1, 2.2

- [x] 2.4 Restructure `skills/simplify-implementation/SKILL.md`: add `## Roles` (Review =
      steps 0–4, artifact-only writes, ends with `validate`; Apply = steps 5–8, starts with
      `validate`, renders the ledger, never changes a fence verdict or disposition, raises
      disagreements to a human); tag each Workflow step with its role; add the artifact to
      the Coverage Gate and Test Pruning sections; script-table row; Verification items;
      Red Flags rows (Apply edited a verdict; hand-written ledger in the orchestrated path);
      invocation-mode line names `--simplify` as the operator request — **M**
      **Spec scenarios**: sw *Skill documents both roles*, *Review role writes nothing but
      the artifact*, *Apply role cannot promote a kept fence*, *Flag is the operator request*
      **Design decisions**: D4
      **Dependencies**: 2.3

- [x] 2.5 Test: content invariants in `skills/tests/simplify-implementation/test_skill_md.py`
      — Roles section exists with Review before Apply; every Workflow step carries a role
      tag; `simplify_review.py` appears in the script table and in Verification; the
      existing phase-ordering and two-sided-catalog invariants still hold — **XS**
      **Spec scenarios**: sw *Skill documents both roles*
      **Design decisions**: D4
      **Dependencies**: 2.4

- [x] Checkpoint: `skills/tests/simplify-implementation` green; `ruff check
      skills/simplify-implementation/scripts`; confirm only `wp-simplify-skill.write_allow` changed

## Phase 3 — wp-autopilot-phases: SIMPLIFY_REVIEW and SIMPLIFY_APPLY

- [ ] 3.0 Confirm `fix-autopilot-archetype-and-apply-outcome` is archived
      (`openspec/changes/archive/*-fix-autopilot-archetype-and-apply-outcome/` exists);
      rebase onto `main`; re-read `TRANSITIONS`, `transition()`, `LoopState`, and the
      `apply-outcome` contract; adjust the anchors below if their shape moved — **XS**
      **Design decisions**: D10
      **Dependencies**: None

- [ ] 3.1 Test: `transition()` resolves `SIMPLIFY_OR_VALIDATE` to `SIMPLIFY_REVIEW` when
      `state.simplify_enabled` and to `VALIDATE` otherwise, on both upstream edges;
      `SIMPLIFY_REVIEW` `findings`/`clean`/`failed` and `SIMPLIFY_APPLY`
      `complete`/`skipped`/`failed` resolve per D1; every other `TRANSITIONS` entry equals
      the pre-change table — **S**
      **Spec scenarios**: sw *Opt-in simplify phases after implementation review*, *Clean
      simplify review skips apply*, *Simplify phases still run when review is skipped*,
      *Flag enables the review phase*, *Flag absent leaves the edges unchanged*
      **Design decisions**: D1
      **Dependencies**: 3.0

- [ ] 3.2 Test: a schema-v5 `loop-state.json` fixture loads under v6 with the four new
      fields at defaults and every pre-existing field unchanged; v6 round-trips — **XS**
      **Spec scenarios**: sw *Schema v5 loop-state loads under v6*
      **Design decisions**: D6
      **Dependencies**: 3.0

- [ ] 3.3 Test: the existing end-to-end loop fixture without `--simplify` produces a
      `phase_history` equal to the pre-change golden — **S**
      **Spec scenarios**: sw *Default trace is unchanged without the flag*
      **Design decisions**: D1
      **Dependencies**: 3.0

- [ ] 3.4 Implement the state-machine edge, both `TRANSITIONS` rows, `LoopState` v6 fields
      and migration, and `--simplify` parsing into `simplify_enabled` (SKILL.md step 0
      block + `run_loop` kwarg, mirroring `--no-review`) — **M**
      **Spec scenarios**: all scenarios under 3.1–3.3
      **Design decisions**: D1, D6
      **Dependencies**: 3.1, 3.2, 3.3

- [ ] Checkpoint: `test_phase_transitions.py` and `test_loop_state.py` green; review the
      diff; confirm only `autopilot.py` and tests changed

- [ ] 3.5 Test: `_phase_simplify_review` — artifact with a `fix` finding → `findings` and
      `simplify_review_path` set; artifact with none → `clean`; artifact failing `validate`
      → `clean` + `skipped_reason: invalid_review_artifact`; `check_scope` exit 2 at review
      → `clean` + reason; dispatch exception → `failed`; when IMPL_REVIEW ran, its
      `test_quality` findings appear in the dispatch prompt — **S**
      **Spec scenarios**: sw *Invalid artifact is visible, not fatal*, *IMPL_REVIEW
      test-quality findings seed the review*, *Simplify review writes only the artifact*
      **Design decisions**: D2, D5, D7
      **Dependencies**: 3.4

- [ ] 3.6 Test: `_phase_simplify_apply` — scripted prune exit 2, contract exit 2, dual-run
      exit 2, unpinnable → `skipped` with matching reason and head == `B1` when a refactor
      commit existed; clean run → `complete`; ledger on disk equals `render-ledger` of the
      artifact; dispatch exception → `failed`; resume after prune commits reads `b1` and
      `simplify_review_path` from state — **M**
      **Spec scenarios**: sw *Dual-run failure reverts to the post-prune baseline*, *Prune
      commits match the reviewer's ledger*, *Resume at apply reconstructs the dual-run*,
      *Simplify apply writes commits*
      **Design decisions**: D3, D5, D6
      **Dependencies**: 3.4

- [ ] 3.7 Test: every simplify-phase outcome writes a `phase_history` entry with the nine
      evidence fields (`seams_removed` counted from applied seam-pattern findings); on a run
      reaching the dual-run, `simplify-report.json` exists in the change dir and
      `simplify_report_path` points at it; Convergence Report carries the SIMPLIFY line — **S**
      **Spec scenarios**: sw *Counters present on every outcome*, *Report lands in the change directory*
      **Design decisions**: D8
      **Dependencies**: 3.4

- [ ] 3.8 Implement `_phase_simplify_review` in `autopilot.py`: 3-step dispatch to the
      Review role, seed injection from IMPL_REVIEW findings, `simplify_review.py validate`
      on the artifact, `B0` and `simplify_review_path` recording, `findings`/`clean`
      outcome with reason, evidence counters — **S**
      **Spec scenarios**: all scenarios under 3.5 and 3.7
      **Design decisions**: D2, D5, D7, D8
      **Dependencies**: 3.5, 3.7

- [ ] 3.9 Implement `_phase_simplify_apply` in `autopilot.py`: 3-step dispatch to the Apply
      role, `render-ledger` into the change dir, `B1` recording, explicit `--report` path,
      refusal → `skipped` with reset to `B1`, evidence counters, Convergence Report line — **M**
      **Spec scenarios**: all scenarios under 3.6 and 3.7
      **Design decisions**: D3, D5, D6, D8
      **Dependencies**: 3.6, 3.7

- [ ] Checkpoint: `skills/tests/autopilot` green; review the cumulative diff against
      `wp-autopilot-phases.write_allow`; update checkboxes

- [ ] 3.10 Register both phases in every enumeration: `_HANDOFF_BOUNDARIES`
      (`IMPL_REVIEW→SIMPLIFY_REVIEW`, `IMPL_ITERATE→SIMPLIFY_REVIEW`,
      `SIMPLIFY_REVIEW→SIMPLIFY_APPLY`, `SIMPLIFY_REVIEW→VALIDATE`, `SIMPLIFY_APPLY→VALIDATE`),
      `phase_agent` (`_WORKTREE_PHASES`, `_PHASE_SIGNAL_KEYS`, `_PHASE_TASKS` — Review
      role prompt / Apply role prompt, expected outcomes), `handoff_builder` labels,
      `token_budget_check` dispatching phases and fallback models, `audit_log_validator`
      phase model and canonical-trace synthesis, `_PHASE_TO_REVIEW_TYPE`,
      `agents_config.WRITE_CAPABLE_PHASES` / `NON_TERMINAL_PHASES`, `archetypes.yaml`
      `phase_mapping` (→ `reviewer`, → `implementer`), both `convergence-state.schema.json`
      copies; update hard-coded phase-list fixtures in `skills/tests/autopilot/` — **M**
      **Spec scenarios**: sw *Simplify phases resolve distinct archetypes*
      **Design decisions**: D7, D10
      **Dependencies**: 3.4

- [ ] 3.11 Test: structural parity — one test enumerates the phase tables named in 3.10 and
      asserts both phases are present in each — **S**
      **Spec scenarios**: sw *Simplify phases resolve distinct archetypes*
      **Design decisions**: D7
      **Dependencies**: 3.10

- [ ] 3.12 `skills/autopilot/SKILL.md`: `--simplify` in Arguments; parsing block in step 0;
      `### 5.5. SIMPLIFY_REVIEW Phase (Opt-in)` and `### 5.6. SIMPLIFY_APPLY Phase (Opt-in)`
      cloned from the IMPL_ITERATE template with 3-step dispatch, outcome tables, seed
      injection, and artifact paths; fallback ladder steps; dispatch roster count;
      write-capable phase list; archetype table rows; Output artifact list — **S**
      **Spec scenarios**: sw *Opt-in simplify phases after implementation review*
      **Design decisions**: D1, D5, D7, D8
      **Dependencies**: 3.9, 3.10

- [ ] Checkpoint: full `skills/tests/autopilot` + `skills/autopilot/scripts/tests` +
      coordinator archetype config tests green; `ruff check skills/autopilot/scripts`

## Phase 4 — wp-review-diagnostic: read-only test-quality findings

- [x] 4.1 Test: a review round whose only consensus findings are `test_quality` at
      `criticality: low` converges (`_is_blocking` false for each); test lives in
      `skills/tests/parallel-infrastructure/` — **XS**
      **Spec scenarios**: sw *Test-quality findings do not block convergence alone*
      **Design decisions**: D9
      **Dependencies**: None

- [x] 4.2 `skills/parallel-review-implementation/SKILL.md`: Test quality checklist under
      Code Quality Review naming the Delete catalog smells and the four seam patterns, the
      `axis` mapping and `criticality: low` rule, the read-only constraint, and the note
      that these findings seed `SIMPLIFY_REVIEW`; add `test_quality`, `simplification`, and
      `behavioral_failure` to the Finding Types list — **S**
      **Spec scenarios**: sw *Self-mocking test is flagged*, *Checklist present in the skill*
      **Design decisions**: D9, D10
      **Dependencies**: None

- [x] 4.3 Test: content invariant in `skills/tests/parallel-review-implementation/` — the
      checklist section exists and names each smell and seam pattern; Finding Types includes
      `test_quality` — **XS**
      **Spec scenarios**: sw *Checklist present in the skill*
      **Design decisions**: D9
      **Dependencies**: 4.2

- [x] Checkpoint: `skills/tests/parallel-review-implementation` and the 4.1 test green;
      confirm only the package's `write_allow` changed

## Phase 5 — wp-docs-and-mirrors: prose in other skills and docs

- [ ] 5.1 Test: content invariants — `implement-feature/SKILL.md` and
      `iterate-on-implementation/SKILL.md` polish paragraphs reference `/autopilot --simplify`
      and do not state autopilot never runs simplify — **XS**
      **Spec scenarios**: sw *Polish paragraphs name the flag*
      **Design decisions**: D10
      **Dependencies**: 2.4, 3.12, 4.2

- [ ] 5.2 Update the two polish paragraphs; add a Review/Apply roles paragraph to
      `docs/guides/testing-policy.md` — **XS**
      **Spec scenarios**: sw *Polish paragraphs name the flag*, *Not default-on*
      **Design decisions**: D4, D10
      **Dependencies**: 5.1

- [ ] 5.3 Update `docs/autopilot-phase-archetype-resolution.md` (phase list, archetype
      table, dispatch matrix), `docs/skill-flow/README.md` (two SIMPLIFY nodes and edges;
      polish-edge prose), `docs/skills-catalogue.md` (autopilot and simplify-implementation
      rows) — **S**
      **Design decisions**: D7
      **Dependencies**: 5.2

- [ ] 5.4 Run `bash skills/install.sh --mode rsync --deps none --python-tools none` to
      resync `.claude/skills/` and `.agents/skills/`; confirm `skills/tests/install_sh` green — **XS**
      **Dependencies**: 5.3

- [ ] Checkpoint: content-invariant tests from 5.1 green; review the diff; confirm only
      the named SKILL.md files, `docs/`, and mirrors changed

## Phase 6 — wp-integration

- [ ] 6.1 Run the full skills suite (`skills/tests`, `skills/autopilot/scripts/tests`) and
      the coordinator archetype config tests; `ruff check` on touched packages — **S**
      **Dependencies**: all Phase 1–5 tasks

- [ ] 6.2 `openspec validate add-autopilot-simplify-phase --strict`; confirm every SHALL
      scenario in `specs/skill-workflow/spec.md` maps to at least one test task above — **XS**
      **Dependencies**: 6.1

- [ ] 6.3 Append the Implementation `PhaseRecord` via `write_both()`; update this file's
      checkboxes; commit and push — **XS**
      **Dependencies**: 6.2

<!-- GENERATED: begin coordinator:tasks-status -->
<!-- Informational projection — see openspec/changes/add-autopilot-simplify-phase/proposal.md "What Doesn't Change" -->
- [x] 1.1: Test: `simplify-review.schema.json` is a valid JSON Schema 2020-12 document; — done 2026-09-05
- [x] 1.2: Test: `type` and `review_type` enums are identical across canonical, — done 2026-09-05
- [x] 1.3: Implement the contract: confirm `simplify-review.schema.json`'s conditional rules (including — done 2026-09-05
- [x] 1.4: Implement the enum additions in all five copies (adding `behavioral_failure` to — done 2026-09-05
- [x] 2.1: Test: `simplify_review.py validate` exits 0 on the valid fixture, 2 on the — done 2026-09-05
- [x] 2.2: Test: round-trip on a synthetic git repo — `render-ledger` from an artifact with — done 2026-09-05
- [x] 2.3: Implement `skills/simplify-implementation/scripts/simplify_review.py` with — done 2026-09-05
- [x] 2.4: Restructure `skills/simplify-implementation/SKILL.md`: add `## Roles` (Review = — done 2026-09-05
- [x] 2.5: Test: content invariants in `skills/tests/simplify-implementation/test_skill_md.py` — done 2026-09-05
- [ ] 3.0: Confirm `fix-autopilot-archetype-and-apply-outcome` is archived — pending
- [ ] 3.1: Test: `transition()` resolves `SIMPLIFY_OR_VALIDATE` to `SIMPLIFY_REVIEW` when — pending — blocked on 3.0
- [ ] 3.2: Test: a schema-v5 `loop-state.json` fixture loads under v6 with the four new — pending — blocked on 3.0
- [ ] 3.3: Test: the existing end-to-end loop fixture without `--simplify` produces a — pending — blocked on 3.0
- [ ] 3.4: Implement the state-machine edge, both `TRANSITIONS` rows, `LoopState` v6 fields — pending — blocked on 3.1, 3.2, 3.3
- [ ] 3.5: Test: `_phase_simplify_review` — artifact with a `fix` finding → `findings` and — pending — blocked on 3.4
- [ ] 3.6: Test: `_phase_simplify_apply` — scripted prune exit 2, contract exit 2, dual-run — pending — blocked on 3.4
- [ ] 3.7: Test: every simplify-phase outcome writes a `phase_history` entry with the nine — pending — blocked on 3.4
- [ ] 3.8: Implement `_phase_simplify_review` in `autopilot.py`: 3-step dispatch to the — pending — blocked on 3.5, 3.7
- [ ] 3.9: Implement `_phase_simplify_apply` in `autopilot.py`: 3-step dispatch to the Apply — pending — blocked on 3.6, 3.7
- [ ] 3.10: Register both phases in every enumeration: `_HANDOFF_BOUNDARIES` — pending — blocked on 3.4
- [ ] 3.11: Test: structural parity — one test enumerates the phase tables named in 3.10 and — pending — blocked on 3.10
- [ ] 3.12: `skills/autopilot/SKILL.md`: `--simplify` in Arguments; parsing block in step 0; — pending — blocked on 3.9, 3.10
- [x] 4.1: Test: a review round whose only consensus findings are `test_quality` at — done 2026-09-05
- [x] 4.2: `skills/parallel-review-implementation/SKILL.md`: Test quality checklist under — done 2026-09-05
- [x] 4.3: Test: content invariant in `skills/tests/parallel-review-implementation/` — the — done 2026-09-05
- [ ] 5.1: Test: content invariants — `implement-feature/SKILL.md` and — pending — blocked on 3.12
- [ ] 5.2: Update the two polish paragraphs; add a Review/Apply roles paragraph to — pending — blocked on 5.1
- [ ] 5.3: Update `docs/autopilot-phase-archetype-resolution.md` (phase list, archetype — pending — blocked on 5.2
- [ ] 5.4: Run `bash skills/install.sh --mode rsync --deps none --python-tools none` to — pending — blocked on 5.3
- [ ] 6.1: Run the full skills suite (`skills/tests`, `skills/autopilot/scripts/tests`) and — pending
- [ ] 6.2: `openspec validate add-autopilot-simplify-phase --strict`; confirm every SHALL — pending — blocked on 6.1
- [ ] 6.3: Append the Implementation `PhaseRecord` via `write_both()`; update this file's — pending — blocked on 6.2
<!-- GENERATED: end coordinator:tasks-status -->
