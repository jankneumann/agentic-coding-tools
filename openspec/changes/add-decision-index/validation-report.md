# Validation Report: add-decision-index

**Date**: 2026-04-24 (post-iteration-1)
**Commit**: 816dc13
**Branch**: openspec/add-decision-index
**Tier**: sequential (single `wp-main` package)
**Scope note**: This change ships a docs-index generator, a `make decisions` target, and a CI staleness gate. It does not introduce any deployable service, database schema, HTTP API, or frontend, so Deploy / Smoke / Gen-Eval / Security / E2E phases are intentionally `skip`.

## Phase Results

| Phase | Result | Details |
|-------|--------|---------|
| Deploy | skip | No deployable service; change is a build-target + code generator + CI job |
| Smoke | skip | No HTTP API to probe |
| Gen-Eval | skip | No evaluation descriptors apply — feature is a deterministic file emitter |
| Security | skip | No API surface, no new external network I/O; feature reads repo markdown and writes local markdown |
| E2E | skip | No UI |
| Architecture | pass | `validate_flows.py` on 26 changed files reports 0 findings (0 errors / 0 warnings / 0 info); 0 new entrypoints (emitter is pure file-in/file-out) |
| Spec Compliance | pass | Task-drift gate passes (0 unchecked / 8 commits). All 11 requirements verified against the live pipeline — see traceability below |
| Evidence | pass | Work-queue result audit N/A — sequential tier with single `wp-main` package, no distributed work-queue results to validate. `scope_check` and `verification` covered by the normal test gate (54 passing) |
| Logs | skip | No runtime logs to scan |
| CI/CD | pass (with pre-existing unrelated failures) | New `validate-decision-index` job passes. 11 of 14 checks pass. 3 failures pre-date this PR and are unrelated — see CI/CD section below |

## Spec Compliance — live verification

All 11 requirements in `change-context.md` verified at commit `816dc13`:

| Req ID | Evidence |
|---|---|
| skill-workflow.1–4 | 25 `architectural:` tags extracted from active + archived session-logs; `test_extract_*` tests pass |
| skill-workflow.5 | Sanitizer soak on `archive/2026-04-22-cloudflare-domain-setup/session-log.md` preserves all 4 `configuration` tags, 0 REDACTED tokens on any tag string |
| software-factory-tooling.1 | 5 capability markdown files generated: `agent-coordinator`, `configuration`, `merge-pull-requests`, `skill-workflow`, `software-factory-tooling` |
| software-factory-tooling.2 | Sample entry (`configuration.md` D1) renders title, rationale, change-id, phase name, phase date, and back-ref as a navigable Markdown link: `[openspec/changes/archive/2026-04-22-cloudflare-domain-setup/session-log.md](/openspec/changes/archive/2026-04-22-cloudflare-domain-setup/session-log.md) (D1)` |
| software-factory-tooling.3 | Supersession chain exercised by `test_supersession_chain_preserved` + `test_cross_capability_supersession` + `test_bullet_position_supersedes_resolves_with_untagged_prefix` |
| software-factory-tooling.4 | `test_new_capability_file_auto_created` + `test_stale_capability_file_removed_on_rerun` cover the deterministic-rewrite contract (spec narrowed from "incremental" this iteration) |
| software-factory-tooling.5 | `make decisions` run twice in succession; `git diff --stat docs/decisions/` reports no changes → byte-identical |
| software-factory-tooling.6 | `docs/decisions/README.md` exists, regenerated on every run, lists all 5 active capabilities |

Unit tests: **54 passed** in `skills/explore-feature/tests/` (21 extraction + 15 emission + 2 readme + 2 e2e + 6 regressions + 8 others).

## CI/CD Status

**New gate (this PR)**: ✓ `validate-decision-index` — passes (re-runs `make decisions --strict` and `git diff --exit-code`)

**All passing (11)**: `check-docker-imports`, `docker-smoke-import`, `formal-coordination`, `gen-eval`, `secret-scan`, `test`, `test-infra-skills`, `test-integration`, `test-skills`, `validate-decision-index`, `validate-specs`

**Failing (3, all pre-existing, not introduced by this PR)**:
- `SonarCloud Code Analysis` — pre-existing repo health check
- `dependency-audit-coordinator` — flags `authlib 1.6.7` CVE-2026-27962 (upstream vulnerability in an existing dependency; requires a coordinator-specific dependency bump in a separate PR)
- `dependency-audit-skills` — same authlib CVE surfaced at the skills venv

None of the three failures relate to files this PR touches.

## Architecture Diagnostics

```
Entrypoints checked: 0
Flows with test coverage: 0
Flows without test coverage: 0
Findings: 0 total (0 errors, 0 warnings, 0 info)
```

Expected outcome — this feature adds no cross-layer flows. The emitter is a library + CLI (single process, file-in/file-out) and the CI job invokes it; there is no new request-path, service boundary, or side-effect edge to validate.

## Result

**PASS** — all applicable phases green. CI-level dependency failures are pre-existing and outside this PR's scope.

**Next step**: `/cleanup-feature add-decision-index` after PR #121 approval.
