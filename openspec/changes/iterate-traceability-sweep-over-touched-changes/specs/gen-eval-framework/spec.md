# gen-eval-framework — delta

## MODIFIED Requirements

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
the CI job and not of the gate: every blocking invocation SHALL supply
`--change <id>`, and union mode SHALL be used only by the non-blocking
post-merge run. The gate SHALL NOT infer blocking from the flag, and SHALL NOT
fail merely because `--change` was omitted — a gate that required a change id
would reject the one run legitimately entitled to omit it.

The sweep SHALL run as a single CI job on three events — `pull_request`,
`merge_group`, and `push` to the integration branch — and SHALL select both its
invocation and whether its result gates on `github.event_name`. The job SHALL
NOT be guarded off any of those three events. A required check that does not run
on `merge_group` is not a check on the merge candidate, and an unguarded job on
an event with no rule is the unfalsifiable green this requirement exists to
prevent; the event set is therefore normative here, not a CI implementation
detail.

Change-id derivation SHALL consider only paths that the diff ADDS or MODIFIES,
under a directory matching `openspec/changes/<id>/` where `<id>` is not
`archive`, and SHALL be computed with rename detection disabled so that the
derived set does not depend on a similarity heuristic. Deleted paths SHALL NOT
yield a change id.

All three conditions are load-bearing, and the deletion filter is the one whose
absence is least visible. Archiving is a `git mv` from
`openspec/changes/<id>/` to `openspec/changes/archive/<date>-<id>/`. With
rename detection disabled — which the determinism requirement above mandates —
that move decomposes into deletions at the source and additions at the
destination. Excluding `archive` therefore suppresses only the destination
half: the source half still names `<id>`, so an archive pull request would
derive the id of the change it is archiving and invoke a blocking run against a
directory that no longer exists on that commit. Excluding deletions suppresses
the source half, and the two exclusions together make an archive pull request
touch no change directory at all.

That result — the SKIP — is the correct one, because archiving is OpenSpec
bookkeeping rather than a change the gate can scope to, and any traceability
debt the merge introduces is reported by the post-merge run.

The deletion filter also makes derivation robust to a base commit that predates
an archive: without it, any pull request whose diff spans an archive commit
derives the archived id alongside its own and gates a change that is no
longer open.

On `pull_request`, the job SHALL derive the set of change directories touched
by the diff against the pull request's base commit, SHALL invoke the gate once
per derived change id with `--change <id>`, and SHALL block if any invocation
fails. Where the diff touches no change directory, it SHALL print an explicit
SKIP naming the branch and SHALL NOT fail. Several change directories is not an
error: a scaffold of sibling changes or a batch of plans is an ordinary pull
request, and each change is gated on its own scope.

On `merge_group`, the job SHALL derive the set of change directories touched by
the diff against the merge group's base commit, SHALL invoke the gate once per
derived change id with `--change <id>`, and SHALL block if any invocation fails.
The same per-change rule applies: a merge group batches whatever the queue
batched, so several change directories is its ordinary case rather than an
error. Where the diff touches no change directory, the job SHALL print an
explicit SKIP naming the merge group and SHALL NOT fail.

The merge-group run SHALL NOT use union mode. The set of change directories in
the *diff* is the batch; the set present in the *tree* is not, because a
merge-queue branch is the integration branch plus the batched pull requests and
therefore carries every unarchived change directory the integration branch
already had. Unioning the tree would evaluate a blocking run against
requirements belonging to changes that are not in the batch, whose
implementations have not landed and which the batch's authors cannot cite or
exclude — an exclusion naming them fails by the rule above. A blocking run
SHALL only ever be scoped to a change it is actually evaluating.

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

Union mode is deliberately the looser of the two — it admits requirements from
changes whose implementation has not landed — and that is exactly why the only
run that uses it reports and never blocks. `openspec/changes/` on any branch
built from the integration branch holds every in-flight change, not the subset
under evaluation, so union mode can never say anything scoped. An earlier draft
of this requirement assumed a merge-queue branch was an exception, on the
reasoning that it "is the integration branch plus the batched pull requests" —
which is true and is precisely the refutation, since the integration branch part
carries all the others. Under that draft the blocking merge-group run would have
failed on uncited requirements belonging to changes outside the batch, and the
batch's authors could not have fixed it: citing them is not their work, and
excluding them fails by the other-changes-are-invisible rule. Blocking scope
comes from the diff, never from the tree.

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
  delta present directly under `openspec/changes/<id>/`
- **AND** it SHALL NOT union deltas under `openspec/changes/archive/`, which
  are already merged into `openspec/specs/`
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

<!-- Scenario ID: gen-eval-framework.pull-request-iterates-over-touched-changes -->
#### Scenario: A pull request touching two change directories is evaluated once per change

- **WHEN** the job runs on a `pull_request` event whose diff touches two
  directories under `openspec/changes/`
- **THEN** it SHALL invoke the gate twice, once per derived change id, each
  with `--change <id>`
- **AND** it SHALL NOT fail as ambiguous
- **AND** a violation in an opted-in surface of either change SHALL fail the
  pull request

<!-- Scenario ID: gen-eval-framework.merge-group-iterates-over-the-batch -->
#### Scenario: A merge group batching two changes is evaluated once per change

- **WHEN** the job runs on a `merge_group` event whose diff touches two
  directories under `openspec/changes/`
- **THEN** it SHALL invoke the gate twice, once per derived change id, each
  with `--change <id>`
- **AND** it SHALL NOT fail as ambiguous
- **AND** a violation in an opted-in surface of either change SHALL fail the
  merge group

<!-- Scenario ID: gen-eval-framework.archive-pull-requests-skip -->
#### Scenario: An archive pull request derives no change id

- **WHEN** the job runs on a pull request that moves `openspec/changes/<id>/`
  to `openspec/changes/archive/<date>-<id>/` and changes nothing else under
  `openspec/changes/`
- **THEN** it SHALL derive no change id
- **AND** it SHALL derive neither the literal id `archive` from the added paths
  nor `<id>` from the deleted paths
- **AND** it SHALL print a SKIP and SHALL NOT fail as ambiguous

<!-- Scenario ID: gen-eval-framework.merge-group-ignores-unbatched-changes -->
#### Scenario: A merge group is not evaluated against changes outside the batch

- **WHEN** the job runs on a `merge_group` event and the branch carries
  unarchived change directories that the diff against the merge group's base
  does not touch
- **THEN** those changes' requirements SHALL NOT enter any blocking invocation's
  effective requirement set
- **AND** the merge group SHALL NOT fail for an uncited requirement belonging
  to a change outside the batch

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
