## ADDED Requirements

### Requirement: Decision-Tag Backfill Classification

`backfill_decision_tags.propose_tags_for_archive` SHALL classify each untagged Decision bullet extracted from an archived `session-log.md` by routing it to a capability. Classification SHALL ask a calibrated judgment — a `Choice(capability, the keyword map's tags plus "none")` — batched into a single calibrated-decision call per session-log phase (every untagged decision within one `## Phase:` block answered by one call), over each decision's title and rationale as shared state. A decision the judgment resolves to `"none"` SHALL be treated the same as no keyword match: `proposed_capability` SHALL be `None`, excluding it from proposed edits. When the judgment is unavailable for a whole phase or for one decision within an otherwise-answered phase, that decision SHALL fall back to the existing keyword-overlap heuristic (`classify_decision`), unchanged. The classifier SHALL only propose — it SHALL NOT mutate any markdown file itself, and SHALL write a JSON proposals report only when the caller supplies an output path.

#### Scenario: All decisions in one phase are answered by a single batched call

- **GIVEN** a session-log phase with two or more untagged Decision bullets
- **WHEN** `propose_tags_for_archive` runs and the judgment is available
- **THEN** the calibrated-decision call SHALL be invoked exactly once for that phase
- **AND** every decision in the phase SHALL receive an answer from that one call

#### Scenario: A "none" choice excludes the decision from proposed edits

- **GIVEN** a decision the judgment routes to `"none"`
- **WHEN** `propose_tags_for_archive` runs
- **THEN** the proposal's `proposed_capability` SHALL be `None`
- **AND** the decision SHALL be counted under `no_match`, not any confidence bucket

#### Scenario: The confidence field is populated from the judgment's own calibrated probability

- **GIVEN** a decision the judgment confidently routes to a capability
- **WHEN** `propose_tags_for_archive` runs
- **THEN** the proposal's `confidence` field SHALL be the judgment's own confidence value
- **AND** the existing 0.5/0.8 confidence-bucketing logic SHALL apply to it unchanged

#### Scenario: Unavailable judgment falls back to the keyword map unchanged

- **GIVEN** the judgment is unavailable (module missing, no usable answer) for a phase or for one decision within it
- **WHEN** `propose_tags_for_archive` runs
- **THEN** the affected decision(s) SHALL be classified by the existing keyword-overlap heuristic, exactly as `propose_tags_for_archive` behaved before the judgment existed

#### Scenario: The script never mutates markdown and writes JSON only on request

- **GIVEN** any classification outcome
- **WHEN** `propose_tags_for_archive` runs
- **THEN** no session-log markdown file SHALL be modified
- **AND** a JSON proposals report SHALL be written only when an output path is supplied
