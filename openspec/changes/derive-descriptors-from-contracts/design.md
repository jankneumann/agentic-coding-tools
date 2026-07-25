# Design — Derive gen-eval descriptors from contracts

## Context

Three defects share one root cause: gen-eval has no notion of an *operation*.
It has surface-local interface strings, hand-authored into a descriptor, with
no link back to the contract that says what the system is supposed to do.

Everything below follows from introducing that link and choosing its direction.

## Decisions

### D1 — The contract is the source; introspection is the verifier

**Decision.** Descriptors are derived *from* `openspec/contracts/<cap>/openapi/*.yaml`
(services) and `openspec/contracts/<cap>/cli/*.yaml` (tools). Runtime
introspection — FastAPI `app.openapi()`, MCP `list_tools()`, argparse
`parser._actions` — is used **only** to assert the implemented surface is a
subset of the contract. It never populates a descriptor.

**Why.** Direction is the whole design. If introspection populates the
declared set, a broken or unreachable surface yields an empty set, and
`unevaluated_interfaces == []` reports full coverage. This repo hit that class
of bug three times in one PR:

| Defect | Fail-open mechanism |
|---|---|
| UP-1 | Console script raised `TypeError`; a `--help`-based probe would read that as "no CLI" |
| UP-3 | Zero scenarios evaluated → `pass_rate` 0.0, but `--fail-threshold 0` exited green |
| UP-4 | Health check had to *succeed*, so CLI-only projects faked a reachable URL |

**Consequence.** This **inverts** the existing normative statement in
`Interface Descriptor` ("auto-discovery of HTTP endpoints from OpenAPI specs,
MCP tools from `tools/list`, and CLI commands from `--help` output"). That
requirement is MODIFIED, not extended. The OpenAPI half survives — a spec
*is* a contract; the `tools/list` and `--help` halves are re-cast as
verification inputs.

### D2 — Derivation produces checked-in artifacts, never runtime output

**Decision.** Generators write descriptor YAML into the repo. A `--check` mode
regenerates into a temp dir and diffs, exiting non-zero on drift. CI runs
`--check`; tests assert the same.

**Why.** Same pattern as `contracts/generated/models.py` +
`test_contracts_generated.py`, and as `scripts/generate_contract_schemas.py --check`
from PR #277. Reviewers already know this shape. It also makes the descriptor a
reviewable diff instead of an invisible runtime computation.

**Rejected**: generating in-memory at descriptor-load time. Cheaper, but the
declared surface then depends on generator success at run time — reintroducing
D1's failure mode through the back door.

### D3 — Every guard fails closed

**Decision.** Each drift guard asserts, in order:

1. the generated artifact is **non-empty**;
2. its operation count **equals** the contract's operation count;
3. its content matches the checked-in copy byte for byte.

A generator that silently emits zero operations fails at (1), before the diff
in (3) can pass trivially against an equally-empty checked-in file.

**Why.** (3) alone is satisfied by "empty == empty". Both files can rot to
nothing together and the guard stays green. (1) and (2) are what make it a
gate rather than a mirror.

### D4 — Coverage is keyed on operation × surface

**Decision.** Replace the flat `list[str]` interface vocabulary with an
operation-keyed structure:

```
operation_id: "acquire_lock"
  surfaces:
    http:  { exposed: true,  covered: true  }
    mcp:   { exposed: true,  covered: false }
    cli:   { exposed: false, reason: "not exposed on CLI" }
```

`unevaluated_interfaces` derives from this: an operation is unevaluated when
no *exposed* surface was covered. `per_surface` detail is additive.

**Why.** Today `POST /locks/acquire`, `mcp:acquire_lock` and `cli:lock acquire`
are three unrelated strings; testing the operation once leaves two "uncovered".
The 38/39/37 counts prove surfaces are genuinely partial, so `exposed: false`
must be first-class or every derived descriptor carries permanent false gaps.

**Trade-off accepted.** This changes the meaning of `unevaluated_interfaces`,
which ACA's ri-06 asserts on directly. Handled by `DOWNSTREAM.md` and by
keeping the legacy flat field populated during the deprecation window (D6).

### D5 — Tool contracts are a separate schema, not OpenAPI

**Decision.** Service contracts stay OpenAPI. Tool contracts get their own
schema (`contracts/cli-contract.schema.json`) describing commands, flags,
argument types, and **exit codes**.

**Why.** OpenAPI cannot express exit codes, and a tool's flags are process
configuration rather than operation parameters. Forcing `--fail-threshold` into
an OpenAPI operation would be a lie that later readers have to decode. This is
the same category error UP-4 fixed in the lifecycle.

**Cost acknowledged.** This is the binding-spec cost named in the proposal's
Approach 1 cons. It is accepted because it is exactly what makes flags nameable,
and flag-only nameability is what currently lets ri-06's gate pass for free.

### D6 — Additive migration with a populated legacy field

**Decision.** `InterfaceDescriptor` keeps loading and keeps emitting the flat
`unevaluated_interfaces`. When a descriptor declares a contract, the derived
path is used and the flat field is computed *from* the operation model for
backward compatibility. Deprecation warning on the hand-authored path; no
removal in this change.

**Why.** ACA, agentic-assistant and the coordinator all consume the current
shape. A hard cutover blocks on a coordinator OpenAPI contract that does not
exist yet.

### D7 — OpenAPI → MCP projection is mechanical but not total

**Decision.** Derive an MCP tool per operation by flattening (path, query, body)
parameters into one input object. Two carve-outs:

- `description` is copied from the operation's `summary`/`description` and is
  **semantically load-bearing** — an agent reads it to decide when to call. The
  contract must be authored for agent consumption, not only validation.
- MCP resources and prompts are **not** operations and are out of the
  projection. A descriptor may declare them; they are excluded from
  operation × surface coverage.

**Why.** The coordinator's 38 HTTP vs 39 MCP delta shows non-total projection
is already the reality, not a hypothetical.

### D8 — gen-eval self-migration is the proving case

**Decision.** gen-eval's own `evaluation/descriptor.yaml` (added in PR #277)
becomes the first derived tool descriptor, generated from a checked-in
`gen-eval` CLI contract and drift-guarded in CI.

**Why.** It is the smallest real case, it is already wired into a blocking CI
gate (`make dogfood`), and it is the descriptor that currently reports
`0 interfaces`. If the model works, that number becomes the flag count and the
dogfood coverage assertion stops being vacuous.

## Risks

| Risk | Mitigation |
|---|---|
| `unevaluated_interfaces` meaning change breaks ri-06 | D6 keeps the flat field populated; `DOWNSTREAM.md` notifies ACA; their gate needs a non-emptiness guard regardless |
| CLI contract schema over-fits gen-eval's argparse | Validate against a second tool (ACA's or agentic-assistant's descriptor) before finalizing the schema |
| Dual-path loading rots | Deprecation warning from day one; removal tracked as an explicit follow-up, not left implicit |
| Coordinator OpenAPI contract never gets authored | Out of scope by design; the service-descriptor path ships with fixtures and is proven on the coordinator in a follow-up |

## Open questions

- Should `exposed: false` require a stated `reason`? Leaning yes — an
  unexplained exclusion is how coverage gaps get laundered into "intentional".
- Does the CLI contract need to express flag *combinations* (mutually exclusive
  groups, required-together)? argparse can express them; deferring until a
  second tool proves the need.
