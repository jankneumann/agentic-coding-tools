# Contracts — none applicable

This change extends a pure Python library (`packages/system-one-decisions`)
with a live SDK call path. No HTTP API, no database schema, and no event
payload crosses a process boundary. Contract sub-types evaluated and why none
apply:

- **OpenAPI** — the package exposes Python functions, not an HTTP endpoint.
  The `typesafe_sdk` client it calls has its own vendor-owned contract, which
  this package does not re-specify.
- **Database** — no schema, no migration.
- **Events** — `decide()`'s new `event_sink` callback shape is specified as
  spec requirements and design decision D2 in `design.md`, not as a JSON
  Schema contract, for the same reason `decide_intent()`'s sink wasn't one in
  `ri-01`: it is a caller-supplied Python callable within one process, not a
  serialized event crossing a process boundary.
- **Type generation stubs** — not applicable; `decide()`'s signature and the
  real `typesafe_sdk` response types it returns are the interface, checked by
  this item's unit tests against the real SDK's shapes directly.
