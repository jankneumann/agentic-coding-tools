# Validation Report: derive-descriptors-from-contracts

**Date**: 2026-07-27
**Commit**: 081663b2
**Branch**: openspec/derive-descriptors-from-contracts

## Phase Results

○ Deploy: Skipped — no docker-compose.yml relevant to this package (pure-Python `gen-eval` library change, no live service to deploy)
○ Smoke: Skipped — no live HTTP/MCP service surface for this change
✓ Gen-Eval (dogfood): 13/13 scenarios passed (100.0%), coverage 58.8% (10 of 17 units), `check_coverage_completeness.py` exit 0
○ Security: Skipped — no network-facing surface changed; non-critical phase not run this pass
○ E2E: Skipped — no `tests/e2e/` directory for this package
✓ Spec Compliance: 8/8 requirements traced and verified against live execution (see `change-context.md`, generated this run)
✓ Evidence (work-packages): `tasks.md` 0/N unchecked, no drift between plan and commit history (75 commits ahead of `main` on this branch)
✓ Log Analysis: N/A (no deploy log; ruff/mypy/test output inspected directly, see below)
✓ CI/CD: `openspec validate --strict` passes; ruff clean; mypy 5 pre-existing errors (documented, `continue-on-error` in CI); ci.yml selector reproduced locally

## Independent Verification (re-run, not carried over from IMPL_REVIEW round 9)

All of the following were executed fresh against commit `081663b2` in a detached
checkout, independent of and corroborating `reviews/round-9/synthesis.md`:

- **Round-7 BLOCKING finding** ("`__main__.py:324` loads every descriptor with
  `InterfaceDescriptor.from_yaml()`, discarding `operations`/`commands`/`executable`")
  — **confirmed fixed**. `__main__.py:368` now calls `load_descriptor()`
  (`descriptor.py:337`), which dispatches on document shape (`operations` →
  `ServiceDescriptor`, `executable` → `ToolDescriptor`, neither → base model).
  The fix is structural, documented in the function's own docstring citing the
  exact defect it closes.
- `make test`: **1068 passed, 1 skipped, 12 deselected** (matches claim exactly;
  the 1 skip requires `make dogfood` to have run first — order-dependent, not a
  regression)
- `make dogfood`: **13/13 passed (100.0%)**, coverage **58.8%** (10/17 units)
- `make lint` (ruff): **clean**
- `mypy src/gen_eval/ --strict --ignore-missing-imports`: **5 errors**, all
  pre-existing (matches claim exactly)
- `openspec validate derive-descriptors-from-contracts --strict`: **valid**
- `generate_tool_descriptor.py --check`: **up to date (17 coverage units)**
- `tasks.md`: **0 unchecked boxes**
- `CONTRACT_VERSION == "2"`, matches all three published contract schemas'
  `x-gen-eval-contract-version`
- Rename prerequisite (`rename-descriptor-model-levels`) confirmed actually
  landed in code: `gen_eval.ToolDescriptor is gen_eval.McpToolSpec` → `False`
  (distinct types, not silently-aliased names)

## Known non-blocking findings (carried from round-9, not re-litigated)

- N1: coverage attribution credits a flag for being passed, not asserted —
  honest figure is 8/17 not 10/17; no gate outcome changes
- N2: `work-packages.yaml` still instructs the superseded `CONTRACT_VERSION 2->3`
  bump (archived plan history, not a live requirement) — confirmed still present
  at `work-packages.yaml:446,557-559`
- N3: uncoerced `int()` in `check_coverage_completeness.py:67` — confirmed
  present, cosmetic (still fail-closed on the paths that matter)
- N4: bare `openspec validate --strict` selects no target — documentation-only

## Result

**PASS** — Ready for SUBMIT_PR.

Caveat carried forward from round-9 (not a validation blocker, but must be
addressed before merge): the branch is ~23 commits behind `main` and must be
rebased before the PR is opened — green here is not green on the merge result.
