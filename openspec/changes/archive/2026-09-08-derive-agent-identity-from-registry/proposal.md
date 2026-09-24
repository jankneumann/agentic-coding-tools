# Change: derive-agent-identity-from-registry

> Parent roadmap: `principal-credential-architecture` (item `pca-01`, Phase 1 of 4)
> Change ID: `derive-agent-identity-from-registry`
> Effort: M
> Depends on: nothing (deliberately requires no OpenBao)
> Related: `dispatch-governance` dg-07 (isolation enforcement), symphony `trust-posture-binding`

## Why

The `agent-identity` spec has declared `agents.yaml` "the single source of truth for agent
identity, trust levels, permissions, and API key mapping" since 2026-03-01, and has required a
`seed_profiles_from_config()` function since the same change. **That function was never
implemented** — it exists only in spec files and archived proposals. The
`add-agy-grok-pi-harnesses` change (2026-07-24) even *modified* the seeding requirement
(adding the retired-harness scenario) while still not implementing it, then onboarded three
new harnesses whose declared `trust_level: 3` and `profile: antigravity_local` /
`grok_local` / `pi_local` resolve to nothing: no DB rows exist, `resolve_trust_level()`
silently falls back to `default_trust_level = 2`, and guardrails with `min_trust_level: 3`
block them in ways nobody decided. Meanwhile `get_api_key_identities()` filters to
`transport: "http"` agents, so none of the five local harnesses get API-key identities from
the canonical file — `scripts/setup_cloud.py` compensates with a second, hand-maintained
seven-agent roster that mints keys and pushes them to Railway behind `agents.yaml`'s back.

The unifying failure mode is **fail-open drift** across four layers (registry, env vars, DB
profiles, OpenBao): every layer degrades gracefully, so a half-onboarded harness never
errors — it just runs with quietly wrong permissions. Nothing failed when the authorization
half of the harness onboarding was forgotten, which is precisely why it was forgotten. This
change makes the registry actually canonical and makes drift a CI failure instead of a
runtime surprise. (Trust layer, with Coordination-layer touchpoints in the HTTP API and
Governance-layer touchpoints in the audit of sync actions.)

## What Changes

- **Registry-derived identity for every agent.** `get_api_key_identities()` drops the
  `transport == "http"` filter — the MCP server's HTTP-proxy fallback makes every harness a
  potential HTTP principal, so every registry agent gets an identity. **BREAKING**: the
  auto-populated identity map grows from 2 entries to the full roster; any deployment
  relying on local agents being *absent* from the map must now rotate per-agent keys.
- **Startup profile sync replaces the never-implemented explicit seeding.** The coordinator
  upserts `agent_profiles` rows from the registry at startup (name, agent_type, trust_level,
  allowed_operations derived from `capabilities`); rows whose profile name is no longer
  declared by any registry entry are **disabled** (not deleted), with an audit event per
  mutation. **BREAKING**: reverses the spec's "additive only / explicit action" posture; the
  retired `gemini_*` / `strands_*` rows get disabled on first boot.
- **Fail loud for known agents.** `resolve_trust_level()` distinguishes "principal not in
  registry" (default low trust, unchanged) from "registry agent whose profile row is missing
  or disabled" (hard error + audit event). The silent trust-2 fallback for declared agents
  is gone.
- **One trust scale.** The 0–4 scale the `agent-coordinator` spec already names (0 Untrusted,
  1 Limited, 2 Standard, 3 Elevated, 4 Admin) becomes the single programmatic definition in
  one module; the YAML schema's divergent 1–5 range, the DB CHECK constraint, and the policy
  engine's READ/WRITE/ADMIN thresholds all derive from it. **BREAKING** for any config
  declaring `trust_level: 5` (none do today).
- **`setup_cloud.py` becomes a thin wrapper.** Its hardcoded `AGENTS` list is deleted; the
  roster, key flags, and identity map derive from `load_agents_config()`. Operator UX
  (key minting, `.env.cloud`, aliases, Railway push) is preserved.
- **CI invariant test.** A new test asserts, for every agent in `agents.yaml`: a profile row
  materializes with the declared trust level, an identity map entry exists, the profile name
  referenced actually resolves, and no enabled orphan profiles remain. This is the test that
  would have caught the agy/grok/pi half-onboarding.
- **Rollback plan** (required for the BREAKING items): the sync is guarded by
  `PROFILE_SYNC_ENABLED` (default on); setting it off restores pre-change runtime behavior,
  and disabled rows can be re-enabled with a single documented SQL statement. The identity-map
  widening rolls back by pinning `COORDINATION_API_KEY_IDENTITIES` explicitly (existing
  env-var precedence is preserved). The trust-scale migration ships with a paired down
  migration.

