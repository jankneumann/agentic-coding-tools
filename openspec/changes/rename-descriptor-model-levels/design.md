# Design — Rename descriptor model levels

## Context

One suffix, `*Descriptor`, currently names an element, a container, and a
document. This change makes the level legible from the name.

The design is deliberately small. Its entire job is to leave the namespace in a
settled state so that `derive-descriptors-from-contracts` can define document
archetypes without also performing a migration.

## Decisions

### D1 — `*Spec` names an element, `*Descriptor` names a document

**Decision.**

| Level | Suffix | Types after this change |
|---|---|---|
| One element, or a per-surface container of elements | `*Spec` | `EndpointSpec`, `McpToolSpec`, `CommandSpec`, `ServiceSpec` |
| A whole descriptor document | `*Descriptor` | `InterfaceDescriptor` |

`ServiceSpec` keeps container semantics under the `*Spec` suffix deliberately: it
describes one *surface* of a project, not the project. The document that
describes the project is `InterfaceDescriptor`.

**Why.** The distinction that matters to a reader is "is this the whole thing or
a part of it". Encoding it in the suffix makes every future addition
self-classifying.

### D2 — No freed name is reused in this change

**Decision.** All four old names become deprecation aliases pointing at their
renamed types. Nothing in this change defines a new type under a freed name.

**Why.** This is the property whose absence caused the extraction. When a change
both frees a name and reassigns it, there is a window in which the name's
meaning depends on which work package has run — and a verification step cannot
assert a stable fact about it. Concretely, the previous attempt had a gate at the
DAG root asserting `ToolDescriptor` no longer carried the legacy element fields,
while the type that gives it its new meaning was created by a package that
*depended on* the root. The gate could not pass; the DAG could not advance.

Here every old name has exactly one meaning throughout: "deprecated alias for the
renamed type". One rule, one gate, no wave-dependent state.

**Consequence for the consumer.** `derive-descriptors-from-contracts` occupies
`ServiceDescriptor` and `ToolDescriptor` *after* this lands. At that point it is
redefining a name that is a deprecated alias, not racing a rename. Its
DOWNSTREAM notice must say so, because a consumer that ignores the deprecation
warning here will silently get a different type there.

### D3 — The version bump covers every generated artifact

**Decision.** `CONTRACT_VERSION` goes 1 → 2, and all four artifacts
`scripts/generate_contract_schemas.py` writes are regenerated:
`interface-descriptor.schema.json`, `scenario.schema.json`,
`eval-report.schema.json`, and `VERSION`.

**Why.** The generator stamps `x-gen-eval-contract-version` into all three
schemas, so a bump changes every one — not only the descriptor schema whose
`$defs` titles are renamed. Scoping the change to one artifact would leave
`test_contract_schemas.py::TestNoDrift` failing on the other two.

### D4 — Aliases warn, and the gate proves both halves

**Decision.** Each alias must resolve *and* emit `DeprecationWarning` on access.
The verification asserts both.

**Why.** Presence alone is satisfied by a plain re-export that never deprecates,
which would leave consumers with no signal before removal. A warning alone is
satisfied by a broken alias. The pair is what makes the deprecation real.

## Risks

| Risk | Mitigation |
|---|---|
| A consumer imports a renamed type and breaks | Aliases for one release; `CONTRACT_VERSION` bump makes the break detectable rather than silent; DOWNSTREAM notice |
| The rename is mechanical but touches ~112 references, so a miss is easy | A gate scans `tests/` for any pre-rename name and fails on a hit; the suite is additionally run under `-W error::DeprecationWarning` |
| Consumers read the alias warning as "this name is going away" when it is in fact about to be **reused** with a different meaning | The DOWNSTREAM notice states the reuse explicitly; `derive-descriptors-from-contracts` repeats it when it lands |
| `ServiceSpec` is a container, not a leaf, so `*Spec` is slightly loose | Accepted and documented in D1: the meaningful line is whole-document vs. part-of-document |

## Open questions

- Is one release a long enough alias window? The consuming change reuses two of
  these names, which shortens the practical window for anyone tracking `main`.
