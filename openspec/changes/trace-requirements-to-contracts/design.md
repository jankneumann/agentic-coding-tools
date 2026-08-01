# Design: Trace requirements to contracts

## Context

`derive-descriptors-from-contracts` established that the contract is the
declared surface and that introspection only verifies against it. This change
adds the edge above: the contract must cite the requirements it exists to serve,
and no requirement may go uncited without a stated reason.

Every decision below is constrained by one fact: **requirement → contract adds
information.** A requirement says what must be possible; a contract says by what
route, with what shape, returning what. The gap between them is design work, and
no gate can close it. What a gate can do is refuse to let the gap be crossed
silently.

---

### D1 — Traceability is cited, never inferred

**Decision.** An operation's requirement citations are written into the
contract. Nothing infers them from names, paths, or prose similarity.

**Why.** Inference here has exactly one failure mode and it is fatal: a
plausible-looking match. `POST /locks/acquire` and "SHALL allow an agent to
acquire a lock" share a word, and a matcher that pairs them would also pair
`POST /locks/release` with the same requirement, and `GET /audit` with whatever
requirement happens to mention auditing. The gate would go green on a mapping
nobody agreed with, which is strictly worse than no gate — a false negative that
looks like coverage.

The parallel to `derive-descriptors-from-contracts` D1 is exact. That decision
forbade introspection from *populating* the declared surface, for the same
reason: a source of truth that derives itself from the thing it is supposed to
constrain constrains nothing.

**Consequence.** Retrofitting is manual. That is a cost, not a defect: the cost
is one human decision per operation, and the decision is the artifact.

---

### D2 — Requirement ids are derived from the heading, and fail closed

**Decision.** A requirement id is `<capability>.<slug-of-heading>`, e.g.
`agent-coordinator.lock-acquisition-is-exclusive`. A resolver maps ids to
requirements by reading `openspec/specs/<capability>/spec.md`. A citation naming
an id that resolves to nothing **fails**.

**The slug algorithm is normative, not an implementation detail:** NFKD
normalize and drop non-ASCII marks, lowercase, replace each run of characters
outside `[a-z0-9]` with a single `-`, collapse, strip leading and trailing
`-`. It has to be written down because real headings in this repository start
with backticks and contain em-dashes — under a naive rule they derive ids the
contract schema's pattern rejects, making those requirements permanently
uncitable, and the only remedy would be a false exclusion.

**Collisions fail closed.** Two headings in one capability deriving the same
slug fail the resolver naming both. An undetected collision is worse than a
broken citation: a citation to the shared id marks *both* requirements cited,
and one of them becomes invisible to reverse completeness — the direction
nothing else detects — with no signal. Zero collisions exist across the 29
capability specs today (632 headings checked), which is exactly why the check
is cheap to add now and expensive to discover later.

**Why derived rather than declared.** OpenSpec requirements have headings, not
ids, and adding an `id:` field is a change to a shared external tool on someone
else's schedule (proposal approach C). Deriving works today and becomes a thin
adapter if OpenSpec adds explicit ids.

**Why fail closed on a reworded heading.** Rewording a heading renames its id
and breaks every citation to it. That is the correct behaviour, not a bug to
smooth over. The alternative — fuzzy re-matching — silently rebinds a citation
to whatever heading now looks closest, which is D1's failure mode reintroduced
through the back door. A broken citation is a two-minute fix and an accurate
signal that the requirement changed.

**Consequence.** The gate's error message must name both the unresolved id and
the nearest candidate headings — bounded to five, ranked by edit distance —
or the two-minute fix becomes a twenty-minute hunt. Bounding matters at this
repository's scale (`skill-workflow` has 208 requirement headings; a
capability-wide rename would otherwise print failures × headings). Ranking is
for display only and is not rebinding: stated here so a later reader does not
mistake the candidate list for the inference D1 forbids and remove it.

---

### D3 — The gate is bidirectional, and the reverse direction is the valuable one

**Decision.** Forward (every operation cites) and reverse (every requirement is
cited) are both enforced.

**Why.** Forward completeness catches surface nobody asked for. Reverse
completeness catches requirements nobody built — and **nothing in this
repository detects that today.** Not the coverage model, which measures the
declared surface against scenarios and cannot see a requirement that never
became an operation. Not the drift guards, which compare artifacts to contracts.
Not review, reliably, because a missing thing has no diff.

