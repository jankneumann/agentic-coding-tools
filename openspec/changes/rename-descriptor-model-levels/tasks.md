# Tasks — Rename descriptor model levels

Test tasks precede the implementation they verify (RED before GREEN).
Sizes: XS ≤30min · S 30min–2hr · M 2hr–1day. No L or XL tasks.

All work is in `packages/gen-eval/`. This change is **mechanical**: no behaviour
changes. If a test that is not a naming, alias, or schema-version test changes
meaning, the rename has overreached — stop and reassess.

Measured on the branch before starting: `EndpointDescriptor` 5 refs in `src/`
and 39 in `tests/`; `ToolDescriptor` 5 / 9; `CommandDescriptor` 5 / 6;
`ServiceDescriptor` 7 / 36. Plus 8 `$defs` titles in the published schema.
`InterfaceDescriptor` (32 / 150) is NOT renamed.

## Phase 1 — Rename with warning aliases

- [x] 1.1 Write tests pinning the new names, the aliases, and the warnings `[S]`
  **Spec scenarios**: Descriptor Model Naming Levels (a renamed element type is reachable under its new name); Renamed Published Types Retain Warning Aliases (an old name still resolves and warns); (an alias that does not warn fails the gate)
  **Design decisions**: D1, D4
  **Dependencies**: None
  **Note**: assert BOTH halves per alias — resolves, and emits
  `DeprecationWarning` on access. Presence alone is satisfied by a plain
  re-export that never deprecates; a warning alone is satisfied by a broken
  alias. Test file: `tests/test_descriptor_naming.py`.

- [x] 1.2 Rename the four element/container models `[M]`
  **Design decisions**: D1
  **Dependencies**: 1.1
  **Note**: `EndpointDescriptor`→`EndpointSpec`, `ToolDescriptor`→`McpToolSpec`,
  `CommandDescriptor`→`CommandSpec`, `ServiceDescriptor`→`ServiceSpec`.
  `InterfaceDescriptor` is unchanged.

- [x] 1.3 Add warning deprecation aliases for all four old names `[S]`
  **Design decisions**: D2, D4
  **Dependencies**: 1.2
  **Note**: all four alias uniformly — this change frees names but reuses none
  (D2), so there is no special case. `derive-descriptors-from-contracts` reuses
  two of them later; that is its concern, not this change's.

- [x] 1.4 Update `__init__.py` exports and `test_public_api_parity.py` `[S]`
  **Design decisions**: D1
  **Dependencies**: 1.3
  **Note**: `ServiceDescriptor` is in `__all__` today and pinned by the parity
  test, so both must move together or the parity test fails.

- [x] Checkpoint: run tests, review diff, verify scope

## Phase 2 — Version bump and artifact regeneration

- [x] 2.1 Write tests asserting the version bump and clean regeneration `[S]`
  **Spec scenarios**: Renamed Published Types Retain Warning Aliases (renaming a published type bumps the contract version)
  **Design decisions**: D3
  **Dependencies**: 1.4

- [x] 2.2 Bump `CONTRACT_VERSION` 1 → 2 and regenerate all four artifacts `[S]`
  **Design decisions**: D3
  **Dependencies**: 2.1
  **Note**: the generator writes `interface-descriptor.schema.json`,
  `scenario.schema.json`, `eval-report.schema.json`, and `VERSION`, and stamps
  `x-gen-eval-contract-version` into all three schemas. Regenerating only the
  descriptor schema leaves `test_contract_schemas.py::TestNoDrift` failing on
  the other two.

- [x] Checkpoint: run tests, review diff, verify scope

## Phase 3 — Migrate call sites and notify

- [x] 3.1 Migrate the 11 test files that reference pre-rename names `[S]`
  **Design decisions**: D1
  **Dependencies**: 1.3
  **Note**: `conftest.py`, `test_descriptor.py`, `test_cli_generator.py`,
  `test_cli_transport_stderr.py`, `test_feedback.py`, `test_generator.py`,
  `test_hybrid_generator.py`, `test_integration_orchestrator.py`,
  `test_integration_scenarios.py`, `test_optional_startup.py`,
  `test_sdk_generator.py`.
  **Note**: these PASS untouched because the aliases work — that is the trap.
  Landing without this leaves 11 files on deprecated names on day one.
  `tests/test_descriptor_naming.py` is exempt: it must reference the old names
  in order to test them.

- [ ] 3.2 Write the downstream notice `[S]`
  **Design decisions**: D2
  **Dependencies**: 2.2
  **Note**: must state that `ServiceDescriptor` and `ToolDescriptor` will be
  **reused** with different meanings by `derive-descriptors-from-contracts`. A
  consumer reading "deprecated" as "going away" will be surprised when the name
  reappears as a different type. This is the one place the two changes are
  coupled and it must be said plainly.

- [ ] Final checkpoint: full suite green under `-W error::DeprecationWarning`
      (excluding `test_descriptor_naming.py`), `generate_contract_schemas.py
      --check` clean, `openspec validate --strict` passes
