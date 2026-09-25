# Tasks: registry-derived OpenBao principals

Every test task starts RED against the current implementation. Size is the
focused agent-session budget (XS/S/M); no task is L or XL. The contract paths
below are relative to this change directory. Checkpoints run the relevant
suite, inspect the cumulative diff, and verify package scope.

## 1. Freeze projection and adapter contracts (`wp-projection`)

- [x] 1.1 (S) Test principal topology projection.
  **Spec scenarios**: AI-01, AI-02, AI-07, AI-08, AI-09, AI-11, AI-12, AI-13, AI-14, AI-16, AI-17; CFG-03, CFG-16, CFG-20.
  **Contracts**: `contracts/principal-topology.schema.json`, `contracts/agent-secret.schema.json`, `contracts/vendor-secret.schema.json`.
  **Design decisions**: D1.
  **Dependencies**: `wp-contracts`.
- [x] 1.2 (M) Implement canonical registry principal projection.
  Add the top-level `credential_vendors` catalog and per-agent
  `vendor_credentials`; remove `openbao_role_id` overrides from the roster.
  Emit `principal_id` and `vendor_credentials` in `get_dispatch_configs()`;
  update the endpoint fixture for keyed and keyless agents.
  **Dependencies**: 1.1.
- [x] 1.3 (S) Test typed OpenBao adapter behavior.
  **Spec scenarios**: CFG-01, CFG-03, CFG-04, CFG-05, CFG-06, CFG-07, CFG-16, CFG-17, CFG-20, CFG-23, CFG-24; COORD-07.
  Cover recovery from a fresh wrapped bundle after cached-token revocation or expiry, and reject reuse of the consumed bundle.
  **Contracts**: `contracts/bootstrap-bundle.schema.json`, `contracts/session-cache.schema.json`, `contracts/openbao-event.schema.json`.
  **Design decisions**: D2, D3.
  Include a fake for server-side wrapping lookup and reject a forged bundle path before unwrap.
  **Dependencies**: `wp-contracts`.
- [x] 1.4 (M) Implement shared OpenBao adapter boundary.
  **Dependencies**: 1.3.
- [x] 1.5 (S) Test the shared package in coordinator container imports.
  **Spec scenarios**: CFG-03, COORD-06.
  **Design decisions**: D2, D6.
  **Dependencies**: 1.4.
- [x] 1.6 (S) Bundle the shared package in the coordinator Docker build.
  Update the Dockerfile builder COPY plus the CI container smoke module list.
  **Dependencies**: 1.5.
- [x] Checkpoint: run projection, adapter, plus container import checks; review diff, verify scope.

## 2. Provision and migrate (`wp-seeding`)

- [x] 2.1 (S) Test explicit migration-map preflight.
  **Spec scenarios**: AI-02, AI-07, AI-09, AI-10; CFG-08, CFG-12, CFG-13, CFG-18.
  Reject migration-map agent keys that disagree with registry `api_key` placeholders.
  **Contracts**: `contracts/principal-topology.schema.json`, `contracts/migration-map.schema.json`.
  **Design decisions**: D1, D3, D6.
  **Dependencies**: 1.2.
- [x] 2.2 (M) Implement mapped per-principal provisioning.
  **Dependencies**: 2.1, 1.4.
- [x] 2.3 (S) Test protected bootstrap delivery.
  **Spec scenarios**: CFG-05, CFG-06, CFG-09, CFG-10, CFG-11, CFG-23.
  **Contracts**: `contracts/bootstrap-bundle.schema.json`, `contracts/openbao-event.schema.json`.
  **Design decisions**: D3.
  **Dependencies**: 1.4.
- [x] 2.4 (M) Implement audited bootstrap reconciliation.
  **Dependencies**: 2.2, 2.3.
- [x] Checkpoint: run seeder tests, review diff, verify scope.

## 3. Reload coordinator identities (`wp-coordinator`)

- [x] 3.1 (S) Test complete identity snapshot construction.
  **Spec scenarios**: AI-03, AI-04, AI-05; CFG-02, CFG-04; COORD-02, COORD-06, COORD-09.
  **Contracts**: `contracts/principal-topology.schema.json`, `contracts/openbao-event.schema.json`.
  **Design decisions**: D2, D4.
  **Dependencies**: 1.4.
- [x] 3.2 (M) Implement identity-reader snapshot loading.
  **Dependencies**: 3.1.
- [x] 3.3 (S) Test bounded identity reload lifecycle.
  **Spec scenarios**: COORD-01, COORD-03, COORD-04, COORD-05.
  **Contracts**: `contracts/openbao-event.schema.json`, `contracts/openapi/v1.yaml`.
  **Design decisions**: D4.
  **Dependencies**: 3.2.
- [x] 3.4 (M) Implement atomic identity reload lifecycle.
  **Dependencies**: 3.3.
