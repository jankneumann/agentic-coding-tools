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
An exclusions file SHALL only exclude requirements of its own capability; an
entry naming a requirement whose capability prefix is not the owning capability
SHALL fail the gate naming both capabilities.

Cross-capability *citations* are permitted (a citation adds a claim, and D9
reports them as a distinct list), but a cross-capability *exclusion* is
refused, because the two are not symmetric. A citation says "this operation
serves that requirement" — information the cited capability can audit. An
exclusion says "that requirement needs no operation at all", which discharges
an obligation the other capability owns and can neither see nor contest. That
is the laundering path D4 exists to close, arriving from outside.

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

<!-- Scenario ID: gen-eval-framework.cross-capability-exclusion-fails -->
#### Scenario: One capability cannot excuse another's requirement

- **WHEN** `openspec/contracts/<A>/traceability-exclusions.yaml` contains an
  exclusion whose requirement identifier resolves to capability `B`
- **THEN** the gate SHALL exit non-zero naming both `A` and `B`
- **AND** the excluded requirement SHALL still count against `B`'s reverse
  completeness

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

A change that flips an opt-in switch SHALL additionally touch everything that
switch newly governs. Where the diff adds a traceability block to a contract
document that had none, every operation in that document SHALL be touched.
Where the diff adds a `traceability-exclusions.yaml` for a capability that had
none, every requirement of that capability SHALL be touched.

A validation run enforcing the full archived set blocks every change to a
capability on gaps it did not create. But a scope that silently resolves to
empty is worse than a broad one — a blocking gate that evaluates nothing while
reporting success is the unfalsifiable-green failure this whole change exists
to eliminate. Change scope restricts what the full evaluation would enforce; it
never enforces anything the full evaluation would not.

The opt-in clause exists because the transition is otherwise invisible to a
node-level diff. Adding one traceability block changes one node, but D6 makes
the whole document strictly enforced from that moment; creating an exclusions
file changes no requirement at all, yet D13 turns the capability's entire
reverse direction blocking. Under a touched set keyed only on changed nodes,
`/validate-feature` would pass on the very change that flips the switch and
`main` would red immediately afterward — the gate reporting green on the one
diff that could still cheaply fix it. The switch-flipping change is precisely
the change that must prove the surface is clean, because it is the change
asserting that it is.

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

<!-- Scenario ID: gen-eval-framework.forward-opt-in-touches-document -->
#### Scenario: Opting a document in touches every operation in it

- **WHEN** the active change adds a traceability block to a contract document
  that previously declared none, and another operation in that same document
  cites no requirement and carries no exclusion
- **THEN** the change-scoped run SHALL fail naming that other operation
- **AND** it SHALL NOT pass on the grounds that the operation's node is
  unchanged in the diff

<!-- Scenario ID: gen-eval-framework.reverse-opt-in-touches-capability -->
#### Scenario: Opting a capability in touches every requirement of it

- **WHEN** the active change adds `traceability-exclusions.yaml` to a
  capability that previously had none, and a pre-existing requirement of that
  capability is cited by no operation and excluded by no entry
- **THEN** the change-scoped run SHALL fail naming that requirement
- **AND** the failure SHALL NOT be deferred to the full sweep on `main`

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

A full-capability evaluation SHALL run as a blocking check on the merge
candidate, and SHALL run again, explicitly non-blocking, on the integration
branch after merge. The blocking run SHALL fail on violations in contract
documents that have opted into forward enforcement and in capabilities that
have opted into reverse enforcement, and SHALL report untraced documents and
not-opted-in capabilities without failing.

The gate SHALL have exactly one resolution rule, keyed on whether a change id
is supplied. Given `--change <id>`, it SHALL resolve against the archived
capability specs shadowed by that change's spec delta, with other in-flight
changes' requirements neither citable nor excludable. With `--change` omitted,
it SHALL resolve against the archived specs shadowed by every spec delta present
directly under `openspec/changes/<id>/` on the branch, excluding
`openspec/changes/archive/`. Archived deltas SHALL NOT be unioned: they have
already been merged into `openspec/specs/`, so re-applying them shadows the
archive with itself, and a delta that REMOVED or RENAMED a requirement would
resurrect or re-move it. Which run blocks SHALL be a property of
the CI job and not of the gate. Supplying `--change` SHALL NOT imply blocking
and omitting it SHALL NOT imply reporting: the two choices are independent, and
the merge-candidate run on `merge_group` both omits `--change` and blocks.

The sweep SHALL run as a single CI job on three events — `pull_request`,
`merge_group`, and `push` to the integration branch — and SHALL select both its
invocation and whether its result gates on `github.event_name`. The job SHALL
NOT be guarded off any of those three events. A required check that does not run
on `merge_group` is not a check on the merge candidate, and an unguarded job on
an event with no rule is the unfalsifiable green this requirement exists to
prevent; the event set is therefore normative here, not a CI implementation
detail.

