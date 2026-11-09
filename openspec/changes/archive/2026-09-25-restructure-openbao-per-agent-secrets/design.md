# Design: registry-derived OpenBao principals

## Context

`agents.yaml` is the canonical agent registry after pca-01. Today `bao_seed.py`,
`agents_config.py`, and `api_key_resolver.py` independently select a shared Bao
path and reuse `BAO_SECRET_ID`; both runtime readers can fall back after a Bao
failure. The selected Approach 1 gives them one contract and narrow typed
adapters while retaining their separate lifecycles.

## Decisions

### D1 — One deterministic topology projection

A pure projection accepts a validated registry snapshot and returns typed
principal records. Every keyed agent has its canonical SPIFFE ID, a Bao-safe
role/policy name, exactly one `secret/agents/<name>` KV-v2 path, and an explicit
`vendor_credentials` set. A top-level `credential_vendors` catalog in the
registry defines valid vendor IDs independently of policy/catalog vendor fields.
The projection rejects missing or duplicate names,
unknown vendors, collisions after encoding, and hand-authored
`openbao_role_id`. Name encoding is deterministic, with the canonical SPIFFE ID
recorded for audit and diagnostics. The topology schema is
`contracts/principal-topology.schema.json`. A versioned, explicit migration
mapping lists each keyed agent and credential vendor with one source key in
the flat secrets input; it also lists intentionally retained internal keys.
Every source key must be accounted for exactly once. The mapping, rather than
`policy_vendor` or CLI fields, defines the allowed vendor vocabulary and
prevents ambiguous copying. Its format is `contracts/migration-map.schema.json`.
No secret values appear in this mapping. The seeder accepts it through an
explicit `--migration-map PATH` argument; its vendor keys must equal the
registry catalog. A mount-relative logical path such as `agents/<name>` is
passed to `hvac`, while `<mount>/data/agents/<name>` is the policy API path.
Both agent and vendor KV-v2 data payloads contain exactly one nonempty string
`api_key` field, validated by `contracts/agent-secret.schema.json` and
`contracts/vendor-secret.schema.json`.

Two service records are projected beside agents. The egress gateway has the
canonical ID `spiffe://coordinator.rotkohl.ai/service/egress-gateway` and read
scope on the configured `secret/data/vendors/<vendor>` paths only. A coordinator
identity reader has its own service ID and read scope on declared
`secret/data/agents/<name>` paths only, allowing snapshot
reload without borrowing agent bootstrap material. Both services are denied
the other namespace. The latter is an explicit Gate 2 assumption needed to
implement the approved reload behavior. Neither service's broad path read
scope is a per-dispatch vendor authorization grant; dg-08/pca-04 own that.
The gateway's exact path set is the sorted union of agents' explicit vendor
lists. The identity reader's exact path set is all keyed agent documents.

### D2 — Typed adapter boundary

Place a small shared package in the repository where coordinator and skill
scripts can import it without importing one another. Its public types cover
principal/path projection, bootstrap metadata, KV-v2 reads, AppRole login,
wrapping lookup/unwrap, and classified errors. The `hvac==2.4.0` adapter is the
only layer that inspects raw API dictionaries. It uses the explicit
`client.secrets.kv.v2` surface and maps unavailable, permission denied,
missing secret, malformed response, expired wrap, and configuration errors to
stable typed failures. Callers log only class, principal ID, path category,
and correlation ID; no token, SecretID, API key, or response body.

`BAO_MOUNT_PATH` remains configurable. Projection validates a mount segment
and derives every KV-v2 logical/API policy path from it; the default is
`secret`. Preflight fails if the configured mount is absent or is not KV-v2.

Configuration is explicit: absence of Bao configuration may use the existing
development/static path; once Bao is configured for a registry agent, missing
bootstrap, auth, read, or parse failure is an authorization failure. Dispatch
lookup accepts a canonical principal and requested vendor; it refuses vendors
outside `vendor_credentials` before any read. It does not introduce pca-04
credential injection or proxy token issuance.
The public dispatch signature is `resolve(principal_id, vendor_id)`; the caller
derives `principal_id` from the registry entry, not a role-name override or
SDK environment variable. A protected `BAO_BOOTSTRAP_DIR` is required in
configured mode, and the adapter selects a principal-specific bundle/session
filename from the canonical projection. Missing or unreadable files fail
closed. Deployment exposes only that principal's files to its consumer.
The dispatch-config producer emits the canonical `principal_id` and explicit
`vendor_credentials` alongside existing transport fields; both API and direct
registry loading consume that shape. A keyless endpoint agent has a null
principal ID and an empty credential scope. In pca-02, configured Bao credential
resolution applies to SDK and OpenAI-compatible dispatch tiers. CLI vendor
processes retain their existing ambient environment until pca-04 implements
credential injection; they never invoke the Bao resolver in this phase.

