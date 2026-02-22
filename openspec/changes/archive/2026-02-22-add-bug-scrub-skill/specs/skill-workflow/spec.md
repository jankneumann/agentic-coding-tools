# skill-workflow Spec Delta: add-bug-scrub-skill

## ADDED Requirements

### Requirement: Bug Scrub Diagnostic Skill

The system SHALL provide a `bug-scrub` skill that performs a comprehensive project health check by collecting signals from multiple sources, aggregating findings into a unified schema, and producing a prioritized report of actionable issues. The skill is a read-only diagnostic (no approval gate) positioned as a supporting skill alongside `/explore-feature` and `/refresh-architecture`.

The skill SHALL accept the following arguments:
- `--source <list>` (optional; comma-separated signal sources to include; default: all available)
- `--severity <level>` (optional; minimum severity to report; default: "low"; values: "critical", "high", "medium", "low", "info")
- `--project-dir <path>` (optional; directory containing pyproject.toml for CI tool execution; default: auto-detect from repository root)
- `--out-dir <path>` (optional; default: `docs/bug-scrub`)
- `--format <md|json>` (optional; default: both)

Valid signal source names: `pytest`, `ruff`, `mypy`, `openspec`, `architecture`, `security`, `deferred`, `markers`

#### Scenario: Full bug scrub run with all sources

- **WHEN** the user invokes `/bug-scrub`
- **THEN** the skill SHALL collect signals from all available sources in parallel
- **AND** normalize findings into a unified schema with severity, source, affected files, and category
- **AND** produce a prioritized markdown report at `docs/bug-scrub/bug-scrub-report.md`
- **AND** produce a machine-readable JSON report at `docs/bug-scrub/bug-scrub-report.json`

#### Scenario: Selective source execution

- **WHEN** the user invokes `/bug-scrub --source ruff,mypy,markers`
- **THEN** the skill SHALL collect signals only from the specified sources
- **AND** skip unavailable sources with a warning rather than failing

#### Scenario: Severity filtering

- **WHEN** the user invokes `/bug-scrub --severity high`
- **THEN** the report SHALL include only findings at or above the specified severity
- **AND** report the count of filtered-out findings at lower severities

### Requirement: Signal Collection from CI Tools

The bug-scrub skill SHALL collect findings from the project's CI tool chain by executing each tool and parsing its output.

#### Scenario: pytest signal collection

- **WHEN** the `pytest` source is enabled
- **THEN** the skill SHALL run pytest (excluding e2e and integration markers) and capture failures
- **AND** classify each test failure as severity "high" with source "pytest"
- **AND** record the test name, file path, and failure message

#### Scenario: ruff signal collection

- **WHEN** the `ruff` source is enabled
- **THEN** the skill SHALL run `ruff check` and parse the output
- **AND** classify findings by ruff rule severity (error → "high", warning → "medium")
- **AND** record the rule code, file path, and line number

#### Scenario: mypy signal collection

- **WHEN** the `mypy` source is enabled
- **THEN** the skill SHALL run `mypy` and parse the output
- **AND** classify type errors as severity "medium" with source "mypy"
- **AND** record the error code, file path, line number, and message

#### Scenario: openspec validation signal collection

- **WHEN** the `openspec` source is enabled
- **THEN** the skill SHALL run `openspec validate --strict --all` and parse the output
- **AND** classify validation errors as severity "medium" with source "openspec"

#### Scenario: Tool not available

- **WHEN** a CI tool (pytest, ruff, mypy) is not installed or not available in PATH
- **THEN** the skill SHALL skip that source with a warning message
- **AND** NOT treat the skip as a failure

### Requirement: Signal Collection from Existing Reports

The bug-scrub skill SHALL harvest findings from existing report artifacts produced by other skills.

#### Scenario: Architecture diagnostics harvesting

- **WHEN** the `architecture` source is enabled and `docs/architecture-analysis/architecture.diagnostics.json` exists
- **THEN** the skill SHALL parse the diagnostics file
- **AND** classify errors as severity "high", warnings as "medium", and info as "low"
- **AND** record the diagnostic type, affected node/path, and description

#### Scenario: Security review report harvesting

- **WHEN** the `security` source is enabled and `docs/security-review/security-review-report.json` exists
- **THEN** the skill SHALL parse the security report
- **AND** preserve the original severity classification from the security scanner
- **AND** record the scanner name, finding ID, title, and affected component

#### Scenario: Stale report detection

- **WHEN** a report artifact is older than 7 days
- **THEN** the skill SHALL include a staleness warning in the bug-scrub report
- **AND** recommend re-running the source skill to refresh the data

### Requirement: Deferred Issue Harvesting from OpenSpec Changes

The bug-scrub skill SHALL scan OpenSpec change artifacts for deferred and out-of-scope findings, including unchecked tasks in `tasks.md` files from both active and archived changes.

