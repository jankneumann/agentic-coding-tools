# project-context-refresh-orchestration — delta

## REMOVED Requirements

### Requirement: Architecture freshness fails closed on unverifiable provenance

**Reason**: The requirement's premise is reversed, not adjusted, so a MODIFIED block whose
heading still reads "fails closed" would be false. Architecture freshness is a per-machine
property: `check_freshness` reports fresh only when every recorded artifact is present with
a matching digest, and a repository that records those artifacts as local-cache holds no
such baseline on a clean checkout. Blocking on that condition blocked on something true by
design everywhere except the machine that last ran the refresh — measured in the first
consumer as `refresh_status: degraded` on every convergence pass for a week, with no step in
the workflow that could clear it.

**Migration**: Replaced by the ADDED "Architecture freshness is reported, not enforced"
below, which keeps every scenario of the retired requirement including
`Absent owner degrades without blocking`, and keeps the report block byte-identical in
shape. What is withdrawn is the blocking consequence alone; the *reporting* distinction
from ri-10 D4 survives, so "no baseline" stays distinguishable from "digests disagree".
Consumers regain freshness through `run_architecture.py --ensure` at their read boundary.

## ADDED Requirements

### Requirement: Architecture freshness is reported, not enforced

The architecture producer SHALL determine freshness by comparing local provenance against
recomputed artifact digests, and SHALL NOT report freshness by rebuilding provenance from
the working tree.

Missing, malformed, or schema-invalid provenance SHALL be reported as `unverifiable`, not
as an absent optional owner, because unverifiable evidence is not the same as absent
tooling. The distinction is retained for readers of the gate report.

Architecture freshness SHALL be classified as informational drift and SHALL NOT contribute
to `blocking_drift` or to the drift exit code. Architecture artifacts and their provenance
are a regenerable local analysis cache whose freshness is a property of the checkout that
last regenerated them; a gate evaluated on any other checkout cannot observe it, so
blocking on it would block on a condition that is true of every clean clone.

An architecture owner that is genuinely not importable SHALL remain an absent optional
owner and SHALL NOT fail the gate.

#### Scenario: Missing provenance is reported but does not block
- **WHEN** the drift gate runs on a checkout with no local architecture provenance
- **AND** no other producer reports blocking drift
- **THEN** the report's `architecture.freshness` SHALL be `unverifiable`
- **AND** `architecture` SHALL appear in `informational_drift`
- **AND** the gate SHALL exit zero

#### Scenario: Stale architecture is reported but does not block
- **WHEN** local provenance digests do not match recomputed artifact digests
- **AND** no other producer reports blocking drift
- **THEN** the report's `architecture.freshness` SHALL be `stale`
- **AND** the gate SHALL exit zero

#### Scenario: Architecture drift never masks committed-artifact drift
- **WHEN** architecture provenance is missing
- **AND** the `decisions.timeline` producer reports drift
- **THEN** the gate SHALL exit with the drift exit code
- **AND** `blocking_drift` SHALL contain `decisions.timeline` and SHALL NOT contain `architecture`

#### Scenario: Absent owner degrades without blocking
- **WHEN** the drift gate runs on a checkout where the architecture refresh owner is not importable
- **AND** no other producer reports drift
- **THEN** architecture SHALL be reported as an absent optional owner
- **AND** the gate SHALL exit zero



### Requirement: Architecture freshness is ensured by consumers on demand

A skill that reads architecture artifacts SHALL ensure they are fresh immediately before
reading, by invoking the architecture runner's ensure mode against the checkout it is
about to read from. Freshness SHALL NOT be assumed from a prior gate result, a prior
convergence, or the recorded revision.

The branch-local checkpoint SHALL NOT invoke ensure mode; it reports architecture
freshness and delta as findings and remains read-only.

#### Scenario: Consumer regenerates stale artifacts before reading
- **WHEN** a consuming skill begins its artifact-reading step
- **AND** the local provenance is stale or missing
- **THEN** the skill SHALL invoke ensure mode before reading
- **AND** the artifacts it reads SHALL carry provenance for the current working tree

#### Scenario: Consumer reads fresh artifacts without regeneration
- **WHEN** a consuming skill begins its artifact-reading step
- **AND** the local provenance is fresh
- **THEN** ensure mode SHALL write nothing
- **AND** the skill SHALL proceed to read without delay beyond the check

#### Scenario: Checkpoint reports rather than ensures
- **WHEN** the branch-local checkpoint runs on a checkout with stale architecture provenance
- **THEN** the checkpoint SHALL report architecture as stale
- **AND** SHALL NOT regenerate artifacts or provenance
