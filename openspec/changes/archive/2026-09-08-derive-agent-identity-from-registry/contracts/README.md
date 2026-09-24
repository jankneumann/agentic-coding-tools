# Contracts — derive-agent-identity-from-registry

Contract sub-types evaluated for this change:

- **Database** — **applicable.** The trust-scale alignment modifies the `agent_profiles`
  CHECK constraint and formalizes `enabled` semantics for orphan disabling. See
  `db/schema.sql` (with paired down-migration statements).
- **Events** — **applicable.** Startup profile sync emits `profile_sync` audit events;
  the payload shape is the coordination boundary between the sync implementation and the
  registry-projection invariant test. See `events/profile-sync-audit.schema.json`.
- **OpenAPI** — **not applicable.** No endpoint is added or changes its request/response
  schema. `resolve_trust_level()`'s fail-loud path surfaces through existing error
  envelopes (500-class configuration fault, per design D3).
- **Generated type stubs** — **not applicable.** No cross-language interface is introduced;
  the trust-scale module is consumed only by Python code in the same package.
