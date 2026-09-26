# OpenBao contract v1

The JSON Schemas describe serialized values at the adapter boundary. The following projection rules are normative because JSON Schema cannot compare fields across objects or derive strings from a registry key.

## Principal projection

- Every `agents.yaml` entry declaring an API key produces exactly one `agent` principal, regardless of transport. Its canonical ID is `spiffe://coordinator.rotkohl.ai/agent/<name>`. The registry name must match `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`; reject names that cannot be encoded and reject duplicate IDs, role names, policy names, or paths. The explicit `vendor_credentials` array is sorted; reject undeclared vendors and duplicate entries rather than silently deduplicating or broadening access. Manually authored `openbao_role_id` is invalid.
- An agent's AppRole and policy names are both `agent-<name>`. At the configured mount (default `secret`), its mount-relative KV logical path is `agents/<name>`. Its policy grants `read` on `<mount>/data/agents/<name>` and, for each declared vendor `<vendor>`, `read` on `<mount>/data/vendors/<vendor>`. It grants no wildcard paths. The corresponding KV-v2 metadata path is distinct and is not a workload read capability.
- The coordinator identity reload uses `spiffe://coordinator.rotkohl.ai/service/identity-reader`, role and policy `service-identity-reader`, with `read` on each declared keyed agent data path at the configured mount and no vendor access. It never authenticates with an agent AppRole.
- The dg-08 gateway uses `spiffe://coordinator.rotkohl.ai/service/egress-gateway`, role and policy `service-egress-gateway`, with `read` on each configured vendor data path at the configured mount and no agent access. This contract does not issue proxy tokens or authorize dispatches.
- The projection contains exactly one of each service principal. Provisioner privileges are separate from these workload policies. Reconciliation is deterministic, reports proposed mutations in dry run, and only retires resources it owns.

## Bootstrap and client lifecycle

The provisioner creates a different AppRole SecretID for every principal, sets `secret_id_num_uses=1` plus the projected `token_period_seconds` (default 3600, no explicit max TTL), and asks OpenBao to response-wrap its creation response with a short TTL. The bundle contains the role ID and **wrapping token**, never a plain SecretID. The receiver uses `client.adapter.post("/v1/sys/wrapping/lookup", json={"token": wrapping_token})` to obtain the server-returned creation path, checks that it equals `auth/approle/role/<role_name>/secret-id` before unwrapping (the bundle field alone is not trusted), checks its expiry, unwraps once, and logs in once. It then uses and renews the issued client token. A fresh SecretID and bundle are required for a later login. `role_id` is treated as sensitive in the delivery artifact even though it is not sufficient to authenticate alone.

Bundle files are atomically replaced beneath an explicitly configured mode-0700 directory, with mode 0600 on each file. Neither bundle content nor raw OpenBao response dictionaries may enter logs, events, CLI output, source control, or domain models. A failed write must leave the previous valid bundle intact.

## Typed adapter errors and events

Provisioning, coordinator reload, and dispatch lookup share the `error_code` enum in `openbao-event.schema.json`. `CONFIGURATION_INVALID` covers malformed registry projection and missing required configuration; `BOOTSTRAP_INVALID` covers wrong creation path, expired wrap, or malformed bundle; `AUTHENTICATION_FAILED` covers rejected AppRole login; `AUTHORIZATION_DENIED` covers policy denial; `SECRET_NOT_FOUND` covers absent KV data; `SECRET_MALFORMED` covers missing or invalid expected fields; `TIMEOUT` covers bounded request expiry; `BACKEND_UNAVAILABLE` covers other transport and server failures; `TOKEN_EXPIRED` covers exhausted client-token renewal. Adapters may carry a sanitized context enum and causal exception internally, but domain code must not receive raw `hvac` dictionaries or fall back to static secrets for configured OpenBao principals.

Emit a sanitized event with `action`, resource class, and outcome for each reconciliation mutation, bootstrap issuance or rejection, failed identity refresh, snapshot expiry, and credential lookup failure. The event schema deliberately contains no credential values, SecretIDs, wrapping tokens, raw paths, arbitrary messages, or exception text. A failed identity refresh retains the last valid snapshot for no more than 120 seconds; subsequent new authentication fails closed until a valid snapshot is installed. Successful refresh atomically installs an immutable snapshot. The default refresh interval is 30 seconds.

## Migration mapping and session reuse

`migration-map.schema.json` defines an explicit key-name-only input file, passed as `--migration-map PATH`. Every keyed agent and every declared vendor has one source key in the flat secrets file; every remaining source key must be listed as retained internal. Preflight rejects missing destinations, repeated source keys, unaccounted input fields, and unknown vendor IDs before writing Bao. `legacy_role_aliases` names pre-migration role overrides to retire after confirmed cutover. The mapping is not a credential store.

`session-cache.schema.json` defines the protected renewable client-token cache shared by short-lived processes of the same principal. Interprocess locking guards first unwrap, renewal, and atomic replacement; the cache is 0600 under the 0700 bootstrap directory. The cache records only a SHA-256 digest of the consumed wrapping token. Under the same interprocess lock, the adapter checks cached-token validity with OpenBao; after expiry or revocation it may bootstrap only from a bundle with a different token digest, then atomically replace the cache. A consumed wrapping token cannot be reused after token expiry or revocation. AppRole tokens have a short renewal period without an explicit maximum TTL. Rebootstrap requires a fresh issued bundle.

The coordinator-internal profile loader and Langfuse helper keep the existing `secret/coordinator` path under separate `BAO_INTERNAL_ROLE_ID` and `BAO_INTERNAL_SECRET_ID` configuration. Those inputs never authenticate an agent or vendor lookup.

## KV-v2 payloads and service scope

`agent-secret.schema.json` and `vendor-secret.schema.json` each define a data payload with one nonempty string `api_key`. The adapter passes mount-relative logical paths to hvac; the policy grants full `<mount>/data/...` API paths. The registry top-level `credential_vendors` catalog defines allowed vendor IDs. The gateway policy contains the sorted union of agents' explicitly declared vendor IDs; the identity-reader policy contains the exact keyed agent paths. Neither uses a wildcard.

## Bootstrap directory layout and dispatch wire

For each validated projected `role_name`, use `<BAO_BOOTSTRAP_DIR>/<role_name>.bundle.json` (0600), `<role_name>.session.json` (0600), and `<role_name>.lock` (0600, `flock`). The root is 0700. Reject path traversal and symlink destinations. Provisioning writes the bundle; the adapter owns the session and lock. Consumer configuration supplies the canonical principal ID, from which the role name and filenames are derived.

`GET /agents/dispatch-configs` and the direct `agents.yaml` loader produce the same dispatch record: existing transport fields plus `principal_id` and sorted `vendor_credentials`, with no `openbao_role_id`. A keyed agent has its canonical SPIFFE ID; a keyless endpoint agent has `principal_id: null` and `vendor_credentials: []`. Neither response includes a key or bootstrap token. The SDK and OpenAI-compatible tiers use these fields for `resolve(principal_id, vendor_id)`; the CLI tier retains its existing vendor environment contract until pca-04.

The migration map's agent source key must equal the variable in that agent's exact `${VAR}` `api_key` placeholder. A mismatch or a fallback expression fails preflight. Vendor keys that currently exist only in deployment environment must be staged into the protected flat secrets input before preflight; seed-time staging does not authorize runtime environment fallback.
