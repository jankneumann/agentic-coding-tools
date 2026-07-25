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

### D3 — Every guard fails closed, counting the archetype's own coverage unit

**Decision.** Each drift guard asserts, in order:

1. the generated artifact declares a **non-zero number of coverage units**;
2. its coverage-unit count **equals** the contract's;
3. its content matches the checked-in copy byte for byte.

The **coverage unit is archetype-specific**, and this is load-bearing:

| Archetype | Coverage unit |
|---|---|
| Service | operation |
| Tool | flag + positional + named subcommand (**not** command) |

A generator that silently emits zero units fails at (1), before the diff in (3)
can pass trivially against an equally-empty checked-in file.

**Why the unit matters.** Phrasing all three assertions in terms of
*operations* — as the first draft of this design did — reopens the exact hole
the change exists to close, for the tool archetype. `cli-contract.schema.json`
sets `minItems: 1` on `commands` but no minimum on `flags`. So this contract:

```json
{"contract_version":"1","tool":{"name":"gen-eval","executable":"gen-eval"},
 "commands":[{"name":""}]}
```

validates today, declares 1 command and 0 flags, and passes all three
assertions (1 ≠ 0; 1 == 1; bytes match) while the derived declared surface is
**empty**. That is UP-1/UP-3's vacuous-pass family reintroduced inside the guard
built to prevent it.

**Consequence.** `cli-contract.schema.json` gains a constraint requiring at
least one coverage unit: a command with an empty `name` MUST declare at least
one flag or positional. The "1 command / 0 flags" case becomes an explicit
negative fixture in task 1.5, alongside `empty` and `count_mismatch`.

**Why (3) alone is not enough.** It is satisfied by "empty == empty". Both files
can rot to nothing together and the guard stays green. (1) and (2) are what make
it a gate rather than a mirror.

### D4 — Coverage is keyed on operation × surface

**Decision.** Replace the flat `list[str]` interface vocabulary with an
operation-keyed structure in which each surface entry **names the surface-local
element that serves the operation**:

```
operation_id: "acquire_lock"
  surfaces:
    http:  { exposed: true,  covered: true,  element: "POST /locks/acquire" }
    mcp:   { exposed: true,  covered: false, element: "acquire_lock" }
    cli:   { exposed: false, reason: "not exposed on CLI" }
```

`unevaluated_interfaces` derives from this: an operation is unevaluated when
no *exposed* surface was covered. `per_surface` detail is additive.

**One element may serve several operations.** The `element` binding is
deliberately many-to-one, because the real surface is:

```
operation_id: "list_active_locks"
  surfaces: { http: {element: "GET /locks/active"},        mcp: {element: "check_locks"} }
operation_id: "get_lock_status"
  surfaces: { http: {element: "GET /locks/status/{path}"}, mcp: {element: "check_locks"} }
```

The coordinator's MCP tool `check_locks` ("Check lock status for one or more
file paths") serves **both** HTTP operations by branching on `file_paths` being
`None` (`agent-coordinator/src/coordination_mcp.py:165`), while the CLI splits
the same pair into `lock list` and `lock status`.

Without the binding, a 1:1 projection (D7) would contract two MCP tools —
`list_active_locks` and `get_lock_status` — that do not exist, and the subset
verifier (task 4.6) would report the *real* `check_locks` as an undocumented
excess while simultaneously reporting the two invented tools as omissions.
Three false findings from one legitimate merge.

**Consequence.** Subset verifiers compare the implemented surface against the
**set of bound elements**, not against derived one-per-operation names. Coverage
of any bound element counts as coverage of every operation it serves.

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

### D6 — Behaviourally additive, nominally breaking, with a populated legacy field

**Decision.** Two halves, and they differ:

**Behaviour is additive.** `InterfaceDescriptor` keeps loading and keeps
emitting the flat `unevaluated_interfaces`. When a descriptor declares a
contract, the derived path is used and the flat field is computed *from* the
operation model for backward compatibility. Deprecation warning on the
hand-authored path; no removal in this change.

**Names are not.** Per D9 the published `$defs` titles change, so
`CONTRACT_VERSION` goes 1 → 2 and consumers pinning the schema must update. A
consumer that only *loads descriptors* is unaffected; a consumer that
*imports the model classes or validates against the published schema* must
change.

