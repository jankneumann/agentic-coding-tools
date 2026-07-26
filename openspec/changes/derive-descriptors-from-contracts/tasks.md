# Tasks — Derive gen-eval descriptors from contracts

Test tasks precede the implementation they verify (RED before GREEN).
Sizes: XS ≤30min · S 30min–2hr · M 2hr–1day. No L or XL tasks.

Most work is in `packages/gen-eval/`; task 1.8 touches
`openspec/contracts/README.md`.

## Prerequisites

**1. PR #277 (UP-1..UP-5) — SATISFIED.** Merged to `main` on 2026-07-25 as
`c2213c5f` + `e5fabe3d`. This change builds on top of it and **must not revert
or amend those commits**.

| Artifact | Depended on by |
|---|---|
| `packages/gen-eval/scripts/generate_contract_schemas.py` | task 1.6 (mirrors its `--check` shape), D2 |
| `packages/gen-eval/evaluation/descriptor.yaml` | task 5.3 (migration target), D8 |
| `make dogfood` CI gate | tasks 5.3, 5.4, D8 |

**2. `rename-descriptor-model-levels` — MUST LAND FIRST.** That change renames
the existing element/container models to `*Spec`, freeing `ServiceDescriptor`
and `ToolDescriptor` for the document-level archetypes tasks 1.4 and 2.2 define.

Until it lands, both names still resolve to unrelated element types
(`descriptor.py:41` one MCP tool, `:67` one testable service), and tasks 1.4 /
2.2 would be redefining live public API.

This was originally Phase 0 of *this* change. It was extracted because freeing a
name and reusing it inside one change creates an intermediate state that
verification cannot express — a gate asserting the new meaning runs before the
package that creates it. Three review rounds produced four variants of that
defect before the pattern was recognised. See that change's design D2.

**Verify before starting Phase 1:**

```bash
# Prerequisite 1 — PR #277's artifacts are present
test -f packages/gen-eval/scripts/generate_contract_schemas.py
test -f packages/gen-eval/evaluation/descriptor.yaml

# Prerequisite 2 — the rename has landed.
# `uv run python`, NOT bare python3 — see the third trap below.
cd packages/gen-eval && uv run python -c "
import gen_eval, gen_eval.descriptor as d, pathlib, sys
src = pathlib.Path(gen_eval.__file__).resolve()
sys.exit(f'reading an installed copy, not this tree: {src}') \
    if pathlib.Path('src').resolve() not in src.parents else None
sys.exit('rename-descriptor-model-levels has NOT landed — McpToolSpec is absent, '
         'so ToolDescriptor/ServiceDescriptor are still the legacy element types') \
    if not hasattr(d, 'McpToolSpec') else print('prerequisite 2 satisfied')"
```

Probe `McpToolSpec` specifically, via `uv run`, and assert the import came from
this tree. Three traps make the obvious checks wrong:

- `gen_eval.ToolDescriptor` **does not exist** — only `ServiceDescriptor` and
  `InterfaceDescriptor` are exported at package level. Reaching for it raises
  `AttributeError`, not a useful message. The type lives at
  `gen_eval.descriptor.ToolDescriptor`.
- Asserting `'input_schema' not in ToolDescriptor.model_fields` **fails even
  when the prerequisite is satisfied**. After the rename, `ToolDescriptor` is a
  deprecation alias for `McpToolSpec`, which still carries `input_schema`. That
  check cannot distinguish "rename landed" from "rename didn't", which is the
  only thing it exists to decide.
- **Bare `python3` does not read this tree at all.** `packages/gen-eval` is a
  src-layout package, so an unqualified interpreter resolves `gen_eval` from
  whatever is installed — on this machine, the coordinator's venv at
  `agent-coordinator/.venv/lib/python3.12/site-packages/gen_eval/`. A check run
  that way answers a question about a different copy, and will report "not
  landed" on a branch where it HAS landed. That is worse than no check. Hence
  `uv run python` plus the explicit provenance assertion on the first line.

`McpToolSpec` exists exactly when the rename has landed and at no other time.

