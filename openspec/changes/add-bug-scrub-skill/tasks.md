# Tasks: add-bug-scrub-skill

## Group 1: Data Models and Finding Schema

- [x] 1.1 Create `skills/bug-scrub/scripts/models.py` with unified finding schema
  **Files**: `skills/bug-scrub/scripts/models.py`
  **Requirements**: Unified Finding Schema
  **Details**: Define dataclasses for `Finding` (id, source, severity, category, file_path, line, title, detail, age_days, origin: Optional[FindingOrigin]), `FindingOrigin` (change_id, artifact_path, task_number: Optional[str], line_in_artifact: Optional[int] — enough metadata for fix-scrub to locate and update the source), `SourceResult` (source, status, findings, duration_ms), and `BugScrubReport` (timestamp, sources_used, severity_filter, findings, staleness_warnings, recommendations). Severity and category as Literal types. Include `to_dict()` methods for JSON serialization.

- [x] 1.2 Create `skills/bug-scrub/scripts/__init__.py`
  **Files**: `skills/bug-scrub/scripts/__init__.py`
  **Details**: Empty init file for package imports. (Removed — not needed, avoided package name collisions)

## Group 2: Signal Collectors (parallelizable — no file overlap)

- [x] 2.1 Create pytest signal collector
  **Files**: `skills/bug-scrub/scripts/collect_pytest.py`
  **Dependencies**: 1.1

- [x] 2.2 Create ruff signal collector
  **Files**: `skills/bug-scrub/scripts/collect_ruff.py`
  **Dependencies**: 1.1

- [x] 2.3 Create mypy signal collector
  **Files**: `skills/bug-scrub/scripts/collect_mypy.py`
  **Dependencies**: 1.1

- [x] 2.4 Create openspec validation collector
  **Files**: `skills/bug-scrub/scripts/collect_openspec.py`
  **Dependencies**: 1.1

- [x] 2.5 Create architecture diagnostics collector
  **Files**: `skills/bug-scrub/scripts/collect_architecture.py`
  **Dependencies**: 1.1

- [x] 2.6 Create security review report collector
  **Files**: `skills/bug-scrub/scripts/collect_security.py`
  **Dependencies**: 1.1

- [x] 2.7 Create deferred issue harvester
  **Files**: `skills/bug-scrub/scripts/collect_deferred.py`
  **Dependencies**: 1.1

- [x] 2.8 Create code marker scanner
  **Files**: `skills/bug-scrub/scripts/collect_markers.py`
  **Dependencies**: 1.1

## Group 3: Aggregation and Reporting

- [x] 3.1 Create finding aggregator
  **Files**: `skills/bug-scrub/scripts/aggregate.py`
  **Dependencies**: 1.1

- [x] 3.2 Create report renderer
  **Files**: `skills/bug-scrub/scripts/render_report.py`
  **Dependencies**: 3.1

## Group 4: Orchestrator

- [x] 4.1 Create main orchestrator
  **Files**: `skills/bug-scrub/scripts/main.py`
  **Dependencies**: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2

## Group 5: Skill Definition

- [x] 5.1 Create `skills/bug-scrub/SKILL.md`
  **Files**: `skills/bug-scrub/SKILL.md`
  **Dependencies**: 4.1

## Group 6: Tests (parallelizable — no file overlap with implementation)

- [x] 6.1 Create tests for models
  **Files**: `skills/bug-scrub/tests/test_models.py`

- [x] 6.2 Create tests for CI tool collectors
  **Files**: `skills/bug-scrub/tests/test_collect_ci.py`

- [x] 6.5 Create tests for report-based collectors
  **Files**: `skills/bug-scrub/tests/test_collect_reports.py`

- [x] 6.6 Create tests for deferred issue harvester
  **Files**: `skills/bug-scrub/tests/test_collect_deferred.py`

- [x] 6.7 Create tests for code marker scanner
  **Files**: `skills/bug-scrub/tests/test_collect_markers.py`

