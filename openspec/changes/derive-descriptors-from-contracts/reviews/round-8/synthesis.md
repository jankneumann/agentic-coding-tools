# Round 8 — IMPL_REVIEW synthesis

Scope: the full branch, `c6d8eefb..5883748a` (74 commits, 90 files, +13532/-148).
Phases 1–5 complete; all 65 task checkboxes and all 10 `Checkpoint:` lines flipped.
Vendors: codex (gpt-5.5), grok (grok-4.5), pi (qwen3-coder). Claude excluded as author.
Antigravity dispatched but returned invalid JSON — quorum 3 of 4.
Raw: 49 findings. Every claim below re-verified here by direct execution.

## Round 7 is genuinely closed — all 12 defect classes fixed

This is the headline. Round 7's twelve verified defects were re-tested
independently, by me and by two vendors, and every one is fixed in code, not
merely in prose:

| # | Round-7 defect | Verification |
|---|---|---|
| 1 | Runtime never built a derived descriptor | `load_descriptor('evaluation/descriptor.yaml')` -> `ToolDescriptor`, 17 units, `commands=1`, `executable`/`contract` preserved. `__main__.py:360` calls it. |
| 2 | `coverage_pct` element-denominated | `orchestrator.py:404` divides by `len(per_operation)`. Grok's synthetic multi-surface case: 50% operation-denominated vs 25% element. |
| 3 | `operations_for_element()` dead for HTTP | Both `'POST /things'` and `'http:POST /things'` resolve to `['create_thing']`. |
| 4 | OpenAPI `$ref` path items skipped | 3.1 `components/pathItems` resolves; path-level `parameters` merge; unresolvable and external `$ref` both raise `ValueError` (fail-closed per D1). |
| 5 | Task 4.7 gate tautological | Gate now uses the real `build_parser()`. Grok mutated `build_parser` on disk, cleared `__pycache__`, and the gate went RED; restored clean. Plus a delegation guard so re-inlining `parse_args` cannot silently revert it. |
| 6 | `--` terminator not honoured | `['--mode','template-only','--','--descriptor']` -> `['cli:--mode']` only. |
| 7 | Short flags never alias | `['-v']` with an alias map -> `['cli:--verbose']`. |
| 8 | `verify_argparse` blind to subparsers | Undocumented `--force` on subcommand `run` -> violation `cli:run --force`. |
| 9 | 5.4d threshold unreachable | `make dogfood` green: 13/13 scenarios, 58.8% coverage, `10 of 17 units exercised, 7 excluded with reasons`. The delta spec correctly scopes the 80% floor to the **service** archetype and gives the tool archetype a completeness rule. |
| 10 | `CONTRACT_VERSION` bump | Not bumped. Still `"2"`; `git diff c6d8eefb..HEAD -- contracts/__init__.py` is empty. Schema gain (`declared_interface_count`) is additive with a default. |
| 11 | `_merge_schemas` clobbers | Incompatible property types raise `ValueError` naming the element and both schemas. |
| 12 | `--min-coverage` unit footgun | `0.8` and `0.5` rejected with an explanatory message; `1`, `0`, `80` accepted. |

The new Phase-5 gates were also shown to fail on a broken tree rather than
being decoration: `check_coverage_completeness.py` exits 1 on an unexplained
unit, a blank reason, a stale exclusion, zero coverage, zero declared units and
a missing report; `generate_tool_descriptor.py --check` exits 1 on a mutated
executable and on a contract flag-count change. Both generators refuse an empty
declared surface. `verify/surfaces.py` contains no `except`, no bare `pass` and
no `return []`. Ruff clean; `openspec validate --strict` passes; the CI-selected
suite is 1050 passed / 1 skipped.

## BLOCKING

### B1 — `make test`, introduced by this change, is red on a clean tree

**Convergence: 2 of 3 vendors (codex-001 critical, grok-001 critical),
reproduced here.**

`packages/gen-eval/Makefile` is new in this change. Its `test` target runs
`uv run pytest -q -m "not slow"`, which does **not** exclude the integration
marker. Result on an unmodified tree:

    $ make -C packages/gen-eval test
    7 failed, 1047 passed, 1 skipped, 4 deselected
    make: *** [test] Error 1

All seven resolve scenarios to `<repo>/evaluation/gen_eval/scenarios/<category>`
— a coordinator-repo path that does not exist in this tree
(`tests/test_integration_scenarios.py:45`, `tests/test_integration_orchestrator.py:34`).

