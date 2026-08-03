# Independent plan review: expose-fail-closed-semantic-code-search

Read these artifacts as immutable input:

- `proposal.md`
- `design.md`
- `tasks.md`
- `specs/code-search/spec.md`
- `contracts/README.md`
- `contracts/openapi/v2.yaml`
- `work-packages.yaml`

Review specification completeness, OpenAPI consistency, exact-index
correctness, scope security, startup/lifecycle ownership, HTTP/MCP/proxy
parity, capability truthfulness, resilience, observability, compatibility,
performance bounds, task coverage, and work-package validity.

Pay special attention to these invariants:

1. No legacy repo-slug table may be query-authoritative.
2. Revision, provider, or scope mismatch returns zero hits before embedding
   whenever determinable.
3. Scope resolution never fails open.
4. `CAN_CODE_SEARCH` is body-aware and never inferred from route/tool presence.
5. Optional semantic infrastructure cannot fail global coordinator readiness.
6. Direct MCP does not reuse async resources created in another event loop.

Return only JSON conforming to
`openspec/schemas/review-findings.schema.json`, with:

- `review_type: "plan"`
- `target: "expose-fail-closed-semantic-code-search"`
- a populated `reviewer_vendor`
- findings containing `id`, `axis`, `severity`, `type`, `criticality`,
  prefixed `description`, `resolution`, and coherent `disposition`

Use `Critical:` for blocking issues, `Nit:` for required minor corrections,
`Optional:` and `FYI:` for accepted advice, and `severity: none` for positive
observations.
