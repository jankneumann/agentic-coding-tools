# Tasks — add-agy-grok-pi-harnesses (plan revision 2)

Implements Approach A (config-driven via the generic `CliVendorAdapter`) per proposal Gate 1.
Canonical provider key is `antigravity` (D3); `agy` appears only as `cli.command`.

**Plan revision 2** restructures the plan after the ESCALATE halt (see `design.md` § D8).
The bespoke gate scripts and manifest are deleted; every verification below is either an
existing test suite, a one-line `git grep` written inline, or an explicitly human-reviewed
checkpoint. Task numbers from revision 1 no longer apply — historical references to them
(review findings, round-1 resolution tables) are records of that revision, not of this file.

**Measured scope** (2026-07-22, informational — the gates below are authoritative, not these
counts): `git grep -lI "gemini\|Gemini\|GEMINI"` minus the carve-out directories yields
**124** tracked files. In scope: **66** code/config files, **12** user-facing
docs/templates/Makefile, and **10** SKILL.md files (the 8 lifecycle skills named by the
`skill-workflow` delta, plus `setup-coordinator` and `collect-transcripts`). Explicitly
untouched: **3** review-provenance annotations in `apps/kanban-viz` (design § Carve-outs).
Deferred to a follow-up change: **~33** narrative/historical prose files (design D6) — list
them any time with the inventory command in `design.md` § Scope inventory.

---

## Phase 0 — Baseline repair (pre-existing failures the gates depend on)

These failures exist on `main` today and would turn every downstream gate red regardless of
roster work. They are labeled here — not laundered into roster tasks — per D8.4.

- [ ] 0.1 Add `fastapi` and `httpx` to the **`test` extra** in `skills/pyproject.toml`
  (`[project.optional-dependencies] test`, alongside `pytest`), then re-sync with
  **`uv sync --all-extras`**; confirm `skills/.venv/bin/python -m pytest skills/tests -q`
  collects without `Interrupted` (S)
  **Why**: `skills/tests/agent-coordinator/test_kanban_viz_endpoints.py:31` imports
  `fastapi.testclient`, absent from the venv. The dependency goes in `pyproject.toml`, never
  directly into the venv — `uv sync` regenerates the venv and would discard it.
  **The extra and the `--all-extras` flag are both load-bearing** (PLAN_FIX round 3, claude
  finding R3-C3, verified): `pytest>=9.0.3` lives in the `test` extra, not in
  `[project] dependencies`, so a **bare `uv sync` removes pytest from `skills/.venv`** and
  breaks every skills gate this task exists to repair. Putting the new deps in `dependencies`
  instead would ship test-only packages to every skill consumer.
  **Dependencies**: None

- [x] 0.2 Rebase this branch on `add-frontier-model-tier` (PR #262) and confirm
  `pytest skills/tests/vendor-neutral-autopilot` is green (XS)
  **Why**: PR #262 absorbed the original repairs (schema promoted to
  `openspec/schemas/provider-model-map.schema.json`, contract-doc path repointed to the
  archive, `write_capable` fixture fixed).
  **Dependencies**: 0.1
  **Done 2026-07-22**: PR #262 merged to main (`c5081542`); this branch rebased onto it.
  `skills/.venv/bin/python -m pytest skills/tests/vendor-neutral-autopilot` → **32 passed**
  (was 19 passed / 5 failed). Task 0.1 remains open — `skills/tests` as a whole still stops
  at `Interrupted: 1 error during collection` for the missing `fastapi.testclient`.

- [ ] 0.3 Repair the 3 macOS-only `test_docker_manager.py` failures so the wp-coordinator
  gate can pass (S)
  **Why**: added in PLAN_FIX round 3 (codex finding R3-1, confirmed). `wp-coordinator`'s gate
  runs the full non-e2e coordinator suite, which is **3 failed, 2027 passed** before any
  roster work — an unpassable gate, the exact class D7/D8.2 exist to prevent.
  **Diagnosis (verified)**: not environmental and not flaky. `TestDetectRuntime.
  test_auto_falls_back_to_podman` (and the two `TestStartContainer` cases) patch
  `shutil.which` with `lambda name: f"/usr/bin/{name}"`, which returns a path for **every**
  binary — including `colima`. So `is_colima_installed()` returns True, `detect_runtime`
  takes the macOS Colima branch (`docker_manager.py:152-162`) and returns `"docker"` instead
  of falling through to `"podman"`. Proven: with `is_colima_installed` forced False the same
  call returns `"podman"`. The production code is correct; the **test mock is over-broad**.
  Linux CI passes only because `sys.platform != "darwin"` skips the branch entirely.
  **Fix**: narrow the `_which` mocks to the binaries under test (return `None` for `colima`),
  or patch `src.docker_manager.is_colima_installed` to False. Do NOT deselect the tests —
  scoping a gate around breakage is what D7 rejects.
  **Dependencies**: None

