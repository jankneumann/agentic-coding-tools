# Tasks — Findings-Model + Enforcement Gate for `validate-feature`

> Test-first ordering within each phase. Each implementation task lists the test
> it depends on. Spec scenarios and design decisions are referenced inline.
> Size estimates: XS / S / M / L.

## 1. Findings model + auto-fix tier (Phase 1)

- [ ] 1.1 Write contract test at two levels: (a) `review-findings.schema.json` is
  byte-for-byte unchanged (its `disposition` enum, `axis`, `severity`, and
  `review_type` enum all intact); (b) a complete `validation-findings.json`
  (envelope + `phase_statuses[]` + `findings[]`) validates against
  `validation-findings.schema.json`, a validation finding with no `fixability`
  reads as `escalate`, and one with `triage_state: skip` validates. **(S)**
  **Spec scenarios**: validate-feature-findings.new-self-contained-validation-findings-schema-review-schema-untouched,
  validate-feature-findings.validation-findings-file-validates-against-its-own-schema
  **Design decisions**: D1
  **Dependencies**: None
- [ ] 1.2 Add a new self-contained
  `openspec/schemas/validation-findings.schema.json` (envelope: `schema_version`,
  `change_id`, validated commit; `phase_statuses[]` of `{phase,status,reason}`;
  `findings[]` whose item is a validation finding record with `id`, `type`,
  `criticality`, `description`, `phase`, file/endpoint, optional `fixability`,
  optional `triage_state`). Do NOT modify `review-findings.schema.json`. Verify with
  1.1. **(S)**
  **Spec scenarios**: validate-feature-findings.findings-carry-a-fixability-tier,
  validate-feature-findings.new-self-contained-validation-findings-schema-review-schema-untouched
  **Design decisions**: D1
  **Dependencies**: 1.1
- [ ] 1.3 Write test for shared `emit_finding()` and `record_phase_status()`
  helpers: `emit_finding()` appends a schema-valid record; `record_phase_status()`
  writes a per-phase status (`pass`/`fail`/`skip`/`not-run`/`error`) + reason to
  `validation-findings.json`. **(S)**
  **Spec scenarios**: validate-feature-findings.phases-emit-structured-findings,
  validate-feature-findings.phases-record-explicit-execution-status
  **Dependencies**: 1.2
- [ ] 1.4 Implement `emit_finding()` + `record_phase_status()` (e.g.
  `scripts/findings.py`) and wire EVERY failable phase (`smoke`, `security`,
  `e2e`, `architecture`, `spec`, `logs`, `deploy`, `gen-eval`, `ci`) to call both
  — emitting findings on issues and always recording an explicit status.
  Architecture phase already emits findings — adapt it to the shared helper.
  Verify with 1.3. **(L)**
  **Spec scenarios**: validate-feature-findings.phases-emit-structured-findings,
  validate-feature-findings.clean-phase-produces-no-findings,
  validate-feature-findings.phases-record-explicit-execution-status
  **Dependencies**: 1.3
- [ ] 1.5 Write test for the fixability classifier: mechanical finding-types
  (formatting, import-order, naming) → `auto-fix`; everything else → `escalate`.
  **(S)**
  **Spec scenarios**: validate-feature-findings.findings-carry-a-fixability-tier
  **Design decisions**: D3
  **Dependencies**: 1.2
- [ ] 1.6 Implement the classifier with a mechanical-type allowlist; default
  `escalate`. Verify with 1.5. **(S)**
  **Design decisions**: D3
  **Dependencies**: 1.5
- [ ] 1.7 Write test for the auto-fix triage step: an `auto-fix` finding is
  applied and resolved on a passing re-run; a regressing fix is reverted and
  re-classified `escalate`. **(M)**
  **Spec scenarios**: validate-feature-findings.auto-fix-triage-step
  **Design decisions**: D2
  **Dependencies**: 1.4, 1.6