On `pull_request`, the job SHALL derive a change id from the change directory
under `openspec/changes/` touched by the diff against the pull request's base
commit, SHALL invoke the gate with `--change <id>`, and SHALL block. Where the
diff touches no change directory, it SHALL print an explicit SKIP naming the
branch and SHALL NOT fail. Where it touches more than one, it SHALL fail as
ambiguous rather than choosing.

On `merge_group`, the job SHALL invoke the gate with `--change` omitted against
the merge group's base commit, and SHALL block. It SHALL NOT derive a change id,
and the ambiguity rule SHALL NOT apply: a merge group batches whatever the queue
batched, so a diff spanning several change directories is its ordinary case
rather than an error. Deriving a single change id there would fail the queue
whenever two OpenSpec changes batch together.

On `push` to the integration branch, the job SHALL invoke the gate with
`--change` omitted, SHALL evaluate every capability in full, and SHALL NOT
block — its exit status SHALL NOT depend on what it found.

Where a base commit is required and cannot be resolved, the job SHALL fail
naming the event and the base it could not resolve, and SHALL NOT skip.

An unresolvable base and an absent change directory SHALL NOT share an exit
path. They are opposite conditions: the second says the work was not planned
through OpenSpec and is legitimately out of the gate's remit, while the first
says the gate does not know what it is looking at. A rule that skipped on both
would turn every event whose base the derivation did not anticipate into a
silent pass. That is the unfalsifiable-green outcome this capability's
change-scope requirement already forbids in terms; the blocking sweep does not
get an exemption from it. The rule is stated for the three events the job runs
on precisely so that a fourth event, added later without a rule, fails loudly
instead of passing quietly.

Keying resolution on the flag rather than on the run context is what keeps the
gate out of the business of knowing which CI job invoked it. The gate still has
exactly one resolution rule; the job, not the gate, reads `github.event_name`.

Union mode's looseness is a property of the branch it runs on, not of the mode.
On `push` to the integration branch, `openspec/changes/` holds every in-flight
change whose plan has merged and whose implementation has not — so the union
admits requirements nothing has built yet, and that run reports rather than
blocks. Inside a merge group the same directory holds precisely the changes
that are landing, because the evaluated branch *is* the integration branch plus
the batched pull requests. There the union is exact, and blocking on it is the
whole point of evaluating the merge candidate. Reading "union mode" as
"non-blocking by nature" would leave the merge queue ungated.

The SKIP exists because OpenSpec is not the only way work reaches this
repository. Dependency bumps, chores, and cloud-session branches carry no spec
delta, no contract citation, and no exclusions file, because nothing in the
planning process was expected to produce them; failing them for the absence of
an artifact they were never asked to author would red every such pull request
on the day this gate lands. The debt those pull requests could still introduce
is not lost — the post-merge run sees every capability in full and reports it.

Diff-scoping alone would never surface accumulated gaps — nothing touches them,
so nothing reports them. The sweep is what makes existing debt visible without
blocking anyone, and opting in is the only switch that turns its report into a
block: a second reported-to-blocking flag would create an opted-in-but-not-
blocking state, which is the half-traced-yet-green outcome opt-in exists to
make impossible. The blocking run is on the merge candidate, not on a push to
the integration branch: a scheduled run cannot block a merge, but neither can a
push event that fires *after* the merge has landed. Both can red the branch;
only a check on the candidate can stop it going red.

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

<!-- Scenario ID: gen-eval-framework.change-flag-selects-resolution -->
#### Scenario: The change flag selects which delta shadows the archive

- **WHEN** the sweep runs at capability scope with `--change <id>` on a change
  that adds new requirements and cites them from a contract document in the
  same change
- **THEN** those citations SHALL resolve against that change's spec delta
- **AND** requirements belonging to other in-flight changes SHALL NOT resolve

<!-- Scenario ID: gen-eval-framework.omitted-change-flag-unions-deltas -->
#### Scenario: Omitting the change flag unions every on-branch delta

- **WHEN** the sweep runs at capability scope with no `--change` argument
- **THEN** it SHALL resolve against the archived specs shadowed by every spec
  delta present under `openspec/changes/`
- **AND** it SHALL NOT fail for the absence of a change id

<!-- Scenario ID: gen-eval-framework.non-openspec-pr-skips -->
#### Scenario: A pull request that was not planned through OpenSpec skips

- **WHEN** the blocking job runs on a pull request whose base resolves and
  whose diff touches no directory under `openspec/changes/`
