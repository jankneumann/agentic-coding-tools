## ADDED Requirements

### Requirement: Deterministic File Selection Before Packet Rendering

The review packet builder SHALL run a pure selection function over every
changed file before rendering the packet body. The function SHALL apply gates
in this order: `binary`, `user_exclude`, `user_include` (which keeps the file
and skips the remaining gates), `generated_path` (vendored, lockfile,
snapshot, and generated-code patterns from a contracted default list),
`deleted`, and `too_large` (the file's estimated tokens alone exceed the
per-file ceiling). Every decision SHALL carry the path, the reason enum, and
the estimated token count. The function SHALL NOT read git, the network, or
the model; it SHALL be callable with an in-memory diff list.

#### Scenario: Excluded file is recorded with a reason

- **WHEN** a changed file matches the default generated-path list (for
  example `**/*.lock` or `**/__snapshots__/**`)
- **THEN** the file SHALL be absent from the packet diff
- **AND** `review-packet.meta.json` SHALL list the path under `selection.excluded`
  with `reason: generated_path`

#### Scenario: Include overrides a default exclusion

- **WHEN** a project rule file declares `include: ["skills/tests/**"]`
- **AND** a changed file under `skills/tests/` would otherwise match a default
  test-file pattern
- **THEN** the file SHALL be selected
- **AND** the decision SHALL record `reason: none` and `gate: user_include`

#### Scenario: Oversized file is excluded before truncation

- **WHEN** one changed file's estimated tokens exceed the per-file ceiling
- **THEN** that file SHALL be excluded with `reason: too_large`
- **AND** the remaining selected files SHALL be rendered in full
- **AND** the character-budget tail truncation SHALL apply only if the
  selected set still exceeds the packet budget

#### Scenario: No file is dropped without a reason

- **WHEN** the packet is built for any diff
- **THEN** the count of changed files SHALL equal the count of selected files
  plus the count of excluded files in `selection`
- **AND** every excluded entry SHALL have a non-empty reason from the enum

### Requirement: Preview Parity For File Selection

The packet builder SHALL expose a preview mode that returns the selection
decisions without rendering a packet, writing a round directory, or
dispatching. Preview and build SHALL obtain their decisions from the same
function call so the two cannot diverge.

#### Scenario: Preview matches the real build

- **WHEN** preview and build run over the same diff and rule file
- **THEN** the two selection decision lists SHALL compare equal
- **AND** preview SHALL create no files under `.review-cache/`

### Requirement: Ingest-Time Line Resolution From Verbatim Snippet

The dispatcher SHALL resolve `line_range` for any finding that carries
`existing_code` and lacks a usable `line_range`, after schema validation and
before checkpointing. Resolution SHALL parse the packet diff into hunks,
normalize whitespace and leading diff markers on both sides, and match the
snippet's non-blank lines as a consecutive run on the new side of each hunk,
then the old side, then the full new-file content when available. A finding
whose snippet does not match SHALL be kept with `line_range` absent and
SHALL be counted in the manifest as unanchored. Resolution SHALL NOT call a
model.

#### Scenario: Snippet resolves to new-side lines

- **WHEN** a finding carries `existing_code` equal to two consecutive added
  lines in the packet diff
- **THEN** `line_range.start` and `line_range.end` SHALL equal those lines'
  new-file numbers
- **AND** the finding SHALL record `line_resolution: hunk_new`

#### Scenario: Snippet matches only old-side lines

- **WHEN** a finding's snippet appears only among deleted or context lines on
  the old side
- **THEN** `line_range` SHALL be set from old-file numbers
- **AND** the finding SHALL record `line_resolution: hunk_old`

#### Scenario: Unmatched snippet is kept, not dropped

- **WHEN** a finding's snippet matches nowhere in the diff or file
- **THEN** the finding SHALL remain in the payload with `line_range` absent
- **AND** the manifest SHALL increment `unanchored_findings` for that vendor

#### Scenario: Vendor-supplied line range wins

- **WHEN** a finding already carries a non-zero `line_range`
- **THEN** the resolver SHALL leave it unchanged

### Requirement: Path-Glob Rule Groups In The Review Packet

The packet builder SHALL resolve one checklist rule per selected file from a
layered rule configuration: a project file at `<repo>/.review-rules.json`
over an embedded default sidecar shipped beside the builder. Within a layer,
entries SHALL be evaluated in declaration order and the first matching glob
SHALL win. Files that resolve to the same source, pattern, and rule text
SHALL be rendered under one rule group in the packet so the text appears
once. The schema-derived prompt contract SHALL remain present and unchanged;
rule groups add focus and do not replace the contract.