Out of scope (later roadmap phases): OpenBao secret topology (pca-02), session tokens /
deleting static keys (pca-03), posture resolution and credential injection (pca-04).

## Approaches Considered

### Approach 1: Startup sync — registry projected into DB on boot (Recommended)

The coordinator treats `agent_profiles` as a materialized view of `agents.yaml`: upsert on
startup, disable orphans, audit every mutation. Identity map derives from the full roster.

- **Pros**: drift becomes structurally impossible rather than procedurally avoided; no
  operator action to forget (the exact failure that occurred); disabled-not-deleted keeps
  history and honors auditability; works in every environment including CI.
- **Cons**: reverses the spec's "explicit action, additive only" stance (spec delta
  required); startup gains a DB write path that must be idempotent and concurrency-safe
  across multiple API workers; disabling orphans is a behavior change operators must know
  about.
- **Effort**: M

### Approach 2: Implement the spec as written — explicit `seed_profiles_from_config()`

Build the additive-only seeding function the spec already requires, invoked by the
setup-coordinator skill; keep the transport filter fix and CI test.

- **Pros**: smallest spec delta (implements existing requirements instead of modifying
  them); no startup write path; operator retains full control over when the DB changes.
- **Cons**: preserves the drift window — seeding can still be forgotten, which is the
  documented root cause (two changes shipped without it); additive-only means retired
  gemini/strands ghosts persist unless a human remembers; "single source of truth" remains
  aspirational between seed runs.
- **Effort**: S

### Approach 3: Runtime fallback chain — registry consulted at resolution time

Leave the DB alone; make `resolve_trust_level()` and profile lookup read `agents.yaml`
directly when the DB misses, DB winning when present.

- **Pros**: no migrations, no sync machinery, cheapest diff; registry values take effect
  immediately on file edit.
- **Cons**: two *live* authorities with precedence rules instead of one — the DB row and the
  YAML entry can still disagree silently (a stale DB row shadows a registry edit, inverting
  today's bug); per-request file reads or another cache layer on the hot auth path; ghost
  rows never cleaned; the "which source won?" question infects every future debugging
  session.
- **Effort**: S

### Recommended

**Approach 1.** Approach 2 re-implements the design whose failure motivated this change —
its own history (promised in March, still absent in August, forgotten across two shipped
changes) is the evidence against "explicit operator action" as a consistency mechanism.
Approach 3 trades one drift mode for a subtler one by keeping two live authorities.
Approach 1 is the only one under which the CI invariant is *structural*: if the registry
loads, the projections exist. Its startup-write cost is bounded (one idempotent upsert per
boot) and its orphan-disabling is precisely the auditable retirement path the current system
lacks.

### Selected Approach

Approach 1, selected by the operator at Gate 1 (2026-08-14) with prior structural decisions
from the planning conversation: roadmap-plus-phase-1 structure, `setup_cloud.py` rewritten
as a thin wrapper (not deleted until pca-03), SPIFFE-shaped naming reserved for pca-02+.

## Impact

**Specs** (delta files under `specs/`):

- `agent-identity` — MODIFIED: "Declarative Agent Configuration" (registry canonical for all
  transports), "API Key Identity Generation" (filter removal), "Profile Seeding from Config"
  (explicit-additive seeding replaced by startup sync with orphan disabling); ADDED:
  "Unified Trust Scale", "Registry Projection Invariant" (CI-enforced).
- `agent-coordinator` — MODIFIED: "Agent Profiles" (fail-loud resolution for known agents,
  trust-scale reference).

**Code**:

- `agent-coordinator/src/agents_config.py` — identity generation, new `sync_profiles()`,
  trust-scale module (or new `src/trust_levels.py`)
- `agent-coordinator/src/coordination_api.py` — startup hook, `resolve_trust_level()` fail-loud
- `agent-coordinator/src/profiles.py`, `src/policy_engine.py` — derive tier thresholds from
  the trust-scale module
- `agent-coordinator/database/migrations/` — new migration: trust CHECK constraint alignment,
  `enabled` semantics for orphan disabling (paired down migration)
- `agent-coordinator/scripts/setup_cloud.py` — roster derivation from registry
- `agent-coordinator/agents.yaml` — schema version note; no trust values change (all within 0–4)
- Tests: new `tests/test_registry_projection.py` (CI invariant), updates to
  `test_agents_config.py`, `test_profiles.py`, `test_coordination_api.py`

**Docs**: `agent-coordinator/CLAUDE.md` env-var section, `docs/guides/workflow.md` if it
references setup_cloud, roadmap files under `openspec/roadmaps/principal-credential-architecture/`.