If prerequisite 1 fails, this branch has not been rebased onto the merged
`main`. If prerequisite 2 fails, stop: tasks 1.4 and 2.2 will collide with live
public API.

## Phase 1 — Tool contract + tool descriptor (gen-eval self-migration)

- [x] 1.1 Write tests for CLI contract schema validation — required fields, exit codes, flag types `[S]`
  **Spec scenarios**: Descriptor Derivation Drift Guard (a tool contract declaring commands but no coverage units fails)
  **Contracts**: `contracts/cli-contract.schema.json`
  **Design decisions**: D5 (tool contracts are a separate schema)
  **Dependencies**: None

- [x] 1.2 Create `contracts/cli-contract.schema.json` — commands, flags, argument types, exit codes `[S]`
  **Design decisions**: D5
  **Dependencies**: 1.1

- [x] 1.3 Write tests for tool-descriptor derivation from a CLI contract `[M]`
  **Spec scenarios**: Contract As Descriptor Source Of Truth (descriptor derives from a contract); Operation And Surface Coverage Model (flag-only tool surfaces are nameable); Service And Tool Descriptor Archetypes (tool descriptor requires no lifecycle configuration)
  **Design decisions**: D1, D5
  **Dependencies**: 1.2
  **Note**: the lifecycle scenario is normative and easy to leave untested,
  because a tool descriptor that merely *omits* startup config passes trivially.
  Assert the orchestrator actually SKIPS startup, health check, seeding and
  teardown for the tool archetype — that is the behaviour UP-4 shipped and this
  spec delta pins. Omitting startup and observing no crash is not the same
  claim.

- [x] 1.4 Implement the `ToolDescriptor` model with contract-reference loading `[M]`
  **Design decisions**: D1, D5, D6
  **Dependencies**: 1.3

- [x] Checkpoint: run tests, review diff, verify scope

- [x] 1.5 Write tests for the drift guard's fail-closed assertions `[M]`
  **Spec scenarios**: Descriptor Derivation Drift Guard (all four scenarios — drift fails; empty fails; count mismatch fails; commands-but-no-coverage-units fails)
  **Design decisions**: D2, D3
  **Dependencies**: 1.4
  **Note**: each assertion must be proven to FAIL on a deliberately broken fixture, not merely pass on a good one. Fixtures: `empty`, `count_mismatch`, `drifted`, and `one_command_zero_flags` — the last is the case that passed all three original assertions while deriving an empty surface, and is why D3 counts coverage units rather than commands.
  **Note**: the guard counts the archetype's own unit — operations for a service descriptor, flags + positionals + named subcommands for a tool descriptor.

- [x] 1.6 Implement `scripts/generate_tool_descriptor.py` with `--check` mode `[M]`
  **Design decisions**: D2, D3
  **Dependencies**: 1.5
  **Note**: mirror `scripts/generate_contract_schemas.py` from PR #277

- [x] 1.7 Author gen-eval's own CLI contract under `openspec/contracts/gen-eval-framework/cli/` `[S]`
  **Spec scenarios**: Dogfood (gen-eval evaluates its own CLI surface)
  **Design decisions**: D8
  **Dependencies**: 1.2

- [x] 1.8 Document the `<capability>/cli/` sub-path in `openspec/contracts/README.md` `[XS]`
  **Design decisions**: D1, D5
  **Dependencies**: 1.7
  **Note**: the README currently documents only `<capability>/schemas/*.schema.json`
  and `<capability>/openapi/*.yaml`. D1 and task 1.7 introduce a third sibling,
  `<capability>/cli/*.yaml`, for tool contract *instances*. Without this task the
  new sub-path ships as undocumented convention, which is the same drift the
  contracts directory was created to prevent. Also add the `gen-eval-framework`
  row to the "Current contents" table.

- [x] 1.9 Promote `cli-contract.schema.json` to `openspec/contracts/gen-eval-framework/schemas/` `[XS]`
  **Design decisions**: D5
  **Dependencies**: 1.2
  **Note**: promotion happens while the change is in flight, NOT on archival —
  `openspec/contracts/README.md` requires it ("so no window of drift opens") and
  the schema's `$id` already points at the promoted path. Without this the `$id`
  URL 404s and DOWNSTREAM DS-3 points consumers at a path that moves on archive.
  The schema goes to `schemas/`; the contract *instance* from task 1.7 goes to
  `cli/`.

