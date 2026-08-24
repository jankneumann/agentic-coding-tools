# Design — derive-agent-identity-from-registry

Phase 1 of the `principal-credential-architecture` roadmap (pca-01). Scope: make
`agents.yaml` canonical and derive all identity/trust projections from it. No OpenBao
topology changes (pca-02), no auth-mechanism changes (pca-03), no posture resolution (pca-04).

## Context

Full failure analysis lives in the roadmap proposal
(`openspec/roadmaps/principal-credential-architecture/proposal.md`). The short version:
four authorization layers drift independently because every one of them fails open, and the
spec's `seed_profiles_from_config()` requirement (2026-03-01) was never implemented — the
gap that let `add-agy-grok-pi-harnesses` ship dispatch plumbing without authorization
plumbing, leaving three harnesses at silent trust 2 with no canonical identities.

## Decisions

### D1 — `agent_profiles` is a materialized view; sync runs at startup

The DB table stops being a co-equal authority. Coordinator startup upserts one row per
registry agent (keyed by declared `profile` name) and the table is thereafter read-only from
the operator's perspective. Explicit-seeding (the spec's original design) was rejected
because its own five-month history of non-implementation across two shipped changes is the
evidence against operator-invoked consistency; runtime fallback (registry consulted on DB
miss) was rejected because it creates two *live* authorities whose precedence must be
debugged forever. Recorded as the Gate 1 selection in `proposal.md`.

### D2 — Orphans are disabled, never deleted; every sync mutation is audited

Rows whose profile name no registry entry declares get `enabled = false`. This reverses the
spec's "additive only" posture deliberately: ghost profiles (`gemini_*`, `strands_*`) are
live authorization state for retired principals — exactly what an attacker or a stale
script would use. Disabling rather than deleting preserves history and makes rollback a
one-line re-enable. Each insert/update/disable emits an `audit_log` event
(`operation = "profile_sync"`), so the projection is observable, satisfying the
Governance-layer requirement that authorization changes leave a trail.

**Amended at implementation — not every profile is a harness identity.** Reading the
seeded rows revealed a class the original decision would have broken: `evaluator`
(migration `026_evaluator_profile.sql`, `agent_type: evaluator`, exercised by
`tests/test_evaluator_profile.py` and the generator-evaluator work-queue routing) is a
**role** profile, not a harness identity. It has no CLI, no transport, and no business
being in `agents.yaml` — but a blanket "disable everything the registry doesn't declare"
would disable it and silently break evaluation task assignment. That is the same
class of collateral damage this change exists to prevent, arriving from the other
direction.

The registry therefore owns *harness-identity* profiles, and a short, explicit
`UNMANAGED_PROFILES` allowlist names the role profiles it deliberately does not own.
Orphan disabling skips that set. The allowlist lives beside `sync_profiles()` with a
comment explaining the distinction, and the Registry Projection Invariant asserts every
enabled profile is either registry-declared **or** on the allowlist — so a future role
profile that nobody thought about still fails CI rather than being quietly disabled or
quietly tolerated. Rejected alternative: adding `evaluator` to `agents.yaml`, which would
mean the registry claims to describe agents it cannot dispatch, authenticate, or assign a
transport to.

### D3 — Fail-loud is scoped to *registry-declared* agents

Two miss cases split:

- Principal not in the registry (env-var-configured externals, tests): default trust —
  unchanged, because the registry cannot be authoritative for principals it doesn't name.
- Registry-declared agent with a missing/disabled profile row: hard error + audit event.
  A known agent with a broken projection means the projection machinery itself failed —
  continuing at a default trust level is precisely the fail-open drift this change removes.

`resolve_trust_level()` gains the registry check; the error surfaces as a 500-class
response (configuration fault), not a 403 (the caller did nothing wrong).

### D4 — One trust-scale module; validators derive from it

New `agent-coordinator/src/trust_levels.py` defining the existing documented scale
(0 Untrusted, 1 Limited, 2 Standard, 3 Elevated, 4 Admin) as an `IntEnum` plus
`MIN_TRUST` / `MAX_TRUST`. The `agents.yaml` JSON schema bounds, the policy engine's
read/write/admin thresholds, and the migration's CHECK constraint test all reference it.
The YAML schema's current 1–5 range is a bug (DB constraint is 0–4); no live config uses
0 or 5, so tightening is a no-op for data and **BREAKING** only for hypothetical configs.