#### Scenario: Harvest from active change impl-findings

- **WHEN** the `deferred` source is enabled
- **THEN** the skill SHALL scan `openspec/changes/*/impl-findings.md` for findings marked "out of scope" or "deferred"
- **AND** classify each as severity "medium" with source "deferred:impl-findings"
- **AND** record the original change-id, finding description, and deferral reason

#### Scenario: Harvest from active change deferred-tasks

- **WHEN** the `deferred` source is enabled and `openspec/changes/*/deferred-tasks.md` files exist
- **THEN** the skill SHALL parse deferred task tables
- **AND** classify each as severity "medium" with source "deferred:tasks"
- **AND** record the original change-id, task description, and migration target

#### Scenario: Harvest unchecked tasks from active change tasks.md

- **WHEN** the `deferred` source is enabled
- **THEN** the skill SHALL scan `openspec/changes/*/tasks.md` for unchecked items (`- [ ]`)
- **AND** classify each as severity "medium" with source "deferred:open-tasks"
- **AND** record the change-id, task number, task description, file scope, and dependencies

#### Scenario: Malformed deferred artifact

- **WHEN** the `deferred` source is enabled and an `impl-findings.md`, `deferred-tasks.md`, or `tasks.md` file contains unparseable content (missing table headers, malformed markdown)
- **THEN** the skill SHALL skip that artifact with a warning message identifying the file path and parse error
- **AND** continue processing remaining artifacts

#### Scenario: Harvest from archived changes

- **WHEN** the `deferred` source is enabled
- **THEN** the skill SHALL scan archived changes at `openspec/changes/archive/*/` for:
  - `impl-findings.md` with "out of scope" or "deferred" findings
  - `deferred-tasks.md` with migrated tasks
  - `tasks.md` with unchecked items (`- [ ]`)
- **AND** classify archived deferred findings as severity "low" (lower priority than active)
- **AND** record the archive date prefix and original change-id for traceability

### Requirement: Code Marker Scanning

The bug-scrub skill SHALL scan source code for TODO, FIXME, HACK, and XXX markers.

#### Scenario: Marker scanning

- **WHEN** the `markers` source is enabled
- **THEN** the skill SHALL scan Python files (`**/*.py`) for TODO, FIXME, HACK, and XXX markers
- **AND** classify FIXME and HACK as severity "medium", TODO and XXX as severity "low"
- **AND** record the file path, line number, marker type, and surrounding context

#### Scenario: Marker age estimation

- **WHEN** a marker is found in source code
- **THEN** the skill SHALL use `git log` to estimate the marker's age (date of last modification to that line)
- **AND** include the age in the finding metadata

### Requirement: Parallel Signal Collection

The bug-scrub skill SHALL execute independent signal collectors concurrently using Task() with run_in_background=true.

#### Scenario: Parallel collection execution

- **WHEN** the skill begins signal collection
- **THEN** it SHALL launch independent collectors (pytest, ruff, mypy, markers, report parsers) as parallel Task(Bash) agents
- **AND** collect all results before proceeding to aggregation
- **AND** NOT fail-fast on first collector error

### Requirement: Unified Finding Schema

All findings from all sources SHALL be normalized into a unified schema before aggregation and reporting.

Each finding SHALL contain:
- `id`: Unique identifier (source-specific)
- `source`: Signal source name (e.g., "pytest", "ruff", "deferred:impl-findings")
- `severity`: One of "critical", "high", "medium", "low", "info"
- `category`: One of "test-failure", "lint", "type-error", "spec-violation", "architecture", "security", "deferred-issue", "code-marker"
- `file_path`: Affected file (if applicable)
- `line`: Line number (if applicable)
- `title`: Short description
- `detail`: Full description with context
- `age_days`: Estimated age in days (if available)
- `origin`: Optional provenance metadata (change_id, artifact_path, task_number, line_in_artifact) for findings harvested from OpenSpec artifacts — enables fix-scrub to locate and update the source

#### Scenario: Cross-source deduplication

- **WHEN** multiple sources report the same underlying issue (e.g., a type error that also causes a test failure)
- **THEN** the skill SHALL group related findings that share the same file path and target lines within 10 lines of each other
- **AND** present them as a cluster in the report rather than as independent items

### Requirement: Bug Scrub Report Format

The bug-scrub skill SHALL produce a structured report that prioritizes findings by severity and actionability.

#### Scenario: Report structure

