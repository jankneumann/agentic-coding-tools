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

## Phase 1 — Tool contract + tool descriptor (gen-eval self-migration)

- [ ] 1.1 Write tests for CLI contract schema validation — required fields, exit codes, flag types `[S]`
  **Spec scenarios**: Service And Tool Descriptor Archetypes (tool descriptor requires no lifecycle configuration)
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

- [ ] 1.5 Write tests for the drift guard's three fail-closed assertions `[M]`
  **Spec scenarios**: Descriptor Derivation Drift Guard (all three scenarios — drift fails; empty fails; count mismatch fails)
  **Design decisions**: D2, D3
  **Dependencies**: 1.4
  **Note**: each assertion must be proven to FAIL on a deliberately broken fixture, not merely pass on a good one

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
  `<capability>/cli/*.yaml`, for tool contracts. Without this task the new
  sub-path ships as undocumented convention, which is the same drift the
  contracts directory was created to prevent.

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 2 — Service descriptor derivation

- [ ] 2.1 Write tests for OpenAPI operation extraction — paths, methods, operationIds `[M]`
  **Spec scenarios**: Contract As Descriptor Source Of Truth (descriptor derives from a contract)
  **Contracts**: `contracts/openapi/v1.yaml` (fixture)
  **Design decisions**: D1
  **Dependencies**: None

- [ ] 2.2 Implement the `ServiceDescriptor` model with OpenAPI-backed operations `[M]`
  **Design decisions**: D1, D6
  **Dependencies**: 2.1

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 2.3 Write tests for the MCP projection carve-outs — resources excluded, descriptions preserved `[M]`
  **Spec scenarios**: Operation And Surface Coverage Model (a surface that does not expose an operation is not a gap)
  **Design decisions**: D7
  **Dependencies**: 2.2

- [ ] 2.4 Implement the OpenAPI-to-MCP tool projection `[M]`
  **Design decisions**: D7
  **Dependencies**: 2.3
  **Note**: flatten path/query/body into one input object; copy `summary`/`description` verbatim (agent-readable, load-bearing)

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

- [ ] 3.4 Compute the legacy flat `unevaluated_interfaces` from the operation model `[S]`
  **Design decisions**: D6
  **Dependencies**: 3.3

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

- [ ] 4.5 Write tests for the MCP subset verifier — undocumented tool detected `[M]`
  **Spec scenarios**: Implemented Surface Subset Verification (verification distinguishes excess from omission)
  **Design decisions**: D1, D7
  **Dependencies**: 2.4

- [ ] 4.6 Implement the MCP subset verifier over the server tool listing `[M]`
  **Design decisions**: D1, D7
  **Dependencies**: 4.5

- [ ] Checkpoint: run tests, review diff, verify scope

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
  **Dependencies**: 1.6, 1.7
  **Note**: the dogfood run currently reports `0 interfaces`; after this task it must report the contracted flag count

- [ ] 5.4 Write tests asserting an empty declared surface fails the dogfood gate `[S]`
  **Spec scenarios**: Dogfood (an empty declared surface fails rather than reporting coverage)
  **Design decisions**: D3
  **Dependencies**: 5.3

- [ ] Checkpoint: run tests, review diff, verify scope

- [ ] 5.5 Wire both drift guards into the `gen-eval-tests` CI job `[S]`
  **Design decisions**: D2, D3
  **Dependencies**: 1.6, 2.5

- [ ] 5.6 Refresh `DOWNSTREAM.md` with the as-built coverage semantics `[S]`
  **Design decisions**: D4, D6
  **Dependencies**: 3.4
  **Note**: the notice was authored at plan time (DS-1 is actionable by ACA immediately and does not depend on this change). This task reconciles DS-2's described shape with what actually shipped, then answers the three open questions at its end.

- [ ] 5.7 Update `packages/gen-eval/README.md` for the contract-derived model `[S]`
  **Dependencies**: 5.3

- [ ] Final checkpoint: full suite green, `make dogfood` green, `openspec validate --strict` passes