**The flat field's back-compat covers `per_interface` too.** `per_interface` is
built at `orchestrator.py:382-388` from `v.interfaces_tested` — per-surface
strings produced by `_extract_interfaces`. DOWNSTREAM.md tells ACA to assert on
it, so it must be populated from the operation model on the same terms as
`unevaluated_interfaces`, not left to drift. Tasks 3.3/3.4 cover both fields.

**Why.** ACA, agentic-assistant and the coordinator all consume the current
shape. Keeping *behaviour* additive means their runs keep working while they
migrate. Accepting a *nominal* break is the deliberate choice recorded in D9:
downstream consumers must adapt to the coverage-semantics change regardless, so
one coherent break is cheaper than a permanent pair of near-identical names.

**Rejected**: keeping the old names and giving the new archetypes qualified
ones (`ContractServiceDescriptor` / `ContractToolDescriptor`). It avoids the
version bump, but leaves `*Descriptor` meaning three different levels
simultaneously and makes every future reader disambiguate by prefix.

### D7 — OpenAPI → MCP projection is mechanical but not total

**Decision.** Derive an MCP tool per operation by flattening (path, query, body)
parameters into one input object. **The projection is a default, not a law** —
where a contract declares an explicit `mcp.element` binding (D4), that binding
wins and no tool name is derived. Three carve-outs:

- `description` is copied from the operation's `summary`/`description` and is
  **semantically load-bearing** — an agent reads it to decide when to call. The
  contract must be authored for agent consumption, not only validation.
- MCP resources and prompts are **not** operations and are out of the
  projection. A descriptor may declare them; they are excluded from
  operation × surface coverage.
- **Many-to-one is legal and must be declared, not derived.** One MCP tool may
  serve several operations (`check_locks` serves both `list_active_locks` and
  `get_lock_status`). Deriving a name per operation in that case invents tools
  that do not exist. When several operations bind to one element, the generator
  emits the bound name once and records the fan-in.

**Why.** The coordinator's 38 HTTP vs 39 MCP delta shows non-total projection
is already the reality, not a hypothetical — and inspecting the delta shows it
is not merely *partial* (operations missing from a surface) but *non-injective*
(one element serving many operations). `exposed: false` handles the first;
only an explicit binding handles the second.

### D8 — gen-eval self-migration is the proving case

**Decision.** gen-eval's own `evaluation/descriptor.yaml` (added in PR #277)
becomes the first derived tool descriptor, generated from a checked-in
`gen-eval` CLI contract and drift-guarded in CI.

**Why.** It is the smallest real case, it is already wired into a blocking CI
gate (`make dogfood`), and it is the descriptor that currently reports
`0 interfaces`. If the model works, that number becomes the flag count and the
dogfood coverage assertion stops being vacuous.

### D9 — `*Spec` names an element, `*Descriptor` names a document

**Decision.** Adopt a two-level naming scheme and rename the existing models to
fit it. `CONTRACT_VERSION` goes 1 → 2 and the published
`interface-descriptor.schema.json` is regenerated.

| Level | Suffix | Types |
|---|---|---|
| One element, or a container of elements for one surface | `*Spec` | `EndpointSpec`, `McpToolSpec`, `CommandSpec`, `ServiceSpec` |
| A whole descriptor document | `*Descriptor` | `InterfaceDescriptor` (existing, deprecated), `ServiceDescriptor` (new archetype), `ToolDescriptor` (new archetype) |

Renames: `EndpointDescriptor`→`EndpointSpec`, `ToolDescriptor`→`McpToolSpec`,
`CommandDescriptor`→`CommandSpec`, `ServiceDescriptor`→`ServiceSpec`. Each keeps
a deprecation alias for one release.

**Why.** The plan's two headline deliverables were originally named
`ServiceDescriptor` and `ToolDescriptor` — **both already taken** in the exact
module the plan targets, with unrelated meanings:

| Name | Currently means | `descriptor.py` |
|---|---|---|
| `ToolDescriptor` | one MCP tool | `:41` |
| `ServiceDescriptor` | one testable service | `:67` |

`ServiceDescriptor` is re-exported in `__init__.py`, listed in `__all__`, pinned
by `tests/test_public_api_parity.py`, and both appear as `$defs` titles in the
versioned schema PR #277 published for offline consumers. Defining new types
under those names in the same namespace is not a collision to be worked around
— it is a signal that `*Descriptor` was already carrying three distinct
meanings (element, container, document).

