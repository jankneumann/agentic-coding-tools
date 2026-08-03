# Rename descriptor model levels: `*Spec` for elements, `*Descriptor` for documents

## Why

`*Descriptor` currently means three different things in
`packages/gen-eval/src/gen_eval/descriptor.py`:

| Name | Level it names | Line |
|---|---|---|
| `EndpointDescriptor` | one HTTP endpoint | `:29` |
| `ToolDescriptor` | one MCP tool | `:41` |
| `CommandDescriptor` | one CLI command | `:50` |
| `ServiceDescriptor` | a container of the above, for one surface | `:67` |
| `InterfaceDescriptor` | the whole YAML document | — |

One suffix, three levels. A reader encountering `ServiceDescriptor` cannot tell
from the name whether it is an element, a container, or a document.

This was surfaced by `derive-descriptors-from-contracts`, which needs
`ServiceDescriptor` and `ToolDescriptor` for **document-level** archetypes and
found both names already taken with unrelated meanings. That change originally
carried the rename as its Phase 0. It was extracted here because the rename
turned out to be the dominant source of defects in that plan — not because the
rename is wrong, but because coupling a namespace migration to a feature made
both harder to verify.

### Why it was extracted

Three consecutive review rounds on `derive-descriptors-from-contracts` produced
blocking findings that all traced to one shape: the rename freed two names that
the same change then immediately reused, at a work-package wave boundary.

Verification could not express the intermediate state. A gate asserting
"`ToolDescriptor` no longer means the old thing" ran in the wave that performs
the rename — but the new meaning is created in the *next* wave, by a package
that depends on it. The gate could not pass. Reviewers found four variants of
this before the pattern was recognised.

Separating the two changes removes the boundary entirely. Here, the rename is
mechanical and has no reuse: four names move, all four keep aliases, nothing
is redefined. The consuming change then starts from a settled namespace.

## What Changes

Adopt a two-level naming scheme and rename the existing models to fit it.

| Level | Suffix | Types |
|---|---|---|
| One element, or a per-surface container of elements | `*Spec` | `EndpointSpec`, `McpToolSpec`, `CommandSpec`, `ServiceSpec` |
| A whole descriptor document | `*Descriptor` | `InterfaceDescriptor` (unchanged) |

Renames:

| Was | Becomes | Old name reused here? |
|---|---|---|
| `EndpointDescriptor` | `EndpointSpec` | no |
| `ToolDescriptor` | `McpToolSpec` | no |
| `CommandDescriptor` | `CommandSpec` | no |
| `ServiceDescriptor` | `ServiceSpec` | no |

**Nothing in this change reuses a freed name.** All four old names become
deprecation aliases for one release. That uniformity is the point of the
extraction: there is no "this name now means something else" case to verify.

Also in scope:

- `CONTRACT_VERSION` 1 → 2, since `$defs` titles change in the versioned schema
  `src/gen_eval/contracts/interface-descriptor.schema.json` published by PR #277.
- Regeneration of all four artifacts `scripts/generate_contract_schemas.py`
  writes — the version stamp touches every schema, not just the descriptor one.
- Migration of the 11 existing test files that reference the old names.
- A downstream notice, since consumers were directed at that schema.

### Out of scope

- Defining any new descriptor archetype. Freeing the names is all this change
  does; `derive-descriptors-from-contracts` occupies them afterward.
- Removing the aliases. That is a later change with its own notice period.

## Approaches Considered

### Approach 1 — Two-level scheme, all four renamed, uniform aliases (**Recommended**)

Rename all four element/container types to `*Spec`, reserve `*Descriptor` for
document-level types, keep deprecation aliases for all four.

**Pros**
- No name is freed and reused in the same change, so there is no intermediate
  state a gate cannot express. This is the specific property whose absence
  generated four blocking findings previously.
- Uniform compatibility story: every old name aliases, one rule, one gate.
- The level becomes legible from the name alone, permanently.

**Cons**
- Larger rename than strictly required: ~22 references in `src/`, ~90 in
  `tests/`, 8 `$defs` titles.
- Forces a `CONTRACT_VERSION` bump on consumers who may not care about naming.

**Effort**: M

### Approach 2 — Rename only the two names the consuming change needs

Rename `ToolDescriptor` and `ServiceDescriptor` only; leave
`EndpointDescriptor` and `CommandDescriptor` alone.

**Pros**
- Half the churn, and the same unblocking effect for the consuming change.
- Smaller diff to review.

**Cons**
- `*Descriptor` still spans two levels afterward, so the underlying confusion
  survives and the next reader still has to disambiguate by memory.
- Leaves an inconsistent family: `EndpointDescriptor` beside `McpToolSpec`
  describing the same kind of thing.
- The version bump is incurred anyway, so the main cost is paid without the
  main benefit.

**Effort**: S

### Approach 3 — Qualified names for the new archetypes, no rename at all

Leave every existing name alone; have the consuming change use
`ContractServiceDescriptor` / `ContractToolDescriptor`.

**Pros**
- Zero churn here, no version bump, no downstream notice.
- Unblocks the consuming change immediately.

**Cons**
- Permanently freezes the three-meaning ambiguity, and adds a fourth and fifth
  name to the same family.
- Every future reader disambiguates near-identical names by prefix.
- Was explicitly rejected by the operator when this decision was first taken.

**Effort**: XS

### Selected Approach

**Approach 1.** Approach 3 was rejected when the naming decision was originally
made and nothing has changed that reasoning — the goal is one canonical name per
concept. Approach 2 pays the version-bump cost without buying the clarity, and
leaves a visibly inconsistent family.

Approach 1's larger diff is acceptable precisely because it is mechanical: no
behaviour changes, and the uniform alias rule means a single gate covers every
renamed type.
