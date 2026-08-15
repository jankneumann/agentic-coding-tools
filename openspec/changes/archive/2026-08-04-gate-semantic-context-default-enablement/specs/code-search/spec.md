# code-search Specification Delta

**Change ID**: `gate-semantic-context-default-enablement`

## REMOVED Requirements

### Requirement: Retrieval Quality Gate

**Reason**: Superseded by `Semantic Context Enablement Gate` (ADDED below).
The adoption-era scenario "Gate report exists before backend implementation"
required `eval/spike-report.md` inside this capability's originating change
directory; the successor requirement's own scenario forbids consumers
referencing any path inside a change directory, so that scenario is
intentionally dropped rather than carried forward. Expressed as
REMOVED + ADDED (not MODIFIED) to record the drop explicitly, and renamed
because the successor gates *default enablement*, not the original
adoption spike.

## ADDED Requirements

### Requirement: Semantic Context Enablement Gate

Default enablement of semantic context SHALL be gated on a recorded evaluation stored at a durable repository path, covering at least ten realistic retrieval tasks with hand-labeled expected files, run against the production query backend on this repository, and reporting top-5 hit rate and rendered-line cost against an exact-search baseline computed over the same tasks under the same context budget. The gate passes only if hit@5 is at least 7 of 10 including at least 2 tasks the exact-search baseline measurably missed. A blocked, waived, unmeasured, or absent evaluation is not a pass and SHALL NOT authorize enablement.

#### Scenario: A waived evaluation is not a pass

- **WHEN** an evaluation could not be executed, was abandoned, or was accepted by
  operator judgement without measurement
- **THEN** the recorded verdict SHALL be a failure with an explicit reason
- **AND** it SHALL NOT satisfy this gate

#### Scenario: The gate report is machine-checkable at a durable path

- **WHEN** default enablement of semantic context is claimed
- **THEN** a schema-valid evaluation report SHALL exist at the durable
  repository path, carrying per-task results, the exact-search baseline it was
  compared against, and a verdict drawn from a closed two-value set
- **AND** no consumer of this requirement SHALL reference a path inside a change
  directory

#### Scenario: A measurement taken against the wrong backend does not count

- **WHEN** the recorded evaluation was produced against a retrieval backend
  other than the one serving requests
- **THEN** the report SHALL record the backend it measured
- **AND** the gate SHALL fail

### Requirement: Evaluation Provenance For Enablement

Any evaluation used to authorize semantic context enablement SHALL record the exact source revision its index was built from, the embedding provider kind, model identity, dimension and fingerprint, the indexing policy and pipeline fingerprints available from the serving response, and whether the code-search service was enabled while the measurement was taken.

#### Scenario: A measurement taken with the service disabled is void

- **WHEN** the code-search service was disabled during the measurement
- **THEN** the recorded retrieval verdict SHALL be a failure
- **AND** the report SHALL name the service state

#### Scenario: Embedding identity is derived, never asserted

- **WHEN** the report records the embedding configuration
- **THEN** those values SHALL be derived from the configured embedding contract
  and the serving response
- **AND** no evaluation component SHALL assert a particular model identifier as
  a literal

### Requirement: Enablement Evidence Expiry

Authorization to enable semantic context SHALL lapse when the evidence supporting it no longer describes the current system. A changed evaluation corpus, a changed threshold, a changed harness version, a change to the harness's own source, a changed embedding fingerprint, an index revision unreachable from the tree under test, a report that fails schema validation, a report whose body does not account for every case, gate, and consumer the corpus declares, or a report whose recorded verdict is not the verdict its own body composes to SHALL each render the evidence absent.

#### Scenario: A changed threshold invalidates the existing evidence

- **WHEN** a gate threshold or any corpus case changes
- **THEN** the corpus digest SHALL change
- **AND** a report recorded against the previous digest SHALL no longer
  authorize enablement

#### Scenario: A changed embedding configuration invalidates the evidence

- **WHEN** the configured embedding fingerprint differs from the one the report
  recorded
- **THEN** the evidence SHALL be treated as absent
- **AND** a matching model name alone SHALL NOT restore it

#### Scenario: A changed harness invalidates its own evidence

- **WHEN** the harness's source differs from the source that produced a report
- **THEN** the evidence SHALL be treated as absent
- **AND** an unchanged declared harness version SHALL NOT restore it

#### Scenario: Current provenance over an empty body authorizes nothing

- **WHEN** a report carries current provenance and a passing verdict but records
  no gate result, no consumer result, or no case result
- **THEN** the report SHALL fail schema validation and SHALL NOT be writable at
  the durable path
- **AND** the evidence SHALL be treated as absent

#### Scenario: A report that omits a declared gate or consumer is not evidence

- **WHEN** a schema-valid report omits a gate, a consumer, or a case the corpus
  declares, or records a scored-case count its own results do not support
- **THEN** the evidence SHALL be treated as absent
- **AND** the unmet condition SHALL be named

#### Scenario: A report that contradicts its own body authorizes nothing

- **WHEN** a report records a passing verdict while its own body records a
  failing required gate, a failing consumer, an unscored declared case, a
  scored-case count below its declared count, or a gate that passed at an index
  tier below the one that gate declares it needs
- **THEN** the recorded verdict SHALL be re-derived from the body rather than
  read, and the evidence SHALL be treated as absent
- **AND** a report whose recorded verdict is a failure SHALL remain valid
  evidence of that failure even where its individual results all passed, because
  a run may fail for a reason no single result carries
