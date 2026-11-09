## MODIFIED Requirements

### Requirement: Implementation Strategy Selection

The system SHALL select an implementation strategy per work package: `alternatives` (3 independent implementations + synthesis) or `lead_review` (1 implements + others review). Selection SHALL ask a calibrated judgment over the package's `work-packages.yaml` metadata, available vendor count, and its matching `design.md` section (when a design path is available), falling back to the existing weighted-sum rule over `metadata.loc_estimate`, `metadata.alternatives_count`, `metadata.package_kind`, and vendor count when the judgment is unavailable or its confidence is below a config-held floor. Vendor availability is judgment context, not a separate deterministic gate -- the existing weighted-sum fallback's own treatment of vendor count (one additive term, no hard floor) is unchanged. Packages without metadata SHALL default to `lead_review` without a judgment attempt.

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

#### Scenario: Vendor scarcity below three stays reachable via the unmodified fallback

- **GIVEN** a package with metadata whose weighted sum clears the "alternatives" threshold
- **WHEN** strategy selection runs with fewer than 3 available vendors and no judgment is available
- **THEN** the strategy SHALL still be "alternatives", exactly as the existing weighted-sum rule already produces today

#### Scenario: Judged strategy uses the matching design.md section

- **GIVEN** a package whose id matches a heading in the change's `design.md`
- **WHEN** strategy selection runs and the judgment is available
- **THEN** that section's text, along with the available vendor count, SHALL be included in the state passed to the judgment

#### Scenario: Low-confidence judgment falls back to the weighted sum

- **GIVEN** a judgment answer whose confidence is below the configured floor
- **WHEN** strategy selection runs
- **THEN** the strategy SHALL be determined by the existing weighted-sum rule, unchanged
