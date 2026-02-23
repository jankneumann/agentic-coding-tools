# skill-workflow Specification

## Purpose
TBD - created by archiving change add-iterate-on-implementation-skill. Update Purpose after archive.
## Requirements
### Requirement: Iterative Refinement Skill
The system SHALL provide an `iterate-on-implementation` skill that performs structured iterative refinement of a feature implementation after `/implement-feature` completes and before `/cleanup-feature` runs.

The skill SHALL accept the following arguments:
- Change-id (required; or detected from current branch name `openspec/<change-id>`)
- Max iterations (optional; default: 5)
- Criticality threshold (optional; default: "medium"; values: "critical", "high", "medium", "low")

#### Scenario: Basic iterative refinement
- **WHEN** the user invokes `/iterate-on-implementation <change-id>`
- **THEN** the skill SHALL review the proposal, design, tasks, and current implementation code
- **AND** produce a structured improvement analysis for each iteration
- **AND** implement all findings at or above the criticality threshold
- **AND** commit the iteration's changes as a separate commit
- **AND** update documentation (CLAUDE.md, AGENTS.md, or docs/) with new lessons learned
- **AND** repeat until max iterations reached or only findings below threshold remain

#### Scenario: Early termination when only low-criticality findings remain
- **WHEN** an iteration's analysis produces only findings below the criticality threshold
- **THEN** the skill SHALL stop iterating and present a summary of all completed iterations
- **AND** report the remaining low-criticality findings for optional manual review

#### Scenario: Max iterations reached
- **WHEN** the configured max iterations have been completed
- **THEN** the skill SHALL stop iterating and present a summary
- **AND** report any remaining findings that were not addressed

#### Scenario: Out-of-scope findings
- **WHEN** an iteration identifies an issue that requires design changes beyond the current proposal scope
- **THEN** the skill SHALL flag the finding as "out of scope"
- **AND** recommend creating a new OpenSpec proposal for it
- **AND** NOT attempt to implement the out-of-scope change

#### Scenario: Parallel quality check execution
- **WHEN** the skill runs quality checks (pytest, mypy, ruff, openspec validate)
- **THEN** the skill SHALL execute all quality checks concurrently using Task(Bash) with run_in_background=true
- **AND** collect all results before reporting
- **AND** report all failures together rather than fail-fast on first error

#### Scenario: Quality check partial failure
- **WHEN** one or more quality checks fail while others succeed
- **THEN** the skill SHALL report all check results (both passing and failing)
- **AND** indicate which specific checks failed
- **AND** continue with iteration if fixes are possible

### Requirement: Structured Improvement Analysis
Each iteration SHALL produce a structured analysis where every finding contains:
- **Type**: One of bug, edge-case, workflow, performance, UX
- **Criticality**: One of critical, high, medium, low
- **Description**: What the issue is and why it matters
- **Proposed fix**: How to address the finding

#### Scenario: Analysis covers all improvement categories
- **WHEN** the skill reviews the current implementation
- **THEN** it SHALL evaluate for bugs, unhandled edge cases, workflow improvements, performance issues, and UX issues (where applicable)
- **AND** classify each finding by type and criticality

#### Scenario: Analysis is reproducible and auditable
- **WHEN** an iteration completes
- **THEN** the findings and actions taken SHALL be recorded in the commit message for that iteration

### Requirement: Iteration Commit Convention
Each iteration SHALL produce exactly one commit on the current feature branch with a message following this format:
```
refine(<scope>): iteration <N> - <summary>

Iterate-on-implementation: <change-id>, iteration <N>/<max>

Findings addressed:
- [<criticality>] <type>: <description>

Co-Authored-By: Claude <noreply@anthropic.com>
```

#### Scenario: Commit per iteration
- **WHEN** an iteration implements improvements
- **THEN** all changes for that iteration SHALL be staged and committed as a single commit
- **AND** the commit message SHALL list the findings addressed with their criticality and type

### Requirement: Documentation Update Per Iteration
Each iteration SHALL review whether genuinely new patterns, lessons, or gotchas were discovered and, if so, update the relevant documentation files.

Documentation updates SHALL follow the existing convention:
- Update CLAUDE.md or AGENTS.md directly if they are under 300 lines each
- If either file exceeds 300 lines, refactor into focused documents in docs/ and reference them

#### Scenario: New lesson discovered during iteration
- **WHEN** an iteration reveals a pattern or gotcha not already documented
- **THEN** the skill SHALL add the lesson to CLAUDE.md, AGENTS.md, or the appropriate docs/ file
- **AND** include the documentation change in the iteration's commit

