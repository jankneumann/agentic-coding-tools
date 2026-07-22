# Tasks — add-agy-grok-pi-harnesses

Implements Approach A (config-driven via the generic `CliVendorAdapter`) per proposal Gate 1.
Canonical provider key is `antigravity` (D3); `agy` appears only as `cli.command`.

**Measured scope** (corrected in PLAN_REVIEW round 1): **133** tracked files reference gemini.
Of those, **69** are code/config and **11** are user-facing docs/templates/Makefile — together
the 78-path in-scope set in `scripts/in-scope.txt`. The remaining 44 narrative-prose files are
deferred to a follow-up (design D6), and a further set is carved out as historical record
(design § Carve-outs) — applied SQL migrations and review-provenance annotations MUST NOT be
edited.

The proposal's original enumeration listed ~15 sites; an earlier inventory claimed 68 and was
wrong (it used `grep -r` under a `.gitignore`-aware shell wrapper). Authoritative gate:
`scripts/check_roster_residue.py`.

Task sizes follow the plan-feature sizing table. No task is XL. One task is L (4.1) and is
flagged; its decomposition rationale is in `design.md`.

---

## Phase 1 — Contracts and roster definition

- [ ] 1.1 Write `contracts/roster.md` naming the five canonical provider keys and the one
  string per vendor rule (S)
  **Spec scenarios**: configuration.1 (provider map includes all first-class providers),
  agent-archetypes.1 (archetype resolves for antigravity/grok/pi)
  **Design decisions**: D3 (single canonical key)
  **Dependencies**: None

- [ ] 1.2 Update `contracts/provider-model-map.schema.json` to accept the five roster keys and
  reject `gemini` (S)
  **Spec scenarios**: configuration.1, configuration.2 (pi maps to OpenRouter slugs)
  **Dependencies**: 1.1

- [ ] 1.3 Checkpoint: run `openspec validate add-agy-grok-pi-harnesses --strict`, review diff,
  verify scope

## Phase 2 — Empirical CLI verification (resolves proposal open decisions 2 and 3)

These tasks produce facts that Phases 3-7 depend on. They are deliberately first: guessing
CLI flags is the failure mode this phase exists to prevent.

- [ ] 2.1 Record `agy models` output and resolve the exact `--model` slug strings for the
  antigravity premium/standard/economy tiers (S)
  **Dependencies**: None
  **Output**: `design.md` § Empirical CLI findings

- [ ] 2.2 Verify `grok --prompt-file /dev/stdin` delivers a prompt correctly under a
  subprocess pipe (S)
  **Spec scenarios**: skill-workflow.15 (prompt delivered via stdin when configured)
  **Dependencies**: None
  **On failure**: apply Approach B narrowly to grok only; record the decision in `design.md`

- [ ] 2.3 Verify `pi --provider openrouter` resolves `OPENROUTER_API_KEY` from the subprocess
  environment (S)
  **Spec scenarios**: configuration.2
  **Dependencies**: None

- [ ] 2.4 Record the re-login command for `agy` and `pi`, or confirm the
  `<command> login` fallback is correct (XS)
  **Spec scenarios**: skill-workflow.18 (vendor without a confirmed re-login command)
  **Dependencies**: None
  **Note**: `grok login` is already confirmed ("Sign in to Grok")

- [ ] 2.5 Checkpoint: fold facts E1-E4 into `design.md` § Empirical CLI findings with evidence

- [ ] 2.6 Record `grok` model slug strings for premium/standard/economy (fact E5) (S)
  **Consumed by**: 3.5, 3.8
  **Dependencies**: None
  **Note**: added in PLAN_FIX (finding C4). `contracts/roster.md` previously claimed task 2.2
  resolved these; 2.2 only verifies stdin delivery.

- [ ] 2.7 Verify `grok --output-format json` with `--json-schema` pointed at
  `review-findings.schema.json` emits a conforming envelope (fact E6) (S)
  **Consumed by**: 5.2, 3.2
  **Dependencies**: None
  **On failure**: grok's eval backend and review dispatch fall back to text parsing; record in
  `design.md` and re-scope task 5.2

