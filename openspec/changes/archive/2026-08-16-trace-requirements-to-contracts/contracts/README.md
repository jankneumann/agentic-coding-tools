# Contracts — trace-requirements-to-contracts

## `traceability.schema.json`

The shape of a traceability block: citations from a contracted operation to the
requirements it serves, or an exclusion with a stated reason. This block covers
the **operation side** only — see `traceability-exclusions.schema.json` for the
requirement side.

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

## `traceability-exclusions.schema.json`

The requirement side of D4's "both directions accept exclusions". A
requirement with no operation has, by construction, no operation to hang an
exclusion on, so requirement exclusions live in their own per-capability file:
`openspec/contracts/<capability>/traceability-exclusions.yaml`, shape lifted
from `check_coverage_completeness.py`'s exclusion list.

That file's **existence is the capability's reverse-enforcement opt-in**
(design D13). Forward enforcement opts in per contract document (D6, keyed on
a traceability block's presence in the document); reverse enforcement opts in
per capability, keyed on this file. The two directions are different claims
with different owners, so each has exactly one switch. An empty `exclusions`
list is valid and means every requirement must be cited.

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

Per `openspec/contracts/README.md`, `traceability.schema.json` and
`traceability-exclusions.schema.json` are promoted to
`openspec/contracts/gen-eval-framework/schemas/` **while this change is in
flight**, not on archival, so no window of drift opens between the schema
consumers validate against and the one this change defines.

The promotion is owned by task 2.0 (wp-model), which also rewrites each
promoted copy's `$id` to its promoted location, extends
`cli-contract.schema.json` to admit `traceability` on flags, positionals, and
commands (it is rejected today by `additionalProperties: false`), and adds a
test that loads each promoted copy — the guard the predecessor's promotion
has, without which a promotion silently does not happen.