Measured on the coordinator: 10 requirements name an operation the application
does not serve. Each is unimplemented, implemented without an interface, or
obsolete. All three matter and none surface anywhere.

**Contrast with `derive-descriptors-from-contracts` D1**, which ran subset
verification in **one** direction on purpose — excess is a violation, omission
is coverage's job — because reporting both delivered one defect twice. That
reasoning does not transfer, because here there is no second mechanism. Omission
at the requirement level is reported by nothing else, so reporting it here is
the only report.

---

### D4 — Exclusions carry reasons, in the D11 shape

**Decision.** Both directions accept exclusions. An exclusion needs a non-blank
reason. An exclusion naming something that no longer exists fails.

**Why.** Lifted wholesale from `derive-descriptors-from-contracts` D11, and the
argument is unchanged: an unexplained exclusion is how a gap gets laundered into
"intentional". The stale-exclusion check matters more here than it did there,
because requirements outlive operations — an exclusion written for a requirement
that has since been deleted keeps a slot warm for the next requirement to reuse
the slug, which inherits an approval nobody granted it.

**Legitimate exclusions exist and are the point.** "Enforced by review, no
interface" is a real answer for a requirement about code style. "Health probe,
infrastructure not product surface" is a real answer for `GET /live`. Neither is
recorded anywhere today, and both are worth having written down.

---

### D5 — The gate never claims the operation satisfies the requirement

**Decision.** Four checks: citations resolve, forward completeness, reverse
completeness, exclusions explained. Explicitly **not** whether the cited
operation actually satisfies the cited requirement.

**Why.** Nothing static can decide it, and a gate that implied it would be the
most dangerous artifact this change could ship: an unfalsifiable green light
over a correctness claim. Satisfaction is what scenarios, the coverage model and
human review are for.

This bounds the change's claim precisely: it establishes that **the question was
asked and a human answered it**, and nothing more. That is a smaller claim than
"the system implements its requirements" and it is the largest claim a static
gate can honestly make.

**Consequence.** The gate's output must be worded so it cannot be misread as a
satisfaction claim. "every operation cites a requirement" — never "requirements
are implemented".

---

### D6 — Forward enforcement is opt-in per contract document, keyed on the block's presence

**"Contract document" means a contract *instance*, and only that.** The term is
load-bearing twice — forward opt-in is keyed on the document, and the
missing-spec rule is keyed on a directory "containing contract documents" — so
it is defined here rather than left to the reader. A contract document is a
file under `openspec/contracts/<capability>/openapi/` or
`openspec/contracts/<capability>/cli/`: the two locations `contracts/README.md`
calls contract *instances*. Files under `schemas/` are contract **schemas**, not
documents. The distinction is not bookkeeping — a schema describes what a valid
instance looks like and has no operations, so there is nothing on it for a
citation to attach to.

This settles what would otherwise be an ambiguity with immediate consequences.
Measured on 2026-07-28, `openspec/contracts/` holds 13 `*.schema.json` files
against exactly two instances (`gen-eval-framework/cli/gen-eval.yaml`,
`code-search/v2.yaml`). Under a reading where any file is a "contract
document", `phase-record`, `project-context-refresh`, and `prototyping` — all
schemas-only — would be capability directories "containing contract documents",
and the missing-spec rule would fail all three. Under this definition they
contain no contract documents at all and are simply out of scope, which is the
correct answer for a directory of schemas.

**A misplaced instance is reported, and fails only if newly added.** An
instance directly at the capability root, not under `openapi/` or `cli/`, is
reported by the sweep naming the file and the expected location, and fails the
change-scoped gate only when the diff adds or modifies it. A discovery walk
keyed on the two directories would silently skip it, and silently skipping an
OpenAPI document is precisely the invisible-surface failure this change exists
to prevent — but failing on it outright is not the remedy, because
`code-search/v2.yaml` is a full OpenAPI 3.1 document at that exact location
**today**, contrary to README's own layout table. An unconditional failure
would red the branch the moment the blocking sweep landed, and would directly
contradict the acceptance criterion that the merge candidate exit zero at
capability scope. Report-the-existing, fail-the-new is the ratchet: the debt is
named on every run and cannot grow, and fixing the layout is a task rather than
a merge blocker.

