# Contracts — trace-requirements-to-contracts

## `traceability.schema.json`

The shape of a traceability block: citations from a contracted operation to the
requirements it serves, or an exclusion with a stated reason.

Carried two ways, because the two contract archetypes already spell their
extensions differently:

| Archetype | Location |
|---|---|
| Service (OpenAPI) | `x-traceability` on an operation object |
| Tool (CLI contract) | `traceability` on a flag, positional, or command |

Both parse into one model, following the precedent `x-gen-eval-surface` set in
`derive-descriptors-from-contracts`.

### Why `oneOf` rather than allowing both keys

An operation carrying both `requirements` and `excluded` states that it has a
purpose and that it has none. Permitting it would force the gate to pick a
winner, and whichever it picked would be a silent decision about the operation's
justification — the failure mode `_merge_schemas` was fixed for in the
predecessor change.

### Why `requirements` has `minItems: 1`

An empty list is not "no requirements"; it is an exclusion written without a
reason, spelled differently. The gate cannot distinguish `requirements: []` from
an author who meant to fill it in later, so the schema refuses the shape rather
than leaving the gate to guess.

## Not in this directory

**No OpenAPI document.** This change adds no HTTP surface. The coordinator
contract it authors (task 5.1) belongs under
`openspec/contracts/agent-coordinator/openapi/` — the durable location — not
here, because it describes a system that exists rather than a change to one.

That directory holds one or several documents. Because completeness is
evaluated per capability (D10) rather than per file, splitting the coordinator's
surface into `locks.yaml`, `work-queue.yaml` and so on costs nothing in rigour
and is how a capability opts in one subsystem at a time.

**No report schema change.** The gate writes no report into
`eval-report.schema.json`. It is a standalone check with an exit code, in the
shape of `check_coverage_completeness.py`. If a machine-readable output is
wanted later it is additive and gets its own version consideration.

## Promotion

Per `openspec/contracts/README.md`, `traceability.schema.json` is promoted to
`openspec/contracts/gen-eval-framework/schemas/` **while this change is in
flight**, not on archival, so no window of drift opens between the schema
consumers validate against and the one this change defines.
