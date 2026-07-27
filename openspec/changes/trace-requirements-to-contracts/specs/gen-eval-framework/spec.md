## ADDED Requirements

### Requirement: Contracted operations cite the requirements they serve

A contracted operation SHALL cite zero or more requirement identifiers naming
the requirements it exists to serve. Citations SHALL be written into the
contract by its author and SHALL NOT be inferred from operation names, paths, or
prose similarity.

Inference has one failure mode and it is fatal: a plausible-looking match makes
the gate report green on a mapping nobody agreed with, which is worse than no
gate. The citation is a claim a human makes at the moment they design the
operation.

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
- **AND** the failure SHALL name both the unresolved identifier and the
  candidate requirement headings in that capability

### Requirement: Requirement identifiers are stable and fail closed

The framework SHALL derive a requirement identifier from its capability and the
slug of its heading. Reworded headings SHALL break citations to them rather than
silently rebinding to the nearest match.

A broken citation is an accurate signal that the requirement changed. Fuzzy
re-matching would silently rebind the citation to whatever heading now looks
closest, which is the inference this capability forbids, reintroduced through
the back door.

<!-- Scenario ID: gen-eval-framework.identifier-derivation -->
#### Scenario: An identifier is derived from the heading

- **WHEN** the resolver reads a capability's spec
- **THEN** each requirement SHALL be addressable as
  `<capability>.<slug-of-heading>`
- **AND** the derived identifiers SHALL be stable across runs for unchanged
  headings

<!-- Scenario ID: gen-eval-framework.reworded-heading-fails-closed -->
#### Scenario: A reworded heading breaks its citations

- **WHEN** a requirement's heading is reworded and a citation still names the
  previous identifier
- **THEN** the gate SHALL fail
- **AND** it SHALL NOT rebind the citation to the reworded requirement

### Requirement: Traceability completeness is enforced in both directions

The framework SHALL fail when a contracted operation cites no requirement and
carries no exclusion, and SHALL fail when a requirement is cited by no operation
and carries no exclusion.

The reverse direction is the one nothing else detects. The coverage model
measures the declared surface against scenarios and cannot see a requirement
that never became an operation; the drift guards compare artifacts to contracts.
A requirement nobody built has no diff, so review does not reliably catch it
either.

<!-- Scenario ID: gen-eval-framework.forward-completeness -->
#### Scenario: An uncited operation fails the gate

- **WHEN** a traced contract declares an operation that cites no requirement and
  carries no exclusion
- **THEN** the gate SHALL fail naming that operation
- **AND** a proportion of operations traced SHALL NOT satisfy the gate in its
  place

<!-- Scenario ID: gen-eval-framework.reverse-completeness -->
#### Scenario: An uncited requirement fails the gate

- **WHEN** a requirement in a traced capability is cited by no operation and
  carries no exclusion
- **THEN** the gate SHALL fail naming that requirement

<!-- Scenario ID: gen-eval-framework.every-failure-is-named -->
#### Scenario: Every failure is reported in one run

- **WHEN** a run finds several uncited operations and several uncited
  requirements
- **THEN** the gate SHALL report all of them
- **AND** it SHALL NOT stop at the first

### Requirement: Traceability exclusions state a reason

An exclusion SHALL carry a non-blank reason. An exclusion naming an operation or
requirement that no longer exists SHALL fail the gate.

An unexplained exclusion is how a gap gets laundered into "intentional". A stale
exclusion is worse here than for coverage units, because requirements outlive
operations: an exclusion for a deleted requirement keeps a slot warm for the
next requirement to reuse the slug, which inherits an approval nobody granted it.

<!-- Scenario ID: gen-eval-framework.blank-reason-fails -->
#### Scenario: A blank reason fails the gate

- **WHEN** an exclusion carries an empty or whitespace-only reason
- **THEN** the gate SHALL fail naming that exclusion

<!-- Scenario ID: gen-eval-framework.stale-exclusion-fails -->
#### Scenario: A stale exclusion fails the gate

- **WHEN** an exclusion names a requirement identifier or operation that no
  longer exists
- **THEN** the gate SHALL fail naming that exclusion

### Requirement: Traceability enforcement is opt-in per contract

A contract declaring a traceability block on any operation SHALL be enforced
strictly across all of its operations. A contract declaring none SHALL be
recorded as untraced and SHALL NOT fail the gate.

Keying enforcement on the block's presence makes the decision one-way. A
contract cannot report green while most of it is unattributed, and a contract
that has not opted in is visible in the report rather than silent.

<!-- Scenario ID: gen-eval-framework.opting-in-is-total -->
#### Scenario: Declaring traceability commits the whole contract

- **WHEN** a contract declares a traceability block on one operation and omits
  it on another
- **THEN** the gate SHALL fail for the operation that omits it

<!-- Scenario ID: gen-eval-framework.untraced-is-recorded -->
#### Scenario: A contract with no traceability is recorded, not failed

- **WHEN** a contract declares no traceability block on any operation
- **THEN** the gate SHALL record the contract as untraced
- **AND** the run SHALL NOT fail on that contract
- **AND** the untraced status SHALL appear in the gate's output

