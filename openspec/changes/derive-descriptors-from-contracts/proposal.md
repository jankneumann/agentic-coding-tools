# Derive gen-eval descriptors from contracts

## Why

gen-eval's `InterfaceDescriptor` is hand-authored, and the coverage vocabulary
it produces is unsound in three separate ways. All of this was found
empirically while landing PR #277 (UP-1..UP-5).

### 1. One type is doing two jobs

The agent-coordinator descriptor declares **38 HTTP endpoints, 39 MCP tools and
37 CLI commands** — ~114 hand-maintained entries that are three near-isomorphic
projections of roughly *one* operation set. gen-eval's own descriptor, ACA's,
and agentic-assistant's are something else entirely: a program's own argv
surface, not an API client.

These are two archetypes wearing one type:

| | Ground truth | Coverage unit | Lifecycle |
|---|---|---|---|
| **Service** (coordinator) | an API contract | operation × surface | starts services |
| **Tool** (gen-eval, ACA) | its argument parser | flag / subcommand | starts nothing |

UP-4 in PR #277 — making `startup` optional — was this same conflation
surfacing in the *lifecycle* instead of the vocabulary. A CLI-only project was
forced to invent a `StartupConfig` it never used because the type assumed
"service".

### 2. Coverage is keyed on per-surface strings

`POST /locks/acquire`, `mcp:acquire_lock` and `cli:lock acquire` are counted as
three unrelated interfaces. Exercise the operation once via HTTP and the report
claims **two remain uncovered** — for a single operation. The framework already
*believes* these are equivalent: `Evaluator._detect_cross_interface_mismatch`
fails a scenario when consecutive cross-transport steps disagree about state.
It just doesn't derive its vocabulary from that belief.

### 3. `unevaluated_interfaces` is vacuously empty for flag-only CLIs

`Evaluator._extract_interfaces` derives a CLI identifier from the words *before
the first flag*. gen-eval's CLI is flat — all flags, no subcommands — so it
yields **zero** interfaces. Confirmed in CI: the dogfood run reports
`descriptor loaded — 1 services, 0 interfaces`.

Zero declared interfaces means `unevaluated_interfaces == []`. ACA's ri-06
asserts exactly that emptiness as its coverage gate, so **the gate currently
passes for free** on any flag-only project. This is the same vacuous-pass
family as UP-1's health check and UP-3's zero-scenario run: a gate reporting
green because it was handed an empty set.

### 4. The chain only catches omission, never excess

`contract → descriptor → implementation` detects "the implementation lacks what
was promised". It cannot detect "the implementation exposes what was never
contracted" — undocumented endpoints, debug flags, uncontracted admin routes.
`unevaluated_interfaces == []` means *everything declared was tested*, never
*everything that exists was tested*.

### 5. The hooks for all of this already exist and are dead

`ServiceDescriptor.openapi_spec`, `.tools_manifest` and `.cli_schema` are
declared on the model and **read by nothing**. Worse, the current spec already
mandates the capability — and mandates the wrong direction:

> The framework MUST support auto-discovery of HTTP endpoints from OpenAPI
> specs, MCP tools from `tools/list`, and CLI commands from `--help` output.
> — `gen-eval-framework`, Requirement: Interface Descriptor

Discovering *from* `tools/list` and `--help` makes the implementation the
source of truth. A broken surface then yields an empty declared set and a green
gate. That is precisely the failure this repo hit three times in PR #277.

## What Changes

### The model

Ground truth is `openspec/contracts/<capability>/openapi/*.yaml` — already the
canonical, archive-proof contract home per `openspec/contracts/README.md`.

```
openspec/contracts/<cap>/openapi/v1.yaml     ← ground truth (exists)
   ├─→ contracts/generated/models.py         ← EXISTS, drift-guarded
   ├─→ Service Descriptor (http + mcp)       ← NEW
   └─→ Tool Descriptor (cli arguments)       ← NEW
                  ↓
           gen-eval scenarios                 ← EXISTS
                  ↓
            implementation
                  ↓
        reverse verifier (⊆ contract)         ← NEW
```

**Governing principle, to be encoded normatively:** the contract is *always*
the source; implementation introspection is *always* the verifier, never the
source.

### Deliverables

1. **Two descriptor archetypes.** `ServiceDescriptor` (contract-derived, http +
   mcp bindings) and `ToolDescriptor` (cli argument definitions). Additive —
   the existing hand-authored `InterfaceDescriptor` keeps working and is
   deprecated, not removed.
2. **Derivation generators** with `--check` drift mode, reusing the shape
   already proven by `contracts/generated/models.py` +
   `test_contracts_generated.py` and by PR #277's
   `scripts/generate_contract_schemas.py --check`.
3. **Fail-closed drift guards.** Every guard asserts non-emptiness *and* an
   operation-count match against the contract. A generator that silently emits
   an empty descriptor must fail, not pass.
4. **Reverse-link verifiers for all three surfaces** — FastAPI `app.openapi()`,
   MCP `list_tools()`, argparse `parser._actions`, each asserted ⊆ contract.
5. **Operation × surface coverage.** `unevaluated_interfaces` becomes
   operation-keyed with per-surface detail, making *"covered, but only via
   HTTP"* expressible. Surfaces are explicitly partial — the 38/39/37 deltas
   are real, so "not exposed on surface X" is first-class rather than a
   permanent false gap.