- [ ] 2.8 Verify `agy --print` + stdin + `--mode plan` behave Claude-shaped (fact E7) (S)
  **Consumed by**: 3.2, 5.3
  **Dependencies**: None

- [ ] 2.9 Verify `pi` accepts the prompt as a trailing positional and record its output shape
  (fact E8) (S)
  **Consumed by**: 3.2, 5.5
  **Dependencies**: None

- [ ] 2.10 Checkpoint: confirm all eight rows E1-E8 in `design.md` read `confirmed` or
  `refuted` with evidence; no row may remain `pending`

## Phase 3 — Registry and provider config

- [ ] 3.1 Write failing tests for the new roster in `agent-coordinator/tests/test_agents_config.py`
  and `test_agents_config_isolation.py` (M)
  **Spec scenarios**: configuration.1, configuration.2, agent-archetypes.1, agent-archetypes.2
  **Contracts**: `contracts/provider-model-map.schema.json`
  **Dependencies**: 1.2, 2.10

- [ ] 3.2 Add `antigravity-local`, `grok-local`, `pi-local` entries to `agents.yaml` with
  `cli.dispatch_modes` for review/alternative/quick (M)
  **Spec scenarios**: skill-workflow.15 (dispatch modes from config)
  **Dependencies**: 3.1

- [ ] 3.3 Remove `gemini-local` and `gemini-remote` from `agents.yaml` (S)
  **Spec scenarios**: configuration.1
  **Dependencies**: 3.1

- [ ] 3.4 Checkpoint: run `agent-coordinator/.venv/bin/python -m pytest tests/test_agents_config*.py`,
  review diff, verify scope

- [ ] 3.5 Add antigravity/grok/pi tier maps to `DEFAULT_PROVIDER_MODEL_MAP`
  (`src/agents_config.py`) (S)
  **Spec scenarios**: configuration.2
  **Dependencies**: 3.1, 2.1, 2.6

- [ ] 3.6 Remove the `gemini` entry from `DEFAULT_PROVIDER_MODEL_MAP` (XS)
  **Spec scenarios**: configuration.2
  **Dependencies**: 3.5
  **Note**: split from 3.5 deliberately — adding before removing keeps every intermediate
  commit dispatchable, which is the safe migration order

- [ ] 3.7 Checkpoint: run `test_agents_config.py`, review diff, verify scope

- [ ] 3.8 Add antigravity/grok/pi `model_aliases` to `archetypes.yaml` (S)
  **Spec scenarios**: agent-archetypes.1, agent-archetypes.2
  **Dependencies**: 3.1, 2.1, 2.6

- [ ] 3.9 Remove the gemini `model_aliases` from `archetypes.yaml` (XS)
  **Spec scenarios**: agent-archetypes.1
  **Dependencies**: 3.8

- [ ] 3.10 Update roster references in `src/coordination_api.py` (S)
  **Spec scenarios**: agent-coordinator.1 (runtime and transport matrix)
  **Dependencies**: 3.6

- [ ] 3.11 Checkpoint: run the coordinator config suite, review diff, verify scope

- [ ] 3.12 Update roster references in `scripts/setup_cloud.py` (S)
  **Spec scenarios**: agent-coordinator.1
  **Dependencies**: 3.6

- [ ] 3.13 Update `tests/test_differential_policy.py` fixtures to the new roster (S)
  **Dependencies**: 3.6, 3.9

- [ ] 3.14 Update `tests/model_routing/test_feedback.py` fixtures to the new roster (S)
  **Dependencies**: 3.6, 3.9

- [ ] 3.15 Checkpoint: run the full `agent-coordinator` suite, review diff, verify scope

- [ ] 3.16 Bump `DEFAULT_PROVIDER_MODEL_MAP["schema_version"]` and
  `_normalize_provider_model_map` to `2`, matching the contract (S)
  **Spec scenarios**: configuration.1
  **Dependencies**: 3.6
  **Note**: added in PLAN_FIX (finding U2). The contract declares `const: 2` while
  `agents_config.py:33` and `:1050` emit `1`; without this the contract and implementation
  ship in disagreement.

- [ ] 3.17 Checkpoint: run the coordinator suite, confirm schema_version 2 round-trips

## Phase 4 — Dispatch allow-lists