#### Scenario: Files sharing a rule are grouped

- **WHEN** three selected files all match `skills/**/scripts/*.py`
- **THEN** the packet SHALL contain one rule group listing the three paths
- **AND** the rule text SHALL appear exactly once

#### Scenario: Project rule outranks the embedded default

- **WHEN** the project file declares a rule for `agent-coordinator/**/*.yaml`
- **AND** the embedded default also matches that path
- **THEN** the project rule text SHALL be used
- **AND** the group SHALL record `source: project`

#### Scenario: No rule file present

- **WHEN** `<repo>/.review-rules.json` does not exist
- **THEN** the packet SHALL still build using the embedded default layer
- **AND** unmatched files SHALL fall to the default entry

### Requirement: Per-Vendor Coverage Contract

A vendor findings payload MAY carry a `coverage` block listing files reviewed
and files skipped with reasons. The dispatcher SHALL compute a coverage rate
against the packet's selected file list and record it in the round manifest.
When the rate is below the contracted threshold, the vendor SHALL NOT count
toward quorum for findings on files it did not review, and the manifest SHALL
record `coverage_eligibility: partial`. A payload without a `coverage` block
SHALL be treated as full coverage and the manifest SHALL record
`coverage: unreported`.

#### Scenario: Partial coverage limits quorum eligibility

- **WHEN** a vendor reports reviewing four of ten selected files
- **THEN** its manifest entry SHALL show `coverage_rate: 0.4`
- **AND** the synthesizer SHALL exclude that vendor from the quorum count for
  findings whose `file_path` is among the six unreviewed files

#### Scenario: Missing coverage block does not penalize

- **WHEN** a vendor payload has no `coverage` block
- **THEN** the vendor SHALL count toward quorum on every file
- **AND** the manifest SHALL record `coverage: unreported`

#### Scenario: Skipped file needs a reason

- **WHEN** a vendor lists a file under `coverage.skipped` without a reason
- **THEN** coercion SHALL fill `reason: unspecified`
- **AND** the manifest SHALL count it as skipped

### Requirement: Diff-Grounded Fact Check Before Synthesis

For each successful vendor result, the convergence loop SHALL run one
fact-check model call on the vendor's economy tier over the packet diff and
that vendor's validated findings. The pass SHALL remove a finding only on two
grounds: the code it describes is absent from its subject file's diff, or a
specific diff line literally contradicts its central claim. Findings whose
subject is memory safety, concurrency, declaration consistency, behavioral or
compatibility change, or an unused parameter SHALL never be removed. Every
removal SHALL be written to a decision file in the round directory with the
finding id, the ground, and the disproving line. The raw vendor payload SHALL
be checkpointed before the pass runs. Fact-check token usage SHALL be added
to the round budget and reported in the manifest. When the call fails or
times out, nothing SHALL be removed and the manifest SHALL record
`fact_check: skipped`.

#### Scenario: Provably wrong finding is removed with evidence

- **WHEN** a finding claims an identifier is unused
- **AND** a line in the packet diff uses that identifier
- **THEN** the finding SHALL be absent from the set passed to synthesis
- **AND** `fact-check-decisions.json` SHALL record the finding id, ground B,
  and the diff line

#### Scenario: Protected subject survives a wrong verdict

- **WHEN** a finding concerns a data race
- **AND** the fact-check model reports it as contradicted
- **THEN** the finding SHALL still be passed to synthesis
- **AND** the decision file SHALL record `vetoed: protected_subject`

#### Scenario: Fact-check failure removes nothing

- **WHEN** the fact-check call errors or exceeds its timeout
- **THEN** the vendor's full validated findings SHALL be passed to synthesis
- **AND** the manifest entry SHALL record `fact_check: skipped` with the error class

#### Scenario: Removal is never silent

- **WHEN** any finding is removed by the pass
- **THEN** the checkpointed raw vendor file SHALL still contain it
- **AND** the manifest SHALL report `fact_check_removed` for that vendor

### Requirement: Optional OCR Reviewer Vendor

`agents.yaml` MAY declare an `ocr` reviewer whose review mode invokes
`alibaba/open-code-review` through an adapter script that emits a
review-findings payload. The vendor SHALL be discoverable at Tier 1 only when
the `ocr` binary is on PATH and its LLM configuration is present; otherwise
discovery SHALL skip it with the standard Tier-3 line and no other change to
dispatch. OCR categories and severities SHALL be mapped through the coercion
sidecar. OCR findings SHALL carry `existing_code` and resolved lines from
the adapter and SHALL be ingested with `evidence_class: judgment`.

