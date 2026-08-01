# Contracts: harden-review-consensus-and-recovery

This change modifies internal JSON/Python boundaries rather than HTTP, database, or event interfaces. The frozen revision-2 coordination contracts are:

- `consensus-policy.schema.json` — complete revision-2 consensus boundary: stable groups, match provenance, adjudication ledger entries, quorum, exact summary counts, and compatibility aliases.
- `review-attempt.schema.json` — one logical review request and its bounded attempt chain, including terminal/quorum invariants, sanitized diagnostics, and routing/thinking provenance across CLI, SDK, async polling, and an optional replacement vendor.

Production implementation remains authoritative in `openspec/schemas/consensus-report.schema.json`, its install-asset copy, and the dataclasses/config models in the transport-neutral review helpers, `review_dispatcher.py`, and `agents_config.py`. Package implementations MUST validate producer and consumer fixtures against these frozen contracts. Per-source disposition is authoritative; `vendor_dispositions` is only a deprecated per-vendor summary. `validate_consensus_report()` enforces canonical/legacy alias equality, `received <= requested`, distinct eligible-vendor receipt, and `met == (received >= minimum_required)`. `validate_review_attempt_chain()` enforces unique monotonic indexes, fallback membership/deduplication, one monotonic vendor deadline, legal vendor transitions, terminal-vendor equality, and no attempts after success. Every producer and consumer calls these validators before persistence or quorum evaluation. No OpenAPI, SQL, generated language type, event, or mock contract applies.

The authoritative adjudication ledger is stored at `openspec/changes/<change-id>/reviews/adjudications.json` and written atomically. Entries are keyed by stable `group_id` plus the exact sorted concern fingerprints. The synthesizer may apply a prior entry only when both still match; unknown or stale entries fail closed. Review vendors and the synthesizer cannot originate `accepted_risk` authorization. Its `approval_ref` must resolve through an injected trusted-approval resolver to a human coordinator audit record, GitHub approval, or signed local record.

Validate with:

```bash
uv run --project skills python -m json.tool openspec/changes/harden-review-consensus-and-recovery/contracts/consensus-policy.schema.json
uv run --project skills python -m json.tool openspec/changes/harden-review-consensus-and-recovery/contracts/review-attempt.schema.json
```
