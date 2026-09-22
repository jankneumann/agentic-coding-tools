# Validation Report: pin-isolation-contract

Validated implementation/review commit: `741f9ff2`  
Comparison base: `09cc9216` (`origin/openspec/add-adaptive-model-router`)

## Surface Classification

**Status**: pass

The validation surface classifier reports `deployable: false`. DG-05 changes a
Python contract/configuration and routing boundary, tests, schemas, and OpenSpec
artifacts; it adds no independently deployable service, UI, or migration.

## Spec Compliance

**Status**: pass

- Strict OpenSpec validation passed.
- Traceability validation passed: 69 operations cite 37 requirements.
- All three DG-05 requirements are traced to implementation and tests in
  `change-context.md`; all tasks are complete.
- Work-package validation, including overlap checks, passed.
- Canonical isolation is exactly `none|worktree|sandbox`; absent values fall
  through with source provenance, invalid present values fail at their named
  rung, and exact agent/mode overrides have router/outage parity.
- `container` remains explicitly outside scope and requires a later contract,
  schema, dispatcher, fallback, and enforcement amendment.

## Test Evidence

**Status**: pass

- Coordinator regression partition: 2,650 passed, 43 skipped, 1 warning.
- Order-sensitive policy modules in an isolated process: 193 passed.
- Skills routing-fallback and review-dispatcher suites: 146 passed.
- Affected coordinator and skills Ruff checks passed.
- The two-process coordinator partition covers the complete suite while avoiding
  known pre-existing process-global policy-test state contamination.

## Evidence Integrity

**Status**: pass

- Vendor implementation review reached the configured 2-of-5 quorum (Claude and
  Grok) with no confirmed blocking consensus finding.
- Three adapters failed because the review packet exceeded their argv transport
  limit; their failure metadata and the two successful raw reviews are preserved
  under `reviews/implementation/`.
- Five unconfirmed advisories were reconciled in the implementation review
  summary. No choices ledger exists because the independent audit dispatch was
  unavailable at the repository thread limit; the session log records that
  fallback.
- No work-queue result exists because IMPLEMENT/VALIDATE used the documented
  inline fallback after sub-agent dispatch reached the same thread limit.

## Architecture

**Status**: pass

Architecture policy is advisory. The correctly parameterized refresh completed;
scoped flow validation reported 0 findings. Repository-wide diff and structural
checks reported existing/stale global topology and file-size advisories but no
blocking DG-05 dependency or flow violation. See `architecture-impact.md`.

## Deploy

**Status**: not applicable

The change is non-deployable and introduces no runtime service instance.

## Smoke Tests

**Status**: not applicable

No deployment surface exists; the contract is exercised by unit and integration
tests above.

## Gen-Eval

**Status**: not applicable

The repository descriptor covers live coordinator HTTP/MCP/CLI service interfaces;
DG-05 adds no endpoint or tool and has no change-specific live-service scenario.

## Security

**Status**: not applicable

The surface classifier does not require a deployable security phase. Contract
fail-closed behavior and schema parity are covered by the regression suites.

## E2E Tests

**Status**: not applicable

DG-05 has no browser or deployed end-to-end surface. Cross-boundary
router/configuration/outage-fallback parity is covered by the integration suites.

## Logs

**Status**: not applicable

No live deployment was created, so there are no runtime logs for this validation.

## CI/CD

**Status**: skipped

The branch had not yet been pushed and no pull request existed during local
validation. Pull-request checks will be inspected after submission.

## Validation Review

**Status**: pass

All required phases for the non-deployable surface passed. Non-applicable phases
are explicitly distinguished from skipped checks; advisory limitations are
preserved above. Result: **PASS**.
