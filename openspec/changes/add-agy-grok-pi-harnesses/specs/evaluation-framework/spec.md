# evaluation-framework — delta for add-agy-grok-pi-harnesses

Replaces the Gemini/Jules eval backend with `antigravity`, `grok`, and `pi` backends, bringing
eval coverage to full roster parity (proposal decision D4).

## MODIFIED Requirements

### Requirement: Agent Backend Abstraction

The system SHALL define an `AgentBackend` protocol allowing different agent implementations to be benchmarked through a uniform interface.

The framework SHALL ship one backend per first-class provider in the supported roster: Claude Code, Codex, antigravity, grok, and pi. It SHALL NOT ship a Gemini/Jules backend.

#### Scenario: Agent backend submits task
- **WHEN** the harness submits a task to an agent backend
- **THEN** the backend SHALL accept task description, affected files, and coordination configuration
- **AND** return task result including output, timing, token usage, and success indicator

#### Scenario: Claude Code backend
- **WHEN** the Claude Code backend receives a task
- **THEN** it SHALL execute the task via Claude Code CLI or Task() invocation
- **AND** capture all coordination metrics from the instrumented primitives

#### Scenario: Codex backend
- **WHEN** the Codex backend receives a task
- **THEN** it SHALL execute the task via Codex CLI
- **AND** return results in the standard backend result format

#### Scenario: antigravity backend
- **WHEN** the antigravity backend receives a task
- **THEN** it SHALL execute the task via the `agy` CLI in headless mode
- **AND** return results in the standard backend result format

#### Scenario: grok backend
- **WHEN** the grok backend receives a task
- **THEN** it SHALL execute the task via the `grok` CLI with `--output-format json`
- **AND** parse the structured JSON envelope rather than scraping stdout
- **AND** return results in the standard backend result format

#### Scenario: pi backend
- **WHEN** the pi backend receives a task
- **THEN** it SHALL execute the task via the `pi` CLI with `--provider openrouter`
- **AND** return results in the standard backend result format

#### Scenario: Retired Gemini/Jules backend is absent
- **WHEN** the backend registry is enumerated
- **THEN** no Gemini or Jules backend SHALL be exported
- **AND** requesting one SHALL raise a structured error naming the supported roster

#### Scenario: Backend comparison run
- **WHEN** evaluation is configured with multiple agent backends
- **THEN** the harness SHALL run identical tasks through each backend
- **AND** produce a cross-backend comparison table in the report