#### Scenario: No new lessons in an iteration
- **WHEN** an iteration's findings are variations of already-documented patterns
- **THEN** the skill SHALL NOT add redundant documentation

### Requirement: OpenSpec Document Update Per Iteration
Each iteration SHALL review whether the current OpenSpec documents (proposal.md, design.md, spec deltas) accurately reflect the refined implementation. When findings reveal spec drift, incorrect assumptions, or missing requirements, the relevant OpenSpec documents SHALL be updated.

#### Scenario: OpenSpec document update on spec drift
- **WHEN** an iteration reveals that the proposal, design, or spec deltas contain assumptions or requirements that don't match the refined implementation
- **THEN** the skill SHALL update the relevant OpenSpec documents to reflect the actual state
- **AND** include those changes in the iteration's commit

#### Scenario: OpenSpec documents still accurate
- **WHEN** an iteration's changes are consistent with the existing OpenSpec documents
- **THEN** the skill SHALL NOT make unnecessary changes to OpenSpec documents

### Requirement: Skill Workflow Position

The `iterate-on-implementation` skill SHALL fit into the feature development workflow as an optional step between `/implement-feature` and `/cleanup-feature`. The `validate-feature` skill SHALL fit as an optional step between `/iterate-on-implementation` and `/cleanup-feature`:

```
/plan-feature → /implement-feature → /iterate-on-implementation (optional) → /validate-feature (optional) → /cleanup-feature
```

#### Scenario: Workflow integration
- **WHEN** the user completes `/implement-feature` and has a PR ready for review
- **THEN** they MAY invoke `/iterate-on-implementation` to refine the implementation before requesting review
- **AND** they MAY invoke `/validate-feature` to verify the deployed feature works correctly
- **AND** the skills SHALL operate on the existing feature branch without creating new branches

#### Scenario: Validate after iterate
- **WHEN** the user completes `/iterate-on-implementation`
- **THEN** they MAY invoke `/validate-feature` to verify the refined implementation against live deployment
- **AND** if validation fails, they MAY return to `/iterate-on-implementation` to address findings

#### Scenario: Validate without iterate
- **WHEN** the user completes `/implement-feature` without running `/iterate-on-implementation`
- **THEN** they MAY invoke `/validate-feature` directly
- **AND** the validation skill SHALL work regardless of whether iterate was run

### Requirement: Parallel Task Implementation Pattern
The `implement-feature` and `iterate-on-implementation` skills SHALL support parallel Task() subagents for implementing independent tasks or fixes concurrently.

#### Scenario: Spawn parallel implementation agents
- **WHEN** the skill identifies independent tasks (no shared files) that can be parallelized
- **THEN** it MAY spawn Task(general-purpose) agents with run_in_background=true
- **AND** scope each agent's prompt to specific files/modules
- **AND** NOT create git worktrees for agent isolation

#### Scenario: Agent file scope enforcement
- **WHEN** multiple agents are spawned for parallel implementation
- **THEN** each agent's prompt SHALL explicitly list which files/modules are in scope
- **AND** tasks with overlapping file scope SHALL be executed sequentially, not in parallel

#### Scenario: Result collection and integration
- **WHEN** all parallel agents complete their tasks
- **THEN** the orchestrator SHALL collect results using TaskOutput
- **AND** verify each agent's work before committing
- **AND** create a single commit integrating all agent work (or separate commits if appropriate)

#### Scenario: Agent failure recovery
- **WHEN** a background agent fails during execution
- **THEN** the orchestrator SHALL report the failure with context
- **AND** MAY attempt recovery using the Task resume parameter
- **AND** SHALL NOT commit partial work from failed agents without user confirmation

### Requirement: Parallel Context Exploration Pattern
Skills that gather context (plan-feature, iterate-on-plan) SHALL support parallel Task(Explore) agents for faster context collection when multiple independent sources need analysis.

#### Scenario: Parallel exploration execution
- **WHEN** a skill needs to gather context from multiple sources (specs, code, in-progress changes)
- **THEN** it MAY spawn multiple Task(Explore) agents concurrently
- **AND** synthesize the results after all agents complete

#### Scenario: Exploration is read-only
- **WHEN** Task(Explore) agents are used for context gathering
- **THEN** they SHALL NOT modify any files
- **AND** they SHALL return analysis results to the orchestrator for synthesis

### Requirement: Worktree Isolation Pattern

