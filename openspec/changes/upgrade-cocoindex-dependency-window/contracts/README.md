# Contracts: upgrade-cocoindex-dependency-window

No machine-readable contracts apply. Sub-types evaluated:

- **OpenAPI** — no HTTP/MCP endpoint changes; `search_code` / `POST /search/code` request and
  response shapes are untouched.
- **Database** — no schema or migration changes. Chunk table and registry shapes are unchanged;
  only the pipeline fingerprint *value* changes, which existing registry columns already hold.
- **Events** — none emitted or changed.
- **Type generation** — nothing to generate.

The binding interface for this change is the dependency window itself (`pyproject.toml` pins,
`uv.lock`, `cli_models._PIPELINE_PAYLOAD`), specified in
`specs/code-search/spec.md` → *Coupled Upstream Dependency Window* and enforced by
`packages/code-search/tests/test_cocoindex_revision_compat.py`.
