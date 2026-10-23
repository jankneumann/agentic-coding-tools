# Contracts: add-why-mode-to-explain-code-with-epistemic-tiers

No contract sub-types apply to this change:

- **OpenAPI:** none. `why_trace.py` is a local, read-only CLI with no HTTP surface.
- **Database:** none.
- **Events:** none.

Two interfaces change, and both are specified normatively in
`specs/skill-workflow/spec.md` rather than in a separate schema file:

- **The `why_trace.py` JSON document** (`schema_version: 1`). See requirement "Why Trace
  Script" and design D4. It has a single consumer, the explain-code reply contract, and
  it is pinned by `skills/tests/explain-code/test_why_trace.py`.
- **The optional `evidence_level` finding property.** See requirement "Review Finding
  Evidence Level". It is added to the existing contract file
  `openspec/schemas/review-findings.schema.json` and its install-assets mirror, so no
  new contract file is needed.