CI is green only because the workflow uses a different selector
(`-m "not e2e and not integration"`). So the change ships a documented developer
entry point that can never pass, next to a CI command that always does. This is
the gates-must-fail-before-work rule inverted: a target that is always red is
ignored just as fast as one that is always green, and the next real failure in
it will be invisible.

The test failures themselves predate this change; **the `make test` target that
surfaces them does not.**

**Disposition: fix** — align the `test` target with the CI selector, or repoint
the integration fixtures at paths that exist / skip with a clear message when
absent. Do not leave a red default target.

### B2 — the delta spec requires a `CONTRACT_VERSION` bump the implementation deliberately refused

**Convergence: 2 of 3 vendors (codex-002, grok-002), reproduced here.**

`specs/gen-eval-framework/spec.md:213-227`:

    A previously-aliased type name assigned to a different type SHALL resolve, at
    package level, to the new type; SHALL increment the descriptor contract version;
    ...
    #### Scenario: A reclaimed name is announced rather than silently rebound
    - **THEN** the descriptor contract version SHALL be incremented

Observed: `CONTRACT_VERSION == "2"`, `contracts/VERSION == 2`, all three
published schemas carry `x-gen-eval-contract-version: 2`, and the diff of
`contracts/__init__.py` against the merge base is empty.

