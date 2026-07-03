# evaluation-framework Specification

## Purpose
TBD - created by archiving change add-evaluation-framework. Update Purpose after archive.
## Requirements
### Requirement: Evaluation Harness

The system SHALL provide an evaluation harness that orchestrates benchmark runs across configurable agent backends and coordination configurations.

The harness SHALL support:
- Loading evaluation configurations specifying tasks, agents, ablation flags, and trial count
- Running tasks through the agent-coordinator's coordination layer
- Collecting metrics from instrumented coordination primitives
- Generating structured evaluation reports

#### Scenario: Run evaluation suite
- **WHEN** user invokes the evaluation harness with a configuration specifying task tier, agent backend, and trial count
- **THEN** the harness SHALL load matching tasks from the task registry
- **AND** execute each task through the specified agent backend with coordination enabled
- **AND** collect timing, token usage, correctness, and coordination metrics per task
- **AND** aggregate results across trials with statistical measures (mean, median, confidence intervals)

#### Scenario: Run evaluation with ablation
- **WHEN** user specifies ablation flags toggling coordination mechanisms (locking, memory, handoffs, parallelization, queue)
- **THEN** the harness SHALL run the task suite once per ablation configuration
- **AND** produce a comparison report showing the contribution of each mechanism

#### Scenario: Evaluation with external benchmark adapter
- **WHEN** user specifies an external benchmark adapter (SWE-bench, Context-Bench, MultiAgentBench)
- **THEN** the harness SHALL load tasks through the adapter
- **AND** convert external task format to internal task representation
- **AND** execute and report using the standard metrics pipeline

### Requirement: Task Suite

The system SHALL provide a suite of reproducible coding tasks organized by coordination complexity tier, sourced from both external OSS repositories (SWE-bench, open-source projects) and curated internal tasks.

Tasks SHALL be defined in YAML format with metadata including: task ID, tier (1-3), source (external/curated), description, difficulty, parallelizable subtask count, affected file list, golden patch, and test command.

#### Scenario: Load task from registry
- **WHEN** the harness queries the task registry with a tier filter
- **THEN** the registry SHALL return all tasks matching the tier
- **AND** each task SHALL include complete metadata for execution and evaluation

#### Scenario: Tier 1 isolated task execution
- **WHEN** a Tier 1 (isolated, single-file) task is executed
- **THEN** the task SHALL be completable by a single agent without coordination primitives
- **AND** the result SHALL be evaluable by running the task's test command

#### Scenario: Tier 2 parallelizable task execution
- **WHEN** a Tier 2 (parallelizable, multi-file) task is executed
- **THEN** the task's subtasks SHALL be independently executable in parallel
- **AND** the harness SHALL measure speedup factor relative to sequential execution

#### Scenario: Tier 3 coordinated task execution
- **WHEN** a Tier 3 (coordinated, dependent) task is executed
- **THEN** the task SHALL require coordination primitives (locking, ordering, handoffs) for correct completion
- **AND** the harness SHALL measure coordination overhead relative to task execution time

### Requirement: Metrics Collection

The system SHALL instrument coordination primitives to collect performance and effectiveness metrics across five categories: correctness, efficiency, parallelization, coordination, and scaling.

#### Scenario: Correctness metrics
- **WHEN** a task evaluation completes
- **THEN** the system SHALL report task pass rate (tests passing), spec compliance score, and patch match ratio against golden solution

#### Scenario: Efficiency metrics
- **WHEN** a task evaluation completes
- **THEN** the system SHALL report wall-clock time, total tokens consumed, estimated API cost, and coordination overhead percentage (time spent in lock/unlock, memory operations vs productive work)

#### Scenario: Parallelization metrics
- **WHEN** a parallelizable task is run in both parallel and sequential modes
- **THEN** the system SHALL report speedup factor, Amdahl efficiency, and merge conflict rate

#### Scenario: Coordination metrics
- **WHEN** tasks using coordination primitives complete
- **THEN** the system SHALL report lock contention rate, memory hit rate, handoff continuity score, and dead agent recovery time

#### Scenario: Scaling metrics
- **WHEN** evaluation is run with varying agent counts
- **THEN** the system SHALL report performance vs agent count curve and coordination overhead growth rate

### Requirement: Evaluation Reports

The system SHALL generate structured evaluation reports in both markdown and JSON formats.

