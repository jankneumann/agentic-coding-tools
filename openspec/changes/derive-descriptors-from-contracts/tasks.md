# Tasks — Derive gen-eval descriptors from contracts

Test tasks precede the implementation they verify (RED before GREEN).
Sizes: XS ≤30min · S 30min–2hr · M 2hr–1day. No L or XL tasks.

Most work is in `packages/gen-eval/`; task 1.8 touches
`openspec/contracts/README.md`.

**Prerequisite (satisfied).** PR #277 (UP-1..UP-5) merged to `main` on
2026-07-25 as `c2213c5f` + `e5fabe3d`. This change builds on top of it and
**must not revert or amend those commits**. The artifacts this plan depends on
all arrived with that merge:

| Artifact | Depended on by |
|---|---|
| `packages/gen-eval/scripts/generate_contract_schemas.py` | task 1.6 (mirrors its `--check` shape), D2 |
| `packages/gen-eval/evaluation/descriptor.yaml` | task 5.3 (migration target), D8 |
| `make dogfood` CI gate | tasks 5.3, 5.4, D8 |

Verify before starting Phase 1: both files exist on the branch's merge base.
If they do not, this branch has not been rebased onto the merged `main` and
Phase 1 will build against a missing substrate.

## Phase 0 — Free the archetype names (D9)

The two headline deliverables are named `ServiceDescriptor` and `ToolDescriptor`,
and **both names are already taken** in `packages/gen-eval/src/gen_eval/descriptor.py`
with unrelated meanings (`:41` one MCP tool, `:67` one testable service). This
phase renames the existing models to the `*Spec` level before anything defines
the archetypes. It is mechanical and changes no behaviour.

- [ ] 0.1 Write tests pinning the deprecation aliases and the new public API `[S]`
  **Spec scenarios**: Descriptor Model Naming Levels (both scenarios)
  **Design decisions**: D9
  **Dependencies**: None
  **Note**: only `EndpointDescriptor` and `CommandDescriptor` can be aliases —
  assert they import and emit `DeprecationWarning`. `ToolDescriptor` and
  `ServiceDescriptor` are HARD BREAKS: the new archetypes reuse those names, so
  a symbol cannot resolve to both the legacy element type and the new document
  type. Assert those two no longer carry the legacy element fields
  (`input_schema` / `endpoints`). Also assert `test_public_api_parity.py`
  reflects the new `__all__`.

- [ ] 0.2 Rename the four element/container models; add aliases for the two non-reused names `[M]`
  **Design decisions**: D9
  **Dependencies**: 0.1
  **Note**: `EndpointDescriptor`→`EndpointSpec`, `ToolDescriptor`→`McpToolSpec`,
  `CommandDescriptor`→`CommandSpec`, `ServiceDescriptor`→`ServiceSpec`.
  ~22 references in `src/`, ~90 in `tests/`. `InterfaceDescriptor` is unchanged.

- [ ] 0.3 Bump `CONTRACT_VERSION` 1 → 2 and regenerate the published schema `[S]`
  **Spec scenarios**: Descriptor Model Naming Levels (renaming a published type bumps the contract version)
  **Design decisions**: D9, D6
  **Dependencies**: 0.2
  **Note**: `$defs` titles in `src/gen_eval/contracts/interface-descriptor.schema.json`
  change, so `scripts/generate_contract_schemas.py --check` must be re-run and
  `tests/test_contract_schemas.py` must pass against the regenerated copy

- [ ] 0.4 Migrate the 11 existing test files off the deprecated names `[S]`
  **Design decisions**: D9
  **Dependencies**: 0.2
  **Note**: `conftest.py`, `test_descriptor.py`, `test_cli_generator.py`,
  `test_cli_transport_stderr.py`, `test_feedback.py`, `test_generator.py`,
  `test_hybrid_generator.py`, `test_integration_orchestrator.py`,
  `test_integration_scenarios.py`, `test_optional_startup.py`,
  `test_sdk_generator.py`.
  **Note**: these PASS untouched because the aliases work — that is exactly the
  trap. Landing the rename without this leaves 11 files on deprecated names on
  day one, and any suite escalating `DeprecationWarning` to an error breaks.
  Verify with `pytest -W error::DeprecationWarning` after migrating.

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 1 — Tool contract + tool descriptor (gen-eval self-migration)

