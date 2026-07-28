## ADDED Requirements

### Requirement: Contracted operations cite the requirements they serve

A contracted operation SHALL cite one or more requirement identifiers naming
the requirements it exists to serve, or SHALL carry an exclusion with a stated
reason. Citations SHALL be written into the contract by its author and SHALL
NOT be inferred from operation names, paths, or prose similarity.

Inference has one failure mode and it is fatal: a plausible-looking match makes
the gate report green on a mapping nobody agreed with, which is worse than no
gate. The citation is a claim a human makes at the moment they design the
operation. An empty citation list is not permitted — it is an exclusion written
without a reason, spelled differently.

<!-- Scenario ID: gen-eval-framework.citation-is-declared -->
#### Scenario: An operation declares its citations

- **WHEN** a contract declares an operation with a `traceability` block naming
  one or more requirement identifiers
- **THEN** the framework SHALL record those identifiers against that operation
- **AND** it SHALL NOT add, remove, or reorder identifiers based on the
  operation's name or path

<!-- Scenario ID: gen-eval-framework.citation-resolves -->
#### Scenario: A citation names a requirement that exists

- **WHEN** an operation cites a requirement identifier
- **THEN** the identifier SHALL resolve to a requirement in the referenced
  capability's spec
- **AND** an identifier resolving to no requirement SHALL fail the gate
- **AND** the failure SHALL name the unresolved identifier and the nearest
  candidate requirement headings in that capability, bounded to at most five,
  ranked for display only — ranking SHALL NOT rebind the citation

### Requirement: Requirement identifiers are stable and fail closed

The framework SHALL derive a requirement identifier from its capability and the
slug of its heading, using one normative algorithm: Unicode-normalize (NFKD)
and drop non-ASCII marks, lowercase, replace each run of characters outside
`[a-z0-9]` with a single `-`, and strip leading and trailing `-`. Reworded
headings SHALL break citations to them rather than silently rebinding to the
nearest match. Two requirements in one capability deriving the same identifier
SHALL fail the resolver.

A broken citation is an accurate signal that the requirement changed. Fuzzy
re-matching would silently rebind the citation to whatever heading now looks
closest, which is the inference this capability forbids, reintroduced through
the back door. An undetected slug collision is worse: a citation to either
heading marks both requirements cited, and one requirement becomes permanently
invisible to reverse completeness with no signal at all.

<!-- Scenario ID: gen-eval-framework.identifier-derivation -->
#### Scenario: An identifier is derived from the heading

- **WHEN** the resolver reads a capability's spec
- **THEN** each requirement SHALL be addressable as
  `<capability>.<slug-of-heading>` under the normative slug algorithm
- **AND** every derived identifier SHALL match the citation pattern declared in
  `traceability.schema.json`
- **AND** the derived identifiers SHALL be stable across runs for unchanged
  headings

<!-- Scenario ID: gen-eval-framework.reworded-heading-fails-closed -->
#### Scenario: A reworded heading breaks its citations

- **WHEN** a requirement's heading is reworded and a citation still names the
  previous identifier
- **THEN** the gate SHALL fail
- **AND** it SHALL NOT rebind the citation to the reworded requirement

<!-- Scenario ID: gen-eval-framework.colliding-identifiers-fail -->
#### Scenario: Two headings deriving the same identifier fail the resolver

- **WHEN** two requirement headings in one capability derive the same
  identifier
- **THEN** the resolver SHALL fail naming both headings
- **AND** it SHALL NOT resolve citations to that identifier against either
  requirement

### Requirement: Traceability completeness is enforced in both directions

The framework SHALL fail when a contracted operation cites no requirement and
carries no exclusion, and SHALL fail when a requirement subject to reverse
enforcement is cited by no operation and carries no exclusion.

The reverse direction is the one nothing else detects. The coverage model
measures the declared surface against scenarios and cannot see a requirement
that never became an operation; the drift guards compare artifacts to contracts.
A requirement nobody built has no diff, so review does not reliably catch it
either.

<!-- Scenario ID: gen-eval-framework.forward-completeness -->
#### Scenario: An uncited operation fails the gate