#### Scenario: OCR absent leaves dispatch unchanged

- **WHEN** `ocr` is not on PATH
- **THEN** `discover_reviewers` SHALL list it as unavailable
- **AND** the set of dispatched vendors SHALL equal today's set

#### Scenario: OCR output is coerced and validated

- **WHEN** the adapter returns a comment with `category: bug` and
  `severity: high`
- **THEN** coercion SHALL yield `type: correctness`, `axis: correctness`,
  `criticality: high`, `severity: critical`
- **AND** schema validation SHALL pass

#### Scenario: OCR positioning failure is unanchored, not fatal

- **WHEN** an OCR comment reports `start_line: 0` and `end_line: 0`
- **THEN** the adapter SHALL omit `line_range` and keep `existing_code`
- **AND** the ingest resolver SHALL attempt resolution as for any vendor

### Requirement: Labeled Review Fixture Set

The repository SHALL carry a committed fixture manifest of at least ten
findings over real diffs, each labeled `true` or `false` with a one-line
justification, under the parallel-infrastructure test tree. Tests SHALL
compute fact-check precision and line-resolution rate against the manifest
and SHALL fail when a labeled-true finding is removed or the resolution rate
drops below the contracted floor.

#### Scenario: True finding removal fails the suite

- **WHEN** the fact-check pass removes a fixture finding labeled `true`
- **THEN** the fixture test SHALL fail naming the finding id

#### Scenario: Resolution floor is enforced

- **WHEN** fewer than ninety percent of fixture findings with `existing_code`
  resolve to a line range
- **THEN** the fixture test SHALL fail with the measured rate

## MODIFIED Requirements

### Requirement: Review Packet As Default Input

The dispatcher and `converge()` SHALL build a review packet before dispatch
containing: the schema-derived prompt contract, the selected-file diff (unified
on round 1 or last-fix on later rounds), rule groups for the selected files,
traced spec excerpts, and open ledger items when a ledger exists. Selection
SHALL run before rendering and its decisions SHALL be written to the packet
metadata. The packet SHALL be written to the round directory with a checksum.
When the packet is under the contracted size budget, the prompt SHALL tell
the reviewer the packet is complete and not to explore the repo for missing
artifacts. Character-budget truncation SHALL apply only after selection and
per-file ceilings, and the metadata SHALL record which files were truncated.

#### Scenario: Packet includes diff and schema contract

- **WHEN** a review round is dispatched
- **THEN** the round directory SHALL contain a packet file whose body includes
  a diff hunk header or an explicit empty-diff marker
- **AND** includes the required finding fields from the canonical schema

#### Scenario: Missing ledger still builds a packet

- **WHEN** `.review-ledger/` is absent
- **THEN** the packet SHALL still be built from diff, specs, and schema
  contract
- **AND** dispatch SHALL proceed

#### Scenario: Over-budget packet sets tools overflow

- **WHEN** the packet body exceeds the contracted size budget after selection
- **THEN** the packet metadata SHALL set `tools_overflow` true
- **AND** the prompt SHALL allow Read/Grep to recover truncated context
- **AND** the metadata SHALL list the truncated file paths

#### Scenario: Packet metadata carries selection and rule groups

- **WHEN** a packet is built
- **THEN** `review-packet.meta.json` SHALL contain a `selection` object with
  `selected`, `excluded`, and `truncated` lists
- **AND** a `rule_groups` list naming each group's source, pattern, and files

### Requirement: Review Findings Schema Extension

The schema at `openspec/schemas/review-findings.schema.json` (mirrored at
`skills/parallel-infrastructure/install_assets/openspec/schemas/review-findings.schema.json`
and injected into `agent-coordinator/agents.yaml` by sentinel) SHALL encode an
8-axis review categorization and the 5 severity prefixes.

The schema SHALL define:

- An `axis` field on each finding with enum values: `correctness`, `readability`,
  `architecture`, `security`, `performance`, `observability`, `resilience`,
  `compatibility`
- A `severity` field on each finding with enum values: `critical`, `nit`, `optional`,
  `fyi`, `none`
- An optional `existing_code` string on each finding: a verbatim excerpt of
  one or more consecutive lines from the reviewed diff that the finding
  targets
- An optional `line_resolution` enum on each finding: `vendor`, `hunk_new`,
  `hunk_old`, `file`, `unresolved`
- An optional top-level `coverage` object with `reviewed` (array of paths),
  `skipped` (array of `{path, reason}`), and `rate` (number 0 to 1)

