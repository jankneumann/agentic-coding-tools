# Change: restructure-openbao-per-agent-secrets

## Why

OpenBao currently projects every agent onto one shared secret path and policy, while three
independent clients reuse a global `BAO_SECRET_ID` and silently fall back when resolution
fails. A compromised agent can therefore cross principal and vendor boundaries, rotation is
not observed without restart, and dispatch-governance dg-08 has no least-privilege service
principal with which to retrieve vendor credentials.

pca-01 has already made `agents.yaml` canonical for identity and trust. This change applies
the same projection rule to credentials: each declared principal receives one deterministic
AppRole, policy, secret namespace, and single-use bootstrap; vendor access is explicit in the
registry; and configured OpenBao failures are visible authorization failures rather than a
static-key bypass.

## What Changes

- Add an explicit `vendor_credentials` list to each keyed `agents.yaml` entry and derive all
  agent AppRoles, policies, and secret paths from the canonical registry principal.
- Preserve canonical SPIFFE IDs for audit and authorization while deterministically encoding
  Bao-safe role and policy names; reject collisions and non-canonical overrides.
- Partition KV-v2 data into `secret/agents/<name>` and `secret/vendors/<vendor>`, with policies
  targeting the actual KV-v2 API paths under `secret/data/...`.
- Provision `spiffe://coordinator.rotkohl.ai/service/egress-gateway` as a first-class service
  principal that can read vendor paths and cannot read any agent path. This is the complete
  pca-02 dependency delivered to dg-08; iron-proxy and per-dispatch proxy-token authorization
  remain out of scope.
- Generate a unique AppRole SecretID for each principal with one permitted use, request a
  short-lived response-wrapped result, and atomically write one mode-0600 bootstrap bundle per
  principal beneath an explicit mode-0700 output directory. Plain SecretIDs and wrapping
  tokens are never printed or committed. Receivers validate the exact creation path before
  unwrapping, following OpenBao's response-wrapping guidance:
  https://openbao.org/docs/concepts/response-wrapping/
- Introduce narrow typed OpenBao adapters so provisioning, coordinator identity reload, and
  dispatch credential lookup share names, paths, and a stable error taxonomy without passing
  raw `hvac` response dictionaries through domain code. The locked client is `hvac==2.4.0`;
  KV-v2 calls use its explicit `client.secrets.kv.v2` surface:
  https://python-hvac.org/en/stable/usage/secrets_engines/kv.html
- Load API-key identities into an immutable snapshot and atomically hot-reload it every 30
  seconds. A failed refresh retains the last-known-good snapshot for at most 120 seconds,
  emits a sanitized audit event, marks readiness degraded, and then denies new authentication
  until a valid snapshot is installed.
- Reconcile retired agent roles, policies, and paths deterministically and audit every
  mutation; unrelated dynamic-database and coordinator-internal secrets remain unchanged.
- Add a pinned dev-mode OpenBao integration matrix proving own-path allow, cross-agent and
  unrelated-vendor denial, gateway vendor-only access, single-use wrapping, rotation without
  restart, and fail-loud audited errors.
- **BREAKING**: remove shared `BAO_SECRET_ID`, shared `secret/coordinator` agent access,
  manually authored `openbao_role_id` identity overrides, and configured-agent fallback to
  `.secrets.yaml` or ambient vendor-key environment variables. Static X-API-Key HTTP
  authentication remains until pca-03, but its values live only in per-agent OpenBao paths.
- Rollback is release-level, not dual-read: restore the prior release and its backed-up
  `secret/coordinator` data. The migration provides dry-run output and does not delete the old
  path until the operator explicitly confirms cutover.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Security isolation | Unauthorized reads in the live principal/path matrix | 0 successful cross-agent, unrelated-vendor, or gateway-to-agent reads | Live OpenBao integration |
| Bootstrap confidentiality | Plain SecretIDs or wrapping tokens emitted to stdout, logs, git, or files broader than 0600 | 0 disclosures; output directory is 0700 and bundles are 0600 | Unit tests, secret scan, live integration |
| Rotation convergence | Time from a valid per-agent key update to an atomically installed identity snapshot | <= 60 seconds under the 30-second default refresh cadence | Coordinator integration |
| Bounded degradation | Age of last-known-good identities accepted after refresh failure | <= 120 seconds, followed by denial of new authentication | Clock-controlled coordinator tests |
| Operability | Registry agents lacking exactly one role, policy, agent path, and explicit vendor scope | 0; dry-run exits non-zero on ambiguity or collision | Projection invariant and CLI tests |
| Reproducibility | Live OpenBao test image references using a mutable tag | 0 (`latest` forbidden for the test fixture) | CI configuration test |

