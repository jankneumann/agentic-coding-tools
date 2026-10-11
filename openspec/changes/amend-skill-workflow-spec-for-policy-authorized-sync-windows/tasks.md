# Tasks: amend-skill-workflow-spec-for-policy-authorized-sync-windows

## 1. Spec amendment

- [ ] 1.1 Author the `skill-workflow` MODIFIED delta for "Main Receives Work Through PR Sync Points" and the `trust-posture` ADDED delta "Sync Window Declarations"; confirm `openspec validate amend-skill-workflow-spec-for-policy-authorized-sync-windows --strict` passes (S)
  **Spec scenarios**: skill-workflow "No sync window declared keeps the user-invoked default", "Scheduled invocation keeps the guards unchanged", "Scheduled invocation keeps validation gates unchanged", "Scheduled invocation is bounded by the window's sources and ceiling"
  **Dependencies**: None

## 2. Posture contract: sync windows

- [ ] 2.1 Write failing tests in `skills/shared/tests/test_trust_posture_sync_windows.py`: absent/empty windows declare nothing; a valid window round-trips; each malformed shape (unknown field, missing field, unknown skill/source/ceiling, bad cadence, duplicate id, non-list) is rejected with the window named; ceiling ordering; vocabulary parity with `discover_prs.py` / `classify_kind.py`; `authorize_sync_window` success, unknown-window and unlisted-skill refusals; digest unchanged without windows and changed by a window edit; the live `TRUST_POSTURE.md` and the template still validate and declare no window (M)
  **Spec scenarios**: trust-posture "Absent sync windows declare nothing", "Declared window loads and authorizes its skills", "Malformed window is rejected", "Auto-merge ceiling orders PR kinds", "Digest is unchanged without windows and changes with them"; skill-workflow "Scheduled invocation names an undeclared window or skill"
  **Design decisions**: D2, D3, D4, D5, D6, D7
  **Dependencies**: 1.1
- [ ] 2.2 Implement `SyncWindow`, `MergeCeiling`, `SyncWindowNotAuthorized`, `sync_windows` parsing/validation, `TrustPosture.sync_windows`, `authorize_sync_window`, digest extension, and `show` output in `skills/shared/trust_posture.py` (S)
  **Dependencies**: 2.1
- [ ] Checkpoint: run `skills/.venv/bin/python -m pytest skills/shared/tests -q`, review diff, verify scope
- [ ] 2.3 Mirror `sync_windows` in `openspec/schemas/trust-posture.schema.json` (`SyncWindow` `$def`, closed enums, cadence pattern) and add a schema test that the template and a sample window validate against it (S)
  **Design decisions**: D1, D3, D4
  **Dependencies**: 2.2

## 3. Documentation

- [ ] 3.1 Document the `sync_windows` block (commented-out example, field table, fail-closed and guard-unchanged rules) in `TRUST_POSTURE.template.md` without changing the effective front matter of `TRUST_POSTURE.md` (XS)
  **Design decisions**: D7
  **Dependencies**: 2.2
- [ ] Checkpoint: run tests, `openspec validate --strict`, review diff, verify scope