`axis` and `severity` SHALL be required for new findings. Findings produced
before this change SHALL be migratable by setting `axis: "correctness"` and
`severity: "fyi"` as defaults. The new fields SHALL be optional so every
existing emitter remains valid. All copies of the schema (canonical,
install-assets mirror, sentinel-injected) SHALL carry the identical enums.

#### Scenario: New finding includes axis and severity

**WHEN** a parallel-review skill produces a finding
**THEN** the finding JSON SHALL include both `axis` and `severity` fields
**AND** the values SHALL match the schema enums

#### Scenario: NFR axes accepted by the schema

**WHEN** a finding with `axis` set to `observability`, `resilience`, or `compatibility`
is validated against the schema
**THEN** validation SHALL pass

#### Scenario: Schema validation rejects missing fields

**WHEN** a finding without `axis` or `severity` is validated against the updated schema
**THEN** validation SHALL fail with a clear error identifying the missing field

#### Scenario: Existing schema fields preserved

**WHEN** the updated schema is loaded
**THEN** all pre-existing required fields SHALL remain required
**AND** all pre-existing enum values SHALL remain valid

#### Scenario: Schema copies stay identical

**WHEN** the canonical schema, the install-assets mirror, and the sentinel-injected
copy are compared
**THEN** the `axis` and `severity` enums SHALL be identical across all three

#### Scenario: Snippet and coverage are optional

**WHEN** a finding without `existing_code` and a payload without `coverage`
are validated
**THEN** validation SHALL pass
**AND** a payload carrying both SHALL also pass

### Requirement: Finding Coercion Before Validation

The dispatcher SHALL apply a contracted alias table to a parsed findings
payload before schema validation. Coercion SHALL NOT invent findings. Coercion
SHALL be logged. After coercion, schema validation remains mandatory and
fail-closed. The alias table SHALL include the OCR category and severity
vocabularies. Line resolution and the fact-check pass SHALL run only after
validation succeeds and SHALL never change a finding's schema validity.

#### Scenario: Known type alias is coerced

- **WHEN** a vendor finding has `"type": "bug"`
- **THEN** coercion SHALL set `type` to `correctness`
- **AND** the wrapper SHALL record that a coercion occurred
- **AND** schema validation SHALL then pass for that field

#### Scenario: Iterate-on-plan axis rejected as type is coerced

- **WHEN** a vendor finding has `"type": "completeness"` or `"type": "testability"`
- **THEN** coercion SHALL replace `type` with a legal review-findings `type`
  enum value and SHALL set `axis` to `architecture` (completeness) or
  `correctness` (testability) when `axis` is missing
- **AND** schema validation SHALL NOT fail solely because of the original
  illegal `type`

#### Scenario: Missing severity filled from criticality

- **WHEN** a finding has `criticality` but omits `severity`
- **THEN** coercion SHALL fill `severity` from the contracted map
- **AND** the reverse fill SHALL apply when `severity` is present and
  `criticality` is omitted

#### Scenario: Unknown enum still fails closed

- **WHEN** a finding has `"type": "not-a-real-type"` that is not in the alias
  table
- **THEN** schema validation SHALL fail
- **AND** the dispatcher SHALL proceed to the repair retry rather than
  accepting the payload

#### Scenario: OCR vocabulary is coerced

- **WHEN** a finding has `"type": "maintainability"` or `"type": "documentation"`
- **THEN** coercion SHALL map them to `architecture` and `style` respectively
- **AND** an OCR `severity: high` SHALL coerce to `criticality: high` and
  `severity: critical`

### Requirement: Cross-Vendor Finding Matching

Findings SHALL be matched across vendors using axis, file location, verbatim
snippet, finding type, and description similarity. Axis SHALL remain a hard
gate. When both findings carry `existing_code` and the normalized snippets
are equal, the pair SHALL score in the highest band regardless of line
numbers, because a shared verbatim excerpt is stronger evidence than vendor
line arithmetic.

#### Scenario: Match identical findings

- GIVEN Codex finding: security issue at `src/api.py:42`
- AND grok finding: security issue at `src/api.py:42`
- WHEN the matching algorithm runs
- THEN the findings are matched with high confidence (score >= 0.8)

#### Scenario: Equal snippets match despite drifted lines

- **GIVEN** two findings on the same file and axis whose `existing_code`
  normalize to the same text
- **AND** their `line_range` values do not overlap
- **WHEN** the matching algorithm runs
- **THEN** the score SHALL be at least 0.9 with basis `snippet`

### Requirement: Gate-Time Review Ledger

