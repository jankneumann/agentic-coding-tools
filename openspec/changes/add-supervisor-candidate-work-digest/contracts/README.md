# Contracts — add-supervisor-candidate-work-digest

Evaluated sub-types:

- **OpenAPI** — none. No HTTP surface; the coordinator is reached only through the
  existing handoff write that change 2 already contracts.
- **Database** — none.
- **Events** — two file-carried JSON Schemas under `schemas/`:
  - `rubric-score.schema.json` — the only output the rubric sub-agent may produce:
    per-stub five-factor scores with justifications, plus the fingerprint they were
    scored under. `digest.py rank` rejects anything else.
  - `digest.schema.json` — `openspec/supervise/digest.json`, the ranked digest with
    factor breakdown, mechanical signals, and section assignment.
- **Type generation** — none.

Consumed contracts (not owned here): `openspec/schemas/candidate-work.schema.json`
(ri-11), `contracts/schemas/supervisor-record.schema.json` from
`extend-handoff-document-with-supervisor-record` (`back_edge.digested_stubs`), and
`skills/refine-roadmap/templates/refinement-request.yaml` (the `add` op shape
`stub-to-request` emits).

Coordination boundary: `wp-digest-module` writes `digest.json` and reads
`rubric-score` files; `wp-rubric-prompt` produces a prompt whose only valid output is
a `rubric-score` document. They meet only at that schema.