- [ ] 0.4 Install frontend dependencies so the kanban gates test the roster, not the
  environment: run `npm ci` in `apps/kanban-viz` (XS)
  **Why**: added in PLAN_FIX round 3 (codex finding R3-2, confirmed). A fresh worktree has no
  `apps/kanban-viz/node_modules`, so `npm test -- --run` exits with
  `sh: vitest: command not found`. Phases 4 and 6 both invoke `npm test` with no install
  step, so `wp-frontend` and the final full-suite gate would fail on setup rather than on
  roster behavior.
  **Dependencies**: None

- [ ] 0.5 Checkpoint: with the roster unmodified, run the **verification step of each of
  `wp-coordinator`, `wp-skills`, and `wp-frontend`** (in `work-packages.yaml`) and confirm all
  three pass on the baseline-repaired tree. **All three baselines must be green before any
  roster edit** — otherwise every downstream gate inherits a failure it did not cause. The
  suite commands live only in `work-packages.yaml`; do not restate them here.

## Phase 1 — Empirical CLI facts (resolves proposal open decisions 2 and 3)

Each task records its facts as `confirmed` or `refuted` **with the exact command and output
excerpt** in `design.md` § Empirical CLI findings. Whether the CLIs were genuinely invoked is
**not mechanically verifiable** — two scripted attempts at it were both defeated in review —
so checkpoint 1.4 is a human review, by design (D8.2). Operator authorization for live billed
calls is on record in `design.md`.

- [ ] 1.1 antigravity: record `agy models` output and resolve exact `--model` slugs for
  premium/standard/economy (E1); verify `--print` + stdin + `--mode plan` behave Claude-shaped
  (E7); record the re-login command or confirm the `agy login` fallback (E4a) (S)
  **Dependencies**: None

- [ ] 1.2 grok: verify `--prompt-file /dev/stdin` delivers a prompt under a subprocess pipe
  (E2); record model slugs for the three tiers (E5); verify `--output-format json` +
  `--json-schema review-findings.schema.json` emits a conforming envelope (E6) (S)
  **On failure of E2**: apply Approach B (thin wrapper) narrowly to grok; record in design.md.
  **On failure of E6**: grok's eval backend and review dispatch fall back to text parsing;
  re-scope task 2.6 before starting it.
  **Dependencies**: None

- [ ] 1.3 pi: verify `OPENROUTER_API_KEY` resolves from the subprocess environment with
  `--provider openrouter` (E3); verify the prompt passes as a trailing positional and record
  the output shape (E8); record the re-login command or confirm `pi login` fallback (E4b) (S)
  **Dependencies**: None

- [ ] 1.4 Checkpoint (**human review**): every row E1–E8 in `design.md` reads `confirmed` or
  `refuted` with command + output evidence. No package may hardcode a CLI flag, model slug, or
  output-parsing assumption for these vendors until this checkpoint passes.

## Phase 2 — Coordinator (registry, model map, eval backends, seeder, Makefile)

- [ ] 2.1 Write failing tests for the new roster in `agent-coordinator/tests/test_agents_config.py`
  and `test_agents_config_isolation.py` (M)
  **Spec scenarios**: configuration.1, configuration.2, agent-archetypes.1, agent-archetypes.2
  **Contracts**: `contracts/roster.md`
  **Dependencies**: 1.4