- **WHEN** a traced contract declares ten operations of which nine cite a
  requirement and one cites nothing and carries no exclusion
- **THEN** the gate SHALL fail naming the uncited operation
- **AND** the gate SHALL NOT pass on the basis of the proportion of operations
  traced

<!-- Scenario ID: gen-eval-framework.reverse-completeness -->
#### Scenario: An uncited requirement fails the gate

- **WHEN** a requirement in a capability with reverse enforcement is cited by
  no operation and carries no exclusion
- **THEN** the gate SHALL fail naming that requirement

<!-- Scenario ID: gen-eval-framework.every-failure-is-named -->
#### Scenario: Every failure is reported in one run

- **WHEN** a run finds at least two uncited operations and at least two uncited
  requirements
- **THEN** the gate SHALL report all of them in a single run
- **AND** the number of findings reported SHALL equal the number of violations
- **AND** it SHALL NOT stop at the first

### Requirement: Traceability exclusions state a reason

An exclusion SHALL carry a non-blank reason. Operation exclusions SHALL be
written in the contract on the operation they exclude; requirement exclusions
SHALL be written in the capability's
`openspec/contracts/<capability>/traceability-exclusions.yaml`. An exclusion
naming an operation or requirement that no longer exists SHALL fail the gate.

An unexplained exclusion is how a gap gets laundered into "intentional". A
requirement with no operation has no operation to carry its exclusion, so the
reverse direction needs its own artifact — the same shape
`check_coverage_completeness.py` established for coverage units. A stale
exclusion is worse here than for coverage units, because requirements outlive
operations: an exclusion for a deleted requirement keeps a slot warm for the
next requirement to reuse the slug, which inherits an approval nobody granted
it.

<!-- Scenario ID: gen-eval-framework.blank-reason-fails -->
#### Scenario: A blank reason fails the gate

- **WHEN** an exclusion carries an empty or whitespace-only reason
- **THEN** the gate SHALL fail naming that exclusion

<!-- Scenario ID: gen-eval-framework.stale-exclusion-fails -->
#### Scenario: A stale exclusion fails the gate

- **WHEN** an exclusion names a requirement identifier or operation that no
  longer exists
- **THEN** the gate SHALL fail naming that exclusion

<!-- Scenario ID: gen-eval-framework.valid-operation-exclusion-suppresses -->
#### Scenario: An excluded operation does not fail forward completeness

- **WHEN** an operation carries an exclusion with a non-blank reason and cites
  no requirement
- **THEN** forward completeness SHALL NOT fail on that operation
- **AND** the exclusion and its reason SHALL appear in the gate's output

<!-- Scenario ID: gen-eval-framework.valid-requirement-exclusion-suppresses -->
#### Scenario: An excluded requirement does not fail reverse completeness

- **WHEN** a requirement is cited by no operation and the capability's
  exclusions file excludes it with a non-blank reason
- **THEN** reverse completeness SHALL NOT fail on that requirement
- **AND** the exclusion and its reason SHALL appear in the gate's output

### Requirement: Forward enforcement is opt-in per contract document

A contract document declaring a traceability block on any operation SHALL be
enforced strictly across all of its operations. A contract document declaring
none SHALL be recorded as untraced and SHALL NOT fail forward completeness.

Keying forward enforcement on the block's presence in the document makes the
decision one-way at the right grain. A document cannot report green while most
of it is unattributed, and a document that has not opted in is visible in the
report rather than silent. Splitting a capability's surface into several
documents stages the forward direction — each document opts in when its
subsystem is ready — without weakening any document that has opted in.

<!-- Scenario ID: gen-eval-framework.opting-in-is-total -->
#### Scenario: Declaring traceability commits the whole contract document

- **WHEN** a contract document declares a traceability block on one operation
  and omits it on another
- **THEN** the gate SHALL fail for the operation that omits it

<!-- Scenario ID: gen-eval-framework.untraced-is-recorded -->
#### Scenario: A contract with no traceability is recorded, not failed

