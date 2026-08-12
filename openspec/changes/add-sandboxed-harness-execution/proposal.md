# Change: add-sandboxed-harness-execution

> Design source: `docs/proposals/sandboxed-harness-execution.md`
> Parent context: `dispatch-governance` roadmap (consumer of dg-02/dg-03/dg-05/dg-07),
> RI-10 (cloud lane), `add-coordinator-llm-gateway` (credential data plane)

## Why

Every dispatched vendor CLI today inherits the supervisor's full ambient authority —
`subprocess.run()` in `review_dispatcher.py` is called with no `env=`, so a spawned
`codex`/`grok`/`pi` process sees the developer's complete environment, `~/.ssh`, and
unrestricted egress — while the trust-posture work is simultaneously making it easier
to remove humans from the loop. This change gives the dispatch layer real execution
backends (local OS sandbox, generic cloud sandbox) and replaces ambient credentials
with per-dispatch brokered ones, so that autonomy gates can be flipped to `auto`
without widening what a confused or prompt-injected worker can reach. The always-on
GX10 host (tailnet-only) is the trust anchor throughout: the cloud lane must require
zero inbound paths to the tailnet.

## What Changes

Phased; each phase is independently landable and independently valuable.

**Phase 0 — Prerequisites (existing dispatch-governance items, sequenced not built here)**
- `build-structured-vendor-result-channel` (dg-02) — hard functional prerequisite for
  any remote backend: stdout of a process on another machine cannot be regexed; the
  coordinator completion ledger becomes the only result channel.
- `add-isolation-posture-detection` (dg-03) and `pin-isolation-contract` (dg-05),
  with one amendment made **now, while the vocabulary is being pinned**: admit
  `container` to `VALID_ISOLATION_MODES` and carry the router's `location` axis
  (`local | cloud`) through the contract.

**Phase 1 — Execution backend seam + local sandbox lane**
- New `ExecutionBackend` protocol (`run`/`poll`/`cancel` over a `DispatchSpec`) behind
  `CliVendorAdapter`, modeled on `evaluation/backends/registry.py` and symphony's
  `agent-runner-port`. Backend selection is a pure function of the routing decision's
  `(location, isolation)` pair — no second decision point.
- The `(local, none|worktree)` backend is byte-identical to today's subprocess path.
- `(local, sandbox)` lands via `add-dispatch-sandbox-enforcement` (dg-07) exactly as
  designed (srt renderer + `wrap_command()`), expressed as a backend.

**Phase 2 — Credential brokering (from ambient to brokered)**
- **Explicit child environments everywhere.** Every backend — including the local
  unsandboxed one — constructs the child env from an allowlist (precedent:
  `agents_config.get_mcp_env()`), never by inheritance. **BREAKING** for any dispatch
  consumer that silently relied on inherited env vars; rollback is a feature flag
  (`DISPATCH_ENV_ALLOWLIST=off`) restoring inheritance while emitting an audit event.
- **Dispatcher-as-secrets-broker.** Sandboxes and subprocesses never gain OpenBao
  reachability. The dispatcher (on the tailnet host) authenticates locally via a
  dedicated AppRole whose policy reads exactly the vendor-key and GitHub-App KV paths,
  resolves what a dispatch needs, and pushes leaf credentials into the workspace at
  creation. Workers hold leaf credentials only — never the means to mint more.
- **Gateway virtual keys for inference.** Where the vendor CLI supports a base-URL
  override, dispatches receive a short-lived LLM-gateway virtual key
  (`add-coordinator-llm-gateway` is the data plane); raw vendor keys stop being
  shipped anywhere. CLIs that cannot be pointed at the gateway get a dedicated
  per-lane vendor key with a spend cap, so revocation stays cheap.
- **Scoped git credentials.** Cloud dispatches push with ~1h repo-scoped GitHub App
  installation tokens minted by the dispatcher (App private key in OpenBao KV);
  the user's PAT/SSH key never leaves the supervisor host.
