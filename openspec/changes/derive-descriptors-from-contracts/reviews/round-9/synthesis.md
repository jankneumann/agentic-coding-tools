# Round 9 — IMPL_REVIEW synthesis

Confirming round for Phase 6 (commit `081663b2`), which claimed to remediate
round 8's 2 blocking + 1 high + 3 medium + 5 low findings.

Vendors: codex (gpt-5.5, 481s), grok (grok-4.5, 407s), antigravity
(gemini-3.6-flash-medium, 145s). Claude excluded as author. Pi returned invalid
JSON and contributed nothing — quorum 3 of 4.

Raw: 23 findings. **Zero blocking. Zero critical. Zero high.** Twenty are
`disposition: accept` confirmations; three are nits. Every round-8 finding was
independently re-verified here by direct execution as well as by the vendors.

## Round 8 is closed — all eleven items confirmed fixed

Each row was re-run here, and by at least two vendors independently.

| # | Round-8 finding | Verification |
|---|---|---|
| B1 | `make test` red on a clean tree | `make -C packages/gen-eval test` → **exit 0**, `1068 passed, 1 skipped, 12 deselected`. Selector is now `-m "not slow and not e2e and not integration"`; CI's is `-m "not e2e and not integration"` (`ci.yml:428`, gen-eval-tests job). Grok's collect-only diff: CI 1073 tests vs make 1069 — the 4-test gap is exactly the `slow` install/wheel suite. A **strict subset**, not a hide-the-failures exclusion. |
| B2 | Spec demanded a `CONTRACT_VERSION` bump the code refused | Requirement and both scenarios now state the negative. `CONTRACT_VERSION == "2"`, `contracts/VERSION == 2`, all three published schemas at `x-gen-eval-contract-version: 2`. `descriptor.py:468` docstring corrected to "deliberately NOT incremented". `DOWNSTREAM.md` DS-5 names both meanings. `openspec validate derive-descriptors-from-contracts --strict` → valid. Package export: `from gen_eval import ToolDescriptor` is `gen_eval.descriptor.ToolDescriptor`, not `McpToolSpec`. |
| H1 | 3 of 5 flag scenarios did not discriminate their flag | **All five** now discriminate. Verified here by removing each flag from the invocation: `--verbose` → "descriptor loaded" absent; `--min-coverage 0.8` → no "not a rate", exit 1 not 2; `--report-format json` → `gen-eval-report.md` present, so `error_excludes` fails; `--mode not-a-mode` → no invalid-choice, exit 1 not 2; `--no-services` → `CalledProcessError` raised by the `false` startup. Grok reproduced all five in-place against the real dogfood suite and restored the file to its original md5. |
| M1 | Bogus `contract:` path silenced the D6 warning | `contract: does-not-exist.yaml` now raises `ValueError` naming the path. |
| M2 | Declared contract + no archetype marker fell to the base model | Raises `ValueError`. Empty `operations: []` is falsy and likewise refused. **Rule 4 holds**: a legacy descriptor with no `contract:` loads as `InterfaceDescriptor` with an *identical* `model_dump()` to `InterfaceDescriptor.from_yaml()` and exactly one `DeprecationWarning`. |
| M3 | `--fail-threshold` rate vs `--min-coverage` percent | Accepted with documentation. Help text names the asymmetry, gives the `1.0` + `1` worked example, and states why reconciling would silently redefine every existing invocation (Rule 4). All three vendors agree documenting is the correct resolution. |
| L1 | Stale "5 of 17" in the gate docstring | Now "10 are"; matches dogfood output. |
| L2 | `evaluation/README.md` omitted Phase-5 artifacts | Documents `flag-surface.yaml`, `coverage-exclusions.yaml`, both fixtures, the D11 gate and the remove-the-flag discrimination check. |
| L3 | YAML parse errors escaped as tracebacks | Malformed exclusions YAML → exit 1 with `... is not valid YAML: ...`; malformed report JSON → exit 1 with `... is not valid JSON: ... re-run make dogfood`. No traceback in either. |
| L4 | `$ref` sibling keys silently dropped | `resolve_path_item` refuses any sibling but `summary`/`description`, naming the path and the siblings. Gated on `$ref` being present, so pure refs and non-ref path items are unaffected. |
| L5 | Gate trusted report-derived key space | Cross-checks `len(known) != declared_interface_count`. Injecting an undeclared identifier into `per_interface` → exit 1 ("declares 17 ... names 18"). A report missing the field fails closed as zero declared units, not a green bootstrap hole. |

### The gates fail before they are worth anything

Confirmed here and by two vendors that each gate goes RED on a broken tree:

- `check_coverage_completeness.py` — exit 1 on a mutated declared count, a
  missing report, a blank exclusion reason, a stale exclusion, an unexplained
  unit, 0% coverage, and a legacy report with no `declared_interface_count`;
  exit 0 on the clean report.
- `generate_tool_descriptor.py --check` — exit 0 clean
  (`tool descriptor up to date (17 coverage units)`); exit 1 with a unified diff
  under a mutated `executable` or a mutated flag name.