The refusal is correct and deliberate — round-7 finding #9 established that
reclaiming a *Python export name* is not a breaking *JSON Schema* change, and
`DOWNSTREAM.md:192-197` says so explicitly. What was never done is amend the
requirement. The trail is visible: `handoffs/plan-2.json` decision 3 says
"CONTRACT_VERSION 1->2 in the rename and 2->3 for the reclamation"; round 7
overturned it; the spec text and the `ToolDescriptor` docstring
(`descriptor.py:413`, "which is why the spec requires a contract-version
increment") still carry the superseded plan.

This is blocking because the **delta spec is what archives into
`openspec/specs/`**. Merging as-is publishes a durable requirement that this
change's own implementation violates, and the next author to read it will
either bump the version for no reason or conclude the code is wrong.

**Disposition: fix** — amend the requirement and its scenario to demand the
downstream notice plus the package-level export correction, without a JSON
Schema contract-version bump; correct the `descriptor.py:413` docstring to
match.

## HIGH

### H1 — three of the five `flag-surface.yaml` scenarios credit a flag they do not discriminate

The file's own header (lines 3-7) sets the standard: *"Exercising here means
asserting an observable consequence, not merely passing the flag and watching
the process survive — a flag that is only parsed contributes a number to the
coverage percentage and no evidence, which is the laundering D11 exists to
stop."*

Three of its five scenarios do not meet it. Running the fixture **without** the
flag under test produces the same observable the scenario asserts:

    $ uv run gen-eval --verbose --descriptor evaluation/fixtures/no-scenarios-descriptor.yaml \
        --output-dir /tmp/noflag --fail-threshold 0
    gen-eval: descriptor loaded — 1 services, 0 interfaces, mode=template-only
    gen-eval: report written to /tmp/noflag/gen-eval-report.json
    gen-eval: FAIL (no scenarios were evaluated)
    $ ls /tmp/noflag
    findings-gen-eval.json  gen-eval-report.json  gen-eval-report.md

- `cli-mode-template-only-is-accepted` asserts `mode=template-only` — the default.
- `cli-report-format-json-writes-only-json` asserts `gen-eval-report.json` — the
  default `both` writes it too. Its own description says *"Asserting the
  **absence** of the markdown report is what makes this an exercise of the
  flag"*, but the `expect` block asserts a presence.
- `cli-no-services-skips-startup` asserts `no scenarios were evaluated` — printed
  regardless.

Each still pins that argparse *accepts* the flag (deleting it would exit 2), so
this is weaker than a no-op — but it is not the standard the file states, and
three of the ten units the D11 gate counts as "exercised" rest on it.

Root cause is expressive, not careless: `ExpectBlock` (`models.py:15-36`) has
`error_contains` but no negative string assertion and no file presence/absence
assertion, so the intended check is currently inexpressible.

**Disposition: fix** — either add the missing primitive (`error_excludes`, or a
file-absence side-effect step) and write the discriminating assertion, or move
these three units into `coverage-exclusions.yaml` with the honest reason ("no
negative-assertion primitive exists yet"). The exclusions file is exactly the
mechanism for this, and using it costs nothing but the printed percentage.

## MEDIUM

### M1 — a non-empty `contract:` string silences the deprecation warning even when it resolves to nothing

(grok-003, reproduced here.) `descriptor.py:377` tests only truthiness:

    contract: does-not-exist.yaml   ->  ToolDescriptor, 0 warnings, interfaces ['cli:--a']

The surface is still whatever someone typed, undrift-checked — the exact state
D6's warning exists to surface. **Fix:** warn (or fail closed) when `contract`
is set but does not resolve to a readable file.

### M2 — archetype dispatch is keyed on payload markers, and degrades silently

`load_descriptor` (`descriptor.py:389-397`) dispatches on `data.get("operations")`
then `data.get("executable")`. A descriptor that declares `contract:` but whose
marker is absent or empty falls through to the base model, and pydantic's
default `extra: ignore` then discards `contract`, `commands` and `operations` —
with no warning, because `contract` is truthy. Verified:

    contract present, executable stripped  -> InterfaceDescriptor, 0 warnings,
                                              contract attr ABSENT, 0 interfaces
    operations: [] on a service descriptor -> InterfaceDescriptor, 0 warnings,
                                              no operations attribute

This is round 7's blocker in a narrower shape. It is contained downstream — the
run then exits 1 — but the message is `no scenarios were evaluated`, which
misattributes the cause and sends the reader to the scenario directory.
**Fix:** dispatch on the declared archetype (an explicit `kind:`, or the
contract's own type) and raise when a descriptor declares a contract but no
recognisable archetype payload. Same family as M1: the loader trusts declared
markers without validating them.

### M3 — `--fail-threshold` and `--min-coverage` carry different units on one command line

`make dogfood` passes `--fail-threshold 1.0` (a rate, = 100%) and
`--min-coverage 1` (a percent, = 1%) three lines apart. Task 4.19's validator
closes the silent-pass case for `--min-coverage`, and the Makefile documents the
choice at length, but the asymmetry is still live for anyone copying the
invocation. **Disposition: accept or fix** — consider giving `--fail-threshold`
the same percent semantics and validator.

## LOW

1. **Stale counts in the gate's own docstring** (grok-004).
   `check_coverage_completeness.py:10-11` says "14 of gen-eval's 17 flags would
   have to be exercised and 5 are". The real number is 10. The Makefile comment
   already says 10/17.
2. **`evaluation/README.md` does not document the Phase-5 artifacts** (grok-005).
   Its layout section omits `scenarios/flag-surface.yaml` and
   `coverage-exclusions.yaml`, so a reader cannot discover the D11 gate that
   `make dogfood` runs.
3. **YAML parse errors escape as a raw traceback** (grok-006).
   `check_coverage_completeness.main()` catches `FileNotFoundError` and
   `ValueError` but not `yaml.parser.ParserError`. Still fail-closed (exit 1),
   but without the operator-readable `_fail(...)` message every other guard has.
4. **`$ref` sibling keys are dropped** (grok-007, FYI). `resolve_path_item`
   returns only the target; `parameters` declared alongside a `$ref` on the
   referencing path item are lost. OAS 3.1 leaves this undefined; worth a
   documented limitation if not fixed.
5. **The completeness checker trusts `per_interface` keys as declared units.**
   `exercised = set(report["per_interface"])` (line 85) and
   `known = set(unevaluated) | exercised` (line 111). `_attribute_interfaces`
   self-maps an identifier matching nothing declared, so such a token would both
   inflate the printed "N of M units exercised" and shield a stale exclusion.
   Narrow today (the CLI tokeniser filters by declared membership); intersect
   with the declared set rather than trusting the report's key space.

## FYI — not defects in this change

- The CI `mypy --strict` step is `continue-on-error: true`, and the tree has 5
  errors (`findings_emitter.py:44,296`, `llm_generator_base.py:87`,
  `clients/mcp_client.py:33`, `__main__.py:137`). All pre-existing at the merge
  base. The "strict" type gate cannot fail the build.
- The branch is **23 commits behind main**. Green CI here is not green CI on the
  merge result; rebase before merging.
- Antigravity returned invalid JSON and contributed nothing. This is the
  dispatcher fragility already noted as unfiled in the round-7 resume note
  (a malformed vendor response is discarded rather than re-dispatched).
- Pi returned 14 findings, all `disposition: accept` corroborations of the
  round-7 fixes, but labelled `severity: critical` — a combination the review
  schema's own red-flag list calls incoherent. Its finding 10 ("CONTRACT_VERSION
  was correctly bumped from 1 to 2") credits this change with the prerequisite
  PR's bump and is discounted.

## Verdict

**not_converged.** Two blocking findings, each confirmed by two independent
vendors and reproduced here, plus one high. All three are narrow: a Makefile
selector, a spec paragraph plus a docstring, and three scenario assertions (or
three exclusion entries). None of them re-opens a round-7 defect — the
implementation itself is in good shape.
