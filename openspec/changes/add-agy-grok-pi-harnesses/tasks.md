# Tasks — add-agy-grok-pi-harnesses

Implements Approach A (config-driven via the generic `CliVendorAdapter`) per proposal Gate 1.
Canonical provider key is `antigravity` (D3); `agy` appears only as `cli.command`.

**Measured scope**: 68 live files reference gemini outside runtime mirrors and archived
changes, plus the repo-root `.gemini/` directory. The proposal's original enumeration listed
~15 sites; the inventory below is the authoritative list.

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

- [ ] 2.5 Checkpoint: fold all empirical findings into `design.md` before any config is written

## Phase 3 — Registry and provider config

- [ ] 3.1 Write failing tests for the new roster in `agent-coordinator/tests/test_agents_config.py`
  and `test_agents_config_isolation.py` (M)
  **Spec scenarios**: configuration.1, configuration.2, agent-archetypes.1, agent-archetypes.2
  **Contracts**: `contracts/provider-model-map.schema.json`
  **Dependencies**: 1.2, 2.5

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
  **Dependencies**: 3.1, 2.1

- [ ] 3.6 Remove the `gemini` entry from `DEFAULT_PROVIDER_MODEL_MAP` (XS)
  **Spec scenarios**: configuration.2
  **Dependencies**: 3.5
  **Note**: split from 3.5 deliberately — adding before removing keeps every intermediate
  commit dispatchable, which is the safe migration order

- [ ] 3.7 Checkpoint: run `test_agents_config.py`, review diff, verify scope

- [ ] 3.8 Add antigravity/grok/pi `model_aliases` to `archetypes.yaml` (S)
  **Spec scenarios**: agent-archetypes.1, agent-archetypes.2
  **Dependencies**: 3.1, 2.1

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
  **Dependencies**: 2.5

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

- [ ] 7.3 Update vendor fixtures in `apps/kanban-viz/src/__tests__/VendorSwimlanes.test.tsx`,
  `useCoordinator.test.tsx`, `src/hooks/useCoordinator.ts`,
  `agent-coordinator/src/schemas/kanban_viz/saved-view.json`,
  `agent-coordinator/tests/test_kanban_viz_endpoints.py`, and
  `skills/tests/agent-coordinator/test_kanban_viz_endpoints.py` (M)
  **Spec scenarios**: coordinator-kanban-viz.1 (vendor swimlanes)
  **Dependencies**: 7.1
  **Note**: `VendorSwimlanes.tsx` itself needs no change — it derives the vendor from the
  `agent_id` suffix and holds no roster. Verified during planning.

- [ ] 7.4 Checkpoint: run `npm test` in `apps/kanban-viz` plus the kanban endpoint tests,
  review diff, verify scope

## Phase 8 — Removal and residual references

- [ ] 8.1 Delete `agent-coordinator/scripts/gemini_wrapper.sh` (XS)
  **Dependencies**: 4.11

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

- [ ] 8.7 Checkpoint: run the agent-scenarios suite, review diff, verify scope

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

- [ ] 9.4 Update lifecycle SKILL.md provider prose to the new roster (M)
  **Spec scenarios**: skill-workflow.23
  **Dependencies**: 9.1

- [ ] 9.5 Checkpoint: run `openspec validate --all --strict`, review diff, verify scope

## Phase 10 — Integration

- [ ] 10.1 Run `bash skills/install.sh --mode rsync --force --deps none --python-tools none`
  and confirm mirrors carry no gemini references (S)
  **Spec scenarios**: skill-workflow.3 (infrastructure skills are synced)
  **Dependencies**: 9.5

- [ ] 10.2 Confirm zero live gemini references remain outside `openspec/changes/archive/` (S)
  **Dependencies**: 10.1
  **Verification**: the inventory command in `design.md` § Scope inventory returns empty

- [ ] 10.3 Run the full test suite across `agent-coordinator`, `skills`, `packages`, and
  `apps/kanban-viz` (M)
  **Dependencies**: 10.2

- [ ] 10.4 Run a live smoke dispatch against each of antigravity, grok, and pi (M)
  **Spec scenarios**: skill-workflow.24
  **Dependencies**: 10.3
