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

## Summary

- Total iterations: 1
- Total findings addressed: 4
- Remaining findings (below threshold): none
- Termination reason: threshold met
