# Implementation Findings

<!-- Each iteration of /iterate-on-implementation appends a new section below.
     Do not remove previous iterations — this is a cumulative record. -->

## Iteration 1

<!-- Date: 2026-02-20 -->

### Findings

<!-- Finding types: bug, edge-case, workflow, performance, UX
     Criticality: critical > high > medium > low -->

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | bug | high | `main.py` called `check_prereqs.sh --json` without `--require`, so missing prerequisites were never surfaced and bootstrap auto-mode could not trigger correctly. | Added plan-derived prerequisite requirements (`dependency-check`, `zap`) and passed them into prereq checks before bootstrap decisions. |
| 2 | edge-case | high | DAST-capable profiles with no `--zap-target` were treated as `skipped`, allowing false `PASS` decisions in strict mode. | Updated scanner planning/execution so DAST-capable profile + missing target marks ZAP `unavailable`, yielding `INCONCLUSIVE` unless degraded pass is explicitly allowed. |
| 3 | workflow | medium | `docs/security-review/` runtime outputs created persistent untracked noise in git status. | Added `docs/security-review/.gitignore` to keep generated intermediate outputs out of commits by default while preserving discoverable location. |
| 4 | workflow | medium | Bootstrap helper output is plain text, but orchestration expected JSON and recorded bootstrap as an error even on successful print-only guidance. | Added non-JSON command handling for bootstrap execution so successful print-only guidance records status `ok` in report metadata. |

### Quality Checks

- `pytest`: fail (`No module named pytest` in this environment)
- `mypy`: fail (`mypy` command not installed in this environment)
- `ruff`: fail (`ruff` command not installed in this environment)
- `openspec validate add-security-review-skill --strict`: pass
- Targeted behavior check: `python3 skills/security-review/scripts/main.py --repo . --change add-security-review-skill --profile-override docker-api --dry-run` returns `INCONCLUSIVE` (exit code `11`) with ZAP marked `unavailable` when target is missing.

### Spec Drift

- Updated `openspec/changes/add-security-review-skill/specs/skill-workflow/spec.md` with a scenario for DAST-profile detection without `--zap-target`, matching implemented `INCONCLUSIVE` behavior.

---

## Iteration 2

<!-- Date: 2026-02-20 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | bug | high | `run_dependency_check.sh` only fell back to Docker when the native binary was absent, not when native execution existed but failed. | Added native-failure Docker fallback path with explicit `docker-fallback` mode and failure provenance in messages. |
| 2 | edge-case | medium | Dry-run scan adapters only generated stub reports when report files were missing, so stale JSON from previous runs could be reused silently. | Updated dry-run behavior to always overwrite `dependency-check-report.json` and `zap-report.json` with deterministic dry-run payloads. |
| 3 | workflow | medium | Orchestrator dry-runs with `--change` could overwrite `openspec/changes/<id>/security-review-report.md`, creating review artifact churn from non-authoritative runs. | Skip change-artifact overwrite during `--dry-run` and emit explicit summary marker `change_artifact: skipped (dry-run)`. |

### Quality Checks

- `pytest`: fail (`No module named pytest` in this environment)
- `mypy`: fail (`mypy` command not installed in this environment)
- `ruff`: fail (`ruff` command not installed in this environment)
- `openspec validate add-security-review-skill --strict`: pass
- `python3 -m py_compile skills/security-review/scripts/*.py`: pass
- Targeted adapter check: simulated native dependency-check failure with Docker fallback returns `mode=docker-fallback` and status `ok`.
- Targeted behavior check: `python3 skills/security-review/scripts/main.py --repo . --change add-security-review-skill --profile-override docker-api --dry-run` returns `INCONCLUSIVE` (exit code `11`) and leaves OpenSpec artifact untouched in dry-run mode.

### Spec Drift

- Updated `openspec/changes/add-security-review-skill/specs/skill-workflow/spec.md` with a scenario for native dependency-check failure and Docker fallback behavior.

---

## Summary

- Total iterations: 2
- Total findings addressed: 7
- Remaining findings (below threshold): none
- Termination reason: threshold met
