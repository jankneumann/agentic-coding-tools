# Contracts: add-sandboxed-harness-execution

Frozen interface definitions for work-package execution.

| Artifact | Defines | Consumed by |
|---|---|---|
| `openapi/v1.yaml` | Coordinator additions: network-policy export (rendering input), per-dispatch identity issue/revoke | Tasks 3.9–3.12, backend renderers |
| `schemas/dispatch-spec.schema.json` | `DispatchSpec` — the single argument to `ExecutionBackend.run()` | Tasks 2.1–2.5, 4.2–4.3 |
| `schemas/dispatch-audit-event.schema.json` | Audit payload for every loud degradation and refusal on the dispatch path | All groups (D7: degradation is loud, never silent) |

Deliberately **not** defined here:

- **Inference key issuance** — owned by `add-coordinator-llm-gateway`
  (`contracts/openapi/v1.yaml`, `/llm/keys/issue` / `/llm/keys/revoke`). This change
  consumes that contract; redefining it would violate the one-resolver/one-source
  constraint the dispatch-governance epic imposes.
- **The isolation vocabulary** — pinned by `pin-isolation-contract` (dg-05), amended
  by task group 1 to carry `container` and `location`. The enums in
  `dispatch-spec.schema.json` mirror it and dg-05 remains authoritative.
- **Completion-ledger records** — owned by `build-structured-vendor-result-channel`
  (dg-02).
- **Provider APIs** (Daytona/E2B) — external; the backend adapter wraps the
  provider SDK and is bounded by `dispatch-spec.schema.json` on our side.