- [x] 1.10 Author an OpenAPI service-contract fixture for Phase 2 `[S]`
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

- [x] Checkpoint: run tests, review diff, verify scope

## Phase 2 — Service descriptor derivation

- [x] 2.1 Write tests for OpenAPI operation extraction — paths, methods, operationIds `[M]`
  **Spec scenarios**: Contract As Descriptor Source Of Truth (descriptor derives from a contract); Contract As Descriptor Source Of Truth (unreachable implementation does not shrink the declared surface)
  **Contracts**: `contracts/openapi/v1.yaml` (fixture, authored by task 1.10)
  **Design decisions**: D1
  **Dependencies**: 1.10
  **Note**: include the fail-closed case — load a descriptor whose implementation
  is absent/unreachable and assert the declared surface is byte-identical to the
  contract-derived one. This is the assertion that distinguishes the selected
  approach from rejected Approach 2; without it D1 is an unverified claim.

- [x] 2.2 Implement the `ServiceDescriptor` model with OpenAPI-backed operations `[M]`
  **Design decisions**: D1, D6
  **Dependencies**: 2.1

- [x] Checkpoint: run tests, review diff, verify scope

- [x] 2.3 Write tests for the MCP projection carve-outs — resources excluded, descriptions preserved, many-to-one honoured `[M]`
  **Spec scenarios**: Operation And Surface Coverage Model (a surface that does not expose an operation is not a gap); Operation And Surface Coverage Model (one surface element serving two operations is covered once)
  **Design decisions**: D4, D7
  **Dependencies**: 2.2, 1.10
  **Note**: the many-to-one case must assert that an explicit `element` binding
  SUPPRESSES name derivation — two operations bound to one tool derive one tool,
  not two.

- [x] 2.4 Implement the OpenAPI-to-MCP tool projection with binding support `[M]`
  **Design decisions**: D4, D7
  **Dependencies**: 2.3
  **Note**: flatten path/query/body into one input object; copy `summary`/`description` verbatim (agent-readable, load-bearing). Derivation is the DEFAULT — an explicit `element` binding wins and emits the bound name once, recording the fan-in.

- [x] 2.5 Implement `scripts/generate_service_descriptor.py` with `--check` mode `[M]`
  **Spec scenarios**: Descriptor Derivation Drift Guard (drift fails)
  **Design decisions**: D2, D3
  **Dependencies**: 2.4

- [x] Checkpoint: run tests, review diff, verify scope

## Phase 3 — Operation × surface coverage model

- [x] 3.1 Write tests for operation-keyed coverage — exposure separate from coverage `[M]`
  **Spec scenarios**: Operation And Surface Coverage Model (one operation tested via one surface is not three gaps; a surface that does not expose an operation is not a gap)
  **Design decisions**: D4
  **Dependencies**: 2.2

- [x] 3.2 Implement the operation-keyed coverage structures in the report model `[M]`
  **Design decisions**: D4
  **Dependencies**: 3.1

- [x] 3.3 Write tests for legacy flat-field back-compatibility `[S]`
  **Spec scenarios**: Operation And Surface Coverage Model (report continues to emit the flat interface list)
  **Design decisions**: D4, D6
  **Dependencies**: 3.2
  **Note**: cover `per_interface` as well as `unevaluated_interfaces` —
  `per_interface` is built at `orchestrator.py:382-388` from `interfaces_tested`,
  and DOWNSTREAM.md tells ACA to assert on it.

- [x] 3.4 Compute the legacy flat `unevaluated_interfaces` and `per_interface` from the operation model `[S]`
  **Design decisions**: D6
  **Dependencies**: 3.3

- [x] Checkpoint: run tests, review diff, verify scope

