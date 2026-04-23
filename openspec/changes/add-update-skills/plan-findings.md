# Plan Findings — add-update-skills

## Iteration 1 (2026-04-23)

Threshold: medium. Max iterations: 3.

| # | Type | Criticality | Description | Disposition |
|---|------|-------------|-------------|-------------|
| 1 | assumptions | high | Pre-commit install mechanism — `uv pip install` ad-hoc vs. dev-dep in `skills/pyproject.toml` via `uv sync`. Two valid paths; CLAUDE.md conventions favor the latter. | **User decision: dev-dep via uv sync.** Applied to proposal.md, tasks.md (2.3), and new spec requirement. |
| 2 | assumptions / consistency | high | Codex SessionStart wiring — proposal.md said "Codex equivalent" but task 4.3 only named `.claude/settings.json`. Inconsistency between documents. | **User decision: wire both.** Applied to proposal.md (What Changes + Affected Code), tasks.md (4.3), and new spec scenario. |
| 3 | completeness | high | Missing spec requirement for `install-hooks.sh` behavior — idempotency, first-run install, missing `uv` failure mode. | Fixed: added new "Install-hooks bootstrap is idempotent" requirement with 3 scenarios. |
| 4 | completeness | high | Missing scenarios for orchestrator partial-failure cases — install.sh fails, sync_agents_md.py fails mid-orchestration. | Fixed: added "Orchestrator aborts on sync-script failure" and "Orchestrator aborts on install.sh failure" scenarios. |
| 5 | testability | medium | "Pre-commit hook exit 0 silently" scenario conflated the underlying script (must be silent) with the pre-commit framework (always prints hook id/status). | Fixed: rephrased scenario to bind the "silent" assertion to `sync_agents_md.py --check` only and explicitly allow framework output. |
| 6 | testability | medium | "Push retry exhausted" didn't specify output channel or format. | Fixed: specified stderr human-readable summary + stdout single-line `UNPUSHED_COMMIT=<sha>` for automation. |
| 7 | clarity | medium | Push-retry backoff timing was ambiguous (is 1s before or after attempt 1?). | Fixed: spelled out "attempt 1 with no preceding wait; on rejection wait 1s then attempt 2; on rejection wait 2s then attempt 3". |
| 8 | security | low | `git push` scenario didn't specify explicit remote `origin`. | Fixed (raised to MEDIUM since explicit remote aligns with M6 scenario rewrite): scenario now says "git push origin <current-branch>". |

## Residual findings (below threshold)

None. All medium-and-above findings addressed in this iteration.

## Parallelizability assessment

- **Independent tasks**: Phase 4 (auto-pull hook) is independent of Phases 1-3. Phase 5 (docs + initial generation) depends on all prior phases. Phase 6 (verification) depends on everything.
- **Sequential chains**: Phase 1 → Phase 2 → Phase 3 → Phase 5/6 is a single chain. Phase 4 runs in parallel with Phase 3.
- **Max parallel width**: 2 (Phase 3 + Phase 4 concurrently).
- **File-overlap conflicts**: none — Phase 3 writes under `skills/update-skills/`, Phase 4 writes `skills/session-bootstrap/scripts/hooks/auto_pull.py` + two wiring points in different files. No overlap.

Note: this change is declared sequential-tier (single `wp-main` package), so the parallelism opportunity is advisory only. The assessment is recorded for possible future tier upgrade.
