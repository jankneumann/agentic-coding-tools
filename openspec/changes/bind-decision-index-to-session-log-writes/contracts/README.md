# Contracts — bind-decision-index-to-session-log-writes

No contract sub-types apply. Evaluated:

- **OpenAPI** — no HTTP surface is introduced or modified.
- **Database** — no schema is introduced or modified.
- **Events** — no event payload is introduced or modified. The coordinator handoff payload
  written by step three is unchanged by this change.
- **Type generation** — nothing to generate; `PhaseWriteResult` keeps its existing fields.

The behavioural contract this change carries is the four-step ordering and the best-effort
guarantee, expressed as spec scenarios rather than a machine-readable interface. That is the
same convention `add-deterministic-context-drift-gates` and ri-08/ri-09 used for
producer-shaped work.
