# Tasks: Make expedite fail closed on missing validation

> Change ID: `make-expedite-fail-closed-on-missing-validation`
> Roadmap item: `ri-02` (`verification-enforcement-discipline`)

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## 1. Missing report blocks (wp-expedite)

- [x] 1.1 Write failing tests for the missing-report check in `skills/expedite/scripts/tests/test_expedite.py` (S)
  - Replace `TestValidationReportCheck.test_skip_when_path_none` with `test_fail_when_no_report`: status `fail`, detail names the three probed paths, action contains `/validate-feature`.
  - Replace `TestExpedite.test_ready_when_skips_only` with `test_blocked_when_no_validation_report`: no reports → `ready is False`.
  - Add `test_ready_with_rework_skip_only`: passing validation report + no rework report → READY (the remaining legitimate `skip`).
  - Add `test_cli_exits_1_without_report`.
  - Rewrite `TestCli.test_exit_zero_when_ready` and `TestCli.test_json_output_shape` to write a passing report first (both currently rely on a report-less READY).
  - Add `test_explicit_nonexistent_path_is_missing`: `--validation-report <path that does not exist>` → `fail` with `/validate-feature` action; with `--accept-missing-validation` the override applies.
  - Add `test_unreadable_report_fails_and_is_not_overridable`: a report path that exists but cannot be read (e.g. a directory) → `fail`, and `--accept-missing-validation` leaves it `fail` with `overrides == []`.
  - Add `test_probed_directory_candidate_is_unreadable_not_missing`: no `--validation-report`, and `openspec/changes/<id>/validation-report.md` is a directory → `fail` (unreadable, not missing), and `--accept-missing-validation` leaves it `fail` with `overrides == []`.
  - Add `test_ready_non_deployable_spec_only_report`: `work-packages.yaml` declares no deployable surface and the report carries only `## Spec Compliance: pass` → READY (also exercises D3's change-dir derivation).
  **Spec scenarios**: expedite.missing-report-blocks, expedite.explicit-path-missing, expedite.unreadable-report-fails, expedite.passing-report-ready
  **Design decisions**: D1
  **Dependencies**: None
- [x] 1.2 Write failing tests for change-dir derivation (XS)
  - Report only under `openspec/changes/<id>/reports/` → `pre_merge_gate` receives `change_dir == openspec/changes/<id>` (monkeypatch `gate_logic.pre_merge_gate` to capture the kwarg).
  **Spec scenarios**: expedite.change-dir-from-id
  **Design decisions**: D3
  **Dependencies**: None
- [x] 1.3 Make `check_validation_report` return `fail` on a missing report (S)
  - New signature `check_validation_report(report_path, *, change_id, repo_root, accept_missing=None)`; the detail lists the probed paths (reuse `_probe_paths`'s candidate list, extracted to `_candidate_paths`).
  - Discovery distinguishes absent from invalid: `_probe_paths` returns the first candidate that **exists** (`exists()`, not `is_file()`), so a probed directory or unreadable file reaches the unreadable-report branch and fails without being overridable; only "no candidate exists" counts as missing.
  - Update the four direct callers in `test_expedite.py` (`test_pass_when_all_hard_gates_pass`, `test_fail_when_smoke_fails`, `test_fail_when_security_fails`, `test_fail_when_e2e_fails`) to pass `change_id=` and `repo_root=`; they raise `TypeError` otherwise.
  **Dependencies**: 1.1
- [x] 1.4 Derive `change_dir` from the change id (XS)
  **Dependencies**: 1.2, 1.3
- [x] Checkpoint: run tests, review diff, verify scope

## 2. Recorded override (wp-expedite)

- [x] 2.1 Write failing tests for `--accept-missing-validation` (S)
  - With reason and no report: exit 0, detail starts `OVERRIDE — no validation report accepted: <reason>`, JSON `overrides == [{"check": "validation_report", "reason": "<reason>"}]`.
  - Text output contains `OVERRIDE`.
  - `""` and `"   "` → exit 2, nothing on stdout.
  - With a failing report plus the flag: check stays `fail`, `overrides == []`.
  - Without the flag: JSON still carries `"overrides": []`.
  - The `OVERRIDE — ` prefix is one module constant (`OVERRIDE_PREFIX`) that tests import.
  **Spec scenarios**: expedite.overrides-key-always-present, expedite.override-records-reason, expedite.override-empty-reason-rejected, expedite.override-ignored-when-report-exists, expedite.override-explicit-missing-path, expedite.override-not-applied-to-unreadable-report
  **Design decisions**: D2
  **Dependencies**: 1.3
- [x] 2.2 Add the `overrides` field to `Verdict` (XS)
  **Dependencies**: 2.1
- [x] 2.3 Add the `--accept-missing-validation` CLI flag (S)
  - Reject a blank reason via `p.error(...)` (exit 2) before calling `expedite()`; thread the reason through `expedite(..., accept_missing_validation=...)`.
  **Dependencies**: 2.2
- [x] Checkpoint: run tests, review diff, verify scope

## 3. SKILL.md agrees with the code (wp-expedite)

- [x] 3.1 Write the failing drift test `skills/expedite/scripts/tests/test_skill_md_drift.py` (S)
  - Observe each check's reachable statuses by running it against fixtures; parse the SKILL.md `| Check fail | Resolution |` table; assert the four properties in design D4. It must fail against today's SKILL.md line 67.
  - Also walk the `expedite.py` AST and assert every `status="skip"` literal sits inside `check_rework_report`, so a `skip` added in a branch no fixture reaches still fails the test.
  **Spec scenarios**: expedite.skill-table-drift
  **Design decisions**: D4
  **Dependencies**: 1.3
- [x] 3.2 Correct the SKILL.md status table (XS)
  - Keep the `validation_report` (no file) row; add the override as its resolution alternative; rewrite line 67 so `skip` is documented only for `rework_report`.
  **Dependencies**: 3.1
- [x] 3.3 Document `--accept-missing-validation` in SKILL.md (XS)
  - Usage line, the `OVERRIDE —` detail, and `overrides` in the JSON shape block.
  **Dependencies**: 2.3
- [x] 3.4 Update `docs/mental-models.md` G2 (XS)
  - Test count, and "a missing validation report blocks; override is recorded".
  **Dependencies**: 3.2
- [x] 3.5 Re-sync runtime mirrors (XS)
  - `bash skills/install.sh --mode rsync --deps none --python-tools none`; commit only `.claude/skills/expedite/` and `.agents/skills/expedite/` changes.
  - Done: mirrors synced and verified identical; both mirror trees are gitignored (`.gitignore` `.claude/skills/`, `.agents/skills/`), so there is nothing to commit.
  **Dependencies**: 3.2, 3.3
- [x] Checkpoint: run tests, review diff, verify scope

## 4. Verification

- [x] 4.1 Run the expedite suite (XS)
  - `skills/.venv/bin/python -m pytest skills/expedite/scripts/tests -q`
  **Dependencies**: 3.5
- [x] 4.2 Run strict OpenSpec validation (XS)
  - `openspec validate make-expedite-fail-closed-on-missing-validation --strict`
  **Dependencies**: 4.1

## 5. Independent-review fixes (wp-expedite)

- [x] 5.1 An unreadable report fails the check and the verdict is still emitted (XS)
  - `test_fail_when_report_not_utf8`, `test_fail_when_report_path_is_directory`, `test_json_emitted_when_report_unreadable`.
  **Spec scenarios**: expedite.unreadable-report-blocks
- [x] 5.2 Probe the worktree report where `/validate-feature` writes it (XS)
  - `.git-worktrees/<id>/openspec/changes/<id>/validation-report.md` replaces `.git-worktrees/<id>/validation-report.md`, which nothing writes.
  **Spec scenarios**: expedite.worktree-report-found
- [x] 5.3 Table rows for every failing condition; drift test compares conditions (S)
  - Rows for `validation_report` (unreadable), `rework_report` (`revise-spec`), (load failure) and (unknown `summary_action`); `test_table_rows_equal_failing_conditions`.
  **Spec scenarios**: expedite.skill-table-drift
  **Design decisions**: D4
- [x] 5.4 A blank reason passed to the library is no override (XS)
  - `test_blank_reason_not_an_override_in_library`, `test_blank_reason_not_an_override_in_check`.
  **Spec scenarios**: expedite.override-blank-reason-library
  **Design decisions**: D2
