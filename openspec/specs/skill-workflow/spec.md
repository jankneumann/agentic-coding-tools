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

The `implement-feature`, `iterate-on-implementation`, `cleanup-feature`, and `fix-scrub` skills SHALL support per-feature git worktree isolation to enable concurrent CLI sessions working on different features.

Worktrees SHALL be created at `.git-worktrees/<change-id>/` inside the project root (gitignored), instead of `../<repo-name>.worktrees/<change-id>/`.

Skills that create, remove, or detect worktrees SHALL use `scripts/worktree.py` instead of inline bash commands. The script SHALL use only Python standard library modules and SHALL be invokable via `python3 scripts/worktree.py <subcommand>`, matching the pre-approved `Bash(python3:*)` permission pattern.

#### Scenario: Worktree creation on implement-feature
- **WHEN** the user invokes `/implement-feature <change-id>`
- **THEN** the skill SHALL invoke `python3 scripts/worktree.py setup <change-id>`
- **AND** the worktree SHALL be created at `<project-root>/.git-worktrees/<change-id>/`
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
- **THEN** the skill SHALL invoke `python3 scripts/worktree.py detect`
- **AND** resolve OpenSpec files from the main repository
- **AND** operate normally on implementation files in the worktree

#### Scenario: Worktree cleanup on cleanup-feature
- **WHEN** the user invokes `/cleanup-feature <change-id>`
- **AND** a worktree exists for that change-id
- **THEN** the skill SHALL invoke `python3 scripts/worktree.py teardown <change-id>`
- **AND** the teardown SHALL check both `.git-worktrees/` and legacy `../<repo>.worktrees/` locations
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
- **THEN** the skill SHALL invoke `python3 scripts/worktree.py setup <date> --branch <name> --prefix fix-scrub`
- **AND** the worktree SHALL be created at `<project-root>/.git-worktrees/fix-scrub/<date>/`
- **AND** change the working directory to the worktree

#### Scenario: Auto-detect active implementation worktree
- **WHEN** the user invokes `/fix-scrub` without `--worktree`
- **AND** the current working directory is inside a git worktree (detected via `python3 scripts/worktree.py detect`)
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

### Requirement: Gitignore Worktree Directory

The project `.gitignore` SHALL include `.git-worktrees/` to prevent worktree contents from being tracked by the main repository.

#### Scenario: Worktree contents not tracked
- **WHEN** a worktree exists at `.git-worktrees/<change-id>/`
- **AND** the user runs `git status` in the main repo
- **THEN** files inside `.git-worktrees/` SHALL NOT appear as untracked

### Requirement: Parallel Skill Family

The system SHALL provide a `parallel-*` skill family alongside the existing skills (renamed to `linear-*`) for multi-agent parallel feature development.

- The `parallel-*` skills SHALL include: `parallel-explore-feature`, `parallel-plan-feature`, `parallel-implement-feature`, `parallel-review-plan`, `parallel-review-implementation`, `parallel-validate-feature`, `parallel-cleanup-feature`.
- Existing skills SHALL be renamed to `linear-*` prefix with backward-compatible aliases.
- Both skill families SHALL coexist and share the same OpenSpec artifact structure.

#### Scenario: Invoke parallel plan skill
- **WHEN** a user invokes `/parallel-plan-feature <description>`
- **THEN** the skill SHALL produce a `contracts/` directory with OpenAPI specs and a `work-packages.yaml` conforming to `work-packages.schema.json`
- **AND** the skill SHALL validate work-packages against the schema before presenting for approval

#### Scenario: Invoke existing skill by original name
- **WHEN** a user invokes a skill by its original name (e.g., `/explore-feature`)
- **THEN** the system SHALL resolve it to the `linear-*` equivalent via alias
- **AND** behavior SHALL be identical to the pre-rename skill

#### Scenario: Parallel skill degrades when coordinator unavailable
- **WHEN** a `parallel-*` skill detects that required coordinator capabilities (`CAN_DISCOVER`, `CAN_QUEUE_WORK`, `CAN_LOCK`) are unavailable
- **THEN** the skill SHALL degrade to linear-equivalent behavior
- **AND** the skill SHALL emit a warning explaining the degradation

### Requirement: Contract-First Development Phase

The `/parallel-plan-feature` skill SHALL produce machine-readable interface definitions before any implementation agent starts.

- Contracts SHALL include OpenAPI specs as the canonical artifact for API endpoints.
- Contracts SHALL support language-specific type generation: Pydantic models for Python, TypeScript interfaces for frontend.
- Contracts SHALL include SQL schema definitions for new database tables.
- Contracts SHALL include event schemas (JSON Schema) for async communication.
- Contracts SHALL support executable mock generation via Prism from the OpenAPI spec.

#### Scenario: Plan produces contract artifacts
- **WHEN** `/parallel-plan-feature` completes successfully
- **THEN** the `contracts/` directory SHALL contain at least one valid OpenAPI spec file
- **AND** `work-packages.yaml` SHALL reference all contract files in `contracts.openapi.files`
- **AND** `contracts.revision` SHALL be set to 1

#### Scenario: Contract compliance verification layers
- **WHEN** a work package completes implementation
- **THEN** the package's verification steps SHALL include static type checking of generated types
- **AND** Schemathesis property-based testing against the OpenAPI spec (Tier A minimum)
- **AND** Pact consumer-driven contract tests when CDC is enabled

### Requirement: Contract Revision Semantics

The system SHALL enforce contract revision tracking to prevent agents from working against stale contracts.

- Any contract file modification after implementation dispatch SHALL require a `contracts.revision` bump in `work-packages.yaml`.
- The orchestrator SHALL reject results whose `contracts_revision` does not match the current `work-packages.yaml` value.

#### Scenario: Contract changes during implementation
- **WHEN** an escalation triggers a contract modification after work packages have been dispatched
- **THEN** the orchestrator SHALL bump `contracts.revision` in `work-packages.yaml`
- **AND** the orchestrator SHALL resubmit all packages whose `contracts_revision` is now stale
- **AND** the orchestrator SHALL acquire the `feature:<id>:pause` lock during the bump procedure

#### Scenario: Result with stale contract revision
- **WHEN** a completed package reports `contracts_revision` lower than the current `work-packages.yaml` value
- **THEN** the orchestrator SHALL treat the result as stale and ignore it
- **AND** the orchestrator SHALL not merge the package's worktree

### Requirement: Work Package DAG Scheduling

The `/parallel-implement-feature` skill SHALL decompose implementation into agent-scoped work packages with deterministic DAG scheduling.

- Each work package SHALL declare explicit file scope (`scope.write_allow`, `scope.read_allow`, `scope.deny`).
- Each work package SHALL declare explicit resource claims (`locks.files`, `locks.keys`).
- For any two packages that can run in parallel, `scope.write_allow` sets SHALL NOT overlap (except `wp-integration`).
- For parallel packages, `locks.keys` sets SHALL NOT overlap.
- The DAG SHALL be computed via topological sort with cycle detection.
- No dependent package SHALL run if its dependency is FAILED or CANCELLED.

#### Scenario: DAG preflight validation
- **WHEN** the orchestrator parses `work-packages.yaml` before dispatch
- **THEN** the orchestrator SHALL validate against `work-packages.schema.json`
- **AND** detect and reject cycles in the dependency graph
- **AND** verify file scope non-overlap for parallel packages
- **AND** verify logical lock non-overlap for parallel packages

#### Scenario: Dependency package fails
- **WHEN** a work package completes with `status=failed`
- **THEN** all packages that transitively depend on it SHALL be marked CANCELLED
- **AND** the orchestrator SHALL not dispatch cancelled packages

#### Scenario: All packages complete successfully
- **WHEN** all non-integration packages complete with `status=completed`
- **THEN** the orchestrator SHALL dispatch the `wp-integration` package
- **AND** `wp-integration` SHALL claim the union of all file locks from all packages

### Requirement: Scope Enforcement

The system SHALL enforce per-package file scope compliance via deterministic diff checks.

- Modified files SHALL be computed from `git diff --name-only`.
- Each modified file SHALL match at least one glob in `scope.write_allow`.
- No modified file SHALL match any glob in `scope.deny`.
- Scope violations SHALL cause the package to fail with `error_code="SCOPE_VIOLATION"`.

#### Scenario: Agent modifies file within scope
- **WHEN** a work package agent modifies a file that matches `scope.write_allow` and does not match `scope.deny`
- **THEN** the scope check SHALL pass for that file

#### Scenario: Agent modifies file outside scope
- **WHEN** a work package agent modifies a file that does not match any `scope.write_allow` glob
- **THEN** the scope check SHALL fail
- **AND** the package SHALL report `error_code="SCOPE_VIOLATION"` with the violating file paths

### Requirement: Escalation Protocol

Work package executors SHALL signal structured escalations when they cannot complete correctly under current constraints.

- Escalations SHALL be dual-written: in the package's `result.escalations[]` and as an independent `task_type="escalation"` work-queue task with `priority=1`.
- The orchestrator SHALL follow a deterministic decision procedure per escalation type.
- `BLOCKING` severity escalations SHALL trigger the pause-lock mechanism (`feature:<id>:pause`).

#### Scenario: Contract revision required escalation
- **WHEN** a package agent discovers the contract is wrong during implementation
- **THEN** the agent SHALL submit an escalation with `type="CONTRACT_REVISION_REQUIRED"` and `severity="BLOCKING"`
- **AND** the agent SHALL stop making forward progress and fail the package
- **AND** the orchestrator SHALL execute the contract revision bump procedure

#### Scenario: Non-blocking escalation
- **WHEN** a package agent encounters a flaky test unrelated to its code changes
- **THEN** the agent SHALL include an escalation with `type="FLAKY_TEST_QUARANTINE_REQUEST"` and `severity="NON_BLOCKING"` in `result.escalations[]`
- **AND** the agent MAY complete the package successfully

### Requirement: Review Agent Decoupling

`/parallel-review-plan` and `/parallel-review-implementation` SHALL operate as independent, read-only evaluation agents.

