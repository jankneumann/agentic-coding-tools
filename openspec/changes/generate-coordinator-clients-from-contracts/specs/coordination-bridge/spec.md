## ADDED Requirements

### Requirement: Contract-Generated Bindings

The bridge SHALL obtain the request and response types, HTTP method, path, path parameters, and authentication requirement of each contract-backed operation from bindings generated from the hand-authored OpenAPI contract, not from values written by hand in the bridge.

Generated bindings SHALL be produced only from documents under `openspec/contracts/`, never from the running application's self-description.

Generated bindings SHALL import only the Python standard library, because skills invoke the bridge with the system `python3` interpreter and no virtual environment.

Generation SHALL be deterministic: regenerating from an unchanged contract SHALL produce byte-identical files, and the generated files SHALL carry no timestamps or absolute paths.

The generator SHALL provide a check mode that exits non-zero when the checked-in bindings differ from what the current contract produces, and CI SHALL run that check mode.

#### Scenario: Bindings are regenerated from the contract
- **WHEN** a maintainer runs the generator against `openspec/contracts/agent-coordinator/openapi/features.yaml`
- **THEN** it SHALL write a models module containing a `TypedDict` for every request body and success response schema in the document
- **AND** it SHALL write an operations module mapping each `operationId` to its method, path, path parameter names, and whether an API key is required

#### Scenario: Regeneration is byte-identical
- **WHEN** the generator runs twice against an unchanged contract
- **THEN** the second run SHALL produce files byte-identical to the first

#### Scenario: Stale bindings fail CI
- **WHEN** a pull request changes a response schema in `features.yaml` without regenerating the bindings
- **THEN** the generator's check mode SHALL exit non-zero
- **AND** its output SHALL name the stale file and the regeneration command

#### Scenario: Bindings stay standard-library only
- **WHEN** the bridge module is imported by a `python3` interpreter that has only the standard library installed
- **THEN** the import SHALL succeed
- **AND** no module reachable from the generated bindings SHALL be a third-party package

### Requirement: Feature Registry Bridge Helpers

The bridge SHALL expose a helper for every operation in the feature registry contract: `try_register_feature`, `try_deregister_feature`, `try_get_feature`, `try_list_active_features`, and `try_analyze_feature_conflicts`.

Each helper SHALL resolve its method and path from the generated operations module, SHALL type its payload and its successful `data` with the generated models, and SHALL return the bridge's existing uniform envelope with status `ok`, `skipped`, or `error`.

Existing keyword parameters of `try_register_feature` and `try_deregister_feature` SHALL remain accepted with their current defaults.

#### Scenario: Register feature against a live coordinator
- **WHEN** `try_register_feature` is called with a reachable coordinator and a valid API key
- **THEN** the helper SHALL send `POST /features/register` as resolved from the generated operations module
- **AND** it SHALL return status `ok` with the registration result in `data`

#### Scenario: Capability probe recognises the feature registry
- **WHEN** coordinator availability detection probes the feature registry on a coordinator that serves `GET /features/active`
- **THEN** `CAN_FEATURE_REGISTRY` SHALL be reported as available

#### Scenario: Get a single feature
- **WHEN** `try_get_feature(feature_id="f-1")` is called and the coordinator knows `f-1`
- **THEN** the helper SHALL send `GET /features/f-1` with the identifier URL-encoded into the path
- **AND** it SHALL return status `ok` with the feature in `data`

#### Scenario: Unknown feature
- **WHEN** `try_get_feature` is called for an identifier the coordinator does not know
- **THEN** the helper SHALL return a non-`ok` envelope without raising

#### Scenario: Coordinator unreachable
- **WHEN** any feature registry helper is called while the coordinator is unreachable
- **THEN** it SHALL return status `skipped` with reason `coordinator_unreachable` and SHALL NOT raise