The `implement-feature`, `iterate-on-implementation`, and `cleanup-feature` skills SHALL support per-feature git worktree isolation to enable concurrent CLI sessions working on different features.

Worktrees SHALL be created at `../<repo-name>.worktrees/<change-id>/` relative to the main repository.

#### Scenario: Worktree creation on implement-feature
- **WHEN** the user invokes `/implement-feature <change-id>`
- **THEN** the skill SHALL create a worktree at `../<repo-name>.worktrees/<change-id>/`
- **AND** create the feature branch `openspec/<change-id>` if it doesn't exist
- **AND** change the working directory to the worktree
- **AND** continue implementation in the worktree

#### Scenario: Skip worktree creation when already in worktree
- **WHEN** the user invokes `/implement-feature <change-id>`
- **AND** the current working directory is already the worktree for that change-id
- **THEN** the skill SHALL skip worktree creation
- **AND** continue with implementation

#### Scenario: Worktree detection in iterate-on-implementation
- **WHEN** the user invokes `/iterate-on-implementation <change-id>`
- **AND** the current working directory is a git worktree
- **THEN** the skill SHALL detect the main repository path
- **AND** resolve OpenSpec files from the main repository
- **AND** operate normally on implementation files in the worktree

#### Scenario: Worktree cleanup on cleanup-feature
- **WHEN** the user invokes `/cleanup-feature <change-id>`
- **AND** a worktree exists for that change-id
- **THEN** the skill SHALL remove the worktree after archiving
- **AND** NOT remove the worktree if cleanup is aborted

### Requirement: OpenSpec File Access in Worktrees

Skills running in worktrees SHALL access OpenSpec files from the main repository, not from the worktree.

#### Scenario: OpenSpec path resolution in worktree
- **WHEN** a skill needs to read OpenSpec files (proposal.md, tasks.md, design.md, specs/)
- **AND** the skill is running in a worktree
- **THEN** it SHALL resolve the path relative to the main repository using git-common-dir
- **AND** NOT expect OpenSpec files to exist in the worktree

### Requirement: Feature Validation Skill

The system SHALL provide a `validate-feature` skill that deploys the feature locally, runs behavioral tests against the live system, **runs security scans against the live deployment**, checks CI/CD status, and verifies OpenSpec spec compliance. The skill operates between `/iterate-on-implementation` and `/cleanup-feature` in the workflow.

The skill SHALL accept the following arguments:
- Change-id (required; or detected from current branch name `openspec/<change-id>`)
- `--skip-e2e` (optional; skip Playwright E2E phase)
- `--skip-playwright` (optional; alias for `--skip-e2e`)
- `--skip-ci` (optional; skip CI/CD status check)
- `--skip-security` (optional; skip the Security Scan phase)
- `--phase <name>[,<name>]` (optional; run only specified phases, e.g., `--phase smoke,security`)

Valid phase names SHALL include: `deploy`, `smoke`, `security`, `e2e`, `architecture`, `spec`, `logs`, `ci`

#### Scenario: Full validation run includes security scanning
- **WHEN** the user invokes `/validate-feature <change-id>`
- **THEN** the skill SHALL execute validation in seven sequential phases: Deploy, Smoke, Security, E2E, Architecture, Spec Compliance, Log Analysis
- **AND** the Security phase SHALL run after Smoke confirms the API is healthy
- **AND** the Security phase SHALL run before E2E
- **AND** produce a structured validation report with pass/fail/skip/degraded per phase
- **AND** include security scan results in the validation report

#### Scenario: Security phase invokes security-review orchestrator
- **WHEN** the Security phase begins and services are confirmed healthy by Smoke
- **THEN** the skill SHALL invoke `security-review/scripts/main.py` with:
  - `--repo` pointing to the repository root
  - `--zap-target` pointing to the live API URL (e.g., `http://localhost:${AGENT_COORDINATOR_REST_PORT}`)
  - `--change` set to the current change-id
  - `--out-dir` set to `docs/security-review`
  - `--allow-degraded-pass` enabled
- **AND** capture the exit code and report output
- **AND** report the gate decision (PASS/FAIL/INCONCLUSIVE) in the phase result

#### Scenario: Security phase is non-critical
- **WHEN** the Security phase fails (exit code 10 = FAIL or exit code 11 = INCONCLUSIVE)
- **THEN** the skill SHALL continue with remaining phases (E2E, Architecture, Spec Compliance, Log Analysis)
- **AND** include the security findings in the final validation report
- **AND** NOT stop validation