### D5 — Transport does not gate identity

`get_api_key_identities()` iterates all agents, not `transport == "http"`. Rationale: the
MCP server's HTTP-proxy fallback makes every local agent an HTTP principal in practice
(this planning session itself authenticated that way). `transport` remains as dispatch
metadata only.

### D6 — Duplicate resolved API keys become a load error

Current behavior logs a warning and last-writer-wins — an identity-confusion bug waiting to
happen (two principals, one key, wrong attribution in audit logs). With the identity map now
covering the full roster, collisions get likelier; fail at load with both agent names.

### D7 — `setup_cloud.py` keeps its UX, loses its roster

The hardcoded `AGENTS` list and per-agent `--<agent>-key` flag table are replaced by
iteration over `load_agents_config()`; key-flag names derive from agent names. Operator
workflow (`.env.cloud`, aliases, Railway push, `--verify`) is unchanged. The script is
scheduled for deletion in pca-03 when static keys die — documented in its module docstring
so nobody invests in it further.

### D8 — Rollback levers ship with the change

- `PROFILE_SYNC_ENABLED=false` skips all sync writes (logged warning), restoring pre-change
  runtime behavior.
- Explicit `COORDINATION_API_KEY_IDENTITIES` still overrides registry derivation (existing
  precedence), pinning the identity map if the widened roster misbehaves.
- The trust-constraint migration ships with a paired down migration.
- Disabled orphan rows re-enable with one documented `UPDATE`.

### D9 — Sync concurrency via idempotent upserts (amended at implementation)

Multiple API workers can boot simultaneously.

**Original decision**: take a Postgres advisory lock (`pg_advisory_lock`) around the sync
transaction. **Amended during implementation** — that lock is not reachable through this
codebase's DB abstraction, for three independent reasons found by reading
`src/db_postgres.py`:

1. `DatabaseClient` exposes only `rpc` / `query` / `insert` / `update` / `delete`; there is
   no raw-SQL escape hatch.
2. `rpc()` emits `SELECT fn(name := $1)` — *named* parameter syntax, which Postgres
   built-ins like `pg_advisory_lock(bigint)` do not accept (they have no parameter names).
3. Session-scoped advisory locks are unsafe over a connection pool: `pool.acquire()` hands
   each call a different connection, so the lock and its release can land on different
   sessions.

**Amended decision**: correctness comes from idempotence, not mutual exclusion. Profile
upserts are `INSERT … ON CONFLICT (name) DO UPDATE` and orphan disabling is a single
`UPDATE … WHERE name <> ALL($1) AND enabled = true`. Both are safe to run concurrently and
converge on the same state, which is what the spec's "idempotent and safe under concurrent
startup" requirement actually demands. Where the sync needs per-mutation audit detail
(old/new values), the migration defines SQL functions that perform the mutation and RETURN
what changed, called through `db.rpc()`; those functions may take `pg_advisory_xact_lock`
internally — a *transaction*-scoped lock is safe on a pooled connection because it releases
with the implicit transaction — purely to avoid duplicate audit events when two workers boot
at the same instant. Duplicate audit events are cosmetic, not corrupting, so this is a
refinement rather than a requirement.

### D11 — The registry projects assignments too, because assignments are what resolve

Added after the profile projection landed. Projecting `agent_profiles` alone is not sufficient
for the change's own claim ("every registry agent resolves to its declared trust"), because
`agent_profiles` is not what resolution reads first.

`get_agent_profile(p_agent_id, p_agent_type)` (migration 007) resolves in two steps: an explicit
`agent_profile_assignments` row for the agent id, and failing that a fallback on
`agent_type` with `ORDER BY created_at ASC LIMIT 1`. When two agents share an `agent_type` and
neither has an assignment, the **oldest** profile row wins regardless of declared trust.

Migration `018_agent_profile_assignments.sql` already diagnosed and fixed exactly this, by hand:
its header records `claude-remote` resolving to `claude_code_cli` (trust 3) instead of
`claude_code_web_implementer` (trust 2), and it wrote one assignment row per agent for the
six-agent roster of the time. That fix is correct and still holds for those agents. It simply
does not extend to anything added later — `antigravity-local`, `grok-local` and `pi-local` have
profile rows but no assignments, and resolve correctly today only because each happens to be the
sole profile of its `agent_type`. A future `grok-remote` reintroduces the 018 bug verbatim.

