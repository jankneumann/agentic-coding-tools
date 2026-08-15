# semantic-context-evaluation Specification

## Purpose
TBD - created by archiving change gate-semantic-context-default-enablement. Update Purpose after archive.
## Requirements
### Requirement: Declared Evaluation Corpus

The evaluation corpus SHALL declare, as reviewable data rather than as code, every case, every gate, every threshold, every named consumer, and the shared context budget applied to both arms. Threshold values SHALL NOT appear as literals in the scoring implementation, and the corpus SHALL produce a deterministic digest that identifies the exact evidence any report was produced against.

#### Scenario: Thresholds are corpus data

- **WHEN** a gate threshold is changed
- **THEN** the change SHALL appear as a diff in the corpus manifest
- **AND** the corpus digest SHALL change
- **AND** no threshold value SHALL be readable from the scoring modules alone

#### Scenario: An unlabeled consumer is a corpus error

- **WHEN** the corpus declares a consumer
- **THEN** it SHALL also declare that consumer's case slice and an explicit
  statement of whether coding-context utility applies to it
- **AND** a consumer with neither SHALL fail corpus validation rather than be
  silently omitted from measurement

#### Scenario: Rescued cases keep their identity

- **WHEN** a case is carried forward from an earlier evaluation
- **THEN** it SHALL retain its original identifier, query, expected files,
  category, and rationale
- **AND** it SHALL record the artifact it was rescued from

### Requirement: Reproducible Exact-Search Baseline

Every semantic measurement SHALL be reported against an exact-search baseline computed over the same cases, under the same context budget, on the same repository revision. The baseline producer SHALL receive its repository root as an injected value and SHALL NOT derive it from the location of its own source file.

#### Scenario: The baseline is reproducible from its published artifact

- **WHEN** the baseline producer runs from any directory depth, including after
  its change has been archived
- **THEN** it SHALL resolve the repository root correctly
- **AND** a root that is not a repository checkout SHALL be an apparatus failure
  rather than a silently empty result

#### Scenario: Both arms share one budget

- **WHEN** the semantic arm and the exact-search arm are compared
- **THEN** both SHALL be rendered under the identical declared bounds on hit
  count, distinct file count, total lines, and per-hit lines
- **AND** an unbounded baseline SHALL NOT be compared against a bounded section

#### Scenario: The ranking algorithm is pinned independently of the tree

- **WHEN** the baseline ranking is exercised
- **THEN** its ordering SHALL be asserted against hand-computed expected output
  over a fixed fixture tree
- **AND** a number measured over the live repository SHALL be recorded in the
  report rather than asserted in a test

### Requirement: Retrieval Relevance Measurement

Retrieval relevance SHALL be measured per case as top-k hit rate against hand-labeled expected files, coverage of the labeled files a task requires, and the count of cases the semantic arm answers that the exact-search baseline misses. A win over the baseline SHALL be determined by measurement, never by a hand-applied label.

#### Scenario: Wins are measured, not labeled

- **WHEN** a case carries a category label predicting the baseline will miss it
- **THEN** the gate SHALL count that case as a win only if the baseline
  measurably missed it in this run
- **AND** the label SHALL be retained as descriptive metadata only

#### Scenario: Coverage is distinct from hit rate

- **WHEN** a case labels more than one file as required
- **THEN** finding one of them SHALL count as a top-k hit
- **AND** it SHALL NOT count as full coverage

### Requirement: Coding-Context Utility Measurement

Coding-context utility SHALL be measured deterministically, per consumer, and relative to the exact-search baseline, using labeled required files and labeled evidence spans. The measurement SHALL report required-file coverage, the proportion of rendered lines that fall inside labeled evidence, and the number of rendered results that must be read before the first labeled evidence appears.

#### Scenario: Utility is measured against labeled evidence

- **WHEN** utility is computed for a case
- **THEN** it SHALL be computed against that case's labeled required files and
  evidence spans
- **AND** it SHALL NOT be inferred from relevance scores returned by the index

#### Scenario: Missing evidence is censored, not null

- **WHEN** no rendered result intersects any labeled evidence span
- **THEN** the read-cost measure SHALL take the declared censored value
- **AND** it SHALL NOT be recorded as absent, null, or excluded from the mean

#### Scenario: No consumer may regress

- **WHEN** any single consumer's semantic required-file coverage is below its
  own exact-search baseline
- **THEN** that consumer's verdict SHALL be a failure
- **AND** the composed verdict SHALL be a failure
- **AND** a gain in another consumer SHALL NOT offset it

### Requirement: Scope Compliance Measurement

Scope compliance SHALL be measured on both the outbound request and the rendered result, against the case's declared read-allow and deny globs with deny taking precedence. A single rendered result outside the declared scope SHALL fail the gate; there is no tolerance threshold.

#### Scenario: A single violation fails the gate

- **WHEN** exactly one rendered result lies outside the declared scope
- **THEN** the scope compliance gate SHALL fail
- **AND** the violating path SHALL be named in the report

#### Scenario: A leaked hit is caught client-side

- **WHEN** a recorded service response contains a result outside the declared
  scope
- **THEN** the measured result SHALL contain no such result
- **AND** it SHALL be recorded as omitted for a scope reason

#### Scenario: A degraded scope adapter is an apparatus failure

- **WHEN** the shared scope-normalization dependency cannot be resolved and the
  measurement falls back to unnormalized globs
- **THEN** the report SHALL record the degraded adapter
- **AND** the run SHALL fail rather than report a compliance result derived from
  different semantics than it claims

### Requirement: Fail-Closed Evaluation Verdict

