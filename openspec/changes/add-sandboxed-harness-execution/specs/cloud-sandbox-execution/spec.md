## ADDED Requirements

### Requirement: The cloud lane SHALL require zero inbound paths to the tailnet

Every link in a cloud dispatch SHALL be outbound-from-host or outbound-from-sandbox
to a public endpoint: dispatcher → provider API, sandbox → coordinator tunnel
hostname, sandbox → git remote, sandbox → inference gateway. No cloud-lane
component SHALL require an inbound connection to the tailnet or a tailnet
credential inside a sandbox.

#### Scenario: Sandbox reaches the coordinator only through the tunnel

- **WHEN** a cloud sandbox communicates with the coordinator
- **THEN** it SHALL connect to the public tunnel hostname with its per-dispatch
  API identity
- **AND** no tailnet address, tailscale key, or direct host route SHALL be present
  in the sandbox.

#### Scenario: Configuration demanding tailnet access is rejected

- **WHEN** a backend configuration specifies a tailnet address or tailnet
  credential for sandbox use
- **THEN** validation SHALL fail before any sandbox is created
- **AND** the rejection SHALL name the offending configuration key.

### Requirement: Sandbox provisioning SHALL compose with existing environment detection

Provisioning SHALL create the sandbox from a prebuilt snapshot, shallow-clone the
repository at the work branch, inject brokered credentials, and set
`AGENT_EXECUTION_ENV=cloud`, so that the existing worktree short-circuit and
checkout policy operate unchanged inside the sandbox.

#### Scenario: Skills short-circuit inside the sandbox

- **WHEN** a skill invokes worktree setup inside a provisioned sandbox
- **THEN** the environment profile SHALL report cloud isolation from the explicit
  environment variable
- **AND** worktree creation SHALL no-op and the checkout SHALL classify as
  `isolated_harness`.

#### Scenario: Missing detection signal blocks mutation

- **WHEN** the isolation signal is absent from a provisioned sandbox
- **THEN** the mutation guard SHALL block shared-checkout writes as it does today
- **AND** the dispatch SHALL fail visibly rather than mutate an unclassified
  checkout.

### Requirement: Sandbox egress SHALL be a rendering of the coordinator policy

The sandbox egress allowlist (coordinator tunnel hostname, git remote, inference
gateway) SHALL be rendered from the coordinator's exported network policy into the
provider's network controls. If provider controls cannot express the rendered
allowlist, an adjacent cloud egress proxy SHALL be used; sandbox traffic SHALL NOT
be routed through the tailnet host.

#### Scenario: Egress is bounded to rendered destinations

- **WHEN** a cloud sandbox attempts a connection to a destination outside the
  rendered allowlist
- **THEN** the connection SHALL be blocked by the provider control or egress proxy
- **AND** the rendered allowlist SHALL contain no destination absent from the
  authored policy.

#### Scenario: Coarse provider controls degrade per posture, never silently

- **WHEN** the provider cannot express the rendered allowlist and no egress proxy
  is deployed
- **THEN** the dispatch SHALL proceed only if the applicable trust-posture gate
  permits the resulting posture
- **AND** a warning and audit event SHALL record that egress enforcement was
  degraded.

### Requirement: Gate autonomy SHALL be conditioned on resolved isolation

A trust-posture gate disposition of `auto` or `notify_with_timeout` SHALL be valid
only when the executing dispatch's resolved isolation meets the gate's declared
`min_isolation`; otherwise the effective disposition SHALL degrade to `block` with
an audit event.

#### Scenario: Sufficient isolation honors the declared disposition

- **WHEN** a gate declared `auto` with `min_isolation: sandbox` fires for a
  dispatch resolved to `(cloud, container)`
- **THEN** the gate SHALL auto-proceed
- **AND** the audit record SHALL include the posture and resolved isolation that
  authorized it.

#### Scenario: Insufficient isolation degrades to block

- **WHEN** a gate declared `auto` with `min_isolation: sandbox` fires for a
  dispatch resolved to `(local, none)`
- **THEN** the effective disposition SHALL be `block`
- **AND** an audit event SHALL record the degradation and its cause
- **AND** the loop SHALL park for human action exactly as under a declared `block`.

### Requirement: Sandbox lifecycle SHALL be bounded and results delivered via the data plane

Every sandbox SHALL carry a wall-clock bound (provider auto-stop). Results SHALL
leave as pushes on the conventional branch (`openspec/<change-id>--<agent-id>`)
referenced from the completion ledger; teardown SHALL not depend on the worker
cooperating.

#### Scenario: Completed dispatch delivers branch plus ledger record

- **WHEN** a cloud dispatch completes
- **THEN** its result SHALL exist as a pushed branch named by the convention
- **AND** the ledger record SHALL reference the branch and terminal status
- **AND** the sandbox SHALL be stopped or destroyed.

#### Scenario: Runaway sandbox is bounded

- **WHEN** a sandbox reaches its wall-clock bound without completing
- **THEN** the provider SHALL stop it independent of worker cooperation
- **AND** the ledger SHALL record a timeout terminal state
- **AND** its per-dispatch credentials SHALL be revoked or left to expire without
  renewal.