**Why rename rather than qualify.** The alternative — `ContractServiceDescriptor`
/ `ContractToolDescriptor` — avoids the version bump but permanently freezes the
ambiguity, leaving every reader to disambiguate near-identical names by prefix.
Downstream consumers must already adapt to the coverage-semantics change
(DS-2), so one coherent break costs less than the name soup it avoids.

**Consequences.** A rename package runs **before** the archetype packages, since
they occupy the freed names. It must own `descriptor.py`, `__init__.py`,
`contracts/__init__.py`, the published schema, and `test_public_api_parity.py`.
DOWNSTREAM.md gains DS-4 for the version bump.

### D10 — A coverage vocabulary is only real if something can fail on it

**Decision.** Extend `Evaluator._extract_interfaces` to produce tested
identifiers that share a vocabulary with the derived declared surface, and add a
coverage threshold the CLI can actually fail on. Both land in the same phase as
the coverage model.

**Why.** Without this, the change makes the dogfood gate *worse*, not better:

1. `_extract_interfaces` (`evaluator.py:530`) is the sole producer of
   `interfaces_tested`, and for CLI steps it requires `step.command` to be
   truthy. gen-eval's 8 dogfood steps use `args: [...]` with no `command`, so
   it yields `[]`.
2. Coverage is pure string matching of tested-vs-declared
   (`orchestrator.py:376`, `:401`).
3. So once task 5.3 makes the declared surface N contracted flags, `covered`
   stays empty → `coverage_pct` 0.0, and all N flags land in
   `unevaluated_interfaces`.

The MODIFIED Dogfood requirement demands 80%+ coverage as a blocking gate — so
the change would convert today's vacuous *pass* into tomorrow's guaranteed
*violation*. And it would not even be caught: gen-eval's CLI has no coverage
threshold at all (`__main__.py:399` exits on `report.pass_rate` only), and
`make dogfood` passes `--fail-threshold 1.0`, which is pass-rate, not coverage.

**Consequences.** `wp-coverage-model` must own `evaluator.py` and `__main__.py`
and depend on `wp-tool-descriptor` (it needs the tool vocabulary). The
integration package asserts on `coverage_pct`, **not** on
`declared_interfaces_non_empty` — non-emptiness of the declared set is the same
vacuous signal this change exists to remove.

## Risks

| Risk | Mitigation |
|---|---|
| `unevaluated_interfaces` meaning change breaks ri-06 | D6 keeps the flat field populated (and `per_interface` with it); `DOWNSTREAM.md` notifies ACA; their gate needs a non-emptiness guard regardless |
| CLI contract schema over-fits gen-eval's argparse | Validate against a second tool (ACA's or agentic-assistant's descriptor) before finalizing the schema |
| Dual-path loading rots | Deprecation warning from day one; removal tracked as an explicit follow-up, not left implicit |
| Coordinator OpenAPI contract never gets authored | Out of scope by design; the service-descriptor path ships with fixtures and is proven on the coordinator in a follow-up |
| Rename (D9) breaks a consumer we did not anticipate | Deprecation aliases for one release; `CONTRACT_VERSION` bump makes the break detectable rather than silent; DS-4 notifies |
| The rename package becomes a merge bottleneck — it owns `descriptor.py`, which two archetype packages then extend | It is deliberately small (mechanical rename + aliases + regeneration, no behaviour change) and is the DAG root alongside `wp-contracts`; archetype packages branch from its completion |
| Excess detection ships but never runs against a real surface | Task 4.7 wires a subset verifier into CI against gen-eval's own argparse — the one real surface this change owns end-to-end |

## Open questions

- Should `exposed: false` require a stated `reason`? Leaning yes — an
  unexplained exclusion is how coverage gaps get laundered into "intentional".
- Does the CLI contract need to express flag *combinations* (mutually exclusive
  groups, required-together)? argparse can express them; deferring until a
  second tool proves the need.

### Resolved by plan review (round 1)

- **Which name do the new archetypes take?** Resolved by D9: the existing
  element/container models are renamed to `*Spec`, freeing `*Descriptor` for
  document-level types. Accepted as a breaking change with a
  `CONTRACT_VERSION` bump.
- **Can one MCP tool serve several operations?** Yes — resolved by D4's
  `element` binding and D7's third carve-out. `check_locks` is the proving case.
- **What counts as a coverage unit for the fail-closed guard?** Resolved by D3:
  operations for the service archetype, flags/positionals/subcommands for the
  tool archetype. Counting commands was the hole.