- Review agents SHALL receive artifacts as read-only input.
- Review agents SHALL produce findings conforming to `review-findings.schema.json`.
- Review agents SHALL NOT modify any artifacts directly.
- Review agents SHALL support dispatch to different AI vendors than the implementing agent.

#### Scenario: Review produces actionable findings
- **WHEN** `/parallel-review-implementation` reviews a completed work package's diff
- **THEN** the review SHALL produce a findings table with `id`, `type`, `criticality`, `description`, and `disposition`
- **AND** each finding SHALL have disposition of `fix`, `regenerate`, `accept`, or `escalate`

#### Scenario: Review finding with fix disposition
- **WHEN** a review finding has `disposition="fix"`
- **THEN** the orchestrator SHALL dispatch a `wp-fix-<package_id>` package inheriting the same locks and scope

### Requirement: Continuous Validation

Validation SHALL be distributed across implementation phases rather than concentrated in a monolithic post-implementation step.

- Linting, type checking, and unit tests SHALL run during implementation in each package's `verification.steps`.
- Contract compliance (Schemathesis, Pact) SHALL run during implementation at Tier A minimum.
- Scope compliance SHALL run after code generation as a deterministic diff check.
- Full end-to-end and integration tests SHALL run only in `wp-integration` and `/parallel-validate-feature`.

#### Scenario: Package-level verification during implementation
- **WHEN** a work package agent completes code generation
- **THEN** the agent SHALL execute all `verification.steps` in order
- **AND** on any step failure the agent SHALL fail fast without continuing to subsequent steps
- **AND** the result SHALL include which step failed and why

### Requirement: Feature Registry and Cross-Feature Coordination

The coordinator SHALL maintain a feature registry for cross-feature resource claim management.

- Each registered feature SHALL declare resource claims using the lock key namespace.
- The coordinator SHALL produce parallel feasibility assessments: `FULL`, `PARTIAL`, or `SEQUENTIAL`.
- Cross-feature resource collisions SHALL be handled via the `RESOURCE_CONFLICT` escalation type.

#### Scenario: Two features with no resource conflicts
- **WHEN** two features register resource claims that do not overlap
- **THEN** the feasibility assessment SHALL be `FULL`

#### Scenario: Two features with blocking conflicts
- **WHEN** two features claim the same critical resource
- **THEN** the feasibility assessment SHALL be `SEQUENTIAL`
- **AND** the second feature SHALL wait until the first completes

### Requirement: CI Coverage for Skill Test Suites

The CI pipeline SHALL include a dedicated job that runs the test suites for diagnostic skills (bug-scrub and fix-scrub) on every push and pull request.

- **GIVEN** the CI pipeline runs on push to main or on a pull request
- **WHEN** the `test-skills` job executes
- **THEN** it SHALL run all tests in `skills/bug-scrub/tests/` and `skills/fix-scrub/tests/`
- **AND** it SHALL use the agent-coordinator virtual environment for pytest execution
- **AND** it SHALL run from the repository root to preserve cross-skill import path resolution
- **AND** a test failure SHALL block the CI pipeline (non-`continue-on-error`)

#### Scenario: Skills tests pass in CI

- **GIVEN** a push to main with no regressions in skill scripts
- **WHEN** the `test-skills` CI job runs
- **THEN** all bug-scrub and fix-scrub tests SHALL pass
- **AND** the job SHALL report success

#### Scenario: Skills test failure blocks CI

- **GIVEN** a pull request that introduces a regression in a skill script
- **WHEN** the `test-skills` CI job runs
- **THEN** the failing test SHALL be reported
- **AND** the CI pipeline SHALL not pass

### Requirement: Launcher Invariant (All Write Skills)

Every skill that modifies git state (commit, branch checkout, merge) SHALL operate in a worktree, never on the shared checkout. The shared checkout is a read-only launcher.

- The launcher invariant SHALL apply to: `parallel-plan-feature`, `linear-plan-feature`, `parallel-implement-feature`, `linear-implement-feature`, `parallel-cleanup-feature`, `linear-cleanup-feature`
- The launcher invariant SHALL NOT apply to read-only skills: `*-explore-feature`, `*-review-*`, `*-validate-feature`
- Skills SHALL call `scripts/worktree.py setup <change-id>` (feature-level) or `scripts/worktree.py setup <change-id> --agent-id <id>` (package-level) as their first write-capable step
- No skill SHALL run `git add`, `git commit`, `git checkout`, or `git merge` in the shared checkout directory

#### Scenario: Two planning sessions from same checkout
- **WHEN** terminal 1 runs `/parallel-plan-feature` for change `feature-a` and terminal 2 runs `/parallel-plan-feature` for change `feature-b` from the same checkout
- **THEN** terminal 1 creates worktree `.git-worktrees/feature-a/` on branch `openspec/feature-a`
- **AND** terminal 2 creates worktree `.git-worktrees/feature-b/` on branch `openspec/feature-b`
- **AND** both commit their planning artifacts to their respective branches
- **AND** the shared checkout is never modified

#### Scenario: Planning worktree reused by implementation
- **WHEN** `/parallel-plan-feature` completes and pins its worktree
- **AND** user approves and runs `/parallel-implement-feature` for the same change
- **THEN** implementation reuses the existing feature branch (with planning artifacts)
- **AND** creates sub-worktrees for each package from that branch

---

### Requirement: Planning Skills Use Feature-Level Worktrees

`parallel-plan-feature` and `linear-plan-feature` SHALL create a feature-level worktree for artifact creation, committing planning artifacts to the feature branch.

- Planning skills SHALL call `worktree.py setup <change-id>` (no agent-id) at skill start
- All artifact creation (`openspec new change`, writing proposal/design/specs/tasks/work-packages) SHALL happen inside the worktree
- Planning skills SHALL commit artifacts to branch `openspec/<change-id>` and push
- Planning skills SHALL pin the worktree after completion (for reuse by implementation)

#### Scenario: Parallel plan feature uses worktree
- **WHEN** user runs `/parallel-plan-feature "add user auth"` with change-id `add-user-auth`
- **THEN** skill creates worktree `.git-worktrees/add-user-auth/` on branch `openspec/add-user-auth`
- **AND** all OpenSpec artifacts are created inside that worktree
- **AND** artifacts are committed and pushed on `openspec/add-user-auth`
- **AND** worktree is pinned for reuse

---

### Requirement: Cleanup Skills Use Worktrees

`parallel-cleanup-feature` and `linear-cleanup-feature` SHALL perform merge, archive, and branch operations inside a worktree.

- Cleanup skills SHALL call `worktree.py setup <change-id> --agent-id cleanup` at skill start
- All merge (`gh pr merge`), archive (`openspec archive`), and branch operations SHALL happen inside the cleanup worktree
- After cleanup completes, the skill SHALL teardown all remaining worktrees for the change-id and run `worktree.py gc`

#### Scenario: Parallel cleanup uses worktree
- **WHEN** user runs `/parallel-cleanup-feature add-user-auth`
- **THEN** skill creates worktree `.git-worktrees/add-user-auth/cleanup/`
- **AND** performs merge and archive operations inside that worktree
- **AND** tears down all worktrees for `add-user-auth` after completion

---

### Requirement: Implementation Orchestrator Worktree Setup

The `parallel-implement-feature` orchestrator SHALL create a dedicated worktree for every work package — including root packages — before implementation begins.

- The orchestrator SHALL call `scripts/worktree.py setup <change-id> --agent-id <package-id>` for every package (root and parallel) before implementation
- The orchestrator SHALL NEVER modify the shared checkout directly — it is a read-only launcher
- The orchestrator SHALL implement root packages (no dependencies) sequentially in their own worktrees, merging each into the feature branch before parallel dispatch
- The orchestrator SHALL pin all parallel worktrees during execution to prevent GC reclamation
- The orchestrator SHALL record worktree paths and branches in the agent dispatch context
- The orchestrator SHALL teardown all worktrees after integration completes or on failure

#### Scenario: Orchestrator creates worktrees for parallel packages
- **WHEN** orchestrator dispatches 3 parallel packages (wp-backend, wp-frontend, wp-tests) for change `add-auth`
- **THEN** `.git-worktrees/add-auth/wp-backend/`, `.git-worktrees/add-auth/wp-frontend/`, `.git-worktrees/add-auth/wp-tests/` exist
- **AND** branches `openspec/add-auth/wp-backend`, `openspec/add-auth/wp-frontend`, `openspec/add-auth/wp-tests` exist
- **AND** all three worktrees are registered in `.git-worktrees/.registry.json`
- **AND** all three are pinned

#### Scenario: Root packages implemented in worktrees, not shared checkout
- **WHEN** DAG has root package `wp-contracts` (no deps) and parallel packages depending on it
- **THEN** orchestrator creates worktree `.git-worktrees/add-auth/wp-contracts/`
- **AND** implements `wp-contracts` in that worktree
- **AND** merges `wp-contracts` branch into feature branch
- **AND** tears down the root worktree
- **AND** parallel package worktrees are created from the updated feature branch
- **AND** the shared checkout is never modified

#### Scenario: Multiple orchestrators on same checkout do not conflict
- **WHEN** terminal 1 runs `/parallel-implement-feature feature-a` and terminal 2 runs `/parallel-implement-feature feature-b` from the same checkout
- **THEN** terminal 1 creates worktrees under `.git-worktrees/feature-a/`
- **AND** terminal 2 creates worktrees under `.git-worktrees/feature-b/`
- **AND** the shared checkout remains unchanged
- **AND** no git staging, branch switching, or file contention occurs between the two

#### Scenario: Worktrees cleaned up after completion
- **WHEN** integration merge completes successfully
- **THEN** orchestrator calls `worktree.py teardown` for each package worktree
- **AND** worktrees are removed from the registry

---

### Requirement: Agent Dispatch with Worktree Context

The orchestrator SHALL include worktree path and branch information in every parallel agent dispatch, and use vendor isolation when available as a safety net.

