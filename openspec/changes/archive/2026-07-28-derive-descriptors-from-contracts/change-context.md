# Change Context: derive-descriptors-from-contracts

Generated during the VALIDATE phase (autopilot). This is the requirement
traceability matrix required by `validate-feature` step 7.1; it did not exist
prior to this run. Evidence below was collected by direct execution against
commit `081663b2` in a detached checkout of the change branch, independent of
the round-9 IMPL_REVIEW synthesis (`reviews/round-9/synthesis.md`), which this
matrix corroborates rather than merely restates.

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Test(s) | Evidence |
|---|---|---|---|---|
| R1 | spec.md:5 Contract As Descriptor Source Of Truth | Descriptors derive from `openspec/contracts/<cap>/`; runtime introspection only verifies a subset, never widens the declared surface | `test_derivation_drift.py`, `test_dogfood_descriptor_derivation.py` | pass 081663b2 — `generate_tool_descriptor.py --check` exits 0, "tool descriptor up to date (17 coverage units)" |
| R2 | spec.md:32 Service And Tool Descriptor Archetypes | `ServiceDescriptor`/`ToolDescriptor` load via archetype-aware dispatch (`load_descriptor`), not the discarding `InterfaceDescriptor.from_yaml()` path (round-7 BLOCKING) | `test_descriptor_loading.py`, `test_service_descriptor.py`, `test_tool_descriptor.py` | pass 081663b2 — `descriptor.py:337` `load_descriptor()` dispatches on `operations`/`executable` markers; confirmed `ToolDescriptor.from_yaml` vs `load_descriptor` no longer diverge (17 vs 17); round-7 defect closed |
| R3 | spec.md:63 Descriptor Derivation Drift Guard | Mutated contract/descriptor fails `--check` with a diff, not silently | `test_derivation_drift.py` | pass 081663b2 — suite green; round-9 vendors independently mutated `executable` and a flag name, `--check` exited 1 with a unified diff, restored byte-for-byte |
| R4 | spec.md:106 Implemented Surface Subset Verification | Undocumented endpoints/flags reported; excess vs omission distinguished | `test_metrics_surface.py`, `test_empty_surface_fails.py` | pass 081663b2 — suite green |
| R5 | spec.md:135 Operation And Surface Coverage Model | Many-to-one operation/surface binding; flag-only tool units are nameable and creditable | `test_coverage_model.py`, `test_coverage_vocabulary.py`, `test_min_coverage_units.py`, `test_coverage_denominator.py` | pass 081663b2 — `make dogfood`: 10 of 17 units exercised (58.8%), 7 excluded with written reasons, `check_coverage_completeness.py` exit 0 |
| R6 | spec.md:213 Descriptor Reclamation Is Announced | `ToolDescriptor`/`ServiceDescriptor` are distinct from the legacy `McpToolSpec`/`ServiceSpec` exports, not silently rebound | `test_descriptor_naming.py` | pass 081663b2 — `gen_eval.ToolDescriptor is gen_eval.McpToolSpec` → `False`; both names resolve, distinct types confirmed live via direct import |
| R7 | spec.md:246 Interface Descriptor | Base model still validates project surface; optional lifecycle config; declared surface sourced from contract | `test_descriptor.py` | pass 081663b2 — suite green |
| R8 | spec.md:292 Dogfood | gen-eval's own CLI surface is contract-derived and dogfooded end-to-end, 80%+ coverage claim reconciled to the achievable 58.8% floor (`--min-coverage 1`) | `make dogfood` (evaluation/descriptor.yaml) | pass 081663b2 — `13/13 passed (100.0%)`, `coverage 58.8% >= 1.0%`, gate `check_coverage_completeness.py` exit 0 |

## Coverage Summary

- Requirements traced: 8 / 8
- Tests mapped: 8 / 8 (all have dedicated test modules; full suite below)
- Evidence collected: 8 / 8 (all `pass`, commit `081663b2`)
- Gaps: 0 blocking. Non-blocking N1 (coverage-attribution honesty: 8/17 asserted vs 10/17 passed-flag-credited; recorded in round-9 synthesis, no gate outcome changes)
- Deferred: none

## Independent re-verification (this run, not carried over from round-9)

- `make test` (after `make dogfood` populates the report dependency): **1068 passed, 1 skipped, 12 deselected**
- `make dogfood`: **13/13 passed (100.0%)**, coverage **58.8%** (10 of 17 units), `check_coverage_completeness.py` → exit 0
- `make lint` (ruff): **clean**
- `uv run mypy src/gen_eval/ --strict --ignore-missing-imports`: **5 errors** (pre-existing, matches round-9 claim exactly)
- `openspec validate derive-descriptors-from-contracts --strict`: **valid**
- `generate_tool_descriptor.py --check`: **up to date (17 coverage units)**
- `tasks.md` unchecked boxes: **0**
- `CONTRACT_VERSION`: **"2"**, matches all three published schema files' `x-gen-eval-contract-version`
- Round-7 BLOCKING finding (archetype-discarding load path) independently confirmed fixed by reading `__main__.py:364-368` and `descriptor.py:337-377` — the fix is structural (archetype dispatch on document shape), not a workaround
