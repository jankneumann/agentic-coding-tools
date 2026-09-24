# Contracts — rename-descriptor-model-levels

## Applicable sub-types

| Sub-type | Applies | Why |
|---|---|---|
| JSON Schema | **Modified, not authored** | `src/gen_eval/contracts/interface-descriptor.schema.json` is regenerated: four `$defs` titles are renamed and `x-gen-eval-contract-version` goes 1 → 2. The schema is generated from the Pydantic models by `scripts/generate_contract_schemas.py`, so it is not hand-authored here. |
| OpenAPI | No | This change introduces no HTTP endpoints. |
| Database | No | gen-eval holds no persistent state. |
| Events | No | No events emitted or consumed. |
| Type generation | No | The generated artifacts ARE the type contract, and they are produced by the existing generator. |

## The versioned contract this change touches

PR #277 published `src/gen_eval/contracts/` for offline consumers: three schemas
plus a `VERSION` file, each schema stamped with `x-gen-eval-contract-version`.

This change renames four `$defs` titles in `interface-descriptor.schema.json`,
which is a breaking change for any consumer resolving `$defs` by title. That is
why `CONTRACT_VERSION` bumps rather than the rename shipping silently — see
design D3.

**All four generated artifacts are regenerated**, not just the descriptor
schema, because the version stamp appears in all three schemas plus `VERSION`.
Regenerating a subset leaves `test_contract_schemas.py::TestNoDrift` failing on
the remainder.

## Not promoted to `openspec/contracts/`

`openspec/contracts/README.md` describes promotion for contracts that must
outlive their change. These schemas are **not** promoted, because they are not
change-local artifacts in the first place: they live at a stable path inside the
published package (`src/gen_eval/contracts/`) and are already what consumers
read. There is no archive-drift risk to mitigate.