- For vendors supporting agent isolation (e.g., Claude Code `isolation: "worktree"`), the dispatch SHALL use the vendor isolation mechanism as a safety net
- For vendors without isolation support, the agent prompt SHALL instruct the agent to `cd` into the worktree path as its first action
- The dispatch prompt SHALL include `WORKTREE_PATH`, `BRANCH`, `CHANGE_ID`, and `PACKAGE_ID` for every parallel agent
- The agent SHALL verify it is operating in the correct worktree before modifying files

#### Scenario: Claude Code agent dispatched with vendor isolation
- **WHEN** orchestrator dispatches a parallel package to a Claude Code agent
- **THEN** Agent tool call includes `isolation: "worktree"` parameter
- **AND** agent prompt includes the worktree path and branch from our registry
- **AND** agent commits to the registered branch name

#### Scenario: Non-isolating vendor agent dispatched with cd instruction
- **WHEN** orchestrator dispatches a parallel package to an agent without isolation support
- **THEN** agent prompt begins with `cd <worktree-path>` instruction
- **AND** agent operates exclusively within that directory
- **AND** agent commits to the registered branch name

#### Scenario: Agent worktree verification
- **WHEN** agent begins work on a package
- **THEN** agent verifies `git rev-parse --show-toplevel` matches the expected worktree path
- **AND** agent verifies `git branch --show-current` matches the expected branch name
- **AND** if verification fails, agent reports error rather than proceeding in wrong directory

---

### Requirement: Integration Merge Protocol

After all parallel packages complete, an integration agent SHALL merge per-package branches into the feature branch with conflict detection.

- The integration merge SHALL use `git merge --no-ff` for each package branch to preserve per-package commit history
- Merge conflicts SHALL be treated as scope overlap violations and reported as errors
- The integration agent SHALL run the full verification suite after merging all branches
- The integration agent SHALL operate in its own worktree (`--agent-id integrator`)

#### Scenario: Clean integration merge
- **WHEN** all 3 parallel packages complete with non-overlapping changes
- **THEN** integrator merges `openspec/add-auth/wp-backend`, `openspec/add-auth/wp-frontend`, `openspec/add-auth/wp-tests` into `openspec/add-auth`
- **AND** each merge uses `--no-ff` creating a merge commit
- **AND** full test suite passes on the merged result

#### Scenario: Merge conflict detected
- **WHEN** two packages modified the same file (scope violation)
- **THEN** integrator reports the conflict as a SCOPE_VIOLATION escalation
- **AND** identifies the conflicting files and packages
- **AND** does NOT attempt automatic conflict resolution

---

### Requirement: Vendor-Agnostic Isolation Strategy

The worktree isolation approach SHALL work across agent vendors without requiring vendor-specific code paths in the core orchestration logic.

- The orchestrator's worktree management (Layer 1) SHALL be identical regardless of agent vendor
- Vendor-specific isolation (Layer 2) SHALL be configured via the agent profile in `agents.yaml`, not hardcoded
- The `agents.yaml` schema SHALL support an optional `isolation` field per agent type
- When vendor isolation is unavailable, the system SHALL degrade to cd-based worktree access with a logged warning

#### Scenario: Agent profile declares isolation capability
- **WHEN** `agents.yaml` declares `claude-code-local` with `isolation: worktree`
- **THEN** orchestrator uses `Agent(isolation="worktree")` when dispatching to that agent
- **AND** also sets up our Layer 1 worktree for registry/lifecycle tracking

#### Scenario: Agent profile without isolation capability
- **WHEN** `agents.yaml` declares `codex-local` without an `isolation` field
- **THEN** orchestrator dispatches without vendor isolation
- **AND** agent prompt includes explicit `cd <worktree-path>` instruction
- **AND** a warning is logged that vendor isolation is unavailable

### Requirement: Change Context Traceability Artifact

The system SHALL produce a `change-context.md` artifact during the feature workflow that maps every spec requirement to its implementing code, tests, and validation evidence.

The artifact SHALL contain the following sections:
- **Requirement Traceability Matrix**: One row per SHALL/MUST requirement with columns: Req ID, Spec Source, Description, Files Changed, Test(s), Evidence
- **Design Decision Trace**: One row per decision from design.md (omitted when no design.md exists)
- **Review Findings Summary**: Synthesized review findings (parallel workflow only, omitted for linear)
- **Coverage Summary**: Exact counts of requirements traced, tests mapped, evidence collected, gaps, and deferred items

#### Scenario: Artifact generated during linear implementation
- **WHEN** the agent executes `/implement-feature <change-id>`
- **THEN** the system SHALL create `change-context.md` in the change directory
- **AND** the Requirement Traceability Matrix SHALL contain one row per SHALL/MUST clause from `specs/<capability>/spec.md`
- **AND** the Req ID format SHALL be `<capability>.<N>` where N is the ordinal position in the spec file

#### Scenario: Artifact generated during parallel implementation
- **WHEN** the orchestrator executes `/parallel-implement-feature <change-id>`
- **THEN** the system SHALL create `change-context.md` after integration merge
- **AND** the Files Changed column SHALL cross-reference `files_modified` from work-queue results per package
- **AND** the Review Findings Summary SHALL synthesize findings from all `review-findings.json` files

#### Scenario: Backward compatibility for pre-existing changes
- **WHEN** `/validate-feature` runs on a change that lacks `change-context.md`
- **THEN** the system SHALL generate the skeleton on-the-fly from specs and git diff
- **AND** proceed with evidence population as normal

#### Scenario: Coverage summary accuracy
- **WHEN** `change-context.md` is populated
- **THEN** the Coverage Summary SHALL use exact counts (not estimates)
- **AND** gaps SHALL list requirements with no test mapping
- **AND** deferred items SHALL list requirements that could not be verified

### Requirement: 3-Phase Incremental Generation

The `change-context.md` artifact SHALL be built incrementally across three workflow phases.

#### Scenario: Phase 1 — Test plan (pre-implementation)
- **WHEN** the agent reads spec delta files before implementing tasks
- **THEN** the system SHALL populate Req ID, Spec Source, Description, Contract Ref, Design Decision, and Test(s) columns
- **AND** Contract Ref SHALL reference the contract file the requirement maps to (e.g., `contracts/openapi/v1.yaml#/paths/~1users`), or `---` if no contract applies
- **AND** Design Decision SHALL reference the decision from `design.md` (e.g., `D3`) that the requirement validates, or `---` if none applies
- **AND** Files Changed SHALL be set to `---`
- **AND** Evidence SHALL be set to `---`
- **AND** the agent SHALL write failing tests (RED) for each row in the matrix

#### Scenario: Phase 2 — Implementation
- **WHEN** the agent completes implementation tasks
- **THEN** the system SHALL update the Files Changed column with actual source files modified
- **AND** tests from Phase 1 SHALL now pass (GREEN)
- **AND** the Design Decision Trace Implementation column SHALL be populated if design.md exists

#### Scenario: Phase 3 — Validation evidence
- **WHEN** `/validate-feature` runs the spec compliance phase
- **THEN** the system SHALL fill the Evidence column for each requirement row
- **AND** evidence values SHALL be one of: `pass <short-SHA>`, `fail <short-SHA>`, `deferred <reason>`

### Requirement: TDD Enforcement via Change Context

The implementation workflow SHALL enforce test-driven development structurally through the change-context artifact.

#### Scenario: Tests written before implementation code
- **WHEN** the agent begins the implementation phase
- **THEN** step 3a "Generate Change Context & Test Plan" SHALL execute before step 3 "Implement Tasks"
- **AND** the Test(s) column SHALL be populated with planned test function names derived from spec scenarios
- **AND** those tests SHALL be written as failing tests before any implementation code

#### Scenario: Tests encode spec scenarios
- **WHEN** the agent writes tests in Phase 1
- **THEN** each test function SHALL encode the corresponding spec scenario's WHEN/THEN/AND clauses as assertions
- **AND** tests for requirements with a Contract Ref SHALL assert against the contracted interface (e.g., validate response schemas match OpenAPI spec, event payloads match JSON schema, DB operations respect schema constraints)
- **AND** tests for requirements with a Design Decision SHALL verify the chosen approach (e.g., if D3 chose pg_notify over polling, test that NOTIFY is used, not SELECT loops)
- **AND** tests for scenarios requiring live services SHALL use `@pytest.mark.integration` or `@pytest.mark.e2e` markers

#### Scenario: Existing TDD advisory replaced
- **WHEN** the skill instructions for `/implement-feature` are updated
- **THEN** the existing 3-line TDD advisory note SHALL be removed
- **AND** TDD enforcement SHALL be achieved through the structural step ordering (step 3a before step 3)

### Requirement: Validation Report Spec Compliance Refactoring

The `validation-report.md` template SHALL reference `change-context.md` for spec compliance instead of duplicating the data.

#### Scenario: Spec compliance section replaced
- **WHEN** `/validate-feature` generates the validation report
- **THEN** the "Spec Compliance Details" section SHALL be replaced with a reference to `change-context.md`
- **AND** only a summary count (N/M requirements verified) SHALL appear in the validation report

#### Scenario: Operational phases retained
- **WHEN** the validation report is generated
- **THEN** all operational phases (Deploy, Smoke, Security, E2E, Architecture, Logs, CI/CD) SHALL be retained unchanged

### Requirement: Change Context Update During Iteration

The `/iterate-on-implementation` skill SHALL update `change-context.md` when iteration findings change the requirement-to-code mapping.

#### Scenario: New requirement discovered during iteration
- **WHEN** an iteration finding reveals a missing spec requirement
- **THEN** a new row SHALL be added to the Requirement Traceability Matrix
- **AND** the corresponding test SHALL be written before the fix is implemented

#### Scenario: Files or tests changed during iteration
- **WHEN** an iteration adds new files, tests, or changes requirement mappings
- **THEN** the Files Changed and Test(s) columns SHALL be updated accordingly
- **AND** the Coverage Summary SHALL be updated with new counts

### Requirement: Implement Feature Skill Step Structure

The `/implement-feature` skill SHALL include a new step 3a "Generate Change Context & Test Plan" inserted before the existing "Implement Tasks" step.

