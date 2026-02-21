# Tasks: add-bug-scrub-skill

## Group 1: Data Models and Finding Schema

- [ ] 1.1 Create `skills/bug-scrub/scripts/models.py` with unified finding schema
  **Files**: `skills/bug-scrub/scripts/models.py`
  **Requirements**: Unified Finding Schema
  **Details**: Define dataclasses for `Finding` (id, source, severity, category, file_path, line, title, detail, age_days, origin: Optional[FindingOrigin]), `FindingOrigin` (change_id, artifact_path, task_number: Optional[str], line_in_artifact: Optional[int] — enough metadata for fix-scrub to locate and update the source), `SourceResult` (source, status, findings, duration_ms), and `BugScrubReport` (timestamp, sources_used, severity_filter, findings, staleness_warnings, recommendations). Severity and category as Literal types. Include `to_dict()` methods for JSON serialization.

- [ ] 1.2 Create `skills/bug-scrub/scripts/__init__.py`
  **Files**: `skills/bug-scrub/scripts/__init__.py`
  **Details**: Empty init file for package imports.

## Group 2: Signal Collectors (parallelizable — no file overlap)

- [ ] 2.1 Create pytest signal collector
  **Files**: `skills/bug-scrub/scripts/collect_pytest.py`
  **Dependencies**: 1.1
  **Requirements**: Signal Collection from CI Tools (pytest scenario)
  **Details**: Run `pytest -m "not e2e and not integration" --tb=line -q` in the project directory (from `--project-dir` or auto-detected via pyproject.toml), parse failures into Finding objects with severity "high", source "pytest". Handle tool-not-available gracefully.

- [ ] 2.2 Create ruff signal collector
  **Files**: `skills/bug-scrub/scripts/collect_ruff.py`
  **Dependencies**: 1.1
  **Requirements**: Signal Collection from CI Tools (ruff scenario)
  **Details**: Run `ruff check --output-format=json`, parse JSON output into Finding objects. Map ruff severity (error → high, warning → medium). Handle tool-not-available.

- [ ] 2.3 Create mypy signal collector
  **Files**: `skills/bug-scrub/scripts/collect_mypy.py`
  **Dependencies**: 1.1
  **Requirements**: Signal Collection from CI Tools (mypy scenario)
  **Details**: Run `mypy src/ --no-error-summary` in the project directory (from `--project-dir` or auto-detected), parse output lines into Finding objects with severity "medium", source "mypy". Handle tool-not-available.

- [ ] 2.4 Create openspec validation collector
  **Files**: `skills/bug-scrub/scripts/collect_openspec.py`
  **Dependencies**: 1.1
  **Requirements**: Signal Collection from CI Tools (openspec scenario)
  **Details**: Run `openspec validate --strict --all`, parse output for errors/warnings into Finding objects with severity "medium", source "openspec". Handle tool-not-available.

- [ ] 2.5 Create architecture diagnostics collector
  **Files**: `skills/bug-scrub/scripts/collect_architecture.py`
  **Dependencies**: 1.1
  **Requirements**: Signal Collection from Existing Reports (architecture scenario)
  **Details**: Parse `docs/architecture-analysis/architecture.diagnostics.json`. Map error → high, warning → medium, info → low. Check file modification time for staleness (>7 days). Handle missing file.

- [ ] 2.6 Create security review report collector
  **Files**: `skills/bug-scrub/scripts/collect_security.py`
  **Dependencies**: 1.1
  **Requirements**: Signal Collection from Existing Reports (security scenario)
  **Details**: Parse `docs/security-review/security-review-report.json`. Preserve original severity mapping. Check file modification time for staleness. Handle missing file.

- [ ] 2.7 Create deferred issue harvester
  **Files**: `skills/bug-scrub/scripts/collect_deferred.py`
  **Dependencies**: 1.1
  **Requirements**: Deferred Issue Harvesting from OpenSpec Changes
  **Details**: Scan three artifact types across both active (`openspec/changes/*/`) and archived (`openspec/changes/archive/*/`) changes: (a) `impl-findings.md` for "out of scope"/"deferred" findings, (b) `deferred-tasks.md` for migrated task tables, (c) `tasks.md` for unchecked items (`- [ ]`). Parse markdown checkbox lines and tables. For each finding, record change-id, task number/description, file scope, and dependencies. Active → severity "medium", archived → severity "low". Include the source path (e.g., `deferred:open-tasks`, `deferred:impl-findings`, `deferred:tasks`) and enough metadata for fix-scrub to locate and update the source file when a fix is applied.

- [ ] 2.8 Create code marker scanner
  **Files**: `skills/bug-scrub/scripts/collect_markers.py`
  **Dependencies**: 1.1
  **Requirements**: Code Marker Scanning
  **Details**: Scan `**/*.py` for TODO/FIXME/HACK/XXX markers. FIXME and HACK → medium, TODO and XXX → low. Use `git log -1 --format=%ai` on each file:line for age estimation. Skip `.venv`, `node_modules`, `__pycache__`.