- **THEN** it SHALL print a SKIP naming the branch
- **AND** it SHALL NOT fail the pull request
- **AND** the post-merge run SHALL still evaluate every capability in full

<!-- Scenario ID: gen-eval-framework.unresolvable-base-fails-not-skips -->
#### Scenario: An unresolvable base fails rather than skipping

- **WHEN** the job runs on an event that requires a base commit and cannot
  resolve it
- **THEN** it SHALL fail naming the event and the base it could not resolve
- **AND** it SHALL NOT take the no-change-directory SKIP path, which would make
  an unanticipated event indistinguishable from work not planned through
  OpenSpec

<!-- Scenario ID: gen-eval-framework.ambiguous-change-fails -->
#### Scenario: A pull request touching two change directories fails as ambiguous

- **WHEN** the job runs on a `pull_request` event whose diff touches more than
  one directory under `openspec/changes/`
- **THEN** it SHALL fail naming each candidate change id
- **AND** it SHALL NOT choose one

<!-- Scenario ID: gen-eval-framework.merge-group-unions-and-blocks -->
#### Scenario: A merge group batching two changes blocks without ambiguity

- **WHEN** the job runs on a `merge_group` event whose diff touches two
  directories under `openspec/changes/`
- **THEN** it SHALL invoke the gate with `--change` omitted
- **AND** it SHALL NOT fail as ambiguous
- **AND** a violation in an opted-in surface SHALL fail the merge group

<!-- Scenario ID: gen-eval-framework.push-to-integration-branch-reports -->
#### Scenario: The run on the integration branch cannot fail

- **WHEN** the job runs on a `push` to the integration branch and the sweep
  finds violations in opted-in surfaces
- **THEN** it SHALL report every violation it found
- **AND** it SHALL exit zero, because a run that fires after the merge can red
  the branch but cannot stop it going red

<!-- Scenario ID: gen-eval-framework.job-runs-on-every-declared-event -->
#### Scenario: The job is not guarded off any declared event

- **WHEN** the CI workflow declares the `pull_request`, `merge_group`, and
  `push` triggers
- **THEN** the sweep job SHALL run on all three
- **AND** it SHALL NOT carry a condition that excludes it from `merge_group`,
  which would leave the merge candidate unevaluated by the check that gates it

### Requirement: The gate fails closed on malformed input

A contract document SHALL be a contract instance under
`openspec/contracts/<capability>/openapi/` or
`openspec/contracts/<capability>/cli/`; files under `schemas/` SHALL NOT be
contract documents. An instance SHALL be identified structurally, not by
location: a `.yaml`, `.yml`, or `.json` file whose top level is a mapping
carrying an `openapi` key (OpenAPI instance) or a `tool` key (CLI contract
instance). `README.md` and `traceability-exclusions.yaml` carry neither and
SHALL NOT be treated as instances under any rule. An instance found at the
capability root SHALL be reported as misplaced, naming the file and the
expected location, and SHALL NOT be silently skipped; the sweep SHALL NOT fail
on it, and change scope SHALL fail on it only when the diff adds or modifies
it. A contract document that cannot be parsed SHALL fail the gate naming
the file, and SHALL NOT be recorded as untraced. A traceability block that violates the
traceability schema SHALL fail the gate naming the file and the offending
block. An existing `traceability-exclusions.yaml` that cannot be read, cannot
be parsed, is empty, or violates the exclusions schema SHALL fail the gate
naming the file, and SHALL NOT be treated as absent. A capability directory
containing contract documents that declare traceability, but no capability
spec, SHALL fail with a message distinguishing the missing spec from an
unresolved identifier; where no document declares traceability, the missing
spec SHALL be reported and SHALL NOT fail. A capability with a spec and no
contracts SHALL be recorded as forward-untraced, which SHALL NOT affect
whether its reverse direction is enforced.

Enforcement is keyed on the presence of traceability blocks, so a parse error
that reads as "no blocks found" would silently downgrade a traced contract to
untraced and turn a syntax error into a green run. The schema-invalid shapes —
`requirements` and `excluded` together, or an empty citation list — were
excluded from the schema deliberately, and a gate that let them through would
have to pick a winner, which is the silent decision the schema exists to
refuse.

The misplaced instance is the one rule here that reports rather than fails, and
deliberately: `openspec/contracts/code-search/v2.yaml` is an OpenAPI instance at
a capability root **today**. A rule that failed on it would red the tree the
moment the blocking sweep was installed, and would contradict the acceptance
criterion that the merge candidate exit zero at capability scope. Reporting the
existing one while failing any newly added one is the ratchet: the debt is
visible and cannot grow, without the change reddening the branch it lands on.
Structural identification matters for the same reason — "any file at the root"
fails `README.md`, and "any YAML at the root" fails
`traceability-exclusions.yaml`, which would turn D13's reverse opt-in switch
into a permanent gate failure the first time anyone flipped it.

