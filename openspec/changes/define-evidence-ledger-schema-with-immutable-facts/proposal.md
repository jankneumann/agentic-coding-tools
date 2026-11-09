# Define evidence ledger schema with immutable facts

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `define-evidence-ledger-schema-with-immutable-facts`
> Effort: M
> Priority: 1

## Summary

Add a versioned evidence-ledger.schema.json covering facts (id, kind, source, gathered_by, host, time_window, tool_version, role variable|control), signals derived from variable/control fact pairs, and hypotheses with cites, optional components, and status. Ship a deterministic validator module that enforces schema conformance and fact immutability, routing disputed facts through reverify_request entries.

## Dependencies

- None

## Acceptance Outcomes

- The schema validates a fixture ledger containing variable and control facts, a derived signal, and a cited hypothesis.
- The validator rejects a ledger revision in which a previously recorded fact's fields were edited in place, and accepts the same dispute expressed as a reverify_request plus a new fact.
- Signals are classified as signal or noise and each references exactly one variable fact and one control fact.
- Validator tests live under skills/tests/ and resolve any OpenSpec paths via change_dir().

## Rationale

Every later capability (debugging rewrite, eliminative review, collect-facts, gap taxonomy, regression scenarios) consumes this ledger, and the proposal's core gap is the missing schema that ties hypotheses to facts. Immutability is a hard constraint and must be enforced at the foundation.
