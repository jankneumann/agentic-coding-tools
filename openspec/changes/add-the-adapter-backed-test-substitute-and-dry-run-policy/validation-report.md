# Validation Report: add-the-adapter-backed-test-substitute-and-dry-run-policy

**Branch**: openspec/add-the-adapter-backed-test-substitute-and-dry-run-policy

## Phase Results

Invoked as `/validate-feature add-the-adapter-backed-test-substitute-and-dry-run-policy --phase spec,evidence` per `/implement-feature` Step 6.5, matching `ri-01`/`ri-02`'s own split. This package has no deployable surface (a library) — Deploy/Smoke/Security/E2E are not applicable, not skipped.

## Spec Compliance

**Status**: pass

- Task checkbox drift gate (7.0): 0 unchecked boxes.
- Requirement-to-contract traceability gate (7.0b): `check_traceability.py --scope change --change add-the-adapter-backed-test-substitute-and-dry-run-policy` exits 0. No OpenAPI contract for this capability, correctly excluded.
- Per-requirement verification (7.1): 3/3 new requirements verified — see `change-context.md`'s matrix. 45 tests pass, 1 correctly skips (the adapter-backed behavioural test, no `ANTHROPIC_API_KEY` in this environment). `ruff check` and `mypy` clean on every file this item touched.

## Evidence (Work Package)

**Status**: not applicable

Implemented directly by the orchestrating session, same as `ri-01`/`ri-02` — no `artifacts/wp-main/result.json` to validate against `work-queue-result.schema.json`. Evidenced directly: `git diff --name-only main..HEAD` matches `work-packages.yaml`'s (corrected) `write_allow` exactly, all 45 tests plus `ruff`/`mypy` pass.

## Additional findings from this validation pass

- Confirmed the double opt-in gate (`ANTHROPIC_API_KEY` AND `SYSTEM_ONE_ADAPTER_TESTS=1`) correctly skips when either variable alone is set, not just when both are absent — verified directly, not only through the test's own assertion.
- Found and fixed `skills/uv.lock` staleness dating back to `ri-02` (see `change-context.md`'s "Lockfile propagation" section) — `test-skills`'s CI job never actually syncs `skills/` itself, so this had no way to surface as a CI failure until now.
- A fresh zero-extras scratch-venv install still succeeds; `decide(..., dry_run=True)` returns `None` without any extras installed at all.

## Result

**PASS** (environment-safe phases; no deployable surface exists for this library).

Ready for PR creation.
