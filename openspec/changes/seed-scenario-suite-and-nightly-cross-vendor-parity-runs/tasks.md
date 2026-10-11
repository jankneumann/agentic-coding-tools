# Tasks: seed-scenario-suite-and-nightly-cross-vendor-parity-runs

Spec scenario references use `<capability>.<requirement>/<scenario>` shorthand:
`ath` = `agent-trajectory-harness`, `he` = `harness-engineering`.
Design decisions are `D1`–`D8` in `design.md`. All tests use `FakeExecutor` or test
doubles — no vendor CLI, no network, no `systemctl`, no database.

## 1. Foundation — schemas and harness extensions (wp-foundation)

- [x] 1.1 Promote contract schemas into package data (with schema tests) [S]
  Copy `contracts/schemas/*.json` into `packages/agent-scenarios/src/agent_scenarios/schemas/`
  (package data); write `tests/test_schemas.py` asserting each is a valid Draft 2020-12
  schema and that the capability-gap example payload validates. Also copy the example
  payload into package data. `jsonschema` is already in the dev group; do not make it a
  runtime dependency.
  **Contracts**: contracts/schemas/results-record.schema.json, capability-gap-entry.schema.json, nightly-config.schema.json
  **Dependencies**: None
- [x] 1.2 Write tests for fixture `local_remote`/`prs`, hermetic env and timeout message [S]
  Built-in `HERMETIC_SCRUB` denylist applied with an empty `env_scrub` (GitHub tokens, every coordination-bridge URL/API-key/CF Access variable); `env_scrub` extends it; `gaps.api_key_env` / `gaps.coordinator_url_env` variables always scrubbed; `COORDINATION_API_URL` forced to the sentinel after `env_set`; drift test `HERMETIC_SCRUB` ⊇ `coordination_bridge` `_HTTP_URL_ENV_KEYS` ∪ `_API_KEY_ENV_KEYS` ∪ CF names (skip when the skills tree is absent); drift test config-schema `env_set.propertyNames` enum == `HERMETIC_SCRUB ∪ {COORDINATION_API_URL}`; `TimeoutExpired` → "timed out after Ns" distinct from "unavailable".
  **Spec scenarios**: ath.Live runs never reach real GitHub/local remote fixture; ath.Live runs never reach real GitHub/credential variables are scrubbed; ath.Live runs never reach real GitHub/the runner's coordinator credential never reaches an agent; ath.Live runs never reach real GitHub/the denylist covers every coordinator variable the skills read; ath.Skill under test is materialized/a timeout is distinguishable from a missing CLI
  **Design decisions**: D5
  **Dependencies**: None
- [x] 1.3 Implement `FixtureSpec.local_remote` + `FixtureSpec.prs` + `HERMETIC_SCRUB` + `CLIVendorExecutor(env_scrub=..., env_set=..., always_scrub=...)` (sentinel forced last) + timeout message [M]
  Sibling bare repo `<workdir>.origin.git`, `origin` remote, base branch and PR head branches pushed; backward-compatible defaults (no env change when both are empty).
  **Dependencies**: 1.2
- [x] 1.4 Write tests for skill-under-test materialization [S]
  Whole-tree copy (siblings present; `tests/`, `.venv/`, `__pycache__/`, `node_modules/` excluded), git-exclude, `skills_sha` with `+dirty` carried onto the result.
  **Spec scenarios**: ath.Skill under test is materialized/skill copied into the workspace; ath.Skill under test is materialized/missing skill is an executor error
  **Design decisions**: D5
  **Dependencies**: None
- [x] 1.5 Implement whole-tree `skills_root` materialization in `materialize.py` with git-exclude and `skills_sha` capture [M]
  Shared helper usable by both `CLIVendorExecutor` and `FakeExecutor` (opt-in) so the acceptance drill can exercise it.
  **Dependencies**: 1.4
- [x] 1.6 Write tests for the `gh` shim `tests/test_gh_shim.py` [S]
  Subprocess-level against a temp local origin: `auth status`, `repo view`, `pr list|view|status --json`, `pr create`, `pr merge --merge|--squash|--rebase [--delete-branch]` (merge visible on origin, state `MERGED`), `api repos/{o}/{r}` permissions + protection 404, unsupported call → exit 1 + logged → executor forces `error`; executor's post-run `gh pr view` resolves through the shim.
  **Spec scenarios**: ath.Live runs never reach real GitHub/gh resolves to the shim; ath.Live runs never reach real GitHub/an unsupported gh call is an infrastructure error
  **Design decisions**: D5
  **Dependencies**: None
