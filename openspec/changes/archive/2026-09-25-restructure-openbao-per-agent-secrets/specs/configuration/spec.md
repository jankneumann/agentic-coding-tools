# configuration Specification (delta)

## MODIFIED Requirements

### Requirement: Secret Interpolation

Profile interpolation SHALL preserve `${VAR}`, `${VAR:-default}`, and `$${VAR}` syntax. When OpenBao is configured, principal credentials SHALL resolve exclusively through the typed OpenBao credential adapter and its principal-specific paths; `.secrets.yaml`, ambient vendor-key variables, and interpolation defaults SHALL NOT mask a missing or failed configured credential lookup. For coordinator-internal profile values, `_load_secrets()` SHALL still obtain a flat string map from `secret/coordinator` when Bao is enabled, then apply the existing secrets-dict → environment precedence, `${VAR:-default}` defaults, escape syntax, profile inheritance, and `FIELD_ENV_MAP`. Non-string internal values SHALL be filtered with a warning. Non-credential profile settings and non-OpenBao operation SHALL retain their existing precedence and behavior. Coordinator-internal and dynamic-database secrets SHALL retain their existing contracts unless explicitly migrated by this change.

#### Scenario: CFG-01 Configured credential lookup fails loud

- **WHEN** a configured OpenBao vendor credential cannot be read
- **THEN** dispatch SHALL receive a typed failure and SHALL NOT use an ambient vendor key or `.secrets.yaml`

#### Scenario: CFG-02 Non-OpenBao profile remains compatible

- **WHEN** `BAO_ADDR` is absent
- **THEN** existing file and environment interpolation behavior SHALL remain available

### Requirement: OpenBao Secret Backend

Configured agent and vendor credentials SHALL use the KV-v2 mount `secret` by default, with data paths `secret/data/agents/<name>` and `secret/data/vendors/<vendor>` and corresponding logical paths `agents/<name>` and `vendors/<vendor>`. Path construction SHALL be centralized in a typed topology contract. The adapter SHALL receive mount-relative logical paths (`agents/<name>` and `vendors/<vendor>`), while policies SHALL use full `<mount>/data/...` API paths. Each KV-v2 data document SHALL contain exactly one nonempty string `api_key` field. Consumers SHALL use explicit KV-v2 client calls, validate returned shape and string credential values, and expose stable typed errors for configuration, authentication, authorization, not-found, malformed-data, timeout, and backend-unavailable failures. Domain code SHALL NOT interpret raw `hvac` response dictionaries. Configured failures SHALL be sanitized in logs and audit events and SHALL NOT fall back to `secret/coordinator` or static credentials. The coordinator-internal data path and dynamic-database secret behavior SHALL remain unchanged; only the internal authentication inputs change under the separate requirement below. In configured mode, `_load_secrets()` SHALL continue reading the flat `secret/coordinator` document with an internal-only AppRole and SHALL raise on missing credentials, authentication errors, or timeout rather than start with partial secrets. `BAO_MOUNT_PATH` SHALL remain configurable; all paths SHALL derive from that validated KV-v2 mount and a missing or wrong-version mount SHALL fail preflight.

#### Scenario: CFG-03 Agent and vendor KV-v2 paths

- **WHEN** an agent reads its own key and a declared vendor credential
- **THEN** the adapter SHALL request logical KV-v2 paths `agents/<name>` and `vendors/<vendor>` at the configured mount
- **AND** the policy SHALL target the corresponding `secret/data/...` API paths

#### Scenario: CFG-16 Alternate KV-v2 mount

- **WHEN** an operator selects a valid non-default KV-v2 mount
- **THEN** projection, policy generation, and adapter reads SHALL use that mount consistently
- **AND** a missing or wrong-version mount SHALL fail preflight before mutation

#### Scenario: CFG-20 Typed credential documents

- **WHEN** a consumer reads an agent or vendor KV-v2 data document
- **THEN** it SHALL validate a nonempty string `api_key` field against the respective payload schema
- **AND** an unexpected or missing field SHALL produce a sanitized malformed-data failure

#### Scenario: CFG-04 Typed failure and no fallback

- **WHEN** the backend returns permission denied, not found, malformed data, or times out
- **THEN** the adapter SHALL classify the failure without exposing tokens or secret values
- **AND** the consumer SHALL not retry via the shared path, file, or environment