- **WHEN** the skill completes aggregation
- **THEN** the report SHALL contain:
  - **Header**: Timestamp, signal sources used, severity filter, total finding count
  - **Summary**: Finding counts by severity and by source
  - **Critical/High findings**: Listed first with full detail
  - **Medium findings**: Listed with condensed detail
  - **Low/Info findings**: Count only (expandable in JSON)
  - **Staleness warnings**: For any report artifacts older than 7 days
  - **Recommendations**: Up to 5 suggested actions, selected by these rules in priority order: (1) if staleness warnings exist → "Refresh stale reports with /security-review or /refresh-architecture"; (2) if >5 test failures → "Fix failing tests before other fixes"; (3) if >10 lint findings → "Run /fix-scrub --tier auto for quick lint fixes"; (4) if deferred findings from >2 changes → "Consolidate deferred items into a follow-up proposal"; (5) if >20 findings total → "Consider running /fix-scrub --dry-run to preview remediation plan"

#### Scenario: Empty report

- **WHEN** no findings are discovered at or above the severity threshold
- **THEN** the report SHALL indicate a clean bill of health
- **AND** still include the staleness warnings section if applicable

### Requirement: Fix Scrub Remediation Skill

The system SHALL provide a `fix-scrub` skill that consumes the bug-scrub report and applies fixes with clean separation from the diagnostic phase. The skill classifies findings into three fixability tiers, applies fixes in parallel where safe, and verifies quality after changes.

The skill SHALL accept the following arguments:
- `--report <path>` (optional; default: `docs/bug-scrub/bug-scrub-report.json`)
- `--tier <list>` (optional; comma-separated tiers to apply; default: `auto,agent`; values: `auto`, `agent`, `manual`)
- `--severity <level>` (optional; minimum severity to fix; default: "medium")
- `--dry-run` (optional; plan fixes without applying them)
- `--max-agent-fixes <N>` (optional; limit agent-fix batch size; default: 10)

#### Scenario: Full fix-scrub run

- **WHEN** the user invokes `/fix-scrub`
- **THEN** the skill SHALL read the bug-scrub report from the default or specified path
- **AND** classify each finding into a fixability tier (auto, agent, manual)
- **AND** apply auto-fixes and agent-fixes for findings at or above the severity threshold
- **AND** run quality checks after all fixes
- **AND** commit the changes with a structured commit message
- **AND** report a summary of fixes applied, findings skipped, and manual-only items remaining

#### Scenario: Dry-run mode

- **WHEN** the user invokes `/fix-scrub --dry-run`
- **THEN** the skill SHALL classify all findings and produce a fix plan
- **AND** NOT apply any changes to the codebase
- **AND** report what would be fixed, by which tier, grouped by file scope

#### Scenario: No bug-scrub report found

- **WHEN** the user invokes `/fix-scrub` and no report exists at the expected path
- **THEN** the skill SHALL fail with a message recommending `/bug-scrub` be run first

#### Scenario: Bug-scrub report with missing or unknown fields

- **WHEN** the bug-scrub report JSON is missing expected fields or contains unknown fields
- **THEN** the skill SHALL treat missing fields as empty/default values
- **AND** ignore unknown fields
- **AND** log a warning suggesting the report may have been generated by a different version

### Requirement: Finding Fixability Classification

The fix-scrub skill SHALL classify each finding into one of three fixability tiers before applying fixes.

**Tier definitions:**
- **auto**: Tool-native auto-fix available (e.g., `ruff check --fix`, `ruff format`)
- **agent**: Requires code reasoning but has clear file scope (e.g., adding missing type annotations, resolving TODO markers, applying deferred patches)
- **manual**: Requires design decisions, cross-cutting changes, or human judgment (e.g., architecture issues, security findings, design-level deferred items)

#### Scenario: Auto-fixable classification

- **WHEN** a finding has source "ruff" and the rule supports `--fix`
- **THEN** the skill SHALL classify it as tier "auto"

#### Scenario: Agent-fixable classification

- **WHEN** a finding has source "mypy" (type error), or source "markers" where the marker text contains at least 10 characters after the keyword (sufficient context for an agent prompt), or source "deferred:impl-findings" where the finding includes a non-empty "Proposed Fix" or "Resolution" field
- **THEN** the skill SHALL classify it as tier "agent"

#### Scenario: Marker with insufficient context falls to manual

- **WHEN** a finding has source "markers" and the marker text contains fewer than 10 characters after the keyword (e.g., `# TODO` or `# FIXME: x`)
- **THEN** the skill SHALL classify it as tier "manual"

#### Scenario: Manual-only classification

- **WHEN** a finding has source "architecture" or source "security" or category "deferred-issue" without a clear proposed fix
- **THEN** the skill SHALL classify it as tier "manual"
- **AND** include it in the report as a manual action item

### Requirement: Auto-Fix Execution

The fix-scrub skill SHALL apply tool-native auto-fixes for all auto-tier findings.

#### Scenario: Ruff auto-fix

- **WHEN** auto-tier ruff findings exist
- **THEN** the skill SHALL run `ruff check --fix` on the affected files
- **AND** record which findings were resolved by the auto-fix