An evaluation verdict SHALL be exactly one of pass or fail. The report format SHALL provide no value expressing skipped, blocked, waived, partial, or unmeasured, and SHALL provide no waiver field. An evaluation that could not be taken SHALL be recorded as a failure with an explicit reason.

#### Scenario: A verdict enum with no escape value

- **WHEN** an evaluation cannot be executed for any reason
- **THEN** the report SHALL carry a failing verdict with an explicit reason
- **AND** the format SHALL make any other representation of that outcome
  unwritable

#### Scenario: An unmeasured gate is a failing gate

- **WHEN** a gate declared by the corpus is absent from a run's results
- **THEN** the composed verdict SHALL fail
- **AND** the missing gate SHALL be named

#### Scenario: The denominator is declared

- **WHEN** any declared case is not scored, for any reason including an
  exception, a timeout, an invalid document, or an exhausted budget
- **THEN** that case SHALL be recorded as unscored with its reason
- **AND** the composed verdict SHALL fail
- **AND** the pass rate SHALL NOT be computed over the surviving cases alone

#### Scenario: Nothing exits zero without a passing report

- **WHEN** the evaluation entry point completes
- **THEN** a success exit code SHALL require a schema-valid report with a
  passing verdict
- **AND** an apparatus failure, a gate failure, and an absent or stale report
  SHALL each use a distinct non-zero code

### Requirement: Index Tier Declaration

Each gate SHALL declare the minimum index tier its measurement requires, and a report produced at a lower tier than a gate declares SHALL fail that gate. Retrieval-relevance and semantic-arm utility measurements SHALL require a real index built from the exact evaluated revision by the production indexing path.

#### Scenario: A live retrieval measurement needs a real index

- **WHEN** a retrieval-relevance result is produced without a real index built
  at the evaluated revision
- **THEN** the gate SHALL fail for insufficient index tier
- **AND** a seeded or fixture index SHALL NOT satisfy it

#### Scenario: A disabled service measures nothing

- **WHEN** the code-search service was disabled during a retrieval measurement
- **THEN** the retrieval gate SHALL fail
- **AND** the report SHALL record the service state at measurement time

#### Scenario: Client-side gates need no index

- **WHEN** scope compliance or fail-closed regression is measured
- **THEN** it SHALL be measurable from recorded service responses with no
  database and no embedding backend

### Requirement: Evaluation Report Record

An evaluation report SHALL record the indexed revision, the evaluated repository revision, the embedding provider kind, model identity, dimension and fingerprint, the applied context budget, the corpus digest, the harness version, a digest of the harness's own source, the service state at measurement time, and each gate's thresholds alongside its measured values and verdict. The report SHALL live at a durable path that does not move when this change is archived.

#### Scenario: The report identifies its index and configuration

- **WHEN** a report is written
- **THEN** it SHALL name the exact revision the serving index was built from and
  the full embedding configuration that produced it
- **AND** the model identity SHALL be derived from the configured embedding
  contract rather than asserted as a literal anywhere in the harness

#### Scenario: The report identifies the software that produced it

- **WHEN** a report is written
- **THEN** it SHALL carry a digest derived from the harness's own source
- **AND** that digest SHALL NOT be satisfiable by declaring a version string

#### Scenario: The report has a durable home

- **WHEN** this change is archived
- **THEN** the report path referenced by specs, guides, and gates SHALL still
  resolve
- **AND** no consumer SHALL reference a path inside a change directory

#### Scenario: Every gate is self-describing

- **WHEN** a gate result is recorded
- **THEN** it SHALL carry the threshold it was judged against and the value it
  measured
- **AND** a reader SHALL NOT need the harness source to interpret it

### Requirement: Fail-Closed Regression Cases

The corpus SHALL contain cases asserting that an unavailable index for the exact evaluated revision, a revision mismatch, a rejected scope, and an unrecognized service state each produce an explicit exact-search fallback carrying zero results, and that none of them blocks the coding job.

#### Scenario: An unavailable exact-revision index restores exact search

- **WHEN** no index exists for the revision a coding job is working against
- **THEN** the measured result SHALL be a fallback naming exact search
- **AND** it SHALL carry zero results
- **AND** the case SHALL be scored, not skipped

#### Scenario: An unrecognized state never becomes an injection

- **WHEN** a recorded response carries a service state the client does not
  recognize
- **THEN** the measured result SHALL be an unavailable fallback

### Requirement: Deterministic Scoring

Ordering, selection, and scoring SHALL depend only on the evaluated documents, the corpus, and the declared thresholds. They SHALL NOT depend on wall-clock time, pseudorandom values, hash-set iteration order, process identity, or the order in which results were produced.

#### Scenario: Reordered input produces identical output

- **WHEN** the same results are scored twice in different input orders
- **THEN** every metric, every per-consumer verdict, and the composed verdict
  SHALL be identical
- **AND** the assertion SHALL be against a fixed expected ordering derived
  independently of the implementation

### Requirement: Advisory Qualitative Review

An optional qualitative review of a rendered context section MAY be recorded in the report, and SHALL be structurally incapable of affecting any verdict. Its absence SHALL never be a failure reason.

#### Scenario: The judge cannot reach the verdict

- **WHEN** the verdict is composed
- **THEN** the composition SHALL NOT receive any qualitative review as input
- **AND** attaching a review SHALL happen only after the verdict exists

#### Scenario: An absent review is not a gate

- **WHEN** no qualitative review backend is configured
- **THEN** the run SHALL complete normally
- **AND** no failure reason SHALL be recorded for its absence

