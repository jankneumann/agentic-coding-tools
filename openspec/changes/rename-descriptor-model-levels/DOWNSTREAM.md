# Downstream notice: gen-eval descriptor model renames

> From: `jankneumann/agentic-coding-tools`, change `rename-descriptor-model-levels`
> To: anyone importing `gen_eval` descriptor models or validating against
> `interface-descriptor.schema.json` — `agentic-assistant`, ACA
> (`establish-cli-gen-eval-coverage` / `ri-06`)
> Contract: `CONTRACT_VERSION` **1 → 2**

**DS-3 is the one that will not announce itself.** If you read only one section,
read that one — it describes a name that keeps working while meaning something
else.

---

## What changed

Four models are renamed. `*Spec` now names a single surface element or a
per-surface container of elements; `*Descriptor` is reserved for the whole
document (design D1).

| Was | Now | Level |
|---|---|---|
| `EndpointDescriptor` | `EndpointSpec` | one HTTP endpoint |
| `ToolDescriptor` | `McpToolSpec` | one MCP tool |
| `CommandDescriptor` | `CommandSpec` | one CLI command |
| `ServiceDescriptor` | `ServiceSpec` | container: one *surface* of a project |

`InterfaceDescriptor` is **unchanged** — it is the document type, and after this
change it is the only `*Descriptor` in the module.

No repository-internal consumer was affected: outside `packages/gen-eval/` there
were zero references to any of the four names.

---

## DS-1 — Python callers: aliases work, for one release

All four old names still resolve from both `gen_eval` and
`gen_eval.descriptor`, and emit a `DeprecationWarning` naming the replacement.

```python
from gen_eval import ServiceDescriptor   # works, warns
from gen_eval import ServiceSpec         # what to move to
```

Two details worth knowing:

- The old names **left `__all__`**. They remain importable by name, but
  `from gen_eval import *` no longer provides them. If you rely on star-import,
  switch to explicit imports or the new names.
- The alias warns on **every** access, not just the first. If you run with
  `-W error::DeprecationWarning`, you will see this immediately rather than on
  a later unrelated run.

**Migration is a mechanical rename.** Field names, types, and behaviour are
untouched — this change alters no behaviour anywhere.

---

## DS-2 — Schema consumers: `$defs` keys and titles moved

If you validate descriptors against `interface-descriptor.schema.json`, or
generate client types from it, the `$defs` keys and their `title` values now use
the `*Spec` names. `$ref` targets moved with them.

Validation of an existing *descriptor document* is unaffected — the wire format
did not change, only the names of the schema definitions describing it. What
breaks is code that reaches into `$defs` by name, or generated types whose class
names come from those keys.

`x-gen-eval-contract-version` is `2` in all three published schemas, and the
`VERSION` file reads `2`. Pin accordingly.

---

## DS-3 — ⚠️ `ServiceDescriptor` and `ToolDescriptor` will be **reused**, not removed

This is the part a deprecation warning cannot tell you, and the reason this
notice exists at all.

The follow-on change `derive-descriptors-from-contracts` **reclaims both names
for different types** — document-level archetypes derived from contracts under
`openspec/contracts/`. It is a distinct change with its own version bump
(`CONTRACT_VERSION` 2 → 3).

Read the deprecation on these two names as **"this name is about to mean
something else"**, not "this name is going away":

| | What you get | How you find out |
|---|---|---|
| A **removed** name | `ImportError` | loudly, at import |
| A **deprecated** name | the right object | a warning |
| A **reclaimed** name | a *different* object | **nothing** |

After `derive-descriptors-from-contracts` lands, `from gen_eval import
ServiceDescriptor` will still succeed, still return a valid type, and hand you
something that is not what you asked for. The import does not fail. There is no
warning, because nothing is deprecated any more — the name is simply in use by
someone else.

**What to do:** migrate `ServiceDescriptor` → `ServiceSpec` and `ToolDescriptor`
→ `McpToolSpec` *now*, while the alias still warns. The other two
(`EndpointDescriptor`, `CommandDescriptor`) are ordinary deprecations with no
reclamation planned; migrate them at leisure.

The practical alias window on the two reclaimed names is therefore **shorter
than one release** for anyone tracking `main`.

---

## Verification you can run

```bash
cd packages/gen-eval
uv run python -c "import gen_eval; print(gen_eval.ServiceSpec.model_fields.keys())"
uv run python -c "from gen_eval.contracts import CONTRACT_VERSION; print(CONTRACT_VERSION)"  # 2
uv run python -W error::DeprecationWarning -c "import gen_eval; gen_eval.ServiceDescriptor"  # raises
```

The third command is the fastest way to find every call site you still need to
migrate: run your own suite under `-W error::DeprecationWarning`.
