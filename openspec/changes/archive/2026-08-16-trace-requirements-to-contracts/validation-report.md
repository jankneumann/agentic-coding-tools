# Validation Report: trace-requirements-to-contracts

**Date**: 2026-08-15 17:32:22
**Commit**: 4f26059c
**Branch**: openspec/trace-requirements-to-contracts

This change is tooling + CI wiring (a requirement↔contract traceability gate
and its wiring into `/validate-feature` and CI). It does not deploy or expose
a live service, so the Deploy/Smoke/Security/E2E phases are recorded as
skipped with that reason rather than fabricated.

## Phase Results

○ **Deploy**: Skipped — change is tooling + CI wiring; no service under test
is deployed or modified by this change (only `agent-coordinator/docker-compose.yml`
exists in the repo, and it is unrelated to this change's diff).

○ **Smoke**: Skipped — depends on Deploy, which was skipped. (Confirmed:
running the smoke suite bare against `localhost:8000` returns 11
`ConnectError` failures, not the auto-skip exit 5, because no service is
listening — consistent with "no deployment", not a smoke-test regression.)

○ **Gen-Eval**: Skipped — the only `evaluation/descriptors/*.yaml` under the
repo belongs to `agent-coordinator` (an unrelated capability, not touched by
this change's diff beyond untraced contract files already reported below).
`packages/gen-eval` itself ships `evaluation/descriptor.yaml` (singular),
which the phase's descriptor glob does not match, and is exercised directly
by `packages/gen-eval`'s own pytest suite instead (see Evidence below).

○ **Security**: Skipped — no live deployment to scan (see Deploy).

○ **E2E**: Skipped — change is tooling + CI wiring; no `tests/e2e/` surface
is added or modified.

✓ **Architecture** (informational, non-critical): structural linters ran
clean of `critical` findings but surfaced 16 findings: 2 **high** and 14
**medium**.
  - **high** (both new, introduced by this change's `skills/cite-requirements/`
    skill): `skills/cite-requirements/SKILL.md:63` and
    `skills/cite-requirements/scripts/walkthrough.py:22` each hardcode the
    canonical `skills/cite-requirements/scripts/walkthrough.py` runtime path
    instead of the installed-skill-base convention other skills use (e.g.
    `<skill-base-dir>/...`). This is the same rule
    `validate-feature/scripts/linters/dependency_direction.py` enforces, and
    it is invoked non-piped, standalone, with a real non-zero exit:
    `uv run python validate-feature/scripts/linters/dependency_direction.py --skills-root .`
    → **exit 1**, naming both lines verbatim. The same script is invoked by
    CI's `test-infra-skills` job step "Validate standalone skill install
    payload" (`.github/workflows/ci.yml`), which has no
    `continue-on-error` — so this is a real, reproducible CI-breaking defect
    on the current HEAD (4f26059c), not merely an architecture-phase nit.
  - **medium** (14, file-size >500 lines): includes
    `skills/validate-feature/SKILL.md` (1015 lines — pre-existing before this
    change's +91-line 7.0b addition; the file was already over the limit) and
    `skills/tests/validate-feature/test_ci_sweep_wiring.py` (756 lines, new
    in this change). Informational; not blocking.

✓/✗ **Spec Compliance** (`spec` phase; 7.0 and 7.0b are CRITICAL within this
non-critical phase per `skills/validate-feature/SKILL.md`):

  - ✗ **7.0 Task Checkbox Drift Gate (CRITICAL)** — ran bare, never piped:
    `grep -cE "^\s*- \[ \]" tasks.md` → `UNCHECKED=3`,
    `git rev-list --count main..HEAD` → `COMMIT_COUNT=50` →
    **exit 1 (FAIL)**. The 3 unchecked items:
      - `tasks.md:547` — `Checkpoint: run tests, review diff, verify scope` (end of Phase 4)
      - `tasks.md:883` — `5.7c [human] The unmutated tree passes at capability scope` — still open; this is the acceptance run of the gate at `--scope capability` against the merge candidate, explicitly out of this validation's scope per the operator's instruction not to touch human artifacts/5.7c.
      - `tasks.md:999` — `Final checkpoint: full suite green, openspec validate --strict passes, ...` — the sign-off task this very validation run feeds evidence into, not something this run is authorized to check off.
    Per SKILL.md's CI-invoked behavior, this is recorded as a CRITICAL finding
    (Result=fail) rather than silently continued past. This reflects genuine,
    expected incompleteness (a `[human]` acceptance task and the final
    sign-off are pending) rather than an agent-fixable implementation bug —
    it was intentionally left untouched per this run's scope.

  - ✓ **7.0b Requirement-to-Contract Traceability Gate (CRITICAL, change-scoped)**
    — ran per this change's own re-rooting fix (commit `9beba62a`):
    `TRACE_ROOT="$(git rev-parse --show-toplevel)"`, then bare, never piped,
    from `$TRACE_ROOT/packages/gen-eval`:
    `python scripts/check_traceability.py --scope change --change trace-requirements-to-contracts`
    → **exit 0 (PASS)**. Output: "18 operations cite 14 requirements. This
    gate does not check that any requirement is satisfied." No touched-scope
    violations; pre-existing gaps in `agent-coordinator` and `code-search`
    (many capabilities not opted into reverse enforcement, one misplaced
    contract instance) are reported, not failed — consistent with the
    change-scoped, report-don't-fail-preexisting-debt design (D12).

  - ○ **7.1 Per-requirement live verification**: Skipped/deferred — no
    `change-context.md` exists for this change directory (it was never
    generated for this change; the Contract Ref generation feature this
    change builds in task 5.5 is for *other* changes' future matrices, not
    retrofitted onto its own). Not fabricated here; tasks.md's embedded
    "Spec scenarios" annotations plus the 7.0b gate result above are the
    de-facto traceability evidence for this change.

○ **Evidence** (`evidence`/7.5, work-package completeness): Skipped —
`work-packages.yaml` exists (3 packages: wp-model/wp-matrix/wp-wiring per
`gate_signals.package_count`), but no `artifacts/` directory exists under
this change with `work-queue-result.json` files to validate against the
schema; nothing to check.

✓ **`packages/gen-eval` test suite**: `uv sync --all-extras` (fresh venv;
picked up the `mcp` extra) then
`uv run python -m pytest -q -m "not e2e and not integration"` (matching
`ci.yml:434`) → **1213 passed, 2 skipped, 37 deselected, 0 failed**. (A bare
`pytest -q` with no marker filter surfaces 7 pre-existing, environment-only
failures in `test_integration_scenarios.py` / `test_integration_orchestrator.py`
— these are `@pytest.mark.integration` tests requiring live docker-compose
services and are excluded by CI's own marker filter; not a regression.)

✓ **`skills/` test suite**: from `skills/`, `uv run pytest -v -m "not e2e and not integration" --tb=short`
(matching `test-infra-skills`'s effective scope) → **2392 passed, 0 failed**,
including the new `tests/validate-feature/test_ci_sweep_wiring.py` (11 tests),
`tests/validate-feature/test_validate_feature_gate.py`, and
`tests/cite-requirements/test_walkthrough.py`.

✓ **Lint (ruff)**: `uv run ruff check .` from `skills/` → **All checks
passed!**

✗ **Install payload validation**: `bash install.sh --check` →
**"Skill install portability validation passed"** (passes), but the
companion step in the same CI job,
`uv run python validate-feature/scripts/linters/dependency_direction.py --skills-root .`,
→ **exit 1** (see Architecture findings above). Both commands are run
back-to-back in `ci.yml`'s `test-infra-skills` job with no
`continue-on-error`, so this job would fail CI on the current HEAD.

✓ **`openspec validate --strict --changes trace-requirements-to-contracts`**
(and full `--changes` sweep) → **34 passed, 0 failed** (34 items), including
`change/trace-requirements-to-contracts`.

○ **CI/CD**: PR #342 is open. `gh pr checks` reports no checks on the current
HEAD; the only workflow runs on record (`gh run list`) are from
2026-08-02T15:15 / 2026-08-02T00:24, both **success**, but against SHAs
(`165a4a5e`, `147e2807`) far behind the current `4f26059c` (13 commits of
IMPLEMENT/IMPL_ITERATE work since). CI has simply not re-run since — not a
failure, but not evidence for the current tree either.

## Result

**FAIL** — Two CRITICAL/blocking issues on the current HEAD:

1. **7.0 task-drift gate fails** (3 unchecked items), of which two —
   `5.7c [human]` and the `Final checkpoint` — require a human's judgment
   and action (per this run's explicit instructions, not touched here) and
   one (Phase 4's checkpoint) is a bookkeeping item that should be
   reconciled once Phase 4's own work is confirmed complete.
2. **The dependency-direction linter fails** on the new
   `skills/cite-requirements/` skill (2 high-severity, real, CI-breaking
   findings) — this one *is* an agent-fixable implementation defect: reword
   the two runtime-path examples in `skills/cite-requirements/SKILL.md:63`
   and `skills/cite-requirements/scripts/walkthrough.py:22` to use the
   installed-skill-base convention instead of the hardcoded canonical
   `skills/` path.

The 7.0b requirement-traceability gate this change itself adds — the
specific new gate this validation run was asked to exercise — **passes**
cleanly. All test suites (`packages/gen-eval`, `skills/`), lint, and
`openspec validate --strict` are green. The failures above are (a) a
human-gated acceptance/sign-off gap, and (b) one concrete, scoped, fixable
defect in new code.

Recommended next steps: fix the two `cite-requirements` path references
(implementer/iterate), then have the human complete task 5.7c's acceptance
run and the Final checkpoint before re-validating.
