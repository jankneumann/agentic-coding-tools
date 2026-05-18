# Tasks

Sequential at the phase level; tests precede implementation within each task.

## Phase 1 — Skill scaffolding and scanners

- [ ] 1.1 Write tests for the skill-inventory scanner
  - **Spec scenarios**: `skill-workflow.skill-inventory-scan`
  - **Design decisions**: D2 (filesystem source of truth)
  - **Dependencies**: None
  - Add `skills/tests/update-documentation/test_skill_scanner.py` with fixtures: a valid `SKILL.md` parses correctly; missing frontmatter produces a warning; `user_invocable: true|false` is captured; `related:` is captured as a list.

- [ ] 1.2 Implement `skill_scanner.py`
  - **Spec scenarios**: `skill-workflow.skill-inventory-scan`
  - **Design decisions**: D2
  - **Dependencies**: 1.1
  - Create `skills/update-documentation/scripts/skill_scanner.py`. Use `PyYAML` (already in `skills/.venv/`). Return a list of `SkillRecord(name, description, user_invocable, triggers, related, group, path)`.

- [ ] 1.3 Write tests for the spec-inventory scanner
  - **Spec scenarios**: `skill-workflow.spec-inventory-scan`
  - **Design decisions**: D2
  - **Dependencies**: None
  - Add `test_spec_scanner.py`: counts `### Requirement:` headers per spec; captures spec title from first H1 or frontmatter.

- [ ] 1.4 Implement `spec_scanner.py`
  - **Spec scenarios**: `skill-workflow.spec-inventory-scan`
  - **Design decisions**: D2
  - **Dependencies**: 1.3

- [ ] 1.5 Write tests for the docs-inventory scanner
  - **Spec scenarios**: `skill-workflow.docs-inventory-scan`
  - **Design decisions**: D2
  - **Dependencies**: None
  - Add `test_docs_scanner.py`: lists `docs/*.md` with frontmatter `description:` or first paragraph; lists subdirectories with a `README.md` summary if present.

- [ ] 1.6 Implement `docs_scanner.py`
  - **Spec scenarios**: `skill-workflow.docs-inventory-scan`
  - **Design decisions**: D2
  - **Dependencies**: 1.5

## Phase 2 — Renderer and marker engine

- [ ] 2.1 Write tests for the marker-insertion engine
  - **Spec scenarios**: `skill-workflow.generated-block-roundtrip`, `skill-workflow.preserves-prose-verbatim`
  - **Design decisions**: D1 (markers), D4 (three-target)
  - **Dependencies**: None
  - Add `test_marker_engine.py`: round-trip test (insert, re-render with same input → byte-identical); unbalanced markers raise; hand-authored prose outside markers is preserved byte-for-byte; missing markers cause deterministic insertion at heading anchor (Q3).

- [ ] 2.2 Implement `marker_engine.py`
  - **Spec scenarios**: Same as 2.1
  - **Design decisions**: D1, D4, Q3 (deterministic insertion)
  - **Dependencies**: 2.1
  - Factor into `skills/shared/markers.py` so `coordinator-task-status-renderer` can adopt it later if useful.

- [ ] 2.3 Write tests for per-target renderers
  - **Spec scenarios**: `skill-workflow.readme-blocks-rendered`, `skill-workflow.claude-md-blocks-rendered`, `skill-workflow.catalogue-blocks-rendered`
  - **Design decisions**: D4
  - **Dependencies**: None
  - Add `test_renderers.py`: golden-file tests against a snapshot inventory; readme tree matches expected; specs table matches expected; CLAUDE.md docs index matches expected; catalogue quick-map counts and per-group tables match expected.

- [ ] 2.4 Implement `renderers.py` (readme, claude_md, catalogue)
  - **Spec scenarios**: Same as 2.3
  - **Design decisions**: D4
  - **Dependencies**: 2.3

## Phase 3 — CLI, cross-link check, report

- [ ] 3.1 Write tests for the cross-link checker
  - **Spec scenarios**: `skill-workflow.slash-mentions-resolve`, `skill-workflow.doc-links-resolve`
  - **Design decisions**: Q2 (scope of link check)
  - **Dependencies**: None
  - Add `test_link_checker.py`: a `/skill-name` mention that resolves passes; one that doesn't fails with a clear message; a `docs/foo.md` link is verified relative to repo root.