- [x] 3.5 Write tests for tested-identifier extraction from `args`-only CLI steps `[M]`
  **Spec scenarios**: Operation And Surface Coverage Model (a flag exercised by a scenario is recorded as covered)
  **Design decisions**: D10
  **Dependencies**: 3.2, 1.4
  **Note**: `_extract_interfaces` (`evaluator.py:530`) requires `step.command` to
  be truthy for CLI steps. gen-eval's 8 dogfood steps use `args: [...]` with no
  `command`, so it yields `[]`. Test against those real scenarios, not a synthetic
  step — the whole defect is that the real ones produce nothing.

- [x] 3.6 Extend `_extract_interfaces` to emit flag-level and operation-level identifiers `[M]`
  **Design decisions**: D10, D4
  **Dependencies**: 3.5
  **Note**: tested identifiers must share a vocabulary with the derived declared
  surface, else coverage is string-matching two disjoint sets and reports 0%.
  For the tool archetype emit contracted flags seen in `args`; for the service
  archetype emit operation ids via the element binding.

- [x] 3.7 Write tests for a coverage threshold that fails independently of pass-rate `[S]`
  **Spec scenarios**: Operation And Surface Coverage Model (coverage below the threshold fails the run)
  **Design decisions**: D10
  **Dependencies**: 3.6

- [x] 3.8 Add a `--min-coverage` gate to the CLI `[S]`
  **Design decisions**: D10
  **Dependencies**: 3.7
  **Note**: `__main__.py:399` exits on `report.pass_rate` only, and `make dogfood`
  passes `--fail-threshold 1.0` which is pass-rate. Without this the spec's 80%
  coverage floor has no enforcement mechanism at all.

- [x] Checkpoint: run tests, review diff, verify scope

## Phase 4 — Implemented-surface subset verifiers

- [x] 4.1 Write tests for the argparse subset verifier — undocumented flag detected `[M]`
  **Spec scenarios**: Implemented Surface Subset Verification (undocumented CLI flag is reported; verification distinguishes excess from omission)
  **Design decisions**: D1
  **Dependencies**: 1.4

- [x] 4.2 Implement the argparse subset verifier `[M]`
  **Design decisions**: D1
  **Dependencies**: 4.1

- [x] Checkpoint: run tests, review diff, verify scope

- [x] 4.3 Write tests for the FastAPI subset verifier — undocumented route detected `[M]`
  **Spec scenarios**: Implemented Surface Subset Verification (undocumented endpoint is reported)
  **Design decisions**: D1
  **Dependencies**: 2.2

- [x] 4.4 Implement the FastAPI subset verifier over `app.openapi()` `[M]`
  **Design decisions**: D1
  **Dependencies**: 4.3

- [x] 4.5 Write tests for the MCP subset verifier — undocumented tool detected, many-to-one not a false positive `[M]`
  **Spec scenarios**: Implemented Surface Subset Verification (verification distinguishes excess from omission); Operation And Surface Coverage Model (one surface element serving two operations is covered once)
  **Design decisions**: D1, D4, D7
  **Dependencies**: 2.4
  **Note**: the many-to-one fixture models the real case — `check_locks` serves
  both `list_active_locks` and `get_lock_status` by branching on `file_paths`
  being None (`agent-coordinator/src/coordination_mcp.py:165`). A 1:1 projection
  reports THREE false findings here: `check_locks` as undocumented excess, plus
  two invented tools as omissions. Assert zero violations.

- [x] 4.6 Implement the MCP subset verifier over the server tool listing `[M]`
  **Design decisions**: D1, D4, D7
  **Dependencies**: 4.5
  **Note**: compare against the set of BOUND elements, not against derived
  one-per-operation names.

- [x] Checkpoint: run tests, review diff, verify scope

- [x] 4.7 Wire the argparse subset verifier into CI against gen-eval's own parser `[S]`
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
  **Note (round-7)**: a synthetic parser built by adding one argument per
  contracted unit is a mirror of the contract, not the real surface, and stays
  green when `parse_args` drifts. `parse_args` currently discards its
  `ArgumentParser`, so this task must first extract `build_parser()` and run the
  verifier against THAT. Depends on 4.9 for the loader.

## Phase 4b — Round-7 review remediation

Inserted after the round-7 multi-vendor review (`reviews/round-7/synthesis.md`).
Four independent vendors reviewed waves 1–3; every task below addresses a
finding re-verified by direct execution, not by vendor assertion.

