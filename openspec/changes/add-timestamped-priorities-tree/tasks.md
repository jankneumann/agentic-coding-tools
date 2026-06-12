# Tasks — add-timestamped-priorities-tree

## Phase 1 — Skill implementation

- [x] 1.1 Write tests for `priorities_paths.py`: run-id construction, dated-dir path, latest-path
  **Spec scenarios**: skill-workflow "Run-id construction", "Run-id stability under reruns"
  **Design decisions**: D2 (run-id format)
  **Dependencies**: None
  **Size**: S

- [x] 1.2a Implement `build_run_id()` in `skills/prioritize-proposals/scripts/priorities_paths.py` — pure helper returning `<YYYY-MM-DD>-HHMMSS-<short-git-sha>` from UTC now + git HEAD
  **Spec scenarios**: skill-workflow "Run-id construction"
  **Design decisions**: D2 (run-id format)
  **Dependencies**: 1.1
  **Size**: S

- [x] 1.2b Implement `build_paths()` in `skills/prioritize-proposals/scripts/priorities_paths.py` — pure helper returning `(dated_dir, latest_md_path, latest_json_path)` from a run-id
  **Spec scenarios**: skill-workflow "Per-run dated artifact written", "Latest pointer rewritten on each run"
  **Design decisions**: D1 (directory layout), D3 (flat-file latest)
  **Dependencies**: 1.2a
  **Size**: S

- [x] 1.3 Write tests for `artifact_header.py`: header field population, ISO-8601 timestamp format, git_sha length
  **Spec scenarios**: skill-workflow "Header fields populated"
  **Design decisions**: D4 (artifact header schema)
  **Dependencies**: None
  **Size**: S

- [x] 1.4 Implement `skills/prioritize-proposals/scripts/artifact_header.py` — inline header constructor (~10 LOC); leave docstring noting future migration to `skills/shared/artifact_header.py`
  **Spec scenarios**: skill-workflow "Header fields populated", "Header migration to shared helper"
  **Design decisions**: D4
  **Dependencies**: 1.3
  **Size**: S

- [x] 1.5 Checkpoint: run tests, review diff, verify scope (`skills/prioritize-proposals/` only)
  **Dependencies**: 1.2a, 1.2b, 1.4

- [x] 1.6 Write tests for `retention.py`: 30-default keeps 30, custom `--retain 5` keeps 5, archive accumulates, archive never deletes, archive subdir excluded from count
  **Spec scenarios**: skill-workflow "Default retention preserves 30 most recent", "Custom retention", "Archive accumulates, never deletes"
  **Design decisions**: D5 (retention policy)
  **Dependencies**: 1.2b
  **Size**: M

- [x] 1.7 Implement `skills/prioritize-proposals/scripts/retention.py` — enumerate dated dirs, sort by name (lexically chronological), move oldest beyond Nth to `archive/`
  **Spec scenarios**: skill-workflow "Default retention preserves 30 most recent", "Custom retention"
  **Design decisions**: D5
  **Dependencies**: 1.6
  **Size**: S

- [x] 1.8 Update `skills/prioritize-proposals/SKILL.md`: replace `REPORT_FILE="openspec/changes/prioritized-proposals.md"` with the new write flow (dated dir + latest files + retention scan). Add `--retain N` argument documentation.
  **Spec scenarios**: skill-workflow "Per-run dated artifact written", "Latest pointer rewritten on each run", "Legacy write path is rejected"
  **Design decisions**: D1, D3 (flat-file latest), D5
  **Dependencies**: 1.2a, 1.2b, 1.4, 1.7
  **Size**: M

- [x] 1.9 Checkpoint: run all Phase 1 tests, review diff, verify only `skills/prioritize-proposals/` was touched
  **Dependencies**: 1.7, 1.8

## Phase 2 — Migration and spec sync

- [x] 2.1 Write test for `migrate_legacy.py`: idempotent move of `openspec/changes/prioritized-proposals.md` to `openspec/priorities/2026-05-04-legacy/report.md`; no-op if already migrated
  **Spec scenarios**: skill-workflow "Legacy entry is readable"
  **Design decisions**: D6 (legacy migration)
  **Dependencies**: None
  **Size**: S

- [x] 2.2 Implement `skills/prioritize-proposals/scripts/migrate_legacy.py` — one-shot migration script
  **Spec scenarios**: skill-workflow "Legacy entry is readable"
  **Design decisions**: D6
  **Dependencies**: 2.1
  **Size**: S

- [ ] 2.3 Run `migrate_legacy.py` from the worktree (creates `openspec/priorities/2026-05-04-legacy/report.md`, deletes `openspec/changes/prioritized-proposals.md`). Commit the migration as a discrete commit.
  **Spec scenarios**: skill-workflow "Legacy entry is readable"
  **Design decisions**: D6
  **Dependencies**: 2.2
  **Size**: S

- [ ] 2.4 Update `openspec/specs/skill-workflow/spec.md`: this is the live spec, and the delta in this change folder will be applied to it during archive — verify the delta matches what we actually shipped after Phase 1 completes.
  **Spec scenarios**: all in `specs/skill-workflow/spec.md`
  **Dependencies**: 1.8

- [ ] 2.5 Checkpoint: run all tests, verify spec validation passes (`openspec validate add-timestamped-priorities-tree --strict`), verify the migration target file exists and the source is gone
  **Dependencies**: 2.3, 2.4

## Phase 3 — End-to-end verification

- [ ] 3.1 End-to-end smoke: run `/prioritize-proposals` (md only) in the worktree; verify `openspec/priorities/<today>-HHMMSS-<sha>/report.md` exists; verify `openspec/priorities/latest.md` exists and matches; verify NO write to `openspec/changes/prioritized-proposals.md`
  **Spec scenarios**: skill-workflow "Per-run dated artifact written", "Latest pointer rewritten on each run", "Legacy write path is rejected"
  **Dependencies**: 2.5
  **Size**: S

- [ ] 3.2 End-to-end smoke: run `/prioritize-proposals --format json`; verify `report.json` exists with the mandatory `_header` block carrying all six required fields; verify `latest.json` exists and is byte-identical to the dated `report.json`
  **Spec scenarios**: skill-workflow "Header fields populated"
  **Dependencies**: 3.1
  **Size**: S

- [ ] 3.3 End-to-end smoke: artificially create 31 dated directories via test fixture; run `/prioritize-proposals`; verify exactly 30 remain and one was moved to `archive/`
  **Spec scenarios**: skill-workflow "Default retention preserves 30 most recent"
  **Dependencies**: 3.2
  **Size**: S

- [ ] 3.4 Sync skill mirrors: run `bash skills/install.sh --mode rsync --deps none --python-tools none` to regenerate `.claude/skills/prioritize-proposals/` and `.agents/skills/prioritize-proposals/` from the canonical source
  **Dependencies**: 3.3
  **Size**: XS

- [ ] 3.5 Final checkpoint: full test suite (`skills/.venv/bin/python -m pytest skills/tests/prioritize-proposals/` if that path is used, otherwise the agent-coordinator venv), `openspec validate add-timestamped-priorities-tree --strict`, review final diff
  **Dependencies**: 3.4