**"Instance" is identified structurally, not by location.** A `.yaml`, `.yml`,
or `.json` file whose top level is a mapping carrying an `openapi` key (OpenAPI)
or a `tool` key (the CLI contract shape, per `gen-eval.yaml`). The definition
has to be structural precisely because the misplaced-instance rule looks at the
capability root, and the root is not empty: a rule of "any file at the root"
fires on `README.md`, and "any YAML at the root" fires on
`traceability-exclusions.yaml` — which would make D13's reverse opt-in switch
fail the gate the first time anyone flipped it, since the switch *is* a YAML
file at that exact path.

**Decision.** A contract document declaring a `traceability` block anywhere
opts into strict **forward** enforcement across all of its operations. A
document with no such block anywhere is recorded `untraced` and does not fail
forward completeness. The reverse direction has its own, separate switch —
D13 — because it is a different claim with a different owner.

**Why.** The ri-08 context-impact gate pattern, chosen for the same reason:
enforcement keyed on whether the block exists is one-way. Declaring it commits
the whole document, so nobody gets a half-traced document that reports green
while most of it is unattributed. Omitting it is visible in the report rather
than silent.

**Why the unit is the document, not the capability.** An earlier draft said
"opts the capability in", and that reading collides head-on with D10's staging
path: if opting `locks.yaml` in opted in `agent-coordinator`, every other
coordinator document would immediately be enforced, which is the trace-all-82
cliff splitting exists to avoid. The document is the unit an author can
honestly commit; the capability is the unit completeness is *evaluated* over
(D10). In the mixed capability — one traced document, one untraced — the
traced document is enforced, the untraced one is recorded, and the traced
document's citations still count toward the capability's reverse completeness.

It also makes the coordinator tractable. Its contract can land `untraced` and
tighten per document, instead of blocking on 82 decisions before anything ships.

**Rejected: a percentage threshold.** "70% of operations traced" is the metric
D11 already rejected one level down, for the reason that applies here with more
force — the number does not say whether the untraced remainder is health probes
or an unasked-for subsystem.

---

### D7 — Citation concentration is reported, not failed

**Decision.** A requirement cited by an implausibly large share of a contract's
operations is surfaced in the gate's output. It does not fail the build.

**Why.** The predictable way to defeat this gate is for every operation to cite
one catch-all requirement. The gate would be green and the citations worthless.

But the threshold between "this requirement genuinely governs many operations"
and "someone is box-ticking" is a judgement, and encoding it as a number would
fail honest contracts while a determined box-ticker just spreads citations over
two requirements instead of one. Surfacing it puts the judgement where it
belongs — with the reviewer — and costs nothing when it is a false alarm.

**The output is deterministic even though the judgement is not.** The gate
emits, per cited requirement, the count and share of the capability's traced
operations citing it, descending, and marks entries at or above a named module
constant (`CONCENTRATION_REPORT_SHARE`) as concentrated. The constant is a
display trigger, documented as such: changing it can never change an exit code.
Without a defined trigger, the test for concentration (task 3.9) would have to
assert whatever the implementation happens to flag — the implementation
verifying a mirror of itself, which is the exact defect class this change
exists to eliminate. The denominator is the capability's traced operations,
not one document's, or splitting a contract (D10's staging mechanism) would
dilute the share and defeat the report.

This is the one place the change deliberately reports rather than gates, and the
reason is that the failure it detects is a social one, not a structural one.

---

### D8 — `change-context.md`'s Contract Ref column becomes generated

**Decision.** The Requirement Traceability Matrix's Contract Ref column is
generated from citations rather than hand-filled.

**Why.** `skills/implement-feature/SKILL.md` already instructs the implementer
to map each SHALL clause to the contract file that validates it. Nothing checks
it, so it is the unenforced-convention problem this whole line of work exists to
fix, sitting one layer above where it was fixed.

Generating it also removes a class of drift that has already bitten: a matrix
row pointing at a contract path that was renamed three changes ago is
indistinguishable from a correct one at a glance.

**Consequence.** The matrix stops being a place to record a mapping and becomes
a view of one. The mapping lives in the contract, next to the operation it
describes, where the person making the decision is already looking.

