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
| Evidence | pass | Requirement traceability: 11/11 rows in `change-context.md` have Files Changed + `Evidence: pass 816dc13` populated, each linked to a named test method. Work-queue result validation is the only sub-check that does not apply to sequential tier (no distributed `artifacts/<pkg>/work-queue-result.json` is produced when a single agent owns the whole `wp-main` scope) |
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

Unit tests: **54 passed** in `skills/explore-feature/tests/` (21 extraction + 15 emission + 2 readme + 2 e2e + 6 regressions + 8 others) at commit `816dc13`.

## Evidence — note on sequential-tier scope

The Evidence phase is split into two sub-checks in `validate-feature`:

1. **Requirement traceability** — every SHALL clause in the spec deltas has (a) a named test method and (b) an `Evidence: pass <SHA>` entry in `change-context.md`. This **applies to every change regardless of tier** and is the real spec-compliance evidence. Status here: **11/11 rows populated**.
2. **Work-queue result audit** — validates `artifacts/<pkg>/work-queue-result.json` files against `work-queue-result.schema.json`, checks `contracts_revision` / `plan_revision` alignment, and audits cross-package consistency. These artifacts are only produced by parallel / coordinated tiers where multiple agents execute work packages in their own worktrees; sequential tier has a single agent owning the whole `wp-main` scope and no distributed results to reconcile. Status here: **does not apply** (not a gap — the schema is for multi-agent orchestration).

Not creating synthetic work-queue-result.json for sequential tier is intentional: fabricating it would add ceremony without adding signal. `scope_check` and `verification` that those artifacts would normally encode are covered by (a) the file-scope declaration in `work-packages.yaml` being respected by git diff (nothing outside `write_allow` was modified, confirmable via `git diff --name-only`), and (b) the 54-test suite green at HEAD.

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