### Requirement: OpenBao Configuration Dataclass

`OpenBaoConfig` SHALL remain the coordinator-internal configuration dataclass. `from_env()` SHALL read `BAO_ADDR`, `BAO_INTERNAL_ROLE_ID`, `BAO_INTERNAL_SECRET_ID`, `BAO_MOUNT_PATH`, `BAO_SECRET_PATH`, `BAO_TIMEOUT`, and `BAO_TOKEN_TTL`; the latter SHALL still default to 3600 seconds. `is_enabled()` SHALL still reflect a nonempty `BAO_ADDR`, and `create_client()` SHALL return an authenticated `hvac.Client` using only the internal AppRole. Missing internal credentials SHALL identify the missing variable and fail startup, invalid authentication SHALL raise a sanitized error with the address and role identifier, and unreachable Bao SHALL fail after the configured bounded timeout. Disabled configuration SHALL reject `create_client()`. The separate principal adapter SHALL use its own configuration type.

#### Scenario: CFG-26 Internal config from environment

- **WHEN** the internal Bao variables are set
- **THEN** `OpenBaoConfig.from_env()` SHALL populate the renamed AppRole inputs and preserve existing defaults
- **AND** `create_client()` SHALL authenticate with that internal AppRole

#### Scenario: CFG-27 Internal config fails safely

- **WHEN** internal credentials are missing or invalid, or Bao is unreachable
- **THEN** internal loading SHALL raise the corresponding missing-credential, authentication, or timeout error without starting with partial secrets
- **AND** `create_client()` SHALL reject a disabled configuration

### Requirement: Bootstrap Seeding Script

The provisioner SHALL project agents and service principals from the canonical registry and explicit service-principal definitions, reconcile one AppRole and policy per principal, and place agent and vendor values in their respective KV-v2 documents. Every mutation, including retired role, policy, and path removal, SHALL emit an audit record with principal, resource, action, and outcome but no credential value. A versioned migration map SHALL explicitly assign every keyed agent and declared vendor one source key from the flat secrets file; an agent source key SHALL exactly match the variable in its registry `${VAR}` `api_key` placeholder and any mismatch or fallback expression SHALL fail preflight; every remaining source key SHALL be explicitly retained for internal use. Dry-run SHALL reject missing, duplicate, or unaccounted mappings before mutation. Dry-run SHALL show the complete planned changes and detect ambiguity or collision without changing OpenBao. Retired resources SHALL be removed only when ownership is established by the projection and the operator has explicitly confirmed cutover; unrelated dynamic-database and coordinator-internal resources SHALL remain untouched. A successful apply SHALL create a unique one-use SecretID per principal, request short-lived response wrapping, and atomically deliver one bootstrap bundle per principal into an explicitly selected mode-0700 directory as mode-0600 files. Plain SecretIDs and wrapping tokens SHALL never appear on stdout, in logs, or in tracked files. Re-running a reconciliation SHALL not duplicate roles or policies; issuing a fresh bootstrap SHALL produce fresh one-use material.

#### Scenario: CFG-08 Dry-run catches drift without mutation

- **WHEN** dry-run finds a retired principal, new vendor grant, or name collision
- **THEN** it SHALL report the intended mutation or validation error without credential values
- **AND** it SHALL make no OpenBao or filesystem mutation

#### Scenario: CFG-18 Explicit migration map

- **WHEN** a keyed agent or declared vendor has no unique source key, or an input key is unaccounted for
- **THEN** preflight SHALL fail before any OpenBao or filesystem mutation
- **AND** an agent-map source key that differs from the registry `api_key` placeholder variable SHALL fail preflight
- **AND** the report SHALL contain key names but no secret values

#### Scenario: CFG-09 Atomic protected bootstrap delivery

- **WHEN** apply issues a wrapped SecretID for an agent or service principal
- **THEN** it SHALL write the bundle atomically under the selected 0700 directory with file mode 0600
- **AND** no plain SecretID or wrapping token SHALL be printed or committed

#### Scenario: CFG-10 Retired principal reconciliation

- **WHEN** an owned agent is removed from the registry after confirmed cutover
- **THEN** its owned AppRole, policy, and agent data path SHALL be removed deterministically and audited
- **AND** unrelated resources SHALL remain unchanged