- [ ] 4.1 Write failing tests for the new roster across the dispatch test surface (L — flagged;
  see `design.md` § Why 4.1 stays L) (L)
  **Spec scenarios**: skill-workflow.4 (review dispatcher protocol), .5 (reviewer discovery
  fallback), .6 (vendor diversity), .20 (review convergence loop), .24 (manual provider smoke path)
  **Files**: `skills/tests/vendor-neutral-autopilot/*.py`,
  `skills/tests/parallel-infrastructure/*.py`, `skills/tests/autopilot*/*.py`,
  `skills/parallel-infrastructure/scripts/tests/*.py`, `skills/fix-scrub/tests/test_vendor_dispatch.py`,
  `skills/tests/prototype-feature/test_dispatch_variants.py`,
  `skills/tests/integration/test_prototype_convergence.py`,
  `skills/parallel-infrastructure/tests/test_vendor_diversity.py`,
  `skills/autopilot/scripts/tests/test_implementation_strategy_selector.py`
  **Dependencies**: 3.15

- [ ] 4.2 Update `_SUPPORTED_PROVIDERS` in `skills/autopilot/scripts/provider_dispatch.py` (S)
  **Spec scenarios**: skill-workflow.23 (lifecycle skills use provider-neutral terminology)
  **Dependencies**: 4.1

- [ ] 4.3 Update argparse `choices` in `token_budget_check.py` and `smoke_provider_dispatch.py` (S)
  **Spec scenarios**: skill-workflow.24
  **Dependencies**: 4.1

- [ ] 4.4 Checkpoint: run `skills/.venv/bin/python -m pytest skills/tests/vendor-neutral-autopilot/`,
  review diff, verify scope

- [ ] 4.5 Replace the hardcoded `available = ["claude", "codex", "gemini"]` list in
  `skills/autopilot-roadmap/scripts/orchestrator.py:319` (S)
  **Spec scenarios**: skill-workflow.6
  **Dependencies**: 4.1
  **Note**: `ri-02` later deletes this list entirely in favour of the vendor registry; this
  change keeps its structure so that deletion stays a clean removal

- [ ] 4.6 Update `_STATIC_COST_TIERS` in `skills/autopilot-roadmap/scripts/policy.py` (S)
  **Dependencies**: 4.1
  **Note**: `ri-02` replaces this stub with the real cost table; keep the shape stable

- [ ] 4.7 Update `_RELOGIN_COMMANDS` in `skills/parallel-infrastructure/scripts/review_dispatcher.py`
  and drop the Gemini `-o json` envelope-unwrap special case (M)
  **Spec scenarios**: skill-workflow.18 (auth error surfacing)
  **Dependencies**: 4.1, 2.4

- [ ] 4.8 Checkpoint: run the parallel-infrastructure suite, review diff, verify scope

- [ ] 4.9 Update roster references in `consensus_synthesizer.py`,
  `openspec/schemas/consensus-report.schema.json`, and the mirrored
  `skills/parallel-infrastructure/install_assets/` copy (S)
  **Spec scenarios**: skill-workflow.7 (consensus synthesizer)
  **Dependencies**: 4.1

- [ ] 4.10 Update roster references in `skills/quick-task/scripts/quick_task.py`,
  `skills/review-artifacts/scripts/open_artifacts.py`, `scripts/impl_review_driver.py`, and
  `scripts/impl_review_handoff.py` (S)
  **Dependencies**: 4.1

- [ ] 4.11 Checkpoint: run the full skills suite, review diff, verify scope

- [ ] 4.12 Repoint `skills/tests/vendor-neutral-autopilot/test_contracts.py:10` at
  `openspec/changes/archive/2026-05-16-vendor-neutral-autopilot` (S)
  **Dependencies**: 4.1
  **Note**: added in PLAN_FIX (finding U1, decision D7). The constant resolves a change
  directory archived months ago; `pytest skills/tests/vendor-neutral-autopilot` reports
  **5 failed** on this branch today, so wp-dispatch's gate is unpassable until this lands.

- [ ] 4.13 Update the `schema_version` fixture in `test_contracts.py` from 1 to 2 (XS)
  **Dependencies**: 4.12, 3.16

