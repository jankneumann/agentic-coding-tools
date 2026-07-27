# Tasks — Trace requirements to contracts

Test tasks precede the implementation they verify (RED before GREEN).
Sizes: XS ≤30min · S 30min–2hr · M 2hr–1day. No L or XL tasks.

Most work is in `packages/gen-eval/`. Phases 4 and 5 touch
`openspec/contracts/`, `skills/implement-feature/`, and `.github/workflows/`.

## Prerequisites

**`derive-descriptors-from-contracts` MUST LAND FIRST.** This change extends
`ToolDescriptor` / `ServiceDescriptor`, reuses the exclusion shape from
`scripts/check_coverage_completeness.py`, and writes into the
`openspec/contracts/<capability>/` layout. All three are that change's.

"Land" means its *code* is on `main`, not that its PR exists. Verify:

```bash
# The archetypes and the loader
cd packages/gen-eval && uv run python -c "
import sys
from gen_eval import ServiceDescriptor, ToolDescriptor
from gen_eval.descriptor import load_descriptor
print('prerequisite satisfied')"

# The exclusion gate whose shape D4 reuses
test -f packages/gen-eval/scripts/check_coverage_completeness.py
```

`uv run python`, not bare `python3` — `packages/gen-eval` is a src-layout
package and an unqualified interpreter resolves `gen_eval` from whatever is
installed, which on a developer machine is the coordinator's venv. A check run
that way answers a question about a different copy.

---

## Phase 1 — Requirement identifiers

- [ ] 1.1 Write tests for identifier derivation from spec headings `[S]`
  **Spec scenarios**: Requirement Identifiers Are Stable And Fail Closed (an identifier is derived from the heading)
  **Design decisions**: D2
  **Dependencies**: None
  **Note**: drive the REAL `openspec/specs/agent-coordinator/spec.md`, not a
  synthetic fixture. A fixture written alongside the resolver agrees with
  whatever the resolver does; the repository's own specs are the only input
  that can disagree.

- [ ] 1.2 Implement the requirement resolver `[M]`
  **Design decisions**: D2
  **Dependencies**: 1.1
  **Note**: reads `openspec/specs/<capability>/spec.md`, yields
  `<capability>.<slug>` per `### Requirement:` heading. No OpenSpec CLI
  dependency at runtime — the gate must work in an environment without npm.

- [ ] 1.3 Write a test that derived ids agree with OpenSpec's own parse `[S]`
  **Design decisions**: D2, and the "second parser drifts" risk
  **Dependencies**: 1.2
  **Note**: assert the resolver finds exactly the requirements
  `openspec validate --strict` accepts for the same file. Mark `integration` —
  it shells out to npx. This is the only guard against the resolver and the
  CLI diverging on what a requirement is.