So migration 018 is a second hand-maintained roster, the same species of artifact as
`setup_cloud.py`'s `AGENTS` list (D7), and it survives for the same reason: nothing failed when
it went stale. `sync_profiles()` therefore projects assignments as well, which makes the
`created_at` tiebreak unreachable for registry agents rather than merely unlucky.

Two sub-decisions:

- **Stale assignments are deleted, not disabled** — deliberately unlike D2's rule for profiles.
  The table has no `enabled` column, and an assignment is a *pointer*, not authorization state:
  the profile it referenced is still retained and disabled, so nothing is lost. Each removal is
  audited with the profile name it pointed at, keeping the action reconstructible.
- **The invariant now asserts through resolution, not row existence.** The original checker
  looked profiles up by name, which is why it certified a projection that resolution could still
  get wrong. Checking the row exists is a weaker claim than checking the agent reaches it, and
  only the weaker one was tested.

### D12 — Enforce the claim at runtime, not only in CI (corrects D11)

An adversarial security review after D11 landed found that the change's central claim —
"every registry agent resolves to its declared trust" — was enforced by the CI invariant and
**not** by the runtime gate. Two defects, both confirmed in code:

**The gate checked "a profile resolved", not "the declared profile resolved."**
`resolve_trust_level()` loaded `registry_entry.profile` and never compared it to
`profile.name`. A registry agent resolving to a different, higher-trust profile was accepted
silently. This is precisely the weaker claim D11 rewrote the invariant checker to stop
making; only the checker was fixed.

**Retiring an agent escalated it.** The success branch ran *before* the "not in the registry"
branch, so a decommissioned agent kept resolving — through the `agent_type` fallback, to
whatever sibling profile survived. Removing `codex-remote` disables `codex_remote` (trust 2)
and deletes its assignment, after which the fallback lands on `codex_local` at trust 3,
crossing `MIN_ADMIN_TRUST` and unlocking `force_push` / `delete_branch` / `cleanup_agents` /
`rollback_policy`.

That second defect was **introduced by D11's own sub-decision**, whose reasoning was wrong:
deleting a pointer that *constrains* resolution does not lose information, it *relaxes*
resolution. Before the assignment projection existed, the stale assignment row pinned the
retired agent at trust 2. "A pointer is not authorization state" is false whenever the
fallback behind it is more permissive than the pointer.

The corrected rule uses `ProfileResult.source`, which the SQL function already returns:

- **Registry-declared agent** — the resolved `profile.name` must equal the declared
  `profile`; a mismatch is a projection failure (audit + `TrustResolutionError`).
  `source == 'assignment'` is deliberately *not* also required, because with
  `PROFILE_SYNC_ENABLED=false` or before the first sync there are no assignments and a
  correct name match through the fallback is still correct.
- **Non-registry principal** — a resolved profile counts only when `source == 'assignment'`,
  i.e. a binding somebody deliberately created. Anything reached through the `agent_type`
  fallback yields the default trust level.

The resolver also moved to `src/trust_resolution.py` because there was more than one copy of
it: `work_queue.py` carried a verbatim pre-change duplicate that still failed open, so a
registry agent with a broken projection was denied on the HTTP path and silently granted
trust 2 on the queue path. One implementation, two call sites.

**Standing lesson for this roadmap**: a CI invariant proves the *projection* is correct; it
says nothing about whether the *enforcement point* consults it. Both halves need the same
test.

### D10 — OpenBao code is untouched

`_resolve_api_key_from_openbao()` and `bao_seed.py` keep their current (flawed) behavior;
fixing the shared-secret/shared-path topology is pca-02's entire scope. Phase 1 must remain
shippable with no OpenBao deployed. The identity-generation refactor keeps the OpenBao
resolution hook exactly where it is.

## Risks

- **Startup write path**: a bad registry now blocks boot. Mitigated by D8's flag and by the
  registry-projection CI test catching bad registries before deploy.
- **Widened identity map**: local-agent keys become accepted HTTP credentials wherever the
  registry's `${VAR}`s resolve. This is the *intended* semantic (they already are, via
  setup_cloud env vars), but the diff makes it visible; per-agent key rotation is the
  operator action if any local key was shared or leaked.
- **`allowed_operations` derivation**: capabilities → operations mapping must reproduce the
  operation lists the hand-written migrations granted, or agents lose abilities silently.
  The mapping table is data-driven and covered by an explicit regression test comparing
  against the operations currently granted to `claude_code_local`.
