# Contracts — ownership-map

Contract sub-types evaluated for this change:

- **JSON Schema (configuration artifacts)** — **applicable.** Two schemas are the coordination
  boundary between the work packages: `schemas/owners.schema.json` (the ownership map
  `openspec/owners.yaml`, consumed by `wp-resolver` and `wp-codeowners`) and
  `schemas/human-principals.schema.json` (the `humans:` block of `agents.yaml`, consumed by
  `wp-registry` for the coordinator's inline mirror and by `wp-resolver` for the skills-side
  reader). The copies here are the drafts the plan was written against; `wp-contracts` promotes
  them to `openspec/schemas/` and `skills/ownership-runtime/install_assets/openspec/schemas/`,
  and a byte-identity test pins all three copies (design D2, D12). Live code references the
  promoted paths only, per `openspec/contracts/README.md`.
- **OpenAPI** — **not applicable.** No HTTP endpoint is added or changed; the resolver is an
  in-process library and the coordinator gains no route. The `work-packages.yaml` `openapi`
  block therefore points at this README, following the house convention from
  `derive-agent-identity-from-registry`.
- **Database** — **not applicable.** Human principals are not persisted; no migration.
- **Events** — **not applicable.** No audit event or bus message is emitted; the check's output
  is a CLI report (`--json`), whose shape is documented in `design.md` D9 rather than contracted
  here because nothing machine-consumes it yet (`ri-09` will decide whether to promote it).
- **Generated type stubs** — **not applicable.** Single-language (Python) surface.