- [x] 4.8 Write tests for archetype-aware descriptor loading `[S]`
  **Spec scenarios**: Service And Tool Descriptor Archetypes (a derived descriptor loads as its archetype)
  **Design decisions**: D4, D6
  **Dependencies**: 1.4, 2.2
  **Note**: must be RED. Assert that loading a generated tool descriptor through
  the runtime entrypoint yields the contracted flag count, and that a generated
  service descriptor retains `operations` so `build_operation_coverage` takes the
  operation path rather than the `_from_element` fallback.

- [x] 4.9 Implement archetype-aware descriptor loading `[M]`
  **Design decisions**: D4, D6
  **Dependencies**: 4.8
  **Note (BLOCKING — round-7 critical, 2 vendors)**: `__main__.py` loads every
  descriptor with `InterfaceDescriptor.from_yaml()`. Pydantic drops unknown
  fields, so `ServiceDescriptor.operations` and
  `ToolDescriptor.commands`/`executable`/`contract` are discarded on load.
  Verified: the same generated file yields 17 interfaces as a `ToolDescriptor`
  and 0 as the base model. Every derived artifact is inert at runtime.
  **Note**: dispatch on the document's own shape (`operations` → service,
  `executable`/`commands` → tool, neither → hand-authored base) or on an
  explicit `kind` field. Rule 4 applies: a hand-authored descriptor must keep
  loading exactly as it does today.
  **Note**: 5.1, 5.2 and 5.3 have acceptance criteria that are unreachable
  without this. Do not start Phase 5 before it lands.

- [x] 4.10 Write tests asserting `coverage_pct` is operation-denominated `[S]`
  **Spec scenarios**: Operation And Surface Coverage Model
  **Design decisions**: D4
  **Dependencies**: 3.2
  **Note**: must be RED. An operation exposed on three surfaces and exercised on
  one must report 100%, not 33%.

- [x] 4.11 Compute `coverage_pct` over operations, not elements `[S]`
  **Design decisions**: D4
  **Dependencies**: 4.10
  **Note (round-7 high)**: `orchestrator.py` divides by `len(all_interfaces)`.
  That is precisely the element arithmetic D4 exists to remove — the operation
  model was built and the headline number kept the old denominator. `--min-coverage`
  gates on this number.

- [x] 4.12 Fix the HTTP prefix mismatch in `operations_for_element()` `[S]`
  **Design decisions**: D7
  **Dependencies**: 2.2
  **Note (round-7, 2 vendors)**: the comparison key is `f"{surface}:{element}"`
  for every surface, but `interface_id("http")` returns an unprefixed
  `"METHOD /path"`. The HTTP branch can never match, so the public fan-in API
  returns `[]` for the primary service surface. Write the failing test first.

- [x] 4.13 Write tests for `$ref` path items and path-level parameters `[S]`
  **Spec scenarios**: Implemented Surface Subset Verification
  **Design decisions**: D1
  **Dependencies**: 2.2, 4.4
  **Note**: must be RED, and must cover both call sites — `_extract_operations`
  and `verify_fastapi`.

- [x] 4.14 Resolve `$ref` path items and merge path-level parameters `[M]`
  **Design decisions**: D1
  **Dependencies**: 4.13
  **Note (round-7 high, 2 vendors)**: both call sites iterate path-item keys and
  test membership in `_HTTP_METHODS`. `$ref` is not a method, so an OpenAPI 3.1
  document using `components/pathItems` yields no operations and no violations —
  the declared surface shrinks silently. That is a fail-open in the one
  direction D1 requires to fail closed.
  **Note**: path-item-level `parameters` are siblings of the verbs and apply to
  every operation under them. Not merging them omits required path parameters
  from derived MCP input schemas.

- [x] 4.15 Write tests for argv end-of-options and short-flag aliasing `[S]`
  **Spec scenarios**: Coverage Vocabulary
  **Design decisions**: D10
  **Dependencies**: 3.6
  **Note**: must be RED. Verified today:
  `args=['--mode','template-only','--','--descriptor']` records
  `cli:--descriptor` for a token the process never interpreted as a flag.