## Group 3: Aggregation and Reporting

- [ ] 3.1 Create finding aggregator
  **Files**: `skills/bug-scrub/scripts/aggregate.py`
  **Dependencies**: 1.1
  **Requirements**: Unified Finding Schema (cross-source deduplication scenario)
  **Details**: Accept list of `SourceResult` objects, merge all findings, sort by severity then age. Group related findings by file_path proximity. Produce `BugScrubReport` with summary counts by severity and source. Generate top 3-5 recommendations based on finding patterns (e.g., "Run /security-review to refresh stale security data").

- [ ] 3.2 Create report renderer
  **Files**: `skills/bug-scrub/scripts/render_report.py`
  **Dependencies**: 3.1
  **Requirements**: Bug Scrub Report Format
  **Details**: Accept `BugScrubReport`, produce both markdown (`bug-scrub-report.md`) and JSON (`bug-scrub-report.json`) outputs. Markdown: header, summary table, critical/high with full detail, medium condensed, low/info counts only. JSON: full finding list. Write to `--out-dir` (default `docs/bug-scrub/`).

## Group 4: Orchestrator

- [ ] 4.1 Create main orchestrator
  **Files**: `skills/bug-scrub/scripts/main.py`
  **Dependencies**: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2
  **Requirements**: Parallel Signal Collection, Bug Scrub Diagnostic Skill
  **Details**: Parse CLI arguments (`--source`, `--severity`, `--project-dir`, `--out-dir`, `--format`). Auto-detect project directory from pyproject.toml location if `--project-dir` not specified. Import and invoke each collector, passing project directory to CI tool collectors. Aggregate results. Render report. Return exit code 0 for clean, 1 for findings at/above severity threshold. Handle `--source` filtering to skip unneeded collectors.

## Group 5: Skill Definition

- [ ] 5.1 Create `skills/bug-scrub/SKILL.md`
  **Files**: `skills/bug-scrub/SKILL.md`
  **Dependencies**: 4.1
  **Requirements**: Bug Scrub Diagnostic Skill
  **Details**: Frontmatter (name, description, category, tags, triggers). Document arguments, prerequisites, steps (signal collection via main.py, interpretation guide). Reference parallel Task() pattern for the SKILL.md orchestration layer.

## Group 6: Tests (parallelizable — no file overlap with implementation)

- [ ] 6.1 Create tests for models
  **Files**: `skills/bug-scrub/tests/test_models.py`
  **Dependencies**: 1.1
  **Details**: Test Finding creation, serialization, severity ordering. Test BugScrubReport summary generation.

- [ ] 6.2 Create tests for CI tool collectors
  **Files**: `skills/bug-scrub/tests/test_collect_ci.py`
  **Dependencies**: 2.1, 2.2, 2.3, 2.4
  **Details**: Test pytest, ruff, mypy, and openspec collector output parsing with sample inputs. Test tool-not-available handling for each. Test ruff JSON parsing and severity mapping.

- [ ] 6.5 Create tests for report-based collectors
  **Files**: `skills/bug-scrub/tests/test_collect_reports.py`
  **Dependencies**: 2.5, 2.6
  **Details**: Test architecture diagnostics JSON parsing with sample data. Test security report parsing. Test staleness detection (mocked file modification times). Test missing file handling.

- [ ] 6.6 Create tests for deferred issue harvester
  **Files**: `skills/bug-scrub/tests/test_collect_deferred.py`
  **Dependencies**: 2.7
  **Details**: Test impl-findings.md parsing for "out of scope"/"deferred" markers. Test deferred-tasks.md table parsing. Test tasks.md checkbox parsing. Test archived vs active severity mapping. Test malformed artifact handling. Test FindingOrigin metadata population.

- [ ] 6.7 Create tests for code marker scanner
  **Files**: `skills/bug-scrub/tests/test_collect_markers.py`
  **Dependencies**: 2.8
  **Details**: Test TODO/FIXME/HACK/XXX detection. Test severity classification. Test directory exclusion (.venv, node_modules, __pycache__). Test age estimation with mocked git output.

- [ ] 6.3 Create tests for aggregator
  **Files**: `skills/bug-scrub/tests/test_aggregate.py`
  **Dependencies**: 3.1
  **Details**: Test severity sorting, deduplication by proximity, summary count generation, recommendation logic.

- [ ] 6.4 Create tests for report renderer
  **Files**: `skills/bug-scrub/tests/test_render_report.py`
  **Dependencies**: 3.2
  **Details**: Test markdown output format, JSON serialization, severity filtering in output, empty report case.