- **WHEN** a contract document declares no traceability block on any operation
- **THEN** the gate SHALL record the document as untraced
- **AND** the run SHALL NOT fail on that document
- **AND** the untraced status SHALL appear in the gate's output

<!-- Scenario ID: gen-eval-framework.mixed-capability-documents -->
#### Scenario: A traced and an untraced document coexist in one capability

- **WHEN** a capability holds one contract document that has opted in and one
  that has not
- **THEN** forward completeness SHALL be enforced on the traced document only
- **AND** the untraced document SHALL be recorded as untraced
- **AND** the traced document's citations SHALL still count toward the
  capability's reverse completeness

### Requirement: Reverse enforcement is opt-in per capability via the exclusions file

Reverse completeness SHALL be enforced for a capability exactly when
`openspec/contracts/<capability>/traceability-exclusions.yaml` exists. For a
capability without that file, uncited requirements SHALL be reported and SHALL
NOT fail the gate. An exclusions file with an empty exclusion list SHALL be
valid and SHALL mean every requirement must be cited.

The two directions make different claims with different owners, so each gets
exactly one switch. Forward — "every operation in this document is justified" —
is a claim the document's author can make one document at a time. Reverse —
"every requirement of this capability is served or excused" — is a claim about
the whole capability that no single document can make. Creating the exclusions
file is the act of triaging the capability's requirement set, which is why the
file and the switch are the same artifact: the switch cannot be flipped without
doing the work it certifies.

<!-- Scenario ID: gen-eval-framework.reverse-opt-in-enforces -->
#### Scenario: The exclusions file's presence enforces reverse completeness

- **WHEN** a capability has a traceability-exclusions file and a requirement is
  cited by no operation and not excluded
- **THEN** the gate SHALL fail naming that requirement

<!-- Scenario ID: gen-eval-framework.reverse-not-opted-in-reports -->
#### Scenario: Without the exclusions file, uncited requirements are reported

- **WHEN** a capability has no traceability-exclusions file and a requirement
  is cited by no operation
- **THEN** the gate SHALL report that requirement as uncited
- **AND** the run SHALL NOT fail on it
- **AND** the capability's reverse status SHALL appear in the output as
  not opted in

### Requirement: The gate reports citation concentration deterministically

The gate SHALL emit, for every cited requirement in a capability, the count and
share of the capability's traced operations citing it, ordered by share
descending, and SHALL mark entries at or above a named reporting constant as
concentrated. The exit code SHALL NOT depend on concentration.

Citing one catch-all requirement everywhere is the predictable way to defeat
this gate. The threshold between a requirement that genuinely governs many
operations and box-ticking is a judgement, so concentration never fails a run —
but the *output* must be deterministic, or the test for it asserts the
implementation against itself. The denominator is the capability's traced
operations, not one document's: a per-document share would be defeated by
splitting the document.

<!-- Scenario ID: gen-eval-framework.concentration-is-surfaced -->
#### Scenario: Concentration appears in the output

- **WHEN** one requirement's share of a capability's traced operations meets or
  exceeds the reporting constant
- **THEN** the gate SHALL name that requirement, its count, and its share in
  the concentration section of its output

<!-- Scenario ID: gen-eval-framework.concentration-never-fails -->
#### Scenario: A run whose only finding is concentration exits zero

- **WHEN** a run's completeness checks all pass and one requirement exceeds the
  concentration reporting constant
- **THEN** the run SHALL exit zero
- **AND** the same concentration entry SHALL be present when an unrelated
  failure makes the run exit non-zero

### Requirement: Citations may name requirements in another capability

A citation SHALL be permitted to name a requirement belonging to any
capability. The gate SHALL report cross-capability citations as a distinct list
and SHALL NOT fail on the capability differing. A cross-capability citation
SHALL count toward the cited capability's reverse completeness.

Cross-capability operations already exist — one service may serve another
capability's requirement. Forbidding the citation would not remove the
coupling; it would make the only artifact that records it illegal. Crediting
the cited capability is what makes the record honest: the requirement *is*
served, and reporting it uncited would demand a false exclusion.