- **Per-dispatch coordinator API identities** via the existing
  `COORDINATION_API_KEY_IDENTITIES` mechanism, for per-dispatch revocation and audit.
- **OpenBao hardening** (host-side): persistent storage, TLS listener, audit device,
  CIDR-bound token issuance — the broker makes OpenBao load-bearing for every dispatch.

**Phase 3 — Generic cloud sandbox backend**
- One-week spike first: provider egress-control granularity (domain allowlist?),
  snapshot build with the CLI roster, create/exec/teardown latency, end-to-end
  brokered-credential injection. Daytona is the primary candidate; E2B (already named
  by sentinel/verification specs) evaluated in the same spike so one provider serves
  both uses.
- `CloudSandboxBackend`: create-from-snapshot → shallow-clone at work branch →
  inject brokered credentials → exec harness CLI headless. `AGENT_EXECUTION_ENV=cloud`
  inside the sandbox so `worktree.py`/`checkout_policy.py` short-circuit unchanged.
- Zero-inbound topology: sandbox reaches the coordinator only through the existing
  cloudflared tunnel (hardened with Cloudflare Access service tokens); results leave
  as git pushes on `openspec/<change-id>--<agent-id>`; ledger is the single source of
  dispatch state.
- Sandbox egress allowlist rendered from `network_policies.py` (single-source
  constraint); a cloud-adjacent egress proxy only if the spike shows provider
  controls are too coarse — never proxied through the tailnet host.
- **Trust-posture coupling**: a gate disposition of `auto`/`notify_with_timeout` is
  valid only when the executing dispatch's resolved isolation meets the gate's
  declared `min_isolation`; otherwise it degrades to `block` with an audit event.
- Pilot on review fan-out (read-only archetypes), then implementer work-packages.

**Phase 4 — Local containers (optional, on demonstrated need)**
- OpenShell (or equivalent) as an additional renderer + backend only if placement
  rules keep enough sensitive work local that srt's boundary is insufficient. A
  re-evaluation point, not a commitment.

## Approaches Considered

### Approach 1: Backend seam under the pinned isolation contract + push-model credential brokering (**Recommended**)

Extend the dispatch-governance chain (router decides → orchestrator carries →
dispatch enforces) with an `ExecutionBackend` seam; credentials are resolved by the
dispatcher inside the tailnet and pushed into workspaces; inference flows through
gateway virtual keys.

- **Pros**: One decision point (the dg-04 router) and one policy source
  (`network_policies.py`, OpenBao) — no split-brain; zero inbound paths to the
  tailnet-only host; secret store never exposed beyond the tailnet; every phase is
  independently valuable (explicit env alone closes the worst current gap); the
  strongest isolation move (cloud placement) becomes available to vendors with no
  cloud offering (`grok`, `pi`, planned `opencode`).
- **Cons**: More moving parts than vendor-native flags; gateway base-URL support
  varies per CLI and needs a spike; leaf credentials in cloud sandboxes are
  short-TTL but real (response-wrapping is unusable when workers cannot reach the
  vault).
- **Effort**: L (across phases; Phase 2 alone is M)

### Approach 2: Vendor-native mechanisms only

Rely on `claude --remote` / `codex cloud exec` for cloud execution and each vendor's
sandbox flags (`-s read-only`, `--allowedTools`) locally; no broker, no seam.

- **Pros**: Near-zero new code; no new dependencies; works today for two vendors.
- **Cons**: Leaves credentials fully ambient (the actual worst gap); covers only
  vendors that ship their own cloud; enforcement is "three incompatible dialects,
  enforced by nobody" per `add-dispatch-sandbox-enforcement`; `isolation: sandbox`
  stays inert; nothing to couple trust-posture autonomy to.
- **Effort**: S

### Approach 3: Direct sandbox→OpenBao access (pull-model secrets)

