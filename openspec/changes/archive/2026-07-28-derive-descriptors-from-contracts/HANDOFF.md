# Handoff — contract-derived gen-eval descriptors

**Date:** 2026-07-25 (updated 2026-07-26) · **Phase:** planning complete, 5 review rounds, not yet implemented
**Written for:** whoever picks this up next, with no context from the session

---

## TL;DR

Nothing is implemented yet — this is all planning. Two coupled OpenSpec changes
plus one unrelated infrastructure fix that had to happen first to make review
work at all.

| Branch | What it is | State |
|---|---|---|
| `openspec/fix-review-vendor-dispatch-config` | Repairs 3 broken review vendors | **PR #284 MERGED** (`ed56f6da`, `21f5afec`) |
| `openspec/rename-descriptor-model-levels` | Prerequisite: frees two type names | **PR #285 MERGED** — but see the warning below |
| `openspec/derive-descriptors-from-contracts` | The feature | Rebased onto `main`, pushed, no PR |

Gates re-run after the rebase, all green: `openspec validate --strict` on both
changes, `validate_work_packages.py` VALID on both (schema, refs, DAG, lock keys).

---

## ⚠️ Merging #285 did NOT satisfy the prerequisite

`rename-descriptor-model-levels` is a **planning** change. PR #285 landed six
documents — proposal, design, delta spec, tasks, work packages, a `contracts/`
README — and **no code**. On `main` today its `tasks.md` reads 11 unchecked, 0
checked, and `McpToolSpec` does not exist anywhere in
`packages/gen-eval/src/`.

Read "the rename must land first" as **the rename must be implemented and
merged**, not "its proposal must be merged". The prerequisite check below is the
authority — it probes for `McpToolSpec` and will keep exiting non-zero until the
rename is actually built.

## Start here

```
/implement-feature rename-descriptor-model-levels     # ← next
```

then, only once that has merged and the prerequisite check prints
`prerequisite 2 satisfied`:

```
/implement-feature derive-descriptors-from-contracts
```

Implementation entry point once the rename has merged:

```
/implement-feature derive-descriptors-from-contracts
```

Its `tasks.md` opens with a **Prerequisites** section carrying an executable
check. Run it first. If it exits non-zero, stop — the rename has not landed and
tasks 1.4 / 2.2 will collide with live public API.

---

## What the feature does

gen-eval's `InterfaceDescriptor` is hand-authored, and its coverage vocabulary
is unsound in four ways — all four verified empirically, not assumed:

| Claim | Verified |
|---|---|
| `openapi_spec` / `tools_manifest` / `cli_schema` are declared but read by nothing | `descriptor.py:74,80,84` + schema; zero consumers in `src/` or `tests/` |
| gen-eval's own descriptor yields **0 interfaces** | 1 service, 0 endpoints / 0 tools / 0 commands |
| Coordinator surfaces are 38 HTTP / 39 MCP / 37 CLI | exact match |
| The base spec mandates the wrong direction *and* contradicts merged code | `openspec/specs/gen-eval-framework/spec.md:12`, and `:10` still requires startup config that PR #277 made optional |

Because the declared set is empty, `unevaluated_interfaces == []` is vacuously
true — so ACA's ri-06 coverage gate **currently passes for free**. That is the
problem being solved.

The fix (design D1): **the contract is always the source; runtime introspection
is always the verifier, never the source.** Descriptors are derived from
contracts under `openspec/contracts/<cap>/`, generated as checked-in artifacts
with `--check` drift guards, and introspection only asserts the implemented
surface is a subset of the contract.

Read `proposal.md` then `design.md` (D1–D8, D10, D11). D9 is deliberately absent
— it moved to the rename change.

---

## Why there are two changes

The feature needs the names `ServiceDescriptor` and `ToolDescriptor` for
document-level archetypes. Both were already taken in the same module
(`descriptor.py:41`, `:67`) meaning unrelated things.

Carrying the rename inside the feature meant one change both **freed** two names
and **reused** them, in the same work-package DAG. That creates a state where a
name's meaning depends on which wave has run, and verification cannot assert a
stable fact about it. A gate asserting "`ToolDescriptor` no longer means the old
thing" ran in wave 0, while the type giving it its new meaning was created in
wave 1 by a package depending on wave 0. The gate could not pass.

Four variants of that one shape were found across three review rounds, each
introduced while fixing the previous one. Splitting on that seam fixed the class:
in the rename nothing is reused, so every old name has exactly one meaning
throughout.

**The sharpest thing to understand about the pair:** `ServiceDescriptor` and
`ToolDescriptor` are **reclaimed**, not removed. After both changes they still
import successfully and mean something different. A removed name fails loudly; a
deprecated name warns; a reclaimed name does neither. That is why there are two
`CONTRACT_VERSION` bumps (1→2 in the rename, 2→3 for the reclamation) and why
`DOWNSTREAM.md` DS-5 exists.

---

## State of the plan

**derive-descriptors-from-contracts** — 6 packages, 42 tasks, 31 scenarios, D1–D8/D10/D11

```
wave 0  wp-contracts
wave 1  wp-service-descriptor · wp-tool-descriptor
wave 2  wp-coverage-model · wp-subset-verifiers
wave 3  wp-integration
```

