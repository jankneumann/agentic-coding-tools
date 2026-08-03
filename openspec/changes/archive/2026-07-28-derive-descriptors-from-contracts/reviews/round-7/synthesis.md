# Round 7 — IMPL_REVIEW synthesis

Scope: waves 1–3 implemented (`f09d7ae2..9d811ecc`) + the wave-4 plan (tasks 4.7, 5.1–5.8).
Vendors: codex, grok, antigravity, pi (claude excluded — authored the implementation).
Raw: 25 findings. Verified below by direct execution, not by vendor assertion.

## BLOCKING — the runtime never constructs a derived descriptor

**Convergence: 2 of 4 vendors independently, 4 findings** (codex-001 critical,
grok-1 critical, codex-002 high, grok-9 medium).

`__main__.py:324` loads every descriptor with `InterfaceDescriptor.from_yaml()`.
`ServiceDescriptor` adds `operations`; `ToolDescriptor` adds
`commands`/`executable`/`contract`. Pydantic drops those on the base model, so
every derived artifact loses exactly the fields that make it derived.

Verified on the real CLI contract:

    ToolDescriptor.from_yaml(generated)   -> 17 interfaces
    InterfaceDescriptor.from_yaml(same)   ->  0 interfaces

Consequences, all reachable today:
- `build_operation_coverage()` sees no `operations` and takes the `_from_element`
  fallback, so D4's operation keying never engages at runtime and fan-in is lost
  (`mcp:check_locks` covers one pseudo-operation instead of `list_active_locks`
  + `get_lock_status`).
- Task 5.3's stated acceptance — "after this task it must report the contracted
  flag count" — cannot be met. The migrated YAML loads to 0 interfaces.
- Tasks 5.1/5.2 (deprecation when a descriptor declares no contract) cannot be
  implemented correctly: `contract` is discarded on load, so the warning either
  always fires or can never see the field.

**Plan gap, not just a code bug.** `tasks.md` and `design.md` contain zero
occurrences of `from_yaml`, archetype-aware loading, or descriptor dispatch.
No task owns this. Phase 5 as written cannot deliver its own acceptance criteria.

**Disposition: fix** — add an archetype-aware load path (dispatch on
`operations` / `executable` / `contract`, or an explicit `kind` field) as a new
task sequenced BEFORE 5.1, 5.2 and 5.3.

## HIGH — verified defects in landed code

1. **`coverage_pct` is element-denominated, contradicting D4**
   (antigravity-001). `orchestrator.py:390` divides by `len(all_interfaces)`.
   An operation exposed on 3 surfaces and fully exercised via HTTP reports 33%.
   This is the exact arithmetic D4 exists to remove — the operation model was
   built, then the headline number kept the old denominator. `--min-coverage`
   gates on this number.

2. **`operations_for_element()` is dead for HTTP** (grok-2 high, codex-006 low —
   2 vendors). `service_descriptor.py:234` compares `op.interface_id(surface)`
   against `f"{surface}:{element}"`, but `interface_id("http")` returns an
   unprefixed `"METHOD /path"` (line 102-103). Confirmed by inspection: the HTTP
   branch can never match, so the public fan-in API returns `[]` for the primary
   service surface.

3. **OpenAPI `$ref` path items are silently skipped** (codex-003, grok-3 —
   2 vendors). Both `_extract_operations` and `verify_fastapi` iterate path-item
   keys and test membership in `_HTTP_METHODS`; `$ref` is not one, so a 3.1
   document using `components/pathItems` yields no operations and no violations.
   The declared surface shrinks silently — a fail-open in the direction D1 says
   must fail closed. Related: path-item-level `parameters` are not merged into
   each operation, so derived MCP input schemas omit required path params.

4. **Task 4.7's gate as landed is tautological** (grok-6 high, pi-001).
   `test_subset_verifiers.py:193-209` builds a synthetic parser by adding one
   argument per contracted unit — a mirror of the contract, not `parse_args`.
   Adding an uncontracted flag to the real `parse_args` leaves it green.
   `parse_args` also discards the `ArgumentParser`, so CI cannot reach the real
   surface without a `build_parser()` extraction. This is the
   gates-must-fail-before-work rule: the gate must fail on an unmodified tree.

## MEDIUM — verified

5. **`--` option terminator not honoured** (codex-004, grok-4 — 2 vendors).
   Verified: `args=['--mode','template-only','--','--descriptor']` records
   `['cli:--mode', 'cli:--descriptor']`. Coverage is credited for a token the
   process never interpreted as a flag.

6. **Short flags never alias to their long unit** (grok-5). `coverage_units`
   emits only `flag.name`; a step using `-v` produces `cli:-v`, fails the
   declared-membership filter, and `cli:--verbose` stays uncovered despite a
   real exercise. Same D10 vocabulary split the change exists to close.

7. **`verify_argparse` does not descend into subparsers** (codex-005).
   `_SubParsersAction` has no option strings, so an undocumented `--force` on a
   subcommand is invisible to the verifier.

8. **5.4d's threshold is unreachable** (antigravity-004, grok-7 — 2 vendors).
   Dogfood covers ~5 of 17 flags (~29%). If 5.4d sets `--min-coverage 80` to
   match the "80%+" language still in `specs/gen-eval-framework/spec.md`,
   `make dogfood` is permanently red even when D11 completeness is satisfied.
   Completeness is the tool gate; the percentage is informative.

9. **5.8's `CONTRACT_VERSION` bump violates repo policy** (antigravity-003).
   `CONTRACT_VERSION` versions published JSON Schemas and bumps only on breaking
   schema change. Reclaiming Python export names is not one. Bumping falsely
   signals a breaking schema change to consumers.

10. **The declared-surface filter hides exercised contract omissions**
    (antigravity-002, pi-005 — 2 vendors). This is deliberate choice 3, and the
    reviewers accept the tokenising rationale but note the cost is real: a flag
    the suite exercises and the contract omits produces no tested identifier,
    and `_attribute_interfaces`'s self-mapping fallback never sees it. The
    subset verifier catches this class only once 4.7 is non-tautological.

## LOW

11. **`_merge_schemas` clobbers conflicting properties** (grok-10, accept).
    Union-by-dict-spread is last-write-wins; two operations requiring `x` with
    incompatible types yield one silent type. Intersecting `required` is argued;
    property clobber is not.

12. **`--min-coverage` unit footgun** (grok-8, pi-004). `0.8` is a legal 0.8%
    floor indistinguishable from a user meaning 80%, and it silently PASSES a
    ~30% suite — failing open, the opposite of the gate's purpose.

## Not accepted

pi-002 and pi-003 report Phase 5 tasks as "not implemented". They are wave-4
work that has not started; this is the plan's state by design, not a defect.