#### Scenario: Security phase skipped via flag
- **WHEN** the user invokes `/validate-feature <change-id> --skip-security`
- **THEN** the skill SHALL skip the Security phase entirely
- **AND** report the phase as "skipped" in the validation report
- **AND** NOT treat the skip as a failure

#### Scenario: Security phase degrades gracefully when prerequisites missing
- **WHEN** scanner prerequisites are unavailable (no Java for dependency-check, no container runtime for ZAP)
- **THEN** the Security phase SHALL report degraded coverage (INCONCLUSIVE with `--allow-degraded-pass`)
- **AND** list which scanners were unavailable and why
- **AND** NOT block validation

#### Scenario: Security phase with selective phases
- **WHEN** the user invokes `/validate-feature <change-id> --phase security`
- **THEN** the skill SHALL run only the Security phase (assuming services are already running)
- **AND** NOT run Deploy, Smoke, E2E, or other phases

### Requirement: Validation Report Persistence and PR Integration

The validation skill SHALL persist results and integrate with the PR workflow.

#### Scenario: Report persisted to change directory
- **WHEN** validation completes
- **THEN** the skill SHALL write the validation report to `openspec/changes/<change-id>/validation-report.md`
- **AND** overwrite any previous report (only the latest run matters)
- **AND** include a timestamp and the git commit SHA at the top of the report

#### Scenario: Report posted as PR comment
- **WHEN** validation completes and a PR exists for the `openspec/<change-id>` branch
- **THEN** the skill SHALL post the validation report as a comment on the PR via `gh pr comment`
- **AND** prefix the comment with a header identifying it as an automated validation report

#### Scenario: No PR exists
- **WHEN** validation completes and no PR exists for the feature branch
- **THEN** the skill SHALL skip the PR comment step with an informational message
- **AND** still persist the report to the file

### Requirement: Validation Report Format

The validation skill SHALL produce a structured validation report at the end of each run that summarizes all phase results.

#### Scenario: All phases pass
- **WHEN** all validation phases pass
- **THEN** the report SHALL show a summary like:
  ```
  Validation Report: <change-id>
  ✓ Deploy: Services started (3 containers, DEBUG logging enabled)
  ✓ Smoke: All health checks passed (API, MCP, database)
  ✓ E2E: 5/5 Playwright tests passed
  ✓ Spec Compliance: 8/8 scenarios verified
  ✓ Log Analysis: No warnings or errors found
  ✓ CI/CD: All checks passing

  Result: PASS — Ready for /cleanup-feature
  ```

#### Scenario: Mixed results
- **WHEN** some phases fail while others pass
- **THEN** the report SHALL show each phase result with failure details:
  ```
  Validation Report: <change-id>
  ✓ Deploy: Services started
  ✓ Smoke: All health checks passed
  ✗ E2E: 3/5 tests passed, 2 failures
    - test_login_flow: TimeoutError on /api/auth
    - test_dashboard_load: Element not found: #stats-panel
  ✗ Spec Compliance: 6/8 scenarios verified, 2 mismatches
    - Agent Discovery > No matching agents: Expected empty array, got 500 error
    - Heartbeat > Stale detection: Agent not marked disconnected after threshold
  ⚠ Log Analysis: 3 warnings found
    - [WARNING] Deprecated function call: old_api_handler (line 142)
  ✓ CI/CD: All checks passing

  Result: FAIL — Address findings, then re-run /validate-feature or proceed to /iterate-on-implementation
  ```

### Requirement: Validation Prerequisite Checks

The validation skill SHALL verify prerequisites before starting the validation phases.

#### Scenario: Docker not available
- **WHEN** the user invokes `/validate-feature` and Docker/docker-compose is not installed or not running
- **THEN** the skill SHALL fail immediately with a message explaining how to install/start Docker

#### Scenario: No docker-compose.yml found
- **WHEN** the user invokes `/validate-feature` and no docker-compose.yml exists in the project
- **THEN** the skill SHALL skip the Deploy phase and attempt Smoke tests against already-running services
- **AND** inform the user that deployment validation was skipped

#### Scenario: Feature branch verification
- **WHEN** the user invokes `/validate-feature`
- **THEN** the skill SHALL verify the current branch is `openspec/<change-id>`
- **AND** verify implementation commits exist on the branch
- **AND** fail with guidance if no implementation is found

### Requirement: Proposal Prioritization Skill
The system SHALL provide a `prioritize-proposals` skill that evaluates all active OpenSpec change proposals and produces a prioritized “what to do next” order for the agentic development pipeline.