Reports SHALL include per-task results, per-configuration summaries, ablation comparisons, and statistical significance indicators.

#### Scenario: Generate markdown report
- **WHEN** an evaluation run completes
- **THEN** the system SHALL generate a markdown report with summary tables, per-task breakdowns, and ablation comparison charts
- **AND** write the report to `evaluation/reports/`

#### Scenario: Generate JSON report
- **WHEN** an evaluation run completes
- **THEN** the system SHALL generate a machine-readable JSON report with all raw metrics and aggregated statistics
- **AND** include metadata (timestamp, configuration, agent versions, trial count)

#### Scenario: Statistical significance via effect sizes
- **WHEN** comparing metrics across configurations with multiple trials
- **THEN** the report SHALL include confidence intervals and effect sizes
- **AND** flag comparisons where confidence intervals overlap (inconclusive results)

#### Scenario: Qualitative consensus evaluation
- **WHEN** an evaluation run completes and qualitative assessment is enabled
- **THEN** the system SHALL submit task outputs to 2-3 different LLMs for independent quality assessment
- **AND** report per-judge scores, agreement rate, and consensus qualitative rating
- **AND** flag disagreements where judges diverge significantly

### Requirement: External Benchmark Adapters

The system SHALL provide adapters for integrating external benchmarks into the evaluation framework.

#### Scenario: SWE-bench Verified adapter
- **WHEN** user selects the SWE-bench adapter with optional subset size
- **THEN** the adapter SHALL load task definitions from the HuggingFace dataset `SWE-bench/SWE-bench_Verified`
- **AND** convert each task to internal format (description, repo, golden patch, test command)
- **AND** support random subset sampling for cost control

#### Scenario: Context-Bench adapter
- **WHEN** user selects the Context-Bench adapter
- **THEN** the adapter SHALL load multi-step context management tasks from Letta's evaluation framework
- **AND** map tasks to evaluate the agent-coordinator's episodic and working memory subsystems

#### Scenario: MultiAgentBench adapter
- **WHEN** user selects the MultiAgentBench/MARBLE adapter
- **THEN** the adapter SHALL load coordination scenarios
- **AND** map topology configurations to the agent-coordinator's Task() parallel execution patterns

### Requirement: Agent Backend Abstraction

The system SHALL define an `AgentBackend` protocol allowing different agent implementations to be benchmarked through a uniform interface.

#### Scenario: Agent backend submits task
- **WHEN** the harness submits a task to an agent backend
- **THEN** the backend SHALL accept task description, affected files, and coordination configuration
- **AND** return task result including output, timing, token usage, and success indicator

#### Scenario: Claude Code backend
- **WHEN** the Claude Code backend receives a task
- **THEN** it SHALL execute the task via Claude Code CLI or Task() invocation
- **AND** capture all coordination metrics from the instrumented primitives

#### Scenario: Gemini/Jules backend
- **WHEN** the Gemini/Jules backend receives a task
- **THEN** it SHALL execute the task via Gemini/Jules CLI
- **AND** return results in the standard backend result format

#### Scenario: Codex backend
- **WHEN** the Codex backend receives a task
- **THEN** it SHALL execute the task via Codex CLI
- **AND** return results in the standard backend result format

#### Scenario: Backend comparison run
- **WHEN** evaluation is configured with multiple agent backends
- **THEN** the harness SHALL run identical tasks through each backend
- **AND** produce a cross-backend comparison table in the report

### Requirement: gen-eval Phase Cli-Augmented Mode Selection

The `validate-feature --phase gen-eval` handler SHALL select between `template-only` mode (existing behavior) and `cli-augmented` mode based on the presence of supporting artifacts:

- IF a gen-eval descriptor exists at `evaluation/gen_eval/descriptors/*.yaml` AND an OpenSpec change directory exists at `openspec/changes/<change-id>/specs/`, THEN the handler MUST invoke gen-eval with `--mode cli-augmented --openspec-change <change-id>`.
- OTHERWISE the handler MUST fall back to the existing `--mode template-only --no-services` invocation.

The handler MUST preserve the existing non-blocking semantics: gen-eval failures MUST NOT halt the validate-feature pipeline.

The handler MUST log the selected mode and the rationale (which artifact was missing or present) for operator debuggability.

#### Scenario: Both artifacts present → cli-augmented

