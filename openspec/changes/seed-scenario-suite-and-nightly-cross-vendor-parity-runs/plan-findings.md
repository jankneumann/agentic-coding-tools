# Plan Findings: seed-scenario-suite-and-nightly-cross-vendor-parity-runs

Produced by `/iterate-on-plan` (autopilot PLAN_ITERATE, threshold `medium`). Code
claims were verified against `packages/agent-scenarios/` (ri-15), `skills/improve-harness/scripts/analyze_failures.py`,
`skills/coordination-bridge/scripts/coordination_bridge.py` and the merge-family SKILL.md files.

## Iteration 1

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 1 | feasibility | high | Merge-family skills (`merge-pull-requests`, `cleanup-feature`) require an authenticated `gh` and GitHub PRs; with tokens scrubbed and a bare local origin they would stop at `gh auth status` every night — a permanent false capability gap, not a skill signal. | D5: `gh` shim on every live run's `PATH`, backed by the local origin and fixture `prs:`; unsupported calls force `error`. Tasks 1.6/1.7; spec scenarios; A12. |
| 2 | feasibility | high | Copying only `skills_root/<skill_under_test>/` breaks skills that call siblings via `<skill-base-dir>/../worktree/…`, `../shared/…`, `../session-log/…`. | D5: copy the whole skills tree (minus tests/.venv/caches); `support_skills` dropped; A13. |
| 3 | security | high | Vendor subprocesses inherited the runner's `COORDINATION_API_KEY`, and `coordination_bridge.py` falls back to `localhost:3000` (the live coordinator on the GX10), so fixture agents could take locks / write memories in production. | D5 hermetic env: scrub coordinator + GitHub credentials, always scrub `gaps.api_key_env`, `env_set` `COORDINATION_API_URL=http://127.0.0.1:9`; spec scenario; A14. |
| 4 | consistency | high | Task 7.2 runs `--dry-run` with `enabled: false`, but guard 1 exited as `disabled` first and the spec required an enabled config. | D4/spec: dry-run evaluates guards without acting, works while disabled, writes nothing. |
| 5 | assumptions | high | An all-`error` night (CLIs missing, keys expired) exited 0 — indistinguishable from green to systemd. Exit precedence with `budget_exhausted` was also ambiguous. | D4: exit precedence 2 > 1 > 3 > 0; new exit 3; spec scenarios; A15. |
| 6 | consistency | medium | D4 said every guard writes a matching run record, but the `<2 vendors` guard had no status, invalid config cannot know the store path, and the vendor check came after the cap check. | Guard 0 (invalid config, no record), vendor check before caps, `config_error` status in schema and spec. |
| 7 | consistency | medium | Plan assumed `VendorRunVerdict` has `trajectory_status`/duration; it has neither. | D2 field mapping; runner measures duration. |
| 8 | completeness | medium | Results appended only at run end: a systemd timeout/kill loses the whole night. | D2 incremental append; interrupted-run marking; spec scenario. |
| 9 | completeness | medium | Executor reports timeout and missing CLI identically (exit 127, same message). | D5 distinct timeout message; spec scenario; task 1.2/1.3. |
| 10 | performance | medium | Workspaces (+ bare origins) accumulated without bound nightly. | D4 retention: delete pass workspaces, keep fail/error for `retain_failed_runs` (7). |
| 11 | completeness | medium | `gaps flush` concurrent with a nightly could drop/duplicate spool entries. | D4 spool flock + atomic replace; spec scenario. |
| 12 | consistency | medium | Gap emitter used `COORDINATOR_URL`; repo convention is `COORDINATION_API_URL`; an unset URL would silently target a default host. | D3: configurable env names, default `COORDINATION_API_URL`, unset → spool only; runbook covers the `analyze_failures.py` `COORDINATOR_URL` mismatch. |
| 13 | clarity | medium | Gap key's "first failed gate" order unspecified; cross-vendor dedup in one run unexplained. | D3: declaration order; dedup documented as intended. |
| 14 | clarity | low | systemd `TimeoutStartSec` "cap + margin" could kill the last pair. | D7: ≥ wall clock + per-pair timeout + 10 min; deploy-asset test. |
| 15 | clarity | low | Design suggested vendoring `openspec_paths.py`; none exists and tests read package copies only. | Testing strategy clarified. |
| 16 | clarity | low | `__main__.py` docstring advertises unimplemented `--target`/`--out`. | Task 5.5. |

## Iteration 2

No findings at or above `medium`. Remaining low findings (deferred, optional):

- Example payload is duplicated in package data and `skills/tests/improve-harness/fixtures/`; drift is caught only by each side's own schema/shape assertions.
- The 15k-record `< 2 s` performance test may be sensitive to CI hardware; mark it with a generous margin.
- `gh` shim fidelity vs real GitHub (accepted risk in design.md).

Parallelizability: wp-foundation → {wp-scenarios, wp-results, wp-gaps} (width 3, disjoint `write_allow`) → wp-nightly → wp-integration. File overlap: none between parallel packages; `__main__.py` owned solely by wp-nightly; `executor.py`/`models.py` solely by wp-foundation.