### Requirement: The gate reports concentration without failing on it

The framework SHALL report when a single requirement is cited by a
disproportionate share of a contract's operations, and SHALL NOT fail the run on
that basis alone.

Citing one catch-all requirement everywhere is the predictable way to defeat
this gate. The threshold between a requirement that genuinely governs many
operations and box-ticking is a judgement, and encoding it as a number would
fail honest contracts while a determined box-ticker spreads citations across two
requirements instead of one.

<!-- Scenario ID: gen-eval-framework.concentration-is-surfaced -->
#### Scenario: Concentration appears in the output

- **WHEN** one requirement is cited by a disproportionate share of a contract's
  operations
- **THEN** the gate SHALL name that requirement and the share in its output
- **AND** the run SHALL NOT fail on that basis alone

### Requirement: Citations may name requirements in another capability

A citation SHALL be permitted to name a requirement belonging to any capability.
The gate SHALL report cross-capability citations as a distinct list and SHALL
NOT fail on them.

Cross-capability operations already exist — one service may serve another
capability's requirement. Forbidding the citation would not remove the coupling;
it would make the only artifact that records it illegal, and force an exclusion
whose reason says the operation serves a requirement it may not name.

<!-- Scenario ID: gen-eval-framework.cross-capability-citation -->
#### Scenario: An operation cites another capability's requirement

- **WHEN** an operation in one capability's contract cites a requirement
  identifier carrying a different capability's prefix
- **THEN** the citation SHALL resolve against that capability's spec
- **AND** the gate SHALL NOT fail on the basis of the capability differing
- **AND** the gate SHALL name the citation in its cross-capability report

### Requirement: Completeness is evaluated per capability

The framework SHALL evaluate completeness across every contract citing into a
capability, taken together, rather than one contract at a time. Opt-in status
SHALL likewise be recorded per capability.

Because a requirement may be served by an operation in another capability's
contract, a per-contract evaluation reports genuinely-served requirements as
uncited, and the only available remedy is an exclusion asserting something
false.

<!-- Scenario ID: gen-eval-framework.capability-scoped-completeness -->
#### Scenario: A requirement served from another contract is covered

- **WHEN** a requirement is cited by an operation in a different contract of the
  same capability
- **THEN** reverse completeness SHALL treat that requirement as cited
- **AND** the gate SHALL NOT require a duplicate citation in every contract

<!-- Scenario ID: gen-eval-framework.split-contracts-are-unioned -->
#### Scenario: A capability's contracts are evaluated as one surface

- **WHEN** a capability declares several contract documents
- **THEN** the gate SHALL union their citations before evaluating completeness
- **AND** a capability whose contracts are split SHALL be evaluated identically
  to one whose contracts are combined

### Requirement: The active change's spec delta shadows the archived spec

The framework SHALL resolve requirement identifiers against the archived
capability specs, with the active change's spec delta taking precedence: added
requirements SHALL resolve, modified requirements SHALL resolve to the changed
form, and removed requirements SHALL NOT resolve. Requirements belonging to
other in-flight changes SHALL be neither citable nor excludable.

Every requirement a change adds exists only in its own delta until archive, so
resolving against the archive alone would fail every citation a change makes to
its own new requirements. Permitting references to *other* changes' unarchived
requirements is separately disallowed: when such a change archives, the
exclusion written against it silently suppresses a real finding while its target
exists, which no staleness check can detect.

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
already existed. A full-capability evaluation SHALL be available for scheduled
runs against the integration branch.

A validation run enforcing the full archived set blocks every change to a
capability on gaps it did not create, so adoption would require clearing all
pre-existing debt before any unrelated work could be validated.

<!-- Scenario ID: gen-eval-framework.pre-existing-gap-does-not-block -->
#### Scenario: A pre-existing gap does not fail a change that did not create it

- **WHEN** a change touches one operation in a capability that already contains
  uncited operations it does not touch
- **THEN** the gate SHALL fail only on the touched operation if it is uncited
- **AND** it SHALL report the untouched pre-existing gaps without failing

<!-- Scenario ID: gen-eval-framework.scope-is-stated-in-the-output -->
#### Scenario: The output states which scope it evaluated

- **WHEN** the gate completes a change-scoped run
- **THEN** its output SHALL state that the run was scoped to the change
- **AND** it SHALL NOT report completeness for the capability as a whole

### Requirement: The gate makes no claim that a requirement is satisfied

The gate SHALL establish only that each operation cites a requirement and each
requirement is cited, and SHALL NOT report or imply that a cited operation
satisfies the requirement it cites.

No static check can decide satisfaction, and output implying otherwise would be
an unfalsifiable green light over a correctness claim. Satisfaction is
established by scenarios, the coverage model, and review.

<!-- Scenario ID: gen-eval-framework.no-satisfaction-claim -->
#### Scenario: Output does not claim satisfaction

- **WHEN** the gate passes
- **THEN** its output SHALL state that operations cite requirements
- **AND** it SHALL NOT state or imply that requirements are implemented,
  satisfied, or verified
