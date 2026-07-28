# Change: Trace requirements to contracts

## Why

`derive-descriptors-from-contracts` made the contract the declared surface and
built a gate that reports any interface the implementation exposes and the
contract omits. That works. It is also the bottom half of a four-edge chain:

```
requirement  ──?──>  contract  ──✓──>  descriptor  ──✓──>  declared surface
                                                                  ↑ ✓ verify
                                                             implementation
```

Nothing establishes the first edge. A contract can be perfectly implemented,
perfectly verified, and fully covered while describing something no requirement
asks for — and every gate below stays green while it happens. Green gates on an
unasked-for system is a worse outcome than red gates, because nobody looks.

**Measured on this repository, 2026-07-26.** The coordinator's OpenAPI surface
against `openspec/specs/agent-coordinator/spec.md`:

| | |
|---|---|
| Operations the application serves | 82 |
| Operations a requirement names | 35 |
| **Operations no requirement names** | **47** |
| Requirements naming an operation that does not exist | 10 |

The match is by `METHOD /path` string, so some of the 47 are legitimate
infrastructure (`/live`, `/ready`) and some requirements describe an operation
without spelling its route. The exact figure is not the claim. The claim is that
**nobody knows which**, because nothing has ever asked.

`derive-descriptors-from-contracts` has the same gap in its own flagship
example. `openspec/contracts/gen-eval-framework/cli/gen-eval.yaml` declares
itself "ground truth", and its 17 flags were transcribed from `__main__.py`'s
argparse. The gen-eval spec names three flags, none of them among the 17. So the
subset verifier compares the real parser against a hand-transcription of the
real parser — better than a mirror, because a human could have disagreed while
transcribing, but not derived from any requirement.

This is the same failure family that change spent 65 tasks eliminating one level
down: a `--check` that could only fail, a verifier that mirrored its own
reference, a coverage gate that passed on an empty set. Same shape, one level
up, at the level where being wrong costs the most.

## What Changes

- **Contracted operations cite requirements.** A `traceability` block on each
  operation (OpenAPI `x-traceability`, CLI contract `traceability`) naming the
  requirement ids it serves.
- **A bidirectional completeness gate**, in the shape D11 already established
  for coverage units. An operation citing no requirement fails. A requirement
  no operation cites fails. Either may be excluded, and an exclusion without a
  stated reason fails. Operation exclusions live on the operation in the
  contract; requirement exclusions live in a per-capability
  `traceability-exclusions.yaml`, whose existence is also the reverse
  direction's opt-in switch (D13).
- **Evaluated per capability, not per contract.** A requirement may legitimately
  be served by an operation in another capability's contract, so a per-contract
  run would report genuinely-served requirements as gaps. This also makes
  splitting a capability's contract a staging mechanism rather than a weakening.
- **Two run contexts, one gate.** At `/validate-feature` it is scoped to what
  the change touches and blocks. On the integration branch it sweeps every
  capability: opted-in surfaces block, the rest report. Enforcing the full set
  at validation would block every change to a capability on gaps it did not
  create.
- **Requirement ids become addressable.** OpenSpec requirements have headings,
  not ids. A stable id derived from `<capability>.<slug>` plus a resolver, so a
  citation can be checked rather than believed.
- **`change-context.md`'s Contract Ref column gets a gate.** The traceability
  matrix already asks for exactly this mapping and nothing verifies it. The
  matrix becomes generated from the citations rather than hand-filled.
- **The coordinator contract is authored from its spec**, not generated from
  its app, and the 47 unattributed operations become the first backlog.
- **gen-eval's own CLI contract is retrofitted**, so the flagship example
  demonstrates the whole chain rather than its lower half.

## Scope

**In scope**

- `packages/gen-eval/` — the traceability model, the resolver, the gate
- `openspec/contracts/gen-eval-framework/cli/gen-eval.yaml` — retrofit
- `openspec/contracts/gen-eval-framework/schemas/` — `cli-contract.schema.json`
  extended to admit `traceability`; both new schemas promoted in flight
- `openspec/contracts/gen-eval-framework/traceability-exclusions.yaml` — the
  flagship's reverse opt-in
- `openspec/contracts/agent-coordinator/openapi/v1.yaml` — new, authored
- `openspec/specs/gen-eval-framework/spec.md` — requirements for the above
- `openspec/specs/skill-workflow/spec.md` — Contract Ref generation and the
  validation-time gate, since that capability specs both behaviors today
