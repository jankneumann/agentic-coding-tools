# architecture-refresh — delta

## ADDED Requirements

### Requirement: Architecture provenance is a committed baseline

Architecture provenance SHALL be tracked in version control at
`docs/architecture-analysis/architecture.provenance.json`, so that freshness can be
determined by comparing committed evidence against recomputed digests rather than by
inspecting file modification times.

Without a committed baseline the read-only check has nothing to compare against and fails
closed on every clean checkout, which makes architecture freshness unusable as a gate.

Regenerating architecture artifacts SHALL update the committed provenance in the same
commit, so a clean checkout at the recorded revision passes the freshness check with no
diff.

#### Scenario: Clean checkout at the recorded revision is fresh
- **GIVEN** a clean checkout at the revision recorded in committed provenance
- **WHEN** the read-only freshness check runs
- **THEN** the check SHALL report fresh
- **AND** the checkout SHALL have no diff

#### Scenario: Missing provenance fails closed
- **GIVEN** a checkout with no committed provenance file
- **WHEN** the read-only freshness check runs
- **THEN** the check SHALL fail closed and report the missing provenance

#### Scenario: Regeneration updates the committed baseline
- **GIVEN** architecture artifacts regenerated after a source change
- **WHEN** the regeneration completes
- **THEN** the committed provenance SHALL record the new analyzed revision and digests
- **AND** the freshness check SHALL report fresh without further edits