Give cloud sandboxes OpenBao reachability — via a second cloudflared tunnel or
tailnet ephemeral nodes in the sandbox image — and let each worker authenticate with
a per-dispatch AppRole `secret_id`.

- **Pros**: Textbook Vault pattern (short-TTL `secret_id`, `num_uses=1`); secrets
  fetched just-in-time rather than injected; no broker code in the dispatcher.
- **Cons**: Exposes the secret store beyond the tailnet, breaking the GX10's
  zero-inbound invariant; places a credential *for the credential store* in the
  highest-prompt-injection-surface location in the system; tailnet-node variant
  couples cloud capacity to residential bandwidth; response-wrapping cannot mitigate
  it (unwrapping itself requires vault reachability).
- **Effort**: M

### Recommended

Approach 1. Approach 2 closes neither motivating gap — credentials stay ambient and
isolation stays unenforced — and Approach 3 trades the system's strongest structural
property (a secret store reachable only from the tailnet) for broker-code savings
that are small, since the dispatcher already resolves per-vendor keys via
`ApiKeyResolver`. The push model inverts privilege correctly: the supervisor side
holds mint authority, workers hold leaves.

### Selected Approach

**Approach 1** selected at Gate 1 (2026-08-12), as recommended, with no
modifications: `ExecutionBackend` seam under the pinned isolation contract,
push-model credential brokering from the tailnet-resident dispatcher, and gateway
virtual keys for inference. Credential brokering is Phase 2, ahead of the cloud
sandbox backend that depends on it.

## Impact

**Architecture layers**: Execution (backends, env construction), Coordination
(ledger as dispatch state, per-dispatch identities), Trust (credential brokering,
min-isolation gate coupling), Governance (posture file schema, audit events).

**Affected spec capabilities** (delta files to be created in the `specs` artifact):

- `vendor-dispatch` → `specs/vendor-dispatch/spec.md`: ExecutionBackend seam,
  explicit env allowlist requirement, backend selection from routing decision.
- `agent-coordinator` → `specs/agent-coordinator/spec.md`: network-policy export
  rendering, per-dispatch API identities, completion-ledger as sole dispatch state
  for remote backends.
- `agent-archetypes` → `specs/agent-archetypes/spec.md`: isolation vocabulary gains
  `container` + `location` axis (coordinated with `pin-isolation-contract`).
- New capability `credential-brokering` → `specs/credential-brokering/spec.md`:
  broker AppRole policy bounds, leaf-credential invariant, GitHub App token minting,
  gateway virtual-key provisioning, OpenBao hardening requirements.
- New capability `cloud-sandbox-execution` → `specs/cloud-sandbox-execution/spec.md`:
  zero-inbound topology, snapshot/provisioning contract, egress rendering,
  trust-posture `min_isolation` coupling.

**Code touchpoints**: `skills/parallel-infrastructure/scripts/review_dispatcher.py`
(backend selection; sequenced after dg-02's rewrite of the same methods),
`skills/shared/sandbox_profile.py` (new, shared with dg-07),
`skills/shared/environment_profile.py` (dg-03), `agent-coordinator/src/agents_config.py`
(isolation vocabulary, env allowlist helper), `agent-coordinator/src/network_policies.py`
(export path), `skills/parallel-infrastructure/scripts/api_key_resolver.py`
(broker integration), new `skills/shared/execution_backends/`.

**Coordination with in-flight work**: must not run concurrently with
`build-structured-vendor-result-channel` against `review_dispatcher.py` (same
methods); consumes `add-coordinator-llm-gateway` as the Phase 2 inference data
plane; amends `pin-isolation-contract` before it merges; supplies the enforcement
that `symphony/trust-posture-binding` declares.

**Rollback**: Phases are feature-flagged at the backend-selection point; the
`(local, none|worktree)` backend is the unchanged legacy path. The one **BREAKING**
item (explicit env allowlist) rolls back via `DISPATCH_ENV_ALLOWLIST=off` with an
audit event, so restoring inheritance is observable, never silent.