#### Scenario: Step ordering enforces TDD
- **WHEN** the agent executes `/implement-feature <change-id>`
- **THEN** step 3a SHALL execute before step 3
- **AND** step 3a SHALL produce `change-context.md` with the traceability skeleton and failing tests
- **AND** step 3 SHALL reference tests from step 3a as the behavioral specification

### Requirement: PR Body Includes Change Context Link

The PR creation step SHALL include a link to `change-context.md` alongside the existing proposal link.

#### Scenario: Change context linked in PR
- **WHEN** the agent creates a PR via `gh pr create`
- **THEN** the PR body SHALL include: `**Change Context**: openspec/changes/<change-id>/change-context.md`

### Requirement: Parallel Cleanup Feature Coordinator Integration

The `parallel-cleanup-feature` skill SHALL reference actual coordinator MCP tools and HTTP endpoints instead of pseudo-code for merge queue and feature registry operations.

#### Scenario: Merge queue enqueue in skill
- WHEN the skill enqueues a feature for merge
- THEN it SHALL call MCP tool `enqueue_merge` or HTTP `POST /merge-queue/enqueue`
- AND NOT reference `merge_queue.enqueue()` pseudo-code

#### Scenario: Pre-merge checks in skill
- WHEN the skill runs pre-merge checks
- THEN it SHALL call MCP tool `run_pre_merge_checks` or HTTP `POST /merge-queue/check/{feature_id}`

#### Scenario: Mark merged in skill
- WHEN the skill marks a feature as merged
- THEN it SHALL call MCP tool `mark_merged` or HTTP `POST /merge-queue/merged/{feature_id}`

#### Scenario: Coordinator unavailable fallback
- WHEN the coordinator is unavailable
- THEN the skill SHALL degrade to `linear-cleanup-feature` behavior without error

### Requirement: Infrastructure Skill Packaging

Scripts referenced by multiple skills MUST be packaged as infrastructure skills under `skills/` with a `SKILL.md` and a `scripts/` subdirectory.

#### Scenario: Shared script is packaged as infrastructure skill
- **GIVEN** a Python script in `scripts/` that is referenced by 2+ skills
- **WHEN** the skill packaging is evaluated
- **THEN** the script MUST exist in an infrastructure skill directory under `skills/<infra-skill>/scripts/`
- **AND** the infrastructure skill MUST have a `SKILL.md` file

### Requirement: Infrastructure Skills Are Not User-Invocable

Infrastructure skills MUST set `user_invocable: false` in their SKILL.md frontmatter and `category: Infrastructure`.

#### Scenario: Infrastructure skill frontmatter
- **GIVEN** an infrastructure skill directory under `skills/`
- **WHEN** the SKILL.md frontmatter is parsed
- **THEN** the `user_invocable` field MUST be `false`
- **AND** the `category` field MUST be `Infrastructure`

### Requirement: Infrastructure Skill API Documentation

Infrastructure skills MUST document all script entry points, arguments, outputs, and exit codes in their SKILL.md.

#### Scenario: Script API is documented
- **GIVEN** an infrastructure skill with scripts in `scripts/`
- **WHEN** the SKILL.md is reviewed
- **THEN** each script MUST have documented entry point, CLI arguments, stdout/stderr format, and exit codes

### Requirement: Sibling-Relative Path Resolution

Skills MUST reference infrastructure scripts using sibling-relative paths: `<skill-base-dir>/../<infra-skill>/scripts/<script>`.

#### Scenario: Skill references infrastructure script
- **GIVEN** a skill that depends on `worktree.py`
- **WHEN** the SKILL.md path reference is evaluated
- **THEN** the path MUST use the pattern `<skill-base-dir>/../worktree/scripts/worktree.py`
- **AND** MUST NOT use `scripts/worktree.py` (repo-root-relative)

### Requirement: No Repo-Root Script References

Skills MUST NOT reference scripts at repo-root paths (e.g., `scripts/X.py`) in SKILL.md instructions.

#### Scenario: SKILL.md has no repo-root script paths
- **GIVEN** any SKILL.md file under `skills/`
- **WHEN** scanned for path references
- **THEN** no references matching `scripts/<name>.py` without `<skill-base-dir>` prefix SHALL be found

### Requirement: Sibling-Relative Python Imports

Python scripts that import from other skill packages MUST use sibling-relative `sys.path` resolution, not repo-root-relative.

#### Scenario: Python cross-skill import
- **GIVEN** a Python script in `skills/<skill-a>/scripts/` that imports from `skills/<skill-b>/scripts/`
- **WHEN** the `sys.path` manipulation is evaluated
- **THEN** the path MUST resolve relative to the script location via `Path(__file__).parent.parent.parent / "<skill-b>" / "scripts"`

### Requirement: Infrastructure Skills Are Synced

`install.sh` MUST sync infrastructure skills alongside SDLC skills to all agent runtimes.

#### Scenario: install.sh syncs infrastructure skills
- **GIVEN** infrastructure skill directories exist under `skills/`
- **WHEN** `install.sh` is executed
- **THEN** infrastructure skills MUST appear in `.claude/skills/`, `.codex/skills/`, and `.gemini/skills/`

### Requirement: Source Script Sync

`install.sh` MUST copy source scripts from `scripts/` into infrastructure skill directories before syncing to agents.

#### Scenario: Source scripts are synced to infra skill
- **GIVEN** `scripts/worktree.py` exists as the source of truth
- **WHEN** `install.sh` is executed
- **THEN** `skills/worktree/scripts/worktree.py` MUST be updated to match the source

### Requirement: Cross-Repo Portability

Skills MUST function correctly when synced to a directory with no `scripts/` at the repo root.

#### Scenario: Skill works without repo-root scripts
- **GIVEN** skills are synced to a fresh directory via `install.sh`
- **AND** the target directory has no `scripts/` at root level
- **WHEN** a skill that depends on `worktree.py` is invoked
- **THEN** it MUST resolve the script via sibling-relative path from the infrastructure skill

### Requirement: Review Dispatcher Protocol

The system SHALL provide a `ReviewDispatcher` that can invoke review skills on different AI vendor CLIs (Claude, Codex, Gemini).

#### Scenario: Dispatch review to Codex

- GIVEN a completed implementation package
- WHEN the orchestrator dispatches a review to Codex
- THEN the Codex CLI is invoked with the review skill prompt and artifact paths
- AND a structured findings JSON file is produced at the expected output path

### Requirement: Reviewer Discovery via Coordinator

The `ReviewDispatcher` SHALL discover available reviewers via coordinator `discover_agents()` when the coordinator is available.

#### Scenario: Discover available reviewers

- GIVEN the coordinator is running and agents are registered
- WHEN the dispatcher calls `discover_agents(capability="review")`
- THEN it receives a list of agents with review capability and their vendor types

### Requirement: Reviewer Discovery Fallback

The `ReviewDispatcher` SHALL fall back to binary detection (`which codex`, `which gemini`) when the coordinator is unavailable.

#### Scenario: Discover reviewers without coordinator

- GIVEN the coordinator is unavailable
- WHEN the dispatcher attempts to discover reviewers
- THEN it checks for CLI binaries on PATH via `which`
- AND returns available vendors based on binary presence

### Requirement: Vendor Diversity

The `ReviewDispatcher` SHALL dispatch reviews to at least one vendor different from the implementing agent when multiple vendors are available.

#### Scenario: Ensure vendor diversity

- GIVEN Claude is the implementing agent and Codex and Gemini are available
- WHEN the dispatcher selects reviewers
- THEN at least one of Codex or Gemini is selected as a reviewer

### Requirement: Parallel Review Dispatch

The `ReviewDispatcher` SHALL execute vendor reviews in parallel (concurrent subprocess invocation).

#### Scenario: Parallel dispatch to multiple vendors

- GIVEN Codex and Gemini are both available
- WHEN the dispatcher dispatches reviews
- THEN both vendor subprocesses are started concurrently
- AND results are collected as each completes

### Requirement: Config-Driven Generic Adapter

A single `CliVendorAdapter` class SHALL handle all vendors, parameterized by CLI configuration from `agents.yaml`. There SHALL NOT be per-vendor adapter subclasses.

#### Scenario: Adapter constructed from config

- GIVEN agents.yaml contains a `cli` section for `codex-local` with `command: codex` and dispatch modes
- WHEN the ReviewOrchestrator loads agent config
- THEN it creates a `CliVendorAdapter` instance for `codex-local` using the config
- AND `dispatch_review()` returns a `DispatchResult` with vendor, process handle, output path, and timing

### Requirement: Vendor Timeout Enforcement

The `ReviewDispatcher` SHALL enforce a configurable per-vendor timeout (default: 300 seconds) and terminate timed-out processes.

#### Scenario: Vendor times out

- GIVEN a vendor review is dispatched with a 300-second timeout
- WHEN the vendor process exceeds the timeout
- THEN the process is terminated
- AND the result is marked as timed out with an error message

### Requirement: Consensus Synthesizer

The system SHALL provide a `ConsensusSynthesizer` that merges findings from multiple vendor review outputs.

#### Scenario: Synthesize findings from two vendors

- GIVEN findings JSON from Codex and Gemini for the same package
- WHEN the synthesizer processes both
- THEN it produces a consensus report with matched and unmatched findings

### Requirement: Cross-Vendor Finding Matching

Findings SHALL be matched across vendors using file location, finding type, and description similarity.

#### Scenario: Match identical findings

- GIVEN Codex finding: security issue at `src/api.py:42`
- AND Gemini finding: security issue at `src/api.py:42`
- WHEN the matching algorithm runs
- THEN the findings are matched with high confidence (score >= 0.8)

### Requirement: Confirmed Finding Classification

A finding confirmed by 2+ vendors SHALL be classified as `confirmed` in the consensus report.

#### Scenario: Two vendors agree on finding

- GIVEN matching findings from Codex and Gemini
- WHEN consensus is computed
- THEN the finding status is `confirmed`

### Requirement: Unconfirmed Finding Classification

A finding reported by only one vendor SHALL be classified as `unconfirmed` in the consensus report.

#### Scenario: Single vendor finding