- [ ] 1.1 Write tests for CLI contract schema validation — required fields, exit codes, flag types `[S]`
  **Spec scenarios**: Descriptor Derivation Drift Guard (a tool contract declaring commands but no coverage units fails)
  **Contracts**: `contracts/cli-contract.schema.json`
  **Design decisions**: D5 (tool contracts are a separate schema)
  **Dependencies**: None

- [ ] 1.2 Create `contracts/cli-contract.schema.json` — commands, flags, argument types, exit codes `[S]`
  **Design decisions**: D5
  **Dependencies**: 1.1

- [ ] 1.3 Write tests for tool-descriptor derivation from a CLI contract `[M]`
  **Spec scenarios**: Contract As Descriptor Source Of Truth (descriptor derives from a contract); Operation And Surface Coverage Model (flag-only tool surfaces are nameable)
  **Design decisions**: D1, D5
  **Dependencies**: 1.2

- [ ] 1.4 Implement the `ToolDescriptor` model with contract-reference loading `[M]`
  **Design decisions**: D1, D5, D6
  **Dependencies**: 1.3

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 1.5 Write tests for the drift guard's fail-closed assertions `[M]`
  **Spec scenarios**: Descriptor Derivation Drift Guard (all four scenarios — drift fails; empty fails; count mismatch fails; commands-but-no-coverage-units fails)
  **Design decisions**: D2, D3
  **Dependencies**: 1.4
  **Note**: each assertion must be proven to FAIL on a deliberately broken fixture, not merely pass on a good one. Fixtures: `empty`, `count_mismatch`, `drifted`, and `one_command_zero_flags` — the last is the case that passed all three original assertions while deriving an empty surface, and is why D3 counts coverage units rather than commands.
  **Note**: the guard counts the archetype's own unit — operations for a service descriptor, flags + positionals + named subcommands for a tool descriptor.

- [ ] 1.6 Implement `scripts/generate_tool_descriptor.py` with `--check` mode `[M]`
  **Design decisions**: D2, D3
  **Dependencies**: 1.5
  **Note**: mirror `scripts/generate_contract_schemas.py` from PR #277

- [ ] 1.7 Author gen-eval's own CLI contract under `openspec/contracts/gen-eval-framework/cli/` `[S]`
  **Spec scenarios**: Dogfood (gen-eval evaluates its own CLI surface)
  **Design decisions**: D8
  **Dependencies**: 1.2

- [ ] 1.8 Document the `<capability>/cli/` sub-path in `openspec/contracts/README.md` `[XS]`
  **Design decisions**: D1, D5
  **Dependencies**: 1.7
  **Note**: the README currently documents only `<capability>/schemas/*.schema.json`
  and `<capability>/openapi/*.yaml`. D1 and task 1.7 introduce a third sibling,
  `<capability>/cli/*.yaml`, for tool contract *instances*. Without this task the
  new sub-path ships as undocumented convention, which is the same drift the
  contracts directory was created to prevent. Also add the `gen-eval-framework`
  row to the "Current contents" table.

- [ ] 1.9 Promote `cli-contract.schema.json` to `openspec/contracts/gen-eval-framework/schemas/` `[XS]`
  **Design decisions**: D5
  **Dependencies**: 1.2
  **Note**: promotion happens while the change is in flight, NOT on archival —
  `openspec/contracts/README.md` requires it ("so no window of drift opens") and
  the schema's `$id` already points at the promoted path. Without this the `$id`
  URL 404s and DOWNSTREAM DS-3 points consumers at a path that moves on archive.
  The schema goes to `schemas/`; the contract *instance* from task 1.7 goes to
  `cli/`.

- [ ] 1.10 Author an OpenAPI service-contract fixture for Phase 2 `[S]`
  **Spec scenarios**: Contract As Descriptor Source Of Truth (descriptor derives from a contract)
  **Design decisions**: D1, D7
  **Dependencies**: None
  **Note**: must exercise the `x-gen-eval-surface` binding extension (D4) —
  two operations declaring the same `mcp.element`, and at least one operation
  with a surface marked `exposed: false`.
  **Note**: task 2.1 declares `contracts/openapi/v1.yaml` as its fixture, but no
  task authored it and `wp-service-descriptor` is not scoped to write under
  `openspec/changes/**/contracts/`. It must include a **many-to-one** case (two
  operations binding to one MCP element) so task 2.3 and task 4.5 have a fixture
  for D4/D7's third carve-out.

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 2 — Service descriptor derivation