## Group 7: Integration

- [ ] 7.1 Update `docs/skills-workflow.md` with bug-scrub as supporting skill
  **Files**: `docs/skills-workflow.md`
  **Dependencies**: 5.1
  **Requirements**: Bug Scrub Diagnostic Skill (workflow position)
  **Details**: Add entry under "Supporting Skills" section describing `/bug-scrub` purpose, method, produces, and gate (none — diagnostic step).

- [ ] 7.2 Add `.gitignore` for runtime outputs
  **Files**: `docs/bug-scrub/.gitignore`
  **Dependencies**: 3.2
  **Details**: Ignore `bug-scrub-report.json`, `bug-scrub-report.md`, and `fix-scrub-report.md` runtime outputs (like `docs/security-review/.gitignore`).

## Group 8: Fix Scrub — Classification and Planning

- [ ] 8.1 Create `skills/fix-scrub/scripts/models.py` with fix-specific models
  **Files**: `skills/fix-scrub/scripts/models.py`
  **Dependencies**: 1.1
  **Requirements**: Finding Fixability Classification
  **Details**: Define `FixTier` Literal ("auto", "agent", "manual"), `ClassifiedFinding` (finding + tier + fix_strategy), `FixGroup` (file_path, classified_findings), `FixPlan` (auto_groups, agent_groups, manual_findings, summary). Import Finding and FindingOrigin from bug-scrub models via `sys.path` insertion of `skills/bug-scrub/scripts/` (resolved relative to the repository root using `git rev-parse --show-toplevel`). Include `to_dict()` for JSON serialization. Document the cross-skill import convention in a module docstring.

- [ ] 8.2 Create `skills/fix-scrub/scripts/__init__.py`
  **Files**: `skills/fix-scrub/scripts/__init__.py`
  **Details**: Empty init file for package imports.

- [ ] 8.3 Create fixability classifier
  **Files**: `skills/fix-scrub/scripts/classify.py`
  **Dependencies**: 8.1
  **Requirements**: Finding Fixability Classification
  **Details**: Accept list of Findings from bug-scrub report JSON. Classify each into a FixTier based on source and category: ruff with fixable rules → auto; mypy type errors, markers with clear intent, deferred items with proposed fix → agent; architecture, security, design-level deferred → manual. Return ClassifiedFinding list. Apply `--severity` filter.

- [ ] 8.4 Create fix planner
  **Files**: `skills/fix-scrub/scripts/plan_fixes.py`
  **Dependencies**: 8.3
  **Requirements**: Agent-Fix Execution (file scope grouping), Auto-Fix Execution
  **Details**: Accept ClassifiedFinding list, group by file_path into FixGroups. Separate auto groups from agent groups. Enforce `--max-agent-fixes` limit (highest severity first). Produce FixPlan. Support `--dry-run` mode that outputs the plan without executing.

## Group 9: Fix Scrub — Execution (parallelizable — auto vs agent have no file overlap)

- [ ] 9.1 Create auto-fix executor
  **Files**: `skills/fix-scrub/scripts/execute_auto.py`
  **Dependencies**: 8.4
  **Requirements**: Auto-Fix Execution
  **Details**: Accept auto FixGroups. Run `ruff check --fix` on affected files. Re-run `ruff check` to verify fixes resolved findings. Return list of resolved and persisting findings.

- [ ] 9.2 Create agent-fix prompt generator
  **Files**: `skills/fix-scrub/scripts/generate_prompts.py`
  **Dependencies**: 8.4
  **Requirements**: Agent-Fix Execution
  **Details**: Accept agent FixGroups. For each group, generate a Task(general-purpose) prompt that includes: file scope, finding details, proposed fix strategy, and explicit instruction not to modify other files. Output list of (file_group, prompt_text) tuples for the SKILL.md orchestration layer to dispatch.

## Group 10: Fix Scrub — OpenSpec Task Completion Tracking

- [ ] 10.1 Create task completion tracker
  **Files**: `skills/fix-scrub/scripts/track_completions.py`
  **Dependencies**: 8.1
  **Requirements**: OpenSpec Task Completion Tracking
  **Details**: Accept a list of resolved findings (with FindingOrigin metadata). For each finding with source matching `deferred:open-tasks`, `deferred:tasks`, or `deferred:impl-findings`, locate the source artifact file. For `tasks.md` findings: change `- [ ]` to `- [x]` and append `(completed by fix-scrub YYYY-MM-DD)`. For `deferred-tasks.md` findings: append `(resolved by fix-scrub YYYY-MM-DD)` to the migration target column. Skip partial completions (multi-part tasks where not all sub-items are addressed). Return list of updated file paths for staging in the commit.

## Group 11: Fix Scrub — Verification and Reporting

