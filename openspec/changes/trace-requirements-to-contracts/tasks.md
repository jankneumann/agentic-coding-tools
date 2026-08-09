# Tasks — Trace requirements to contracts

Test tasks precede the implementation they verify (RED before GREEN).
Sizes: XS ≤30min · S 30min–2hr · M 2hr–1day. No L or XL tasks.
Tasks tagged `[human]` are judgement work — deciding which requirement an
operation serves — and MUST NOT be dispatched to implementer agents (D1: the
gate cannot tell a considered citation from a guessed one). Untagged tasks are
ordinary engineering.

**RED-demonstration protocol** (referenced by every "shown to FAIL" note):
apply the task's documented mutation M → run the gate bare (never piped — a
pipeline's `$?` is the last stage's status) → record the command, the exit
code, and the output line naming the target → restore → re-run → record exit
0. For pytest-driven checks, a test that constructs the failing input under
`tmp_path` and asserts the non-zero exit and the naming line IS the
demonstration; for the phase 4/5 demonstrations against real artifacts, the
recorded command + exit-code pair is the evidence and goes in the checkpoint.

Most work is in `packages/gen-eval/`. Phases 4 and 5 touch
`openspec/contracts/`, `skills/implement-feature/`, `skills/validate-feature/`,
and `.github/workflows/`.

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

- [x] 1.1 Write tests for identifier derivation from spec headings `[S]`
  **Spec scenarios**: Requirement Identifiers Are Stable And Fail Closed (an identifier is derived from the heading); (two headings deriving the same identifier fail the resolver)
  **Design decisions**: D2
  **Dependencies**: None
  **Note**: drive the REAL specs — every `openspec/specs/*/spec.md`, not just
  `agent-coordinator` and not a synthetic fixture. A fixture written alongside
  the resolver agrees with whatever the resolver does; the repository's own
  specs are the only input that can disagree. Assert every derived id matches
  the `traceability.schema.json` citation pattern — the repository has
  headings starting with backticks and containing em-dashes, and those are
  exactly the ones a naive slug rule turns into schema-invalid ids.
  **Note**: the collision test constructs its colliding pair under `tmp_path`
  (no real collision exists across the 632 current headings — that is the
  point of adding the check now).

- [x] 1.2 Implement the requirement resolver `[M]`
  **Design decisions**: D2
  **Dependencies**: 1.1
  **Note**: reads `openspec/specs/<capability>/spec.md`, yields
  `<capability>.<slug>` per `### Requirement:` heading under D2's normative
  slug algorithm. No OpenSpec CLI dependency at runtime — the gate must work
  in an environment without npm.
  **Note**: the specs root and changes root are PARAMETERS with no
  repo-relative default baked into the module. `gen_eval` is installed
  standalone by downstream consumers, where `openspec/` does not exist — do
  not hardcode `parent.parent` hops (see `findings_emitter.py` for the
  ancestor-search precedent). `scripts/check_traceability.py` resolves the
  defaults; tests inject `tmp_path` roots.

- [x] 1.3 Write a test that derived ids agree with OpenSpec's own parse `[S]`
  **Design decisions**: D2, and the "second parser drifts" risk
  **Dependencies**: 1.2
  **Note**: assert the resolver finds exactly the requirements
  `openspec show <capability> --json --type spec` enumerates for the same
  file (`validate --strict` returns a verdict, not a requirement list). Shell
  out to the binary resolved via `shutil.which("openspec")` — NOT `npx`;
  there is no root `package.json`, so `npx` would attempt a registry fetch.
  Mark `integration` AND `skipif(shutil.which("openspec") is None)`. This is
  the only guard against the resolver and the CLI diverging on what a
  requirement is.