- [ ] 2.1 Write tests for OpenAPI operation extraction — paths, methods, operationIds `[M]`
  **Spec scenarios**: Contract As Descriptor Source Of Truth (descriptor derives from a contract); Contract As Descriptor Source Of Truth (unreachable implementation does not shrink the declared surface)
  **Contracts**: `contracts/openapi/v1.yaml` (fixture, authored by task 1.10)
  **Design decisions**: D1
  **Dependencies**: 1.10
  **Note**: include the fail-closed case — load a descriptor whose implementation
  is absent/unreachable and assert the declared surface is byte-identical to the
  contract-derived one. This is the assertion that distinguishes the selected
  approach from rejected Approach 2; without it D1 is an unverified claim.

- [ ] 2.2 Implement the `ServiceDescriptor` model with OpenAPI-backed operations `[M]`
  **Design decisions**: D1, D6
  **Dependencies**: 2.1

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 2.3 Write tests for the MCP projection carve-outs — resources excluded, descriptions preserved, many-to-one honoured `[M]`
  **Spec scenarios**: Operation And Surface Coverage Model (a surface that does not expose an operation is not a gap); Operation And Surface Coverage Model (one surface element serving two operations is covered once)
  **Design decisions**: D4, D7
  **Dependencies**: 2.2, 1.10
  **Note**: the many-to-one case must assert that an explicit `element` binding
  SUPPRESSES name derivation — two operations bound to one tool derive one tool,
  not two.

- [ ] 2.4 Implement the OpenAPI-to-MCP tool projection with binding support `[M]`
  **Design decisions**: D4, D7
  **Dependencies**: 2.3
  **Note**: flatten path/query/body into one input object; copy `summary`/`description` verbatim (agent-readable, load-bearing). Derivation is the DEFAULT — an explicit `element` binding wins and emits the bound name once, recording the fan-in.

- [ ] 2.5 Implement `scripts/generate_service_descriptor.py` with `--check` mode `[M]`
  **Spec scenarios**: Descriptor Derivation Drift Guard (drift fails)
  **Design decisions**: D2, D3
  **Dependencies**: 2.4

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 3 — Operation × surface coverage model

- [ ] 3.1 Write tests for operation-keyed coverage — exposure separate from coverage `[M]`
  **Spec scenarios**: Operation And Surface Coverage Model (one operation tested via one surface is not three gaps; a surface that does not expose an operation is not a gap)
  **Design decisions**: D4
  **Dependencies**: 2.2

- [ ] 3.2 Implement the operation-keyed coverage structures in the report model `[M]`
  **Design decisions**: D4
  **Dependencies**: 3.1

- [ ] 3.3 Write tests for legacy flat-field back-compatibility `[S]`
  **Spec scenarios**: Operation And Surface Coverage Model (report continues to emit the flat interface list)
  **Design decisions**: D4, D6
  **Dependencies**: 3.2
  **Note**: cover `per_interface` as well as `unevaluated_interfaces` —
  `per_interface` is built at `orchestrator.py:382-388` from `interfaces_tested`,
  and DOWNSTREAM.md tells ACA to assert on it.

- [ ] 3.4 Compute the legacy flat `unevaluated_interfaces` and `per_interface` from the operation model `[S]`
  **Design decisions**: D6
  **Dependencies**: 3.3

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 3.5 Write tests for tested-identifier extraction from `args`-only CLI steps `[M]`
  **Spec scenarios**: Operation And Surface Coverage Model (a flag exercised by a scenario is recorded as covered)
  **Design decisions**: D10
  **Dependencies**: 3.2, 1.4
  **Note**: `_extract_interfaces` (`evaluator.py:530`) requires `step.command` to
  be truthy for CLI steps. gen-eval's 8 dogfood steps use `args: [...]` with no
  `command`, so it yields `[]`. Test against those real scenarios, not a synthetic
  step — the whole defect is that the real ones produce nothing.