- [x] 6.3 Create tests for aggregator
  **Files**: `skills/bug-scrub/tests/test_aggregate.py`

- [x] 6.4 Create tests for report renderer
  **Files**: `skills/bug-scrub/tests/test_render_report.py`

## Group 7: Integration

- [x] 7.1 Update `docs/skills-workflow.md` with bug-scrub as supporting skill
  **Files**: `docs/skills-workflow.md`

- [x] 7.2 Add `.gitignore` for runtime outputs
  **Files**: `docs/bug-scrub/.gitignore`
  **Details**: Only ignoring ephemeral `agent-fix-prompts.json` — reports are committed for cross-agent access.

## Group 8: Fix Scrub — Classification and Planning

- [x] 8.1 Create `skills/fix-scrub/scripts/fix_models.py` with fix-specific models
  **Files**: `skills/fix-scrub/scripts/fix_models.py`
  **Details**: Renamed from models.py to fix_models.py to avoid module name collision. Uses importlib to load bug-scrub models under unique module name.

- [x] 8.2 Create `skills/fix-scrub/scripts/__init__.py`
  **Files**: `skills/fix-scrub/scripts/__init__.py`
  **Details**: Removed — not needed, avoided package name collisions.

- [x] 8.3 Create fixability classifier
  **Files**: `skills/fix-scrub/scripts/classify.py`
  **Dependencies**: 8.1

- [x] 8.4 Create fix planner
  **Files**: `skills/fix-scrub/scripts/plan_fixes.py`
  **Dependencies**: 8.3

## Group 9: Fix Scrub — Execution (parallelizable — auto vs agent have no file overlap)

- [x] 9.1 Create auto-fix executor
  **Files**: `skills/fix-scrub/scripts/execute_auto.py`
  **Dependencies**: 8.4

- [x] 9.2 Create agent-fix prompt generator
  **Files**: `skills/fix-scrub/scripts/generate_prompts.py`
  **Dependencies**: 8.4

## Group 10: Fix Scrub — OpenSpec Task Completion Tracking

- [x] 10.1 Create task completion tracker
  **Files**: `skills/fix-scrub/scripts/track_completions.py`
  **Dependencies**: 8.1

## Group 11: Fix Scrub — Verification and Reporting

- [x] 11.1 Create quality verifier
  **Files**: `skills/fix-scrub/scripts/verify.py`
  **Dependencies**: 9.1, 9.2, 10.1

- [x] 11.2 Create fix-scrub report renderer
  **Files**: `skills/fix-scrub/scripts/render_fix_report.py`
  **Dependencies**: 11.1

## Group 12: Fix Scrub — Orchestrator and Skill Definition

- [x] 12.1 Create fix-scrub main orchestrator
  **Files**: `skills/fix-scrub/scripts/main.py`
  **Dependencies**: 8.3, 8.4, 9.1, 10.1, 11.1, 11.2

- [x] 12.2 Create `skills/fix-scrub/SKILL.md`
  **Files**: `skills/fix-scrub/SKILL.md`
  **Dependencies**: 12.1

## Group 13: Fix Scrub — Tests (parallelizable)

- [x] 13.1 Create tests for classifier
  **Files**: `skills/fix-scrub/tests/test_classify.py`

- [x] 13.2 Create tests for fix planner
  **Files**: `skills/fix-scrub/tests/test_plan_fixes.py`

- [x] 13.3 Create tests for auto-fix executor
  **Files**: `skills/fix-scrub/tests/test_execute_auto.py`

- [x] 13.4 Create tests for prompt generator
  **Files**: `skills/fix-scrub/tests/test_generate_prompts.py`

- [x] 13.5 Create tests for task completion tracker
  **Files**: `skills/fix-scrub/tests/test_track_completions.py`

- [x] 13.6 Create tests for quality verifier
  **Files**: `skills/fix-scrub/tests/test_verify.py`

## Group 14: Fix Scrub — Integration

- [x] 14.1 Update `docs/skills-workflow.md` with fix-scrub as supporting skill
  **Files**: `docs/skills-workflow.md`