- `skills/implement-feature/` — the Contract Ref column becomes generated
- `skills/validate-feature/` — the change-scoped gate wiring
- `.github/workflows/ci.yml` — the gate

**Out of scope**

- **Generating contracts from requirements.** See "Approaches Considered".
- **Fixing the 47.** This change makes them visible and forces a decision per
  operation; deciding is separate work and mostly not gen-eval's to do.
- **Retrofitting every capability.** The gate is opt-in, in the ri-08 pattern,
  with one switch per direction (D13): declaring a `traceability` block opts a
  contract document into forward enforcement; creating a capability's
  `traceability-exclusions.yaml` opts it into reverse enforcement. Surfaces
  that have opted into neither are recorded and reported, never failed.
- **The coordinator's reverse opt-in.** Triaging its 122 requirements into
  citations and exclusions is the backlog this change creates. Task 5.2 opts
  one contract *document* in — forward only.
- **Other in-flight changes' requirements.** The effective requirement set is
  the archived specs shadowed by the *active* change's delta. Another change's
  unarchived requirements are neither citable nor excludable — an exclusion
  written against one becomes wrong rather than stale the moment that change
  archives, and no staleness check can catch it.
- **Requirement-level test coverage.** Whether a requirement is *tested* is the
  coverage model's job and already exists. This change is about whether it is
  *contracted*.

## Dependencies

- **`derive-descriptors-from-contracts` must land first.** This change extends
  `ToolDescriptor` / `ServiceDescriptor` and reuses `_ANNOTATION_KEYS`,
  `check_coverage_completeness.py`'s exclusion shape, and the
  `openspec/contracts/<capability>/` layout. All are that change's.
- OpenSpec CLI ≥ 1.0 for `validate --strict`.
- No coordinator runtime dependency. The gate is a static read of two files.

## Approaches Considered

### A. Generate contracts from requirements

Parse SHALL clauses and emit OpenAPI.

**Rejected.** "The system SHALL allow an agent to acquire a lock on a file path"
does not contain `POST /locks/acquire`, its request schema, its status codes, or
its idempotency semantics. Those are design decisions, and a generator would
have to invent them. The output would be a contract nobody designed, carrying
the authority of a generated artifact — and the implementation would then be
verified against invented decisions. That is worse than the gap it closes.

The asymmetry with `derive-descriptors-from-contracts` is real and worth stating
plainly: contract → descriptor **is** a derivation, because a descriptor is a
projection of a contract with no information added. Requirement → contract adds
information. Derivation is the wrong verb for an edge that adds information.

### B. Traceability with bidirectional completeness — **selected**

Do not generate the contract. Require it to *cite*, and gate both directions.

The citation is written by whoever designs the operation, at the moment they
design it, when the requirement is in their head. The gate never asks whether
the design is right — only whether someone said which requirement it serves, and
whether any requirement was left without one.

This is D11's rule one level up, and deliberately so. D11 rejected a coverage
*percentage* because "84% covered" does not say whether the missing 16% is
`--verbose` or `--fail-threshold`. The same argument applies here with more
force: "82 operations, 35 traced" says nothing about whether the untraced 47 are
health probes or an entire unasked-for subsystem.

### C. Requirement ids as a first-class OpenSpec feature

Add an `id:` field to requirement headings upstream in OpenSpec.

**Deferred, not rejected.** It is the better long-term answer and this change
would consume it. But it is a change to a shared external tool, on someone
else's schedule, and the derived-id resolver here works without it. If OpenSpec
adopts explicit ids the resolver becomes a thin adapter.

## Selected Approach

B, with C's resolver as a compatibility layer.

## Traceability Semantics

A citation is a claim by the contract author that an operation exists to serve
one or more requirements. The gate checks four things, and deliberately not a
fifth.

| Check | Fails when |
|---|---|
| Citation resolves | A cited requirement id matches no requirement |
| Forward completeness | A contracted operation cites nothing and is not excluded |
| Reverse completeness | A requirement is cited by nothing and is not excluded |
| Exclusions are explained | An exclusion carries no reason, or names something that no longer exists |

**Not checked: whether the operation actually satisfies the requirement.** No
static analysis can decide that, and a gate that pretended to would be the
worst artifact in this document — an unfalsifiable green light over a
correctness claim. Satisfaction is what scenarios and review are for. This gate
establishes only that the question was asked and answered by a human.

