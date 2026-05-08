# evaluation-framework Spec Delta — Factory Missions Architecture Alignment

## ADDED Requirements

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
- **THEN** the handler MUST invoke gen-eval with `--mode cli-augmented --openspec-change example`
- **AND** the handler MUST log "gen-eval: cli-augmented mode (descriptor + OpenSpec change present)"

#### Scenario: Descriptor only → template-only fallback

- **GIVEN** a project with `evaluation/gen_eval/descriptors/api.yaml`
- **AND** no OpenSpec change directory for the active change-id (e.g., the change has no spec deltas)
- **WHEN** `/validate-feature <change-id> --phase gen-eval` runs
- **THEN** the handler MUST invoke gen-eval with `--mode template-only --no-services`
- **AND** the handler MUST log "gen-eval: template-only mode (no OpenSpec change at openspec/changes/<change-id>/specs/)"

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
- **THEN** the emitted `consensus.json` MUST contain 9 ranked findings
- **AND** the 4 behavioral findings MUST appear in the ranking with `type: behavioral_failure`
- **AND** the synthesizer MUST log the vendor breakdown: "merged: claude=3, codex=2, gen-eval=4"

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