- [x] 1.4 Write tests for the effective requirement set `[S]`
  **Spec scenarios**: The Active Change's Spec Delta Shadows The Archived Spec (a citation to the change's own new requirement resolves); (removing a requirement breaks operations that still cite it); (renaming a requirement moves its identifier, fail-closed); (another change's unarchived requirement cannot be referenced)
  **Design decisions**: D11
  **Dependencies**: 1.2
  **Note**: the ADDED case drives this change's own real delta and the
  other-change-invisible case drives the ~34 real change directories. The
  REMOVED and RENAMED cases have NO instance in the repository today — they
  are constructed under `tmp_path` via the injectable roots from 1.2, which
  is why those roots exist. The REMOVED case is the one that earns its keep —
  it is what couples requirement-removal to operation-removal, and nothing
  else in the repository does.
  **Note**: the "other change is invisible" test must assert the failure
  message says the requirement is not in the effective set, not merely "not
  found". The two are different problems with different fixes.

- [x] 1.5 Implement effective-set resolution with delta shadowing `[M]`
  **Design decisions**: D11
  **Dependencies**: 1.4
  **Note**: parses ADDED / MODIFIED / REMOVED / RENAMED sections of the
  active change's delta. `openspec` renders these as `## ADDED Requirements`
  headings; read the same markdown, do not shell out. RENAMED (and a MODIFIED
  block that rewords its heading) moves the identifier: the old id stops
  resolving, the new one starts — ignoring RENAMED fails open in both
  directions at once (D11).
  **Note**: other in-flight changes are not read at all. Do NOT scan
  `openspec/changes/*/specs/` — a resolver that can see them will eventually be
  asked to resolve against them.

- [x] Checkpoint: run tests, review diff, verify scope

## Phase 2 — The traceability model

- [x] 2.0 Extend the CLI contract schema and promote the traceability schemas `[S]`
  **Design decisions**: D13, and the contracts/README.md Promotion section
  **Dependencies**: None (runs first in this phase — 2.1's fixtures must be
  schema-valid)
  **Note**: `cli-contract.schema.json` sets `additionalProperties: false` on
  command, flag, and positional objects, so `traceability:` is REJECTED today
  and `ToolCommandSpec(**c)` would silently drop it. Add an optional
  `traceability` property at those three levels, `$ref`-ing the promoted
  traceability schema, plus rejection tests for still-unknown keys.
  **Note**: promote `contracts/traceability.schema.json` and the new
  `contracts/traceability-exclusions.schema.json` to
  `openspec/contracts/gen-eval-framework/schemas/`, `$id` rewritten to the
  promoted location (mirror `test_cli_contract_schema.py`'s
  `test_id_matches_promoted_location`), and add a test that loads each
  promoted copy — the predecessor's promotion has exactly this guard, and
  without it the promotion silently does not happen.
  **Note**: the promotion adds two files under `openspec/contracts/**`, which
  is the input the `api.contracts` producer renders into
  `docs/architecture-analysis/contracts-inventory.md` — a count in the header
  (`_13 contract schema(s)._` today, becoming 15) plus one row per schema.
  Run `python3 skills/project-context-refresh/scripts/cli.py refresh --producer
  api.contracts` and commit the regenerated inventory IN THIS TASK'S COMMIT.
  Use the single-producer form, NOT `make context-refresh` — that target is
  `generate-all`, which also runs the `documentation.inventory` and
  `decisions.timeline` producers, whose outputs (`skills-inventory.md`,
  `docs/decisions/`) are outside wp-model's `write_allow`. Any unrelated drift
  in those two would be regenerated into paths the package may not write,
  tripping its own scope check. Skipping the refresh entirely leaves CI's
  `context-drift-gate` red as
  `blocking_drift`, and because a staled derived artifact is absent from the
  diff by definition, no reviewer will see it — the predecessor change hit
  exactly this and nine review rounds missed it.

- [x] 2.1 Write tests for parsing traceability blocks off contracts `[S]`
  **Spec scenarios**: Contracted Operations Cite The Requirements They Serve (an operation declares its citations)
  **Design decisions**: D1
  **Dependencies**: 2.0, 1.2
  **Note**: cover both contract shapes — OpenAPI `x-traceability` on an
  operation, CLI contract `traceability` on a flag/command. One model, two
  surface spellings, as with `x-gen-eval-surface`.

- [x] 2.2 Implement traceability parsing on both archetypes `[M]`
  **Design decisions**: D1
  **Dependencies**: 2.1
  **Note**: parse only. Resolution is 2.5, completeness is Phase 3. Keeping
  them separate is what lets 2.3 assert that nothing is inferred.
  **Note**: the traceability field goes on the ARCHETYPE-ONLY models —
  `FlagSpec`, `PositionalSpec`, `ToolCommandSpec` (tool) and `OperationSpec`
  (service). It MUST NOT go on `ServiceSpec`, `EndpointSpec`, `CommandSpec`,
  or `McpToolSpec`: those are reachable from `InterfaceDescriptor` and would
  drift `interface-descriptor.schema.json`, which
  `generate_contract_schemas.py --check` (ci.yml:411) fails on and which no
  work package can regenerate. The field's default MUST be the absent value,
  so `generate_tool_descriptor.py`'s `exclude_defaults=True` keeps
  `evaluation/descriptor.yaml` byte-identical (ci.yml:431).

- [x] 2.3 Write a test that no citation is ever inferred `[S]`
  **Spec scenarios**: Contracted Operations Cite The Requirements They Serve (an operation declares its citations)
  **Design decisions**: D1
  **Dependencies**: 2.2
  **Note**: the load-bearing negative. Give an operation a name and path that
  match a requirement heading almost exactly and assert it still cites
  nothing. Without this, a later "helpful" fuzzy matcher lands with every
  other test still green — and it is the one change that would silently make
  the whole gate worthless.

- [x] 2.4 Write tests for unresolved-citation failure `[S]`
  **Spec scenarios**: Contracted Operations Cite The Requirements They Serve (a citation names a requirement that exists); Requirement Identifiers Are Stable And Fail Closed (a reworded heading breaks its citations)
  **Design decisions**: D2
  **Dependencies**: 2.2
  **Note**: assert the message names the unresolved id AND the nearest
  candidate headings, bounded to five, ranked by edit distance. A fail-closed
  rule whose message says only "not found" turns a two-minute fix into a
  twenty-minute hunt, and the rule gets removed. Ranking is display-only —
  assert it never rebinds.

- [x] 2.5 Resolve citations and fail closed on unknown ids `[S]`
  **Design decisions**: D2
  **Dependencies**: 2.4, 1.2

- [x] Checkpoint: run tests, review diff, verify scope

## Phase 3 — The completeness gate

- [x] 3.1 Write tests for forward completeness `[S]`
  **Spec scenarios**: Traceability Completeness Is Enforced In Both Directions (an uncited operation fails the gate)
  **Design decisions**: D3
  **Dependencies**: 2.5
  **Note**: must be shown to FAIL per the RED protocol. The discriminating
  fixture is ten operations, nine citing, one not: assert the gate fails
  naming the one — a gate satisfied by the 90% proportion is the threshold
  D6 rejects leaking back in.

- [x] 3.2 Write tests for reverse completeness `[S]`
  **Spec scenarios**: Traceability Completeness Is Enforced In Both Directions (an uncited requirement fails the gate); (every failure is reported in one run)
  **Design decisions**: D3, D13
  **Dependencies**: 2.5
  **Note**: this direction is detected by nothing else in the repository, so
  there is no second gate to fall back on if it is weak. Prove it fails on a
  requirement that exists, is cited by nothing, in a capability with an
  exclusions file present.
  **Note**: the every-failure test constructs at least two uncited operations
  AND at least two uncited requirements and asserts the finding count equals
  the violation count — a fail-fast regression reports 1 of 4 and this is
  the only test that catches it.

- [x] 3.3 Write tests for operation exclusions — blank reason, stale target, valid suppression `[S]`
  **Spec scenarios**: Traceability Exclusions State A Reason (a blank reason fails the gate); (a stale exclusion fails the gate); (an excluded operation does not fail forward completeness)
  **Design decisions**: D4
  **Dependencies**: 2.5
  **Note**: the suppression case is load-bearing — an implementation that
  ignores exclusions entirely passes every failure-side test. Assert the
  excluded operation does NOT fail AND that the exclusion's reason appears in
  the output.

- [x] 3.4 Write tests for requirement exclusions and the reverse opt-in switch `[S]`
  **Spec scenarios**: Traceability Exclusions State A Reason (an excluded requirement does not fail reverse completeness); Reverse Enforcement Is Opt-In Per Capability Via The Exclusions File (the exclusions file's presence enforces reverse completeness); (without the exclusions file, uncited requirements are reported)
  **Design decisions**: D4, D13
  **Dependencies**: 2.5
  **Note**: requirement exclusions live in
  `openspec/contracts/<capability>/traceability-exclusions.yaml` (fixtures:
  the equivalent path under `tmp_path`), shape
  `exclusions: [{requirement, reason}]` per
  `traceability-exclusions.schema.json`. Cover: file present + uncited
  requirement → fail; file present + excluded requirement → pass with reason
  in output; file absent + uncited requirement → reported, exit zero; file
  present with empty list → every requirement must be cited.
  **Note**: add the ownership case — an exclusions file under capability `A`
  naming a requirement of capability `B` must FAIL naming both, and `B`'s
  requirement must still count against `B`'s reverse completeness. Four
  reviewers independently flagged the unspecified version of this as a
  laundering path: cross-capability citations are permitted (D9) because they
  are additive and auditable by the cited capability, but an exclusion is
  subtractive and would discharge `B`'s obligation from a file `B` neither
  controls nor reads.

- [x] 3.4b Write tests that an unreadable exclusions file fails closed `[S]`
  **Spec scenarios**: The Gate Fails Closed On Malformed Input (an unreadable exclusions file fails rather than opting out)
  **Design decisions**: D13, D4
  **Dependencies**: 2.5
  **Note**: this is the highest-consensus finding of the plan review — all
  four reviewers reached it independently. D13 makes the file's EXISTENCE the
  reverse switch, so "cannot parse it" and "it isn't there" are one byte apart
  in consequence and opposite in meaning. Cover: unparseable YAML, schema-
  invalid content, a zero-byte file (YAML `None`, which the schema rejects
  since `exclusions` is required), and an unreadable file (chmod 000). Each
  must exit non-zero naming the file, and none may report the capability's
  reverse direction as not opted in.
  **Note**: assert the NEGATIVE explicitly — that the output does not contain
  the not-opted-in status. Asserting only the non-zero exit would still pass
  if the gate failed for an unrelated reason while silently opting out.

- [x] 3.5 Write tests for forward opt-in enforcement `[S]`
  **Spec scenarios**: Forward Enforcement Is Opt-In Per Contract Document (declaring traceability commits the whole contract document); (a contract with no traceability is recorded, not failed); (a traced and an untraced document coexist in one capability)
  **Design decisions**: D6
  **Dependencies**: 2.5
  **Note**: the untraced case must assert the status APPEARS in the output.
  A silently-passing untraced contract is indistinguishable from a compliant
  one, which is the failure mode ri-08 keyed its gate on presence to avoid.
  **Note**: the mixed-capability fixture (one traced document, one untraced,
  same capability) is the case that exposed the plan's original opt-in
  contradiction — assert forward enforcement on the traced document only,
  untraced status for the other, and the traced document's citations counting
  toward reverse completeness.

- [x] 3.6 Write tests for malformed input and document discovery `[S]`
  **Spec scenarios**: The Gate Fails Closed On Malformed Input (an unparseable contract fails the gate); (a schema-invalid traceability block fails the gate); (contracts without a capability spec fail distinctly); (a specless capability that has not opted in is reported); (a capability with a spec and no contracts is forward-untraced); (a contract instance outside openapi/ or cli/ is reported); (a newly misplaced instance fails change scope); (README and the exclusions file are never instances); (a schemas-only capability holds no contract documents)
  **Design decisions**: D6, and the schema's `oneOf`/`minItems` rationale
  **Dependencies**: 2.5
  **Note**: the unparseable case is the dangerous one — enforcement is keyed
  on block presence, so a parse error that reads as "no blocks" downgrades a
  traced contract to untraced and a syntax error goes green. Assert non-zero
  exit naming the file, and assert the document is NOT listed as untraced.
  **Note**: a contract DOCUMENT is an instance under `openapi/` or `cli/`
  (D6). Files under `schemas/` are contract schemas and carry no operations.
  Measured 2026-07-28, three real capabilities — `phase-record`,
  `project-context-refresh`, `prototyping` — hold only `schemas/` and have no
  spec directory; under the loose reading they would each trip the
  missing-spec rule and red `main` the moment this change merged. Fixture
  both: a schemas-only capability (no failure) and a traced instance with no
  spec (failure).
  **Note**: cover the misplaced instance, and cover it as a RATCHET, not a
  cliff. `code-search/v2.yaml` is a full OpenAPI 3.1 document at the capability
  root rather than under `openapi/`, contrary to `contracts/README.md`'s own
  layout table. A discovery walk keyed on the two directories would silently
  skip it — the invisible-surface failure this change exists to prevent — but
  failing on it would red the tree the day the sweep lands and contradict
  5.7c. Three assertions: (a) the sweep REPORTS a pre-existing root instance
  naming the file and the expected location and exits zero on that account;
  (b) change scope FAILS when the diff adds or modifies a root instance;
  (c) `README.md` and `traceability-exclusions.yaml` at a capability root are
  not instances — the second matters most, since D13 puts the reverse opt-in
  switch at exactly that path, and a location-based rule would make flipping
  the switch fail the gate. Identification is structural: top-level `openapi`
  key or top-level `tool` key (verified against `gen-eval.yaml`, whose top
  level is `contract_version`, `tool`, `commands`, `exit_codes`).

- [x] 3.7 Implement `scripts/check_traceability.py` `[M]`
  **Design decisions**: D3, D4, D5, D6, D13
  **Dependencies**: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
  **Note**: reports every failure in one run, not the first. Mirror
  `check_coverage_completeness.py`'s structure — a suite is fixed in one pass
  rather than one build per gap.
  **Note**: takes `--contracts-root`, `--specs-root`, `--changes-root`,
  `--repo-root`, and `--base-ref` with repo-relative defaults, in the shape
  of `check_coverage_completeness.py`'s `--report`/`--exclusions`. This is
  what lets every test in 3.1-3.6 build its tree under `tmp_path` — no
  fixture files under `openspec/contracts/**` (denied to wp-gate) are needed
  or permitted. Use `yaml.safe_load` exclusively, like every existing
  contract path.

- [x] 3.8 Write tests that the output makes no satisfaction claim `[S]`
  **Spec scenarios**: The Gate Makes No Claim That A Requirement Is Satisfied (output does not claim satisfaction)
  **Design decisions**: D5
  **Dependencies**: 3.7
  **Note**: assert the spec's canonical line — `<N> operations cite <M>
  requirements. This gate does not check that any requirement is satisfied.`
  — and that `implemented`/`satisfied`/`verified` are never applied to a
  requirement as subject. The line is pinned in the spec precisely so this
  test asserts the spec's phrase rather than freezing an invented literal.

- [x] 3.9 Write tests for concentration reporting `[S]`
  **Spec scenarios**: The Gate Reports Citation Concentration Deterministically (concentration appears in the output); (a run whose only finding is concentration exits zero)
  **Design decisions**: D7
  **Dependencies**: 3.7
  **Note**: the fixture is deterministic — e.g. six traced operations, four
  citing the same requirement, against `CONCENTRATION_REPORT_SHARE` — because
  D7 defines the reporting trigger as a named constant. Assert the entry
  appears at/above the trigger, the count and share are printed, AND the exit
  code is zero when concentration is the only finding. Without the defined
  trigger this test would assert the implementation against itself.

- [x] 3.10 Implement concentration reporting `[S]`
  **Design decisions**: D7
  **Dependencies**: 3.9
  **Note**: denominator is the capability's traced operations, never one
  document's — a per-document share is defeated by splitting the document
  (D10). The constant is documented as display-only: changing it can never
  change an exit code.

- [x] 3.11 Write tests for capability-scoped completeness `[S]`
  **Spec scenarios**: Completeness Is Evaluated Per Capability (a requirement served from another contract is covered); (a capability's contracts are evaluated as one surface); (a requirement cited by no document still fails)
  **Design decisions**: D9, D10
  **Dependencies**: 3.7
  **Note**: the discriminating fixture is a capability with TWO contracts where
  a requirement is cited from only one. A single-contract fixture passes under
  both the per-contract and per-capability rules and proves nothing.
  **Note**: the failing counterpart is required too — cited by neither,
  excluded by neither → fails naming the requirement exactly ONCE, not once
  per document. Without it, a gate that never fails reverse completeness
  passes every scenario here.

- [x] 3.12 Evaluate completeness per capability, unioning its contracts `[M]`
  **Design decisions**: D10
  **Dependencies**: 3.11
  **Note**: this is what makes splitting a capability's contract a staging
  mechanism for the FORWARD direction (see 5.2). Forward opt-in stays per
  document (D6); reverse stays per capability (D13); the union is the
  evaluation, not the switch.

- [x] 3.13 Write tests for cross-capability citations `[S]`
  **Spec scenarios**: Citations May Name Requirements In Another Capability (an operation cites another capability's requirement); (a cross-capability citation satisfies the cited capability's reverse completeness); (an unresolvable cross-capability citation fails)
  **Design decisions**: D9
  **Dependencies**: 3.12
  **Note**: assert it resolves, does NOT fail, DOES appear in the
  cross-capability report, and DOES credit the cited capability's reverse
  completeness — the worked example (coordinator serving
  `/gen-eval/scenarios`) depends on the credit. The unresolvable case must
  distinguish unknown-capability from unknown-requirement-in-known-capability.

- [x] 3.14 Resolve and report cross-capability citations `[S]`
  **Design decisions**: D9
  **Dependencies**: 3.13

- [x] 3.15 Write tests for change-scoped evaluation `[S]`
  **Spec scenarios**: Validation-Time Evaluation Is Scoped To The Change (a pre-existing gap does not fail a change that did not create it); (a requirement the change adds and nobody cites fails the change-scoped run); (opting a document in touches every operation in it); (opting a capability in touches every requirement of it); (an unresolvable merge base is an error, not an empty scope); (the output states which scope it evaluated)
  **Design decisions**: D12
  **Dependencies**: 3.12
  **Note**: must prove BOTH halves of the forward case — the touched
  violation fails, the untouched pre-existing one is reported and does not.
  A test asserting only the first passes against a gate with no scoping at
  all. Put the touched and untouched operations in the SAME file — scoping is
  node-level, and a file-level implementation passes a two-file fixture.
  **Note**: the reverse case is new debt too: the change adds a requirement
  (reverse-enforced capability), nothing cites it → change-scoped run fails.
  **Note**: change-scope tests `git init` a throwaway repo under `tmp_path`
  (via `--repo-root`/`--base-ref`) — a test diffing the real worktree's merge
  base is nondeterministic, changing as the package itself commits.
  **Note**: the unresolvable-merge-base and missing-change-id cases must exit
  non-zero — an empty scope that passes is a blocking gate that can only
  pass, the defect class this change exists for.
  **Note**: the output-wording test asserts the pinned scope line. A
  change-scoped run that printed "traceability complete" would be asserting
  something about the capability it did not check.
  **Note**: the opt-in TRANSITION cases are the subtle ones and were missed by
  every phase before plan review. Fixture 1: a document with no traceability
  block gains one on a single operation; a DIFFERENT, unmodified operation in
  that same document cites nothing — the change-scoped run must fail on it,
  because D6 makes the whole document strictly enforced the moment the block
  appears. Fixture 2: a capability gains `traceability-exclusions.yaml`; a
  pre-existing requirement nobody cites must fail the change-scoped run, even
  though no requirement node changed. Without these, `/validate-feature`
  greens on the exact change that flips the switch and `main` reds right
  after — the gate reporting success on the one diff that could still fix it
  cheaply.

- [x] 3.16 Implement change-scoped evaluation and the full sweep `[M]`
  **Spec scenarios**: The Full Sweep Blocks Opted-In Surfaces And Reports The Rest (the change flag selects which delta shadows the archive); (omitting the change flag unions every on-branch delta); (a merge group is not evaluated against changes outside the batch)
  **Design decisions**: D12
  **Dependencies**: 3.15
  **Note**: the unbatched-exclusion scenario is a RESOLUTION property, not a CI
  property, and belongs here as well as on 5.7. It holds because `--change <id>`
  resolves against `openspec/specs/` and `openspec/changes/<id>/specs/` and
  nothing else on the branch — assert that directly in `test_resolution_modes.py`
  with several other change dirs present in the tree. Wiring tests can only
  assert the argv the job builds; they cannot prove the tree does not leak.
  **Note**: one gate, a `--scope change|capability` argument. Change scope
  requires `--change <id>` (no inference across the ~34 live change dirs) and
  derives touched operations node-level from
  `git merge-base <integration-branch> HEAD` (branch parameterized, default
  `main`); capability scope reads everything. Unresolvable inputs are errors,
  never empty scopes. Reuse the `resolve_merge_base` shape from
  `project-context-refresh/scripts/checkpoint.py` rather than writing a third
  one. Do not build two scripts — they would drift, and the drift would be
  invisible because each is only run in one context.
  **Note**: `--change` is what selects RESOLUTION, and it is orthogonal to
  `--scope`. Supplied: the archive is shadowed by that one change's delta,
  other in-flight changes neither citable nor excludable. Omitted: the archive
  is shadowed by the union of every delta directly under
  `openspec/changes/<id>/`, EXCLUDING `openspec/changes/archive/` — those 128
  deltas are already merged into `openspec/specs/`, so re-applying them shadows
  the archive with itself, and a REMOVED or RENAMED section would resurrect or
  re-move a requirement. Assert the exclusion in `test_resolution_modes.py`
  against a fixture that has an `archive/` subtree; the repository's real
  `openspec/changes/archive/` is 128 deltas deep and makes a good smoke check
  but a poor unit fixture. Capability
  scope accepts BOTH forms — `--scope capability --change <id>` is exactly what
  task 5.7c runs on the merge candidate, and `--scope capability` bare is the
  post-merge job. Do NOT make the gate error on a missing `--change` at
  capability scope: absence is the post-merge job's signature, and an earlier
  draft of D12 failed the run it meant to permit for exactly this reason.
  Blocking-ness is a CI-job property; the gate never knows which job called it.
  **Note**: this adds a fifth test file, `test_resolution_modes.py`, covering
  the two modes and the `--scope capability --change <id>` combination. It is
  in this package's `write_allow`; add it there and to the pytest verification
  command rather than folding these cases into `test_capability_scope.py`,
  where the flag-orthogonality is the thing being asserted.

- [x] Checkpoint: run tests, review diff, verify scope

## Phase 4 — Retrofit the flagship example

Tasks 4.1, 4.2, and 4.2b are `[human]`: they decide which requirement each
flag serves, which is the judgement D1 says no agent may guess. Task 4.3 is
scripted verification of the human-authored artifacts.

- [x] 4.1 `[human]` Add flag-level requirements to the gen-eval spec `[M]`
  **Design decisions**: D1
  **Dependencies**: 3.7
  **Note**: the spec names three flags today, none of them among the 17 in the
  contract. Each contracted flag needs a requirement or an exclusion. A flag
  that justifies neither is a finding about the flag, not about this task —
  record it, do not delete the flag here.

- [x] 4.2 `[human]` Add citations to `openspec/contracts/gen-eval-framework/cli/gen-eval.yaml` `[S]`
  **Design decisions**: D1, D6
  **Dependencies**: 4.1, 2.0
  **Note**: opting this contract document in commits all 17 flags (D6).
  Regenerate the derived descriptor afterwards —
  `generate_tool_descriptor.py --check` runs in CI and will fail on the
  un-regenerated artifact.

- [x] 4.2b `[human]` Author `openspec/contracts/gen-eval-framework/traceability-exclusions.yaml` `[M]`
  **Design decisions**: D13, D4
  **Dependencies**: 4.2
  **Note**: this is the flagship's REVERSE opt-in, and it is the larger half
  of the retrofit: every gen-eval-framework requirement — the ~20 archived,
  plus the ones this change and 4.1 add — must end up cited by some operation
  or excluded here with a written reason. "Served by the framework API, no
  CLI surface" is a real reason and recording it is the point. Creating this
  file flips reverse enforcement for the capability (D13), so it lands last
  in the phase, when the requirement set is already triaged.

- [ ] 4.3 Demonstrate the gate fails on gen-eval's own contract `[S]`
  **Spec scenarios**: Traceability Completeness Is Enforced In Both Directions (an uncited operation fails the gate)
  **Design decisions**: D3
  **Dependencies**: 4.2b
  **Note**: RED protocol, twice, on the real artifacts, not fixtures: (a)
  remove one citation from the real contract → gate exits non-zero naming
  that flag → restore; (b) remove one exclusion from the real exclusions file
  → gate exits non-zero naming that requirement → restore. The equivalent
  step in `derive-descriptors-from-contracts` task 4.7 is what exposed that
  its predecessor was verifying a mirror.
  **Note**: confirm the failing run reads the mutated YAML and not a stale
  derived artifact — the descriptor regenerated in 4.2 is the staleness
  hazard here, not Python bytecode.

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 5 — The coordinator contract, matrix generation, and CI

Tasks 5.1, 5.2, 5.3, and 5.7c are `[human]` — authoring the coordinator
contract is one decision per operation, and 5.7c's acceptance run may demand
triage of the same kind. Tasks 5.4-5.9 are engineering (wp-matrix and
wp-wiring) **with the single exception of 5.7c**, which sits inside that
numeric range but is owned by no package; 5.6 and 5.7 additionally require the
human-authored artifacts from 4.2/4.2b (and 5.2 for the sweep demonstration) to
be meaningful.

- [ ] 5.1 `[human]` Author `openspec/contracts/agent-coordinator/openapi/v1.yaml` from the spec `[M]`
  **Design decisions**: D1, D6
  **Dependencies**: 3.7
  **Note**: **authored from `openspec/specs/agent-coordinator/spec.md`, NOT
  generated from the application.** `app.openapi()` produces the app
  describing itself; verifying the app against that compares it to a copy of
  itself and reports zero violations forever. Measured 2026-07-26: the app
  serves 82 operations, requirements name 35 of them.
  **Note**: lands `untraced` (D6). Scoping which documents opt in is 5.2.

- [ ] 5.2 `[human]` Split the coordinator contract and opt one document in `[M]`
  **Spec scenarios**: Forward Enforcement Is Opt-In Per Contract Document (declaring traceability commits the whole contract document); Completeness Is Evaluated Per Capability (a capability's contracts are evaluated as one surface)
  **Design decisions**: D6, D10, D13
  **Dependencies**: 5.1, 3.12
  **Note**: D6's unit is the contract DOCUMENT, so splitting
  `openspec/contracts/agent-coordinator/openapi/` into `locks.yaml`,
  `work-queue.yaml` and so on stages the forward direction: each document
  opts in when its subsystem is ready, and D10's capability-level union means
  the split costs nothing in forward rigour.
  **Note**: FORWARD ONLY. Do not create the coordinator's
  `traceability-exclusions.yaml` here — reverse opt-in means triaging all 122
  coordinator requirements (D13), which is the backlog this change creates
  (5.3), not work it performs.
  **Note**: start with locks or work-queue — small, and the operations the spec
  names most concretely. Proves the model on real requirements before anyone
  commits to all 82.

- [ ] 5.3 `[human]` Record the unattributed operations as findings, not fixes `[S]`
  **Dependencies**: 5.1
  **Note**: the ~47 operations no requirement names are out of scope by
  construction (see proposal Scope), as is the coordinator's reverse opt-in.
  File them; do not spec them here. Deciding what each one is for is mostly
  not gen-eval's call.

- [x] 5.4 Write tests for the generated Contract Ref column `[S]`
  **Design decisions**: D8
  **Dependencies**: 3.7
  **Note**: must fail on the current hand-filled matrix, which is the point —
  the column has never been checked against anything.

- [x] 5.5 Generate `change-context.md`'s Contract Ref column from citations `[M]`
  **Design decisions**: D8
  **Dependencies**: 5.4
  **Note**: join matrix rows to citations by parse position of the same spec
  parse (D8) — never by name similarity. The ordinal Req ID format is NOT
  changed by this task.
  **Note**: update `skills/implement-feature/SKILL.md` in the same commit. It
  currently instructs the implementer to fill the column by hand; leaving that
  text in place while generating the column is how the two disagree.
  **Note**: SKILL.md is not the only copy. The `change-context.md` TEMPLATE
  carries the same instruction in its comment block ("Phase 1: Fill Req ID,
  Spec Source, Description, Contract Ref, ...") — and the template is what an
  author actually reads while filling the matrix in. Edit BOTH source copies:
  `openspec/schemas/feature-workflow/templates/change-context.md` and
  `skills/plan-feature/install_assets/openspec/schemas/feature-workflow/templates/change-context.md`.
  Do NOT edit the `.agents/` or `.claude/` copies — `install.sh` regenerates
  them from `skills/`. The skill-workflow delta's "Contract Ref SHALL NOT be
  populated by hand" has no owner other than this task; wp-matrix carries a
  verification step that fails while either template still says to hand-fill it.

- [ ] 5.6 Wire the change-scoped gate into `/validate-feature` `[M]`
  **Spec scenarios**: Validation-Time Evaluation Is Scoped To The Change (a pre-existing gap does not fail a change that did not create it); skill-workflow delta: Validation-Time Requirement Traceability Gate (all four scenarios)
  **Design decisions**: D12
  **Dependencies**: 3.16, 4.2
  **Note**: this is the blocking gate — work is not validated until the
  operations it touched cite their requirements. Runs at `--scope change
  --change <id>`.
  **Note**: `skills/validate-feature/SKILL.md` is the wiring point, and its
  spec-compliance step is the natural neighbour. Adding a gate to a skill means
  adding it to the skill's own tests too (the skill-workflow delta requires
  this), or the wiring is unverified.
  **Note**: run it BARE, never piped. A pipeline's `$?` is the last stage's
  status, so `check_traceability.py | tail` reports tail's 0 on a failing gate.
  **Note**: gate the invocation on detection and print an explicit SKIP when
  `packages/gen-eval/scripts/check_traceability.py` or `openspec/contracts/` is
  absent. `skills/validate-feature/` ships via `install.sh` into consumer repos
  that have neither, where an unconditional invocation fails every validation
  downstream. The skill's existing gen-eval phase already does detect-then-
  print-SKIP — copy that shape. Test the SKIP path, not just the run path: an
  unprinted skip and a passing gate are indistinguishable in a log.

- [ ] 5.7 Wire the full-capability sweep into CI `[S]`
  **Spec scenarios**: The Full Sweep Blocks Opted-In Surfaces And Reports The Rest (an opted-in surface fails the sweep); (a surface that has not opted in is reported, not failed); (a pull request that was not planned through OpenSpec skips); (a pull request touching two change directories fails as ambiguous); (an unresolvable base fails rather than skipping); (a merge group batching two changes is evaluated once per change); (a merge group is not evaluated against changes outside the batch); (an archive pull request derives no change id); (the run on the integration branch cannot fail); (the job is not guarded off any declared event)
  **Design decisions**: D12
  **Dependencies**: 3.16, 5.2
  **Note**: the three event paths differ in more than blocking-ness — they
  differ in what requirement identifiers resolve to. `pull_request` and
  `merge_group` both pass `--change <id>` (merge_group once per batched
  change); only `push`-on-`main` omits it and gets the union of every on-branch
  delta. **Every blocking invocation supplies `--change`; union mode is used by
  exactly one run, the non-blocking one.** That is the invariant, not a
  coincidence: union admits requirements from changes whose implementation has
  not landed, so nothing that blocks can afford it. The gate must still not
  INFER blocking from the flag and must not error on a missing `--change` —
  that was an earlier draft's mistake and it rejected the one run entitled to
  omit it (D12). Both modes are 3.16's work, already built by the time this
  task wires them.
  **Note**: derive the change id from the DIFF, not the branch name. `ci.yml`
  triggers on unfiltered `pull_request:` and `merge_group:` (lines 3-7), and
  live branch prefixes include `dependabot/`, `chore/`, `claude/`, and
  `codex/`; `OPENSPEC_BRANCH_OVERRIDE` produces `claude/op-XXXX` for real
  OpenSpec work, and parallel agents produce `openspec/<id>--<agent-id>`. No
  branch-name rule survives all four. The directory under `openspec/changes/`
  that the diff touches is the robust signal.
  **Note**: zero touched change directories is a SKIP, not a failure — print
  it naming the branch and exit zero. Work that did not go through OpenSpec
  planning was never expected to produce a spec delta, a citation, or an
  exclusions file, and failing a dependency bump for not authoring an artifact
  nobody asked it for would red every such PR the day this lands. Two touched
  directories is a real ambiguity **on `pull_request`**: fail naming both, do
  not choose. On `merge_group` it is the ordinary case — see the event table
  below; the ambiguity rule must not fire there.
  **Note**: NAME the base the diff is taken against, and make an unresolvable
  base an ERROR, never the SKIP. `pull_request` carries
  `github.event.pull_request.base.sha`; `merge_group` does not — it carries
  `github.event.merge_group.base_sha`, and `ci.yml:7` triggers on it
  unfiltered. A derivation written only against the PR payload reads empty in
  the merge queue, the diff comes back empty, zero change directories are
  touched, and the blocking sweep skips silently at the one moment it is the
  last check standing. Two opposite conditions must not share an exit path.
  **Note**: assert BOTH paths in the wiring tests — the SKIP on a genuinely
  non-OpenSpec diff, and the FAILURE on an unresolvable base. A job that skips
  silently and a job that passes are the same green check, which is the
  unfalsifiable-green artifact this change exists to eliminate.
  **Note**: the tests go in `skills/tests/validate-feature/test_ci_sweep_wiring.py`,
  extracting the job's bash fragment from `ci.yml` and driving it — the pattern
  `skills/tests/validate-feature/test_gen_eval_mode_selection.py` already uses.
  Without a named file and a verification step that fails when it is missing,
  these two scenarios are the only ones in the change with no mechanism that
  notices they were never written.
  **Note**: ONE job, three events, selected on `github.event_name`. Do NOT add
  an `if:` that excludes any declared trigger. `ci.yml` fires on `push: [main]`,
  `pull_request`, and `merge_group`, and `grep -n 'if:' .github/workflows/ci.yml`
  currently returns exactly one hit (`if: failure()`) — no job in this workflow
  is event-guarded, so an unguarded job runs on all three whether or not the
  plan anticipated it. The three behaviours:
    - DERIVATION, shared by both blocking events. Three conditions, ALL
      required — the exact command, verified against real commits:

          git diff --no-renames --diff-filter=d --name-only <base> HEAD \
            -- openspec/changes/ \
            | sed 's#^openspec/changes/\([^/]*\)/.*#\1#' | sort -u \
            | grep -v '^archive$'

      `--no-renames` so the set does not depend on git's similarity heuristic;
      `--diff-filter=d` (lowercase — EXCLUDE deletions) so the source half of
      an archive `git mv` does not name the change being archived;
      `grep -v archive` so the destination half does not name the literal id
      `archive`. Dropping any one of the three breaks a real case.
      **The deletion filter is the one whose absence is invisible**, and an
      earlier draft of this task omitted it while claiming the archive
      exclusion alone produced a SKIP. It does not: with `--no-renames` the
      `git mv` decomposes into deletions at `openspec/changes/<id>/` plus
      additions at `openspec/changes/archive/<date>-<id>/`, so excluding
      `archive` suppresses only the additions. Measured on three real archive
      commits with the archive exclusion but no deletion filter:
        `247bc201` → `{derive-descriptors-from-contracts}` — one id, so no
                     ambiguity and no SKIP; the BLOCKING gate then runs
                     `--change` against a directory with zero files at that
                     commit (`git ls-tree -r 247bc201 <that dir>` → 0).
        `600744a5` → two ids → ambiguity rule → every archive PR hard-reds.
        `a17e33f7` → one id, same silent-degradation path as the first.
      With `--diff-filter=d` all three derive `{}` → SKIP, a normal openspec
      commit still derives its own id, and a base predating an archive commit
      derives only the PR's own id instead of tripping ambiguity.
    - `pull_request` → base `github.event.pull_request.base.sha`, derive the
      change id from the diff, invoke `--change <id>`, BLOCKING. Zero touched
      change directories → SKIP; two → fail as ambiguous.
    - `merge_group` → base `github.event.merge_group.base_sha`, derive the SET
      of touched change directories and invoke the gate once per id with
      `--change <id>`, BLOCKING if any invocation fails. Do NOT apply the
      ambiguity rule here: a merge group's diff spans every batched PR, so
      several change directories is the ordinary case. Zero touched → SKIP.
      Do NOT use union mode here. The set of change dirs in the DIFF is the
      batch; the set in the TREE is not — a merge-queue branch is main plus the
      batched PRs, so it carries all 33 unarchived change dirs main already
      had (`git ls-tree --name-only origin/main openspec/changes/` → 34
      entries). Three of them add 11 gen-eval-framework requirements with no
      landed implementation; with 4.2b's exclusions file flipping reverse
      enforcement on, a blocking union run fails on those 11 and the batch's
      authors cannot fix it — citing them is not their work, and excluding them
      fails the `other-changes-are-invisible` rule. Blocking scope comes from
      the diff, never from the tree.
    - `push` to `main` → no base needed, `--change` omitted, NON-blocking; its
      exit status must not depend on what it found.
  **Note**: the two wrong implementations, both of which the earlier wording
  invited. `if: github.event_name == 'pull_request'` makes the merge_group base
  derivation unreachable code and leaves the queue ungated at the one moment
  the check is last standing. No guard at all runs the blocking path on
  push-to-`main`, where neither base exists and the unresolvable-base rule then
  reds `main` on every push. The event set is normative in the spec delta for
  exactly this reason.
  **Note**: an earlier draft put the blocking sweep on `push` to `main`,
  reasoning that cron cannot block a merge — true, but a push event on `main`
  fires *after* the merge lands and shares the defect. It can red `main`; it
  cannot stop `main` going red. Only a check on the merge candidate blocks it.
  **Note**: opted-in surfaces block; the rest report. There is NO separate
  blocking flag — opting in is the switch (D6 forward, D13 reverse), and
  adding one would create an opted-in-but-not-blocking state, the
  half-traced-yet-green outcome D6 exists to make impossible.
  **Note**: the job needs `fetch-depth: 0` if it ever computes a merge base —
  and even for capability scope, keep the invocation bare, as with
  `generate_tool_descriptor.py --check`. A gate whose two call sites disagree
  on argv reports failure on a correct tree.
  **Note**: this is what makes the coordinator's existing gaps visible without
  stopping unrelated work; diff-scoping alone would leave them invisible
  forever, since no change touches them.

- [x] 5.7b Register `tests/validate-feature` in `skills/pyproject.toml` `[XS]`
  **Spec scenarios**: skill-workflow delta: Validation-Time Requirement Traceability Gate (skill wiring is covered by skill tests)
  **Dependencies**: 5.6
  **Note**: `testpaths` in `skills/pyproject.toml` currently lists
  `tests/implement-feature` and `tests/plan-feature` but NOT
  `tests/validate-feature`, and CI's `test-infra-skills` job runs a bare
  `uv run pytest` from `skills/`, which honours `testpaths`. The existing
  `skills/tests/validate-feature/test_gen_eval_mode_selection.py` is already
  invisible for this reason. Without this line the skill-workflow scenario
  would be satisfied by a suite CI never executes — a test that never runs
  fails exactly the way a gate that cannot fail does.
  **Note**: verify by deleting the entry and confirming the new tests vanish
  from the collected set, not merely that they pass with it present.
  **DONE AHEAD OF 5.6** — the registration is independent of the new tests and
  was landed early, so it is not a reason to defer wp-wiring. Verified as the
  note requires, bare from `skills/`: `pytest --collect-only -q | grep -c
  '^tests/validate-feature/'` → **5** with the entry, **0** with it deleted, **5**
  after restore. Full bare suite: **2350 passed** (adding the path co-collects
  cleanly — no flat-module shadowing against the already-listed dirs).
  **5.6 STILL OWES ITS HALF**: this closed the directory, not the file. When
  `test_ci_sweep_wiring.py` is written it must land *under* `skills/tests/
  validate-feature/` to inherit this entry, and the delete-verification must be
  re-run so it covers the new file. A `[x]` here is not evidence the sweep tests
  are collected.
  **Scope finding, out of scope here**: `tests/validate-feature` was not an
  isolated omission. 25 of the dirs under `skills/tests/` are unlisted, hiding
  102 files / ~1161 tests, of which 23 currently FAIL (`tests/autopilot` 7,
  `tests/playwright-validator` 6, `tests/phase-record-compaction` 5,
  `tests/docs` 3, `tests/agent-coordinator` 2). Collecting all 25 at once also
  raises 13 collection errors from flat-module shadowing (several skills ship a
  top-level `scripts/models.py`), so they cannot simply be appended. Filed
  separately; deliberately NOT fixed here.

- [ ] 5.7c `[human]` The unmutated tree passes at capability scope `[M]`
  **Spec scenarios**: The Full Sweep Blocks Opted-In Surfaces And Reports The Rest (both scenarios)
  **Design decisions**: D12, D13
  **Dependencies**: 4.2b, 5.2, 5.7
  **Note**: this is the GREEN half of 4.3's RED demonstration, and it is the
  acceptance criterion the change otherwise lacks. Task 4.3 proves the gate
  goes red on two documented mutations; nothing yet requires it to go GREEN on
  the merge candidate. Run `check_traceability.py --scope capability --change
  trace-requirements-to-contracts` across every capability on the merge commit
  and record the exit code. It MUST be zero — this change flips
  gen-eval-framework into blocking reverse enforcement (4.2b) and installs the
  blocking sweep (5.7) in the same PR, so a non-zero result here means merging
  reds `main` immediately.
  **Note**: pass `--change` explicitly. The requirements 4.1 adds exist only in
  this change's spec delta, and 4.2's citations name them; an archive-only run
  reports every one as unresolved. That is the blocking run's resolution rule
  (D12), and this task is where it is first exercised on real artifacts.
  **Note**: this invocation IS the one that gates the merge, on both blocking
  events — `pull_request` derives this same `--change <id>`, and `merge_group`
  runs it once per batched change. That equivalence is what makes this a real
  acceptance criterion, and it is worth stating because it was briefly untrue:
  an earlier draft had `merge_group` block with `--change` OMITTED (union
  mode), so 5.7c exercised an invocation no blocking event actually ran, and
  nothing in the plan could have detected that the union-blocking run was
  unsatisfiable. If a future edit reintroduces a blocking invocation this task
  does not run, this task stops being an acceptance criterion — check that
  first, before trusting its exit code.
  **Note**: also run the post-merge invocation once, bare `--scope capability`
  with no `--change`, and record its output WITHOUT gating on it. It must not
  be made to pass — it unions every in-flight change on the branch and will
  report other changes' uncited requirements, which is exactly why that run is
  non-blocking. Recording it here proves the two modes were distinguished on
  real artifacts rather than assumed to differ.
  **Note**: expect `code-search/v2.yaml` in the REPORT, not the failures — it
  is a pre-existing root-misplaced instance, and the rule reports the existing
  while failing only newly added ones. If it appears as a failure, discovery
  was implemented as a cliff and 3.6's assertion (a) does not hold.
  **Note**: `[human]` because passing it may require triage decisions (which
  requirements are cited, which are excused and why), which D1 forbids
  delegating. Scale: gen-eval-framework carries 20 archived requirements plus
  this change's 14, and every one needs a citation or a written exclusion.
  If that triage proves larger than 4.2b's budget, the correct response is to
  defer the reverse opt-in to a follow-up change — NOT to weaken the gate or
  to write exclusions whose reason is a placeholder.

- [ ] 5.8 Update `packages/gen-eval/README.md` with the four-edge chain `[S]`
  **Dependencies**: 5.6, 5.7
  **Note**: the README documents contract → descriptor → verify. State the edge
  above it, and state plainly what the gate does NOT claim (D5) — a reader who
  takes "traceability gate: pass" for "requirements are implemented" has been
  misled by the documentation, not by the gate.

- [ ] 5.9 Refresh `DOWNSTREAM.md` for consumers with their own contracts `[S]`
  **Dependencies**: 5.6, 5.7
  **Note**: ACA's tool contract is affected only if they opt in (D6/D13). Say
  so explicitly — the previous notice's DS-2 had to be rewritten at
  implementation time because it promised a change that did not ship.

- [ ] Final checkpoint: full suite green, `openspec validate --strict` passes,
  and both wired gates demonstrated per the RED protocol — the change-scoped
  gate (5.6) and the full sweep (5.7) each exit non-zero against their
  documented mutation and exit zero after restore, with commands and exit
  codes recorded here