<!-- Scenario ID: gen-eval-framework.cross-capability-citation -->
#### Scenario: An operation cites another capability's requirement

- **WHEN** an operation in one capability's contract cites a requirement
  identifier carrying a different capability's prefix
- **THEN** the citation SHALL resolve against that capability's spec
- **AND** the gate SHALL NOT fail on the basis of the capability differing
- **AND** the gate SHALL name the citation in its cross-capability report

<!-- Scenario ID: gen-eval-framework.cross-capability-credits-reverse -->
#### Scenario: A cross-capability citation satisfies the cited capability's reverse completeness

- **WHEN** capability B's requirement is cited only by an operation in
  capability A's contract
- **THEN** B's reverse completeness SHALL treat that requirement as cited

<!-- Scenario ID: gen-eval-framework.cross-capability-unresolvable-fails -->
#### Scenario: An unresolvable cross-capability citation fails

- **WHEN** a citation names an identifier whose capability prefix matches no
  capability spec, or whose slug matches no requirement in that capability
- **THEN** the gate SHALL fail naming the citation
- **AND** the failure SHALL distinguish an unknown capability from an unknown
  requirement within a known capability

### Requirement: Completeness is evaluated per capability

The framework SHALL evaluate completeness across every contract document citing
into a capability, taken together, rather than one document at a time.

Because a requirement may be served by an operation in another document — or
another capability's document — a per-document evaluation reports
genuinely-served requirements as uncited, and the only available remedy is an
exclusion asserting something false.

<!-- Scenario ID: gen-eval-framework.capability-scoped-completeness -->
#### Scenario: A requirement served from another contract is covered

- **WHEN** a requirement is cited by an operation in a different contract
  document of the same capability
- **THEN** reverse completeness SHALL treat that requirement as cited
- **AND** the gate SHALL NOT require a duplicate citation in every document

<!-- Scenario ID: gen-eval-framework.split-contracts-are-unioned -->
#### Scenario: A capability's contracts are evaluated as one surface

- **WHEN** a capability declares several contract documents
- **THEN** the gate SHALL union their citations before evaluating completeness
- **AND** a capability whose contracts are split SHALL be evaluated identically
  to one whose contracts are combined

<!-- Scenario ID: gen-eval-framework.union-does-not-hide-gaps -->
#### Scenario: A requirement cited by no document still fails

- **WHEN** a capability with reverse enforcement declares two contract
  documents and a requirement is cited by neither and excluded by neither
- **THEN** the gate SHALL fail naming that requirement exactly once
- **AND** it SHALL NOT report the gap once per document

### Requirement: The active change's spec delta shadows the archived spec

The framework SHALL resolve requirement identifiers against the archived
capability specs, with the active change's spec delta taking precedence: added
requirements SHALL resolve, modified requirements SHALL resolve to the changed
form, removed requirements SHALL NOT resolve, and renamed requirements SHALL
resolve under the new identifier only. Requirements belonging to other
in-flight changes SHALL be neither citable nor excludable.

Every requirement a change adds exists only in its own delta until archive, so
resolving against the archive alone would fail every citation a change makes to
its own new requirements. Permitting references to *other* changes' unarchived
requirements is separately disallowed: when such a change archives, the
exclusion written against it silently suppresses a real finding while its
target exists, which no staleness check can detect. RENAMED sections matter
because ignoring them fails open — the old identifier keeps resolving out of
the archive while the new one resolves to nothing, both wrong in opposite
directions.

<!-- Scenario ID: gen-eval-framework.added-requirement-resolves -->
#### Scenario: A citation to the change's own new requirement resolves

- **WHEN** the active change adds a requirement and an operation cites it
- **THEN** the identifier SHALL resolve
- **AND** the gate SHALL NOT fail on the requirement being unarchived

<!-- Scenario ID: gen-eval-framework.removed-requirement-stops-resolving -->
#### Scenario: Removing a requirement breaks operations that still cite it

- **WHEN** the active change removes a requirement and an operation still cites
  it
