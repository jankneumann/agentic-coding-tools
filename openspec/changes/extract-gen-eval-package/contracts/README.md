# Contracts — extract-gen-eval-package

This change is a **packaging / extraction** change. It does not introduce or modify external interfaces. The four contract sub-types were evaluated; none apply:

| Sub-type | Applies? | Why not |
|---|---|---|
| OpenAPI | No | No new HTTP endpoints. The existing `/gen-eval/*` endpoints in `agent-coordinator` are preserved bit-for-bit — only the underlying import path changes. The MCP service module's response shapes are unchanged. |
| Database | No | No schema changes. gen-eval's optional db client (`gen_eval.clients.db_client`) is a read-only client that asserts state in user-defined consumer databases — it does not own any schema. |
| Events | No | gen-eval does not emit or consume any inter-service events. |
| Type generation | No | No OpenAPI / GraphQL / proto source from which to generate types. The package's public API surface is defined by `gen_eval/__init__.py` and is exercised through normal Python imports. |

## What *is* the contract this change establishes?

Not an interface in the OpenAPI / schema sense — but the change does establish a **distribution contract** captured in the spec delta at `specs/gen-eval-framework/spec.md`:

- The package is importable as `gen_eval` (not `evaluation.gen_eval`).
- The package is installable via `uv add` from a relative path, git URL, or PyPI.
- The base install is pure-Python; MCP capability requires the `[mcp]` extra.
- The package ships only framework artifacts; consumer descriptors / manifests / scenarios stay in consumer repos.
- The package documents its consumer-adoption path via `examples/agentic-assistant-quickstart.md`.

These are tested by the verification block in `design.md` (specifically the "Static", "Build", and "CLI smoke" verifications) and by tasks 1.1, 2.1, 3.2, 3.3 in `tasks.md`.

## Future contract surface (out of scope for this change)

When this package is later published to PyPI, that change will introduce an OpenAPI-equivalent contract surface in the form of:
- Semantic-version policy
- A `CHANGELOG.md` with breaking-change call-outs
- A deprecation policy for `gen_eval.*` symbols

Those become real contracts the moment an external (non-Jan-owned) repo depends on the package. Tracking note: the PyPI-publishing follow-up change must add these.