- [ ] 4.14 Checkpoint: confirm `pytest skills/tests/vendor-neutral-autopilot` is green

## Phase 5 — Eval backends (proposal decision D4)

- [ ] 5.1 Write failing tests for antigravity, grok, and pi `AgentBackend` implementations (M)
  **Spec scenarios**: evaluation-framework.1 (agent backend abstraction), and its
  antigravity/grok/pi scenarios
  **Dependencies**: 3.15

- [ ] 5.2 Implement the grok backend using `--output-format json` (M)
  **Spec scenarios**: evaluation-framework.1 (grok backend)
  **Dependencies**: 5.1, 2.2

- [ ] 5.3 Implement the antigravity backend (M)
  **Spec scenarios**: evaluation-framework.1 (antigravity backend)
  **Dependencies**: 5.1, 2.1

- [ ] 5.4 Checkpoint: run the evaluation suite, review diff, verify scope

- [ ] 5.5 Implement the pi backend (M)
  **Spec scenarios**: evaluation-framework.1 (pi backend)
  **Dependencies**: 5.1, 2.3

- [ ] 5.6 Delete `evaluation/backends/gemini_jules.py` and its `__all__` export (S)
  **Spec scenarios**: evaluation-framework.1 (retired Gemini/Jules backend is absent)
  **Dependencies**: 5.2, 5.3, 5.5

- [ ] 5.7 Update roster references in `evaluation/__init__.py`, `evaluation/config.py`, and
  `evaluation/backends/base.py` (S)
  **Dependencies**: 5.6

- [ ] 5.8 Checkpoint: run the evaluation suite, review diff, verify scope

## Phase 6 — Transcript adapters

- [ ] 6.1 Write failing tests plus fixtures for `antigravity_cli`, `grok_cli`, and `pi_cli`
  adapters (M)
  **Spec scenarios**: skill-workflow.4
  **Dependencies**: 2.10

- [ ] 6.2 Implement the three adapters under `skills/collect-transcripts/scripts/adapters/` (M)
  **Dependencies**: 6.1

- [ ] 6.3 Register the new adapters in `skills/collect-transcripts/scripts/normalize.py` (S)
  **Dependencies**: 6.2

- [ ] 6.4 Checkpoint: run the collect-transcripts suite, review diff, verify scope

- [ ] 6.5 Delete `adapters/gemini_cli.py`, `tests/test_gemini_cli.py`, and
  `tests/fixtures/gemini_cli/` (S)
  **Dependencies**: 6.3

## Phase 7 — Kanban seeder

- [ ] 7.1 Write a failing test asserting the seeder covers the five-vendor roster (S)
  **Spec scenarios**: coordinator-kanban-viz.2 (seed covers the full vendor roster)
  **Dependencies**: 3.15

- [ ] 7.2 Update `VENDORS` in `agent-coordinator/scripts/seed_kanban_board.py` (S)
  **Spec scenarios**: coordinator-kanban-viz.2
  **Dependencies**: 7.1

- [ ] 7.3 Update roster fixtures in `apps/kanban-viz/src/__tests__/VendorSwimlanes.test.tsx`,
  `agent-coordinator/src/schemas/kanban_viz/saved-view.json`,
  `agent-coordinator/tests/test_kanban_viz_endpoints.py`, and
  `skills/tests/agent-coordinator/test_kanban_viz_endpoints.py` (M)
  **Spec scenarios**: coordinator-kanban-viz.1 (vendor swimlanes)
  **Dependencies**: 7.1
  **Note**: `VendorSwimlanes.tsx` needs no change — it derives the vendor from the `agent_id`
  suffix and holds no roster (design D5).

- [ ] 7.3a Leave the review-provenance annotations in `src/hooks/useCoordinator.ts:244`,
  `src/__tests__/useCoordinator.test.tsx:278`, and `src/lib/coordinator-types.ts:266`
  UNCHANGED, and add each to the terminal gate's carve-out list (S)
  **Dependencies**: 7.1
  **Note**: added in PLAN_FIX (findings C7, U9). These strings name the vendor that raised a
  past finding (`IMPL_REVIEW claude#4/gemini#1`) — they are history, not roster data.
  Rewriting them falsifies the record. `coordinator-types.ts` was missing from the plan
  entirely; it is the one file the original inventory command failed to surface.