- [x] 1.7 Implement `gh_shim.py` (stdlib-only script body + installer writing `<workdir>.bin/gh`, PATH prepend in `CLIVendorExecutor`, unsupported-log check forcing `error`) [M]
  **Dependencies**: 1.6, 1.3
- [x] Checkpoint: run `uv run pytest` in packages/agent-scenarios, review diff, verify scope

## 2. Seed suite (wp-scenarios)

- [x] 2.1 Write suite guard test `tests/test_seed_suite.py` [S]
  Floor (≥10, ≥2 per family, ≥2 vendors, unique ids), every `task_prompt` contains `/<skill_under_test>`, outcome-module presence, `pr`-gate-requires-`local_remote` rule, plus negative cases against temp suite dirs.
  **Spec scenarios**: ath.Seed scenario suite coverage floor/the shipped suite meets the coverage floor; ath.Seed scenario suite coverage floor/removing scenarios below the floor fails the guard; ath.Seed scenario suite coverage floor/a seed prompt that does not invoke its skill fails the guard; ath.Seed scenarios are self-tested/a seed scenario without outcomes is rejected; ath.Live runs never reach real GitHub/PR gates require a local remote
  **Design decisions**: D6
  **Dependencies**: None
- [x] 2.2 Add `suite.py` with `SKILL_FAMILIES` and `skill_family()` [XS]
  **Dependencies**: 2.1
- [x] 2.3 Write parametrized golden/broken self-test `tests/test_seed_outcomes.py` [S]
  **Spec scenarios**: ath.Seed scenarios are self-tested/golden outcome passes every gate; ath.Seed scenarios are self-tested/broken outcome fails a named gate
  **Design decisions**: D6
  **Dependencies**: None
- [x] 2.4 Revise `implement-feature-basic` to gate on a push to the local origin [S]
  Replace the GitHub `pr` gate; set `local_remote: true`; prefix `task_prompt` with `/implement-feature`; add its outcomes module.
  **Dependencies**: 1.3, 2.3
- [x] 2.5 Add outcomes module for `plan-feature-basic` and prefix its `task_prompt` with `/plan-feature` [XS]
  **Dependencies**: 2.3
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 2.6 Author plan scenarios `plan-feature-spec-delta` + `iterate-on-plan-split-fused-task` with outcome modules [M]
  **Dependencies**: 2.3
- [x] 2.7 Author implement scenarios `implement-feature-tdd-new-function` + `implement-feature-respects-scope` with outcome modules [M]
  **Dependencies**: 2.3
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 2.8 Author validate scenarios `validate-feature-flags-failing-test`, `validate-feature-clean-pass`, `validate-feature-spec-gap` with outcome modules [M]
  **Dependencies**: 2.3
- [x] 2.9 Author merge scenarios `merge-pull-requests-local-merge` + `cleanup-feature-archive` (`local_remote: true`, seeded `prs:`) with outcome modules [M]
  Golden outcomes perform the merge through the shim's state (or equivalent git ops on the local origin) so gates are proven satisfiable.
  **Dependencies**: 1.3, 1.7, 2.3
- [x] Checkpoint: guard test green with 11 scenarios; review diff, verify scope

## 3. Results store and query CLI (wp-results)

- [x] 3.1 Write tests for `ResultsStore` append/read [S]
  Record shape vs schema (field mapping from ri-15 `VendorRunVerdict` per D2; all D2 fields present, nullable as explicit null; schema rejects `fail` without failed gates, `pass`/`skipped_budget` with failed gates, `error` without a message), flock-protected append, torn final line and unknown `schema_version` skipped with warning, `result` records without a `run` record flagged as interrupted — or in progress while the run lock is held.
  **Spec scenarios**: ath.Durable per-vendor per-skill results store/results are appended per scenario and vendor; ath.Durable results store/reader tolerates a torn final line and unknown versions; ath.Durable results store/results survive an interrupted run; ath.Durable results store/a run in progress is not reported as interrupted
  **Contracts**: contracts/schemas/results-record.schema.json
  **Design decisions**: D2
  **Dependencies**: 1.1
- [x] 3.2 Implement `results_store.py` (`ResultsStore` protocol, `JsonlResultsStore`, `records_from_matrices`) [M]
  `records_from_matrices` takes an injected `family_of(skill) -> str` callable (wired to `suite.skill_family` by the nightly runner), so this package does not depend on wp-scenarios.
  **Dependencies**: 3.1
