# Downstream notice: gen-eval consumers

> From: `jankneumann/agentic-coding-tools`, change `derive-descriptors-from-contracts`
> To: `establish-cli-gen-eval-coverage` (ACA roadmap item `ri-06`); cc `agentic-assistant`
> Reply to: `UPSTREAM.md` (ACA), items UP-1 … UP-4

Named `DOWNSTREAM.md` because the direction is reversed from your `UPSTREAM.md`
— we are upstream here. Same purpose: things the other repo needs to know.

**DS-1 is actionable now and does not depend on this change landing.** Please
read it first.

---

## Status of your UPSTREAM.md items

All four landed in **PR #277** (`openspec/quick-gen-eval-upstream`), green on 14
CI checks.

| Item | Status | Notes |
|---|---|---|
| UP-1 console script broken | **Fixed** | `async def main(args)` → `run(args)`; new sync zero-arg `main()`. Exit codes now `0` / `2` / `64` as you specified. |
| UP-2 versioned JSON Schema | **Published** | `src/gen_eval/contracts/` ships 3 generated schemas + `VERSION` in wheel *and* sdist. `gen-eval --print-contract-version` → `1`. Took your option 1 (pydantic promotion), so all three schemas are generated, not hand-authored. |
| UP-3 report guarantees | **Confirmed + one gap closed** | `per_category`/`per_interface` populate on all-pass runs; `unevaluated_interfaces` semantics as you assumed. Gap: `--fail-threshold 0` let a zero-scenario run exit 0. `run()` now fails an empty run at *any* threshold. |
| UP-4 mandatory `startup` | **Fixed** | Now optional. Worse than the three no-ops you described: the health check runs even under `--no-services`, so the placeholder URL had to genuinely *succeed*. |
| UP-5 (found by dogfooding) | **Fixed** | `CliClient` put stderr in `StepResult.error`, which the evaluator short-circuits to `status="error"` *before* comparing expectations — so `expect.exit_code` could never assert a failure path. `error` is now reserved for "command could not be run"; stderr moves to `body.stderr`. |

### One shape change to be aware of

`per_visibility` is now **always emitted** (as `{}` when empty); previously the
key was omitted. It remains **optional** in the published schema, so both
shapes validate. Readers using `data.get("per_visibility", {})` are unaffected.

---

## DS-1 — Your coverage gate currently passes for free ⚠️

**This is independent of everything else in this document. It is true of
gen-eval as it exists today, and it will remain true until you add a guard.**

ri-06 asserts `unevaluated_interfaces == []` as its coverage gate. For a
**flag-only CLI** — one with flags but no subcommands, which is what ACA's
descriptor describes — that assertion is **vacuously true**.

Mechanism: `Evaluator._extract_interfaces` derives a CLI interface identifier
from the words *before the first flag*. A flat CLI has none, so it yields zero
interfaces. Zero declared interfaces means nothing can be unevaluated.

Observed in our own CI, on gen-eval's own dogfood descriptor:

```
gen-eval: descriptor loaded — 1 services, 0 interfaces, mode=template-only
gen-eval: completed — 8/8 passed (100.0%)
```

Eight scenarios genuinely passed — but `unevaluated_interfaces` was `[]`
because the declared set was empty, not because coverage was complete. A gate
asserting emptiness cannot tell those two apart.

**Recommended action, regardless of this change:** assert non-emptiness of the
declared surface *before* asserting emptiness of the unevaluated set.

```python
report = json.load(open("gen-eval-report.json"))

declared = set(report["per_interface"]) | set(report["unevaluated_interfaces"])
assert declared, "declared interface surface is empty — coverage is vacuous"
assert report["unevaluated_interfaces"] == [], report["unevaluated_interfaces"]
```

This is the same failure family as UP-1 and UP-3: a gate reporting green
because it was handed an empty set. Worth adding now.

---

## DS-2 — `unevaluated_interfaces` changes meaning

Under this change, coverage is keyed on **operation × surface** rather than on
per-surface interface strings.

Today `POST /locks/acquire`, `mcp:acquire_lock` and `cli:lock acquire` are three
unrelated entries; exercising the operation once via HTTP leaves two "uncovered"
for what is one operation. The new model records exposure and coverage
per surface:

```
operation_id: acquire_lock
  http: { exposed: true,  covered: true  }
  mcp:  { exposed: true,  covered: false }
  cli:  { exposed: false, reason: "not exposed on CLI" }
```

An operation is unevaluated when **no exposed surface** was exercised. A surface
that does not expose an operation is not a gap.

**As built, this is less disruptive than planned. Read this paragraph rather
than the one that was here at plan time.**

`unevaluated_interfaces` **keeps its existing meaning and its existing
values** — per-surface strings, one entry per uncovered element. It is not
recomputed into operation ids. The operation view ships as a *new sibling
field* instead:

| Field | Granularity | Status |
|---|---|---|
| `unevaluated_interfaces` | per surface element | unchanged |
| `per_interface` | per surface element | unchanged |
| `unevaluated_operations` | per operation | **new**, optional |
| `per_operation` | per operation × surface | **new**, optional |
| `declared_interface_count` | one integer | **new**, optional |

Every existing assertion keeps working, on the same values, with the same
cardinality. Nothing in ri-06 needs to change for this item.

We chose this over rebinding the flat field because changing what a field
*means* while keeping its name is the failure mode DS-5 below is entirely
about — and doing it to a field a downstream gate already asserts on would
have been the same trap, one layer down.

One consequence worth naming: `coverage_pct` **is** now denominated in
operations rather than elements, so an operation exposed on three surfaces and
exercised on one reads 100%, not 33%. If you gate on the percentage, expect it
to rise for multi-surface projects. It does not move for a flag-only CLI, where
one element is one operation.

**`declared_interface_count` is the field DS-1 asks you to guard with.** It is
the declared surface size as a plain integer, so the recommended assertion
above becomes a one-liner that cannot be fooled by an empty set:

```python
assert report["declared_interface_count"] > 0, "coverage is vacuous"
```

gen-eval now enforces exactly this on itself: a run whose descriptor declares
nothing exits 1 with *"the descriptor declares no interfaces — coverage of
nothing is not coverage"*, rather than reporting 0% and passing a 0% floor.

---

## DS-3 — Descriptor type split, and what ACA should do

`InterfaceDescriptor` is splitting into two archetypes, because it has been
doing two jobs:

| | Ground truth | Coverage unit | Lifecycle |
|---|---|---|---|
| **Service** descriptor | OpenAPI contract | operation × surface | starts services |
| **Tool** descriptor | CLI contract | command / flag | starts nothing |

**ACA's descriptor is a tool descriptor.** Migration path:

1. **Now** — no action required. The hand-authored format keeps loading; it is
   deprecated, not removed, and will emit a warning naming the replacement.
2. **When this lands** — author a CLI contract for your tool under
   `openspec/contracts/<capability>/cli/` in your repo, following
   `cli-contract.schema.json` (shipped with this change). Your descriptor then
   references it and the declared surface is derived.
3. **Payoff** — your flags become nameable coverage units, so DS-1 stops being
   a problem structurally rather than by a guard you have to remember.

No timeline is imposed on step 2. The hand-authored path is not scheduled for
removal in this change, and removal will get its own downstream notice.

**One sequencing note.** The names `ServiceDescriptor` and `ToolDescriptor`
currently belong to *element* types (one MCP tool, one testable service). A
separate prerequisite change, `rename-descriptor-model-levels`, moves those
element types to `*Spec` names before this change reuses the freed ones for the
archetypes above. It carries its own notice and its own `CONTRACT_VERSION` bump.

If you import model classes rather than just loading descriptors, that change is
the one that affects you — and note the trap it describes: `ServiceDescriptor`
and `ToolDescriptor` do not disappear, they come back meaning something else.

---

## DS-5 — `ServiceDescriptor` and `ToolDescriptor` are RECLAIMED, not removed ⚠️

**This is the sharpest edge across both changes, and a deprecation warning does
not cover it.** Both names keep importing successfully. They mean something
different.

| Name | Meaning before | After the rename | After this change |
|---|---|---|---|
| `ServiceDescriptor` | one testable service (a container of endpoints/tools/commands) | deprecation alias → `ServiceSpec` | **the service document archetype** |
| `ToolDescriptor` | one MCP tool | deprecation alias → `McpToolSpec` | **the tool document archetype** |

