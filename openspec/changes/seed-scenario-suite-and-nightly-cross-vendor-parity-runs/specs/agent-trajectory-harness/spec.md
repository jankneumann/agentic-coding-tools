## ADDED Requirements

### Requirement: Seed scenario suite coverage floor

The agent-scenarios package SHALL ship a seed suite of at least 10 scenarios covering the plan, implement, validate and merge skill families, with at least 2 scenarios per family and at least 2 declared vendors per scenario, and a guard test SHALL fail the build when the suite drops below this floor.

#### Scenario: the shipped suite meets the coverage floor
- **WHEN** the guard test loads every `*.scenario.yaml` under `packages/agent-scenarios/scenarios/`
- **THEN** it SHALL find at least 10 scenarios with unique ids
- **AND** each of the families plan, implement, validate and merge SHALL be represented by at least 2 scenarios according to the package's skill-family map
- **AND** every scenario SHALL declare at least 2 vendors

#### Scenario: removing scenarios below the floor fails the guard
- **WHEN** the guard test runs against a suite directory containing only 9 scenarios, or with no merge-family scenario
- **THEN** the guard test SHALL fail and name the unmet floor

### Requirement: Seed scenarios are self-tested as satisfiable and discriminating

Every seed scenario SHALL have a scripted golden outcome and a scripted broken outcome for the fake executor, and the test suite MUST show that the golden outcome passes all goal gates while the broken outcome fails at least one named gate.

#### Scenario: golden outcome passes every gate
- **WHEN** a seed scenario is run through the runner with the fake executor scripted with its golden outcome
- **THEN** every vendor result SHALL have deterministic status `pass`

#### Scenario: broken outcome fails a named gate
- **WHEN** the same scenario is run with its broken outcome
- **THEN** every vendor result SHALL have deterministic status `fail`
- **AND** the failed gate ids SHALL include the gate id named by the broken outcome

#### Scenario: a seed scenario without outcomes is rejected
- **WHEN** a scenario file is added without a corresponding golden/broken outcome module
- **THEN** the guard test SHALL fail and name the scenario id

### Requirement: Live runs never reach real GitHub

Seed scenarios SHALL NOT depend on GitHub side effects. Push and merge behaviour MUST be exercised against a fixture-local bare `origin` repository, and the live executor SHALL remove configured credential variables from the vendor subprocess environment.

#### Scenario: local remote fixture
- **WHEN** a scenario fixture sets `local_remote: true`
- **THEN** fixture materialization SHALL create a bare repository outside the workspace, register it as `origin`, and push the base branch to it

#### Scenario: PR gates require a local remote
- **WHEN** the guard test finds a seed scenario with a `pr` goal gate and `local_remote` not set
- **THEN** the guard test SHALL fail

#### Scenario: credential variables are scrubbed
- **WHEN** the live executor runs a vendor command with `env_scrub` containing `GH_TOKEN` and `GITHUB_TOKEN`
- **THEN** neither variable SHALL be present in the vendor subprocess environment

### Requirement: Skill under test is materialized from the checkout being evaluated

When a skills root is configured, the live executor SHALL copy the scenario's skill under test (and any declared support skills) from that root into the workspace's project-local skill directories before running the vendor, and SHALL record the skills revision on each result.

#### Scenario: skill copied into the workspace
- **WHEN** the executor runs a scenario whose `skill_under_test` is `validate-feature` with `skills_root` set
- **THEN** `.claude/skills/validate-feature/` and `.agents/skills/validate-feature/` SHALL exist in the workspace with the contents of `skills_root/validate-feature/`
- **AND** those paths SHALL be excluded from git in the workspace so they never appear in agent commits

#### Scenario: missing skill is an executor error
- **WHEN** `skills_root` does not contain the scenario's skill under test
- **THEN** the run SHALL produce deterministic status `error` with a message naming the missing skill
- **AND** no vendor command SHALL be executed

### Requirement: Durable per-vendor per-skill results store

Each nightly run SHALL append one schema-versioned result record per scenario and vendor, and one run-summary record, to an append-only results store, and the package SHALL provide a query interface that filters and aggregates results by vendor, skill, skill family, scenario and time window.

#### Scenario: results are appended per scenario and vendor
- **WHEN** a nightly run executes 11 scenarios across 2 vendors
- **THEN** the store SHALL gain 22 `result` records and 1 `run` record sharing one `run_id`
- **AND** each `result` record SHALL include `scenario_id`, `skill_under_test`, `skill_family`, `vendor`, `deterministic_status`, `failed_gates`, `recorded_at` and `schema_version`

#### Scenario: query by vendor and skill over a time window
- **WHEN** an operator runs `agent-scenarios results query --vendor codex --skill validate-feature --since <date>`
- **THEN** only `result` records matching that vendor, skill and window SHALL be returned

#### Scenario: trend aggregates pass rate per bucket
- **WHEN** an operator runs `agent-scenarios results trend --group-by vendor,skill --bucket day`
- **THEN** the output SHALL report, per vendor, skill and day, the pass count, fail count, error count and a pass rate whose denominator excludes `error` and `skipped_budget` results