- [x] 4.16 Honour `--` and alias short flags to their long unit `[S]`
  **Design decisions**: D10
  **Dependencies**: 4.15
  **Note (round-7, `--` found by 2 vendors)**: stop flag scanning at the first
  bare `--`. Separately, `coverage_units` emits only `flag.name`, so a step
  using `-v` produces `cli:-v`, fails the declared-membership filter, and
  `cli:--verbose` stays uncovered despite a real exercise — the same vocabulary
  split D10 exists to close. Map `FlagSpec.short` to the long unit.

- [x] 4.17 Descend into subparsers in `verify_argparse` `[S]`
  **Design decisions**: D1
  **Dependencies**: 4.2
  **Note (round-7)**: `_SubParsersAction` carries no option strings, so an
  undocumented `--force` on a subcommand is invisible to the verifier. Recurse
  into `choices`, passing the subcommand name as `command`. Test first.

- [x] 4.18 Signal conflicting properties in `_merge_schemas` `[S]`
  **Design decisions**: D7
  **Dependencies**: 2.3
  **Note (round-7)**: union-by-dict-spread is last-write-wins, so two operations
  requiring the same property with incompatible schemas yield a single silent
  type that matches neither. Intersecting `required` is argued in design;
  property clobber is not. Fail loudly rather than picking a winner.

- [x] 4.19 Mitigate the `--min-coverage` unit ambiguity `[S]`
  **Design decisions**: D10
  **Dependencies**: 3.8
  **Note (round-7, 2 vendors)**: `--min-coverage 0.8` is a legal 0.8% floor and
  indistinguishable from a user meaning 80%. It silently PASSES a ~30% suite —
  the gate fails open, the opposite of its purpose. Reject or warn on a value in
  `(0, 1)` rather than treating it as a sub-1% floor.

- [x] Checkpoint: run tests, review diff, verify scope

## Phase 5 — Migration, gates, downstream notice

- [x] 5.1 Write tests for the deprecation warning on the hand-authored path `[S]`
  **Spec scenarios**: Service And Tool Descriptor Archetypes (hand-authored descriptor still loads)
  **Design decisions**: D6
  **Dependencies**: 1.4

- [x] 5.2 Emit the deprecation warning when a descriptor declares no contract `[S]`
  **Design decisions**: D6
  **Dependencies**: 5.1

- [x] 5.3 Migrate `evaluation/descriptor.yaml` to a derived tool descriptor `[M]`
  **Spec scenarios**: Dogfood (gen-eval evaluates its own CLI surface); Operation And Surface Coverage Model (flag-only tool surfaces are nameable)
  **Design decisions**: D8
  **Dependencies**: 1.6, 1.7, 3.6
  **Note**: the dogfood run currently reports `0 interfaces`; after this task it must report the contracted flag count
  **Note**: depends on 3.6 deliberately. Migrating before the tested-identifier
  vocabulary is extended makes the declared surface N flags while `covered` stays
  empty — turning today's vacuous pass into a guaranteed 0% coverage violation.
  Do not reorder these.

- [x] 5.4 Write tests asserting an empty declared surface fails the dogfood gate `[S]`
  **Spec scenarios**: Dogfood (an empty declared surface fails rather than reporting coverage)
  **Design decisions**: D3
  **Dependencies**: 5.3

- [x] 5.4a Write tests for the coverage-completeness rule `[S]`
  **Spec scenarios**: Dogfood (an unexercised, unexcluded tool coverage unit fails the gate); Dogfood (an excluded coverage unit states why)
  **Design decisions**: D11
  **Dependencies**: 3.8, 5.3
  **Note**: must prove the gate FAILS on (a) a unit that is neither exercised
  nor excluded, and (b) an exclusion with a blank reason.

- [x] 5.4b Implement `scripts/check_coverage_completeness.py` `[S]`
  **Design decisions**: D11
  **Dependencies**: 5.4a
  **Note**: asserts `coverage_pct > 0` (zero means declared and tested
  vocabularies never connected), then that every unevaluated unit carries an
  exclusion with a non-blank reason. This is `make dogfood`'s acceptance gate —
  NOT `declared_interfaces_non_empty`, which goes green on a 0% run, and NOT
  `coverage_pct >= 80`, which is unreachable for this surface.

