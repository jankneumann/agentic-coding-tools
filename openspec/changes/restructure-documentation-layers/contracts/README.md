# Contracts: restructure-documentation-layers

Sub-types evaluated per plan-feature Step 7:

- **OpenAPI** — not applicable. The change introduces or modifies no HTTP or MCP endpoint.
- **Database** — not applicable. No schema, migration, or seed data.
- **Events** — not applicable. No event payloads.
- **Type generation** — not applicable. Nothing to derive from the above.

The only machine-readable interface this change adds is the document-metadata block
(`layer`, `owns`, `sources`, `verified_against`) described in `design.md` D4 and pinned by
`skills/tests/docs/test_doc_structure.py`. It is a documentation convention, not a service
contract, so it is defined in `docs/guides/documentation.md` rather than here.

Consuming skills treat a `contracts/` directory containing only this README as
"no contracts applicable".