#### Scenario: reader tolerates a torn final line and unknown versions
- **WHEN** the store ends with a partial line or contains a record with an unknown `schema_version`
- **THEN** the reader SHALL skip those lines with a warning and return all valid records

#### Scenario: latest result per scenario and vendor
- **WHEN** an operator runs `agent-scenarios results latest --skill implement-feature`
- **THEN** exactly one record per (scenario, vendor) SHALL be returned, the most recent by `recorded_at`

### Requirement: Scenario failures feed the capability-gap pipeline

Every deterministic scenario failure SHALL be emitted as a capability-gap episodic-memory entry using the shared tag schema with `source:scenario-parity`, and entries that cannot be delivered to the coordinator MUST be spooled locally and replayed on a later run. Executor errors, budget skips and LLM-judge findings SHALL NOT produce capability-gap entries.

#### Scenario: a failing gate produces a tagged gap entry
- **WHEN** a result has deterministic status `fail` for scenario `validate-feature-clean-pass` on vendor `codex` with failed gate `report-has-status`
- **THEN** the emitter SHALL send one entry with tags including `capability_gap`, `capability_gap:scenario-parity/validate-feature-clean-pass/report-has-status`, `failure_type:verification_failed`, `affected_skill:validate-feature`, `severity:high`, `source:scenario-parity` and `vendor:codex`
- **AND** the entry's `session_id` SHALL be the nightly `run_id`

#### Scenario: errors and judge findings do not emit gaps
- **WHEN** a result has deterministic status `error` or `skipped_budget`, or passes gates but carries LLM-judge findings
- **THEN** no capability-gap entry SHALL be emitted for it

#### Scenario: coordinator unreachable spools entries
- **WHEN** the coordinator memory endpoint is unreachable during emission
- **THEN** every entry SHALL be appended to the gap spool file and none SHALL be lost

#### Scenario: spool replay
- **WHEN** `agent-scenarios gaps flush` runs and the coordinator is reachable
- **THEN** spooled entries SHALL be delivered and removed from the spool
- **AND** entries that still fail delivery SHALL remain in the spool

#### Scenario: a deliberately broken skill change produces a capability gap
- **WHEN** the suite runs against a skills root in which a skill under test has been deliberately broken so that its scenario's gates fail
- **THEN** the run SHALL record a `fail` result for that scenario
- **AND** a capability-gap entry with `affected_skill` equal to that skill and `source:scenario-parity` SHALL be emitted
- **AND** `/improve-harness` failure analysis over that entry SHALL rank a finding for that capability gap with `scenario-parity` in its source set

### Requirement: Nightly runner with off-switch and spend caps

The package SHALL provide a nightly command that runs the suite across an allowlist of at least 2 vendors under explicit size and time caps, and that does nothing unless explicitly enabled.

#### Scenario: disabled by default
- **WHEN** `agent-scenarios nightly` runs with a config whose `enabled` is false
- **THEN** no executor SHALL be constructed and no vendor command SHALL run
- **AND** a `run` record with status `disabled` SHALL be appended and the command SHALL exit 0

#### Scenario: kill-file disables an enabled config
- **WHEN** the config is enabled and the configured `disable_file` exists
- **THEN** the run SHALL behave as disabled

#### Scenario: over-cap plan refuses to start
- **WHEN** the planned scenario×vendor pairs exceed `caps.max_pairs`, or any vendor's pairs exceed `caps.max_pairs_per_vendor`
- **THEN** no pair SHALL be launched
- **AND** a `run` record with status `cap_exceeded` SHALL be appended and the command SHALL exit 2

#### Scenario: wall-clock budget stops launching new pairs
- **WHEN** elapsed run time reaches `caps.max_wall_clock_minutes` with pairs remaining
- **THEN** remaining pairs SHALL NOT be launched and SHALL be recorded with status `skipped_budget`
- **AND** the `run` record status SHALL be `budget_exhausted`

#### Scenario: fewer than two effective vendors is a config error
- **WHEN** the vendor allowlist intersected with the suite's declared vendors yields fewer than 2 vendors
- **THEN** the command SHALL exit 2 without launching any pair

#### Scenario: overlapping runs are refused
- **WHEN** a nightly run starts while another holds the run lock
- **THEN** it SHALL record status `locked` and exit 0 without launching any pair

#### Scenario: dry run plans without executing
- **WHEN** `agent-scenarios nightly --dry-run` runs with an enabled config
- **THEN** it SHALL print the planned pairs and cap evaluation and SHALL NOT launch any pair or write result records

#### Scenario: failing scenarios make the run exit non-zero
- **WHEN** a completed nightly run has at least one `fail` result
- **THEN** the command SHALL exit 1 after writing results, findings and gaps

### Requirement: Schedule shipped as templates only

The change SHALL ship the nightly schedule only as systemd unit and timer templates plus an example config with `enabled: false`, and MUST NOT install, enable or start any scheduled job.

#### Scenario: templates and example config are inert
- **WHEN** the deploy assets under `packages/agent-scenarios/deploy/` are inspected by the test suite
- **THEN** the service and timer templates SHALL contain unresolved placeholder tokens for host-specific paths
- **AND** the example config SHALL parse with `enabled: false`
- **AND** no test, script or CI step in the change SHALL invoke `systemctl`