- GIVEN a finding from Codex with no match from Gemini
- WHEN consensus is computed
- THEN the finding status is `unconfirmed`

### Requirement: Disagreement Classification

When vendors disagree on disposition (e.g., `fix` vs `accept`), the finding SHALL be classified as `disagreement` and escalated.

#### Scenario: Vendors disagree on disposition

- GIVEN Codex says disposition=`fix` and Gemini says disposition=`accept` for matched findings
- WHEN consensus is computed
- THEN the finding status is `disagreement`
- AND the recommended disposition is `escalate`

### Requirement: Consensus Report Schema Conformance

The consensus report SHALL conform to `openspec/schemas/consensus-report.schema.json`.

#### Scenario: Valid consensus report

- GIVEN synthesized consensus findings
- WHEN the report is generated
- THEN it validates against the consensus-report JSON schema

### Requirement: Integration Gate Uses Consensus

The integration gate SHALL use consensus findings: `confirmed` findings with disposition `fix` SHALL block integration.

#### Scenario: Confirmed fix finding blocks gate

- GIVEN a consensus report with a confirmed finding (disposition=`fix`)
- WHEN the integration gate checks
- THEN the gate returns BLOCKED_FIX

### Requirement: Unconfirmed Findings Warn Only

`Unconfirmed` findings SHALL generate warnings but SHALL NOT block integration.

#### Scenario: Unconfirmed finding passes gate

- GIVEN a consensus report with only unconfirmed findings
- WHEN the integration gate checks
- THEN the gate returns PASS with warnings

### Requirement: Disagreement Findings Escalate

`Disagreement` findings SHALL trigger escalation (BLOCKED_ESCALATE).

#### Scenario: Disagreement finding escalates

- GIVEN a consensus report with a disagreement finding
- WHEN the integration gate checks
- THEN the gate returns BLOCKED_ESCALATE

### Requirement: Quorum Reporting

The integration gate SHALL report quorum status (how many vendors reviewed vs. how many were requested).

#### Scenario: Quorum met

- GIVEN 2 vendors requested and 2 returned findings
- WHEN the consensus report is generated
- THEN `quorum_met` is true and `quorum_received` equals `quorum_requested`

### Requirement: Single Vendor Fallback

If no secondary vendors are available, the system SHALL proceed with single-vendor review and emit a warning.

#### Scenario: Only primary vendor available

- GIVEN Claude is the only available agent
- WHEN the dispatcher attempts multi-vendor review
- THEN it proceeds with Claude self-review
- AND emits a warning that vendor diversity was not achieved

### Requirement: Vendor Failure Resilience

If a vendor fails (timeout, invalid output, crash), the system SHALL skip that vendor's findings and proceed with available results.

#### Scenario: One vendor fails

- GIVEN Codex and Gemini are dispatched
- AND Codex times out
- WHEN results are collected
- THEN Gemini's findings are used alone
- AND the consensus report notes Codex's failure

### Requirement: Total Failure Warning

If all vendor dispatches fail, the system SHALL emit a warning and require manual human review before integration.

#### Scenario: All vendors fail

- GIVEN Codex and Gemini are both dispatched
- AND both fail
- WHEN results are collected
- THEN the system emits a warning requiring manual review
- AND the integration gate returns BLOCKED_ESCALATE

### Requirement: Dispatch Modes from Config

Dispatch modes and their CLI args SHALL be read from `agents.yaml` under `cli.dispatch_modes`. The adapter SHALL NOT hardcode CLI flags for any vendor.

#### Scenario: Review mode reads args from config

- GIVEN agents.yaml contains `codex-local.cli.dispatch_modes.review.args: [exec, -s, read-only]`
- WHEN the adapter builds the command for review mode
- THEN the command is `["codex", "exec", "-s", "read-only", "<prompt>"]`

#### Scenario: Alternative mode reads args from config

- GIVEN agents.yaml contains `gemini-local.cli.dispatch_modes.alternative.args: [--approval-mode, yolo]`
- WHEN the adapter builds the command for alternative mode
- THEN the command is `["gemini", "--approval-mode", "yolo", "<prompt>"]`

### Requirement: CLI Configuration Schema

Each agent entry in `agents.yaml` SHALL support an optional `cli` section with: `command` (binary name), `dispatch_modes` (map of mode name to args list), `model_flag` (flag syntax for model override), `model` (primary model or null), and `model_fallbacks` (ordered fallback list).

#### Scenario: Agent with no cli section

- GIVEN an agent entry in agents.yaml without a `cli` section
- WHEN the ReviewOrchestrator loads agent config
- THEN no adapter is created for that agent
- AND the agent is excluded from CLI dispatch (may still be available via other transports)

### Requirement: Non-Interactive Execution Guarantee

The `cli.dispatch_modes` config for each agent SHALL include non-interactive flags. The adapter enforces a hard timeout on every subprocess to catch misconfigured modes.

#### Scenario: Timeout kills hung process

- GIVEN a vendor process is dispatched with a 300-second timeout
- WHEN the process does not complete within 300 seconds
- THEN the dispatcher kills the process
- AND marks the result as timed out

### Requirement: Adapter Capability Check

The `CliVendorAdapter` SHALL implement a `can_dispatch(mode)` method that verifies: (1) the CLI binary exists on PATH, (2) the requested dispatch mode exists in `cli.dispatch_modes`.

#### Scenario: Missing CLI binary detected

- GIVEN the `codex` binary is not on PATH
- WHEN the adapter's `can_dispatch("review")` is called
- THEN it returns False
- AND the dispatcher skips this agent and proceeds with others

#### Scenario: Missing dispatch mode

- GIVEN an agent's cli config has no `alternative` dispatch mode
- WHEN `can_dispatch("alternative")` is called
- THEN it returns False

### Requirement: Model Fallback on Capacity Errors

When a vendor returns a 429 / MODEL_CAPACITY_EXHAUSTED error, the adapter SHALL retry with fallback models from the agent's `model_fallbacks` list in `agents.yaml` before marking the vendor as failed.

#### Scenario: Primary model exhausted, fallback succeeds

- GIVEN Gemini's configured model_fallbacks are `[gemini-2.5-pro, gemini-2.5-flash]`
- AND the primary model returns 429 RESOURCE_EXHAUSTED
- WHEN the adapter detects the capacity error in stderr
- THEN it retries with `-m gemini-2.5-pro` as the first fallback
- AND if the fallback succeeds, the findings are used normally

#### Scenario: All models exhausted

- GIVEN both primary and all fallback models return 429
- WHEN the adapter exhausts the fallback chain
- THEN the vendor is marked as failed with error details listing all models attempted
- AND the dispatcher proceeds with other available vendors

#### Scenario: No fallbacks configured

- GIVEN an agent entry with an empty `model_fallbacks` list
- WHEN the primary model returns 429
- THEN the vendor is marked as failed immediately (no retry)

### Requirement: Configurable Model Fallback Chains

Model fallback chains SHALL be configured per-agent in `agents.yaml` via `model` (primary, null for CLI default) and `model_fallbacks` (ordered list of fallback model names) fields. The adapter SHALL NOT hardcode model names.

#### Scenario: Read fallback config from agents.yaml

- GIVEN agents.yaml contains `model_fallbacks: [gemini-2.5-pro, gemini-2.5-flash]` for gemini-local
- WHEN the Gemini adapter initializes
- THEN it loads the fallback chain from the agent configuration
- AND uses these models in order when the primary model fails

### Requirement: Auth Error Surfacing

When a vendor fails due to authentication issues (expired token, missing login), the adapter SHALL surface a clear, actionable error message to the user with the vendor-specific re-login command.

#### Scenario: Gemini auth expired

- GIVEN Gemini returns a 401 UNAUTHENTICATED error
- WHEN the adapter parses the stderr
- THEN it prints a user-facing warning: "Gemini auth expired. Run: gemini login"
- AND the vendor is marked as failed (no retry, no fallback)

#### Scenario: Codex login required

- GIVEN Codex returns a login-required error
- WHEN the adapter parses the stderr
- THEN it prints a user-facing warning: "Codex login required. Run: codex login"
- AND the vendor is marked as failed (no retry, no fallback)

### Requirement: Review Manifest Generation

The review dispatcher SHALL produce a `reviews/review-manifest.json` file capturing dispatch metadata: which vendors were requested, which responded, timing, model used, quorum status, and error summaries for failed vendors.

#### Scenario: Manifest after mixed success

- GIVEN Codex review succeeded and Gemini review failed with 429
- WHEN the dispatcher completes
- THEN `reviews/review-manifest.json` contains entries for both vendors
- AND the Codex entry shows success=true with findings_count and elapsed_seconds
- AND the Gemini entry shows success=false with error_class="capacity_exhausted" and the models attempted

### Requirement: Auto Dev Loop Skill

The system SHALL provide an `/auto-dev-loop` skill that orchestrates the full plan-review-implement-validate-PR lifecycle as a state machine. The skill SHALL accept either a `change-id` (existing proposal) or a feature description (creates proposal first via `/parallel-plan-feature` or `/linear-plan-feature`).

#### Scenario: Invoke with existing change-id

- **WHEN** the user invokes `/auto-dev-loop test-feature`
- **THEN** the system SHALL load the proposal artifacts and begin the state machine at INIT phase

#### Scenario: Invoke with feature description

- **WHEN** the user invokes `/auto-dev-loop "add user authentication"`
- **THEN** the system SHALL delegate to `/parallel-plan-feature` (or `/linear-plan-feature` if coordinator unavailable) to create proposal artifacts
- **AND** transition to PLAN_REVIEW once artifacts exist

### Requirement: State Machine Phases

The state machine SHALL support phases: INIT, PLAN, PLAN_REVIEW, PLAN_FIX, IMPLEMENT, IMPL_REVIEW, IMPL_FIX, VALIDATE, VAL_REVIEW (optional), VAL_FIX, SUBMIT_PR, DONE, ESCALATE. The state machine SHALL persist its state to `loop-state.json` after every state transition, enabling resumability.

#### Scenario: Normal phase progression (simple feature)

