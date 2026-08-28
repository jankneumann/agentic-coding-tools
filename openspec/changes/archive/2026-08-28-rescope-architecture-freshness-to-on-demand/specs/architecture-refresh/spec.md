# architecture-refresh — delta

## MODIFIED Requirements

### Requirement: Architecture provenance is a committed baseline

Architecture provenance SHALL be written at
`docs/architecture-analysis/architecture.provenance.json`, beside the artifacts it
describes, and SHALL share the version-control status of its **committed-tier** artifacts.
Freshness SHALL be determined by comparing that provenance against recomputed digests of
the artifacts present in the same checkout, never by file modification times.

Each recorded artifact declares a tier. A **committed-tier** artifact is expected in every
clean checkout, and its absence SHALL be reported as drift. A **local-cache** artifact is
regenerated output that a repository MAY decline to track; its absence SHALL NOT be
reported as drift, and its presence SHALL still be digest-verified. A repository therefore
chooses its posture per artifact rather than for the capability as a whole.

The promise a clean checkout carries follows from that choice. Where every recorded
artifact is committed-tier, a clean checkout at the recorded revision SHALL be fresh.
Where the artifacts a consumer needs are local-cache — the posture a repository takes when
those artifacts are too large to review as a diff — a checkout that has not regenerated
them holds an **unverified** baseline rather than a stale one, and the read-only check
SHALL say so. The specification does not require every repository to commit them.

Regenerating architecture artifacts SHALL update the provenance in the same promotion, so
that a checkout which has just regenerated passes the freshness check with no further
edits.

#### Scenario: Clean checkout at the recorded revision is fresh
- **GIVEN** a clean checkout at the revision recorded in provenance
- **AND** every recorded artifact is committed-tier
- **WHEN** the read-only freshness check runs
- **THEN** the check SHALL report fresh
- **AND** the checkout SHALL have no diff

#### Scenario: Missing provenance fails closed
- **GIVEN** a checkout with no provenance file
- **WHEN** the read-only freshness check runs
- **THEN** the check SHALL fail closed and report the missing provenance as unverifiable
- **AND** it SHALL NOT report artifact digests as mismatched

#### Scenario: Regeneration updates the committed baseline
- **GIVEN** architecture artifacts regenerated after a source change
- **WHEN** the regeneration completes
- **THEN** the promoted provenance SHALL record the new analyzed revision and digests
- **AND** the freshness check SHALL report fresh without further edits

#### Scenario: Clean clone is unverified, not stale
- **GIVEN** a repository that records its artifacts as local-cache and does not track them
- **WHEN** the read-only freshness check runs on a checkout holding neither artifacts nor provenance
- **THEN** it SHALL report the provenance as missing
- **AND** SHALL NOT report artifact digests as mismatched

#### Scenario: An untracked local-cache artifact is not drift
- **GIVEN** a repository that records an artifact as local-cache and does not track it
- **WHEN** the read-only freshness check runs on a clean checkout
- **THEN** the absent artifact SHALL NOT be reported as drift
- **AND** a present one SHALL still be digest-verified

## ADDED Requirements

### Requirement: Ensure mode composes check and staged refresh

The architecture runner SHALL provide `--ensure`, which runs the read-only check and, only
if the result is not fresh, runs the deterministic staged refresh. It SHALL exit zero when
the artifacts are fresh on return and SHALL exit with the staged refresh's code otherwise.
Ensure mode SHALL introduce no freshness logic, digest routine, or promotion path of its
own.

#### Scenario: Fresh artifacts are left untouched
- **WHEN** ensure mode runs and the check reports fresh
- **THEN** no artifact or provenance byte SHALL change
- **AND** the exit code SHALL be zero

#### Scenario: Stale artifacts are regenerated
- **WHEN** ensure mode runs and the check reports stale or missing provenance
- **THEN** the staged refresh SHALL run
- **AND** a subsequent read-only check SHALL report fresh

#### Scenario: Ensure is idempotent
- **WHEN** ensure mode runs twice with no intervening source change
- **THEN** the second run SHALL write nothing
- **AND** provenance SHALL be byte-identical before and after the second run

