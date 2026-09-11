# Contracts — add-supervisor-candidate-work-digest

Evaluated sub-types:

- **OpenAPI** — none. No HTTP surface.
- **Database** — none.
- **Events** — `rubric-score.schema.json` and `digest.schema.json` are the reviewed source
  contracts and are installed byte-identically as
  `openspec/schemas/supervise-rubric-score.schema.json` and
  `openspec/schemas/supervise-digest.schema.json` so archival cannot break runtime lookup.
- **Persistence extension** — canonical `openspec/schemas/supervisor-record.schema.json`
  and `supervisor-record-mirror.schema.json` gain decision metadata (`roadmap_ref`,
  `route`, `until`, `reason`) with decision-specific conditions.
- **Type generation** — none.

Consumed contracts (not owned here): `openspec/schemas/candidate-work.schema.json`, the
`back_edge.digested_stubs` envelope introduced by ri-05, the roadmap-runtime strict roadmap loaders and archived-change registry, and
`skills/refine-roadmap/templates/refinement-request.yaml`.

Coordination boundary: `wp-digest-module` reads schema-valid rubric documents;
`wp-rubric-prompt` produces only that contract. They meet at the stable rubric schema.
