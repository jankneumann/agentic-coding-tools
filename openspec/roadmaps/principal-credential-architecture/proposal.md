# Principal & Credential Architecture: One Registry, Issued Credentials, Enforced Posture

## Motivation

An audit of the coordination API-key and trust-level plumbing (2026-08-14, prompted by the
antigravity/grok/pi harness additions) found that agent identity, trust, credentials, and
isolation live in four weakly-coupled layers that already disagree with each other:

1. **`agents.yaml`** declares `trust_level`, `profile`, `api_key`, `openbao_role_id`, and
   `isolation` per agent — and almost none of it is consumed. `AgentEntry.trust_level` is
   loaded, schema-validated (against a 1–5 scale), and never read at runtime anywhere.
   `isolation` has the same defect, already documented by the `dispatch-governance` roadmap.
2. **Env vars** (`COORDINATION_API_KEYS` / `COORDINATION_API_KEY_IDENTITIES`) are what
   actually authenticate HTTP callers. `get_api_key_identities()` auto-populates them from
   `agents.yaml` — but filters to `transport: "http"` agents, so the three new local
   harnesses got no identities from the canonical file. `scripts/setup_cloud.py` papers over
   this with a second, hand-maintained agent roster that mints keys for all seven agents and
   pushes them to Railway, bypassing `agents.yaml` entirely. Two rosters, no consistency check.
3. **The DB `agent_profiles` table** is what actually determines trust at runtime
   (`resolve_trust_level()`), seeded by migrations that still carry retired `gemini`/`strands`
   profiles and never gained `antigravity_local`, `grok_local`, `pi_local`, or `codex_local`.
   Unknown agents silently fall back to `default_trust_level = 2` — so the new harnesses run
   at trust 2 despite the registry declaring 3, and `min_trust_level: 3` guardrails block them
   in ways nobody decided. The DB constraint allows trust 0–4; the YAML schema allows 1–5.
4. **OpenBao** integration exists (`_resolve_api_key_from_openbao`, `bao_seed.py`) but uses a
   **shared `BAO_SECRET_ID`** for every AppRole — any agent can log in as any other agent's
   role — and a **single shared KV path** (`secret/coordinator`) with one `coordinator-read`
   policy, so every agent can read every other agent's coordination key plus all vendor keys.
   On any error it falls back silently to static resolution.

The unifying failure mode is **fail-open drift**: every layer has a graceful fallback
(missing profile → trust 2, missing identity → env var, OpenBao error → static key), so a
half-onboarded harness never errors — it just runs with quietly wrong permissions. Graceful
degradation in an authorization path inverts into a silent policy bypass. Adding one harness
currently requires four separate registrations with no check that they agree, which is exactly
why the `add-agy-grok-pi-harnesses` change updated the dispatch plumbing and missed the
authorization plumbing: nothing failed.

This repository is a testing ground for agent development and deployment practice. The
operator is the sole user and has explicitly accepted breaking changes in exchange for a
design that is clean enough to serve as a teaching example. That is the standard this epic
holds itself to.

**Success looks like**: a new harness is one `agents.yaml` diff; CI proves every projection
(DB profile, identity, OpenBao role and policy, posture) materializes from it; no standing
credential exists anywhere in config; a compromised agent's blast radius is its own secrets;
and the whole chain — identity, trust, credential scope, isolation — is resolved once per
dispatch and observable in the audit trail.

## Design Principles

1. **Declare once, project everywhere.** `agents.yaml` is the only place a human writes
   identity, trust, or posture. DB profile rows, identity maps, OpenBao roles/policies,
   Cedar entities, and sandbox settings are mechanical projections of it. If two projections
   can disagree, the design is wrong.
2. **Identity is declared; credentials are issued.** The registry names principals and their
   trust; it never contains secrets or secret references. Credentials are minted by OpenBao
   with TTLs, delivered at provision/dispatch time, and expire on their own.
3. **Fail closed on authorization, fail loud on availability.** A *known* agent with a broken
   projection is an error, not a default. Only genuine infrastructure absence (OpenBao not
   deployed) degrades — with an audit event.
4. **Posture is one thing.** Trust level, isolation mode, and credential scope are three
   facets of a single per-dispatch decision, computed by one resolver and consumed by API
   auth, guardrails, the sandbox renderer, and credential injection alike.
5. **Standardize identity naming and token shape; keep the authentication mechanism swappable.**
   Mechanisms are deployment-topology-dependent; identity strings leak into every table,
   policy, and audit row and are nearly impossible to change later.

## Trust-Anchor Analysis (why AppRole, why the seam)

Every workload-authentication mechanism reduces to a trust anchor: AppRole trusts the
**provisioner** that delivers a bootstrap secret; SPIFFE/SPIRE trusts an **attestor** that
observes runtime properties; OIDC federation trusts an **external issuer**. In this system's
topology — vendor CLIs spawned as subprocesses on one developer machine, all under one uid —
attestation carries no signal (SPIRE's unix attestor cannot distinguish `pi-local` from
`grok-local`) and no external issuer exists for local processes. The dispatch chokepoint is
the only party that ever actually knows which agent a process is, so formalizing it as the
trust anchor via **AppRole with response-wrapped, single-use secret_ids** is the honest,
standard choice — the current defect is AppRole used wrong (shared secret_id), not AppRole.

