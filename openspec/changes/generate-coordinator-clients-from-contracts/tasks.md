# Tasks: generate-coordinator-clients-from-contracts

Sizing follows the plan-feature Task Sizing Reference. No task is XL or L; the largest are M.
Test tasks precede the implementation they verify. Scenario references use
`<capability>.<requirement>` shorthand:

- `agent-coordinator.fr-http` — Feature Registry HTTP Endpoints (MODIFIED)
- `agent-coordinator.gate` — Contract Breaking-Change Gate
- `agent-coordinator.conformance` — Feature Registry Response Conformance
- `agent-coordinator.drift` — HTTP Contract Drift Verification
- `coordination-bridge.bindings` — Contract-Generated Bindings
- `coordination-bridge.fr-helpers` — Feature Registry Bridge Helpers

## 1. Contracts (wp-contracts)

- [x] 1.1 Validate the typed contract and generated stub — run `openapi-spec-validator` on `contracts/openapi/v1.yaml` and import `contracts/generated/models.py` under `python3 -I`
  **Spec scenarios**: coordination-bridge.bindings (Bindings stay standard-library only)
  **Contracts**: contracts/openapi/v1.yaml, contracts/generated/models.py
  **Design decisions**: D2
  **Dependencies**: None
  **Size**: XS

## 2. Promote the contract (wp-contracts)

- [x] 2.1 Promote `contracts/openapi/v1.yaml` over `openspec/contracts/agent-coordinator/openapi/features.yaml`, keeping its header provenance and every `x-traceability` block
  **Spec scenarios**: agent-coordinator.fr-http (List active features via HTTP, Unauthorized single-feature access)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D1
  **Dependencies**: 1.1
  **Size**: S

- [x] 2.2 Write `contracts/accepted-breaking-changes.yaml` acknowledging each oasdiff breaking finding produced by 2.1 (bare array → envelope on `listActiveFeatures`, new security on `getFeature`, tightened request bodies), one entry per `(document, operation, rule_id)` with rationale
  **Spec scenarios**: agent-coordinator.gate (Acknowledged breaking change passes the gate)
  **Design decisions**: D4
  **Dependencies**: 2.1
  **Size**: S

- [x] 2.3 Run the requirement-traceability sweep (`packages/gen-eval/scripts/check_traceability.py`) over the promoted document and confirm 5/5 operations still cite requirements
  **Dependencies**: 2.1
  **Size**: XS

- [ ] Checkpoint: run tests, review diff, verify scope

## 3. HTTP API route order and conformance (wp-api)

- [x] 3.1 Write `agent-coordinator/tests/test_feature_registry_contract_conformance.py` — load promoted `features.yaml`, resolve refs, drive all five operations through `TestClient(create_coordination_api())` with a fake feature registry service, validate bodies with `Draft202012Validator`; assert every contracted operation is exercised and every success response has a schema; include the `/features/active` not-shadowed case and 401 on `getFeature` without a key. Expect RED on the shadowing case.
  **Spec scenarios**: agent-coordinator.conformance (Every contracted feature operation is exercised, Response shape drift is detected, Untyped success response is rejected), agent-coordinator.fr-http (Active-features route is not shadowed by the feature-id route, Unauthorized single-feature access)
  **Contracts**: openspec/contracts/agent-coordinator/openapi/features.yaml
  **Design decisions**: D5, D6
  **Dependencies**: 2.1
  **Size**: M

- [x] 3.2 Move the `GET /features/active` route above `GET /features/{feature_id}` in `coordination_api.py`
  **Spec scenarios**: agent-coordinator.fr-http (Active-features route is not shadowed by the feature-id route)
  **Design decisions**: D6
  **Dependencies**: 3.1
  **Size**: XS

- [x] 3.3 Fix any further conformance failures 3.1 reports by correcting the endpoint body (not the contract), or — if the contract is wrong against the spec — record the correction in `session-log.md` and update both the promoted file and `contracts/openapi/v1.yaml`
  **Dependencies**: 3.2
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

- [x] 3.4 Write `agent-coordinator/tests/test_feature_registry_http.py` — RED on `/features/active` shadowing before 3.2, GREEN after; guards `GET /features/{feature_id}`, 404 on unknown id, 401 without key
  **Spec scenarios**: agent-coordinator.fr-http (Active-features route is not shadowed by the feature-id route, Unauthorized feature access)
  **Design decisions**: D6
  **Size**: S

- [x] 3.5 Write `agent-coordinator/tests/test_openapi_contract_verification.py` and `openapi_contract_drift_baseline.yaml` — five drift classes between `app.openapi()`/route table and all promoted contracts, ratcheted against a reasoned baseline (27 entries at 2026-10-08); shadowing check proven RED against the unfixed route order
  **Spec scenarios**: agent-coordinator.drift (all four scenarios)
  **Design decisions**: D1
  **Size**: M

## 4. Breaking-change gate (wp-ci)

- [x] 4.1 Write `scripts/contract_gate/tests/test_check_breaking.py` against recorded oasdiff JSON fixtures — unacknowledged break fails with document/operation/rule in output; exact acknowledgement passes and is listed; additive change passes; change-local-only PR reports nothing promoted; stale acknowledgement warns; deleted promoted document fails unless acknowledged
  **Spec scenarios**: agent-coordinator.gate (Unacknowledged breaking change fails the gate, Acknowledged breaking change passes the gate, Additive change passes without acknowledgement, Change-local contracts are not gated)
  **Design decisions**: D4
  **Dependencies**: None
  **Size**: M

