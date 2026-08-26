## ADDED Requirements

### Requirement: Dispatched workers SHALL hold leaf credentials only

Workers (sandboxed subprocesses and cloud sandboxes) SHALL receive only leaf
credentials — values usable for their single dispatch — and SHALL never receive
reachability to the secret store or any credential capable of minting further
credentials. All secret resolution SHALL happen in the dispatcher, on the
tailnet-resident host, with material pushed into the workspace at creation.

#### Scenario: No secret-store reachability in a workspace

- **WHEN** a workspace is provisioned for any dispatch
- **THEN** its environment and filesystem SHALL contain no OpenBao address,
  AppRole `role_id`/`secret_id`, or wrapping token
- **AND** the rendered egress allowlist SHALL NOT include the secret store.

#### Scenario: A spec requesting mint authority is refused

- **WHEN** a dispatch spec requests injection of a credential-store credential or
  the secret-store address into a worker
- **THEN** the broker SHALL refuse the dispatch with a structured error
- **AND** an audit event SHALL record the refused request.

### Requirement: The broker's own authority SHALL be minimal and tailnet-bound

The dispatcher SHALL authenticate to OpenBao with a dedicated AppRole whose policy
grants read on exactly the vendor-key and GitHub-App paths required for dispatch,
and token issuance SHALL be CIDR-bound to the tailnet.

#### Scenario: Reads outside the granted paths are denied

- **WHEN** the broker attempts to read a KV path outside its granted vendor-key
  and GitHub-App paths
- **THEN** OpenBao SHALL deny the read
- **AND** the denial SHALL appear in the OpenBao audit device log.

#### Scenario: Broker authentication from outside the tailnet fails

- **WHEN** the broker AppRole login is attempted from an address outside the bound
  CIDR
- **THEN** authentication SHALL fail
- **AND** no token SHALL be issued.

### Requirement: Git credentials SHALL be short-lived and repo-scoped

Remote dispatches SHALL push with GitHub App installation tokens minted by the
dispatcher, scoped to the target repository with approximately one-hour TTL. The
user's PAT and SSH keys SHALL never appear in a dispatch spec or workspace.

#### Scenario: Push uses a minted installation token

- **WHEN** a cloud dispatch pushes its result branch
- **THEN** authentication SHALL use a dispatch-minted installation token scoped to
  the target repository
- **AND** the token SHALL expire without dispatcher renewal.

#### Scenario: Expired token cannot be self-renewed

- **WHEN** a workspace's installation token expires mid-dispatch
- **THEN** pushes SHALL fail until the dispatcher mints and injects a replacement
- **AND** the workspace SHALL have no material capable of minting its own.

### Requirement: Inference credentials SHALL be gateway virtual keys where supported

Where the vendor CLI supports a base-URL override, dispatches SHALL receive a
short-lived LLM-gateway virtual key instead of a raw vendor key. Where no override
exists, the dispatch SHALL receive a dedicated per-lane vendor key with a spend
cap, and the fallback SHALL be audited.

#### Scenario: Gateway-capable CLI receives no raw vendor key

- **WHEN** a dispatch targets a CLI with base-URL override support
- **THEN** the workspace SHALL receive a gateway virtual key and the gateway URL
- **AND** no raw vendor API key SHALL be present in the workspace.

#### Scenario: Fallback to a capped per-lane key is recorded

- **WHEN** a dispatch targets a CLI without base-URL override support
- **THEN** the workspace SHALL receive a per-lane vendor key subject to a spend cap
- **AND** an audit event SHALL record that the gateway was bypassed for the vendor.

### Requirement: The broker SHALL verify secret-store hardening before serving remote dispatch

Because brokering makes OpenBao load-bearing for every dispatch, the broker SHALL
verify at startup that the store runs with persistent storage, TLS on the listener,
and an enabled audit device, and SHALL refuse to serve *remote* dispatches when
verification fails. Local-lane dispatch MAY continue during such degradation.

#### Scenario: Hardened store serves all lanes

- **WHEN** the broker starts against a store with persistence, TLS, and an audit
  device
- **THEN** both local and remote dispatch SHALL be served.

#### Scenario: Unhardened store degrades loudly to local-only

- **WHEN** the broker detects dev-mode storage, a plaintext listener, or a missing
  audit device
- **THEN** remote dispatches SHALL be refused with a structured error
- **AND** a warning and audit event SHALL record the failed verification
- **AND** local-lane dispatch SHALL remain available.
