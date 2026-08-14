# Registry-Derived Identity: Projection Model and Rollback

Phase 1 of the [`principal-credential-architecture`](../openspec/roadmaps/principal-credential-architecture/proposal.md)
roadmap. This document is the operator-facing companion to the change
`derive-agent-identity-from-registry`.

## The model in one paragraph

`agent-coordinator/agents.yaml` is the **only** place a human declares an agent's identity,
trust level, and capabilities. Everything the coordinator enforces at runtime is a mechanical
*projection* of that file: the API-key identity map, the `agent_profiles` table rows, and the
trust levels the policy engine and guardrails read. Adding a harness is one registry diff; CI
fails if any projection cannot be derived from it.

## What is projected, and when

| Projection | Derived from | When |
|---|---|---|
| API-key identity map (`{key: {agent_id, agent_type}}`) | every registry agent with a resolvable `api_key`, regardless of `transport` | at config load |
| `agent_profiles` rows (name, agent_type, trust_level, allowed_operations) | registry `profile`, `trust_level`, `capabilities` | coordinator startup, after migrations |
| Trust level used by guardrails/policy | the synced profile row | per request |

`transport` describes an agent's *preferred channel*, not its authorization boundary — the MCP
server falls back to the HTTP proxy when the local database is unreachable, so every declared
agent is a potential HTTP principal and every one gets an identity.

## Two things the sync deliberately does not do

**It does not touch role profiles.** The registry owns *harness identities* — things with a
transport that can be dispatched and authenticated. Profiles that represent a role rather than
a harness (today: `evaluator`, seeded by migration 026 and used by generator-evaluator work-queue
routing) are named in an explicit unmanaged-profile allowlist and are left alone. The projection
invariant test asserts every enabled profile is either registry-declared or explicitly unmanaged,
so a new role profile that nobody classified fails CI rather than being silently disabled.

**It does not delete.** Rows for agents the registry no longer declares are set
`enabled = false` and retained, with a `profile_sync` audit event naming each one. Retiring a
harness should leave a trail, and disabling is reversible in one statement.

## What the first sync will do

Measured against the migration history at the time this change landed:

| Action | Profiles |
|---|---|
| Created (declared in the registry, no row exists) | `codex_local`, `antigravity_local`, `grok_local`, `pi_local` |
| Updated (row exists, reconciled to registry values) | `claude_code_local`, `claude_code_remote`, `codex_remote` |
| Disabled (retired harness identities) | `claude_code_reviewer`, `strands_local`, plus `gemini_*` on any deployment where they were seeded |
| Left alone (unmanaged role profile) | `evaluator` |

The "created" row is the bug this change exists to fix, and it is one wider than the original
audit found. Migration 007 seeds five profiles; migration 019 attempts eight renames, three of
which (`codex_local_worker`, `gemini_local_worker`, `gemini_cloud_worker`) name rows that were
never seeded and are therefore silent no-ops. The consequence is that **`codex-local` never had
a profile either** — so a harness that predates the antigravity/grok/pi additions has also been
running at the default trust level 2 while its registry entry declared 3. Nothing failed,
because everything failed open. That is the whole argument for this change in one table.

## Fail-loud, and where it stops

A principal **absent** from the registry (an externally configured identity, a test fixture)
resolves to the configured default trust level, unchanged. A **registry-declared** agent whose
profile row is missing or disabled is a hard error plus an audit event, surfaced as a 500-class
configuration fault — the caller did nothing wrong; the projection machinery failed.

This asymmetry is the point of the change. The previous behavior returned the default trust
level for both cases, which is how three harnesses ran for weeks at trust 2 while their registry
entries declared 3.

Startup sync failure fails coordinator boot, deliberately unlike the surrounding startup steps
that warn and continue. An authorization projection that silently did not happen is worse than a
coordinator that did not start.

## Rollback

Each lever is independent; use the narrowest one that addresses the problem.

**Skip all sync writes** (restores pre-change runtime behavior):

```bash
PROFILE_SYNC_ENABLED=false
```

The coordinator logs a warning that the registry projection is not enforced and performs no
profile writes.

**Pin the identity map** (if the widened roster misbehaves) — explicit env vars still take
precedence over registry derivation:

```bash
COORDINATION_API_KEY_IDENTITIES='{"<key>": {"agent_id": "claude-remote", "agent_type": "claude_code"}}'
COORDINATION_API_KEYS='<key>'
```

**Re-enable profiles the sync disabled:**

```sql
UPDATE agent_profiles SET enabled = true WHERE name IN ('gemini_local', 'strands_local');
```

Query what was disabled and when, from the audit trail:

```sql
SELECT created_at, parameters
FROM audit_log
WHERE operation = 'profile_sync'
ORDER BY created_at DESC
LIMIT 50;
```

**Revert the schema change** — migration `031_unified_trust_scale.sql` carries a paired down
block at the bottom of the file.

## Regenerating cloud configuration

`scripts/setup_cloud.py` derives its roster from the same registry (it no longer carries its
own agent list). It now imports coordinator modules, so run it under the project environment:

```bash
uv run --project agent-coordinator python agent-coordinator/scripts/setup_cloud.py --domain coord.example.com
```

## Where this is going

Static API keys are still the coordination credential — they have simply stopped being
hand-maintained in two places. Roadmap items `pca-02` through `pca-04` move per-agent secrets
into OpenBao with least-privilege paths, replace static keys with short-lived issued session
tokens, and unify trust, isolation, and credential scope into a single per-dispatch posture.
`setup_cloud.py` is scheduled for deletion at `pca-03`.