- [ ] 3.6 Extend `_extract_interfaces` to emit flag-level and operation-level identifiers `[M]`
  **Design decisions**: D10, D4
  **Dependencies**: 3.5
  **Note**: tested identifiers must share a vocabulary with the derived declared
  surface, else coverage is string-matching two disjoint sets and reports 0%.
  For the tool archetype emit contracted flags seen in `args`; for the service
  archetype emit operation ids via the element binding.

- [ ] 3.7 Write tests for a coverage threshold that fails independently of pass-rate `[S]`
  **Spec scenarios**: Operation And Surface Coverage Model (coverage below the threshold fails the run)
  **Design decisions**: D10
  **Dependencies**: 3.6

- [ ] 3.8 Add a `--min-coverage` gate to the CLI `[S]`
  **Design decisions**: D10
  **Dependencies**: 3.7
  **Note**: `__main__.py:399` exits on `report.pass_rate` only, and `make dogfood`
  passes `--fail-threshold 1.0` which is pass-rate. Without this the spec's 80%
  coverage floor has no enforcement mechanism at all.

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 4 — Implemented-surface subset verifiers

- [ ] 4.1 Write tests for the argparse subset verifier — undocumented flag detected `[M]`
  **Spec scenarios**: Implemented Surface Subset Verification (undocumented CLI flag is reported; verification distinguishes excess from omission)
  **Design decisions**: D1
  **Dependencies**: 1.4

- [ ] 4.2 Implement the argparse subset verifier `[M]`
  **Design decisions**: D1
  **Dependencies**: 4.1

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 4.3 Write tests for the FastAPI subset verifier — undocumented route detected `[M]`
  **Spec scenarios**: Implemented Surface Subset Verification (undocumented endpoint is reported)
  **Design decisions**: D1
  **Dependencies**: 2.2

- [ ] 4.4 Implement the FastAPI subset verifier over `app.openapi()` `[M]`
  **Design decisions**: D1
  **Dependencies**: 4.3

- [ ] 4.5 Write tests for the MCP subset verifier — undocumented tool detected, many-to-one not a false positive `[M]`
  **Spec scenarios**: Implemented Surface Subset Verification (verification distinguishes excess from omission); Operation And Surface Coverage Model (one surface element serving two operations is covered once)
  **Design decisions**: D1, D4, D7
  **Dependencies**: 2.4
  **Note**: the many-to-one fixture models the real case — `check_locks` serves
  both `list_active_locks` and `get_lock_status` by branching on `file_paths`
  being None (`agent-coordinator/src/coordination_mcp.py:165`). A 1:1 projection
  reports THREE false findings here: `check_locks` as undocumented excess, plus
  two invented tools as omissions. Assert zero violations.

- [ ] 4.6 Implement the MCP subset verifier over the server tool listing `[M]`
  **Design decisions**: D1, D4, D7
  **Dependencies**: 4.5
  **Note**: compare against the set of BOUND elements, not against derived
  one-per-operation names.

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 4.7 Wire the argparse subset verifier into CI against gen-eval's own parser `[S]`
  **Spec scenarios**: Implemented Surface Subset Verification (undocumented CLI flag is reported)
  **Design decisions**: D1, D3
  **Dependencies**: 4.2, 1.7
  **Note**: without this, excess detection ships with no gate that ever runs
  against a real surface. The drift guards only prove generator-vs-contract
  consistency — they cannot detect a contract that has rotted to a SUBSET of
  reality (truncate the contract from 12 flags to 1 and non-emptiness plus
  count-match both still pass). gen-eval's own argparse is the one real surface
  this change owns end to end.
  **Note**: must be shown to FAIL — add a flag to the parser without contracting
  it and confirm CI goes red.

## Phase 5 — Migration, gates, downstream notice

- [ ] 5.1 Write tests for the deprecation warning on the hand-authored path `[S]`
  **Spec scenarios**: Service And Tool Descriptor Archetypes (hand-authored descriptor still loads)
  **Design decisions**: D6
  **Dependencies**: 1.4

- [ ] 5.2 Emit the deprecation warning when a descriptor declares no contract `[S]`
  **Design decisions**: D6
  **Dependencies**: 5.1