- **GIVEN** a project with `evaluation/gen_eval/descriptors/api.yaml`
- **AND** an OpenSpec change at `openspec/changes/example/specs/api/spec.md`
- **WHEN** `/validate-feature example --phase gen-eval` runs
- **THEN** the gen-eval invocation captured by the handler MUST include the literal arguments `--mode cli-augmented` and `--openspec-change example` (verifiable by inspecting the launched process's argv or by mocking subprocess.run and asserting on the call arguments)
- **AND** the handler MUST emit a log line containing the substring `mode=cli-augmented` to its stdout/stderr (exact log format is non-binding; only the substring presence is normative)

#### Scenario: Descriptor only → template-only fallback

- **GIVEN** a project with `evaluation/gen_eval/descriptors/api.yaml`
- **AND** no OpenSpec change directory for the active change-id (e.g., the change has no spec deltas)
- **WHEN** `/validate-feature <change-id> --phase gen-eval` runs
- **THEN** the gen-eval invocation captured by the handler MUST include the literal arguments `--mode template-only` and `--no-services` (verifiable by argv inspection)
- **AND** the captured argv MUST NOT include `--openspec-change` or `--mode cli-augmented`
- **AND** the handler MUST emit a log line containing the substring `mode=template-only` to its stdout/stderr

#### Scenario: No descriptor → phase skipped

- **GIVEN** a project with no `evaluation/gen_eval/descriptors/*.yaml`
- **WHEN** `/validate-feature <change-id> --phase gen-eval` runs
- **THEN** the handler MUST log "SKIP: No gen-eval descriptors found"
- **AND** the handler MUST exit the phase with status `skip` (existing behavior preserved)

#### Scenario: cli-augmented failure does not halt pipeline

- **GIVEN** the conditions of "Both artifacts present → cli-augmented"
- **AND** the gen-eval cli-augmented run exits non-zero
- **WHEN** the gen-eval phase completes
- **THEN** the validate-feature pipeline MUST continue to subsequent phases
- **AND** the validation report MUST mark the gen-eval phase as `fail` (non-blocking)

---

### Requirement: Behavioral Findings in Consensus Surface

The `consensus_synthesizer.py` script SHALL accept `findings-gen-eval.json` as a vendor-source input alongside the existing per-vendor reviewer finding files. Findings from gen-eval MUST be merged into the same `consensus.json` output as scrutiny-review findings, ranked by the existing severity/criticality rubric.

The `review-findings.schema.json` schema SHALL add `behavioral_failure` to the `type` enum so gen-eval findings validate against it.

The consensus synthesizer MUST distinguish gen-eval findings from scrutiny findings via the `vendor` or `source` metadata field, but MUST treat the two finding types uniformly when ranking and deduplicating.

The synthesizer MUST treat the absence of `findings-gen-eval.json` as not-an-error (gen-eval may legitimately not have run for a change without descriptors).

#### Scenario: Synthesizer merges gen-eval and reviewer findings

- **GIVEN** a change with `findings-claude.json` (3 scrutiny findings) and `findings-codex.json` (2 scrutiny findings)
- **AND** `findings-gen-eval.json` (4 behavioral findings, all `severity: high`)
- **WHEN** `consensus_synthesizer.py` runs against all three files
- **THEN** the emitted `consensus.json` MUST contain exactly 9 finding entries
- **AND** within the emitted ranking array, all entries MUST be ordered by `severity` (with `critical` < `high` < `medium` < `low` mapped to ascending sort order, where lower values rank first); ties broken by source-file order
- **AND** the 4 entries with `type: behavioral_failure` MUST be present in the ranking (no behavioral findings dropped)
- **AND** the synthesizer's stdout MUST contain a vendor-count line matching the regex `merged: .*claude=3.*codex=2.*gen-eval=4`

#### Scenario: behavioral_failure type validates against schema

- **GIVEN** any finding with `type: behavioral_failure` and all other required fields populated
- **WHEN** the finding is validated against `openspec/schemas/review-findings.schema.json`
- **THEN** validation MUST succeed

#### Scenario: Missing gen-eval findings file is not an error

- **GIVEN** scrutiny finding files exist but no `findings-gen-eval.json`
- **WHEN** `consensus_synthesizer.py` runs
- **THEN** the synthesizer MUST log "no gen-eval findings (skipping behavioral source)"
- **AND** the synthesizer MUST continue with scrutiny findings only
- **AND** the synthesizer MUST exit zero