The skill SHALL accept the following arguments:
- `--change-id <id>[,<id>]` (optional; limit analysis to specific change IDs)
- `--since <git-ref>` (optional; default: `HEAD~50`; analyze commits since ref for relevance)
- `--format <md|json>` (optional; default: `md`)

#### Scenario: Prioritized report generation
- **WHEN** the user invokes `/prioritize-proposals`
- **THEN** the skill SHALL analyze all active proposals under `openspec/changes/`
- **AND** produce an ordered list of proposals with a rationale for the ranking
- **AND** identify candidate next steps for the top-ranked proposal

#### Scenario: Scoped change-id analysis
- **WHEN** the user invokes `/prioritize-proposals --change-id add-foo,update-bar`
- **THEN** the skill SHALL limit analysis to the specified change IDs
- **AND** still provide relevance, refinement, and conflict assessments for each

### Requirement: Proposal Relevance and Refinement Analysis
The `prioritize-proposals` skill SHALL evaluate each proposal against recent commits and code changes to determine relevance, required refinements, and potential conflicts.

#### Scenario: Proposal already addressed by recent commits
- **WHEN** recent commits touch the same files and requirements as a proposal
- **THEN** the skill SHALL mark the proposal as likely addressed or needing verification
- **AND** recommend whether to archive, update, or re-scope the proposal

#### Scenario: Proposal needs refinement due to code drift
- **WHEN** a proposal’s target files or assumptions have changed since it was authored
- **THEN** the skill SHALL flag it as requiring refinement
- **AND** suggest which proposal documents to update (proposal.md, tasks.md, or spec deltas)

### Requirement: Conflict-Aware Prioritization Output
The `prioritize-proposals` skill SHALL rank proposals by factoring in estimated file conflicts and dependency ordering to minimize collisions for parallel agent work.

#### Scenario: Conflict-aware ordering
- **WHEN** two proposals modify overlapping files or specs
- **THEN** the skill SHALL order them to minimize merge conflicts
- **AND** explain the detected overlap in the report

#### Scenario: Conflict-free parallel suggestions
- **WHEN** proposals are independent and touch distinct files
- **THEN** the skill SHALL identify them as parallelizable workstreams
- **AND** include that suggestion in the output report

### Requirement: Prioritization Report Persistence
The skill SHALL write the prioritization report to `openspec/changes/prioritized-proposals.md` and update it on each run.

#### Scenario: Report saved for pipeline consumption
- **WHEN** the skill finishes its analysis
- **THEN** it SHALL persist the report to `openspec/changes/prioritized-proposals.md`
- **AND** include a timestamp and analyzed git range in the report header

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

The fix-scrub skill SHALL commit all applied fixes as a single commit with a structured message on the fix-scrub branch (not main).

#### Scenario: Commit on fix-scrub branch
- **WHEN** fixes have been applied and quality checks pass (or the user approves despite warnings)
- **THEN** the skill SHALL stage all changed files and commit on the `fix-scrub/<date>` branch
- **AND** use the existing commit message format
- **AND** NOT commit to main directly

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

### Requirement: Fix Scrub Branch Isolation

The fix-scrub skill SHALL create an isolated branch before applying any code changes, ensuring all fixes go through PR review before reaching main.

#### Scenario: Branch creation on fix-scrub invocation
- **WHEN** the user invokes `/fix-scrub`
- **THEN** the skill SHALL create a branch named `fix-scrub/<YYYY-MM-DD>` from the current main HEAD
- **AND** switch to the new branch before applying any fixes
- **AND** NOT apply changes directly to main

#### Scenario: Branch name collision with existing branch
- **WHEN** the user invokes `/fix-scrub` and a branch `fix-scrub/<YYYY-MM-DD>` already exists
- **THEN** the skill SHALL append a numeric suffix (e.g., `fix-scrub/2026-02-22-2`)
- **AND** create the branch with the suffixed name

#### Scenario: PR creation after fixes applied
- **WHEN** fix-scrub has applied fixes and quality checks pass (or user approves despite warnings)
- **THEN** the skill SHALL push the branch to origin
- **AND** create a PR with the fix-scrub-report summary as the body
- **AND** present the PR URL to the user

#### Scenario: No fixes applied
- **WHEN** fix-scrub classifies all findings as manual-only or dry-run mode is active
- **THEN** the skill SHALL NOT create a branch or PR
- **AND** report the classification results without git operations

### Requirement: Fix Scrub Optional Worktree Isolation

The fix-scrub skill SHALL support optional git worktree isolation using the same pattern as implement-feature, enabled via `--worktree` flag or auto-detected when an active implementation worktree exists.