- [ ] 5.3 Migrate `evaluation/descriptor.yaml` to a derived tool descriptor `[M]`
  **Spec scenarios**: Dogfood (gen-eval evaluates its own CLI surface); Operation And Surface Coverage Model (flag-only tool surfaces are nameable)
  **Design decisions**: D8
  **Dependencies**: 1.6, 1.7, 3.6
  **Note**: the dogfood run currently reports `0 interfaces`; after this task it must report the contracted flag count
  **Note**: depends on 3.6 deliberately. Migrating before the tested-identifier
  vocabulary is extended makes the declared surface N flags while `covered` stays
  empty — turning today's vacuous pass into a guaranteed 0% coverage violation.
  Do not reorder these.

- [ ] 5.4 Write tests asserting an empty declared surface fails the dogfood gate `[S]`
  **Spec scenarios**: Dogfood (an empty declared surface fails rather than reporting coverage)
  **Design decisions**: D3
  **Dependencies**: 5.3

- [ ] 5.4a Write tests for the coverage-completeness rule `[S]`
  **Spec scenarios**: Dogfood (an unexercised, unexcluded tool coverage unit fails the gate); Dogfood (an excluded coverage unit states why)
  **Design decisions**: D11
  **Dependencies**: 3.8, 5.3
  **Note**: must prove the gate FAILS on (a) a unit that is neither exercised
  nor excluded, and (b) an exclusion with a blank reason.

- [ ] 5.4b Implement `scripts/check_coverage_completeness.py` `[S]`
  **Design decisions**: D11
  **Dependencies**: 5.4a
  **Note**: asserts `coverage_pct > 0` (zero means declared and tested
  vocabularies never connected), then that every unevaluated unit carries an
  exclusion with a non-blank reason. This is `make dogfood`'s acceptance gate —
  NOT `declared_interfaces_non_empty`, which goes green on a 0% run, and NOT
  `coverage_pct >= 80`, which is unreachable for this surface.

- [ ] 5.4c Author dogfood scenarios and exclusions covering the contracted flag surface `[M]`
  **Spec scenarios**: Dogfood (gen-eval evaluates its own CLI surface)
  **Design decisions**: D11
  **Dependencies**: 5.4b
  **Note**: measured on the branch — 16 long flags in `__main__.py`, 5 exercised
  by scenarios (`--descriptor`, `--fail-threshold`, `--openspec-change`,
  `--output-dir`, `--print-contract-version`), i.e. 31.2%. Task 3.8 adds
  `--min-coverage`, making 17. The remaining 11 (`--categories`,
  `--changed-features-ref`, `--cli-command`, `--max-iterations`, `--mode`,
  `--no-services`, `--parallel`, `--report-format`, `--sdk-budget`,
  `--time-budget`, `--verbose`) must each be exercised by a scenario or given a
  written exclusion reason. Do not close the gap by lowering a threshold —
  D11 has no threshold to lower.

- [ ] 5.4d Wire `--min-coverage` and the completeness check into `make dogfood` `[S]`
  **Design decisions**: D10, D11
  **Dependencies**: 5.4b, 5.4c

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 5.5 Wire both drift guards into the `gen-eval-tests` CI job `[S]`
  **Design decisions**: D2, D3
  **Dependencies**: 1.6, 2.5

- [ ] 5.6 Refresh `DOWNSTREAM.md` with the as-built coverage semantics and the rename `[S]`
  **Design decisions**: D4, D6, D9
  **Dependencies**: 3.4, 0.3
  **Note**: the notice was authored at plan time (DS-1 is actionable by ACA immediately and does not depend on this change). This task reconciles DS-2's described shape with what actually shipped, then answers the three open questions at its end.
  **Note**: must add DS-5 for the `CONTRACT_VERSION` 1 → 2 bump and the renamed
  `$defs` titles — DS-2/DS-3 already tell consumers to read that schema, so a
  silent title change would break exactly the readers we directed there.

- [ ] 5.7 Update `packages/gen-eval/README.md` for the contract-derived model `[S]`
  **Dependencies**: 5.3

- [ ] Final checkpoint: full suite green, `make dogfood` green, `openspec validate --strict` passes