- [x] 3.3 Write tests for `results query` filters + `results latest` [S]
  **Spec scenarios**: ath.Durable results store/query by vendor and skill over a time window; ath.Durable results store/query by skill family and scenario; ath.Durable results store/latest result per scenario and vendor
  **Dependencies**: 3.2
- [x] 3.4 Write tests for `results trend` bucketing/pass-rate denominator, plus a 15k-record performance test (< 2 s) [S]
  **Spec scenarios**: ath.Durable results store/trend aggregates pass rate per bucket
  **Dependencies**: 3.2
- [x] 3.5 Implement `results_cli.py` (`add_parser(subparsers)`, `query`, `trend`, `latest`; json and table output) [M]
  **Dependencies**: 3.3, 3.4
- [x] Checkpoint: run tests, review diff, verify scope

## 4. Capability-gap emission (wp-gaps)

- [x] 4.1 Write tests for gap entry construction [S]
  Fail → one entry with the D3 tag set, `session_id = run_id` and `details.run_id = run_id`; gap key uses the first failed gate in declaration order; `detail` truncated to 500 chars; error / skipped_budget / judge-only → none; payload validates against the schema and matches the example's tag shape.
  **Spec scenarios**: ath.Scenario failures feed the capability-gap pipeline/a failing gate produces a tagged gap entry; ath.Scenario failures feed the capability-gap pipeline/errors and judge findings do not emit gaps
  **Contracts**: contracts/schemas/capability-gap-entry.schema.json, contracts/examples/capability-gap-entry.example.json
  **Design decisions**: D3
  **Dependencies**: 1.1
- [x] 4.2 Write tests for sinks: coordinator sink against a local `http.server` stub (headers, body, URL from `gaps.coordinator_url_env`), only 2xx + `success: true` acknowledges (200 + `success: false`, non-JSON, 5xx → spooled on emit, kept on flush), unset URL variable → spool with no HTTP request, spool on unreachable port, flush retains still-failing entries, concurrent flush + emit under the spool lock loses/duplicates nothing [S]
  **Spec scenarios**: ath.Scenario failures feed the capability-gap pipeline/coordinator unreachable spools entries; ath.Scenario failures feed the capability-gap pipeline/an application-level rejection is not a delivery; ath.Scenario failures feed the capability-gap pipeline/spool replay; ath.Scenario failures feed the capability-gap pipeline/no coordinator URL configured spools instead of guessing; ath.Scenario failures feed the capability-gap pipeline/concurrent flush and emission lose nothing
  **Dependencies**: 1.1