**rename-descriptor-model-levels** — 1 package (deliberately sequential), 8 tasks, 6 scenarios, D1–D4

Gates, both changes: `openspec validate --strict` pass · work-packages VALID
(schema, refs, DAG, lock keys) · `parallel_zones` valid, no scope or lock overlap.

---

## Review history

Five rounds. Findings trend `[12, 11, 6, 8, 6]` — but the count is misleading;
the *kind* is what converged:

| Round | Found |
|---|---|
| 1 | Unimplementable work, contradictions, vacuous gates |
| 2 | Same classes, mostly in round 1's fixes |
| 3 | Same classes, in round 2's fixes → triggered the extraction |
| 4 | Seam defects + import resolution |
| 5 | Ambient-environment assumptions |

Artifacts are checked in under `reviews/round-{1,2,3-partial-pi-blind,4,5}/`.

**One defect class dominated the entire effort**, appearing eight times in
different mechanisms: *an assertion whose outcome does not track the condition it
claims to test.*

1. Gate globbing a directory, exit 0 on zero matches
2. Fail-closed guard counting commands instead of coverage units
3. Alias promise unsatisfiable where two names are reused
4. Migration grep scanning `src/`, where the aliases must live
5. Coverage floor of 80% on a surface where 80% is unreachable
6. Gate at DAG root asserting a wave-1 fact
7. Bare `python3` reading an installed copy, not the tree being gated
8. Identity check that would fail a correct asymmetric implementation

If you add a gate, ask both questions: **can this fail on a broken tree, and can
it pass on a correct one?** Most of the eight failed the second, not the first.
There is now a mechanical audit — **27/27 gates** across both changes resolve
against the tree they gate and depend on no ambient environment. Re-run it after
any edit to a `command:`.

---

## Landmines

**The prerequisite check is subtle for three separate reasons**, all documented
inline in `tasks.md`. Do not "simplify" it:
- `gen_eval.ToolDescriptor` does not exist — only `ServiceDescriptor` and
  `InterfaceDescriptor` are exported at package level
- asserting `'input_schema' not in ToolDescriptor.model_fields` fails in *both*
  states, because after the rename `ToolDescriptor` aliases `McpToolSpec` which
  still has that field
- bare `python3` reads `agent-coordinator/.venv/.../site-packages/gen_eval/`,
  not this tree

**The archetypes land asymmetrically.** `ToolDescriptor` goes into
`descriptor.py` (superseding its own alias there); `ServiceDescriptor` goes into
`service_descriptor.py` (so `descriptor.ServiceDescriptor` legitimately stays the
alias). Any gate comparing the two by identity will fail a correct
implementation.

**Task 5.3 depends on 3.6 deliberately.** Migrating `evaluation/descriptor.yaml`
before the tested-identifier vocabulary is extended makes the declared surface N
flags while `covered` stays empty — turning today's vacuous pass into a
guaranteed 0% coverage violation. Do not reorder.

**D11 replaced the 80% floor for tool descriptors** with completeness-plus-
declared-exclusions. Measured: 16 long flags, 5 exercised = 31.2%. Do not
"restore" the percentage; it is arithmetically unreachable on this surface.

---

## Open, not addressed — now filed

1. **#286** — `review_dispatcher.py` discards stdout on JSON-parse failure. This
   is the root reason three broken vendors looked like one opaque problem for
   three rounds. agy's CLI printed an actionable error naming the exact fix; the
   dispatcher deleted it and reported "Invalid JSON output".
2. ~~`autopilot/SKILL.md` documents `--check-vendors`, which does not exist.~~
   **Withdrawn (#287, closed).** The flag *does* exist — implemented in
   `75e8406d` with regression tests, verified working on `main`. This
   observation was made against a tree 24 commits behind `main`; it was true
   there and false here. The same wrong-tree trap this plan's own gates were
   repeatedly fixed for, hit while writing the handoff about it.
   The residual real gap: `--check-vendors` probes *reachability*, not
   review-mode envelope conformance. It reports 5/5 available for the three
   vendors #284 fixes — pi included, the one returning `success=True` with
   empty findings. Follow-up belongs on #286.
3. **#288** — Coordinator descriptor drift: declares 38 HTTP endpoints; `src/`
   carries 82 route decorators (re-verified 2026-07-26). Out of scope here by
   design — needs a coordinator OpenAPI contract first.
4. **#289** — `docs/architecture-analysis/contracts-inventory.md` is stale: says
   4 schemas, there are 7 (re-verified). Regenerated by a project-context
   producer; promote/archive ops do not auto-regen. Same class as #168/#157,
   different producer.

Also unreviewed: `openspec/fix-review-vendor-dispatch-config` (PR #284) has had
no plan review at all. It is 3 config-line changes, each verified end-to-end by
probing the vendor, but nobody has looked at it but me.

---

## Session decisions taken with the operator

- Break the public interface for one canonical name per concept, rather than
  qualified names like `ContractServiceDescriptor`
- Extend the coverage model for many-to-one surface bindings now, not later
- Merge PR #277 (rebase) — it was an unmerged dependency this change was
  silently stacked on
- Defer the rename to its own change
