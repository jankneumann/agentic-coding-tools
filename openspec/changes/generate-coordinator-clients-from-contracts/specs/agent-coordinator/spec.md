## MODIFIED Requirements

### Requirement: Feature Registry HTTP Endpoints

The coordination HTTP API SHALL expose feature registry operations as REST endpoints with auth middleware.

The fixed-path route `GET /features/active` SHALL take precedence over the parameterised route `GET /features/{feature_id}`, so that `active` is never interpreted as a feature identifier.

Every feature registry endpoint, including `GET /features/{feature_id}`, SHALL require a valid API key.

#### Scenario: List active features via HTTP
- **WHEN** a client sends `GET /features/active` with a valid API key
- **THEN** the API SHALL return HTTP 200 with an AXI list envelope whose `features` key holds the active features ordered by merge priority
- **AND** the envelope SHALL contain `count` equal to the number of features and a boolean `truncated`

#### Scenario: Active-features route is not shadowed by the feature-id route
- **WHEN** a client sends `GET /features/active` with a valid API key and no feature with id `active` exists
- **THEN** the API SHALL NOT return HTTP 404
- **AND** the request SHALL be handled by the list-active-features operation

#### Scenario: Unauthorized feature access
- **WHEN** a client sends `GET /features/active` without an API key
- **THEN** the API SHALL return HTTP 401

#### Scenario: Unauthorized single-feature access
- **WHEN** a client sends `GET /features/{feature_id}` without an API key
- **THEN** the API SHALL return HTTP 401

## ADDED Requirements

### Requirement: Contract Breaking-Change Gate

CI SHALL compare every OpenAPI document under `openspec/contracts/**/openapi/` that a pull request modifies against the same document at the pull request's merge base, and SHALL fail when the comparison reports a breaking change that the pull request has not explicitly acknowledged.

An acknowledgement SHALL be a checked-in file inside an OpenSpec change directory touched by the same pull request, naming each accepted breaking change by its rule identifier and operation, so that the acceptance is reviewable in the diff.

OpenAPI documents under `openspec/changes/**/contracts/` SHALL NOT be gated; they are gated when promoted into `openspec/contracts/`.

The comparison tool SHALL be pinned to an exact version and its downloaded binary SHALL be verified against a recorded checksum before it runs.

#### Scenario: Unacknowledged breaking change fails the gate
- **WHEN** a pull request removes a required response property from an operation in `openspec/contracts/agent-coordinator/openapi/features.yaml`
- **AND** no change directory in the pull request acknowledges that breaking change
- **THEN** the gate SHALL fail
- **AND** its output SHALL name the document, the operation, and the rule identifier

#### Scenario: Acknowledged breaking change passes the gate
- **WHEN** a pull request makes the same breaking change
- **AND** a change directory touched by the pull request contains an acknowledgement entry for that rule identifier and operation
- **THEN** the gate SHALL pass
- **AND** its output SHALL list the acknowledged change

#### Scenario: Additive change passes without acknowledgement
- **WHEN** a pull request adds an optional response property to a promoted contract
- **THEN** the gate SHALL pass without any acknowledgement

#### Scenario: Change-local contracts are not gated
- **WHEN** a pull request modifies only `openspec/changes/<id>/contracts/openapi/v1.yaml`
- **THEN** the gate SHALL report that no promoted contracts changed and SHALL pass

#### Scenario: Unverified comparison binary is refused
- **WHEN** the downloaded comparison binary's checksum does not match the recorded checksum
- **THEN** the gate SHALL fail before running any comparison

### Requirement: Feature Registry Response Conformance

The test suite SHALL drive every operation declared in `openspec/contracts/agent-coordinator/openapi/features.yaml` through the coordination HTTP API built by `create_coordination_api()`, and SHALL validate each response body against the response schema the contract declares for that status code.

The conformance test SHALL fail when the contract declares an operation that has no response schema for a success status, so that an untyped contract cannot pass by omission.

The conformance test SHALL run without a database, using a substituted feature registry service.

#### Scenario: Every contracted feature operation is exercised
- **WHEN** the conformance test runs
- **THEN** it SHALL issue at least one request for each of `listActiveFeatures`, `registerFeature`, `deregisterFeature`, `getFeature`, and `analyzeFeatureConflicts`
- **AND** it SHALL fail if `features.yaml` declares an operation the test does not exercise

#### Scenario: Response shape drift is detected
- **WHEN** an endpoint returns a body that omits a property the contract marks as required
- **THEN** the conformance test SHALL fail and name the operation and the missing property

#### Scenario: Untyped success response is rejected
- **WHEN** a success response in `features.yaml` has a description but no schema
- **THEN** the conformance test SHALL fail and name the operation and status code