- [x] 5.4c Author dogfood scenarios and exclusions covering the contracted flag surface `[M]`
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

- [x] 5.4d Wire `--min-coverage` and the completeness check into `make dogfood` `[S]`
  **Design decisions**: D10, D11
  **Dependencies**: 5.4b, 5.4c, 4.19
  **Note (round-7, 2 vendors)**: do NOT set `--min-coverage 80` here to match the
  "80%+" language in `specs/gen-eval-framework/spec.md`. Dogfood covers ~5 of 17
  flags (~29%), so an 80% floor makes `make dogfood` permanently red even when
  D11 completeness is fully satisfied. **Completeness is the tool gate; the
  percentage is informative.** Wire the completeness check as the failing gate
  and pass `--min-coverage` only at a floor the contracted surface can actually
  reach. If the spec's "80%+" language implies otherwise, correct the spec text
  in this task rather than adopting an unreachable threshold.

- [x] Checkpoint: run tests, review diff, verify scope

- [x] 5.5 Wire both drift guards into the `gen-eval-tests` CI job `[S]`
  **Design decisions**: D2, D3
  **Dependencies**: 1.6, 2.5

- [x] 5.6 Refresh `DOWNSTREAM.md` with the as-built coverage semantics and the rename `[S]`
  **Design decisions**: D4, D6
  **Dependencies**: 3.4
  **Note**: the notice was authored at plan time (DS-1 is actionable by ACA immediately and does not depend on this change). This task reconciles DS-2's described shape with what actually shipped, then answers the three open questions at its end.
  **Note**: the `CONTRACT_VERSION` bump and the renamed `$defs` titles are NOT
  this change's to announce — they belong to the prerequisite
  `rename-descriptor-model-levels` and are covered by its own notice. DS-3 here
  carries only the sequencing pointer. Do not duplicate that notice.

- [x] 5.7 Update `packages/gen-eval/README.md` for the contract-derived model `[S]`
  **Dependencies**: 5.3

- [x] 5.8 Reclaim the `ServiceDescriptor` / `ToolDescriptor` exports and announce it `[S]`
  **Spec scenarios**: Descriptor Reclamation Is Announced (a reclaimed name is announced rather than silently rebound)
  **Design decisions**: D6
  **Dependencies**: 1.4, 2.2
  **Note**: `gen_eval/__init__.py` lists `ServiceDescriptor` in `__all__`. After
  the prerequisite rename it points at the deprecation alias for `ServiceSpec` —
  the element container. After tasks 1.4 and 2.2 the name should denote the new
  document archetype. Without this task the package-level export keeps resolving
  to the wrong class while `gen_eval.descriptor.ServiceDescriptor` resolves to
  the right one, and the two disagree silently.
  **Note**: `ToolDescriptor` is NOT currently exported at package level — only
  `ServiceDescriptor` and `InterfaceDescriptor` are. Export the new archetype
  and update `tests/test_public_api_parity.py`, which pins `__all__`.
  **Note**: this is a **reclamation**, not a deprecation: both names resolve
  successfully while denoting something different from one release ago. A
  deprecation warning does not cover that failure mode, so the prerequisite
  change's spec requires a version increment and a downstream notice naming both
  meanings. Add the DS entry naming both meanings.
  **Note (round-7)**: do NOT bump `CONTRACT_VERSION` in this task. That constant
  versions the published JSON Schemas and bumps only on a breaking schema change
  (field removed, made required, type narrowed). Reclaiming a Python export name
  is not one, and bumping it would falsely signal a breaking schema change to
  every consumer pinning the value. This also resolves a contradiction already
  in the plan: the notes on 5.6 and above both state the bump belongs to the
  prerequisite `rename-descriptor-model-levels`, not here. The reclamation is
  announced by the DS entry and by `__all__` parity, not by the schema version.

- [x] Final checkpoint: full suite green, `make dogfood` green, `openspec validate --strict` passes
