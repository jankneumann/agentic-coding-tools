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

**Compatibility.** The flat `unevaluated_interfaces` list is still emitted,
computed from the operation model, for the deprecation window (design D6). Your
existing assertion keeps working. Two caveats:

- Its **values** change once a descriptor is contract-derived: entries become
  operation ids rather than per-surface strings.
- Its **cardinality** drops for multi-surface projects — one entry per
  uncovered operation instead of up to three.

If ri-06 asserts only emptiness, nothing breaks. If it asserts on specific
strings or on a count, it will need updating.

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

## Questions back to you

1. Does ri-06 assert only `unevaluated_interfaces == []`, or also on specific
   values or counts? DS-2 is a no-op for the first case and a change for the
   others.
2. Would you rather the flat field keep emitting **per-surface strings**
   (maximum compatibility, but then it disagrees with the operation model), or
   **operation ids** (consistent, but the values change)? Currently planned as
   operation ids.
3. Any objection to the eventual removal of the hand-authored descriptor path,
   and what notice period would you want?