What we adopt from SPIFFE regardless, at zero infrastructure cost:

- **SPIFFE-ID naming** for principals across every plane:
  `spiffe://coordinator.rotkohl.ai/agent/<name>` as AppRole name, KV path segment, Cedar
  entity ID, audit principal, and session-token `sub` claim.
- **JWT-SVID-shaped session tokens** (`sub` = SPIFFE ID, `aud` = coordinator, short `exp`,
  plus `trust_level` / `profile` claims).
- **A pluggable authenticator seam** at `POST /auth/session`: today one authenticator
  validates an OpenBao token (backed by AppRole login); a Kubernetes service-account JWT
  validator (when OpenShell's k3s control plane makes attestation real) or a CI OIDC
  validator (GitHub Actions) is an addition beside it, not a rewrite. Same
  "runtime-shaped but not runtime-bound" seam pattern as `add-dispatch-sandbox-enforcement`'s
  sandbox renderer.

Cloudflare Access service tokens remain at the edge: they authenticate the network path;
AppRole/session tokens authenticate the workload. Different questions, independent failure
domains — defense in depth, not redundancy.

## Secrets Taxonomy

| Class | Example | Lifecycle | Home |
|---|---|---|---|
| Coordination credentials | agent ↔ coordinator auth | issued per session, minutes–hours TTL | never stored; minted via AppRole login |
| Vendor credentials | `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` | external static, manually rotated | OpenBao KV `secret/vendors/<vendor>`, injected only into dispatches of agents whose registry entry needs them |
| Infrastructure | Postgres DSN | dynamic | OpenBao database secrets engine (already stubbed in `bao_seed.py --with-db-engine`) |

The current single shared KV path collapses all three classes into one blast radius. The
target layout is `secret/agents/<name>/*` and `secret/vendors/<vendor>/*` with per-agent
policies granting exactly the agent's own path plus its vendor's path.

Vendor credentials additionally carry a **delivery mode**, because OpenBao can only do
*issuance-time* exchange — whatever it issues, the workload ends up holding, and for static
vendor keys the lease bounds the copy, not the key's validity. Where the dispatch posture
includes an egress gateway (`dispatch-governance` dg-08's iron-proxy), delivery upgrades to
*request-time* exchange: the sandbox holds only a proxy token and the gateway attaches the
real key at egress, so the secret never enters the environment the untrusted code runs in.
Direct injection remains the delivery mode for the local srt tier, where no gateway posture
exists.

## Capabilities

### Capability: Registry-derived identity and trust (Phase 1)

`agents.yaml` becomes canonical and every projection is derived: the `transport == "http"`
filter on identity generation is removed (the MCP→HTTP proxy fallback makes every harness a
potential HTTP principal), DB profiles are synced from the registry at coordinator startup
(upsert; rows the registry no longer names are disabled), the trust scale is unified to one
0–4 definition, missing projections for known agents fail loud, `setup_cloud.py` becomes a
thin wrapper deriving its roster from the registry, and a CI invariant test proves every
registry agent resolves to a profile, an identity, and a posture. No OpenBao required.

**Acceptance Outcomes:**
- Adding a harness to `agents.yaml` is sufficient for it to authenticate with a correct
  trust level; CI fails if any projection cannot be derived
- `resolve_trust_level()` for every registry agent returns the registry-declared value;
  the silent trust-2 fallback for known agents is gone (unknown principals still default low)
- Retired `gemini`/`strands` profile rows are disabled by sync; `setup_cloud.py` contains
  no second agent roster
- One trust scale (0–4, named levels) validated identically in YAML schema, DB constraint,
  and policy-engine tier thresholds

### Capability: Per-agent OpenBao secrets done right (Phase 2)

`bao_seed.py` is reworked to per-agent AppRoles named by SPIFFE ID, per-agent KV paths and
policies (own path + needed vendor paths only), and response-wrapped single-use secret_id
delivery. The shared `BAO_SECRET_ID` bootstrap is removed. Per-agent coordination keys and
vendor keys move to their taxonomy paths. The coordinator loads its identity map from OpenBao
with periodic hot-reload, so key rotation requires no redeploy. `_resolve_api_key_from_openbao`
fail-open becomes fail-loud with an audit event. Static keys still exist but live only in
OpenBao.

One service principal is seeded beside the agents:
`spiffe://coordinator.rotkohl.ai/service/egress-gateway`, with read access to
`secret/vendors/*` and nothing else. This is dg-08's iron-proxy identity — it lets the
gateway fetch vendor keys at egress through exactly the per-principal machinery this phase
builds, without granting it any agent-path access.

**Acceptance Outcomes:**
- No two agents share a secret_id, KV path, or policy; an agent's Bao token cannot read
  another agent's secrets (asserted by an integration test against a dev-mode OpenBao)
- Rotating any agent's coordination key takes effect without coordinator restart
- OpenBao resolution errors for a configured agent produce a hard failure plus audit event,
  never a silent static fallback

### Capability: Issued session credentials replace static keys (Phase 3)

`POST /auth/session` accepts proof from a pluggable authenticator (initially: OpenBao token
lookup backed by AppRole login) and returns a short-TTL signed session token shaped like a
JWT-SVID carrying the resolved principal record. All authenticated endpoints validate the
token statelessly; `COORDINATION_API_KEYS` / `COORDINATION_API_KEY_IDENTITIES` are deleted.
The signing key lives in OpenBao. `setup_cloud.py` key minting is retired.

**Acceptance Outcomes:**
- No standing coordination credential exists in any env var, file, or Railway variable
- Revoking an agent is one AppRole revocation; its next session request fails
- A second authenticator can be added without modifying existing ones (seam demonstrated
  by a test double)

### Capability: Unified dispatch posture (Phase 4)

`resolve_posture(principal, dispatch_mode) → {trust, isolation, credential_delivery,
vendor_credentials}` becomes the single per-dispatch decision, consumed by guardrails/policy,
the sandbox renderer (`dispatch-governance` dg-07's srt seam, later OpenShell), and credential
injection. This phase **consumes** dg-07's renderer and the task router's isolation output
rather than re-deciding them, and supplies the credential-scope dimension both currently lack.

`credential_delivery` has two modes, chosen by the network posture, and the resolver always
picks the strongest the posture supports:

- **direct** (local srt tier): the dispatch adapter fetches only the listed vendor
  credentials from OpenBao and injects them into the subprocess env; nothing else reaches
  the child process. Issuance-time scoping — the key is present but its blast radius is
  bounded.
- **gateway** (dg-08 postures): the adapter injects **proxy tokens** only; iron-proxy swaps
  in the real vendor key at egress under its `service/egress-gateway` principal.
  Request-time exchange — the real secret never enters the sandbox, which is the strongest
  answer available to this epic's motivating threat of a prompt-injected agent reading
  credentials.

**Acceptance Outcomes:**
- One audit event per dispatch records the full resolved posture (principal, trust,
  isolation, credential scope, credential delivery mode, authenticator)
- A dispatched `pi` subprocess env contains the OpenRouter key and no other vendor secret
- In a gateway posture the subprocess env contains proxy tokens and no real vendor secret
  at all
- OpenShell adoption is a renderer + authenticator addition, demonstrated by a design-level
  contract test against the seam interfaces

## Sequencing and Coordination

Phases are strictly ordered (each is independently shippable and leaves the system
consistent). Cross-roadmap edges:

- **dg-07 / `add-dispatch-sandbox-enforcement`** owns the sandbox renderer seam and
  `resolve_isolation()`; Phase 4 consumes them and must not run concurrently against
  `review_dispatcher.py`.
- **dg-08 / `add-egress-gateway-boundary`** owns the iron-proxy renderer and gateway
  deployment; Phase 2 seeds its service principal, and Phase 4's `gateway` delivery mode
  activates only where dg-08 has a gateway posture to offer. Either side ships without the
  other: without dg-08, every posture resolves to `direct`; without Phase 4, dg-08 enforces
  egress policy but vendor keys stay directly injected.
- **symphony `trust-posture-binding`** owns posture *declaration*; Phase 4 is additional
  enforcement surface for what it declares.
- **`implement-the-task-router-vendor-x-location-x-model`** produces the isolation decision
  Phase 4 consumes; the Phase 1 registry sync is upstream of the router's static fallback
  table.

## Trade-offs

**Accepted: breaking changes over migration shims.** Sole-operator system; every phase ships
with a rollback note instead of a compatibility layer. `COORDINATION_API_KEYS` dies in
Phase 3 rather than being deprecated across releases.

**Accepted: provisioner trust over attestation infrastructure.** SPIRE on a single-uid dev
machine would launder the same trust through more moving parts. The seam keeps real
attestation adoptable when OpenShell's k3s makes it meaningful.

**Accepted: OpenBao as a hard dependency for Phases 2+** (dev-mode instance in CI) over
keeping a Bao-less static path alive forever. Phase 1 alone requires no Bao, which is the
fallback posture if OpenBao is ever removed.

**Accepted: two credential-exchange tiers instead of one.** Issuance-time exchange (OpenBao
leases, `direct` delivery) is the ceiling on the local uid, where no unbypassable egress hop
exists; request-time exchange (`gateway` delivery via dg-08's iron-proxy) is reserved for
postures that can actually enforce it. Pretending the local tier has a secret boundary it
cannot enforce would repeat the fail-open drift this epic exists to remove.

**Accepted: Cedar policies stay hand-written.** Cedar *entities* are generated from the
registry (drift-free); generated *policies* would hide the authorization logic this repo
exists to teach.
