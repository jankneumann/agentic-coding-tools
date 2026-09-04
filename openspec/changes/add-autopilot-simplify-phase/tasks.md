# Tasks — add-autopilot-simplify-phase

Five phases, one per work package plus a sequencing precheck. Test tasks precede the
implementation they verify (TDD RED → GREEN). Sizes per the plan-feature Task Sizing
Reference; no task is L or XL.

Capability short name: `sw` = `skill-workflow`. Contracts: none (see `contracts/README.md`).

---

## Phase 0 — precheck: sequencing gate

- [ ] 0.1 Confirm `fix-autopilot-archetype-and-apply-outcome` is archived
      (`openspec/changes/archive/*-fix-autopilot-archetype-and-apply-outcome/` exists);
      rebase onto `main`; re-read `TRANSITIONS`, `transition()`, `LoopState`, and the
      `apply-outcome` contract; adjust the Phase 1 anchors below if their shape moved — **XS**
      **Design decisions**: D8
      **Dependencies**: None

## Phase 1 — wp-autopilot-phase: the opt-in state-machine phase

- [ ] 1.1 Test: `transition()` resolves `SIMPLIFY_OR_VALIDATE` to `SIMPLIFY` when
      `state.simplify_enabled` and to `VALIDATE` otherwise, on both the IMPL_REVIEW
      `converged` edge and the IMPL_ITERATE `complete` edge under `--no-review`; every other
      `TRANSITIONS` entry equals the pre-change table — **S**
      **Spec scenarios**: sw *Opt-in SIMPLIFY phase after implementation review*, *SIMPLIFY
      still runs when review is skipped*, *Flag enables the phase*, *Flag absent leaves the
      edge unchanged*
      **Design decisions**: D1
      **Dependencies**: 0.1

- [ ] 1.2 Test: a schema-v5 `loop-state.json` fixture loads under v6 with
      `simplify_enabled=False`, `simplify_baselines=None`, `simplify_report_path=None`, and
      every pre-existing field unchanged; a v6 round-trip preserves the new fields — **XS**
      **Spec scenarios**: sw *Schema v5 loop-state loads under v6*
      **Design decisions**: D3
      **Dependencies**: 0.1

- [ ] 1.3 Test: the existing end-to-end loop fixture run without `--simplify` produces a
      `phase_history` equal to the pre-change golden (phases and outcomes) — **S**
      **Spec scenarios**: sw *Default trace is unchanged without the flag*
      **Design decisions**: D1
      **Dependencies**: 0.1

- [ ] 1.4 Implement the state-machine edge: `SIMPLIFY_OR_VALIDATE` in `TRANSITIONS` and
      `transition()`, `TRANSITIONS["SIMPLIFY"]`, `LoopState` v6 fields and migration, and
      `--simplify` parsing into `simplify_enabled` (SKILL.md step 0 block + `run_loop`
      kwarg, mirroring `--no-review`) — **M**
      **Spec scenarios**: all scenarios listed under 1.1–1.3
      **Design decisions**: D1, D3
      **Dependencies**: 1.1, 1.2, 1.3

- [ ] Checkpoint: `skills/tests/autopilot/test_phase_transitions.py` and
      `test_loop_state.py` green; review the diff; confirm only `autopilot.py` and tests
      changed

- [ ] 1.5 Test: `_phase_simplify` outcome mapping with scripted script results — scope
      exit 2, prune exit 2, contract exit 2, dual-run exit 2, nothing-to-do each yield
      `skipped` with the matching `skipped_reason`; on dual-run exit 2 after a refactor commit
      the worktree head equals `B1`; a dispatch exception yields `failed`; a clean run yields
      `complete` — **M**
      **Spec scenarios**: sw *Rule of 500 exceeded is a skip, not a failure*, *Dual-run
      failure reverts to the post-prune baseline*, *Prune commits are test-only and ledgered*
      **Design decisions**: D2
      **Dependencies**: 1.4

