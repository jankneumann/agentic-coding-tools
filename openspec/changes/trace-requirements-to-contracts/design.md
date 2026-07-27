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
the candidate headings, or the two-minute fix becomes a twenty-minute hunt.

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

### D6 — Enforcement is opt-in per contract, keyed on the block's presence

**Decision.** A contract declaring a `traceability` block anywhere opts into
strict enforcement across all its operations. A contract with no such block
anywhere is recorded `untraced` and does not fail.

**Why.** The ri-08 context-impact gate pattern, chosen for the same reason:
enforcement keyed on whether the block exists is one-way. Declaring it commits
the whole contract, so nobody gets a half-traced contract that reports green
while most of it is unattributed. Omitting it is visible in the report rather
than silent.

It also makes the coordinator tractable. Its contract can land `untraced` and
tighten per subsystem, instead of blocking on 82 decisions before anything ships.

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
set. Opt-in (D6) is likewise per capability.

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
whole contract, deliberately — a half-traced contract reporting green is the
failure it exists to prevent. But the coordinator is one contract with 82
operations, so contract-level totality would mean tracing all 82 before any of
it counts. Splitting the document is the staging mechanism; lowering D6's bar is
not.

---

### D11 — The effective requirement set is the archive, shadowed by the active change

**Decision.** Resolution reads `openspec/specs/<capability>/spec.md`, with the
active change's `specs/` delta shadowing it: `ADDED` requirements appear,
`MODIFIED` replace their archived version, `REMOVED` disappear. Requirements
belonging to **other** in-flight changes are not in the universe — they can be
neither cited nor excluded.

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

| Context | Scope | Blocking |
|---|---|---|
| `/validate-feature` | Operations and requirements the change touches | Yes |
| CI on `main` | Every capability, in full | Opted-in capabilities block; untraced ones report |

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

**The reporting-to-blocking transition needs no new mechanism, and must not get
one.** An earlier draft of this decision described a capability "transitioning
from reported to blocking once clean", which implied a second switch alongside
D6's opt-in. There is no second switch: **opting a capability in *is* the
transition.** An untraced capability is reported; an opted-in capability blocks.
You opt in when the capability is clean, which is the only order in which
opting in can succeed.

Stated explicitly because the redundancy was nearly built. Two flags meaning
almost the same thing is how a gate acquires a state where it is opted in but
not blocking — which is precisely the half-traced-but-green outcome D6 exists to
make impossible.

**Consequence.** The gate must accept a scope argument and must be honest in its
output about which context it ran in. A diff-scoped pass that printed
"traceability complete" would be a false claim about the capability.

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

**Reporting-to-blocking is per capability.** Recorded in D12 — and recording it
showed that D6's opt-in already *is* that switch, so the second flag the earlier
wording implied has been struck rather than specified. The change is smaller for
having asked.

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
