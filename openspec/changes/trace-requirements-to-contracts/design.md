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

## Risks

| Risk | Mitigation |
|---|---|
| Fuzzy-matching pressure — "surely we can auto-suggest citations" | D1 forbids it in the gate. A *suggestion tool* that a human accepts is not forbidden and is a reasonable follow-up; the line is that nothing unreviewed reaches the contract |
| The resolver becomes a second OpenSpec parser and drifts from the CLI's | Resolver reads the same markdown OpenSpec validates, and a test asserts every id it derives resolves against `openspec validate --strict` output for the same file |
| Reverse completeness makes adding a requirement expensive | It costs one exclusion line with a reason. If that is genuinely too expensive for a requirement, the requirement is probably prose rather than a requirement |
| Retrofit of gen-eval's contract balloons into rewriting its spec | Bounded: 17 flags, each needs one requirement or one exclusion. A flag that justifies neither is a finding about the flag |
| This change repeats `derive-descriptors-from-contracts`' own mistake of freezing a name and reusing it in one DAG | No names are reclaimed here. Every identifier introduced is new |

## Open questions

- Should a citation be allowed to name a requirement in *another* capability's
  spec? Cross-capability operations exist (the coordinator serves gen-eval's
  scenarios). Leaning yes, with the id's capability prefix making it explicit.
- Should the gate run per contract or per capability? Per contract is simpler;
  per capability is what reverse completeness actually needs, since a
  requirement may be served by an operation in a different contract.
- What does the gate do about requirements in `openspec/changes/<id>/specs/`
  that have not been archived into `openspec/specs/` yet? They describe a
  surface that does not exist. Leaning: resolve against both, and treat an
  unarchived requirement as automatically excluded until it lands.