- [ ] 1.4 Write tests for the effective requirement set `[S]`
  **Spec scenarios**: The Active Change's Spec Delta Shadows The Archived Spec (a citation to the change's own new requirement resolves); (removing a requirement breaks operations that still cite it); (another change's unarchived requirement cannot be referenced)
  **Design decisions**: D11
  **Dependencies**: 1.2
  **Note**: three shadowing cases and one exclusion case. The REMOVED case is
  the one that earns its keep — it is what couples requirement-removal to
  operation-removal, and nothing else in the repository does.
  **Note**: the "other change is invisible" test must assert the failure
  message says the requirement is not in the effective set, not merely "not
  found". The two are different problems with different fixes.

- [ ] 1.5 Implement effective-set resolution with delta shadowing `[M]`
  **Design decisions**: D11
  **Dependencies**: 1.4
  **Note**: parses ADDED / MODIFIED / REMOVED sections of the active change's
  delta. `openspec` renders these as `## ADDED Requirements` headings; read the
  same markdown, do not shell out.
  **Note**: other in-flight changes are not read at all. Do NOT scan
  `openspec/changes/*/specs/` — a resolver that can see them will eventually be
  asked to resolve against them.

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 2 — The traceability model

- [ ] 2.1 Write tests for parsing traceability blocks off contracts `[S]`
  **Spec scenarios**: Contracted Operations Cite The Requirements They Serve (an operation declares its citations)
  **Design decisions**: D1
  **Dependencies**: 1.2
  **Note**: cover both contract shapes — OpenAPI `x-traceability` on an
  operation, CLI contract `traceability` on a flag/command. One model, two
  surface spellings, as with `x-gen-eval-surface`.

- [ ] 2.2 Implement traceability parsing on both archetypes `[M]`
  **Design decisions**: D1
  **Dependencies**: 2.1
  **Note**: parse only. Resolution is 2.4, completeness is Phase 3. Keeping
  them separate is what lets 2.3 assert that nothing is inferred.

- [ ] 2.3 Write a test that no citation is ever inferred `[S]`
  **Spec scenarios**: Contracted Operations Cite The Requirements They Serve (an operation declares its citations)
  **Design decisions**: D1
  **Dependencies**: 2.2
  **Note**: the load-bearing negative. Give an operation a name and path that
  match a requirement heading almost exactly and assert it still cites
  nothing. Without this, a later "helpful" fuzzy matcher lands with every
  other test still green — and it is the one change that would silently make
  the whole gate worthless.

- [ ] 2.4 Write tests for unresolved-citation failure `[S]`
  **Spec scenarios**: Contracted Operations Cite The Requirements They Serve (a citation names a requirement that exists); Requirement Identifiers Are Stable And Fail Closed (a reworded heading breaks its citations)
  **Design decisions**: D2
  **Dependencies**: 2.2
  **Note**: assert the message names the unresolved id AND the candidate
  headings. A fail-closed rule whose message says only "not found" turns a
  two-minute fix into a twenty-minute hunt, and the rule gets removed.

- [ ] 2.5 Resolve citations and fail closed on unknown ids `[S]`
  **Design decisions**: D2
  **Dependencies**: 2.4, 1.2

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 3 — The completeness gate

- [ ] 3.1 Write tests for forward completeness `[S]`
  **Spec scenarios**: Traceability Completeness Is Enforced In Both Directions (an uncited operation fails the gate)
  **Design decisions**: D3
  **Dependencies**: 2.5
  **Note**: must be shown to FAIL. Assert the proportion-traced figure does not
  satisfy the gate in place of naming the operation — D6 rejects thresholds and
  this is where that would leak back in.

- [ ] 3.2 Write tests for reverse completeness `[S]`
  **Spec scenarios**: Traceability Completeness Is Enforced In Both Directions (an uncited requirement fails the gate)
  **Design decisions**: D3
  **Dependencies**: 2.5
  **Note**: this direction is detected by nothing else in the repository, so
  there is no second gate to fall back on if it is weak. Prove it fails on a
  requirement that exists and is cited by nothing.

- [ ] 3.3 Write tests for exclusions — blank reason, stale target `[S]`
  **Spec scenarios**: Traceability Exclusions State A Reason (a blank reason fails the gate); (a stale exclusion fails the gate)
  **Design decisions**: D4
  **Dependencies**: 2.5

- [ ] 3.4 Write tests for opt-in enforcement `[S]`
  **Spec scenarios**: Traceability Enforcement Is Opt-In Per Contract (declaring traceability commits the whole contract); (a contract with no traceability is recorded, not failed)
  **Design decisions**: D6
  **Dependencies**: 2.5
  **Note**: the untraced case must assert the status APPEARS in the output.
  A silently-passing untraced contract is indistinguishable from a compliant
  one, which is the failure mode ri-08 keyed its gate on presence to avoid.

- [ ] 3.5 Implement `scripts/check_traceability.py` `[M]`
  **Design decisions**: D3, D4, D5, D6
  **Dependencies**: 3.1, 3.2, 3.3, 3.4
  **Note**: reports every failure in one run, not the first. Mirror
  `check_coverage_completeness.py`'s structure — a suite is fixed in one pass
  rather than one build per gap.

- [ ] 3.6 Write tests that the output makes no satisfaction claim `[S]`
  **Spec scenarios**: The Gate Makes No Claim That A Requirement Is Satisfied (output does not claim satisfaction)
  **Design decisions**: D5
  **Dependencies**: 3.5
  **Note**: assert on the wording. "operations cite requirements" is the claim;
  "requirements are implemented / satisfied / verified" is not, and the whole
  value of D5 evaporates if the success message overstates it.

- [ ] 3.7 Write tests for concentration reporting `[S]`
  **Spec scenarios**: The Gate Reports Concentration Without Failing On It (concentration appears in the output)
  **Design decisions**: D7
  **Dependencies**: 3.5
  **Note**: assert it reports AND that it does not change the exit code. A
  concentration check that fails the build is a threshold, and D7 exists
  precisely because that threshold cannot be set honestly.

- [ ] 3.8 Implement concentration reporting `[S]`
  **Design decisions**: D7
  **Dependencies**: 3.7

- [ ] 3.9 Write tests for capability-scoped completeness `[S]`
  **Spec scenarios**: Completeness Is Evaluated Per Capability (a requirement served from another contract is covered); (a capability's contracts are evaluated as one surface)
  **Design decisions**: D9, D10
  **Dependencies**: 3.5
  **Note**: the discriminating fixture is a capability with TWO contracts where
  a requirement is cited from only one. A single-contract fixture passes under
  both the per-contract and per-capability rules and proves nothing.

- [ ] 3.10 Evaluate completeness per capability, unioning its contracts `[M]`
  **Design decisions**: D10
  **Dependencies**: 3.9
  **Note**: this is what makes splitting a capability's contract a staging
  mechanism rather than a weakening (see 5.2). Opt-in status is recorded per
  capability, not per file.

- [ ] 3.11 Write tests for cross-capability citations `[S]`
  **Spec scenarios**: Citations May Name Requirements In Another Capability (an operation cites another capability's requirement)
  **Design decisions**: D9
  **Dependencies**: 3.10
  **Note**: assert it resolves, does NOT fail, and DOES appear in the
  cross-capability report. The report is the whole value — a coupling that
  passes silently is a coupling nobody reviews.

- [ ] 3.12 Resolve and report cross-capability citations `[S]`
  **Design decisions**: D9
  **Dependencies**: 3.11

- [ ] 3.13 Write tests for change-scoped evaluation `[S]`
  **Spec scenarios**: Validation-Time Evaluation Is Scoped To The Change (a pre-existing gap does not fail a change that did not create it); (the output states which scope it evaluated)
  **Design decisions**: D12
  **Dependencies**: 3.10
  **Note**: must prove BOTH halves — the touched violation fails, the untouched
  pre-existing one is reported and does not. A test asserting only the first
  passes against a gate with no scoping at all.
  **Note**: the output-wording test is not cosmetic. A change-scoped run that
  printed "traceability complete" would be asserting something about the
  capability it did not check.

- [ ] 3.14 Implement change-scoped evaluation and the full sweep `[M]`
  **Design decisions**: D12
  **Dependencies**: 3.13
  **Note**: one gate, a `--scope change|capability` argument. Change scope
  derives touched operations from the diff against the merge base; capability
  scope reads everything. Do not build two scripts — they would drift, and the
  drift would be invisible because each is only run in one context.

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 4 — Retrofit the flagship example

- [ ] 4.1 Add flag-level requirements to the gen-eval spec `[M]`
  **Design decisions**: D1
  **Dependencies**: 3.5
  **Note**: the spec names three flags today, none of them among the 17 in the
  contract. Each contracted flag needs a requirement or an exclusion. A flag
  that justifies neither is a finding about the flag, not about this task —
  record it, do not delete the flag here.

- [ ] 4.2 Add citations to `openspec/contracts/gen-eval-framework/cli/gen-eval.yaml` `[S]`
  **Design decisions**: D1, D6
  **Dependencies**: 4.1
  **Note**: opting this contract in commits all 17 flags (D6). Regenerate the
  derived descriptor afterwards — `generate_tool_descriptor.py --check` runs
  in CI and will fail on the un-regenerated artifact.

- [ ] 4.3 Demonstrate the gate fails on gen-eval's own contract `[S]`
  **Spec scenarios**: Traceability Completeness Is Enforced In Both Directions (an uncited operation fails the gate)
  **Design decisions**: D3
  **Dependencies**: 4.2
  **Note**: remove one citation from the real contract, confirm the gate exits
  non-zero naming that flag, restore. On the real artifact, not a fixture —
  the equivalent step in `derive-descriptors-from-contracts` task 4.7 is what
  exposed that its predecessor was verifying a mirror.
  **Note**: clear `__pycache__` before the confirming run. A same-size,
  same-second restore reuses the mutant's bytecode and `inspect.getsource`
  will not reveal it.

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 5 — The coordinator contract, and CI

- [ ] 5.1 Author `openspec/contracts/agent-coordinator/openapi/v1.yaml` from the spec `[M]`
  **Design decisions**: D1, D6
  **Dependencies**: 3.5
  **Note**: **authored from `openspec/specs/agent-coordinator/spec.md`, NOT
  generated from the application.** `app.openapi()` produces the app
  describing itself; verifying the app against that compares it to a copy of
  itself and reports zero violations forever. Measured 2026-07-26: the app
  serves 82 operations, requirements name 35 of them.
  **Note**: lands `untraced` (D6). Scoping which subsystems opt in is 5.2.

- [ ] 5.2 Split the coordinator contract and opt one subsystem in `[M]`
  **Spec scenarios**: Traceability Enforcement Is Opt-In Per Contract (declaring traceability commits the whole contract); Completeness Is Evaluated Per Capability (a capability's contracts are evaluated as one surface)
  **Design decisions**: D6, D10
  **Dependencies**: 5.1, 3.10
  **Note (revised after D10)**: the plan-time version of this task assumed a
  subsystem could opt in while the rest of one contract stayed out. D6 forbids
  that — declaring traceability commits the whole contract, deliberately, so
  that a half-traced contract cannot report green. Splitting the document is
  the staging mechanism instead: `openspec/contracts/agent-coordinator/openapi/`
  holds `locks.yaml`, `work-queue.yaml` and so on, and D10's capability-level
  union means the split costs nothing in rigour.
  **Note**: start with locks or work-queue — small, and the operations the spec
  names most concretely. Proves the model on real requirements before anyone
  commits to all 82.

- [ ] 5.3 Record the unattributed operations as findings, not fixes `[S]`
  **Dependencies**: 5.1
  **Note**: the ~47 operations no requirement names are out of scope by
  construction (see proposal Scope). File them; do not spec them here. Deciding
  what each one is for is mostly not gen-eval's call.

- [ ] 5.4 Write tests for the generated Contract Ref column `[S]`
  **Design decisions**: D8
  **Dependencies**: 3.5
  **Note**: must fail on the current hand-filled matrix, which is the point —
  the column has never been checked against anything.

- [ ] 5.5 Generate `change-context.md`'s Contract Ref column from citations `[M]`
  **Design decisions**: D8
  **Dependencies**: 5.4
  **Note**: update `skills/implement-feature/SKILL.md` in the same commit. It
  currently instructs the implementer to fill the column by hand; leaving that
  text in place while generating the column is how the two disagree.

- [ ] 5.6 Wire the change-scoped gate into `/validate-feature` `[M]`
  **Spec scenarios**: Validation-Time Evaluation Is Scoped To The Change (a pre-existing gap does not fail a change that did not create it)
  **Design decisions**: D12
  **Dependencies**: 3.14, 4.2
  **Note**: this is the blocking gate — work is not validated until the
  operations it touched cite their requirements. Runs at `--scope change`.
  **Note**: `skills/validate-feature/SKILL.md` is the wiring point, and its
  spec-compliance step is the natural neighbour. Adding a gate to a skill means
  adding it to the skill's own tests too, or the wiring is unverified.
  **Note**: run it BARE, never piped. A pipeline's `$?` is the last stage's
  status, so `check_traceability.py | tail` reports tail's 0 on a failing gate.

- [ ] 5.7 Wire the full-capability sweep into CI on `main` `[S]`
  **Design decisions**: D12
  **Dependencies**: 3.14, 5.2
  **Note**: an opted-in capability blocks; an untraced one reports. There is NO
  separate blocking flag — D6's opt-in is the switch, and adding a second one
  would create an opted-in-but-not-blocking state, which is the half-traced-yet-
  green outcome D6 exists to make impossible.
  **Note**: this is what makes the coordinator's existing gaps visible without
  stopping unrelated work; diff-scoping alone would leave them invisible
  forever, since no change touches them.
  **Note**: bare invocation, as with `generate_tool_descriptor.py --check`. A
  gate whose two call sites disagree on argv reports failure on a correct tree.

- [ ] 5.8 Update `packages/gen-eval/README.md` with the four-edge chain `[S]`
  **Dependencies**: 5.6, 5.7
  **Note**: the README documents contract → descriptor → verify. State the edge
  above it, and state plainly what the gate does NOT claim (D5) — a reader who
  takes "traceability gate: pass" for "requirements are implemented" has been
  misled by the documentation, not by the gate.

- [ ] 5.9 Refresh `DOWNSTREAM.md` for consumers with their own contracts `[S]`
  **Dependencies**: 5.6, 5.7
  **Note**: ACA's tool contract is affected only if they opt in (D6). Say so
  explicitly — the previous notice's DS-2 had to be rewritten at implementation
  time because it promised a change that did not ship.

- [ ] Final checkpoint: full suite green, `openspec validate --strict` passes, both gates demonstrated to fail on an unmodified tree