- [x] 4.3 Implement `gap_emitter.py` (`build_gap_entries`, `MemorySink`, `CoordinatorMemorySink`, `SpoolMemorySink`, `emit_gaps`, `flush_spool`, `add_parser` for `gaps flush`) [M]
  **Dependencies**: 4.1, 4.2
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 4.4 Write improve-harness consumer test `skills/tests/improve-harness/test_scenario_parity_source.py` [S]
  Copies the example payload to `skills/tests/improve-harness/fixtures/`. (a) Drives `analyze_failures.query_memory` against a local `http.server` stub that enforces the real `MemoryQueryRequest` shape (`agent_id` required, `Authorization: Bearer` checked when configured) and answers with the real `memories` list envelope; asserts the entries come back and that entries older than the window are dropped by `created_at`. (b) Feeds the payload (two vendors in one run, plus a later run's copy) through `normalize_memory_entries`/`rank_findings`; asserts `scenario-parity` in sources and frequency 3.
  **Spec scenarios**: he.Scenario-parity capability-gap source/improve-harness attributes scenario-parity findings; he.Scenario-parity capability-gap source/frequency counts failing run-and-vendor pairs; he.Scenario-parity capability-gap source/scenario-parity entries are retrievable by the improve-harness memory query; he.Scenario-parity capability-gap source/the improve-harness memory query matches the coordinator API
  **Contracts**: contracts/examples/capability-gap-entry.example.json
  **Dependencies**: None
- [x] 4.4a Repair (signatures unchanged — `skills/skill-audit/scripts/evidence_join.py` and `export_shared_learnings.py` call them) `analyze_failures.query_memory` / `build_memory_query` in `skills/improve-harness/scripts/analyze_failures.py` [S]
  Send `agent_id` (default `improve-harness`, `--agent-id` / `IMPROVE_HARNESS_AGENT_ID` override) and `Authorization: Bearer` from `COORDINATION_API_KEY` when set; drop the unsupported `time_window_days` request field and filter by `created_at` client-side; read the `memories` envelope (keep `entries` / bare list for older coordinators). Ranking semantics unchanged (D3: frequency unit is (run, vendor)). Update the skill's existing tests that pin the old payload.
  **Design decisions**: D3
  **Dependencies**: 4.4
- [x] 4.5 Add `scenario-parity` to `SOURCE_VOCABULARY` in `skills/session-log/tests/test_memory_tag_conventions.py` [XS]
  **Spec scenarios**: he.Scenario-parity capability-gap source/source value is documented and pinned
  **Dependencies**: None
- [x] 4.6 Document `source:scenario-parity`, `vendor:`, `scenario:` in `docs/guides/memory-conventions.md` [XS]
  **Dependencies**: 4.5
- [x] 4.7 Add the scenario-parity row to the data-sources table in `skills/improve-harness/SKILL.md` (noting the (run, vendor) frequency unit); sync runtime copies via `install.sh` [XS]
  **Dependencies**: 4.4, 4.4a
- [x] Checkpoint: run skills gate set (touched skill tests, `install.sh --check`), review diff, verify scope

## 5. Nightly runner, CLI and deploy templates (wp-nightly)

- [x] 5.1 Write tests for nightly config loading and guards [M]
  Guard order per D4: invalid config / missing `vendor_commands` entry / `env_set` naming a denylisted variable, `COORDINATION_API_URL`, an `env_scrub` entry or a `gaps.*_env` name → exit 2, no record; config omitting `caps` / `enabled` / `disable_file` takes the documented defaults; `enabled: false` (executor factory never called); kill-file; run lock; < 2 effective vendors → `config_error` record + exit 2; over-cap (`max_pairs` and per-vendor) → `cap_exceeded` + exit 2 with nothing launched; `--dry-run` with `enabled: false` and with `enabled: true` (no lock, no record, no executor).
  **Spec scenarios**: ath.Live runs never reach real GitHub/config cannot re-open the live coordinator path; ath.Nightly runner/disabled by default; ath.Nightly runner/kill-file disables an enabled config; ath.Nightly runner/over-cap plan refuses to start; ath.Nightly runner/fewer than two effective vendors is a config error; ath.Nightly runner/invalid config writes nothing; ath.Nightly runner/overlapping runs are refused; ath.Nightly runner/dry run plans without executing
  **Contracts**: contracts/schemas/nightly-config.schema.json
  **Design decisions**: D4
  **Dependencies**: 1.1
- [x] 5.2 Write tests for the run loop with an injected fake clock [M]
  Wall-clock budget → `skipped_budget` + `budget_exhausted` (deterministic pair order); results appended incrementally (simulated kill after N pairs leaves N records, no `run` record); findings/gaps written; exit-code precedence 2 > 1 > 3 > 0 (fail + budget_exhausted → 1; errors only → 3; budget_exhausted with all executed pairs passing → 3; completed and all pass → 0); spool flushed first; pass workspaces deleted, fail/error kept, old run dirs pruned beyond `retain_failed_runs`; `duration_seconds` measured per pair.
  **Spec scenarios**: ath.Nightly runner/wall-clock budget stops launching new pairs; ath.Nightly runner/failing scenarios make the run exit non-zero; ath.Nightly runner/an infrastructure-only failure is not a green night; ath.Nightly runner/workspaces are bounded; ath.Durable results store/results are appended per scenario and vendor; ath.Durable results store/results survive an interrupted run
  **Design decisions**: D4
  **Dependencies**: 1.1
- [x] 5.3 Implement `nightly.py` (config model, guards, pair planning, run loop with budget, wiring of results store, findings emitter, gap emitter, executor factory with `skills_root`/`env_scrub`/timeout) [L]
  Kept L rather than split: guards and loop share the run-record lifecycle; tests 5.1/5.2 bound it. Flagged per sizing rules.
  **Dependencies**: 5.1, 5.2, 3.2, 4.3, 1.5
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 5.4 Write tests for the `__main__` subcommand dispatcher (legacy `--scenarios`/`--validate-only` form unchanged; `validate`, `nightly`, `results`, `gaps` routed) [S]
  **Design decisions**: D8
  **Dependencies**: None
- [x] 5.5 Rewrite `__main__.py` as a subcommand dispatcher (drop the stale `--target`/`--out` docstring) [S]
  **Dependencies**: 5.4, 3.5, 4.3, 5.3
- [x] 5.6 Write tests for deploy assets (placeholders present, `TimeoutStartSec` ≥ wall-clock cap + per-pair timeout of the example config, example config parses with `enabled: false`, no `systemctl` invocation anywhere in package code/tests) [XS]
  **Spec scenarios**: ath.Schedule shipped as templates only/templates and example config are inert
  **Design decisions**: D7
  **Dependencies**: None
- [x] 5.7 Add `deploy/systemd/*.template` + `deploy/nightly.example.yaml` [S]
  **Dependencies**: 5.6
- [x] 5.8 Write runbook `docs/guides/agent-scenarios-nightly.md` (+ package README update) [S]
  Must cover: exit codes 0/1/2/3 and triage (3 = errors or an incomplete, budget-exhausted matrix), capability-gap frequency unit (run, vendor), `COORDINATION_API_URL` vs `COORDINATOR_URL` (gap emitter vs `/improve-harness`) pointing at the same coordinator, dedicated HOME without global skills or coordinator MCP config, workspace retention, `gh` shim unsupported-call errors.
  **Dependencies**: 5.7
- [x] Checkpoint: run tests, review diff, verify scope

## 6. Integration and acceptance (wp-integration)

- [x] 6.1 Write broken-skill acceptance test `tests/test_acceptance_broken_skill.py` [M]
  Temp `skills_root` with a skill; a test executor that reads the materialized SKILL.md and plays the scenario's golden outcome, or its broken outcome when the skill carries the break marker; run `nightly` (enabled, temp state dir, stub coordinator) → `fail` result in store, gap entry with `affected_skill` and `source:scenario-parity`, findings file; then the same with the intact skill → pass, no gap.
  **Spec scenarios**: ath.Scenario failures feed the capability-gap pipeline/a deliberately broken skill change produces a capability gap
  **Design decisions**: D3, D5
  **Dependencies**: 5.3, 2.9, 1.7
- [x] 6.2 Write 2-vendor nightly acceptance test over the full seed suite with golden outcomes (22 result records + 1 run record; `results trend` per vendor × skill returns 100% pass) [S]
  **Spec scenarios**: ath.Durable results store/results are appended per scenario and vendor; ath.Durable results store/trend aggregates pass rate per bucket
  **Dependencies**: 5.5, 2.9
- [x] 6.4 Record the archive-order constraints in the PR description and session log [XS]
  Archive `build-agent-trajectory-scenario-harness` (ri-15) before this change, so ri-15 creates `openspec/specs/agent-trajectory-harness/spec.md` and this change's ADDED requirements merge into it; and whichever of this change and `add-a-judged-first-stage-to-coordinator-audit-triage` archives second adds `scenario-parity` to the "Capability Gap Detection" `source` enum (design D3 base-spec enum).
  **Dependencies**: None
- [x] 6.3 Run full quality gates: package `uv run pytest`, `ruff`, `mypy --strict`; skills gate set; `openspec validate seed-scenario-suite-and-nightly-cross-vendor-parity-runs --strict` [S]
  **Dependencies**: 6.1, 6.2, 4.7, 5.8

## 7. Operator tasks (post-merge)

These require the GX10 host, real vendor CLIs/keys, and human authorization. They are
NOT part of implementation and remain unchecked when the change merges.

- [ ] 7.1 Create a dedicated nightly user/HOME on the GX10 without user-global skills, without coordinator MCP config and without GitHub push credentials (SSH keys, credential helpers, `insteadOf` rewrites); install `claude` and `codex` CLIs and keys for it
- [ ] 7.2 Copy `deploy/nightly.example.yaml` to `~/.config/agent-scenarios/nightly.yaml`, fill `vendor_commands`/paths, keep `enabled: false`, run `agent-scenarios nightly --dry-run` and review the planned pairs and caps
- [ ] 7.3 Render and install the systemd user service/timer from the templates (`systemctl --user daemon-reload`), still with `enabled: false`
- [ ] 7.4 Flip `enabled: true`, run the service once manually, review results/findings/gaps, then `systemctl --user enable --now agent-scenarios-nightly.timer`
- [ ] 7.5 Live broken-skill drill: on a throwaway branch break one plan/validate skill, point a one-off config's `repo_root` at it, run once, confirm a `fail` result and a `source:scenario-parity` gap surfaces in `/improve-harness`; restore
- [ ] 7.6 After one week of nightly runs, confirm `results trend --group-by vendor,skill` shows ≥ 2 vendors × 4 families and record the baseline in the roadmap learning log