- [x] Checkpoint: run coordinator identity/API tests, review diff, verify scope.
- [x] 3.5 (S) Test component readiness response.
  **Spec scenarios**: COORD-06, COORD-07, COORD-08, COORD-09, COORD-10.
  **Contracts**: `contracts/openbao-event.schema.json`, `contracts/openapi/v1.yaml`.
  **Design decisions**: D4, D5.
  **Dependencies**: 3.4.
- [x] 3.6 (S) Wire identity readiness into HTTP authentication.
  **Dependencies**: 3.5.
- [x] 3.7 (S) Test isolated coordinator-internal Bao loading.
  **Spec scenarios**: CFG-19, CFG-21, CFG-22, CFG-26, CFG-27; CFG-02.
  **Design decisions**: D5.
  **Dependencies**: 1.4.
- [x] 3.8 (S) Rename internal Bao credential inputs in `profile_loader.py` and `config.py`;
  retain `OpenBaoConfig` methods and update `test_openbao_config.py`.
  **Dependencies**: 3.7.
- [x] Checkpoint: run coordinator profile tests, review diff, verify scope.

## 4. Scope dispatch lookup (`wp-dispatch`)

- [ ] 4.1 (S) Test scoped dispatch credential lookup.
  **Spec scenarios**: AI-01, AI-08, AI-16, AI-17; CFG-01, CFG-02, CFG-03, CFG-04, CFG-17, CFG-25.
  **Contracts**: `contracts/principal-topology.schema.json`, `contracts/session-cache.schema.json`, `contracts/openbao-event.schema.json`.
  **Design decisions**: D1, D2.
  **Dependencies**: 1.4.
- [ ] 4.2 (M) Update dispatch resolver plus both `review_dispatcher.py` call sites; consume
  `principal_id` and `vendor_credentials` from API and direct registry shapes.
  **Dependencies**: 4.1.
- [ ] Checkpoint: run dispatch resolver tests, review diff, verify scope.

## 5. Live conformance and operator cutover (`wp-integration`)

- [ ] 5.1 (S) Pin the live OpenBao fixture.
  Add a floating-tag guard and a dedicated runner that fails when the server is
  unavailable or zero tests run; it must not inherit PostgREST skip behavior.
  **Spec scenarios**: CFG-15.
  **Design decisions**: D6.
  **Dependencies**: 2.4, 3.6, 4.2.
- [ ] 5.2 (M) Test live principal policy isolation.
  **Spec scenarios**: AI-06, AI-08, AI-10, AI-11, AI-12, AI-13, AI-14; CFG-14.
  **Contracts**: `contracts/principal-topology.schema.json`, `contracts/agent-secret.schema.json`, `contracts/vendor-secret.schema.json`.
  **Design decisions**: D1, D3, D6.
  **Dependencies**: 5.1.
- [ ] 5.3 (M) Test live bootstrap lifecycle failures, including server-side wrapping lookup.
  **Spec scenarios**: CFG-05, CFG-06, CFG-07, CFG-14, CFG-16, CFG-17, CFG-18, CFG-20, CFG-23, CFG-24; COORD-07.
  **Contracts**: `contracts/bootstrap-bundle.schema.json`, `contracts/session-cache.schema.json`, `contracts/migration-map.schema.json`, `contracts/openbao-event.schema.json`.
  **Design decisions**: D2, D3, D5, D6.
  **Dependencies**: 5.2.
- [ ] Checkpoint: run live policy plus bootstrap matrix, review diff, verify scope.
- [ ] 5.4 (S) Test live coordinator key rotation.
  **Spec scenarios**: COORD-01, COORD-02, COORD-03, COORD-05, COORD-09, COORD-10; CFG-14.
  **Design decisions**: D4, D6.
  **Dependencies**: 5.3.
- [ ] 5.5 (S) Document OpenBao cutover procedure.
  Update `docs/openbao-secret-management.md`, coordinator setup examples, and
  `agent-coordinator/CLAUDE.md` and `.secrets.yaml.example`; stage vendor keys
  currently only in deployment environment into the protected flat secrets file
  before preflight, so the old static-identity override is no
  longer presented as an OpenBao-mode rollback lever.
  **Spec scenarios**: CFG-07, CFG-08, CFG-09, CFG-12, CFG-13, CFG-17, CFG-18, CFG-19.
  **Design decisions**: D3, D5, D6.
  **Dependencies**: 5.3.
- [ ] 5.6 (S) Test the Langfuse internal Bao helper.
  **Spec scenarios**: CFG-19.
  **Design decisions**: D5.
  **Dependencies**: 3.8.
- [ ] Checkpoint: run rotation plus internal helper tests, review diff, verify scope.
- [ ] 5.7 (S) Migrate `langfuse_env.sh` to isolated internal credential inputs.
  **Dependencies**: 5.6.
- [ ] 5.8 (S) Run final validation gates.
  **Spec scenarios**: AI-01..14, AI-16..17, CFG-01..27, COORD-01..10.
  **Design decisions**: D6.
  **Dependencies**: 5.4, 5.5, 5.7.

The implementation may use additional narrow test files, but every listed
scenario must have an executable assertion. No pca-03 session-token or
dg-08/pca-04 proxy-token implementation belongs in these tasks.