A name that is *removed* fails loudly at import. A name that is *deprecated*
warns. A name that is **reclaimed** does neither — your import succeeds, your
type checks pass if you did not annotate, and the object simply is not what it
was. That is why this gets its own notice.

**Correction to the plan-time text: there is no second `CONTRACT_VERSION`
increment.** That constant versions the published JSON Schemas and bumps only
on a breaking *schema* change — a field removed, made required, or narrowed.
Reclaiming a Python export name is none of those, and bumping it would signal a
breaking schema change to every consumer pinning the value when no schema
changed. `CONTRACT_VERSION` stays at **2**, the value the rename set.

The fields this change adds (`per_operation`, `unevaluated_operations`,
`declared_interface_count`) are all optional with defaults, so the published
schema grows without breaking a reader of the old one.

**What to do:**

1. **If you only load descriptors (YAML in, report out)** — nothing. No
   behavioural change from either the rename or the reclamation.
2. **If you import either name** — decide which you meant. Wanted the element or
   container type? Use `ServiceSpec` / `McpToolSpec`. Wanted a whole descriptor
   document? The reclaimed names are now correct, but confirm, because the code
   that compiled before this change meant the other thing.
3. **If you pin `CONTRACT_VERSION`** — expect **one** increment, not two:
   1 → 2 at the rename, and no further bump here. See the correction above.

The reclamation is deliberate: `*Descriptor` is reserved for document-level
types, and these two archetypes are documents. But we would rather you learn it
from this table than from a type error three weeks out.

---

## DS-4 — Two things we recorded but did not fix

Both are in `packages/gen-eval/evaluation/README.md`. Flagging them because
they can bite a consumer.

1. **Scalar stdout is JSON-parsed.** `CliClient` runs `json.loads()` on stdout
   before falling back to `{"raw": ...}`. `gen-eval --print-contract-version`
   prints `1`, which is valid JSON, so the parsed body is `{"result": 1}` — an
   **int**. A version like `"v1"` or `"1.2.0-rc"` would land under `raw`
   instead. **The assertion key changes with the value.** If you pin the
   contract version from a scenario, account for this.

2. **A missing `--descriptor` file crashes with a raw traceback.** Exit code is
   1, so it is assertable, but a traceback is not an interface. Picking the
   right exit code (2? `EX_NOINPUT`?) is a contract decision we did not want to
   make unilaterally. If ri-06 has a view, we would take it.

---

## Questions back to you — answered

The three questions asked at plan time are resolved. Kept here with their
answers rather than deleted, so the reasoning is on the record.

1. **Does ri-06 assert only `unevaluated_interfaces == []`, or also on values
   or counts?** — *No longer load-bearing.* As built, the flat field keeps its
   values and cardinality (see DS-2), so every form of that assertion keeps
   working. We would still like to know, because it tells us whether the
   eventual removal in question 3 needs a migration or just a notice.

2. **Per-surface strings or operation ids in the flat field?** — **Per-surface
   strings.** We planned operation ids and changed our minds while building it.
   Rebinding the values of a field a downstream gate already asserts on is the
   same trap DS-5 describes, one layer down: the assertion keeps passing and
   quietly measures something else. The operation view ships as new fields
   instead, so consistency is available without anyone's gate changing meaning
   underneath them.

3. **Removal of the hand-authored path, and what notice period?** — *Still
   open, and still yours to set.* Nothing is scheduled. What shipped is the
   warning only: loading a descriptor with no `contract:` now emits a
   `DeprecationWarning` naming the generator to use. Removal will be its own
   change with its own notice. **Tell us the notice period you want and we will
   plan to it** — we have no reason to prefer one over another, and no work is
   blocked on removing it.

### One question we did not ask at plan time

`--min-coverage` now rejects values between 0 and 1 as a usage error. If any of
your pipelines passes a rate there (`--min-coverage 0.8` meaning 80%), that
invocation will start failing with a message naming both readings. It was
previously accepted as a **0.8% floor** — a gate that passed on any non-empty
run — so the failure is surfacing a misconfiguration rather than creating one.
Pass `80` for eighty percent, or `0` for no floor.
