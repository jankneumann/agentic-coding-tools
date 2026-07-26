# Change Context: rename-descriptor-model-levels

Phase 2 (implementation) complete. Evidence column is populated where the
implementation commit itself proves the requirement; `/validate-feature` fills
the rest.

The contract for this change is **modified, not authored** — the JSON Schema
under `src/gen_eval/contracts/` is generated from the pydantic models by
`scripts/generate_contract_schemas.py`. Contract refs therefore point at the
generated artifact the requirement lands in, not at a hand-written spec in
`contracts/`, which holds only a README.

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| gen-eval-framework.1 | Descriptor Model Naming Levels | An element or per-surface container type SHALL use the `Spec` suffix; a whole-document type SHALL use `Descriptor` | `src/gen_eval/contracts/interface-descriptor.schema.json#/$defs` | D1 | `src/gen_eval/descriptor.py`, `src/gen_eval/__init__.py` | `test_descriptor_naming.py::TestNamingLevels::test_every_element_and_container_type_uses_the_spec_suffix`, `::TestNewNames` (16 cases) | pass `0e9c819c` |
| gen-eval-framework.2 | Descriptor Model Naming Levels | No single suffix SHALL denote both levels | `src/gen_eval/contracts/interface-descriptor.schema.json#/$defs` | D1 | `src/gen_eval/descriptor.py` | `::TestNamingLevels::test_descriptor_suffix_names_only_the_document`, `::test_the_document_type_composes_the_spec_types` | pass `0e9c819c` |
| gen-eval-framework.3 | Descriptor Model Naming Levels | A renamed element type SHALL be importable under its new name and SHALL carry its pre-rename fields | `src/gen_eval/contracts/interface-descriptor.schema.json#/$defs` | D1 | `src/gen_eval/descriptor.py`, `src/gen_eval/__init__.py` | `::TestNewNames::test_carries_its_pre_rename_field` (4 cases), `::test_reachable_on_the_package` | pass `0e9c819c` |
| gen-eval-framework.4 | Renamed Published Types Retain Warning Aliases | A rename of a published model type SHALL retain a deprecation alias under the previous name for at least one release | `src/gen_eval/contracts/VERSION` | D2 | `src/gen_eval/descriptor.py`, `src/gen_eval/__init__.py` | `::TestDeprecationAliases::test_alias_resolves_to_the_renamed_type`, `::test_alias_resolves_on_the_package_too` | pass `0e9c819c` |
| gen-eval-framework.5 | Renamed Published Types Retain Warning Aliases | Accessing an alias SHALL emit a deprecation warning naming the replacement | --- | D4 | `src/gen_eval/descriptor.py` | `::TestDeprecationAliases::test_alias_warns_and_names_the_replacement`, `::test_alias_warns_on_every_access_not_just_the_first`, `::TestNewNames::test_accessing_a_new_name_does_not_warn` | pass `0e9c819c` |
| gen-eval-framework.6 | Renamed Published Types Retain Warning Aliases | A rename of a published model type SHALL increment the descriptor contract version, and every generated artifact carrying that version SHALL be regenerated | `src/gen_eval/contracts/VERSION`, all 3 `*.schema.json` | D3 | `src/gen_eval/contracts/__init__.py`, `contracts/VERSION`, `contracts/*.schema.json` | `test_contract_schemas.py::TestContractVersionBump` (5 cases), `::TestNoDrift` | pass `0e9c819c` |
| gen-eval-framework.7 | Renamed Published Types Retain Warning Aliases | A reclamation SHALL increment the contract version and SHALL be recorded in a downstream notice naming both the old and the new meaning | `openspec/changes/rename-descriptor-model-levels/DOWNSTREAM.md` | D2 | `DOWNSTREAM.md` (§DS-3) | --- (documentation obligation; the 2→3 bump is `derive-descriptors-from-contracts`' obligation) | pass `9c55cf57` |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 — `*Spec` names an element, `*Descriptor` names a document | The distinction a reader needs is "whole thing or part of it"; encoding it in the suffix makes every future addition self-classifying | Four models renamed in `descriptor.py`; `InterfaceDescriptor` left alone as the sole `*Descriptor` | `ServiceSpec` keeps container semantics under `Spec` deliberately — it describes one *surface*, not the project |
| D2 — No freed name is reused in this change | When one change both frees and reassigns a name, the name's meaning depends on which work package has run, and no gate can assert a stable fact about it | All four old names become plain aliases; nothing here defines a new type under a freed name | This is the property whose absence caused the extraction from `derive-descriptors-from-contracts` after four blocking findings of the same shape |
| D3 — The version bump covers every generated artifact | The generator stamps `x-gen-eval-contract-version` into all three schemas, so a bump changes every one | `CONTRACT_VERSION` 1→2 and all four artifacts regenerated in one commit | Regenerating only the descriptor schema leaves `TestNoDrift` failing on the other two |
| D4 — Aliases warn, and the gate proves both halves | Presence alone is satisfied by a plain re-export that never deprecates; a warning alone is satisfied by a broken alias | PEP 562 `__getattr__` returning the renamed type *and* warning, with the alias deliberately not cached into `globals()` | Caching would let the module dict answer every access after the first, so only the first consumer would ever see the warning |

## Coverage Summary

- **Requirements traced**: 7/7
- **Tests mapped**: 6 requirements have at least one test; `gen-eval-framework.7` is a documentation obligation discharged by `DOWNSTREAM.md` §DS-3
- **Evidence collected**: 7/7 requirements have pass evidence
- **Gaps identified**: none
- **Deferred items**: none — `tasks.md` is 11/11 checked, no `deferred-tasks.md`