- **GIVEN** a simple feature with no review findings and no complexity checkpoints
- **WHEN** the loop runs to completion
- **THEN** phases SHALL progress: INIT -> PLAN -> PLAN_REVIEW -> IMPLEMENT -> IMPL_REVIEW -> VALIDATE -> SUBMIT_PR -> DONE

#### Scenario: Phase progression with fixes needed

- **GIVEN** a feature where plan review finds medium-severity issues
- **WHEN** the loop processes plan review
- **THEN** phases SHALL progress: PLAN_REVIEW -> PLAN_FIX -> PLAN_REVIEW (re-review)

#### Scenario: Resume after interruption

- **GIVEN** the loop was interrupted during IMPL_REVIEW phase at iteration 2
- **WHEN** the loop is re-invoked with the same change-id
- **THEN** the system SHALL load state from `loop-state.json` and resume from IMPL_REVIEW iteration 2

#### Scenario: Complex feature with VAL_REVIEW

- **GIVEN** a feature that triggered complexity gate checkpoints (e.g., database migrations)
- **WHEN** validation passes
- **THEN** phases SHALL include VAL_REVIEW before SUBMIT_PR

### Requirement: Review Convergence Loop

The convergence loop SHALL dispatch reviews to all available vendors via `ReviewOrchestrator.dispatch_and_wait()`, synthesize findings via `ConsensusSynthesizer.synthesize()`, and exit when no confirmed or unconfirmed findings at medium or higher severity remain AND quorum is met. The loop SHALL enforce a maximum iteration cap (default 3 rounds per phase).

#### Scenario: Multi-vendor review dispatch

- **GIVEN** 3 vendors are available (claude, codex, gemini)
- **WHEN** a convergence review round begins
- **THEN** the system SHALL dispatch review requests to all 3 vendors

#### Scenario: Convergence achieved with quorum

- **GIVEN** consensus shows 3 low-severity findings and 0 medium+ findings
- **AND** at least 2 vendors returned valid results
- **WHEN** the exit condition is checked
- **THEN** convergence SHALL be declared and the loop SHALL advance to the next phase

#### Scenario: Convergence blocked by insufficient quorum

- **GIVEN** only 1 vendor returned valid results with 0 findings
- **WHEN** the exit condition is checked
- **THEN** convergence SHALL NOT be declared
- **AND** the system SHALL pause with reason "quorum_lost"

#### Scenario: Max iterations reached

- **GIVEN** the plan review has run 3 rounds without convergence
- **WHEN** the 3rd round completes with remaining medium+ findings
- **THEN** the system SHALL transition to ESCALATE state

### Requirement: Finding Trend Tracking and Stall Detection

The convergence loop SHALL track finding counts per round and escalate if findings are not decreasing over a 3-round sliding window (i.e., count at round N >= count at round N-2). Unconfirmed findings (single-vendor, medium+) SHALL block in rounds 1 through N-1 but SHALL NOT block in the final round. Findings with `disagreement` status SHALL always trigger escalation.

#### Scenario: Decreasing trend continues (no stall)

- **GIVEN** round 1 has 10 blocking findings, round 2 has 5, and round 3 has 6
- **WHEN** trend analysis runs after round 3
- **THEN** the system SHALL NOT escalate because round 3 count (6) < round 1 count (10)

#### Scenario: Flat trend triggers stall

- **GIVEN** round 1 has 5 blocking findings, round 2 has 5, and round 3 has 5
- **WHEN** trend analysis runs after round 3
- **THEN** the system SHALL escalate because round 3 count (5) >= round 1 count (5)

#### Scenario: Unconfirmed finding in final round

- **GIVEN** a single-vendor medium-severity finding in round 3 (final round)
- **WHEN** the exit condition is checked
- **THEN** the finding SHALL NOT block convergence

#### Scenario: Vendor disagreement

- **GIVEN** claude recommends "fix" and codex recommends "accept" for the same finding
- **WHEN** consensus synthesis classifies this as "disagreement"
- **THEN** the system SHALL transition to ESCALATE state

### Requirement: Fix Dispatch

Fix dispatch SHALL differ by phase:
- **PLAN_FIX**: The conductor SHALL apply fixes **inline** (directly editing plan artifacts) since it already has full context. No CLI subprocess dispatch.
- **IMPL_FIX**: Fixes SHALL be dispatched to the **recorded lead vendor** for the package (stored in `LoopState.package_authors`), scoped to the package's `write_allow` paths. Post-fix verification SHALL reject edits outside declared scope.
- **VAL_FIX**: Fixes SHALL be applied inline for configuration/test changes, or targeted to the relevant package's author for code changes.

#### Scenario: Plan fix applied inline

- **GIVEN** plan review found 2 medium-severity confirmed findings in design.md
- **WHEN** fix dispatch runs
- **THEN** the conductor SHALL edit design.md directly and re-validate with `openspec validate`

#### Scenario: Implementation fix targeted to lead vendor

- **GIVEN** implementation review found a medium-severity finding in wp-api authored by codex
- **WHEN** fix dispatch runs
- **THEN** the system SHALL dispatch the fix to codex in alternative mode, scoped to wp-api's write_allow paths

#### Scenario: Fix scope enforcement

- **GIVEN** a fix dispatch to wp-api with write_allow of `["src/api/**"]`
- **WHEN** the fix modifies `src/frontend/app.tsx`
- **THEN** the system SHALL reject the fix as a scope violation

### Requirement: Implementation Strategy Selection

The system SHALL select an implementation strategy per work package: `alternatives` (3 independent implementations + synthesis) or `lead_review` (1 implements + others review). Selection SHALL consume structured metadata from `work-packages.yaml` (`metadata.loc_estimate`, `metadata.alternatives_count`, `metadata.package_kind`) when available, falling back to description inference.

#### Scenario: Small ambiguous package with metadata

- **GIVEN** a package with metadata `loc_estimate: 100, alternatives_count: 3, package_kind: algorithm`
- **WHEN** strategy selection runs with 3 vendors available
- **THEN** the strategy SHALL be "alternatives"

#### Scenario: Large straightforward package

- **GIVEN** a package with metadata `loc_estimate: 400, alternatives_count: 0, package_kind: crud`
- **WHEN** strategy selection runs
- **THEN** the strategy SHALL be "lead_review"

#### Scenario: Fallback when metadata absent

- **GIVEN** a package without metadata fields
- **WHEN** strategy selection runs
- **THEN** the strategy SHALL default to "lead_review"

### Requirement: Complexity Gate

The system SHALL assess feature complexity at INIT phase. Thresholds SHALL be configurable via `work-packages.yaml` defaults (`defaults.auto_loop.max_loc`, etc.) with built-in defaults (LOC > 500, packages > 4, external deps > 2). Features exceeding thresholds SHALL require `--force` or inject manual review checkpoints (including enabling VAL_REVIEW). Features touching database migrations or security-sensitive paths SHALL inject checkpoints regardless.

#### Scenario: Simple feature passes

- **GIVEN** a feature with 200 LOC, 2 packages, 0 external deps
- **WHEN** complexity gate runs
- **THEN** the gate SHALL pass without warnings and VAL_REVIEW SHALL be skipped

#### Scenario: Complex feature with checkpoints

- **GIVEN** a feature with 800 LOC and 6 packages without --force
- **WHEN** complexity gate runs
- **THEN** the gate SHALL reject with a warning listing exceeded thresholds

#### Scenario: Database migration enables VAL_REVIEW

- **GIVEN** a feature with 200 LOC but includes a database migration
- **WHEN** complexity gate runs
- **THEN** the gate SHALL pass but inject VAL_REVIEW as a checkpoint

#### Scenario: Custom thresholds from work-packages.yaml

- **GIVEN** work-packages.yaml contains `defaults.auto_loop.max_loc: 1000`
- **WHEN** complexity gate evaluates a 700 LOC feature
- **THEN** the gate SHALL pass (below custom threshold)

### Requirement: Memory and Handoff Integration

The system SHALL write coordinator episodic memory (via `remember(event_type, summary, details, tags)`) at each convergence round, storing the returned `memory_id` in `LoopState.memory_ids`. The system SHALL write handoff documents at each major state transition. At completion, the system SHALL write strategic memory summarizing vendor effectiveness and convergence patterns.

#### Scenario: Episodic memory at convergence round

- **GIVEN** a convergence round completes with 3 findings and 75% vendor agreement
- **WHEN** the round ends
- **THEN** a memory entry SHALL be written with event_type="convergence_round" and tags including the change-id and phase

#### Scenario: Handoff at phase boundary

- **GIVEN** plan review converges
- **WHEN** transitioning to IMPLEMENT
- **THEN** a handoff document SHALL be written with summary, decisions, and implementation context

#### Scenario: Strategic memory at completion

- **GIVEN** the loop completes successfully
- **WHEN** entering DONE state
- **THEN** a memory entry SHALL be written with event_type="loop_completion" including vendor effectiveness stats

### Requirement: ESCALATE Resolution Protocol

When entering ESCALATE, the system SHALL persist `previous_phase` and `escalation_reason` in `LoopState`, write a diagnostic handoff, and exit. On re-invocation, the system SHALL detect ESCALATE state, re-evaluate the escalation condition, and transition to `previous_phase` if resolved.

#### Scenario: Escalation and resume

- **GIVEN** the loop escalated during IMPL_REVIEW due to vendor disagreement
- **AND** the human manually resolved the disagreement
- **WHEN** the human re-invokes `/auto-dev-loop <change-id>`
- **THEN** the system SHALL load state, detect ESCALATE, re-run IMPL_REVIEW gate check
- **AND** transition to IMPL_REVIEW if the disagreement is resolved

#### Scenario: Escalation not yet resolved

- **GIVEN** the loop escalated and the human re-invokes without fixing the issue
- **WHEN** the system re-evaluates the escalation condition
- **THEN** the system SHALL remain in ESCALATE with updated diagnostic

### Requirement: Graceful Degradation