- [ ] 3.2 Implement `link_checker.py`
  - **Spec scenarios**: Same as 3.1
  - **Design decisions**: Q2
  - **Dependencies**: 3.1

- [ ] 3.3 Write tests for the CLI and exit codes
  - **Spec scenarios**: `skill-workflow.cli-write-mode`, `skill-workflow.cli-check-mode`, `skill-workflow.exit-code-semantics`
  - **Design decisions**: D3 (`--check`), D5 (exit codes)
  - **Dependencies**: None
  - Add `test_cli.py`: write mode applies changes and exits 0; check mode with drift exits 2; check mode without drift exits 0; filesystem error exits 1.

- [ ] 3.4 Implement `sync_docs.py` (CLI entry point)
  - **Spec scenarios**: Same as 3.3
  - **Design decisions**: D3, D5, D7
  - **Dependencies**: 3.3, all of Phase 2
  - Wire scanners → renderer → marker engine → link checker → report writer.

- [ ] 3.5 Write tests for the JSON report
  - **Spec scenarios**: `skill-workflow.json-report-schema`
  - **Design decisions**: D6 (report location)
  - **Dependencies**: None
  - Add `test_report.py`: report contains skill_count, spec_count, doc_count, drift_blocks (list), broken_links (list).

- [ ] 3.6 Implement `report_writer.py`
  - **Spec scenarios**: Same as 3.5
  - **Design decisions**: D6
  - **Dependencies**: 3.5

## Phase 4 — SKILL.md and integration

- [ ] 4.1 Author `skills/update-documentation/SKILL.md`
  - **Spec scenarios**: `skill-workflow.skill-frontmatter`
  - **Design decisions**: All
  - **Dependencies**: 3.4
  - Follow the canonical tail-block convention (Common Rationalizations / Red Flags / Verification). `user_invocable: true`. `related: [coordinator-task-status-renderer, refresh-architecture]`.

- [ ] 4.2 Update `.githooks/pre-commit`
  - **Spec scenarios**: `skill-workflow.pre-commit-blocks-drift`
  - **Design decisions**: D3, D5
  - **Dependencies**: 4.1
  - Add a short-circuit: if no staged file is under `skills/`, `openspec/specs/`, or `docs/`, exit 0. Otherwise call `skills/update-documentation/scripts/sync_docs.py --check`. Exit 2 = block commit with one-line fix message.

- [ ] 4.3 Update `.githooks/post-merge`
  - **Spec scenarios**: `skill-workflow.post-merge-syncs`
  - **Design decisions**: Q1 (auto-commit on post-merge)
  - **Dependencies**: 4.1
  - After merges that touched skill/spec/doc files, run sync_docs.py and auto-commit if a diff resulted.

- [ ] 4.4 Wire `/cleanup-feature` pre-merge gate
  - **Spec scenarios**: `skill-workflow.cleanup-blocks-drift`
  - **Design decisions**: D3
  - **Dependencies**: 4.1
  - Edit `skills/cleanup-feature/SKILL.md` to invoke `/update-documentation --check` before merging. Drift blocks the merge.

- [ ] 4.5 Expose `/validate-feature --phase docs`
  - **Spec scenarios**: `skill-workflow.validate-feature-docs-phase`
  - **Design decisions**: D3
  - **Dependencies**: 4.1
  - Edit `skills/validate-feature/SKILL.md` to document the new phase selector.

- [ ] 4.6 Run the skill against the live repo and commit the resulting sync
  - **Spec scenarios**: All (acceptance)
  - **Design decisions**: All
  - **Dependencies**: 4.1–4.5
  - Verify generated blocks land in README.md, CLAUDE.md, docs/skills-catalogue.md. Hand-authored prose preserved byte-for-byte. Idempotent re-run produces zero diff.

- [ ] 4.7 Update `docs/skills-catalogue.md:165` note
  - **Spec scenarios**: None (housekeeping)
  - **Design decisions**: None
  - **Dependencies**: 4.6
  - Replace the "future enhancement (deferred per design D4 of `add-engineering-methodology-skills`)" note with a pointer to `/update-documentation`.