The exclusions file needs the same protection for a stronger reason: D13 makes
its *existence* the reverse switch, so "cannot read it" and "it isn't there"
are one byte apart in consequence and opposite in meaning. A capability that
had opted in would silently opt back out on a YAML typo, and the direction D3
calls the valuable one would fail open — inverting
`check_coverage_completeness.py`, the precedent D4 claims to lift wholesale.
Absence is a decision; unreadability is an accident, and the gate SHALL NOT
read one as the other.

The missing-spec case is bounded twice, because measured on this repository on
2026-07-28 an unbounded reading would red `main` the moment this change merged.
Three capability directories under `openspec/contracts/` have no matching spec
directory — `phase-record`, `project-context-refresh` (the spec tree carries
`project-context-refresh-orchestration` and `project-context-refresh-records`,
neither named `project-context-refresh`), and `prototyping`. All three hold
only `schemas/`, so under D6's definition they contain no contract *documents*
at all and the rule never reaches them. The opt-in gate is the second bound,
covering the future case where such a directory gains an instance: the rule
keeps its teeth exactly where a document has claimed to be traced, which is the
only place a missing spec can hide an unresolved citation.

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

<!-- Scenario ID: gen-eval-framework.misplaced-instance-is-reported -->
#### Scenario: A contract instance outside openapi/ or cli/ is reported

- **WHEN** the full sweep encounters a file at a capability root whose top
  level carries an `openapi` or `tool` key, rather than under `openapi/` or
  `cli/`
- **THEN** the sweep SHALL report it as misplaced, naming the file and the
  expected location
- **AND** it SHALL NOT silently exclude the document from the report
- **AND** it SHALL NOT fail on it, so a pre-existing misplaced instance does
  not red the branch on the day the sweep is installed

<!-- Scenario ID: gen-eval-framework.newly-misplaced-instance-fails -->
#### Scenario: A newly misplaced instance fails change scope

- **WHEN** the diff adds or modifies an instance at a capability root
- **THEN** the change-scoped gate SHALL exit non-zero naming the file and the
  expected location

<!-- Scenario ID: gen-eval-framework.root-non-instances-are-not-documents -->
#### Scenario: README and the exclusions file are never instances

- **WHEN** a capability root holds `README.md` and
  `traceability-exclusions.yaml`
- **THEN** neither SHALL be treated as a contract instance
- **AND** the misplaced-instance rule SHALL NOT fire on the exclusions file,
  whose presence at that exact path is the reverse opt-in switch

<!-- Scenario ID: gen-eval-framework.schemas-are-not-documents -->
#### Scenario: A schemas-only capability holds no contract documents

- **WHEN** a capability directory contains only `schemas/*.schema.json` files
- **THEN** the gate SHALL NOT treat it as containing contract documents
- **AND** the missing-capability-spec rule SHALL NOT fail on it

<!-- Scenario ID: gen-eval-framework.malformed-exclusions-file-fails -->
#### Scenario: An unreadable exclusions file fails rather than opting out

- **WHEN** `openspec/contracts/<capability>/traceability-exclusions.yaml`
  exists but cannot be read, cannot be parsed, is empty, or violates the
  exclusions schema
- **THEN** the gate SHALL exit non-zero naming the file
- **AND** it SHALL NOT record the capability's reverse direction as not opted in

<!-- Scenario ID: gen-eval-framework.missing-capability-spec-fails -->
#### Scenario: Contracts without a capability spec fail distinctly

- **WHEN** a capability directory under `openspec/contracts/` contains contract
  documents that declare traceability, and no `openspec/specs/<capability>/spec.md`
  exists
- **THEN** the gate SHALL fail stating that the capability has no spec
- **AND** the message SHALL be distinguishable from an unresolved identifier

<!-- Scenario ID: gen-eval-framework.missing-spec-untraced-reports -->
#### Scenario: A specless capability that has not opted in is reported

- **WHEN** a capability directory under `openspec/contracts/` contains contract
  documents, none of which declares traceability, and no
  `openspec/specs/<capability>/spec.md` exists
- **THEN** the gate SHALL report the missing spec
- **AND** the run SHALL NOT fail on it

<!-- Scenario ID: gen-eval-framework.spec-without-contracts-untraced -->
#### Scenario: A capability with a spec and no contracts is forward-untraced

- **WHEN** a capability has a spec and no contract documents
- **THEN** the gate SHALL record its forward direction as untraced
- **AND** the run SHALL NOT fail forward completeness on it
- **AND** if the capability has an exclusions file, its reverse completeness
  SHALL still be enforced, failing on any requirement neither cited nor excluded

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
