# Tasks: Make expedite fail closed on missing validation

> Change ID: `make-expedite-fail-closed-on-missing-validation`
> Roadmap item: `ri-02` (`verification-enforcement-discipline`)

## Status

- [x] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## 1. Missing report blocks (wp-expedite)

- [ ] 1.1 Write failing tests for the missing-report check in `skills/expedite/scripts/tests/test_expedite.py` (S)
  - Replace `TestValidationReportCheck.test_skip_when_path_none` with `test_fail_when_no_report`: status `fail`, detail names the three probed paths, action contains `/validate-feature`.
  - Replace `TestExpedite.test_ready_when_skips_only` with `test_blocked_when_no_validation_report`: no reports → `ready is False`.
  - Update `TestCli.test_exit_zero_when_ready` and `TestCli.test_json_output_shape`, which today rely on report-less READY: give them a passing report.
  - Add `test_ready_with_rework_skip_only`: passing validation report + no rework report → READY (the remaining legitimate `skip`).
  - Add `test_cli_exits_1_without_report`.
  **Spec scenarios**: expedite.missing-report-blocks, expedite.passing-report-ready
  **Design decisions**: D1
  **Dependencies**: None
- [ ] 1.2 Write failing tests for change-dir derivation (XS)
  - Report only under `openspec/changes/<id>/reports/` → `pre_merge_gate` receives `change_dir == openspec/changes/<id>` (monkeypatch `gate_logic.pre_merge_gate` to capture the kwarg).
  **Spec scenarios**: expedite.change-dir-from-id
  **Design decisions**: D3
  **Dependencies**: None
- [ ] 1.3 Make `check_validation_report` return `fail` on a missing report (S)
  - New signature `check_validation_report(report_path, *, change_id, repo_root, accept_missing=None)`; the detail lists the probed paths (reuse `_probe_paths`'s candidate list, extracted to `_candidate_paths`).
  **Dependencies**: 1.1
- [ ] 1.4 Derive `change_dir` from the change id (XS)
  **Dependencies**: 1.2, 1.3
- [ ] Checkpoint: run tests, review diff, verify scope

## 2. Recorded override (wp-expedite)

- [ ] 2.1 Write failing tests for `--accept-missing-validation` (S)
  - With reason and no report: exit 0, detail starts `OVERRIDE — no validation report accepted: <reason>`, JSON `overrides == [{"check": "validation_report", "reason": "<reason>"}]`.
  - Text output contains `OVERRIDE`.
  - `""` and `"   "` → exit 2, nothing on stdout.
  - With a failing report plus the flag: check stays `fail`, `overrides == []`.
  - Without the flag: JSON still carries `"overrides": []`.
  - The `OVERRIDE — ` prefix is one module constant (`OVERRIDE_PREFIX`) that tests import.
  **Spec scenarios**: expedite.overrides-key-always-present, expedite.override-records-reason, expedite.override-empty-reason-rejected, expedite.override-ignored-when-report-exists
  **Design decisions**: D2
  **Dependencies**: 1.3
- [ ] 2.2 Add the `overrides` field to `Verdict` (XS)
  **Dependencies**: 2.1
- [ ] 2.3 Add the `--accept-missing-validation` CLI flag (S)
  - Reject a blank reason via `p.error(...)` (exit 2) before calling `expedite()`; thread the reason through `expedite(..., accept_missing_validation=...)`.
  **Dependencies**: 2.2
- [ ] Checkpoint: run tests, review diff, verify scope

## 3. SKILL.md agrees with the code (wp-expedite)

- [ ] 3.1 Write the failing drift test `skills/expedite/scripts/tests/test_skill_md_drift.py` (S)
  - Observe each check's reachable statuses by running it against fixtures; parse the SKILL.md `| Check fail | Resolution |` table; assert the four properties in design D4. It must fail against today's SKILL.md line 67.
  **Spec scenarios**: expedite.skill-table-drift
  **Design decisions**: D4
  **Dependencies**: 1.3
- [ ] 3.2 Correct the SKILL.md status table (XS)
  - Keep the `validation_report` (no file) row; add the override as its resolution alternative; rewrite line 67 so `skip` is documented only for `rework_report`.
  **Dependencies**: 3.1
- [ ] 3.3 Document `--accept-missing-validation` in SKILL.md (XS)
  - Usage line, the `OVERRIDE —` detail, and `overrides` in the JSON shape block.
  **Dependencies**: 2.3
- [ ] 3.4 Update `docs/mental-models.md` G2 (XS)
  - Test count, and "a missing validation report blocks; override is recorded".
  **Dependencies**: 3.2
- [ ] 3.5 Re-sync runtime mirrors (XS)
  - `bash skills/install.sh --mode rsync --deps none --python-tools none`; commit only `.claude/skills/expedite/` and `.agents/skills/expedite/` changes.
  **Dependencies**: 3.2, 3.3
- [ ] Checkpoint: run tests, review diff, verify scope

## 4. Verification

- [ ] 4.1 Run the expedite suite (XS)
  - `skills/.venv/bin/python -m pytest skills/expedite/scripts/tests -q`
  **Dependencies**: 3.5
- [ ] 4.2 Run strict OpenSpec validation (XS)
  - `openspec validate make-expedite-fail-closed-on-missing-validation --strict`
  **Dependencies**: 4.1