- [ ] 2.2 Add `antigravity-local`, `grok-local`, `pi-local` to `agents.yaml` with
  `cli.dispatch_modes` for review/alternative/quick **and a `profile:` + `trust_level:` on
  each entry**; remove `gemini-local` and `gemini-remote` (M)
  **Spec scenarios**: skill-workflow.15, configuration.1, **agent-identity.1** (profile
  seeding: "WHEN `agents.yaml` defines `grok-local` with `profile: grok_local` and
  `trust_level: 3`")
  **Dependencies**: 2.1
  **Note**: the `profile:`/`trust_level:` requirement was added in PLAN_FIX round 3 (claude
  finding R3-C8). The `agent-identity` spec delta was the only one of the 8 capabilities no
  task referenced — its seeding scenarios name `grok-local`'s `profile`/`trust_level` fields,
  which nothing in the plan created. Seeding is additive by contract, so retiring gemini does
  NOT delete its seeded rows and no migration is needed (design § Carve-outs).

- [ ] 2.3 Update `DEFAULT_PROVIDER_MODEL_MAP` (`src/agents_config.py`) and `model_aliases`
  (`archetypes.yaml`): add antigravity/grok/pi base tiers first, then remove gemini (M)
  **Spec scenarios**: configuration.2, agent-archetypes.1
  **Dependencies**: 2.1
  **Note**: add-before-remove keeps every intermediate commit dispatchable. The
  `schema_version: 2` bump landed in `add-frontier-model-tier` — do not re-bump. Preserve the
  existing `frontier` entries for claude_code/codex; the new vendors' `frontier` is OPTIONAL —
  define it only if the empirical phase (E1/E5) surfaces a clearly stronger reasoning model,
  otherwise omit and let resolution fall back to premium.

- [ ] 2.4 Update roster references in `src/coordination_api.py`, `scripts/setup_cloud.py`, and
  the fixtures in `tests/test_differential_policy.py` and `tests/model_routing/test_feedback.py` (M)
  **Spec scenarios**: agent-coordinator.1
  **Dependencies**: 2.2, 2.3

- [ ] 2.5 Checkpoint: run the coordinator config suite, review diff, verify scope

- [ ] 2.6 Eval backends (proposal D4): write failing tests in
  `agent-coordinator/tests/test_evaluation/`, implement `AgentBackend` for grok
  (via `--output-format json`), antigravity, and pi, then delete
  `evaluation/backends/gemini_jules.py`, its `__all__` export, and roster references in
  `evaluation/__init__.py`, `evaluation/config.py`, `evaluation/backends/base.py` (L — flagged;
  single package, single suite, one reviewer sees the whole backend surface at once)
  **Spec scenarios**: evaluation-framework.1 (all vendor scenarios; retired backend absent)
  **Dependencies**: 2.5

- [ ] 2.7 Kanban seeder + coordinator-side fixtures: write a failing five-vendor seeder test,
  update `VENDORS` in `scripts/seed_kanban_board.py`, update
  `tests/test_kanban_viz_endpoints.py` and `src/schemas/kanban_viz/saved-view.json` (M)
  **Spec scenarios**: coordinator-kanban-viz.1, coordinator-kanban-viz.2
  **Dependencies**: 2.5

- [ ] 2.8 `agent-coordinator/Makefile`: remove the `gemini-mcp-setup` and
  `gemini-wrapper-install` targets, drop them from **both** the `mcp-setup` and `hooks-setup`
  prerequisite lists, delete the `GEMINI_AGENT_ID` / `GEMINI_AGENT_TYPE` /
  `GEMINI_MCP_ENV_FLAGS` variables, **then** delete `scripts/gemini_wrapper.sh`;
  confirm `make -n mcp-setup hooks-setup` resolves (M)
  **Spec scenarios**: agent-coordinator.1
  **Dependencies**: 2.5
  **Note**: `hooks-setup` (Makefile:232) has the same dependency `mcp-setup` had — the round-1
  fix missed it. Targets go before the wrapper file, in one task, so no intermediate state breaks.

- [ ] 2.9 Remove `google-generativeai` from `agent-coordinator/pyproject.toml` and run
  `uv lock` (S)
  **Dependencies**: 2.6
  **Note**: declared solely for the retired `gemini-remote` SDK block. The string contains no
  "gemini", so no grep gate can ever catch it — which is why it is an explicit task with an
  explicit verification, not a gate assumption.

- [ ] 2.10 Checkpoint: run **`wp-coordinator`'s verification step** in
  `work-packages.yaml` and confirm it exits 0. That command is the single authority for this
  phase — coordinator suite green, owned tree free of live gemini references, the
  `google-generativeai` dependency gone, and `make -n mcp-setup hooks-setup` resolving. Do not
  restate it here; a second copy is what drifted in round 3.

## Phase 3 — Skills, dispatch allow-lists, adapters, agent-scenarios

- [ ] 3.1 Write failing tests for the new roster across the dispatch test surface (L — flagged;
  every file asserts against the same roster constant; splitting them hides inconsistency):
  `skills/tests/vendor-neutral-autopilot/`, `skills/tests/parallel-infrastructure/`,
  `skills/tests/autopilot*/`, `skills/parallel-infrastructure/scripts/tests/`,
  `skills/parallel-infrastructure/tests/test_vendor_diversity.py`,
  `skills/fix-scrub/tests/test_vendor_dispatch.py`,
  `skills/tests/prototype-feature/test_dispatch_variants.py`,
  `skills/tests/integration/test_prototype_convergence.py`,
  `skills/autopilot/scripts/tests/test_implementation_strategy_selector.py` (L)
  **Spec scenarios**: skill-workflow.4, .5, .6, .20, .24
  **Dependencies**: 0.5, 1.4

- [ ] 3.2 Update `_SUPPORTED_PROVIDERS` in `skills/autopilot/scripts/provider_dispatch.py` and
  the argparse `choices` in `token_budget_check.py` + `smoke_provider_dispatch.py` (S)
  **Spec scenarios**: skill-workflow.23, .24
  **Dependencies**: 3.1

- [ ] 3.3 Update `available = [...]` in `skills/autopilot-roadmap/scripts/orchestrator.py:319`
  and `_STATIC_COST_TIERS` in `skills/autopilot-roadmap/scripts/policy.py`, keeping both
  structures shape-stable for `ri-02`'s clean deletion (S)
  **Spec scenarios**: skill-workflow.6
  **Dependencies**: 3.1

- [ ] 3.4 Update `_RELOGIN_COMMANDS` in
  `skills/parallel-infrastructure/scripts/review_dispatcher.py` (using E4 facts) and drop the
  Gemini `-o json` envelope-unwrap special case (M)
  **Spec scenarios**: skill-workflow.18
  **Dependencies**: 3.1

- [ ] 3.5 Update roster references in `consensus_synthesizer.py`,
  `openspec/schemas/consensus-report.schema.json`, the mirrored
  `skills/parallel-infrastructure/install_assets/` copy, `skills/quick-task/scripts/quick_task.py`,
  `skills/review-artifacts/scripts/open_artifacts.py`, `scripts/impl_review_driver.py`, and
  `scripts/impl_review_handoff.py` (M)
  **Spec scenarios**: skill-workflow.7
  **Dependencies**: 3.1

- [ ] 3.6 Tighten the provider key set in the already-promoted
  `openspec/schemas/provider-model-map.schema.json` (landed via `add-frontier-model-tier`):
  close `providers` to the five roster keys (`propertyNames.enum` + `required`), preserving
  the optional `frontier` tier property; update the
  `skills/tests/vendor-neutral-autopilot/test_contracts.py` fixtures to the v2 roster (S)
  **Spec scenarios**: configuration.1
  **Dependencies**: 3.1, 0.2
  **Note**: the promotion itself, the `const: 2` bump, and the test repoint are already done —
  this task only encodes the roster closure this change is about.

- [ ] 3.7 Checkpoint: dispatch suites green, review diff, verify scope

- [ ] 3.8 Transcript adapters: write failing tests + fixtures for `antigravity_cli`,
  `grok_cli`, `pi_cli`; implement the three adapters under
  `skills/collect-transcripts/scripts/adapters/`; register them in `normalize.py`; then delete
  `gemini_cli.py`, `tests/test_gemini_cli.py`, and `tests/fixtures/gemini_cli/` (L — flagged;
  the three adapters share the event-schema surface and land against one suite)
  **Spec scenarios**: skill-workflow.4
  **Dependencies**: 1.4
  **Note**: E7/E8 output shapes feed the antigravity/pi fixtures.

- [ ] 3.9 Update `.gemini` skip-directory entries in `skills/tech-debt-analysis/scripts/`
  (`analyze_complexity.py`, `analyze_duplication.py`, `analyze_imports.py`), plus roster
  references in `skills/fetch-vendor-skills.sh` and `skills/langfuse/scripts/install-mcp.sh` (S)
  **Spec scenarios**: codebase-analysis.1, codebase-analysis.2
  **Dependencies**: 3.1

- [ ] 3.10 Update `packages/agent-scenarios/`: `executor.py`,
  `scenarios/plan-feature-basic.scenario.yaml`, `tests/test_runner.py`,
  `tests/test_findings_emitter.py`; verify via
  `uv run --project packages/agent-scenarios pytest packages/agent-scenarios/tests -q` (M)
  **Dependencies**: 3.1
  **Note**: the path argument is explicit — `uv run --project` does **not** change the working
  directory, so a bare `pytest tests` would collect the repo-root `tests/`.

- [ ] 3.11 Remove `google-generativeai` from `skills/pyproject.toml` and run `uv lock` (S)
  **Dependencies**: 3.2

- [ ] 3.12 Checkpoint: run **`wp-skills`'s verification step** in `work-packages.yaml` and
  confirm it exits 0 — skills suites (including the four test dirs outside `skills/tests`),
  agent-scenarios via its own project, owned-tree residue clean, and `google-generativeai`
  gone from `skills/pyproject.toml`. SKILL.md prose and the config example belong to Phase 5;
  `skills/tests/agent-coordinator` belongs to `wp-frontend`; the excluded narrative paths are
  deferred per D6. The gate command lives only in `work-packages.yaml`.

## Phase 4 — Kanban frontend

- [ ] 4.1 Update roster fixtures in `apps/kanban-viz/src/__tests__/VendorSwimlanes.test.tsx`.
  `VendorSwimlanes.tsx` is NOT modified — it derives the vendor from the `agent_id` suffix and
  holds no roster (design D5). Leave the review-provenance annotations in
  `src/hooks/useCoordinator.ts:244`, `src/__tests__/useCoordinator.test.tsx:278`, and
  `src/lib/coordinator-types.ts:266` unchanged — they are history, not roster data (S)
  **Spec scenarios**: coordinator-kanban-viz.1
  **Dependencies**: 2.7

- [ ] 4.2 Update the skills-tree kanban endpoint fixtures in
  `skills/tests/agent-coordinator/test_kanban_viz_endpoints.py` (S)
  **Owner**: `wp-frontend` (moved from `wp-skills` in PLAN_FIX round 3, claude finding
  R3-C7). This task depends on 2.7, which `wp-coordinator` owns; `wp-skills` declares
  `depends_on: [wp-empirical]` only, so the DAG did not express the edge and a scheduler
  could have run 4.2 before its prerequisite. `wp-frontend` already depends on
  `wp-coordinator`, so moving the task makes the declared dependency real. The path is added
  to `wp-frontend`'s `write_allow` and removed from `wp-skills`'.
  **Dependencies**: 2.7, 0.1

- [ ] 4.3 Checkpoint: run **`wp-frontend`'s verification step** in `work-packages.yaml` and
  confirm it exits 0 — frontend tests green, the new roster present in both fixture files,
  and `VendorSwimlanes.tsx` plus all three review-provenance files unmodified against `main`.
  **The gemini fixture in `VendorSwimlanes.test.tsx` stays**: the
  `coordinator-kanban-viz` *Historical vendor still renders* scenario requires it, and it is
  the only mechanical evidence that the component consults no roster allow-list (D5). The
  gate command lives only in `work-packages.yaml`.

## Phase 5 — Docs, templates, SKILL.md prose, runtime-dir removal

- [ ] 5.1 Delete the repo-root `.gemini/` directory (XS)
  **Spec scenarios**: skill-workflow.1
  **Design decisions**: D2
  **Dependencies**: 2.8

- [ ] 5.2 Update the supported-vendor roster in `README.md`, `agent-coordinator/CLAUDE.md`,
  and `agent-coordinator/README.md` (including the make targets removed in 2.8) (S)
  **Spec scenarios**: agent-coordinator.1
  **Dependencies**: 2.8

- [ ] 5.3 Update `docs/skills-workflow.md`, `docs/autopilot-provider-smoke.md`,
  `docs/agent-coordinator.md`, **`docs/cross-repo-setup.md`**; replace `GEMINI_API_KEY` with
  `OPENROUTER_API_KEY` in `docs/openbao-secret-management.md` (M)
  **Spec scenarios**: skill-workflow.23, .24, agent-coordinator.1, configuration.2
  **Dependencies**: 2.8, 3.9
  **Note**: `docs/cross-repo-setup.md` added in PLAN_FIX round 3 (claude finding R3-C9). It
  documents `install-mcp.sh`'s `--no-gemini` skip flag and a `~/.gemini/settings.json` target
  (lines 348, 366, 384, 386) — it instructs a human to invoke gemini tooling, which is D6's
  own inclusion criterion, and task 3.9 edits the very script it documents. Hence the added
  dependency on 3.9: the doc must follow the script, not lead it.

- [ ] 5.4 Update templates: `agent-coordinator/.secrets.yaml.example` (add
  `OPENROUTER_API_KEY`, remove `GEMINI_API_KEY`), `agent-coordinator/config.yaml.example`
  (provider enumeration + tier example), `skills/collect-transcripts/config.yaml.example`
  (adapter block), and the vendor list in `openspec/config.yaml` (S)
  **Spec scenarios**: configuration.2
  **Dependencies**: 2.8

- [ ] 5.5 Update provider prose in the 8 lifecycle SKILL.md files named by the
  `skill-workflow` delta (`autopilot`, `plan-feature`, `implement-feature`, `iterate-on-plan`,
  `iterate-on-implementation`, `parallel-review-plan`, `parallel-review-implementation`,
  `validate-feature`) plus `skills/setup-coordinator/SKILL.md` and
  `skills/collect-transcripts/SKILL.md` (M)
  **Spec scenarios**: skill-workflow.23 (no lifecycle skill doc names Gemini/Jules as a
  dispatch provider)
  **Dependencies**: 3.12
  **Note**: these 10 files are IN scope (D8.3) — the spec delta names the 8 lifecycle files
  explicitly, so deferring them would make the spec unsatisfiable by this change. The ~12
  remaining SKILL.md files with narrative gemini mentions stay deferred (D6).

- [ ] 5.5a Update the agent-type roster in the session-log templates:
  `openspec/schemas/feature-workflow/templates/session-log.md:52` and its mirrored copy
  `skills/plan-feature/install_assets/openspec/schemas/feature-workflow/templates/session-log.md:52`
  (both read `| Agent Type | <!-- claude, codex, gemini, other --> |`) (S)
  **Dependencies**: 3.12
  **Note**: added in PLAN_FIX round 3 (codex finding R3-3, confirmed). These are live edit
  sites that instruct an agent to record `gemini` as its type, but **no package owned them**
  — `wp-skills` allows only two specific `openspec/schemas/` files and explicitly denies
  `skills/plan-feature/install_assets/**`. Ownership moved to `wp-docs-finalize`, which
  already owns the template surface. Edit both copies: `install_assets/` is the source
  `install.sh` distributes, so fixing only the canonical one reintroduces the drift.

- [ ] 5.6 Document the optional `~/.grok/config.toml` `[skills] paths` setup as operator-level
  in **`docs/skills-workflow.md`**, citing
  https://docs.x.ai/build/features/skills-plugins-marketplaces (S)
  **Note**: the target file is named because `wp-docs-finalize`'s gate greps for the citation
  under `docs/` only — writing it into a SKILL.md instead would satisfy the task's prose and
  fail the gate (finding R4-C7).
  **Spec scenarios**: skill-workflow.1
  **Design decisions**: D2
  **Dependencies**: 5.3

- [ ] 5.7 Checkpoint: run **`wp-docs-finalize`'s first verification step** in
  `work-packages.yaml` and confirm it exits 0 — `openspec validate --all --strict`, the grok
  citation present, `.gemini/` gone, and the in-scope doc/template/SKILL.md file list free of
  gemini, and — folded into the same gate — that no carve-out file appears in the change's
  diff against `main`. The gate command and its file list live only in `work-packages.yaml`.

## Phase 6 — Integration and validation

- [ ] 6.1 Run `bash skills/install.sh --mode rsync --force --deps none --python-tools none`;
  then run **`wp-docs-finalize`'s second verification step** in `work-packages.yaml`, which
  re-syncs the mirrors and proves they carry no live gemini references (S)
  **Note**: the mirror check MUST use plain `grep -rIl`, never `git grep`.
  `.claude/skills/` and `.agents/skills/` are gitignored (`.gitignore:271-272`), so `git grep`
  searches zero tracked files there and passes unconditionally — it was vacuous in revision 2
  (finding R3-C2). The working command lives only in `work-packages.yaml`.
  **Spec scenarios**: skill-workflow.3
  **Dependencies**: 5.7

- [ ] 6.2 Run **`wp-docs-finalize`'s second verification step** (already invoked in 6.1) and
  confirm the full four-tree suite passes end-to-end after the mirror sync. That step is the
  single home for the full-suite command — it covers `agent-coordinator/tests`, the skills
  tree (including the four dirs `pytest skills/tests` alone does not collect), agent-scenarios
  via its own project, and the kanban frontend. Do not restate the suite commands here. (M)
  **Dependencies**: 6.1

- [ ] 6.3 Live smoke dispatch against each of antigravity, grok, and pi (operator-authorized;
  see design.md § Empirical CLI findings) (M)
  **Spec scenarios**: skill-workflow.24
  **Dependencies**: 6.2

- [ ] 6.4 Record the deferred-narrative follow-up: run the design.md inventory command, save
  the remaining file list into the session log, and note it in the PR description as an
  explicit follow-up change (XS)
  **Dependencies**: 6.2