### D3 — Provisioning, wrapping, and reconciliation

The seeder computes a dry-run reconciliation plan before mutation. It validates
the entire projection, presents names and actions without secret values, and
requires an explicit cutover flag for retiring legacy agent access to
`secret/coordinator`. Apply creates or updates only managed policies, AppRoles, and namespaced
KV-v2 data, and audits each action. Policies grant exact `secret/data/agents/<name>`
or explicitly listed `secret/data/vendors/<vendor>` read paths; metadata or
listing privileges are added only if a concrete adapter operation needs them.
The identity-reader and gateway policies are separate. The seeder never touches
the dynamic database engine or unrelated coordinator secrets.

For each principal, seeding issues a distinct SecretID with one use and obtains
a short-lived response-wrapped creation result. It writes a bundle matching
`contracts/bootstrap-bundle.schema.json` under an explicitly selected 0700
directory by creating a 0600 temporary file, syncing, and atomically renaming.
It refuses unsafe directories and symlink destinations. `BAO_BOOTSTRAP_DIR` names the protected root; the validated projected role name determines the bundle, session, and lock filenames. Each consumer receives its principal ID through deployment configuration. The root is not mounted into an agent child process; provisioner and dispatch broker run as trusted owners. The receiver performs
`POST /v1/sys/wrapping/lookup` using the wrapping token through the hvac adapter,
checks the server-returned creation path against the exact expected endpoint,
unwraps once, and
logs in. The AppRole issues a short-period renewable token with no explicit
maximum TTL; active services renew within each period. After expiry, revocation,
or failed renewal, the principal needs a newly issued protected bundle.
This follows [OpenBao's periodic token semantics](https://openbao.org/docs/concepts/tokens/);
the live matrix must prove renewal beyond the ordinary role max-TTL window.
The one-use SecretID is never treated as a renewable login credential.
For short-lived processes, the adapter stores the issued renewable client
token in a separate protected 0600 session file beneath the same 0700 directory.
An interprocess lock serializes token read/renew/replace and the first unwrap;
the second process reuses the valid token, not the consumed bundle. Atomic
replacement and symlink refusal apply to this cache too. A token at maximum
lease expiry, revocation, or failed renewal invalidates the cache and requires an authorized fresh
wrapped bundle. The cache records the consumed wrapping-token SHA-256 digest.
Under the lock, the adapter checks cached-token validity against OpenBao; it
compares a candidate bundle digest before any new unwrap and refuses the same
consumed bundle. Tests cover sequential and simultaneous dispatch processes.
The cache format is `contracts/session-cache.schema.json`.

Retired managed agents and pre-migration role aliases are identified through
managed state plus the migration map, then removed in deterministic order
after a dry-run preview. Deletion is limited to owned roles, policies, and
agent paths and requires cutover confirmation. The `secret/coordinator` data
path remains for coordinator-internal settings; cutover removes agent access
and the old shared `coordinator-read` policy only after the internal loader has
its separate policy. Previous release plus a backup of `secret/coordinator`
is the rollback procedure; no dual-read mode is
offered. [OpenBao response-wrapping guidance](https://openbao.org/docs/concepts/response-wrapping/)
requires lookup and creation-path validation before unwrap.

### D4 — Atomic identity snapshot and bounded degradation

At startup, the coordinator reads all keyed agent data paths through its
identity-reader principal, validates completeness and duplicate API keys,
then installs an immutable key-to-principal snapshot in one assignment. In
configured Bao mode this snapshot is the sole API-key allowlist; the old
`COORDINATION_API_KEYS` list cannot authorize an unbound or rotated key.
`_principal_for_api_key` checks membership and freshness of the same snapshot
on every request. Non-Bao mode retains its existing static allowlist behavior.
Preflight reports every configured static API key without a registry agent
identity as a cutover blocker. There is no anonymous service-key exception in
pca-02; operators must provision a declared principal for such a caller or
keep it on the prior release until a separate plan covers it.
The reload loop attempts this every 30 seconds. Any partial or invalid read
discards the candidate, emits one sanitized failure event, and marks readiness
degraded. Requests may authenticate against the previous complete snapshot
only while its age is at most 120 seconds. Beyond that, new authentication is
denied until a valid snapshot is installed. A successful refresh clears
degradation and emits a recovery event. Snapshot age uses monotonic time;
readiness and authentication share the same atomic state. No request sees a
partially loaded identity map.

`GET /ready` reports `identity: ready|degraded|disabled` separately from the
existing `db: connected|unreachable`; `disabled` means Bao is not configured.
During the at-most-120-second grace period it returns HTTP 200 with
`identity: degraded`, so existing valid keys remain routable. Startup failure
or snapshot expiry returns 503. The component field and audit event surface
the failure immediately, without causing a readiness restart during grace.

The old static X-API-Key protocol remains for pca-02. pca-03 will replace it
with session tokens. Dynamic database credentials and coordinator-internal
secret loading are outside this identity snapshot change.

### D5 — Keep coordinator-internal secrets separate

`profile_loader.py` and `langfuse_env.sh` still read coordinator-internal settings from the legacy
`secret/coordinator` path and dynamic database credentials have their own
engine. This change preserves those paths and values while renaming the
internal loader's authentication inputs to `BAO_INTERNAL_ROLE_ID` and
`BAO_INTERNAL_SECRET_ID`. They are never used for an agent, vendor lookup,
or identity reload. Deployment migration must supply the renamed internal
variables before removing legacy `BAO_ROLE_ID`/`BAO_SECRET_ID`; preflight
verifies this when internal Bao loading is enabled. The internal loader and
its tests are owned by `wp-coordinator`. Its internal-only policy replaces the
old shared `coordinator-read` grant before the latter is retired. This is a separate, explicit legacy
credential contract pending a future migration; it does not grant agent
access to `secret/coordinator`.
`OpenBaoConfig.from_env()`, `is_enabled()`, and `create_client()` remain the
internal loader's interface, including `BAO_SECRET_PATH`, `BAO_TIMEOUT`, and
`BAO_TOKEN_TTL`; only its role and SecretID input names change. `_load_secrets()`
continues to return a flat string map for profile interpolation and filters
non-string values with a warning. Agent/vendor access uses a separate
principal configuration type.

### D6 — Verification and migration order

Freeze JSON schemas and typed adapter signatures first. Then implement the
pure projection, the seeder, coordinator snapshot, and dispatch consumer in
disjoint work packages. Each behavior is preceded by a failing contract/spec
test. A pinned OpenBao dev image exercises real AppRole and KV-v2 policy
semantics, wrapping one-use behavior, rotation, and denial matrix. Unit fakes
exercise error classification and clock boundaries. The live matrix runs from
`skills/bao-vault/scripts/tests/integration/` through a runner that starts the
pinned Compose fixture, fails if the server is unavailable or the test count is
zero, and tears it down; it does not inherit the coordinator PostgREST skip
fixture. The coordinator Docker build copies the new shared package into the builder
before `uv sync`; the non-editable wheel is installed into the runtime image,
and Docker import smoke checks cover it. The
migration sequence is:
backup legacy path, dry-run and review projection, create new paths/policies,
deliver protected bundles, verify live principal matrix, cut over consumers,
observe reload, then explicitly retire managed legacy agent access. Rollback restores
the prior release and backed-up legacy path.

## Package boundaries

`wp-contracts` freezes interfaces. `wp-projection` owns the shared topology
and typed adapter. `wp-seeding`, `wp-coordinator`, and `wp-dispatch` consume it
in separate code scopes. Their DAG is serialized because each implementation
package must check off its tasks in the same commit, and `tasks.md` is one
shared file; serial execution keeps that write scope valid and avoids merge
conflicts. The orchestrator still dispatches each package to its designated
worker. `wp-integration` owns live Bao tests, docs, migration,
and cross-package validation after all consumers land. The architecture
analysis is stale in this worktree; these boundaries come from inspected code
and are validated by package scope checks before implementation.

## Risks and mitigations

- **Identity-reader scope**: Its all-agent read permission is concentrated.
  Keep it as a distinct service role, issue only to the coordinator, and test
  that it cannot read vendor data or write any path.
- **One-use bootstrap lifecycle**: A consumed SecretID cannot recover an
  expired or revoked token. A protected, locked session cache supports repeated
  short-lived invocations; a short-period token renews while active, and
  documented rebootstrap is required after an extended outage or revocation.
- **Migration ambiguity**: A flat `.secrets.yaml` may not identify each
  destination unambiguously. Dry-run must reject ambiguous mappings and ask
  the operator to provide explicit input, never copy a key to every agent.
- **Concurrent plans**: `add-sandboxed-harness-execution` and
  `add-coordinator-llm-gateway` must consume these contracts, not add another
  fallback or vendor path.