6. **gen-eval's own tool descriptor**, derived and drift-guarded, as the
   proving case.
7. **`DOWNSTREAM.md`** — notice to ACA ri-06, whose coverage assertion changes
   meaning under this model.

### Spec debt fixed along the way

- **MODIFY `Interface Descriptor`**: `startup` is optional. PR #277 already
  shipped this (UP-4) with no spec delta, so the spec currently contradicts
  merged code.
- **MODIFY `Dogfood`**: correct the stale 35/39/31 counts to the actual
  38/39/37, and make the 80% coverage floor conditional on the descriptor
  having nameable interfaces — a flag-only tool descriptor cannot meet it.

### Out of scope

- Migrating the coordinator's 114-entry descriptor. That needs a coordinator
  OpenAPI contract authored under `openspec/contracts/` first, and would
  dominate this change. Follow-up.
- Any change to `packages/gen-eval` under PR #277. That PR is green,
  self-contained, and must land untouched.

## Approaches Considered

### Approach 1 — Contract-derived descriptors as generated artifacts (**Recommended**)

Author the contract; generate `ServiceDescriptor` and `ToolDescriptor` as
checked-in artifacts; guard drift with `--check`; verify the reverse direction
by asserting introspected surface ⊆ contract.

**Pros**
- Fail-closed by construction: derivation happens at build time against a
  static contract, so a broken implementation cannot shrink the declared set.
- Reuses a pattern already proven twice in this repo — reviewers know it.
- Reverse verifiers make *excess* detectable, which no other option offers.
- Descriptors become reviewable diffs rather than 114 hand-maintained entries.

**Cons**
- Requires a binding spec: an operation's (path, query, body) does not map
  mechanically onto flags — arrays as repeated flags, `--no-x` booleans, stdin
  for body, env for auth. That artifact must be written and maintained.
- Two descriptor types means dual-path loading code until the old one is
  removed.
- OpenAPI cannot express exit codes; the tool contract needs its own shape.

**Effort**: L

### Approach 2 — Runtime auto-discovery (implement the existing spec literally)

Implement `openapi_spec` / `tools_manifest` / `cli_schema` as the current spec
describes: probe the live surface at descriptor-load time via `tools/list`,
`--help`, and a served OpenAPI document.

**Pros**
- Smallest change; the requirement already exists so no spec inversion needed.
- Zero generated artifacts to keep in sync.
- Always reflects the deployed surface exactly.

**Cons**
- **Fails open.** A broken CLI or an unreachable service yields an empty
  declared set, hence `unevaluated_interfaces == []`, hence a green gate. This
  is the exact defect class PR #277 spent its length removing (UP-1, UP-3,
  UP-4) and would reintroduce it as architecture.
- Makes the implementation the source of truth, so it cannot detect excess by
  construction — anything the implementation exposes is definitionally correct.
- Non-deterministic reports: verdicts vary with whichever binary is on `PATH`.
- Requires services running to compute coverage at all.

**Effort**: M

### Approach 3 — Annotated hand-authored descriptors

Keep descriptors hand-written, but add an `operation_id` cross-link on each
entry so the three surface projections group into operations. Add a lint that
diffs the descriptor against the contract and reports divergence.

**Pros**
- No generator, no binding spec, no dual-path loading.
- Fixes the operation × surface coverage problem (item 2) on its own.
- Incremental: descriptors can be annotated one at a time.
- Lint gives most of the drift signal without owning generation.

**Cons**
- Leaves ~114 entries hand-maintained; the duplication that motivates this
  change survives intact.
- `operation_id` is itself hand-entered, so it drifts — the annotation needs
  the same guard the descriptor does, with none of the benefit.
- Does not address flag-only naming (item 3) or excess detection (item 4).
- A lint that only *reports* divergence gets ignored; making it blocking is
  equivalent to a drift guard without the generation that makes drift fixable.

**Effort**: M

### Selected Approach

**Approach 1 — Contract-derived descriptors as generated artifacts.** Selected
at Gate 1 with no modifications.

Scope decisions taken with it at discovery:

| Decision | Choice |
|---|---|
| Migration posture | **Additive.** `ServiceDescriptor`/`ToolDescriptor` land alongside the hand-authored `InterfaceDescriptor`, which is deprecated but functional. Derived wins when a contract exists. |
| Spec debt | **Carry both fixes** — `startup` optional (matching shipped PR #277), and corrected `Dogfood` counts with a conditional coverage floor. |
| Reverse verifier | **All three surfaces** (FastAPI, MCP, argparse). A partial verifier gives false assurance about the surfaces it skips. |
| Implementation scope | **Machinery + gen-eval self-migration.** The coordinator's 114-entry descriptor is a follow-up, gated on a coordinator OpenAPI contract existing. |

Approaches 2 and 3 are retained above as rejected alternatives; the rationale
below is what drove the choice.

### Recommendation

**Approach 1.** Approach 2 is disqualified on the fail-open property alone —
it would encode as architecture the precise failure mode PR #277 removed three
times, and it structurally cannot detect excess. Approach 3 solves item 2
cheaply but leaves items 1, 3 and 4 untouched and still needs a guard on its
own annotations, so it buys less than it looks.

Approach 1's real cost is the binding spec (`cli_schema`), which is genuine
work. That cost is accepted because it is the artifact that makes flags
nameable — item 3 — and item 3 is what currently lets ri-06's coverage gate
pass for free.