- [ ] 1.8 Implement the auto-fix triage step delegating to `simplify` /
  `fix-scrub`, re-running the affected phase, reverting on regression. Verify with
  1.7. **(M)**
  **Spec scenarios**: validate-feature-findings.auto-fix-triage-step
  **Design decisions**: D2
  **Dependencies**: 1.7
- [ ] 1.9 Write test: the report renderer produces `validation-report.md` from
  `validation-findings.json`, deriving each phase result from its status record,
  and asserts no pass for a phase whose status is not `pass` or that has an
  unresolved finding. **(S)**
  **Spec scenarios**: validate-feature-findings.report-rendered-from-findings-file,
  validate-feature-findings.phases-record-explicit-execution-status
  **Dependencies**: 1.4
- [ ] 1.10 Refactor SKILL.md §11/§12 report step to render from the findings file;
  update phase sections to document the finding-emit contract. Verify with 1.9.
  **(M)**
  **Spec scenarios**: validate-feature-findings.report-rendered-from-findings-file
  **Dependencies**: 1.9
- [ ] 1.C **Checkpoint**: `pytest skills/tests/validate-feature/` green; a sample
  run writes a schema-valid `validation-findings.json` and a report rendered from
  it.

## 2. Pre-push enforcement gate (Phase 2)

- [ ] 2.1 Write test for the critical-subset runner: it executes only `smoke`, spec
  task-drift, and the **static** `security` checks (dependency audit, secret scan,
  service-free SAST — not the dynamic ZAP scan), returns non-zero when any produces
  an unresolved critical finding, and treats a live-service check that records
  `skip`/`not-run` (e.g. smoke with no stack) as an unresolved critical. **(M)**
  **Spec scenarios**: validate-feature-gate.critical-subset-definition,
  validate-feature-gate.critical-finding-blocks-the-push,
  validate-feature-gate.a-live-service-check-that-cannot-run-blocks-the-push
  **Design decisions**: D4
  **Dependencies**: 1.4
- [ ] 2.2 Implement the critical-subset runner reusing the existing phase scripts
  and the §7.0 task-drift gate. Verify with 2.1. **(M)**
  **Spec scenarios**: validate-feature-gate.critical-subset-definition
  **Design decisions**: D4
  **Dependencies**: 2.1
- [ ] 2.3 Write test for inert-until-enabled + kill-switch: with `core.hooksPath=
  .githooks` and the hook file present but no `validate-gate.enabled` marker, `git
  push` runs no checks (hook exits 0); after opt-in it runs; `VALIDATE_GATE=0` skips
  all checks. **(S)**
  **Spec scenarios**: validate-feature-gate.checked-in-hook-is-inert-until-enabled,
  validate-feature-gate.gate-enabled-on-request,
  validate-feature-gate.kill-switch-disables-the-gate
  **Dependencies**: 2.2
- [ ] 2.4 Add the `.githooks/pre-push` hook (inert no-op unless the
  `validate-gate.enabled` marker is set) + opt-in installer that sets the marker,
  honoring `VALIDATE_GATE=0` and printing escape-hatch guidance on block. Verify
  with 2.3. **(M)**
  **Spec scenarios**: validate-feature-gate.opt-in-pre-push-enforcement-gate,
  validate-feature-gate.checked-in-hook-is-inert-until-enabled,
  validate-feature-gate.kill-switch-disables-the-gate
  **Design decisions**: D4
  **Dependencies**: 2.3
- [ ] 2.5 Document the gate (install, kill-switch, `--no-verify`) in SKILL.md and
  the worktree/session-completion guides. **(S)**
  **Dependencies**: 2.4
- [ ] 2.C **Checkpoint**: with the hook installed, a drifted `tasks.md` blocks a
  push with the unchecked task IDs; `VALIDATE_GATE=0` and `--no-verify` both pass.

## 3. Ephemeral disposable-worktree mode (Phase 3)