- **THEN** the identifier SHALL NOT resolve
- **AND** the gate SHALL fail naming the operation

<!-- Scenario ID: gen-eval-framework.renamed-requirement-rebinds-closed -->
#### Scenario: Renaming a requirement moves its identifier, fail-closed

- **WHEN** the active change renames a requirement's heading, or modifies a
  requirement in a way that rewords its heading
- **THEN** the previous identifier SHALL NOT resolve
- **AND** the new identifier SHALL resolve
- **AND** a citation still naming the previous identifier SHALL fail, naming
  the new heading among the candidates

<!-- Scenario ID: gen-eval-framework.other-changes-are-invisible -->
#### Scenario: Another change's unarchived requirement cannot be referenced

- **WHEN** a citation or exclusion names a requirement that exists only in a
  different in-flight change's spec delta
- **THEN** the gate SHALL fail
- **AND** the failure SHALL state that the requirement is not in the effective
  requirement set

### Requirement: Validation-time evaluation is scoped to the change

At validation the framework SHALL evaluate only the operations and requirements
the active change touches, and SHALL report rather than fail on violations that
already existed. The touched set SHALL be: operations whose contract nodes
changed in the diff between the merge base and the working tree, requirements
added, modified, removed, or renamed in the active change's spec delta, and
requirements named by citations or exclusions the diff adds or changes. The
active change SHALL be named explicitly to the gate, the merge base SHALL be
computed against a named integration branch, and a merge base that cannot be
resolved SHALL be an error rather than an empty scope.

A validation run enforcing the full archived set blocks every change to a
capability on gaps it did not create. But a scope that silently resolves to
empty is worse than a broad one — a blocking gate that evaluates nothing while
reporting success is the unfalsifiable-green failure this whole change exists
to eliminate. Change scope restricts what the full evaluation would enforce; it
never enforces anything the full evaluation would not.

<!-- Scenario ID: gen-eval-framework.pre-existing-gap-does-not-block -->
#### Scenario: A pre-existing gap does not fail a change that did not create it

- **WHEN** a change touches one operation in a capability that already contains
  uncited operations it does not touch
- **THEN** the gate SHALL fail only on the touched operation if it is uncited
- **AND** it SHALL report the untouched pre-existing gaps without failing

<!-- Scenario ID: gen-eval-framework.change-scoped-reverse-completeness -->
#### Scenario: A requirement the change adds and nobody cites fails the change-scoped run

- **WHEN** the active change adds a requirement to a capability with reverse
  enforcement, and no operation cites it and no exclusion covers it
- **THEN** the change-scoped run SHALL fail naming that requirement

<!-- Scenario ID: gen-eval-framework.unresolvable-scope-errors -->
#### Scenario: An unresolvable merge base is an error, not an empty scope

- **WHEN** a change-scoped run cannot resolve the merge base against the
  integration branch, or is given no active change identifier
- **THEN** the run SHALL exit non-zero stating what could not be resolved
- **AND** it SHALL NOT pass by evaluating an empty touched set

<!-- Scenario ID: gen-eval-framework.scope-is-stated-in-the-output -->
#### Scenario: The output states which scope it evaluated

- **WHEN** the gate completes a change-scoped run
- **THEN** its output SHALL contain the line
  `scope: change (<change-id>) — touched operations and requirements only; capability completeness not evaluated`
- **AND** it SHALL NOT report completeness for the capability as a whole

### Requirement: The full sweep blocks opted-in surfaces and reports the rest

A full-capability evaluation SHALL run against the integration branch on every
push. It SHALL fail on violations in contract documents that have opted into
forward enforcement and in capabilities that have opted into reverse
enforcement, and SHALL report untraced documents and not-opted-in capabilities
without failing.

Diff-scoping alone would never surface accumulated gaps — nothing touches them,
so nothing reports them. The sweep is what makes existing debt visible without
blocking anyone, and opting in is the only switch that turns its report into a
block: a second reported-to-blocking flag would create an opted-in-but-not-
blocking state, which is the half-traced-yet-green outcome opt-in exists to
make impossible. The sweep runs on push, not on a schedule — a scheduled run
cannot block a merge.