If coordinator unavailable, the system SHALL fall back to linear workflow. If a vendor drops mid-loop, the system SHALL continue with reduced quorum (minimum 2 for convergence). If quorum drops below 2, the system SHALL pause with reason "quorum_lost" and alert.

#### Scenario: No coordinator

- **GIVEN** coordinator health check returns unavailable
- **WHEN** `/auto-dev-loop` is invoked
- **THEN** the system SHALL emit a warning and delegate to sequential skill invocation

#### Scenario: Vendor drops mid-loop

- **GIVEN** 3 vendors at PLAN_REVIEW but only 2 at IMPL_REVIEW
- **WHEN** the convergence loop dispatches reviews
- **THEN** the system SHALL continue with 2-vendor quorum and log a warning

### Requirement: Convergence State Schema

The convergence state SHALL conform to `convergence-state.schema.json` including: current_phase, iteration, max_iterations, findings_trend, blocking_findings, vendor_availability, packages_status, package_authors, implementation_strategy, memory_ids, handoff_ids, timestamps, previous_phase, escalation_reason, and error.

#### Scenario: State validates

- **GIVEN** a loop-state.json file produced by the state machine
- **WHEN** validated against convergence-state.schema.json
- **THEN** validation SHALL pass

### Requirement: Session Log Artifact

The system SHALL provide a `session-log.md` artifact that captures a structured summary of the agent conversation/session history for each OpenSpec change. The artifact SHALL focus on decision rationale, trade-offs, alternatives considered, and key discussion points — not on replicating code diffs already stored in git.

#### Scenario: Session log generated during cleanup
- **WHEN** `/cleanup-feature <change-id>` or `/linear-cleanup-feature <change-id>` executes
- **AND** agent session context is available (conversation history, handoff documents, or session transcript)
- **THEN** the skill SHALL generate `openspec/changes/<change-id>/session-log.md`
- **AND** the artifact SHALL contain structured sections: Summary, Key Decisions, Alternatives Considered, Trade-offs, Open Questions, and Session Metadata

#### Scenario: Session log generated during parallel cleanup
- **WHEN** `/parallel-cleanup-feature <change-id>` executes
- **AND** multiple agent sessions contributed to the change
- **THEN** the skill SHALL generate a consolidated `session-log.md` combining context from all contributing agent sessions
- **AND** each entry SHALL identify the originating agent/session