- [ ] 7.4 Checkpoint: run `npm test` in `apps/kanban-viz` plus the kanban endpoint tests,
  review diff, verify scope

## Phase 8 — Removal and residual references

- [ ] 8.1a Remove the `gemini-mcp-setup` and `gemini-wrapper-install` targets from
  `agent-coordinator/Makefile`, drop `gemini-mcp-setup` from the aggregate `mcp-setup`
  prerequisite list, and delete the `GEMINI_AGENT_ID` / `GEMINI_AGENT_TYPE` /
  `GEMINI_MCP_ENV_FLAGS` variables (M)
  **Spec scenarios**: agent-coordinator.1
  **Dependencies**: 4.11
  **Note**: added in PLAN_FIX (finding C2, confirmed by both vendors). `Makefile:184` makes
  `mcp-setup` depend on `gemini-mcp-setup`, and `Makefile:216` chmods/symlinks
  `gemini_wrapper.sh`. Deleting the wrapper first (old task 8.1) breaks `make mcp-setup` and
  `make gemini-wrapper-install`. **This task MUST precede 8.1b.**

- [ ] 8.1b Delete `agent-coordinator/scripts/gemini_wrapper.sh` (XS)
  **Dependencies**: 8.1a

- [ ] 8.1c Checkpoint: run `make -n mcp-setup` in `agent-coordinator/` and confirm it resolves
  with no gemini target and no missing prerequisite

- [ ] 8.2 Delete the repo-root `.gemini/` directory (XS)
  **Spec scenarios**: skill-workflow.1 (no per-vendor runtime directory is committed)
  **Design decisions**: D2
  **Dependencies**: 4.11

- [ ] 8.3 Remove `.gemini` from the skip-directory lists in
  `skills/tech-debt-analysis/scripts/analyze_complexity.py`, `analyze_duplication.py`, and
  `analyze_imports.py` (S)
  **Spec scenarios**: codebase-analysis.1, codebase-analysis.2
  **Dependencies**: 8.2

- [ ] 8.4 Checkpoint: run the tech-debt-analysis suite, review diff, verify scope

- [ ] 8.5 Update roster references in `skills/fetch-vendor-skills.sh`,
  `skills/langfuse/scripts/install-mcp.sh`, and `openspec/config.yaml` (S)
  **Dependencies**: 8.2

- [ ] 8.6 Update roster references in `packages/agent-scenarios/` — `executor.py`,
  `scenarios/plan-feature-basic.scenario.yaml`, `tests/test_runner.py`,
  `tests/test_findings_emitter.py` (M)
  **Dependencies**: 4.11

- [ ] 8.8 Run the agent-scenarios suite through its own environment
  (`uv run --project packages/agent-scenarios pytest tests`) and record the working
  invocation in `design.md` (S)
  **Dependencies**: 8.6
  **Note**: added in PLAN_FIX (finding U4, decision D7). `skills/.venv/bin/python -m pytest
  packages/agent-scenarios/tests` produces **6 collection errors** today — that venv lacks the
  package's dependencies, so wp-cleanup's gate as originally written could never pass.

- [ ] 8.7 Checkpoint: run the agent-scenarios suite via the corrected invocation, review diff

## Phase 9 — Documentation

- [ ] 9.1 Update the supported-vendor roster in `README.md` and `agent-coordinator/CLAUDE.md` (S)
  **Spec scenarios**: agent-coordinator.1
  **Dependencies**: 8.7

- [ ] 9.2 Update `docs/skills-workflow.md` and `docs/autopilot-provider-smoke.md` (S)
  **Spec scenarios**: skill-workflow.23, skill-workflow.24
  **Dependencies**: 8.7

- [ ] 9.3 Document the optional `~/.grok/config.toml` `[skills] paths` setup as operator-level,
  citing https://docs.x.ai/build/features/skills-plugins-marketplaces (S)
  **Spec scenarios**: skill-workflow.1 (canonical skill distribution)
  **Design decisions**: D2
  **Dependencies**: 8.2

