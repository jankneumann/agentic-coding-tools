# Tasks: amend-skill-workflow-spec-for-policy-authorized-sync-windows

All tasks run in one package (`wp-main`) in order. 2.1 and 2.3 share the test
file `skills/shared/tests/test_trust_posture_sync_windows.py`, and 2.2/2.3/3.1
all depend on the `SyncWindow` shape fixed in 2.2, so parallel execution would
only produce merge conflicts on a ~350 LOC change.

## 1. Spec amendment

- [x] 1.1 Confirm the spec deltas already authored in this change — the
  `skill-workflow` MODIFIED requirements "Main Receives Work Through PR Sync
  Points" and "Merge Conductor Invokes Iterate Skills", and the `trust-posture`
  ADDED requirement "Sync Window Declarations" — still carry every scenario of
  the base requirements in `openspec/specs/skill-workflow/spec.md`, and that
  `openspec validate amend-skill-workflow-spec-for-policy-authorized-sync-windows --strict`
  passes (XS)
  **Spec scenarios**: skill-workflow "Scheduled invocation names a window and
  passes authorization first", "No sync window declared keeps the
  user-invoked default", "Scheduled invocation keeps the guards unchanged",
  "Scheduled invocation keeps validation gates unchanged", "Scheduled
  invocation is bounded by the window's sources and ceiling", "Sync window does
  not override gate dispositions", "Scheduled merge conductor keeps iterate on
  the feature branch". These are acceptance contracts for `ri-12`/`ri-13`
  callers (design D6, verification boundary); this change verifies only the
  authorization surface they call (2.1).
  **Dependencies**: None

## 2. Posture contract: sync windows

- [x] 2.0 Add an exported `PR_ORIGINS` frozenset to
  `skills/shared/github_classifier.py` (add to `__all__`; no behaviour change)
  and a test in `skills/tests/merge-pull-requests/test_classify.py` that every
  origin `classify_pr` returns for the existing fixtures is in `PR_ORIGINS` and
  that `to_pr_card_origin` accepts every member (XS)
  **Design decisions**: D3
  **Dependencies**: None
- [x] 2.1 Write failing tests in `skills/shared/tests/test_trust_posture_sync_windows.py`:
  - absent, `null` and `[]` windows declare nothing, and authorization fails
    for every id and skill (including with no contract file)
  - a valid window round-trips through `load_posture`
  - each malformed shape is rejected with the window (or entry index) named:
    non-list `sync_windows`, non-mapping entry, unknown field, missing field,
    empty list field, repeated list value, non-kebab `id`, unknown
    skill/source/ceiling, bad cadence (four fields, six fields, `@daily`,
    `MON`), duplicate id
  - ceiling ordering, including that no ceiling permits an unknown kind
  - vocabulary parity: `SYNC_SOURCES == github_classifier.PR_ORIGINS`, ranked
    kinds `== set(classify_kind.KIND_TO_SKILL)`
  - `authorize_sync_window` success, unknown-window and unlisted-skill
    refusals (message names the missing declaration), unknown skill raises
    `ValueError` (not `SyncWindowNotAuthorized`), and refusal for both the
    absent-posture value and `None`
  - digest byte-identical to the gates-only digest without windows (pinned
    against a literal for the live `TRUST_POSTURE.md`), changed by a window
    edit, unchanged by window or list-value reordering
  - `show` prints a `sync_windows:` section after the gate lines
  - the live `TRUST_POSTURE.md` and `TRUST_POSTURE.template.md` validate and
    declare no window
  (M)
  **Spec scenarios**: trust-posture "Absent sync windows declare nothing",
  "Declared window loads and authorizes its skills", "Malformed window is
  rejected", "Malformed sync_windows container is rejected", "Auto-merge
  ceiling orders PR kinds", "Digest is unchanged without windows and changes
  with them"; skill-workflow "Scheduled invocation names an undeclared window
  or skill"
  **Design decisions**: D2, D3, D4, D5, D6, D7, D8
  **Dependencies**: 1.1, 2.0
- [x] 2.2 Implement `SyncWindow`, `MergeCeiling`, `SyncWindowNotAuthorized`,
  `SYNC_SKILLS`/`SYNC_SOURCES` frozensets, `sync_windows` parsing/validation,
  `TrustPosture.sync_windows` (defaulting to an empty tuple so existing
  constructors are unaffected), `authorize_sync_window`, the digest extension
  (windows sorted by id), and `show` output in `skills/shared/trust_posture.py` (S)
  **Design decisions**: D2, D3, D4, D5, D6, D8
  **Dependencies**: 2.1
- [ ] Checkpoint: run `skills/.venv/bin/python -m pytest skills/shared/tests skills/tests/merge-pull-requests -q`,
  then `skills/.venv/bin/python -m pytest skills/tests/supervise skills/tests/autopilot skills/autopilot/tests -q`
  (digest consumers), review diff, verify scope
- [ ] 2.3 Mirror `sync_windows` in `openspec/schemas/trust-posture.schema.json`
  (`SyncWindow` `$def`, closed enums, `uniqueItems`, id and cadence patterns)
  and add schema tests to `test_trust_posture_sync_windows.py`: the template and
  a sample window validate, `sync_windows` absent, `null` and `[]` all validate,
  a malformed window fails (including wrong field types and wrong list-member
  types), and the schema enums equal the Python frozensets (S)
  **Design decisions**: D1, D3, D4
  **Dependencies**: 2.2

## 3. Documentation

- [ ] 3.1 Document the `sync_windows` block in `TRUST_POSTURE.template.md`: a
  commented-out example, a field table, the fail-closed rule, the
  guards-unchanged rule, the necessary-not-sufficient rule (D8), and the
  advice to declare windows while no supervised run is in flight (digest
  re-evaluation). Do not change the effective front matter of
  `TRUST_POSTURE.md` (XS)
  **Design decisions**: D5, D7, D8
  **Dependencies**: 2.2
- [ ] Checkpoint: run tests, `openspec validate --strict`, confirm
  `git diff origin/main -- TRUST_POSTURE.md` is empty, review diff, verify scope