- [ ] 11.1 Create quality verifier
  **Files**: `skills/fix-scrub/scripts/verify.py`
  **Dependencies**: 9.1, 9.2, 10.1
  **Requirements**: Post-Fix Quality Verification
  **Details**: Run pytest, mypy, ruff, openspec validate (reuse same tool invocations as bug-scrub collectors but in verification mode). Compare results against original bug-scrub report to detect regressions (new failures not in original). Return verification result with pass/fail and regression list.

- [ ] 11.2 Create fix-scrub report renderer
  **Files**: `skills/fix-scrub/scripts/render_fix_report.py`
  **Dependencies**: 11.1
  **Requirements**: Fix Scrub Report Output
  **Details**: Accept fix results (auto resolved, agent resolved, manual remaining, OpenSpec tasks completed, regressions, quality check results). Produce markdown summary at `docs/bug-scrub/fix-scrub-report.md`. Include tier breakdown, files changed, tasks marked completed, and manual action items.

## Group 12: Fix Scrub — Orchestrator and Skill Definition

- [ ] 12.1 Create fix-scrub main orchestrator
  **Files**: `skills/fix-scrub/scripts/main.py`
  **Dependencies**: 8.3, 8.4, 9.1, 10.1, 11.1, 11.2
  **Requirements**: Fix Scrub Remediation Skill
  **Details**: Parse CLI arguments (`--report`, `--tier`, `--severity`, `--dry-run`, `--max-agent-fixes`). Load bug-scrub JSON report. Run classifier → planner → auto executor → task completion tracker → verifier → reporter. Return exit code 0 for all fixes clean, 1 for regressions or manual items remaining. Note: agent-fix dispatch happens in the SKILL.md layer using Task() — the Python orchestrator generates prompts but does not execute them.

- [ ] 12.2 Create `skills/fix-scrub/SKILL.md`
  **Files**: `skills/fix-scrub/SKILL.md`
  **Dependencies**: 12.1
  **Requirements**: Fix Scrub Remediation Skill, Fix Scrub Commit Convention, OpenSpec Task Completion Tracking
  **Details**: Frontmatter (name, description, category, tags, triggers). Document arguments, prerequisites (bug-scrub report must exist), steps: 1) Load report and classify, 2) Dry-run preview, 3) Auto-fix execution, 4) Agent-fix dispatch via parallel Task() agents, 5) OpenSpec task completion tracking, 6) Quality verification, 7) Commit with structured message (including tasks.md updates), 8) Summary report.

## Group 13: Fix Scrub — Tests (parallelizable)

- [ ] 13.1 Create tests for classifier
  **Files**: `skills/fix-scrub/tests/test_classify.py`
  **Dependencies**: 8.3
  **Details**: Test tier assignment for each source/category combination. Test severity filtering. Test edge cases (unknown source defaults to manual).

- [ ] 13.2 Create tests for fix planner
  **Files**: `skills/fix-scrub/tests/test_plan_fixes.py`
  **Dependencies**: 8.4
  **Details**: Test file grouping, max-agent-fixes limit enforcement, dry-run output.

- [ ] 13.3 Create tests for auto-fix executor
  **Files**: `skills/fix-scrub/tests/test_execute_auto.py`
  **Dependencies**: 9.1
  **Details**: Test ruff --fix invocation and verification. Test handling when ruff not available. Test partial fix resolution.

- [ ] 13.4 Create tests for prompt generator
  **Files**: `skills/fix-scrub/tests/test_generate_prompts.py`
  **Dependencies**: 9.2
  **Details**: Test prompt content includes file scope restriction, finding detail, and proposed fix. Test same-file batching.

- [ ] 13.5 Create tests for task completion tracker
  **Files**: `skills/fix-scrub/tests/test_track_completions.py`
  **Dependencies**: 10.1
  **Details**: Test checkbox update in tasks.md (active and archived). Test deferred-tasks.md resolution annotation. Test partial completion skip. Test date formatting in annotations.

- [ ] 13.6 Create tests for quality verifier
  **Files**: `skills/fix-scrub/tests/test_verify.py`
  **Dependencies**: 11.1
  **Details**: Test regression detection against baseline. Test all-pass scenario. Test partial regression.

## Group 14: Fix Scrub — Integration

- [ ] 14.1 Update `docs/skills-workflow.md` with fix-scrub as supporting skill
  **Files**: `docs/skills-workflow.md`
  **Dependencies**: 12.2, 7.1
  **Requirements**: Fix Scrub Remediation Skill (workflow position), OpenSpec Task Completion Tracking
  **Details**: Add entry under "Supporting Skills" section describing `/fix-scrub` purpose, method, produces, and gate (none — but prompts user before committing if regressions detected). Document the `/bug-scrub` → `/fix-scrub` workflow pair. Note that fix-scrub updates OpenSpec tasks.md files when addressing deferred findings.