## Approaches Considered

### Approach 1: Contract-first principal projection with typed adapters

Define one principal/credential topology contract, project it from `agents.yaml`, and place
narrow typed adapters between domain services and `hvac`. Provisioning, coordinator reload,
and dispatch lookup remain separate runtime components but consume the same names, paths,
error taxonomy, and bootstrap bundle schema.

Pros:
- Removes the three clients' current path and fallback disagreement without coupling their
  lifecycles.
- Gives dg-08 a stable non-proxy-specific service-principal contract.
- Supports unit fakes and a real OpenBao conformance suite at the adapter boundary.
- Keeps pca-03 session tokens and pca-04 dispatch posture outside this change.

Cons:
- Introduces a contract and adapter layer before behavior changes.
- Requires coordinated migration across skills and coordinator packages.

Effort: M

### Approach 2: Patch each existing OpenBao client in place

Teach `bao_seed.py`, `agents_config.py`, and `api_key_resolver.py` the new topology separately,
retaining their independent `hvac` calls and caches.

Pros:
- Smallest initial code movement.
- Lets each component preserve its current control flow.

Cons:
- Keeps three definitions of paths, wrapping behavior, errors, and fallback policy.
- Makes drift—the motivating defect—likely to recur.
- Requires duplicating fakes and live conformance assertions.

Effort: M

### Approach 3: OpenBao Agent auto-auth sidecars

Move AppRole unwrap, login, caching, and renewal into OpenBao Agent processes and have each
consumer read a local sink or proxy endpoint. OpenBao documents creation-path validation for
wrapped SecretIDs through `secret_id_response_wrapping_path`:
https://openbao.org/docs/agent-and-proxy/autoauth/methods/approle/

Pros:
- Delegates token lifecycle and wrapped-secret handling to OpenBao's own runtime.
- Closely matches a future container-orchestrated deployment.

Cons:
- Adds sidecar/process supervision to local CLI and coordinator workflows now.
- Does not remove the need for canonical registry projection and policy reconciliation.
- Is disproportionate on the current single-host developer topology and complicates tests.

Effort: L

### Recommended

Approach 1. It directly fixes definition drift while keeping runtime lifecycles independent,
provides dg-08 a narrow service-principal boundary, and remains testable with both typed fakes
and a pinned real server. Approach 2 is initially smaller but preserves the root cause;
Approach 3 is operationally stronger for a container fleet but adds infrastructure that the
current topology cannot justify.

### Selected Approach

Pending Gate 1 direction approval.

## Impact

Architecture layers:
- Trust: principal naming, AppRole/SecretID lifecycle, KV policy boundaries, identity reload.
- Coordination: atomic API-key identity snapshots, readiness, and audit events.
- Execution: dispatch-side credential lookup contract only; credential injection remains
  pca-04.
- Governance: registry projection invariant and audited reconciliation.

Affected spec capabilities and required deltas:
- `agent-identity` -> `specs/agent-identity/spec.md`: per-principal projection, SPIFFE/Bao
  naming, explicit vendor scope, removal of shared bootstrap/fallback.
- `configuration` -> `specs/configuration/spec.md`: KV taxonomy, bootstrap delivery,
  migration/rollback, required OpenBao configuration.
- `agent-coordinator` -> `specs/agent-coordinator/spec.md`: atomic identity hot reload,
  bounded last-known-good behavior, readiness, and audit contract.

Major code and documentation touchpoints:
- `agent-coordinator/agents.yaml` and its schema/parser.
- `skills/bao-vault/scripts/bao_seed.py` and tests.
- New shared principal/topology/bootstrap contracts and typed OpenBao adapter surfaces.
- `agent-coordinator/src/config.py`, `agents_config.py`, `coordination_api.py`, and audit
  integration; `profile_loader.py` only where shared topology currently leaks into identity
  loading, without changing dynamic database credentials.
- `skills/parallel-infrastructure/scripts/api_key_resolver.py` and tests.
- Pinned live OpenBao CI/Compose fixture and security integration tests.
- `docs/openbao-secret-management.md` and deployment/migration guidance.

Known coordination conflicts:
- `add-sandboxed-harness-execution` must consume this credential client/topology rather than
  introduce a parallel broker or retain configured-agent environment fallback.
- `add-coordinator-llm-gateway` must consume `secret/vendors/<vendor>` rather than invent a
  second provider-key path.
- Concurrent agent-roster changes must pass the new projection invariant.