#### Scenario: Explicit worktree creation with --worktree flag
- **WHEN** the user invokes `/fix-scrub --worktree`
- **THEN** the skill SHALL create a worktree at `../<repo-name>.worktrees/fix-scrub/<date>/`
- **AND** create the fix-scrub branch in the worktree
- **AND** change the working directory to the worktree

#### Scenario: Auto-detect active implementation worktree
- **WHEN** the user invokes `/fix-scrub` without `--worktree`
- **AND** the current working directory is inside a git worktree (detected via `git rev-parse --git-common-dir`)
- **THEN** the skill SHALL create a separate worktree for the fix-scrub branch
- **AND** NOT apply fixes in the active implementation worktree

#### Scenario: Worktree not needed
- **WHEN** the user invokes `/fix-scrub` without `--worktree`
- **AND** the current working directory is the main repository (not a worktree)
- **THEN** the skill SHALL create only a branch (no worktree)
- **AND** apply fixes on the branch in the main working tree

#### Scenario: Skip worktree creation when already in fix-scrub worktree
- **WHEN** the user invokes `/fix-scrub`
- **AND** the current working directory is already a fix-scrub worktree
- **THEN** the skill SHALL skip worktree creation
- **AND** continue applying fixes in the existing worktree

### Requirement: Skill Script Path Resolution Convention

All SKILL.md files that reference co-located Python scripts SHALL use the `<agent-skills-dir>` placeholder convention to enable portable script resolution across agent runtimes.

Scripts are authored in `skills/<name>/scripts/` and distributed by `install.sh` to agent config directories (`.claude/skills/`, `.codex/skills/`, `.gemini/skills/`). Agents execute scripts from their own config directory, not from the `skills/` source.

#### Scenario: Script path placeholder in SKILL.md
- **WHEN** a SKILL.md contains a bash code block that invokes a Python script
- **THEN** the script path SHALL use the `<agent-skills-dir>/<skill-name>/scripts/` placeholder pattern
- **AND** the agent runtime SHALL substitute `<agent-skills-dir>` with its own config directory path (e.g., `.claude/skills`, `.codex/skills`, `.gemini/skills`)

#### Scenario: Agent substitution for Claude
- **WHEN** Claude Code reads a SKILL.md containing `python3 <agent-skills-dir>/fix-scrub/scripts/main.py`
- **THEN** it SHALL execute `python3 .claude/skills/fix-scrub/scripts/main.py`

#### Scenario: Agent substitution for Codex and Gemini
- **WHEN** Codex or Gemini reads a SKILL.md containing the `<agent-skills-dir>` placeholder
- **THEN** it SHALL substitute with `.codex/skills` or `.gemini/skills` respectively

#### Scenario: Script not found at agent config path
- **WHEN** the agent substitutes the placeholder and the resolved script path does not exist
- **THEN** the agent SHALL report an error indicating the script is missing
- **AND** suggest running `skills/install.sh` to sync scripts to agent directories

#### Scenario: Convention documented in SKILL.md
- **WHEN** a SKILL.md uses the `<agent-skills-dir>` placeholder
- **THEN** it SHALL include a "Script Location" note explaining the convention and the substitution rule

### Requirement: Canonical Skill Distribution

Coordinator-integrated skill content SHALL be authored in the canonical `skills/` tree.

Runtime skill trees (`.claude/skills/`, `.codex/skills/`, `.gemini/skills/`) SHALL be treated as synced mirrors for this work and refreshed using the existing `skills/install.sh` workflow in `rsync` mode.

#### Scenario: Canonical edit and sync
- **WHEN** coordinator integration changes are made to a skill
- **THEN** changes SHALL be applied to `skills/<skill-name>/SKILL.md`
- **AND** runtime mirror trees SHALL be updated by running `skills/install.sh --mode rsync --agents claude,codex,gemini`

#### Scenario: Runtime mirror drift is detected
- **WHEN** runtime mirror skills differ from canonical `skills/` after sync
- **THEN** the differences SHALL be treated as parity defects
- **AND** the change SHALL NOT be considered ready until drift is resolved

#### Scenario: Existing sync workflow is preserved
- **WHEN** implementing this change
- **THEN** it SHALL reuse existing `skills/install.sh` behavior
- **AND** SHALL NOT introduce a second competing distribution mechanism

### Requirement: Coordination Detection

Each integrated skill SHALL detect coordinator access using a transport-aware model that works for both CLI and Web/Cloud agents.