- [x] 4.2 Implement `scripts/contract_gate/check_breaking.py` — merge-base discovery, changed-file filter on `openspec/contracts/**/openapi/*.yaml`, `git show` of base versions to temp files, oasdiff invocation with JSON output, acknowledgement collection from touched change dirs, exact-match suppression, exit codes 0/1
  **Dependencies**: 4.1
  **Size**: M

- [x] 4.3 Write a checksum-verification test — a tampered recorded GoModSum, a missing module Sum, a download error, or any setting that disables Go checksum verification fails before oasdiff is installed or run (revised with D4)
  **Spec scenarios**: agent-coordinator.gate (Unverified comparison binary is refused)
  **Design decisions**: D4
  **Dependencies**: None
  **Size**: XS

- [x] 4.4 Implement `scripts/contract_gate/fetch_oasdiff.py` pinning `github.com/oasdiff/oasdiff@v1.33.0` with the recorded GoModSum in `scripts/contract_gate/oasdiff.sum`; refuse on mismatch or disabled verification (revised with D4)
  **Dependencies**: 4.3
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

- [x] 4.5 Add the `contract-breaking-change-gate` job to `.github/workflows/ci.yml` (fetch-depth 0, fetch + verify oasdiff, run the wrapper; < 60 s target)
  **Dependencies**: 4.2, 4.4
  **Size**: S


## 5. Generated bindings and bridge helpers (wp-bridge)

- [x] 5.1 Write `skills/coordination-bridge/scripts/tests/test_generated_bindings.py` — generator writes models + operations for every operation/schema in `features.yaml`; two runs byte-identical; `--check` exits non-zero and names the file and command when stale; no timestamps or absolute paths in output
  **Spec scenarios**: coordination-bridge.bindings (Bindings are regenerated from the contract, Regeneration is byte-identical, Stale bindings fail CI)
  **Contracts**: openspec/contracts/agent-coordinator/openapi/features.yaml
  **Design decisions**: D2
  **Dependencies**: 2.1
  **Size**: S

- [x] 5.2 Write the stdlib-only import test — run `python3 -I` in a subprocess that imports `coordination_bridge` and assert no loaded module outside the stdlib and the bridge package; assert models are imported only under `TYPE_CHECKING`
  **Spec scenarios**: coordination-bridge.bindings (Bindings stay standard-library only)
  **Design decisions**: D3
  **Dependencies**: None
  **Size**: S

- [x] 5.3 Implement `skills/coordination-bridge/scripts/generate_bindings.py` — wraps pinned `datamodel-codegen` (models) and emits the `OPERATIONS` table (operations); `--check` mode; add `datamodel-code-generator==0.83.0` to the `skills` test extra
  **Dependencies**: 5.1
  **Size**: M

- [x] 5.4 Generate and commit `skills/coordination-bridge/scripts/_generated/{__init__,features_models,features_operations}.py`
  **Dependencies**: 5.3
  **Size**: XS

- [ ] Checkpoint: run tests, review diff, verify scope

- [x] 5.5 Write helper tests — all five helpers resolve method/path from `OPERATIONS`; `try_get_feature` URL-encodes the id; unknown feature returns non-`ok` without raising; unreachable coordinator returns `skipped/coordinator_unreachable`; `CAN_FEATURE_REGISTRY` probe reports available when `/features/active` returns 200; add a probe test for the 200 case (the existing 404 fixture at `test_coordination_bridge.py:107` is kept: it deliberately simulates a deployment without the feature registry)
  **Spec scenarios**: coordination-bridge.fr-helpers (all five scenarios)
  **Design decisions**: D3, D6
  **Dependencies**: 5.4
  **Size**: M

- [x] 5.6 Refactor `try_register_feature` and `try_deregister_feature` to resolve from `OPERATIONS`, keeping every keyword parameter and default
  **Dependencies**: 5.5
  **Size**: S

- [x] 5.7 Add `try_get_feature`, `try_list_active_features`, `try_analyze_feature_conflicts` using the uniform envelope
  **Dependencies**: 5.5
  **Size**: S

- [x] 5.8 Document the generator workflow and the five feature helpers in `skills/coordination-bridge/SKILL.md`
  **Dependencies**: 5.6, 5.7
  **Size**: XS

- [x] 5.9 Refresh runtime mirrors with `./install.sh` so `_generated/` reaches `.claude/skills/` and `.agents/skills/`
  **Dependencies**: 5.8
  **Size**: XS

- [ ] Checkpoint: run tests, review diff, verify scope

## 6. Integration and go/no-go (wp-integration)

- [ ] 6.1 Add a `bridge-bindings-drift` step to the existing `test-infra-skills` job in `.github/workflows/ci.yml` running `generate_bindings.py --check` (sequenced here because it needs wp-ci's `ci.yml` edits and wp-bridge's generator)
  **Spec scenarios**: coordination-bridge.bindings (Stale bindings fail CI)
  **Dependencies**: 4.5, 5.4
  **Size**: XS

- [ ] 6.2 Run the full agent-coordinator and skills suites, `openspec validate --strict`, `./install.sh --check`, and both new CI steps locally against this branch
  **Dependencies**: 2.3, 3.3, 5.9, 6.1
  **Size**: S

- [ ] 6.3 Replay the breaking-change wrapper over the last 20 commits that modified `openspec/contracts/**/openapi/*.yaml`, recording false positives
  **Design decisions**: D7
  **Dependencies**: 6.2
  **Size**: S

- [ ] 6.4 Write `decision.md` scoring the pilot against the NFR table and D7 criteria, with a Go / No-go verdict and the follow-up changes it implies (bridge domains, `http_proxy.py` via `openapi-python-client`, Forge re-entry criteria)
  **Design decisions**: D7
  **Dependencies**: 6.3
  **Size**: S
