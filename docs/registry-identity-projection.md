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
| `agent_profile_assignments` rows (agent_id → profile_id) | registry agent name and its `profile` | coordinator startup, after the profile phase |
| Trust level used by guardrails/policy | the profile the agent **resolves** to | per request |

Both tables matter, because `get_agent_profile()` reads the assignment first and only falls
back to "the oldest enabled profile of this `agent_type`" when there is none. Projecting
profiles alone leaves that fallback load-bearing: two agents sharing a type resolve by
`created_at`, regardless of what they declare. Projecting assignments makes the tiebreak
unreachable for registry agents. Rows the sync writes carry `assigned_by = 'registry_sync'`,
so they are distinguishable from the hand-written rows migration 018 left with `assigned_by`
NULL.

`transport` describes an agent's *preferred channel*, not its authorization boundary — the MCP
server falls back to the HTTP proxy when the local database is unreachable, so every declared
agent is a potential HTTP principal and every one gets an identity.

## Two things the sync deliberately does not do

**It does not touch role profiles.** The registry owns *harness identities* — things with a
transport that can be dispatched and authenticated. Profiles that represent a role rather than
a harness are named in an explicit unmanaged-profile allowlist and left alone. Today that is
`evaluator` (migration 026), and the classification was verified rather than assumed: migration
027's `claim_task` function contains live evaluator-specific logic (excluding an evaluator from
claiming evaluation tasks it submitted itself), so disabling that profile would break evaluation
task claiming. The other candidates were checked the same way and are genuinely dead —
`claude_code_reviewer` and `strands_local` have no reference anywhere outside the migration that
renamed them.

The projection invariant test asserts every enabled profile is either registry-declared or
explicitly unmanaged, so a future role profile that nobody classified fails CI rather than being
silently disabled.

**It does not delete profiles.** Profile rows for agents the registry no longer declares are set
`enabled = false` and retained, with a `profile_sync` audit event naming each one. Retiring a
harness should leave a trail, and disabling is reversible in one statement.

Stale *assignments* are the one exception: they are deleted, not disabled. The table has no
`enabled` column, and an assignment is a pointer rather than authorization state — the profile
it referenced is still retained and disabled, so nothing is lost. Each removal is audited with
the profile the pointer targeted, which is what makes it reconstructible.

## What the first sync will do

Measured against the migration history at the time this change landed:

| Action | Profiles |
|---|---|
| Created (declared in the registry, no row exists) | `antigravity_local`, `grok_local`, `pi_local` |
| Updated (row exists, reconciled to registry values) | `claude_code_local`, `claude_code_remote`, `codex_local`, `codex_remote` |
| Disabled (retired harness identities) | `claude_code_reviewer`, `gemini_local`, `gemini_remote`, `strands_local` |
| Left alone (unmanaged role profile) | `evaluator` |

The "created" row is the bug this change exists to fix: the three harnesses added by
`add-agy-grok-pi-harnesses` got dispatch configuration and no authorization state.

Migration 018 is worth reading alongside this table, because it is the previous attempt at the
same problem. Its header records the identical failure — "`claude-remote` got `claude_code_cli`
(trust 3) instead of `claude_code_web_implementer` (trust 2)" — and it fixed it by hand, adding
the then-missing local profiles and writing one explicit `agent_profile_assignments` row per
agent. That worked, and still works, for the roster as it stood in that migration. It did
nothing for any harness added afterwards, which is precisely why three of them arrived with no
profile at all. Hand-maintained rosters do not survive the next addition; that is the argument
for projecting from the registry instead.

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

**Restore an assignment the sync removed** — the audit event records the agent id and the
profile its pointer targeted, so the row can be rebuilt from the trail:

```sql
INSERT INTO agent_profile_assignments (agent_id, profile_id)
SELECT '<agent-id>', id FROM agent_profiles WHERE name = '<profile-name-from-audit>'
ON CONFLICT (agent_id) DO UPDATE SET profile_id = EXCLUDED.profile_id;
```

Note that re-adding an assignment while `PROFILE_SYNC_ENABLED` is still on will simply be
re-removed at the next boot, since the registry does not declare that agent. Turn the flag off
first if the restoration needs to persist.

Query what was disabled and when, from the audit trail:

```sql
SELECT created_at, parameters
FROM audit_log
WHERE operation = 'profile_sync'
ORDER BY created_at DESC
LIMIT 50;
```

**Revert the schema change** — migration `032_unified_trust_scale.sql` carries a paired down
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