#### Scenario: CFG-11 Repeat apply is convergent

- **WHEN** apply runs twice for the same registry and values
- **THEN** the second run SHALL not duplicate roles, policies, or KV documents
- **AND** any new bootstrap issuance SHALL use a different one-use SecretID

## ADDED Requirements

### Requirement: OpenBao Migration and Rollback

Migration SHALL preflight every registry principal, vendor scope, path, and bootstrap destination before mutation. The operator SHALL receive a dry-run and an explicit cutover confirmation before legacy agent access to `secret/coordinator` is removed. The coordinator-internal data path SHALL remain. The migration SHALL document release-level rollback by restoring the prior release and a backup of `secret/coordinator`; it SHALL not implement dual-read or configured-OpenBao fallback.

#### Scenario: CFG-12 Pre-cutover legacy path preserved

- **WHEN** per-principal provisioning completes without confirmed cutover
- **THEN** legacy agent access SHALL remain available for release rollback until cutover
- **AND** new configured clients SHALL use only per-principal paths

#### Scenario: CFG-13 Cutover confirmation gates deletion

- **WHEN** the operator has not explicitly confirmed cutover
- **THEN** migration SHALL not retire legacy agent access to `secret/coordinator`

### Requirement: Coordinator-Internal Bao Compatibility

The existing coordinator-internal `secret/coordinator` loader, including `langfuse_env.sh`, SHALL retain its data path and dynamic-database behavior. `OpenBaoConfig.from_env()`, `is_enabled()`, and `create_client()` SHALL remain its interface, using `BAO_ADDR`, `BAO_MOUNT_PATH`, `BAO_SECRET_PATH`, `BAO_TIMEOUT`, and `BAO_TOKEN_TTL` as before. A separate principal configuration type SHALL govern agent and vendor access. An internal-only read policy SHALL be installed before the old shared `coordinator-read` policy is removed. Its authentication inputs SHALL be renamed to `BAO_INTERNAL_ROLE_ID` and `BAO_INTERNAL_SECRET_ID` and SHALL never authenticate an agent, vendor lookup, or identity reload. Deployment preflight SHALL require the renamed inputs before removing legacy global variables when internal Bao loading is enabled.

#### Scenario: CFG-19 Internal profile loader remains isolated

- **WHEN** configured internal profile interpolation reads `secret/coordinator`
- **THEN** it SHALL use only the internal credential inputs and preserve existing values
- **AND** no agent or vendor consumer SHALL use those inputs

### Requirement: Internal and Bootstrap Compatibility Scenarios

The internal profile loader SHALL preserve its existing interpolation, failure, and config interface contracts under renamed internal authentication inputs. Principal bootstrap files SHALL follow the deterministic protected layout, and wrapping origin SHALL be verified against the server response.

#### Scenario: CFG-21 Internal loader retains interpolation contract

- **WHEN** Bao is configured and `secret/coordinator` has string and non-string values
- **THEN** `_load_secrets()` SHALL return only string values, warning for filtered values
- **AND** profile interpolation and `FIELD_ENV_MAP` SHALL behave as before

#### Scenario: CFG-22 Internal config interface remains available

- **WHEN** internal Bao loading is enabled with the renamed internal AppRole inputs
- **THEN** `OpenBaoConfig.from_env()`, `is_enabled()`, and `create_client()` SHALL retain their existing behavior and bounded timeout
- **AND** a failed internal read SHALL not silently fall back to file secrets

#### Scenario: CFG-23 Bootstrap files have deterministic protected names

- **WHEN** a projected principal receives or reads bootstrap material
- **THEN** its bundle, session, and lock names SHALL derive from its validated role name under `BAO_BOOTSTRAP_DIR`
- **AND** the root SHALL be mode 0700 and each file mode 0600

#### Scenario: CFG-24 Server validates wrapping origin

- **WHEN** a bundle's asserted creation path differs from the server's wrapping lookup response
- **THEN** the receiver SHALL use the server response for exact origin validation and reject before unwrap

### Requirement: Principal OpenBao Configuration

