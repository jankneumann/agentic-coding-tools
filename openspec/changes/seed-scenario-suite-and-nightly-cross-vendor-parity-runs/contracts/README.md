# Contracts — seed-scenario-suite-and-nightly-cross-vendor-parity-runs

Sub-types evaluated:

| Sub-type | Applies? | Artifact |
|---|---|---|
| OpenAPI | No — no new or changed HTTP endpoint. Capability gaps are written through the existing coordinator `POST /memory/store` (`MemoryStoreRequest`), unchanged. | — |
| Database | No — no migration; the results store is an append-only JSONL file (design D2). | — |
| Events / payloads | Yes — three file/payload formats cross package or process boundaries. | see below |
| Generated types | No — producers are pydantic models in `packages/agent-scenarios`; schemas below are the language-neutral contract. | — |

## Payload contracts

- `schemas/results-record.schema.json` — one JSONL line of the results store
  (`record_type: result | run`). Producer: `results_store.py`; consumers:
  `results_cli.py` and any future coordinator-backed `ResultsStore`.
- `schemas/capability-gap-entry.schema.json` — the `MemoryStoreRequest` body the gap
  emitter sends (and spools). Producer: `gap_emitter.py`; consumer:
  `/improve-harness` (`analyze_failures.py`) via `POST /memory/query`.
  `examples/capability-gap-entry.example.json` is the shared fixture both the
  producer test (packages/agent-scenarios) and the consumer test
  (skills/tests/improve-harness) assert against.
- `schemas/nightly-config.schema.json` — the operator-authored nightly config.

Implementation promotes these schemas into
`packages/agent-scenarios/src/agent_scenarios/schemas/` (package-owned source of
truth); package tests validate against the package copy, so no test pins this change
directory's path. The skills-side consumer test keeps its own copy of the example
payload under `skills/tests/improve-harness/fixtures/`.