#### Scenario: Auto-fix verification

- **WHEN** auto-fixes have been applied
- **THEN** the skill SHALL re-run the originating tool to verify the fixes resolved the findings
- **AND** report any findings that persist after auto-fix

### Requirement: Agent-Fix Execution

The fix-scrub skill SHALL use Task() agents with file scope isolation to apply agent-tier fixes in parallel.

#### Scenario: Parallel agent-fix execution

- **WHEN** agent-tier findings exist targeting different files
- **THEN** the skill SHALL group findings by file path
- **AND** spawn parallel Task(general-purpose) agents, one per file group
- **AND** scope each agent's prompt to its specific files with the finding details and proposed fix
- **AND** collect results before proceeding to quality checks

#### Scenario: Same-file agent-fixes are sequential

- **WHEN** multiple agent-tier findings target the same file
- **THEN** they SHALL be batched into a single agent prompt for that file
- **AND** NOT be split across parallel agents

#### Scenario: Agent-fix batch size limit

- **WHEN** the number of agent-tier findings exceeds `--max-agent-fixes`
- **THEN** the skill SHALL process only the highest-severity findings up to the limit
- **AND** report the remaining findings as deferred to the next run

### Requirement: Post-Fix Quality Verification

The fix-scrub skill SHALL run quality checks after applying fixes to confirm no regressions.

#### Scenario: Quality checks after fixes

- **WHEN** fixes have been applied (auto or agent)
- **THEN** the skill SHALL run pytest, mypy, ruff, and openspec validate in parallel
- **AND** report all results together (no fail-fast)
- **AND** if new failures are introduced, report them clearly as regressions

#### Scenario: Regression detected

- **WHEN** quality checks reveal new failures not present in the original bug-scrub report
- **THEN** the skill SHALL flag them as regressions
- **AND** prompt the user to review before committing

### Requirement: Fix Scrub Commit Convention

The fix-scrub skill SHALL commit all applied fixes as a single commit with a structured message.

#### Scenario: Commit after successful fixes

- **WHEN** fixes have been applied and quality checks pass (or the user approves despite warnings)
- **THEN** the skill SHALL stage all changed files and commit with:
  ```
  fix(scrub): apply <N> fixes from bug-scrub report

  Auto-fixes: <count> (ruff)
  Agent-fixes: <count> (mypy, markers, deferred)
  Manual-only: <count> (reported, not fixed)

  Source report: <report-path>

  Co-Authored-By: Claude <noreply@anthropic.com>
  ```

### Requirement: OpenSpec Task Completion Tracking

The fix-scrub skill SHALL mark addressed findings as completed in their source OpenSpec `tasks.md` files when the fix resolves an open task.

#### Scenario: Mark active change task as completed

- **WHEN** a fix resolves a finding with source "deferred:open-tasks" from an active change
- **THEN** the skill SHALL update `openspec/changes/<change-id>/tasks.md`
- **AND** change the task's checkbox from `- [ ]` to `- [x]`
- **AND** append `(completed by fix-scrub YYYY-MM-DD)` to the task line
- **AND** include the tasks.md update in the fix-scrub commit

#### Scenario: Mark archived change task as completed

- **WHEN** a fix resolves a finding with source "deferred:open-tasks" from an archived change
- **THEN** the skill SHALL update `openspec/changes/archive/<change-id>/tasks.md`
- **AND** change the task's checkbox from `- [ ]` to `- [x]`
- **AND** append `(completed by fix-scrub YYYY-MM-DD)` to the task line
- **AND** include the tasks.md update in the fix-scrub commit

#### Scenario: Mark deferred-tasks entry as resolved

- **WHEN** a fix resolves a finding with source "deferred:tasks"
- **THEN** the skill SHALL update the corresponding `deferred-tasks.md` file
- **AND** add a "Resolved" column value or append `(resolved by fix-scrub YYYY-MM-DD)` to the migration target
- **AND** include the update in the fix-scrub commit

#### Scenario: Partial task completion

- **WHEN** a fix addresses a task whose description contains a numbered sub-list or semicolon-separated items, and not all sub-items are resolved
- **THEN** the skill SHALL NOT mark the task as completed
- **AND** add a note in the fix-scrub report identifying the partial progress and which sub-items remain

### Requirement: Fix Scrub Report Output

The fix-scrub skill SHALL produce a summary report of actions taken.

#### Scenario: Fix summary report

- **WHEN** the fix-scrub run completes
- **THEN** the skill SHALL print a structured summary:
  - Findings processed by tier (auto/agent/manual)
  - Fixes applied successfully
  - Fixes that failed or regressed
  - OpenSpec tasks marked as completed (with change-id and task number)
  - Manual-only items requiring human attention
  - Quality check results
- **AND** write the summary to `docs/bug-scrub/fix-scrub-report.md`