The convergence loop SHALL persist findings to
`openspec/changes/<change-id>/.review-ledger/ledger.json` with statuses
`open`, `addressed`, `retired`, and `parked`. Each item SHALL have a stable
id that survives rounds. New consensus findings SHALL merge into an existing
id when the synthesizer match score meets the threshold or the fingerprint
matches. The fingerprint SHALL be computed from axis, normalized path, and
the normalized `existing_code` snippet when present; it SHALL fall back to
the description token set when no snippet is present, so existing ledgers
keep their ids.

#### Scenario: Same defect keeps its id

- **WHEN** round 2 synthesizes a finding that matches a round-1 ledger item
- **THEN** the ledger SHALL keep the same `id`
- **AND** SHALL update `last_seen_round` to 2

#### Scenario: Ledger created on first round

- **WHEN** `converge()` runs and `.review-ledger/` does not exist
- **THEN** the directory and `ledger.json` SHALL be created
- **AND** the loop SHALL NOT fail solely because the ledger was absent

#### Scenario: Snippet fingerprint is stable across rewording

- **GIVEN** a round-1 item with `existing_code`
- **WHEN** round 2 produces a finding with the same path, axis, and snippet
  but a differently worded description
- **THEN** the fingerprints SHALL match
- **AND** the ledger SHALL keep the same `id`

### Requirement: Compact Before New Hunt

Before dispatching round N>1, the loop SHALL compact the ledger against
current `HEAD`. For an item with `existing_code`, presence SHALL mean the
normalized snippet still occurs in `file_path`; for an item without a
snippet, presence SHALL mean the description tokens still appear in the file
or line window. The loop SHALL retire items whose file is gone or whose
evidence is no longer present, and SHALL return `addressed` items to `open`
when the evidence remains.

#### Scenario: Fixed finding is retired

- **GIVEN** an open finding whose description tokens no longer appear in
  `file_path`
- **WHEN** compact runs
- **THEN** the item status SHALL be `retired`

#### Scenario: Claimed fix that did not take reopens

- **GIVEN** an `addressed` finding whose tokens still appear in `file_path`
- **WHEN** compact runs
- **THEN** the item status SHALL be `open`

#### Scenario: Snippet presence decides for anchored items

- **GIVEN** an `addressed` item whose `existing_code` still occurs verbatim
  in `file_path` after normalization
- **WHEN** compact runs
- **THEN** the item SHALL return to `open` with resolution
  `compact: snippet still present`
- **AND** an open item whose snippet no longer occurs SHALL be `retired`

### Requirement: Review Manifest Generation

The review dispatcher SHALL produce a `reviews/review-manifest.json` file
capturing dispatch metadata: which vendors were requested, which responded,
timing, model used, quorum status, error summaries for failed vendors, the
packet selection summary (selected, excluded with reasons, truncated), and
per-vendor `coverage_rate`, `coverage_eligibility`, `unanchored_findings`,
`fact_check` status, `fact_check_removed`, and fact-check token usage.

#### Scenario: Manifest after mixed success

- GIVEN Codex review succeeded and grok review failed with 429
- WHEN the dispatcher completes
- THEN `reviews/review-manifest.json` contains entries for both vendors
- AND the Codex entry shows success=true with findings_count and elapsed_seconds
- AND the grok entry shows success=false with error_class="capacity_exhausted" and the models attempted

#### Scenario: Provider billing error behind a zero exit code

- GIVEN a vendor CLI that exits 0 while the provider refused the request (pi on OpenRouter HTTP 402 "Insufficient credits")
- WHEN the dispatcher fails to parse findings from stdout
- THEN it SHALL classify the raw output before reporting a format failure, yielding error_class="vendor_unavailable" for billing/credit errors
- AND it SHALL NOT attempt model fallback for that vendor (the error is account-scoped, not model-scoped)
- AND the result error SHALL carry an excerpt of the raw output, so no vendor output is silently discarded

#### Scenario: Declared CLI credential missing

- GIVEN an agent whose `cli` config declares `api_key_env` (pi declares `OPENROUTER_API_KEY`)
- WHEN reviewer discovery or `--check-vendors` runs with that variable unset
- THEN the vendor SHALL NOT be counted as available, even though the binary is on PATH

#### Scenario: Manifest carries selection and per-vendor quality fields

- **WHEN** a round completes with one file excluded as `too_large` and one
  vendor's fact-check removing two findings
- **THEN** the manifest `selection.excluded` SHALL list that file with its reason
- **AND** that vendor's entry SHALL show `fact_check: ran`,
  `fact_check_removed: 2`, and a non-zero `fact_check_tokens`
