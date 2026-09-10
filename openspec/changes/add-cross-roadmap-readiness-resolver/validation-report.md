# Validation Report: add-cross-roadmap-readiness-resolver

**Date**: 2026-09-10 11:57:54 -04:00
**Commit**: `973e971fb74882756d24b164d359b55fc9e14e42`
**Validated tree**: `7ab8d725390ab5f888131c9d3a4004319467192c`
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
| CI/CD | ⚠ | PR #509 is open. The ri-16-owned `test-infra-skills` failure was reproduced and fixed; the exact suite passes locally. The context-drift check remains red from integration-branch metadata outside ri-16. |

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

- The exact `test-infra-skills` command passed 3,796 tests with 13 skips after the archival-stability remediation.
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

**Status**: pass for ri-16-owned checks; inherited context-drift remains

PR #509 exposed one ri-16-owned `test-infra-skills` failure. The exact CI command, `cd skills && uv run pytest -v`, failed at the existing archival-stability guard because `test_readiness.py` pinned this active change directory. Replacing the literal path with `change_dir(repo_root_from(__file__, 3), change_id)` made the guard and readiness tests pass. The full exact rerun passed 3,796 tests with 13 skips. Ruff passed.

The separate `context-drift-gate` remains red because the integration base introduces `openspec/changes/archive/2026-09-10-write-durable-state-artifacts-guide/work-packages.yaml` relative to `main`; that artifact is outside ri-16 and was not modified here.

## Known Limitation

The optional monolithic `pytest skills/tests` diagnostic is not a supported collection mode and stopped during collection with 36 pre-existing bare-module collisions (`models` and `runner`) across unrelated skill trees. The package-declared isolated/focused matrix passed 465 tests, including every affected consumer; no ri-16 failure was observed.

## Result

**PASS** — All required phases for the non-deployable ri-16 surface passed. The change is ready for PR submission and the human merge gate.