<!-- Scenario ID: gen-eval-framework.sweep-blocks-opted-in -->
#### Scenario: An opted-in surface fails the sweep

- **WHEN** the full sweep finds an uncited operation in a traced document, or
  an uncited unexcluded requirement in a capability with reverse enforcement
- **THEN** the sweep SHALL exit non-zero naming the violation

<!-- Scenario ID: gen-eval-framework.sweep-reports-not-opted-in -->
#### Scenario: A surface that has not opted in is reported, not failed

- **WHEN** the full sweep encounters untraced contract documents and
  capabilities without reverse enforcement
- **THEN** it SHALL report each with its status
- **AND** it SHALL NOT fail on them

### Requirement: The gate fails closed on malformed input

A contract document that cannot be parsed SHALL fail the gate naming the file,
and SHALL NOT be recorded as untraced. A traceability block that violates the
traceability schema SHALL fail the gate naming the file and the offending
block. A capability directory containing contracts but no capability spec SHALL
fail with a message distinguishing the missing spec from an unresolved
identifier. A capability with a spec and no contracts SHALL be recorded as
untraced.

Enforcement is keyed on the presence of traceability blocks, so a parse error
that reads as "no blocks found" would silently downgrade a traced contract to
untraced and turn a syntax error into a green run. The schema-invalid shapes —
`requirements` and `excluded` together, or an empty citation list — were
excluded from the schema deliberately, and a gate that let them through would
have to pick a winner, which is the silent decision the schema exists to
refuse.

<!-- Scenario ID: gen-eval-framework.malformed-contract-fails -->
#### Scenario: An unparseable contract fails the gate

- **WHEN** a contract document under `openspec/contracts/` cannot be parsed
- **THEN** the gate SHALL exit non-zero naming the file
- **AND** the document SHALL NOT be recorded as untraced

<!-- Scenario ID: gen-eval-framework.schema-invalid-block-fails -->
#### Scenario: A schema-invalid traceability block fails the gate

- **WHEN** a traceability block carries both `requirements` and `excluded`, or
  an empty `requirements` list, or an exclusion without a reason field
- **THEN** the gate SHALL exit non-zero naming the file and the operation
  carrying the block
- **AND** it SHALL NOT choose between the conflicting keys

<!-- Scenario ID: gen-eval-framework.missing-capability-spec-fails -->
#### Scenario: Contracts without a capability spec fail distinctly

- **WHEN** a capability directory under `openspec/contracts/` contains contract
  documents but no `openspec/specs/<capability>/spec.md` exists
- **THEN** the gate SHALL fail stating that the capability has no spec
- **AND** the message SHALL be distinguishable from an unresolved identifier

<!-- Scenario ID: gen-eval-framework.spec-without-contracts-untraced -->
#### Scenario: A capability with a spec and no contracts is untraced

- **WHEN** a capability has a spec and no contract documents
- **THEN** the gate SHALL record it as untraced
- **AND** the run SHALL NOT fail on it

### Requirement: The gate makes no claim that a requirement is satisfied

The gate SHALL establish only that each operation cites a requirement and each
requirement is cited, and SHALL NOT report or imply that a cited operation
satisfies the requirement it cites. On success its output SHALL contain the
line `<N> operations cite <M> requirements. This gate does not check that any
requirement is satisfied.` and SHALL NOT apply the words `implemented`,
`satisfied`, or `verified` to a requirement as subject.

No static check can decide satisfaction, and output implying otherwise would be
an unfalsifiable green light over a correctness claim. Satisfaction is
established by scenarios, the coverage model, and review. The canonical line is
pinned so the wording test asserts the spec's phrase rather than freezing a
literal the test author invented.

<!-- Scenario ID: gen-eval-framework.no-satisfaction-claim -->
#### Scenario: Output does not claim satisfaction

- **WHEN** the gate passes
- **THEN** its output SHALL contain the canonical citation-claim line
- **AND** it SHALL NOT apply `implemented`, `satisfied`, or `verified` to a
  requirement as subject