OpenBao configuration SHALL require `BAO_ADDR`, a protected `BAO_BOOTSTRAP_DIR`, a canonical principal ID supplied by the registry caller, and a principal-specific bundle containing the RoleID or an already valid renewable token for configured access. The adapter SHALL derive `<role_name>.bundle.json`, `<role_name>.session.json`, and `<role_name>.lock` (mode 0600) under the mode-0700 bootstrap directory from the validated principal projection and SHALL reject missing or unreadable files. `BAO_SECRET_ID` and `BAO_SECRET_PATH` SHALL no longer select a shared agent credential. Configuration SHALL preserve bounded timeout and use a short-period renewable AppRole token without an explicit maximum TTL; a token whose period lapses SHALL require rebootstrap. The authentication adapter SHALL query `POST /v1/sys/wrapping/lookup` through `hvac` adapter POST using the wrapping token, validate the server-returned creation path exactly before unwrap (not trust the bundle field alone), perform the single permitted SecretID login once, and thereafter use a renewable token or obtain a newly issued wrapped SecretID through an authorized rebootstrap flow; it SHALL never attempt a second login with a consumed SecretID. Missing, expired, invalid, or mis-scoped bootstrap material SHALL fail closed. The adapter SHALL store a renewable client token only in a separate mode-0600 session cache under the mode-0700 bootstrap directory. An interprocess lock SHALL serialize first unwrap and renewal, and cache writes SHALL be atomic. After token expiry, revocation, or failed renewal, a fresh wrapped bootstrap SHALL be required; the consumed bundle SHALL NOT be retried. The protected session cache SHALL record a digest of the consumed wrapping token, and under the lock the adapter SHALL compare a newly delivered bundle against that digest before a recovery login. It SHALL check cached-token validity with OpenBao before reuse, treating a revoked token as unusable.

#### Scenario: CFG-05 Single-use bootstrap login

- **WHEN** a receiver loads its bundle and the wrapping token's creation path matches its own AppRole SecretID creation endpoint exactly
- **THEN** it SHALL unwrap once and log in with the resulting SecretID once
- **AND** subsequent operation SHALL use a valid token or new bootstrap material

#### Scenario: CFG-06 Wrong wrapping creation path

- **WHEN** a wrapping token was created for another AppRole or endpoint
- **THEN** the receiver SHALL reject it before unwrap and emit a sanitized failure

#### Scenario: CFG-07 Token expiry needs rebootstrap

- **WHEN** token renewal fails or the token expires after the one-use SecretID is consumed
- **THEN** configured access SHALL fail closed until an authorized fresh wrapped SecretID is delivered
- **AND** the consumed SecretID SHALL not be reused

#### Scenario: CFG-17 Repeated short-lived dispatch

- **WHEN** sequential or concurrent dispatch processes use the same principal bootstrap directory
- **THEN** only one process SHALL unwrap the one-use bundle
- **AND** subsequent processes SHALL reuse a valid protected client-token cache under an interprocess lock

### Requirement: Live OpenBao Conformance Matrix

CI SHALL run a real OpenBao dev-mode fixture pinned to an immutable version or digest. The matrix SHALL prove own-path allow, cross-agent and unrelated-vendor denial, gateway vendor-only access, identity-reader agent-only access, wrapping creation-path validation and single use, key rotation without process restart, and sanitized fail-loud behavior. A mutable `latest` image reference SHALL fail fixture validation.

#### Scenario: CFG-14 Live policy and bootstrap matrix

- **WHEN** CI runs against its pinned OpenBao server
- **THEN** every required allow and deny case and single-use bootstrap assertion SHALL pass

#### Scenario: CFG-15 Mutable image rejected

- **WHEN** the live fixture uses `latest` or another mutable floating tag
- **THEN** fixture validation SHALL fail

### Requirement: Dispatch Tier Credential Boundary

In pca-02, configured OpenBao vendor credential resolution SHALL apply to SDK and OpenAI-compatible dispatch tiers. The CLI tier SHALL retain its existing vendor environment delivery until pca-04; it SHALL not claim a Bao credential lookup or use a missing Bao read as a reason to silently switch a configured SDK request to ambient credentials.

#### Scenario: CFG-25 CLI dispatch boundary

- **WHEN** a CLI vendor process is launched in pca-02
- **THEN** its existing environment-based credential contract SHALL apply
- **AND** SDK and OpenAI-compatible requests SHALL use the configured typed Bao lookup