- [ ] 9.6 Replace `GEMINI_API_KEY` with `OPENROUTER_API_KEY` in
  `agent-coordinator/.secrets.yaml.example` and in `docs/openbao-secret-management.md` (S)
  **Spec scenarios**: configuration.2
  **Dependencies**: 8.2
  **Note**: added in PLAN_FIX (finding U8). `proposal.md` commits to making
  `OPENROUTER_API_KEY` resolvable for pi, but no task added it to the secrets template and the
  file sat outside every package's `write_allow`.

- [ ] 9.7 Update the provider enumerations in `agent-coordinator/config.yaml.example`
  (`One of: claude_code, codex, gemini` plus the gemini tier example) and remove the
  `gemini_cli` adapter block from `skills/collect-transcripts/config.yaml.example` (S)
  **Dependencies**: 8.2

- [ ] 9.8 Update the roster and setup instructions in `agent-coordinator/README.md`,
  `docs/agent-coordinator.md`, and `skills/setup-coordinator/SKILL.md` (M)
  **Spec scenarios**: agent-coordinator.1
  **Dependencies**: 8.1c
  **Note**: `agent-coordinator/README.md` documents the make targets removed in 8.1a.

- [ ] 9.9 Checkpoint: confirm the 11-file in-scope doc set in `design.md` § In-scope
  user-facing set is fully covered, and that no carve-out file was modified

- [ ] 9.4 Update lifecycle SKILL.md provider prose to the new roster (M)
  **Spec scenarios**: skill-workflow.23
  **Dependencies**: 9.1

- [ ] 9.5 Checkpoint: run `openspec validate --all --strict`, review diff, verify scope

## Phase 10 — Integration

- [ ] 10.1 Run `bash skills/install.sh --mode rsync --force --deps none --python-tools none`
  and confirm mirrors carry no gemini references (S)
  **Spec scenarios**: skill-workflow.3 (infrastructure skills are synced)
  **Dependencies**: 9.5

- [ ] 10.2 Confirm zero gemini references remain in the in-scope set (S)
  **Dependencies**: 10.1
  **Verification**: `skills/.venv/bin/python openspec/changes/add-agy-grok-pi-harnesses/scripts/check_roster_residue.py --base main` exits 0
  **Note**: rewritten in PLAN_FIX (findings C1, C3, C6, U6). The original used `grep -rl` with
  an `--include` allow-list, which returns **240** files under system grep (171 inside
  `.venv`) and omitted `*.md` and extensionless files. The gate was unpassable and the scope
  under-measured. `git grep -lI` searches tracked files only and skips binaries.

- [ ] 10.2a Confirm no carve-out file was modified (S)
  **Dependencies**: 10.2
  **Verification**: covered by `check_roster_residue.py`'s carve-out check (same script,
  second assertion) — kept as a distinct task so the reviewer sees it named explicitly
  **Note**: added in PLAN_FIX. Applied SQL migrations seed `gemini_local` profile rows;
  rewriting them desynchronizes deployed databases from their migration history. A
  zero-references gate without this counter-check invites exactly that error.

- [ ] 10.5 Add `fastapi.testclient` (via `fastapi`/`httpx`) to `skills/.venv` so
  `pytest skills/tests` collects (S)
  **Dependencies**: 10.1
  **Note**: added in PLAN_FIX (finding U5, decision D7). `skills/tests/agent-coordinator/
  test_kanban_viz_endpoints.py:31` imports `fastapi.testclient`, which is absent — pytest
  reports `Interrupted: 1 error during collection` and exits non-zero after running 0 tests,
  making wp-integration's gate unpassable.

- [ ] 10.3 Run the full test suite with the per-tree interpreters recorded in `design.md` (M)
  **Dependencies**: 10.2a, 10.5
  **Verification**: `agent-coordinator/.venv` for `agent-coordinator/tests`,
  `skills/.venv` for `skills/tests`, `uv run --project packages/agent-scenarios` for
  agent-scenarios, `npm test -- --run` for `apps/kanban-viz`

- [ ] 10.4 Run a live smoke dispatch against each of antigravity, grok, and pi (M)
  **Spec scenarios**: skill-workflow.24
  **Dependencies**: 10.3
  **Note**: operator has authorized live billed calls (see `design.md` § Empirical CLI findings)