The reverse direction is the one that finds things nothing else can. A
requirement with no contracted operation is either unimplemented, implemented
without an interface, or obsolete. All three are worth knowing and none of them
show up anywhere today.

## Acceptance Outcomes

- A contracted operation citing no requirement fails CI, naming the operation.
- A requirement cited by no operation, in a capability that has opted into
  reverse enforcement, fails CI naming the requirement.
- A citation naming a requirement that does not exist fails CI.
- An exclusion with a blank reason fails CI.
- An exclusion naming a requirement or operation that no longer exists fails CI.
- A well-formed exclusion suppresses the corresponding completeness failure,
  in both directions, and its reason appears in the output.
- A contract document with no `traceability` block anywhere is recorded
  `untraced` and does not fail; a capability without a
  `traceability-exclusions.yaml` has uncited requirements reported, not
  failed — one opt-in switch per direction (D13).
- Two requirement headings deriving the same identifier fail the resolver,
  naming both.
- A contract document that cannot be parsed fails the gate naming the file —
  it is never recorded `untraced`.
- A requirement served by an operation in another contract of the same
  capability is treated as cited.
- A cross-capability citation resolves, does not fail, appears in the gate's
  cross-capability report, and counts toward the cited capability's reverse
  completeness.
- Removing a requirement makes every operation still citing it fail.
- A change-scoped run fails on a touched violation, reports an untouched
  pre-existing one, and says in its output that it was change-scoped.
- A change-scoped run fails when the change adds a requirement (to a
  reverse-enforced capability) that nothing cites or excludes.
- A change-scoped run whose merge base or change id cannot be resolved errors;
  it never passes on an empty touched set.
- The full sweep on the integration branch fails on violations in opted-in
  surfaces and reports the rest.
- `gen-eval.yaml`'s 17 flags each cite a requirement or carry an exclusion,
  and `openspec/contracts/gen-eval-framework/traceability-exclusions.yaml`
  covers every gen-eval-framework requirement with no CLI surface — the
  flagship demonstrates both directions.
- `openspec/contracts/agent-coordinator/openapi/v1.yaml` exists, is authored
  from the spec rather than generated from the app, and every one of its
  operations cites or is excluded.
- The `change-context.md` Contract Ref column is generated from citations.
- Every gate above is demonstrated to fail on its documented mutation — and to
  pass again after restore — before the work that makes it pass is accepted.

## Risks

| Risk | Mitigation |
|---|---|
| Citations become a box-ticking ritual — every operation cites the same catch-all requirement | The resolver reports citation concentration; a requirement cited by an implausible share of operations is surfaced in the gate's output, not failed. Judgement stays with the reviewer |
| The coordinator's 47 stall this change | They are out of scope by construction. The gate ships opt-in; the coordinator contract can land `untraced` and be tightened per subsystem |
| Derived requirement ids break when a heading is reworded | Ids derive from a slug, so rewording renames. The gate fails closed (a citation stops resolving) rather than silently rebinding. An explicit `id:` upstream (approach C) removes this |
| Reverse completeness floods on aspirational requirements | Exclusions with reasons absorb them, and the reason is the useful artifact — "no interface, enforced by review" is a real answer that nothing records today |
| The validation gate blocks unrelated work on pre-existing debt | D12 scopes the validation run to what the change touches and reports the rest. Same lesson as the work-packages schema debt: assert no NEW violations, never "everything validates" |
| Diff-scoping hides the existing gaps forever, since no change touches them | The integration-branch sweep (D12) reports them in full without blocking. A surface starts blocking by opting in (D6 forward, D13 reverse) — opting in is the only switch, and there is no separate reported-to-blocking flag |
| Cross-capability citations become a way to launder a gap into someone else's capability | Reported as a distinct list rather than folded into the pass (D9). The judgement stays with a reviewer, which is the same call D7 makes about concentration |
| gen-eval's spec has to grow ~17 flag-level requirements to retrofit its own contract | That is the point, and it is small. If a flag cannot be justified by a requirement, the finding is about the flag |
| The flagship's reverse opt-in demands a decision for every gen-eval-framework requirement (~31 plus this change's own), not just the 17 flags | Task 4.2b authors the exclusions file as its own sized task; the reasons ("no CLI surface; served by the framework API" and kin) are the artifact, and writing them is the triage D13 makes the switch certify |
| Scope creep into "is the requirement satisfied" | Stated as explicitly out of scope above, and the gate has no mechanism that could express it |