- [ ] 3.1 Write test: on a clean tree `--ephemeral` runs in a scratch worktree
  cloned from `HEAD`, records the validated commit SHA, and removes the worktree on
  completion; on a dirty tree it fails fast naming `--include-dirty`; with
  `--include-dirty` it materializes the working-tree/index state into the scratch
  worktree. **(M)**
  **Spec scenarios**: validate-feature-ephemeral.ephemeral-disposable-worktree-mode,
  validate-feature-ephemeral.dirty-worktree-fails-fast,
  validate-feature-ephemeral.scratch-worktree-discarded-on-completion
  **Design decisions**: D5
  **Dependencies**: 1.4
- [ ] 3.2 Implement `--ephemeral` (+ `--include-dirty`) over the `worktree` skill
  lifecycle; guard against a dirty tree, record the validated commit/tree, and copy
  the report + findings file back to the change branch before teardown. Verify with
  3.1. **(M)**
  **Spec scenarios**: validate-feature-ephemeral.report-still-lands-on-the-change-branch
  **Design decisions**: D5
  **Dependencies**: 3.1
- [ ] 3.3 Write test: under a stubbed cloud-harness `detect()`, `--ephemeral`
  downgrades to in-place and logs the downgrade. **(S)**
  **Spec scenarios**: validate-feature-ephemeral.cloud-harness-fallback
  **Dependencies**: 3.2
- [ ] 3.4 Implement the cloud-harness fallback via `environment_profile.detect()`.
  Verify with 3.3. **(S)**
  **Spec scenarios**: validate-feature-ephemeral.cloud-harness-fallback
  **Design decisions**: D5
  **Dependencies**: 3.3
- [ ] 3.C **Checkpoint**: an `--ephemeral` run leaves `git status` clean on the
  branch while the report lands in `openspec/changes/<change-id>/`.

## 4. Interactive per-finding triage (Phase 4)

- [ ] 4.1 Write test for the `triage_state` apply/render path: `approve` / `fix` /
  `skip` are written back to `validation-findings.json` (leaving `disposition`
  untouched) and a re-run does not re-present resolved findings. **(M)**
  **Spec scenarios**: validate-feature-triage.interactive-per-finding-triage,
  validate-feature-triage.resumable-curated-state
  **Design decisions**: D6
  **Dependencies**: 1.4
- [ ] 4.2 Implement the shared `triage_state` apply/render path (single source for
  both surfaces). Verify with 4.1. **(M)**
  **Spec scenarios**: validate-feature-triage.resumable-curated-state
  **Design decisions**: D6
  **Dependencies**: 4.1
- [ ] 4.3 Write test for `--auto` / `-y`: deterministic defaults — resolved
  `auto-fix` findings → `triage_state: fix`, unresolved `escalate` findings →
  `triage_state: skip`, never `approve`; report records auto application. **(S)**
  **Spec scenarios**: validate-feature-triage.non-interactive-auto-mode
  **Dependencies**: 4.2
- [ ] 4.4 Implement `--triage` (AskUserQuestion in-harness / CLI prompt loop) and
  `--auto`/`-y`. Verify with 4.1 and 4.3. **(M)**
  **Spec scenarios**: validate-feature-triage.interactive-per-finding-triage,
  validate-feature-triage.triage-surface-adapts-to-harness,
  validate-feature-triage.non-interactive-auto-mode
  **Design decisions**: D6
  **Dependencies**: 4.3
- [ ] 4.5 Document `--triage` / `--auto` and the fixability/triage_state lifecycle in SKILL.md.
  **(S)**
  **Dependencies**: 4.4
- [ ] 4.C **Checkpoint**: a triage session marks a finding `skip`; a re-run skips
  it; `--auto` applies defaults headlessly.

## 5. Cross-cutting

- [ ] 5.1 Run `openspec validate validate-feature-findings-gate --strict` and fix
  any spec issues. **(XS)**
  **Dependencies**: 1.C
- [ ] 5.2 Update `skills/validate-feature/SKILL.md` argument list + phase table to
  reflect `--ephemeral`, `--triage`, `--auto`, and the gate. **(S)**
  **Dependencies**: 2.5, 3.C, 4.5
- [ ] 5.3 Sync runtime skill copies via `install.sh` (per CLAUDE.md skills guide).
  **(XS)**
  **Dependencies**: 5.2
