# Contracts — ledger-driven-review-convergence

No HTTP API, database schema, or pub/sub events. The coordination boundary is
the on-disk gate-time ledger that `converge()`, compact, and later
`ambient-review-ledger` must share.

## Contract sub-types evaluated

| Sub-type | Applies? | Notes |
|----------|----------|-------|
| OpenAPI | No | No HTTP endpoints. |
| Database | No | Ledger is a change-local file, not a coordinator table. |
| Events | No | Park/compact are file writes. |
| File format | **Yes** | Ledger and parked-disagreement documents. |

## Files

- [`review-ledger.schema.json`](review-ledger.schema.json) — `.review-ledger/ledger.json`.
- [`parked-disagreements.schema.json`](parked-disagreements.schema.json) —
  `reviews/parked-disagreements.json`.

`ambient-review-ledger` SHALL reuse `review-ledger.schema.json` rather than
fork it.
