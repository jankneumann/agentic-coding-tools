# Contracts — none applicable

This change introduces a pure Python library (`packages/system-one-decisions`)
with no HTTP API, no database schema, and no event payloads. Contract sub-types
evaluated and why none apply:

- **OpenAPI** — the package exposes Python functions, not an HTTP endpoint.
- **Database** — no schema, no migration.
- **Events** — `decide_intent`'s `event_sink` callback shape is specified as
  spec requirements and design decision D2 in `design.md`, not as a JSON Schema
  contract, because the sink is a caller-supplied Python callable within one
  process, not a serialized event crossing a process boundary.
- **Type generation stubs** — not applicable; the package's own `Decision`
  dataclass and function signatures are the interface, checked by the spec's
  scenarios and this item's unit tests directly.