- [ ] 1.6 Test: every SIMPLIFY outcome writes a `phase_history` entry with the six evidence
      fields (zeros and non-null `skipped_reason` on `skipped`); on a run reaching the
      dual-run, `openspec/changes/<id>/simplify-report.json` exists and
      `simplify_report_path` points at it; on resume after prune commits, the dual-run
      baseline is read from `simplify_baselines.b1` — **S**
      **Spec scenarios**: sw *Counters present on every outcome*, *Report lands in the
      change directory*, *Resume mid-SIMPLIFY reconstructs the dual-run*
      **Design decisions**: D5, D6
      **Dependencies**: 1.4

- [ ] 1.7 Implement `_phase_simplify` in `autopilot.py`: 3-step dispatch, `B0`/`B1`
      recording, explicit `--report` / ledger paths, refusal → `skipped` + reset to `B1`,
      evidence counters from `git diff --shortstat`, `check_test_prune --json`, the dual-run
      exit code, and the agent-reported `seams_removed`; Convergence Report SIMPLIFY line — **M**
      **Spec scenarios**: all scenarios listed under 1.5–1.6
      **Design decisions**: D2, D4, D5, D6
      **Dependencies**: 1.5, 1.6

- [ ] Checkpoint: `skills/tests/autopilot` green; review the cumulative diff against
      `wp-autopilot-phase.write_allow`; update checkboxes

- [ ] 1.8 Register `SIMPLIFY` in every phase enumeration: `_HANDOFF_BOUNDARIES`
      (`IMPL_REVIEW→SIMPLIFY`, `IMPL_ITERATE→SIMPLIFY`, `SIMPLIFY→VALIDATE`),
      `phase_agent` (`_WORKTREE_PHASES`, `_PHASE_SIGNAL_KEYS`, `_PHASE_TASKS`, expected
      outcomes), `handoff_builder` labels, `token_budget_check` dispatching phases and
      fallback model, `audit_log_validator` phase model and canonical-trace synthesis (SIMPLIFY
      optional), `agents_config.WRITE_CAPABLE_PHASES` / `NON_TERMINAL_PHASES`,
      `archetypes.yaml` `phase_mapping` (→ `implementer`), both
      `convergence-state.schema.json` copies; update the hard-coded phase-list fixtures in
      `skills/tests/autopilot/` — **M**
      **Spec scenarios**: sw *SIMPLIFY phase resolves an archetype and is dispatched*,
      *Simplify phase writes artifacts*
      **Design decisions**: D4, D9
      **Dependencies**: 1.4

- [ ] 1.9 Test: structural parity — one test enumerates the phase tables named in 1.8 and
      asserts `SIMPLIFY` is present in each, so a future table added without it fails CI — **S**
      **Spec scenarios**: sw *SIMPLIFY phase resolves an archetype and is dispatched*
      **Design decisions**: D4
      **Dependencies**: 1.8

- [ ] 1.10 `skills/autopilot/SKILL.md`: `--simplify` in Arguments; parsing block in step 0;
      new `### 5.5. SIMPLIFY Phase (Opt-in)` section cloned from the IMPL_ITERATE template
      with the 3-step dispatch, outcome table, and artifact paths; fallback ladder step;
      dispatch roster count; write-capable phase list; archetype table row; Output artifact
      list — **S**
      **Spec scenarios**: sw *Opt-in SIMPLIFY phase after implementation review*
      **Design decisions**: D1, D2, D4, D5
      **Dependencies**: 1.7, 1.8

- [ ] Checkpoint: full `skills/tests/autopilot` + `skills/autopilot/scripts/tests` +
      `agent-coordinator` archetype config tests green; `ruff check skills/autopilot/scripts`

## Phase 2 — wp-review-diagnostic: read-only test-quality findings (parallel with Phase 1)

- [ ] 2.1 Test: a finding with `type: test_quality`, `axis: readability`, `criticality: low`
      validates against the canonical schema and the install mirror; the `type` enum is
      identical across canonical, mirror, `consensus-report.schema.json` (both copies), and
      `vendor_review._FALLBACK_ENUMS` — **XS**
      **Spec scenarios**: sw *test_quality finding validates*, *type enum identical across
      all copies*, *Existing schema fields preserved*
      **Design decisions**: D7, D9
      **Dependencies**: None