**The join is by parse position, never by name.** The matrix keys rows by the
ordinal Req ID (`<capability>.<N>`, per skill-workflow's existing spec) while
citations key by the derived slug id. The generator derives both from the same
parse of the spec delta, so a row and its citations are joined by position in
that one parse. Re-matching by name similarity is forbidden — it would be D1's
inference at the matrix layer. The ordinal format itself is left alone in this
change: it is the matrix's row key, its rebinding-on-insertion weakness is
pre-existing, and replacing it belongs to a skill-workflow change, not this
one.

---

### D9 — Citations may name a requirement in another capability

**Decision.** A citation may name any capability's requirement. The identifier's
capability prefix makes a cross-capability citation visible as one.

**Why.** Cross-capability operations already exist — the coordinator serves
`/gen-eval/scenarios`, which is gen-eval-framework's requirement being satisfied
by an agent-coordinator operation. Forbidding the citation would not make the
coupling go away; it would only make the one artifact that records it illegal,
and force the operation to be excluded with a reason that says "serves a
requirement I am not allowed to name."

**Consequence for reverse completeness.** The denominator cannot be "this
capability's requirements checked against this capability's contracts", because
a requirement may legitimately be served from elsewhere. This is what forces
D10.

**Consequence for review.** A cross-capability citation is a coupling worth
noticing, so the gate reports them as a distinct list rather than folding them
into the pass. Reported, not failed — the coupling is often correct, and the
value is that someone sees it.

---

### D10 — The gate's unit is the capability, not the contract

**Decision.** A run gathers every contract that cites into a capability, unions
their citations, and checks completeness against that capability's requirement
set. The capability is the unit of **evaluation** only — forward opt-in stays
per contract document (D6), and reverse opt-in is per capability via the
exclusions file (D13).

**Why.** D9 makes per-contract reverse completeness incorrect, not merely
inconvenient: a requirement served by an operation in another capability's
contract would be reported as uncited by a per-contract run, and the only fix
would be an exclusion asserting something false.

**The consequence that makes staging possible.** Because completeness no longer
cares which *file* an operation lives in, a capability's contract can be split
without weakening the gate.
`openspec/contracts/agent-coordinator/openapi/` can hold `locks.yaml`,
`work-queue.yaml` and so on, each opted in when its subsystem is ready, and the
capability-level check still sees the union.

That resolves a tension D6 would otherwise create. D6 makes opt-in commit a
whole contract document, deliberately — a half-traced document reporting green
is the failure it exists to prevent. But the coordinator is one document with
82 operations, so document-level totality on a single file would mean tracing
all 82 before any of it counts. Splitting the document is the staging
mechanism; lowering D6's bar is not.

**What splitting stages — and what it does not.** Splitting stages the
*forward* direction only: each document's operations are enforced as that
document opts in. It does nothing for the reverse direction, because "every
requirement of this capability is served or excused" is a claim about the
whole capability that no single document can make. The reverse direction's
staging is D13's separate switch — a capability enforces reverse completeness
only once its requirement set has actually been triaged. An earlier draft
claimed the split "costs nothing in rigour" without noticing this asymmetry;
the split costs nothing in *forward* rigour, and the reverse direction was
never split-stageable in the first place.

---

### D11 — The effective requirement set is the archive, shadowed by the active change

**Decision.** Resolution reads `openspec/specs/<capability>/spec.md`, with the
active change's `specs/` delta shadowing it: `ADDED` requirements appear,
`MODIFIED` replace their archived version, `REMOVED` disappear, and `RENAMED`
requirements resolve under the new identifier only. Requirements belonging to
**other** in-flight changes are not in the universe — they can be neither
cited nor excluded.

**RENAMED is not optional.** OpenSpec emits `## RENAMED Requirements` sections
and this repository's own delta parser handles them (`openspec_merge.py`). A
resolver that ignored them would fail *open* in both directions at once: the
old identifier keeps resolving out of the archive, so a stale citation passes
— the exact silent rebinding D2 forbids — while the new identifier resolves to
nothing, so a correctly updated citation fails. A `MODIFIED` block that
rewords its heading is the same case and gets the same treatment: the old id
stops resolving, the new one starts.

**Why the active change must shadow.** Every requirement a change adds lives
only in its own delta until archive. If resolution read the archive alone, every
citation a change makes to its own new requirements would fail, and the gate
would block correct work. That is disqualifying, not inconvenient.

**Why other changes are invisible rather than excludable.** Allowing an
exclusion to name another change's unarchived requirement fails three ways, and
the first is the serious one:

1. **The exclusion becomes wrong rather than stale.** When that change archives,
   the requirement becomes real and the exclusion now suppresses a genuine
   reverse-completeness finding. D4's stale-exclusion check cannot catch it,
   because the target exists. An artifact that looks correct while hiding a true
   signal is the worst outcome available in this design.
2. **It couples changes that must merge independently.** Change A's contract
   referencing change B's spec means B cannot be reworked or abandoned without
   breaking A's gate.
3. **Abandoned changes leave dangling references.** Change directories are
   deleted; the reference then names nothing, discovered later and by accident.

**The property this buys on the deletion path.** A change that removes a
requirement removes it from the effective set, so any operation still citing it
stops resolving and fails the gate. Requirement-removal and operation-removal
become coupled — you cannot delete a requirement while its endpoint still serves
traffic, or delete an endpoint while its requirement claims it exists. Nothing
enforces that today, and deletion is where interface debt accumulates unseen.

---

### D12 — At validation the gate is diff-scoped; the full sweep runs on main

**Decision.** Two run contexts, one gate, differing only in what they consider
in scope:

| Context | Trigger | Gate invocation | Scope | Blocking |
|---|---|---|---|---|
| `/validate-feature` | local / pre-PR | `--change <id>` | Operations and requirements the change touches | Yes |
| CI, merge candidate | `pull_request` | `--change <derived>` | Every capability, in full | Opted-in surfaces block (traced documents forward, exclusions-file capabilities reverse); the rest report |
| CI, merge candidate | `merge_group` | `--change <derived>`, once per batched change | Every capability, in full | Same — opted-in surfaces block |
| CI, debt visibility | `push` on `main` | `--change` omitted | Every capability, in full | No — reports only |

**One job, three events, selected on `github.event_name`.** The three CI rows
are one workflow job, not three. It is deliberately *not* guarded off any
declared event: `ci.yml` triggers on `push: [main]`, `pull_request`, and
`merge_group`, and a required check that does not run on `merge_group` is not a
check on the merge candidate at all. The event selects the invocation and
whether the result gates; nothing else varies.

**Why the blocking sweep is not push-triggered.** An earlier draft ran the full
sweep push-triggered on `main`, reasoning that a *scheduled* run cannot block a
merge. That reasoning was right and the conclusion did not follow: a push event
on `main` fires **after** the merge has landed, so it shares the defect it was
chosen to avoid. It can red `main`; it cannot stop `main` going red. Only a
check that runs on the merge candidate can block the merge. The push-on-`main`
run is kept, with its honest purpose — making accumulated debt visible on the
integration branch — and is explicitly non-blocking, so nothing depends on it
to stop anything.

**Why `merge_group` iterates instead of unioning.** A merge group's diff spans
every pull request the queue batched, so deriving a *single* change id there
would hit the ambiguity rule whenever two OpenSpec changes batch together —
failing the queue for doing exactly what a queue is for. The fix is to run the
gate once per batched change id, not to abandon change scope.

An earlier draft used union mode on `merge_group` instead, reasoning that a
merge-group branch "holds precisely the changes that are landing, because the
evaluated branch is the integration branch plus the batched pull requests."
That reasoning refutes itself: the integration-branch half carries every
unarchived change directory. `git ls-tree --name-only origin/main
openspec/changes/` returns 34 entries, three of which add 11
`gen-eval-framework` requirements with no landed implementation. With D13
reverse enforcement on, a blocking union run would have failed on those 11 —
and the batch's authors could not have fixed it: citing another change's
requirements is not their work, and excluding them fails by D11's
other-changes-are-invisible rule. **Blocking scope comes from the diff, never
from the tree.** The tree is the same on every branch built from `main`; only
the diff knows what is under evaluation.

The ambiguity rule therefore applies on `pull_request` only, where more than
one change directory in a diff really is someone conflating two changes.

**Resolution is keyed on the `--change` flag, not on the run context.** Every
resolution rule in this change is written in terms of *the active change's*
spec delta, which is well-defined at `/validate-feature` and on a merge
candidate and undefined on the integration branch. An earlier draft closed that
by making the blocking run *require* a change id and fail without one — which
does not work, because "no change id" is also the post-merge run's signature,
so the rule failed the run it was supposed to permit. The gate cannot see which
CI job invoked it and should not try.

So the gate has one rule with two modes, selected by the flag: `--change <id>`
shadows the archive with that delta (other in-flight changes neither citable nor
excludable); omitting it shadows the archive with *every* delta present under
`openspec/changes/` on the branch, excluding `archive/` — those deltas are
already merged into `openspec/specs/`, and re-applying a REMOVED or RENAMED one
would resurrect or re-move a requirement.

Blocking-ness lives in the CI job, but the two are not independent in practice:
every blocking invocation supplies `--change <id>`, and union mode is used by
exactly one run, the non-blocking post-merge one. That is not a coincidence to
be tidied away — it is the invariant. Union mode admits requirements from
changes whose implementation has not landed, so nothing that blocks can afford
to use it. The gate still must not *infer* blocking from the flag, and must not
fail merely because `--change` was omitted: that was the earlier draft's error,
and it rejected the one run entitled to omit it.

Resolving archive-only in union mode would instead report every
citation a merged-but-unarchived change makes to its own new requirements, since
a delta lives under `openspec/changes/<id>/` until cleanup archives it.

**The blocking job derives its change id from the diff, and skips when there is
none.** Not from the branch name: `OPENSPEC_BRANCH_OVERRIDE` produces
`claude/op-XXXX`, parallel agents produce `openspec/<id>--<agent-id>`, and CI
triggers on unfiltered `pull_request` and `merge_group`, so `dependabot/*`,
`chore/*`, and `codex/*` all reach the job. The change directory the diff
touches is the robust signal, and its absence is meaningful rather than
exceptional: it says the work was not planned through OpenSpec, so no spec
delta, citation, or exclusions file was ever expected of it. Failing a
dependency bump for not authoring an artifact nobody asked it for would red
every such pull request the day this lands. Two touched directories is a
genuine ambiguity and fails rather than guessing.

**The base is named, and an unresolvable base is an error — not the SKIP.**
"The diff" is against the pull request's base commit on `pull_request` and the
merge group's base commit on `merge_group`; the two events carry different
payloads, and CI triggers on both unfiltered. If the derivation cannot resolve
a base it must fail naming the event, because sharing an exit path with the
no-change-directory SKIP would collapse two opposite conditions into one green
check: "this work was legitimately not planned through OpenSpec" and "the gate
does not know what it is looking at". `merge_group` is the reachable instance —
a derivation written against `github.event.pull_request.base.sha` reads empty
there, the diff comes back empty, and the blocking sweep would skip silently
inside the merge queue, which is the last place anything should. This is the
same rule the change-scope decision already states for the merge base
("unresolvable inputs are errors, never empty scopes"); the sweep does not get
an exemption from it. The debt a skipped pull
request could still introduce is not lost — the post-merge run sees every
capability in full and reports it, which is the same report-don't-block posture
the rest of this design takes.

Left unstated, this whole area was load-bearing: the blocking sweep installed by
task 5.7 runs on the merge candidate for this very change, whose contract
citations (task 4.2) name requirements that task 4.1 adds in the delta and
nowhere else.

**"Touches" is defined, not implied.** The touched set is: operations whose
contract nodes changed in `git diff <merge-base>...HEAD` (node-level, not
file-level — two operations in one file are distinguishable); requirements
ADDED, MODIFIED, REMOVED, or RENAMED in the active change's spec delta; and
requirements named by citations or exclusions the diff adds or changes. The
REMOVED case is what couples requirement-removal to operation-removal. Change
scope only ever *restricts* what the full evaluation enforces — it never
enforces anything the sweep would not.

**Flipping an opt-in switch widens the touched set to what it governs.** Adding
a traceability block to a previously untraced document touches every operation
in that document; adding a capability's exclusions file touches every
requirement of that capability. Without this, the transition is invisible to a
node-level diff — creating an exclusions file changes no requirement node at
all, yet turns the whole capability's reverse direction blocking — and
`/validate-feature` would pass on the exact change that flips the switch, with
`main` reddening right after. This does not violate the restriction property
above: the sweep already enforces these surfaces the moment the switch lands, so
the change-scoped run is being made to agree with the sweep, not exceed it.

**The scope inputs fail closed.** The merge base is
`git merge-base <integration-branch> HEAD`, integration branch a parameter
defaulting to `main`; the active change is an explicit `--change <id>`
argument (there are ~34 change directories on disk — inference would guess).
An unresolvable merge base or missing change id is an **error**, never an
empty scope: a blocking gate that evaluates nothing while exiting zero is the
unfalsifiable-green artifact this change exists to eliminate. This repository
has already been bitten by the shallow-clone variant of exactly this
(`ci.yml`'s `fetch-depth: 0` comment), so the CI wiring task inherits that
requirement, and the resolver should reuse the existing
`resolve_merge_base` shape rather than growing a third implementation.

**Why the validation run must be diff-scoped.** A validation run checking the
full archived set would block every change to `agent-coordinator` on 47
pre-existing gaps it did not create. Adoption then requires fixing all 47 before
any unrelated work can be validated, which is how a gate gets disabled in its
first week.

This is the lesson the work-packages schema debt already taught this repository:
when adding a constraint to a codebase that does not yet satisfy it, assert **no
new violations**, never "everything validates". A ratchet is adoptable; a cliff
is not.

**Why the full sweep still exists.** Diff-scoping alone would never surface the
accumulated gaps — the 47 would stay invisible indefinitely, because no change
touches them. The main-branch sweep is what makes existing debt visible without
blocking anyone.

**The reporting-to-blocking transition needs no mechanism beyond opt-in, and
must not get one.** An earlier draft of this decision described a capability
"transitioning from reported to blocking once clean", which implied a
reported-to-blocking flag alongside the opt-in switches. There is no such
flag: **opting in *is* the transition**, per direction. A traced document
blocks forward; a capability with an exclusions file blocks reverse; everything
else reports. You opt in when the surface is clean, which is the only order in
which opting in can succeed.

Stated explicitly because the redundancy was nearly built. A flag meaning
almost the same thing as an opt-in switch is how a gate acquires a state where
it is opted in but not blocking — which is precisely the half-traced-but-green
outcome D6 exists to make impossible. D13's second *switch* is not that
redundancy: it switches a different claim (the reverse direction), not the
same claim's blocking behavior.

**Consequence.** The gate must accept a scope argument and must be honest in its
output about which context it ran in. A diff-scoped pass that printed
"traceability complete" would be a false claim about the capability.

---

### D13 — The two directions opt in separately; the exclusions file is the reverse switch

**Decision.** Forward enforcement opts in per contract document (D6). Reverse
enforcement opts in per capability, keyed on the existence of
`openspec/contracts/<capability>/traceability-exclusions.yaml` — which is also
where requirement-side exclusions live, in the shape
`check_coverage_completeness.py` established (`exclusions: [{requirement,
reason}]`). An empty exclusion list is valid and means every requirement must
be cited. A capability without the file has its uncited requirements reported,
never failed.

**Why a second switch is not the redundancy D12 struck.** D12 forbade a
reported-to-blocking flag *for the same claim* as an opt-in. Forward and
reverse are different claims with different owners: "every operation in this
document is justified" is a claim one document's author can make; "every
requirement of this capability is served or excused" is a claim about the
whole capability that no document can make. One switch per claim; no claim has
two.

**Why the exclusions file is the switch.** Three candidates were considered:

1. *Reverse enforcement implied by any document opting in (rejected).* Opting
   `locks.yaml` in would instantly demand a citation or exclusion for all 122
   coordinator requirements, and for gen-eval the 17-flag retrofit would drag
   ~31 requirements behind it. Measured, that is exactly how a gate gets
   disabled in its first week — and it silently makes task 5.2's staging
   impossible, which is what surfaced this decision.
2. *A standalone boolean marker (rejected).* A `reverse: true` flag can be
   flipped without doing any work, which invites flipping it aspirationally
   and then drowning in red — or worse, never flipping it because the first
   flip hurts.
3. *The exclusions file itself (selected).* Creating the file **is** the
   triage: every requirement must be either cited somewhere or given a written
   reason, so the switch cannot be flipped without doing the work it
   certifies. The file is also the artifact D4 already needs a home for, so
   the design adds one artifact, not two.

**An exclusions file may only excuse its own capability's requirements.** The
schema permits any `<capability>.<slug>` shape, so the constraint is the gate's
to enforce: an entry whose prefix is not the owning capability fails, naming
both. Cross-capability *citations* stay permitted (D9) and the asymmetry is the
point. A citation is additive — capability B can audit an operation in A that
claims to serve B's requirement, and D9 reports those as a distinct list. An
exclusion is subtractive: it discharges B's obligation from inside A's file,
where B's owner will never look. That is D4's laundering path arriving from
outside the capability, and it creates a state B cannot own — B's reverse
completeness would depend on a file B does not control and cannot audit.

**Why the requirement exclusions cannot live in a contract.** A requirement
with no operation has, by construction, no operation to hang an exclusion on.
The operation-side `excluded` shape in `traceability.schema.json` cannot
express it. Capability-scoped placement matches D10's evaluation unit: the
exclusion excuses the requirement from the *capability's* completeness, not
from one document's.

**Consequence for the flagship.** gen-eval-framework opts in both directions
(tasks 4.2, 4.2b) so the example demonstrates the full chain. The coordinator
opts in forward per document (5.2) and defers its reverse opt-in — triaging
122 requirements is the backlog this change creates, not work it performs.

---

## Risks

| Risk | Mitigation |
|---|---|
| Fuzzy-matching pressure — "surely we can auto-suggest citations" | D1 forbids it in the gate. A *suggestion tool* that a human accepts is not forbidden and is a reasonable follow-up; the line is that nothing unreviewed reaches the contract |
| The resolver becomes a second OpenSpec parser and drifts from the CLI's | Resolver reads the same markdown OpenSpec validates, and a test asserts every id it derives resolves against `openspec validate --strict` output for the same file |
| Reverse completeness makes adding a requirement expensive | It costs one exclusion line with a reason. If that is genuinely too expensive for a requirement, the requirement is probably prose rather than a requirement |
| Retrofit of gen-eval's contract balloons into rewriting its spec | Bounded: 17 flags, each needs one requirement or one exclusion. A flag that justifies neither is a finding about the flag |
| This change repeats `derive-descriptors-from-contracts`' own mistake of freezing a name and reusing it in one DAG | No names are reclaimed here. Every identifier introduced is new |

## Resolved questions

The three questions this design opened with were answered by the operator on
2026-07-27 and are now D9, D10 and D11. Recorded here with what each answer
cost, because two of them changed the shape of the change rather than just
filling a blank.

| Question | Answer | Where |
|---|---|---|
| May a citation name another capability's requirement? | Yes | D9 |
| Per contract or per capability? | Per capability | D10 |
| What about unarchived requirements? | Active change shadows the archive; other changes are invisible | D11 |

**"Per capability" was not a free choice.** It is forced by D9 — once a
requirement may be served from another capability, per-contract reverse
completeness reports true gaps as violations and the only remedy is a false
exclusion. It also unlocked the coordinator staging path in D10, which the
plan-time task 5.2 had assumed without checking against D6.

**D11's answer generated D12.** Deciding that the active change shadows the
archive raised the question of what the *rest* of the archive does during a
validation run, and answering that honestly required the diff-scoped/full-sweep
split. Without it the gate blocks unrelated work on pre-existing debt.

## Resolved: the two questions D9–D12 opened

Answered by the operator on 2026-07-27. Both confirmed the leaning, and the
first removed a mechanism rather than adding one.

**Reporting-to-blocking is per opt-in switch.** Recorded in D12 — and recording
it showed that opting in already *is* that transition, so the reported-to-
blocking flag the earlier wording implied has been struck rather than
specified. Plan iteration 1 subsequently found that "opt-in" itself named two
different claims (forward per document, reverse per capability) that four
documents assigned to three different units; D13 now separates them. The
mixed-capability case that exposed the contradiction — one traced document,
one untraced, same capability — has a scenario of its own.

**A cross-capability citation does not need the cited capability's consent.**
Reporting is enough for now. The gate names cross-capability citations as a
distinct list (D9); it does not ask `gen-eval-framework` to agree that
`agent-coordinator` serves one of its requirements.

Recorded with its revisit trigger, so "for now" has an end condition rather than
being indefinite: **revisit if a cross-capability citation reaches archive that
the cited capability's owner would have rejected.** That is the failure a
consent mechanism would prevent, and until it happens the mechanism is
speculative. If it does happen, the natural shape is an acknowledgement list on
the cited capability's side, not a veto — a veto would let one capability block
another's release over a bookkeeping disagreement.