Detection SHALL set:
- `COORDINATOR_AVAILABLE` (`true` or `false`)
- `COORDINATION_TRANSPORT` (`mcp`, `http`, or `none`)
- capability flags: `CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`

Detection rules:
- Local CLI agents (Claude Codex, Codex, Gemini CLI) inspect available MCP tools by function name
- Web/Cloud agents detect coordinator via HTTP API reachability/capability checks
- Coordination hooks execute only when their capability flag is true

#### Scenario: CLI runtime with MCP tools
- **WHEN** an integrated skill starts in a CLI runtime
- **AND** coordination MCP tools are present
- **THEN** the skill SHALL set `COORDINATION_TRANSPORT=mcp`
- **AND** set `COORDINATOR_AVAILABLE=true`
- **AND** set capability flags based on discovered tool availability

#### Scenario: Web/Cloud runtime with HTTP coordinator
- **WHEN** an integrated skill starts in a Web/Cloud runtime
- **AND** coordinator HTTP endpoint is reachable with valid credentials
- **THEN** the skill SHALL set `COORDINATION_TRANSPORT=http`
- **AND** set `COORDINATOR_AVAILABLE=true`
- **AND** set capability flags based on available HTTP endpoints/features

#### Scenario: Partial capability availability
- **WHEN** transport is available but some capabilities are not
- **THEN** the skill SHALL keep `COORDINATOR_AVAILABLE=true`
- **AND** set missing capability flags to false
- **AND** skip only unsupported hooks

#### Scenario: No coordinator access
- **WHEN** neither MCP nor HTTP coordinator access is available
- **THEN** the skill SHALL set `COORDINATOR_AVAILABLE=false`
- **AND** set `COORDINATION_TRANSPORT=none`
- **AND** continue standalone behavior without errors

#### Scenario: Coordinator becomes unreachable mid-execution
- **WHEN** a coordination call fails after detection succeeded
- **THEN** the skill SHALL log informationally
- **AND** continue standalone fallback behavior for that step
- **AND** NOT abort solely due to coordinator unavailability

### Requirement: File Locking in Implement Feature

The `/implement-feature` skill SHALL use coordinator file locks only when lock capability is available.

#### Scenario: Lock acquisition succeeds
- **WHEN** `/implement-feature` is about to modify a file
- **AND** `CAN_LOCK=true`
- **THEN** the skill SHALL request a lock before modification
- **AND** proceed only after lock acquisition succeeds

#### Scenario: Lock acquisition blocked by another agent
- **WHEN** `/implement-feature` requests a lock held by another agent
- **THEN** the skill SHALL report owner/expiry details when available
- **AND** skip blocked files while continuing unblocked work

#### Scenario: Lock release on completion or failure
- **WHEN** `/implement-feature` completes or fails after acquiring locks
- **THEN** it SHALL attempt lock release
- **AND** log release failures as warnings

#### Scenario: Locking capability unavailable
- **WHEN** `CAN_LOCK=false`
- **THEN** the skill SHALL continue existing non-locking behavior

### Requirement: Work Queue Integration in Implement Feature

The `/implement-feature` skill SHALL integrate with coordinator work queue capabilities when available.

#### Scenario: Submit independent tasks to queue
- **WHEN** independent implementation tasks are identified
- **AND** `CAN_QUEUE_WORK=true`
- **THEN** the skill SHALL submit them to the coordinator queue
- **AND** report submitted task identifiers

#### Scenario: Local claim when tasks are unclaimed
- **WHEN** submitted tasks remain unclaimed within timeout
- **AND** `CAN_QUEUE_WORK=true`
- **THEN** the skill SHALL claim and execute them locally via queue APIs
- **AND** mark completion

#### Scenario: Queue capability unavailable
- **WHEN** `CAN_QUEUE_WORK=false`
- **THEN** the skill SHALL use existing local `Task()` behavior

### Requirement: Session Handoff Hooks

Creative lifecycle skills (`/plan-feature`, `/implement-feature`, `/iterate-on-plan`, `/iterate-on-implementation`, `/cleanup-feature`) SHALL use handoff hooks when `CAN_HANDOFF=true`.

#### Scenario: Read handoff context at skill start
- **WHEN** a lifecycle skill starts
- **AND** `CAN_HANDOFF=true`
- **THEN** the skill SHALL read recent handoffs and incorporate relevant context

#### Scenario: Write handoff summary at completion
- **WHEN** a lifecycle skill completes
- **AND** `CAN_HANDOFF=true`
- **THEN** the skill SHALL write a handoff summary with completed work, in-progress items, decisions, and next steps

