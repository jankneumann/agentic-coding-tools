# Tasks: add-sandboxed-harness-execution

> Phase numbering follows the proposal. Phase 0 items owned by dispatch-governance
> (dg-02, dg-03, dg-07) are external dependencies, not tasks here; the one Phase 0
> amendment this change owns is the vocabulary widening (group 1). Group 2+ tasks
> that touch `review_dispatcher.py` MUST NOT run concurrently with
> `build-structured-vendor-result-channel` (same methods — ordering, not merge).

## 1. Isolation vocabulary (Phase 0 amendment, coordinate with pin-isolation-contract)

- [ ] 1.1 Write tests for the two-axis closed vocabulary — `container` accepted;
  `location` carried; unknown values raise structured errors naming field+value;
  effective isolation resolves per `(agent_type, dispatch_mode)`
  **Spec scenarios**: agent-archetypes (both scenarios of the MODIFIED requirement)
  **Dependencies**: None
  **Files**: agent-coordinator/tests/test_agents_config_isolation.py

- [ ] 1.2 Widen `VALID_ISOLATION_MODES` with `container`, add `VALID_LOCATIONS`,
  add `resolve_effective_isolation(agent_type, dispatch_mode)` beside
  `get_agent_isolation()`; JSON schema enums derive from the constants
  **Design decisions**: D4 (vocabulary widened at pin time)
  **Dependencies**: 1.1
  **Files**: agent-coordinator/src/agents_config.py

## 2. Execution backend seam (Phase 1)

- [ ] 2.1 Write tests for `DispatchSpec`, the `ExecutionBackend` protocol, and the
  registry — selection is a pure function of `(location, isolation)`; unknown pair
  refuses with structured error + audit payload, never falls back to `(local, none)`
  **Spec scenarios**: vendor-dispatch.1 (legacy byte-identical; unknown-pair refusal)
  **Contracts**: contracts/schemas/dispatch-spec.schema.json
  **Design decisions**: D1 (seam shape)
  **Dependencies**: None
  **Files**: skills/tests/shared/test_execution_backends.py

- [ ] 2.2 Implement `skills/shared/execution_backends/` — `base.py`
  (DispatchSpec, protocol), `registry.py` (SUPPORTED_BACKENDS-style), and
  `local_process.py` delegating to the current subprocess path unchanged
  **Dependencies**: 2.1
  **Files**: skills/shared/execution_backends/__init__.py,
  skills/shared/execution_backends/base.py,
  skills/shared/execution_backends/registry.py,
  skills/shared/execution_backends/local_process.py

- [ ] 2.3 Write integration tests: `CliVendorAdapter` dispatches through the seam;
  `(local, none|worktree)` behavior byte-identical against recorded argv/env/cwd
  **Spec scenarios**: vendor-dispatch.1 (legacy byte-identical)
  **Dependencies**: 2.2
  **Files**: skills/tests/parallel-infrastructure/test_review_dispatcher_backends.py

- [ ] 2.4 Route `CliVendorAdapter.dispatch()`/`dispatch_async()` through backend
  selection (after `build_command()`); attach the routing decision to the dispatch
  context
  **Dependencies**: 2.3; external: build-structured-vendor-result-channel (ordering)
  **Files**: skills/parallel-infrastructure/scripts/review_dispatcher.py

