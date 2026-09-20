## MODIFIED Requirements

### Requirement: Capability Gap Detection

The system SHALL record capability-gap signals from four sources — agent self-report, coordinator-emitted patterns, session-log structured sections, and transcript mining — into a shared tag schema in episodic memory, and the `/improve-harness` skill SHALL consume the union of all sources with deduplication and source attribution.

#### Scenario: Structured failure recording schema
WHEN any emitter records a capability-gap signal
THEN it SHALL use the shared episodic-memory tag schema: failure_type (enum: scope_violation, verification_failed, lock_unavailable, timeout, convergence_failed, context_exhaustion), capability_gap (free text describing what was missing), suggested_improvement (free text), affected_skill (skill name), severity (low/medium/high/critical), AND source (enum: self-reported, coordinator-emitted, session-log, transcript-mined)

#### Scenario: Agent self-reports a capability gap
WHEN an agent encounters a task failure and invokes the `remember` MCP tool with capability-gap metadata
THEN the entry SHALL be recorded with `source:self-reported`

#### Scenario: Coordinator auto-emits capability gaps via LLM classifier
WHEN the coordinator's audit-triage background task drains a batch of audit entries from its in-memory ring buffer
THEN a calibrated first-stage judgment SHALL screen the batch for a capability-gap signal before the existing classifier runs, over a config-held recall-oriented threshold (default 0.3, favoring recall per the existing prompt's own "prefer recall over precision" guideline)
AND a batch whose screen probability is below the threshold SHALL NOT invoke the classifier
AND a batch whose screen probability clears the threshold SHALL invoke the existing classifier seeded with the screen's suggested failure_type and severity, which the classifier's own findings SHALL be backfilled with when a returned finding omits them
AND it SHALL resolve the classifier model via the archetype system in `agent-coordinator/archetypes.yaml` (default archetype `analyst`, default provider `claude_code`, both configurable) using `agents_config.resolve_model()`
AND it SHALL compose the classifier system prompt via `agents_config.compose_prompt(archetype, task_prompt)` so the archetype's base prompt is preserved
AND it SHALL invoke the classifier with strict output-schema enforcement so emitted findings always parse (invalid responses dropped with a warning, never written to memory)
AND for each capability gap the classifier identifies, the coordinator SHALL emit a memory entry under the shared tag schema with `source:coordinator-emitted` plus a `prompt_version:N` tag
AND it SHALL NOT require any agent involvement
AND the classifier archetype, provider, batch size, batch interval, and prompt version SHALL be configurable via `agent-coordinator/config.yaml: audit.capability_gap_triage.*`
AND the hot path (`AuditService.log_operation`) SHALL NOT block on LLM calls — only ring-buffer push happens synchronously
AND when the first-stage judgment is unavailable, every batch SHALL reach the classifier exactly as this scenario behaved before the judgment existed

#### Scenario: Session-log captures agent-observed gaps at phase boundaries
WHEN an agent writes a session-log phase entry via the `session-log` skill
AND the entry contains a `### Capability Gaps Observed` section with one or more gaps listed
THEN the skill SHALL emit one memory entry per gap with `source:session-log`
AND the markdown section SHALL be preserved in `openspec/changes/<change-id>/session-log.md` as human-readable record
AND an empty `### Capability Gaps Observed` section SHALL be a valid no-op (no memory entries emitted)

#### Scenario: /improve-harness consumes all sources with deduplication
WHEN `/improve-harness` is invoked
THEN it SHALL query episodic memory for capability_gap entries across ALL source values within a configurable time window (default: 30 days)
AND it SHALL ALSO scan `openspec/changes/**/session-log.md` for `### Capability Gaps Observed` sections (covering gaps not yet mirrored to memory)
AND it SHALL deduplicate findings on (capability_gap, affected_skill, session_id), preserving the set of sources that surfaced each finding
AND group by capability_gap
AND rank by frequency and severity
AND generate a structured report with recommendations

#### Scenario: Report includes source attribution
WHEN `/improve-harness` generates a report
THEN each finding SHALL be annotated with the set of sources that surfaced it (one or more of: self-reported, coordinator-emitted, session-log, transcript-mined)
AND the report SHALL include a summary line stating what fraction of findings surfaced in 2 or more sources (cross-source agreement is the strongest signal)

#### Scenario: Report handles empty capability-gap data
WHEN `/improve-harness` is invoked
AND episodic memory contains zero capability_gap entries within the time window
AND no `openspec/changes/**/session-log.md` files contain Capability Gaps Observed sections
THEN the skill SHALL report "No capability gaps recorded in the last N days" with a suggestion to verify that emitters (self-report, coordinator, session-log, transcript) are configured and active
AND exit with a zero status code

#### Scenario: Report-to-feature pipeline
WHEN an improvement report identifies a high-priority capability gap
THEN the user SHALL be able to invoke a skill that takes the report finding and creates an OpenSpec change proposal from it
AND the skill SHALL pre-populate the proposal with context from the failure patterns, affected skills, suggested improvements, AND the set of sources that surfaced the gap