#### Scenario: Handoff capability unavailable
- **WHEN** `CAN_HANDOFF=false`
- **THEN** the skill SHALL proceed without handoff operations

### Requirement: Memory Hooks

Memory hooks SHALL be applied where historical context is high value.

- Recall at start (`CAN_MEMORY=true`): `/explore-feature`, `/plan-feature`, `/iterate-on-plan`, `/iterate-on-implementation`, `/validate-feature`
- Remember on completion (`CAN_MEMORY=true`): `/iterate-on-plan`, `/iterate-on-implementation`, `/validate-feature`

#### Scenario: Recall relevant memories
- **WHEN** a recall-enabled skill starts
- **AND** `CAN_MEMORY=true`
- **THEN** the skill SHALL query relevant memories and use applicable results

#### Scenario: Record iteration or validation outcomes
- **WHEN** a remember-enabled skill completes
- **AND** `CAN_MEMORY=true`
- **THEN** the skill SHALL store structured outcomes and lessons learned

#### Scenario: Memory capability unavailable
- **WHEN** `CAN_MEMORY=false`
- **THEN** memory hooks SHALL be skipped without failing the skill

### Requirement: Guardrail Pre-checks

The `/implement-feature` and `/security-review` skills SHALL run guardrail checks when `CAN_GUARDRAILS=true`.

In phase 1, guardrail violations SHALL be informational and SHALL NOT hard-block execution.

#### Scenario: Guardrail check indicates safe operation
- **WHEN** a guarded operation is evaluated
- **AND** `CAN_GUARDRAILS=true`
- **AND** the response indicates safe execution
- **THEN** the skill SHALL proceed

#### Scenario: Guardrail violations detected
- **WHEN** guardrail response reports violations
- **AND** `CAN_GUARDRAILS=true`
- **THEN** the skill SHALL report violation details
- **AND** continue in informational mode

#### Scenario: Guardrail capability unavailable
- **WHEN** `CAN_GUARDRAILS=false`
- **THEN** the skill SHALL continue without guardrail checks

### Requirement: Setup Coordinator Skill

The system SHALL provide canonical `skills/setup-coordinator/SKILL.md`, then sync it to runtime mirrors using the canonical distribution flow.

The skill SHALL support both:
- CLI MCP setup/verification
- Web/Cloud HTTP setup/verification

#### Scenario: CLI setup path
- **WHEN** user runs `/setup-coordinator` for CLI usage
- **THEN** the skill SHALL verify or configure MCP coordinator settings
- **AND** verify connectivity through a coordinator session/health call

#### Scenario: Web/Cloud setup path
- **WHEN** user runs `/setup-coordinator` for Web/Cloud usage
- **THEN** the skill SHALL guide HTTP API configuration (URL, credentials, allowlist considerations)
- **AND** verify API connectivity

#### Scenario: Existing configuration detected
- **WHEN** setup detects existing configuration
- **THEN** it SHALL validate and report status
- **AND** provide reconfiguration guidance on failure

#### Scenario: Setup fails
- **WHEN** setup cannot complete due to connectivity/credential issues
- **THEN** the skill SHALL report specific failure and troubleshooting guidance
- **AND** remind that standalone mode remains available

### Requirement: Coordination Bridge Script

The system SHALL provide `scripts/coordination_bridge.py` as stable HTTP coordination contract for helper scripts and Web/Cloud validation flows.

The bridge SHALL:
- Normalize endpoint/parameter differences behind stable helpers
- Detect HTTP availability and exposed capabilities
- Return no-op responses with `status="skipped"` when unavailable

#### Scenario: Bridge detects HTTP coordinator and capabilities
- **WHEN** a script calls bridge detection helper
- **AND** coordinator API is reachable
- **THEN** bridge returns availability, transport (`http`), and capability metadata

#### Scenario: Bridge provides graceful no-op fallback
- **WHEN** bridge operation is called and coordinator is unavailable
- **THEN** bridge returns `status="skipped"` with context
- **AND** does not raise unhandled exceptions for expected unavailability

#### Scenario: Bridge absorbs API contract changes
- **WHEN** coordinator HTTP endpoint shapes evolve
- **THEN** changes are localized to `scripts/coordination_bridge.py`
- **AND** downstream scripts using bridge helpers remain stable

#### Scenario: Bridge used by validation tooling
- **WHEN** validation tooling needs coordination assertions
- **THEN** tooling can use bridge helpers instead of hardcoded HTTP details

