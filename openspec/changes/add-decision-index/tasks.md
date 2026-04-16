# Tasks: add-decision-index

Work package: `wp-main` (sequential tier — single package encompassing the full feature scope).

TDD ordering: within each phase, test tasks come first; implementation tasks declare explicit dependencies on their tests. Test tasks reference the spec scenarios they encode.

---

## Phase 1 — Tag schema + parser (skill-workflow spec)

- [ ] 1.1 Write unit tests for `TaggedDecision` extraction from Phase Entry markdown
  **Spec scenarios**: `skill-workflow.1` (single tagged decision), `skill-workflow.2` (multiple decisions, different capabilities), `skill-workflow.3` (untagged decision remains valid)
  **Design decisions**: extraction regex (design.md §Data model)
  **Fixtures**: synthesize session-log fragments covering tagged, untagged, and malformed cases
  **Dependencies**: None

- [ ] 1.2 Implement `skills/explore-feature/scripts/decision_index.py` with `TaggedDecision` dataclass + `extract_decisions(session_log_path: Path) -> list[TaggedDecision]`
  **Dependencies**: 1.1

- [ ] 1.3 Write unit test asserting `sanitize_session_log.py` leaves tagged decisions unredacted
  **Spec scenarios**: `skill-workflow.5` (sanitizer preserves tags)
  **Fixtures**: session-log with mix of tagged Decisions and genuine secrets; assert tag strings survive, secrets redacted
  **Dependencies**: None

- [ ] 1.4 Update `skills/session-log/SKILL.md` Phase Entry template section to document the `` `architectural: <capability>` `` syntax and provide one tagged + one untagged example
  **Dependencies**: 1.1 (syntax stabilized by tests first)

---

## Phase 2 — Per-capability emitter (software-factory-tooling spec)

- [ ] 2.1 Write unit test: decisions across 3 changes tagged `skill-workflow` produce exactly 3 reverse-chronological entries in `skill-workflow.md`
  **Spec scenarios**: `software-factory-tooling.1` (aggregation by capability)
  **Dependencies**: 1.2

- [ ] 2.2 Write unit test: supersession resolution marks earlier Decision `superseded` and emits bidirectional cross-references
  **Spec scenarios**: `software-factory-tooling.2` (supersession chain preserved)
  **Design decisions**: explicit supersession syntax `` `supersedes: <change-id>#D<n>` `` (design.md §Supersession mechanism)
  **Dependencies**: 1.2

- [ ] 2.3 Write unit test: untagged Decisions are excluded from all `docs/decisions/*.md` output
  **Spec scenarios**: `software-factory-tooling.3` (untagged excluded)
  **Dependencies**: 1.2

- [ ] 2.4 Write unit test: Decision tagged with unknown capability triggers warning; `--strict` mode exits non-zero; non-strict mode skips and continues
  **Spec scenarios**: `software-factory-tooling.6` (malformed tag reported), `skill-workflow.4` (invalid capability reported)
  **Dependencies**: 1.2

- [ ] 2.5 Write unit test: running emitter twice produces byte-identical output (deterministic / idempotent)
  **Spec scenarios**: `software-factory-tooling.5` (incremental regeneration on re-run)
  **Dependencies**: 1.2

- [ ] 2.6 Write unit test: Decision tagged with capability whose `docs/decisions/<cap>.md` does not yet exist creates the file
  **Spec scenarios**: `software-factory-tooling.4` (new capability directory auto-created)
  **Dependencies**: 1.2

- [ ] 2.7 Implement emitter: `emit_decision_index(decisions: list[TaggedDecision], output_dir: Path, *, strict: bool) -> None` in `decision_index.py`
  **Dependencies**: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6

- [ ] 2.8 Implement generated README: `emit_readme(output_dir: Path, capabilities: list[str]) -> None` — writes `docs/decisions/README.md` explaining purpose, generation, how to read
  **Dependencies**: 2.7

- [ ] 2.9 Wire the emitter into `archive_index.py` as a new pass invoked after the existing archive-index walk; respect the existing incremental-indexing checkpoint
  **Dependencies**: 2.7, 2.8

---

## Phase 3 — Systematic backfill of archived session-logs

- [ ] 3.1 Write unit test for heuristic classifier: given keyword-to-capability mapping, correctly routes sample Decisions and reports confidence scores
  **Dependencies**: 1.2

- [ ] 3.2 Implement `skills/explore-feature/scripts/backfill_decision_tags.py` — proposes `architectural:` tags for all untagged Decisions in archived session-logs, emits JSON report of proposals + confidence scores (no file edits yet)
  **Dependencies**: 3.1

- [ ] 3.3 Run classifier over `openspec/changes/archive/**/session-log.md`; capture proposals JSON under `openspec/changes/add-decision-index/backfill-proposals.json` for review
  **Dependencies**: 3.2

- [ ] 3.4 Agent review of low-confidence and multi-candidate proposals; apply accepted tags in-place to archived session-logs (markdown edits only)
  **Dependencies**: 3.3

- [ ] 3.5 Write end-to-end test: run emitter against the backfilled archive and assert all 16 capability files are generated, reverse-chronologically ordered, with at least one entry per actively-developed capability
  **Dependencies**: 3.4, 2.9

---

## Phase 4 — Make target + CI staleness check

- [ ] 4.1 Add `decisions` target to `Makefile` following the `architecture` target precedent (Makefile:120-127)
  **Dependencies**: 2.9

- [ ] 4.2 Add staleness-check step to `.github/workflows/ci.yml`: run `make decisions`, then `git diff --exit-code docs/decisions/`, failing with actionable message if stale
  **Dependencies**: 4.1

- [ ] 4.3 Commit the initial generated `docs/decisions/*.md` set produced from the backfilled archive
  **Dependencies**: 3.5, 4.1

---

## Phase 5 — Validation

- [ ] 5.1 Run `openspec validate add-decision-index --strict` and confirm zero errors
  **Dependencies**: all prior phases

- [ ] 5.2 Run full skills test suite: `skills/.venv/bin/python -m pytest skills/tests/ skills/explore-feature/tests/`
  **Dependencies**: all prior phases

- [ ] 5.3 Run `make decisions` twice in succession; confirm second run produces no `git diff` (idempotent)
  **Dependencies**: 4.3

- [ ] 5.4 Sanitizer soak: run `sanitize_session_log.py` on a backfilled archived session-log and confirm tagged Decisions survive unredacted
  **Spec scenarios**: `skill-workflow.5`
  **Dependencies**: 3.4