- [ ] 2.2 Test: a review round whose only consensus findings are `test_quality` at
      `criticality: low` converges (`_is_blocking` returns false for each); test lives in
      `skills/tests/parallel-infrastructure/` — **XS**
      **Spec scenarios**: sw *Test-quality findings do not block convergence alone*
      **Design decisions**: D7
      **Dependencies**: None

- [ ] 2.3 Implement the enum addition in all five copies (adding `behavioral_failure` to
      the consensus-report enums where missing, per D9); update the enum list in
      `skills/validate-feature/scripts/tests/test_linters.py` — **S**
      **Spec scenarios**: all scenarios listed under 2.1–2.2
      **Design decisions**: D7, D9
      **Dependencies**: 2.1, 2.2

- [ ] 2.4 `skills/parallel-review-implementation/SKILL.md`: Test quality checklist under
      Code Quality Review naming the Delete catalog smells and the four seam patterns, the
      `axis` mapping and `criticality: low` rule, and the read-only constraint; add
      `test_quality` (and `behavioral_failure`) to the Finding Types list — **S**
      **Spec scenarios**: sw *Self-mocking test is flagged*, *Checklist present in the skill*
      **Design decisions**: D7, D9
      **Dependencies**: 2.3

- [ ] 2.5 Test: content invariant in `skills/tests/parallel-review-implementation/` — the
      checklist section exists and names each smell and seam pattern; Finding Types includes
      `test_quality` — **XS**
      **Spec scenarios**: sw *Checklist present in the skill*
      **Design decisions**: D7
      **Dependencies**: 2.4

- [ ] Checkpoint: `skills/tests/parallel-infrastructure`, `skills/tests/merge-pull-requests`,
      `skills/tests/parallel-review-implementation`, `skills/validate-feature/scripts/tests`
      green; confirm only the package's `write_allow` changed

## Phase 3 — wp-docs-and-mirrors: prose in other skills and docs

- [ ] 3.1 Test: content invariants — `implement-feature/SKILL.md` and
      `iterate-on-implementation/SKILL.md` polish paragraphs reference `/autopilot --simplify`
      and do not state autopilot never runs simplify; `simplify-implementation/SKILL.md`
      invocation-mode line names the flag as the operator request — **XS**
      **Spec scenarios**: sw *Polish paragraphs name the flag*, *Flag is the operator request*
      **Design decisions**: D8
      **Dependencies**: 1.10, 2.4

- [ ] 3.2 Update the three SKILL.md files from 3.1 (invocation mode, Red Flags row,
      polish paragraphs) — **S**
      **Spec scenarios**: sw *Polish paragraphs name the flag*, *Not default-on*, *Flag is the
      operator request*
      **Design decisions**: D8
      **Dependencies**: 3.1

- [ ] 3.3 Update `docs/autopilot-phase-archetype-resolution.md` (phase list, archetype
      table, dispatch matrix), `docs/skill-flow/README.md` (SIMPLIFY node and edges in the
      mermaid graph; polish-edge prose), `docs/skills-catalogue.md` (autopilot and
      simplify-implementation rows) — **S**
      **Design decisions**: D4
      **Dependencies**: 3.2

- [ ] 3.4 Run `bash skills/install.sh --mode rsync --deps none --python-tools none` to
      resync `.claude/skills/` and `.agents/skills/`; confirm `skills/tests/install_sh` green — **XS**
      **Dependencies**: 3.3

- [ ] Checkpoint: content-invariant tests from 3.1 green; review the diff; confirm only
      the three SKILL.md files, `docs/`, and mirrors changed

## Phase 4 — wp-integration

- [ ] 4.1 Run the full skills suite (`skills/tests`, `skills/autopilot/scripts/tests`) and
      the coordinator archetype config tests; `ruff check` on touched packages — **S**
      **Dependencies**: all Phase 1–3 tasks

- [ ] 4.2 `openspec validate add-autopilot-simplify-phase --strict`; confirm every SHALL
      scenario in `specs/skill-workflow/spec.md` maps to at least one test task above — **XS**
      **Dependencies**: 4.1

- [ ] 4.3 Append the Implementation `PhaseRecord` via `write_both()`; update this file's
      checkboxes; commit and push — **XS**
      **Dependencies**: 4.2