- The task-4.7 argparse gate — codex and grok each added an undocumented flag to
  the real `build_parser()`, cleared `__pycache__`, and the test FAILED naming
  the rogue flag; restored and re-ran green.

Both vendors that mutated files restored them byte-for-byte and reported
`git diff -- packages/gen-eval/` empty.

Tree state: `make test` 1068 passed / 1 skipped; `make dogfood` 13/13, 58.8%,
`10 of 17 units exercised, 7 excluded with reasons`; `make lint` clean;
`generate_tool_descriptor.py --check` clean; `openspec validate ... --strict`
valid. `evaluation/.reports/` is gitignored, so dogfood runs leave no residue.

## Non-blocking findings

### N1 (medium) — coverage attribution credits a flag for being *passed*, not for being *asserted*

Raised here, not by a vendor; the vendors checked only the five
`flag-surface.yaml` units H1 named.

`Evaluator._extract_interfaces` (`evaluator.py:614-623`) credits a coverage unit
for **any** flag token appearing in a scenario step's `args` that is in the
declared set. Nothing links the credit to whether an assertion depends on the
flag. H1 was fixed at the scenario level — the three non-discriminating
assertions were rewritten — but the mechanism that let them launder coverage is
unchanged, and two of the ten currently-credited units still ride it:

- **`cli:--output-dir`** — removing it from the
  `cli-report-format-json-writes-only-json` invocation leaves every asserted
  observable intact: exit still 1, `error_contains: "gen-eval-report.json"`
  still matches (the report is simply written to the cwd), and
  `error_excludes: "gen-eval-report.md"` still holds.
- **`cli:--fail-threshold`** — removing it entirely yields the identical
  observable, `FAIL (no scenarios were evaluated)` at exit 1, because the
  zero-scenario guard fires before any threshold arithmetic.

Both are scaffolding on scenarios whose assertions are about a different flag.
This is exactly what `flag-surface.yaml:3-12` and `evaluation/README.md:85-88`
declare D11 exists to stop, and by their own stated operational test — "remove
the flag under test from the scenario's args and the scenario must fail" —
neither unit is exercised. The honest figure is 8 of 17 (47%), which still
clears the `--min-coverage 1` floor, so **no gate outcome changes**.

Weaker than a no-op rather than worthless: each still pins that argparse accepts
the flag. The same reasoning round 8 applied to H1.

**Disposition: fix or exclude** — either give each a discriminating assertion
(`--output-dir` has an obvious one: assert the report path under a non-default
directory) or move both into `coverage-exclusions.yaml` with an honest reason.
Not blocking.

### N2 (nit, codex-001) — `work-packages.yaml` still carries the superseded round-8 B2 plan

`work-packages.yaml:446-559` still instructs a `CONTRACT_VERSION 2 -> 3` bump —
the plan Phase 6 deliberately overturned and the delta spec now forbids — and
its D11 verification command uses positional arguments the script does not
accept (`check_coverage_completeness.py evaluation/.reports/gen-eval-report.json`
→ exit 2, `unrecognized arguments`). Stale orchestration metadata, not a runtime
failure; the Makefile gate it describes is correct and green.

**Disposition: fix.** Cheap, and it is the same class of stale-plan artefact
that produced B2 in the first place.

### N3 (nit, grok-013) — one uncoerced field in the D11 gate

`check_coverage_completeness.py:67` does a bare
`int(report.get("declared_interface_count") or 0)`. A non-numeric string raises
an uncaught `ValueError` traceback instead of the `_fail(...)` message every
other guard gives — the exact gap L3 closed elsewhere. Still fail-closed; only
reachable with a hand-corrupted report.

### N4 (fyi, codex-004) — bare `openspec validate --strict` selects no target

Exits 1 with `Nothing to validate` in a non-interactive shell. Reproducible
commands must name the change explicitly. Documentation only.

## FYI — not defects in this change

- **Pi returned invalid JSON** and contributed nothing. Round 8 lost antigravity
  the same way. This is the dispatcher fragility noted as unfiled since round 7:
  a malformed vendor response is discarded rather than re-dispatched, and two
  consecutive rounds have now run at 3-of-4 quorum because of it. Worth filing.
- The branch is **~23 commits behind main**; green here is not green on the
  merge result. Rebase before merging.
- `mypy --strict` reports its 5 pre-existing errors behind a
  `continue-on-error: true` step.
- Untracked `packages/gen-eval/review-findings.json` and
  `openspec/schemas/context-refresh-*` are not part of this change.

## Verdict

**converged.** No blocking findings from any of three independent vendors, and
none raised here. Every round-8 finding is confirmed fixed by execution rather
than by assertion, the new Phase-6 code was reviewed as new code, and every gate
this change adds was shown to go red on a broken tree and green when restored.

The four items above are all non-blocking. N1 and N2 are worth doing before
merge if the cost is acceptable; neither changes a gate outcome, and neither
re-opens a round-7 or round-8 defect.
