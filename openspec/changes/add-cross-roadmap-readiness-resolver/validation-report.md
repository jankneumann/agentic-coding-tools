# Validation Report: add-cross-roadmap-readiness-resolver

**Date**: 2026-09-10 11:32:20 -04:00
**Commit**: `f4eec8418875ba6e9075cd4b580ab9901d454af8`
**Validated tree**: `a88a3faadec1650011b36ecbf510c0a2ae4b670a`
**Branch**: `openspec/add-cross-roadmap-readiness-resolver`
**Surface**: non-deployable deterministic Python CLI/runtime library

## Phase Results

| Phase | Result | Details |
|---|---|---|
| Deploy | ○ | Not applicable: `deployable: false`; no service or container changes. |
| Smoke | ○ | Not applicable: no running endpoint; the CLI boundary is covered by direct tests and a repository smoke invocation. |
| Gen-Eval | ○ | Not applicable: no generator/evaluator descriptors or live service behavior changed. |
| Security | ✓ | Read-only local-file surface; no dependency, credential, network, shell, or write path added; independent review passed. |
| E2E | ○ | Not applicable: no browser or deployed user flow changed. |
| Architecture | ⚠ | Direct source flow passed; graph refresh degraded because configured `src/` and `web/` roots are absent. |
| Traceability | ✓ | 3/3 requirements and 11/11 scenarios mapped to passing evidence in `change-context.md`. |
| Spec Compliance | ✓ | Strict OpenSpec validation passed all 90 active items; change contract validates. |
| Logs | ○ | Not applicable: no service process was deployed. |
| CI/CD | ○ | No PR existed at validation time; local required gates passed. |

## Deploy

**Status**: not applicable

The package declares `deployable: false` and changes only a local deterministic runtime/CLI plus its Python consumers and tests.

## Smoke Tests

**Status**: not applicable

No service health surface exists. `resolve_readiness.py --repo-root .` emitted parseable ranked JSON from the real repository, and the CLI regression verifies newline-terminated JSON plus exit 2 for hard-invalid input.

## Security

**Status**: pass

The resolver reads only active roadmap/checkpoint files below the supplied repository root. It adds no writes, network calls, subprocesses, dependencies, secrets, or dynamic code execution. Diagnostic details are bounded to 512 characters. Independent Antigravity review returned a concrete severity-none security finding.

## E2E Tests

**Status**: not applicable

There is no browser, service, database, or deployed workflow in scope. Cross-component behavior is exercised through the runtime, autopilot-roadmap, plan-roadmap, and supervise integration suites.

## Architecture

**Status**: pass with advisory degradation

The canonical flow and dependency direction pass direct inspection and behavioral tests; see `architecture-impact.md`. Automated graph refresh could not run because configured source roots are absent, not because of a change failure.

## Spec Compliance

**Status**: pass

All three requirements and eleven scenarios are traced in `change-context.md` with passing evidence at `f4eec841`.

Validation matrix:

- 465 focused roadmap-runtime, autopilot-roadmap, plan-roadmap cross-roadmap, and supervise tests passed.
- 14 dedicated readiness tests passed, including schema validation, exact ownership, fail-closed invalid state, checkpoint precedence, global order, fingerprint stability, and CLI status.
- Ruff passed for every touched Python source/test.
- strict OpenSpec validation passed 90/90 active changes/specs.
- work-package schema, references, DAG, and lock validation passed.
- base-relative context-impact validation passed after declaring the implied documentation surface.
- package scope passed for all 41 feature-authored files with zero violations.
- `bash skills/install.sh --check` passed.
- real Codex/Antigravity plan and implementation reviews converged with no remaining blocking findings.

## Logs

**Status**: not applicable

No service process was launched and no runtime log stream exists.

## CI/CD

**Status**: not applicable

No pull request existed at validation time. PR checks become available after the submission gate permits creation.

## Known Limitation

The optional monolithic `pytest skills/tests` diagnostic is not a supported collection mode and stopped during collection with 36 pre-existing bare-module collisions (`models` and `runner`) across unrelated skill trees. The package-declared isolated/focused matrix passed 465 tests, including every affected consumer; no ri-16 failure was observed.

## Result

**PASS** — All required phases for the non-deployable ri-16 surface passed. The change is ready for PR submission and the human merge gate.