#### Scenario: No session context available
- **WHEN** cleanup executes but no agent session context is accessible (e.g., session expired, agent type doesn't support history export)
- **THEN** the skill SHALL skip session log generation with an informational message
- **AND** cleanup SHALL proceed without error

#### Scenario: Session log is optional
- **WHEN** a change is archived without a `session-log.md`
- **THEN** OpenSpec validation SHALL NOT report an error
- **AND** the change SHALL be considered complete

### Requirement: Session Log Content Structure

The `session-log.md` artifact SHALL follow a structured format with the following sections:

- **Summary**: 2-3 sentence overview of what was discussed and decided during the session(s)
- **Key Decisions**: Numbered list of significant decisions with brief rationale for each
- **Alternatives Considered**: For each key decision, alternatives that were discussed and why they were rejected
- **Trade-offs**: Explicit trade-offs accepted in the implementation (e.g., "chose simplicity over performance because...")
- **Open Questions**: Unresolved questions or concerns raised during the session that may need future attention
- **Session Metadata**: Agent type, session ID(s), date range, number of interactions

#### Scenario: Content focuses on rationale not code
- **WHEN** the session log is generated
- **THEN** it SHALL NOT include raw code blocks, full file contents, or diff output
- **AND** it SHALL reference files by path when relevant context requires it
- **AND** it SHALL focus on the reasoning behind decisions, not the mechanical steps taken

#### Scenario: Content is concise
- **WHEN** the session log is generated from a long conversation
- **THEN** the artifact SHALL be a summarized distillation, not a full transcript
- **AND** the total length SHOULD NOT exceed 500 lines

### Requirement: Session Log Sanitization

All session log content SHALL be sanitized before being committed to git to prevent accidental exposure of secrets or sensitive information.

#### Scenario: Secrets detected and redacted
- **WHEN** the session log content contains patterns matching known secret formats (API keys, tokens, passwords, connection strings, private keys, AWS credentials, environment variable values)
- **THEN** the sanitization script SHALL replace each detected secret with `[REDACTED:<type>]` (e.g., `[REDACTED:api-key]`, `[REDACTED:password]`)
- **AND** SHALL log a warning indicating the number and types of redactions performed

#### Scenario: High-entropy strings detected
- **WHEN** the session log content contains strings with high Shannon entropy (>4.5 bits/char) that are longer than 20 characters and not obviously code identifiers
- **THEN** the sanitization script SHALL flag them for review
- **AND** SHALL redact them by default with `[REDACTED:high-entropy]`

#### Scenario: Environment-specific paths redacted
- **WHEN** the session log contains user home directory paths, absolute system paths, or hostnames that could reveal infrastructure details
- **THEN** the sanitization script SHALL normalize them (e.g., `/home/user/...` → `~/.../`, hostnames → `[HOST]`)

#### Scenario: Sanitization script exit codes
- **WHEN** the sanitization script runs
- **THEN** it SHALL exit 0 if no secrets were found or all were successfully redacted
- **AND** it SHALL exit 1 if sanitization encountered an error that could allow secrets through
- **AND** cleanup SHALL abort committing the session log if the script exits non-zero

#### Scenario: No false positives on common patterns
- **WHEN** the session log contains UUIDs, git SHAs, OpenSpec change-ids, or file paths
- **THEN** these SHALL NOT be redacted as they are common development identifiers

### Requirement: Session Log Extraction

The system SHALL support extracting session context from multiple agent types using a provider-agnostic approach.

#### Scenario: Claude Code session extraction
- **WHEN** the active agent is Claude Code
- **THEN** the extraction script SHALL attempt to read the session transcript from Claude Code's local session storage
- **AND** SHALL extract key decisions, user confirmations, and rationale discussions
- **AND** SHALL summarize the conversation into the structured session-log format

#### Scenario: Handoff documents as fallback source
- **WHEN** direct session transcript access is not available
- **AND** `CAN_HANDOFF=true` and handoff documents exist for the change
- **THEN** the extraction script SHALL compile session context from handoff document history (summary, decisions, completed_work fields)
- **AND** SHALL note in Session Metadata that the log was derived from handoff documents

#### Scenario: Manual session log
- **WHEN** automated extraction is not possible (unsupported agent type, no handoff documents)
- **THEN** the cleanup skill SHALL prompt the agent to generate a session log from its current context window
- **AND** the agent SHALL produce the structured summary from its available conversation memory

### Requirement: Cleanup Skill Session Log Integration

The cleanup skills SHALL integrate session log generation as a step before archiving.

#### Scenario: Linear cleanup generates session log
- **WHEN** `/linear-cleanup-feature <change-id>` reaches the archive step
- **THEN** it SHALL first attempt to generate `session-log.md` via the extraction and sanitization pipeline
- **AND** SHALL commit the session log with the archive commit
- **AND** the session log SHALL be included in the archived change directory

#### Scenario: Parallel cleanup consolidates session logs
- **WHEN** `/parallel-cleanup-feature <change-id>` reaches the archive step
- **AND** multiple agent worktrees contributed to the implementation
- **THEN** it SHALL collect session context from each agent's handoff documents
- **AND** consolidate into a single `session-log.md` with per-agent sections
- **AND** commit and archive as with linear cleanup

#### Scenario: Session log generation failure does not block cleanup
- **WHEN** session log generation or sanitization fails
- **THEN** the cleanup skill SHALL log a warning
- **AND** SHALL proceed with archive without the session log
- **AND** SHALL NOT retry or block the cleanup workflow

### Requirement: Bug-scrub parallel collector execution

Bug-scrub SHALL support a `--parallel` CLI flag that runs all selected collectors concurrently using `concurrent.futures.ThreadPoolExecutor`. When `--parallel` is set, bug-scrub SHALL accept `--max-workers <N>` to limit concurrency (default: number of selected sources, max 8). Parallel collector execution SHALL produce results in the same order as the source list (deterministic output). If any collector raises an exception during parallel execution, bug-scrub SHALL record a `SourceResult` with `status="error"` and continue collecting from remaining sources. Parallel mode SHALL produce reports with identical findings, ordering, and source statuses as sequential mode (transient fields `timestamp` and `duration_ms` are excluded from equivalence).

#### Scenario: parallel flag runs collectors concurrently
- GIVEN bug-scrub is invoked with `--parallel`
- WHEN the collection phase executes
- THEN all selected collectors run via ThreadPoolExecutor
- AND results are collected in submission order

#### Scenario: max-workers limits concurrency
- GIVEN bug-scrub is invoked with `--parallel --max-workers 4` and 8 sources selected
- WHEN collectors execute
- THEN at most 4 collectors run concurrently

#### Scenario: failed collector does not abort others
- GIVEN the mypy collector raises an exception during parallel execution
- WHEN all futures resolve
- THEN a SourceResult(source="mypy", status="error") is included in results
- AND all other collectors complete normally

#### Scenario: collector exceeds timeout
- GIVEN a collector exceeds the per-collector timeout (default 300s)
- WHEN parallel mode is active
- THEN the collector returns SourceResult(status="error") with a timeout message
- AND remaining collectors continue

#### Scenario: normalized equivalence between modes
- GIVEN a project with known findings
- WHEN bug-scrub runs sequentially and then with `--parallel`
- THEN both runs produce identical findings, ordering, and source statuses
- AND transient fields (timestamp, duration_ms) are excluded from comparison

### Requirement: Fix-scrub parallel auto-fix and verification

Fix-scrub SHALL support a `--parallel` CLI flag that runs auto-fix groups and verification checks concurrently. Parallel auto-fix execution SHALL only process file groups with non-overlapping `file_path` sets concurrently. Fix-scrub `plan_fixes()` SHALL assert non-overlap of file paths across auto-fix groups when parallel mode is requested. Parallel verification SHALL run pytest, mypy, ruff, and openspec concurrently using `concurrent.futures.ThreadPoolExecutor`. Parallel verification SHALL collect all results before reporting (no fail-fast). The `verify_parallel()` function SHALL accept the same `original_failures: dict[str, set[str]] | None` parameter as the existing `verify()` function to preserve regression-delta behavior.

#### Scenario: parallel auto-fix on non-overlapping groups
- GIVEN fix-scrub is invoked with `--parallel`
- AND auto-fix groups have non-overlapping file paths
- WHEN auto-fix executes
- THEN non-overlapping groups run concurrently via ThreadPoolExecutor

#### Scenario: overlapping groups prevented
- GIVEN a FixPlan has two auto_groups with overlapping file_paths
- WHEN parallel mode validates the plan
- THEN an AssertionError is raised with a descriptive message

#### Scenario: parallel verification runs all checks concurrently
- GIVEN fix-scrub runs with `--parallel`
- WHEN the verification phase executes
- THEN pytest, mypy, ruff, and openspec run as concurrent futures
- AND all results are collected before the VerificationResult is assembled

#### Scenario: failed check does not abort others
- GIVEN pytest fails during parallel verification
- WHEN all checks complete
- THEN the VerificationResult includes results from all 4 tools

#### Scenario: parallel verify preserves regression detection
- GIVEN fix-scrub runs with `--parallel` and original_failures provided
- WHEN a tool reports new failures not in original_failures
- THEN those are included in VerificationResult.regressions

### Requirement: Multi-vendor agent dispatch for fix-scrub

Fix-scrub SHALL support a `--vendors` CLI flag accepting a comma-separated list of vendor names for agent-tier dispatch. When `--vendors` is set, fix-scrub SHALL assign each file-group prompt to exactly one vendor using round-robin distribution, maintaining exclusive file ownership. Multi-vendor dispatch SHALL generate vendor-specific prompt files (`agent-fix-prompts-<vendor>.json`) for SKILL.md consumption. Vendor discovery SHALL use `ReviewOrchestrator.from_coordinator()` with fallback to `from_agents_yaml()`. If a specified vendor is unavailable, fix-scrub SHALL skip it and redistribute its file-groups to remaining vendors with a warning.

#### Scenario: vendors flag routes to specified vendors
- GIVEN fix-scrub is invoked with `--vendors claude,codex`
- WHEN agent-tier prompts are generated for 4 file-groups
- THEN file-groups are assigned round-robin: claude gets groups 0,2 and codex gets groups 1,3

#### Scenario: exclusive file ownership maintained
- GIVEN fix-scrub is invoked with `--vendors claude,codex`
- WHEN vendor routing executes
- THEN each file-group is assigned to exactly one vendor
- AND no file path appears in more than one vendor's prompt file

#### Scenario: unavailable vendor redistributed
- GIVEN codex is unavailable and `--vendors claude,codex` is set
- WHEN vendor routing executes
- THEN all file-groups are assigned to claude
- AND a warning is emitted about codex being unavailable

#### Scenario: per-vendor prompt files created
- GIVEN prompts routed to claude and codex
- WHEN prompt files are written
- THEN `agent-fix-prompts-claude.json` and `agent-fix-prompts-codex.json` are created

### Requirement: Backward compatibility for scrub skills

Without `--parallel`, both skills SHALL behave identically to their current sequential implementation. Without `--vendors`, fix-scrub SHALL generate a single `agent-fix-prompts.json` as it does today. All existing CLI flags and their defaults SHALL remain unchanged. `--parallel` and `--vendors` SHALL be orthogonal — they can be used independently or together.

#### Scenario: default mode is sequential
- GIVEN bug-scrub is invoked without `--parallel`
- WHEN collection executes
- THEN collectors run sequentially in a for-loop (existing behavior)

#### Scenario: default mode is single-vendor
- GIVEN fix-scrub is invoked without `--vendors`
- WHEN agent prompts are generated
- THEN a single `agent-fix-prompts.json` file is written

#### Scenario: existing flags preserved
- GIVEN bug-scrub is invoked with `--source pytest,ruff --severity medium`
- WHEN the command executes
- THEN behavior is identical to current implementation

#### Scenario: parallel and vendors used together
- GIVEN fix-scrub is invoked with `--parallel --vendors claude,codex`
- WHEN execution runs
- THEN parallel auto-fixes execute concurrently
- AND agent prompts are routed to specified vendors per file-group

### Requirement: SDK Vendor Dispatch Adapter

The system SHALL provide a `SdkVendorAdapter` that can dispatch review prompts to vendor APIs (Anthropic, OpenAI, Google) via their Python SDKs when the vendor's CLI is not installed.

- The `SdkVendorAdapter` SHALL implement the same `dispatch()` → `ReviewResult` interface as `CliVendorAdapter`.
- The `SdkVendorAdapter` SHALL only support the `review` dispatch mode (read-only). It SHALL NOT support `alternative` mode (write access).
- The `SdkVendorAdapter` SHALL lazy-import vendor SDK packages to avoid import errors when SDKs are not installed.

#### Scenario: SDK dispatch to Anthropic API

- GIVEN the `claude` CLI is not installed
- AND an API key is resolvable for Anthropic (via OpenBao or `ANTHROPIC_API_KEY` env var)
- WHEN the dispatcher selects reviewers
- THEN it creates a `SdkVendorAdapter` for `claude-remote`
- AND dispatches the review prompt via `anthropic.Anthropic().messages.create()`
- AND parses the JSON findings from the response

#### Scenario: SDK dispatch with model fallback

- GIVEN SDK dispatch to the primary model returns a 429 (rate limit) error
- WHEN the adapter retries with the next model in `model_fallbacks`
- THEN it succeeds with the fallback model
- AND `ReviewResult.models_attempted` contains both model names

#### Scenario: SDK package not installed

- GIVEN `openai` package is not installed in the Python environment
- WHEN `SdkVendorAdapter.can_dispatch("review")` is called for an OpenAI adapter
- THEN it returns False
- AND the vendor is skipped without error

### Requirement: Three-Tier Dispatch Selection

The `ReviewOrchestrator` SHALL select reviewers using a three-tier waterfall, evaluated per vendor:

1. **Tier 1 (Local CLI)**: If the vendor's CLI binary is installed on PATH, use `CliVendorAdapter` with the `*-local` agent config.
2. **Tier 2 (SDK/API)**: If the CLI is not installed but the vendor's Python SDK is importable AND an API key is resolvable, use `SdkVendorAdapter` with the `*-remote` agent config.
3. **Tier 3 (Skip)**: If neither CLI nor SDK dispatch is available, skip this vendor silently.

- The dispatcher SHALL select at most one reviewer per vendor type (no double dispatch).
- The dispatcher SHALL log which tier was selected for each vendor.

#### Scenario: Mixed CLI and SDK dispatch

- GIVEN `claude` CLI is installed but `codex` CLI is not
- AND an OpenAI API key is resolvable for `codex-remote`
- WHEN the dispatcher selects reviewers
- THEN it selects `claude-local` via CLI (Tier 1) and `codex-remote` via SDK (Tier 2)
- AND dispatches to both vendors

#### Scenario: No vendors available

- GIVEN no vendor CLIs are installed AND no API keys are resolvable
- WHEN the dispatcher selects reviewers
- THEN it returns an empty list
- AND logs a warning

#### Scenario: CLI always preferred over SDK for same vendor

- GIVEN `claude` CLI is installed AND Anthropic API key is resolvable
- WHEN the dispatcher selects reviewers for Anthropic/Claude
- THEN it selects `claude-local` via CLI (Tier 1)
- AND does NOT also dispatch via SDK

### Requirement: API Key Resolution via OpenBao

API keys for SDK dispatch SHALL be resolved securely at runtime. Keys SHALL NOT be stored in `agents.yaml`, git history, or any committed file.

- The `ApiKeyResolver` SHALL attempt OpenBao resolution first using the agent's `openbao_role_id`.
- If OpenBao is unavailable (no `OPENBAO_ADDR` set), the resolver SHALL fall back to the environment variable specified in `sdk.api_key_env`.
- If neither source provides a key, the resolver SHALL return `None` and the vendor SHALL be skipped.
- Resolved keys SHALL be cached for the lifetime of the resolver instance to avoid repeated vault lookups within a single dispatch cycle.

#### Scenario: API key resolved from OpenBao

- GIVEN `OPENBAO_ADDR` is set and the vault contains a secret for `openbao_role_id: claude-code-web`
- WHEN the resolver attempts to resolve the Anthropic API key
- THEN it reads the secret from OpenBao and returns the API key

#### Scenario: API key fallback to environment variable

- GIVEN `OPENBAO_ADDR` is not set
- AND `ANTHROPIC_API_KEY` environment variable is set
- WHEN the resolver attempts to resolve the Anthropic API key
- THEN it returns the value of `ANTHROPIC_API_KEY`

#### Scenario: No API key available

- GIVEN `OPENBAO_ADDR` is not set AND `ANTHROPIC_API_KEY` is not set
- WHEN the resolver attempts to resolve the Anthropic API key
- THEN it returns None
- AND the dispatcher skips the Anthropic vendor

### Requirement: SDK Configuration in agents.yaml

Each agent entry in `agents.yaml` SHALL support an optional `sdk` section specifying: `package` (Python SDK package name), `method` (API method to call), `model` (primary model), `model_fallbacks` (ordered fallback list), `api_key_env` (environment variable name for fallback key resolution), and `max_tokens` (maximum response tokens).

- Agents without an `sdk` section SHALL be excluded from SDK dispatch.
- The `get_dispatch_configs()` function SHALL include `sdk` configuration in its output when present.

#### Scenario: Agent with SDK config

- GIVEN agents.yaml contains a `sdk` section for `codex-remote` with `package: openai` and `model: gpt-5.4`
- WHEN `get_dispatch_configs()` is called
- THEN the output includes the `sdk` configuration for `codex-remote`

#### Scenario: Agent without SDK config

- GIVEN agents.yaml does not contain a `sdk` section for `codex-local`
- WHEN `get_dispatch_configs()` is called
- THEN the output for `codex-local` has `sdk: null`