- [ ] 2.5 Register the `(local, sandbox)` backend wrapping argv via
  `sandbox_profile.wrap_command()` (consumes dg-07's renderer; degradation
  semantics stay dg-07's)
  **Dependencies**: 2.2; external: add-dispatch-sandbox-enforcement (dg-07)
  **Files**: skills/shared/execution_backends/local_sandbox.py

## 3. Credential brokering (Phase 2)

- [ ] 3.1 Write tests for explicit child-env construction — only allowlisted vars
  present; SSH/cloud/unrelated-key vars absent; rollback flag restores inheritance
  with warning + audit event emission
  **Spec scenarios**: vendor-dispatch.2 (both scenarios)
  **Dependencies**: None
  **Files**: skills/tests/shared/test_dispatch_env.py

- [ ] 3.2 Implement `dispatch_env.py` (allowlist builder, `DISPATCH_ENV_ALLOWLIST`
  flag, audit emission) and wire it into every registered backend
  **Design decisions**: D7 (flags, loud degradation)
  **Dependencies**: 3.1, 2.2
  **Files**: skills/shared/dispatch_env.py,
  skills/shared/execution_backends/local_process.py,
  skills/shared/execution_backends/local_sandbox.py

- [ ] 3.3 Write tests for the credential broker — leaf-credential invariant (no
  BAO address/role_id/secret_id/wrapping token in assembled workspace material);
  specs requesting mint authority refused; hardening verification (dev-mode /
  plaintext / no-audit ⇒ remote refused, local served)
  **Spec scenarios**: credential-brokering.1 (both), credential-brokering.5 (both)
  **Dependencies**: None
  **Files**: skills/tests/shared/test_credential_broker.py

- [ ] 3.4 Implement `credential_broker.py` — broker AppRole auth (reuse
  `ApiKeyResolver` OpenBao client), hardening verification, leaf-material assembly
  consumed by backends at workspace creation
  **Design decisions**: D2 (push-model secrets)
  **Dependencies**: 3.3
  **Files**: skills/shared/credential_broker.py

- [ ] 3.5 Write tests for GitHub App token minting — repo-scoped ~1h installation
  token; expired token not self-renewable from workspace material
  **Spec scenarios**: credential-brokering.3 (both scenarios)
  **Dependencies**: None
  **Files**: skills/tests/shared/test_github_app_tokens.py

- [ ] 3.6 Implement `github_app_tokens.py` — mint installation tokens from the
  App private key read via the broker's KV path
  **Dependencies**: 3.4, 3.5
  **Files**: skills/shared/github_app_tokens.py

- [ ] 3.7 Write tests for inference credential provisioning — gateway-capable CLI
  receives virtual key + gateway URL and no raw vendor key; incapable CLI receives
  capped per-lane key with audit event recording the bypass
  **Spec scenarios**: credential-brokering.4 (both scenarios)
  **Contracts**: add-coordinator-llm-gateway contracts/openapi/v1.yaml
  (`/llm/keys/issue`, consumed not redefined)
  **Dependencies**: None
  **Files**: skills/tests/shared/test_inference_credentials.py

- [ ] 3.8 Implement inference credential provisioning in the broker — per-vendor
  base-URL capability table in `agents.yaml` (`gateway_base_url_env` field),
  gateway key issuance call, per-lane fallback
  **Design decisions**: D3 (gateway virtual keys)
  **Dependencies**: 3.4, 3.7; external: add-coordinator-llm-gateway
  **Files**: skills/shared/credential_broker.py, agent-coordinator/agents.yaml

- [ ] 3.9 Write coordinator tests for per-dispatch identities — distinct identity
  per dispatch; revocation rejects that identity only; revoked dispatch marked
  failed in ledger
  **Spec scenarios**: agent-coordinator.2 (both scenarios)
  **Contracts**: contracts/openapi/v1.yaml (`/dispatch/identities`)
  **Dependencies**: None
  **Files**: agent-coordinator/tests/test_dispatch_identities.py

- [ ] 3.10 Implement dispatch-identity issue/revoke endpoints and wire into
  `COORDINATION_API_KEY_IDENTITIES` resolution
  **Dependencies**: 3.9
  **Files**: agent-coordinator/src/coordination_api.py,
  agent-coordinator/src/agents_config.py

- [ ] 3.11 Write coordinator tests for network-policy export — rendering derives
  from export; unreachable export falls back narrower-never-wider with audit
  **Spec scenarios**: agent-coordinator.1 (both scenarios)
  **Contracts**: contracts/openapi/v1.yaml (`/policies/network/export`)
  **Dependencies**: None
  **Files**: agent-coordinator/tests/test_network_policy_export.py

- [ ] 3.12 Implement the export path in `network_policies.py` + API route
  **Dependencies**: 3.11
  **Files**: agent-coordinator/src/network_policies.py,
  agent-coordinator/src/coordination_api.py

- [ ] 3.13 Document the OpenBao hardening runbook (persistence, TLS, audit
  device, broker AppRole policy, CIDR binding) and the broker's verification
  behavior
  **Dependencies**: 3.4
  **Files**: docs/openbao-secret-management.md

## 4. Cloud sandbox backend (Phase 3; gated on the spike)

- [ ] 4.1 Run the provider spike and write the decision report — egress-control
  granularity (domain allowlist expressible?), snapshot build with CLI roster,
  create/exec/teardown latency, brokered-credential injection end-to-end; Daytona
  primary, E2B compared (shared with sentinel usage)
  **Design decisions**: D6 (egress provider-first)
  **Dependencies**: None (parallel with group 3)
  **Files**: docs/proposals/cloud-sandbox-provider-spike.md

- [ ] 4.2 Write tests for the cloud backend contract — provisioning sets
  `AGENT_EXECUTION_ENV=cloud` (worktree short-circuit composes); config naming a
  tailnet address/credential fails validation before sandbox creation; ledger
  unreachable parks the dispatch; wall-clock bound produces timeout terminal state
  **Spec scenarios**: cloud-sandbox-execution.1 (rejection),
  cloud-sandbox-execution.2 (both), cloud-sandbox-execution.5 (both),
  vendor-dispatch.3 (both)
  **Contracts**: contracts/schemas/dispatch-spec.schema.json
  **Dependencies**: 2.2
  **Files**: skills/tests/shared/test_cloud_sandbox_backend.py

- [ ] 4.3 Implement `cloud_sandbox.py` (provider adapter behind the backend
  protocol): create-from-snapshot, shallow-clone at branch, broker-material
  injection, exec, auto-stop bound, teardown; ledger submit/complete integration
  **Design decisions**: D1, D5 (ledger-based remote state)
  **Dependencies**: 4.1, 4.2, 3.4; external: build-structured-vendor-result-channel
  **Files**: skills/shared/execution_backends/cloud_sandbox.py

- [ ] 4.4 Implement egress rendering for the chosen provider in the dg-07 renderer
  seam (`render_<provider>_egress()` from the exported policy; adjacent-proxy
  fallback per spike outcome)
  **Spec scenarios**: cloud-sandbox-execution.3 (both scenarios)
  **Dependencies**: 4.1, 3.12; external: add-dispatch-sandbox-enforcement (dg-07)
  **Files**: skills/shared/sandbox_profile.py

- [ ] 4.5 Write tests for the `min_isolation` gate coupling — sufficient isolation
  honors `auto` and audits the authorizing posture; insufficient degrades to
  `block` with audit and parks the loop
  **Spec scenarios**: cloud-sandbox-execution.4 (both scenarios)
  **Dependencies**: None; external: build-approval-gate-service (interviewer
  abstraction) — if unlanded, target its planned module path
  **Files**: skills/tests/shared/test_approval_gate_isolation.py

- [ ] 4.6 Implement `min_isolation` in the trust-posture schema and the approval
  gate check reading the dispatch context's routing decision
  **Dependencies**: 4.5
  **Files**: skills/shared/approval_gate.py, TRUST_POSTURE.template.md

- [ ] 4.7 Add routing rules for the cloud lane to `routing.yaml` (interactivity →
  local; local-secret needs → local sandbox; high parallelism/long duration →
  cloud; untrusted-input phases → cloud with tightest egress) and pilot on review
  fan-out
  **Dependencies**: 4.3, 4.4; external: implement-the-task-router (dg-04)
  **Files**: agent-coordinator/routing.yaml

## 5. Documentation

- [ ] 5.1 Update guides — worktree-management (posture), cloud-vs-local-execution
  (cloud sandbox as a provisioned environment), workflow guide (backend lanes);
  cross-link the design source doc
  **Dependencies**: 4.3
  **Files**: docs/guides/worktree-management.md, docs/cloud-vs-local-execution.md,
  docs/guides/workflow.md
