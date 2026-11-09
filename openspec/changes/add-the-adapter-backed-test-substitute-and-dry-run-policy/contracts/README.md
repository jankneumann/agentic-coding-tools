# Contracts — none applicable

This change extends a pure Python library (`packages/system-one-decisions`)
with test-only helpers and a `dry_run` parameter. No HTTP API, no database
schema, and no event payload crosses a process boundary.

- **OpenAPI** — the package exposes Python functions, not an HTTP endpoint.
- **Database** — no schema, no migration.
- **Events** — no new event shape; `dry_run` changes control flow only.
- **Type generation stubs** — not applicable; `decide()`'s new parameter and
  the `system_one_decisions.testing` helpers are the interface, checked by
  this item's unit tests directly.