#### Scenario: Failed regeneration preserves last known-good
- **WHEN** ensure mode triggers the staged refresh and an analyzer fails before promotion
- **THEN** the previous artifacts and provenance SHALL remain intact
- **AND** ensure mode SHALL exit non-zero

### Requirement: Inapplicable analyzer input is skipped, not failed

An analyzer whose configured input root is absent, or present but containing nothing the
analyzer parses, SHALL be recorded as skipped with a warning naming the root and the
expected input. It SHALL NOT increment the pipeline's error count, SHALL NOT block staged
promotion, and SHALL NOT write an empty artifact in place of a result. This verdict SHALL
be applied uniformly across analyzers.

#### Scenario: Repository without SQL migrations promotes
- **WHEN** the staged refresh runs in a repository whose `MIGRATIONS_DIR` contains no `*.sql` files
- **THEN** the Postgres analyzer SHALL be recorded as skipped with a warning
- **AND** the remaining stages SHALL run
- **AND** promotion SHALL succeed and write provenance

#### Scenario: Missing input root is a warning, not an error
- **WHEN** the staged refresh runs with a `MIGRATIONS_DIR` that does not exist
- **THEN** the pipeline SHALL warn that the root is absent and how to configure it
- **AND** the pipeline's error count SHALL be unchanged

#### Scenario: Present input still fails loudly on analyzer error
- **WHEN** `MIGRATIONS_DIR` contains `*.sql` files and the analyzer exits non-zero
- **THEN** the stage SHALL be recorded as failed
- **AND** promotion SHALL be blocked

### Requirement: Optional-tool resolution is per-analyzer

The interpreter resolver SHALL report which optional grammars a candidate interpreter can
import, and each pipeline stage SHALL run when its own required grammars are available,
independent of grammars other stages require. Provenance SHALL record optional-tool
identity per grammar, and the resolver used by the pipeline SHALL be the same one whose
answer provenance records.

#### Scenario: SQL grammar absence does not disable Python enrichment
- **WHEN** the interpreter can import `tree_sitter` and `tree_sitter_python` but not `tree_sitter_sql`
- **THEN** the tree-sitter SQL analyzer SHALL be skipped
- **AND** the Python enrichment, comment-linker, and pattern-reporter stages SHALL run

#### Scenario: Provenance and pipeline agree per grammar
- **WHEN** the staged refresh promotes
- **THEN** provenance `optional_tools` SHALL list each grammar with its availability
- **AND** each stage recorded as run SHALL have had its required grammars listed as available

#### Scenario: No grammars available skips all tree-sitter stages
- **WHEN** no candidate interpreter can import `tree_sitter`
- **THEN** every tree-sitter stage SHALL be skipped
- **AND** the regex analyzers SHALL still run

### Requirement: ORM metadata is an optional SQL schema source

The pipeline SHALL support an opt-in schema source that emits `CreateTable` DDL for every
table in a configured SQLAlchemy `MetaData` into the staging directory, and SHALL feed
that output to the SQL analyzers as if it were a migrations directory. The default schema
source SHALL remain the migrations directory. The ORM source SHALL require no database
connection.

#### Scenario: Alembic repository gets a SQL schema analysis
- **WHEN** `SCHEMA_SOURCE=sqlalchemy` is configured with an importable `MetaData` target
- **THEN** the pipeline SHALL emit one DDL file containing every declared table
- **AND** the SQL analyzers SHALL produce a Postgres analysis from it
- **AND** no database connection SHALL be opened

#### Scenario: Unimportable metadata skips the source
- **WHEN** `SCHEMA_SOURCE=sqlalchemy` is configured and the `MetaData` target cannot be imported
- **THEN** the schema source SHALL be recorded as skipped with the import error
- **AND** the pipeline SHALL continue and promote

#### Scenario: Default is unchanged
- **WHEN** `SCHEMA_SOURCE` is unset
- **THEN** the pipeline SHALL read `MIGRATIONS_DIR` exactly as before
