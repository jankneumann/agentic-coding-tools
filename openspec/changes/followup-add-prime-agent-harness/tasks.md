# Tasks — followup-add-prime-agent-harness

These are the 33 unchecked tasks migrated from `add-prime-agent-harness` during
post-merge cleanup on 2026-08-30. Their numbering and dependency relationships
are preserved exactly; no task is represented as completed.

Implements Approach A (config-driven via the generic `CliVendorAdapter`,
`prime-agent --mode json`). Canonical provider key is `prime` (design D1);
`prime-agent` appears only as `cli.command`. All roster edits are additive —
add-before-anything keeps every intermediate commit dispatchable.

## Phase 0 — Baseline

- [ ] 0.1 Confirm the coordinator, skills, agent-scenarios, and kanban-frontend
  suites are green on the branch point before any roster edit; record counts here.
  Any pre-existing failure is labeled and filed, never laundered into roster tasks
  (precedent D8.4). (S)
  **Dependencies**: None

## Phase 1 — Empirical CLI facts (resolves proposal Open Decisions 1–4)

Each task records its facts as `confirmed` or `refuted` with the exact command and
output excerpt in `design.md` § Empirical CLI findings. Operator authorization for
live billed calls must be on record in design.md first. No package may hardcode a
CLI flag, model slug, or output-parsing assumption for this vendor until
checkpoint 1.5 passes.

- [ ] 1.1 Install prime-agent on the operator machine; record version and full flag
  inventory (P1); verify trailing-positional prompt delivery under a subprocess pipe
  in `--mode json` (P2); capture a full NDJSON transcript and record the envelope
  shape + final-text location (P3) (S)
  **Dependencies**: None

- [ ] 1.2 Authenticate with `PRIME_API_KEY` only (design D2); verify subprocess env
  inheritance and `auth.json` precedence; record the re-auth story for
  `_RELOGIN_COMMANDS` vs `_MANUAL_REAUTH` (P5); enumerate the Prime Inference
  catalog and select tier slugs per design D4, recording overlap with `pi`'s tiers
  (P4) (S)
  **Dependencies**: 1.1

- [ ] 1.3 Review-mode admission evidence (design D5): attempt a harness-native
  write-prevention configuration; run a review-shaped dispatch against a fixture
  repo and verify (a) no writes occurred, (b) the transcript shows the named files
  were actually read (P6). On failure of either: mark the `review` dispatch mode
  withheld and re-scope tasks 2.2 / 3.x accordingly (S)
  **Dependencies**: 1.1

- [ ] 1.4 Daemon + sub-agent policy: after a `--mode json` one-shot, record resident
  `prime-agent` processes and the cleanup command semantics (P7); record whether
  `rlm()` child model selection can be pinned or disabled via settings (P8); record
  whether any reasoning-effort/thinking flag exists (P9) (S)
  **Dependencies**: 1.1

- [ ] 1.5 Checkpoint (**human review**): every row P1–P9 in `design.md` reads
  `confirmed` or `refuted` with command + output evidence; Open Decisions 1–4 in
  `proposal.md` resolved and recorded. Phases 2–6 are blocked until this passes.
  **Dependencies**: 1.1, 1.2, 1.3, 1.4

## Phase 2 — Coordinator (registry, model map, schema, eval backend, seeder)

- [ ] 2.1 Write failing roster tests in `agent-coordinator/tests/test_agents_config.py`
  and `test_agents_config_isolation.py`, including the D1 collision guard
  (`pi` ≠ `prime`, disjoint `cli.command`, word-bounded roster asserts) (M)
  **Dependencies**: 1.5

- [ ] 2.2 Add `prime-local` to `agents.yaml` with `profile: prime_local`,
  `trust_level: 3`, `transport: mcp`, and `cli.dispatch_modes` per Phase 1 facts
  (review mode included only if 1.3 passed), plus `cli.api_key_env:
  PRIME_API_KEY` for the separately supplied provider credential (M)
  **Dependencies**: 2.1

- [ ] 2.3 Add `prime` tiers to `DEFAULT_PROVIDER_MODEL_MAP` (`src/agents_config.py`)
  and `model_aliases` (`archetypes.yaml`) using the P4 slugs; omit `frontier` unless
  P4 surfaced a clearly stronger reasoning model (M)
  **Dependencies**: 2.1

- [ ] 2.4 Extend `openspec/schemas/provider-model-map.schema.json` to the six-key
  roster (`propertyNames.enum`, `required`, `minProperties: 6`) and bump
  `schema_version` to 3; update the schema-consuming fixtures in
  `skills/tests/vendor-neutral-autopilot/test_contracts.py` (S)
  **Dependencies**: 2.3

- [ ] 2.5 Eval backend: failing tests in `tests/test_evaluation/`, then
  `evaluation/backends/prime.py` (NDJSON stream-parse per P3) registered in
  `backends/registry.py`; `backends/pi.py` is the template (M)
  **Dependencies**: 2.2

- [ ] 2.6 Kanban seeder + saved-view enum: six-vendor seeder test, `VENDORS` in
  `scripts/seed_kanban_board.py`, `src/schemas/kanban_viz/saved-view.json`,
  `tests/test_kanban_viz_endpoints.py` fixtures (S)
  **Dependencies**: 2.2

- [ ] 2.7 Prove the registry-derived coordinator identity boundary in
  `tests/test_setup_cloud.py`: `prime-local` yields `prime_local_key`,
  `--prime-local-key`, a `{agent_id: prime-local, agent_type: prime}` identity, and
  the `cprime-agent` alias injecting that key only as `COORDINATION_API_KEY`.
  Assert setup-cloud neither accepts nor emits `PRIME_API_KEY`; production
  `setup_cloud.py` requires no vendor-specific branch because it already projects
  the registry generically (S)
  **Dependencies**: 2.2

- [ ] 2.8 Checkpoint: coordinator suite green; mypy/ruff clean on changed files;
  model map validates against schema v3; diff scoped to coordinator surface (S)
  **Dependencies**: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7

## Phase 3 — Skills, dispatch allow-lists, adapters, agent-scenarios

- [ ] 3.1 Write failing roster tests across the dispatch test surface
  (`skills/tests/vendor-neutral-autopilot/`, `skills/tests/parallel-infrastructure/`,
  `skills/tests/autopilot*/`, vendor-diversity and fix-scrub dispatch suites) (L)
  **Dependencies**: 1.5

- [ ] 3.2 Add `prime` to `_SUPPORTED_PROVIDERS` (`provider_dispatch.py`), argparse
  `choices` + tier tables (`token_budget_check.py`, `smoke_provider_dispatch.py`) (S)
  **Dependencies**: 3.1

- [ ] 3.3 Add `prime` to `available` (`autopilot-roadmap/scripts/orchestrator.py`)
  and `_STATIC_COST_TIERS` (`policy.py`), shape-stable for the pending registry
  change's deletion (S)
  **Dependencies**: 3.1

- [ ] 3.4 `review_dispatcher.py`: re-auth tables per P5; `_parse_findings` NDJSON
  branch only if P3 showed a shape the existing pi stream-parse cannot handle;
  parse the canonical optional cleanup object and execute it exactly once without a
  shell after every launched attempt (success, non-zero exit, parse failure,
  cancellation, timeout; async only after terminal polling). Add tests for absent
  cleanup, success/failure/timeout paths, literal metacharacter argv, minimal secret
  environment, cleanup failure/timeout, quorum ineligibility, and concurrent-session
  safety per P7/D6 (M)
  **Dependencies**: 3.1, 3.4a

- [ ] 3.4a Canonical config-contract producer for the D6 cleanup field — **required
  before 3.4 consumes cleanup from `agents.yaml`**. The `cli` object declares
  `"additionalProperties": False` (`agent-coordinator/src/agents_config.py`), so a
  `cleanup` key added to a vendor's `cli:` block is rejected today with
  `Additional properties are not allowed ('cleanup' was unexpected)` — verified
  against `load_agents_config` on 2026-08-24. Implement the contract shape
  `cleanup: {args: [string, ...], timeout_seconds: integer}` through:
  1. **Schema** — typed object with non-empty argv tokens and bounded timeout.
  2. **Canonical parser** — a cleanup dataclass on `CliConfig`, parsed by
     `load_agents_config()` with absence remaining backward-compatible.
  3. **HTTP/MCP projection** — `get_dispatch_configs()` emits the object losslessly;
     the existing HTTP and MCP endpoints both delegate to this producer.
  4. **Tests** — `test_agents_config.py` covers acceptance, rejection, absence, and
     load→projection equality; dispatch-config endpoint tests pin the same payload.
  This capability is unconditional. P7 decides whether `prime-local` populates it;
  when no residue exists the entry omits the field, without deleting the generic
  lifecycle contract. (S)
  **Dependencies**: 3.1

- [ ] 3.5 Vendor enum updates: `consensus-report.schema.json` + mirrored
  `install_assets/` copy; `consensus_synthesizer.py` roster references (S)
  **Dependencies**: 3.1

- [ ] 3.6 Transcript adapter: failing tests + fixtures for `prime_cli`, implement
  under `skills/collect-transcripts/scripts/adapters/`, register in `normalize.py`
  (M)
  **Dependencies**: 1.5

- [ ] 3.7 `packages/agent-scenarios/.../executor.py`: add the `prime` argv template;
  verify via the package's own project (`uv run --project packages/agent-scenarios
  pytest packages/agent-scenarios/tests -q`) (S)
  **Dependencies**: 3.1

- [ ] 3.8 Checkpoint: skills + parallel-infrastructure + agent-scenarios suites
  green; word-bounded residue check confirms no unanchored `pi`/`prime` conflation
  in gates or fixtures (S)
  **Dependencies**: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7

## Phase 4 — Kanban frontend

- [ ] 4.1 Add `prime` to the roster fixtures in
  `apps/kanban-viz/src/__tests__/VendorSwimlanes.test.tsx` (component itself holds
  no roster and is not modified — precedent D5); extend
  `test_vendor_extraction_from_agent_id` cases so omission fails the suite (S)
  **Dependencies**: 2.6

- [ ] 4.2 Checkpoint: frontend tests green (`npm ci && npm test -- --run`) (XS)
  **Dependencies**: 4.1

## Phase 5 — Docs and templates

- [ ] 5.1 Update supported-vendor prose: `README.md`, `agent-coordinator/CLAUDE.md`,
  `agent-coordinator/README.md`, `docs/skills-workflow.md`,
  `docs/autopilot-provider-smoke.md`, lifecycle SKILL.md files (M)
  **Dependencies**: 3.8

- [ ] 5.2 Templates: `.secrets.yaml.example` (+`PRIME_API_KEY`),
  `config.yaml.example`, `skills/collect-transcripts/config.yaml.example`,
  `openspec/config.yaml` vendor list, session-log template agent-type roster (both
  the canonical and `install_assets/` copies) (S)
  **Dependencies**: 3.8

- [ ] 5.3 Document the subscription-lane policy (design D2) in the operator setup
  docs: `PRIME_API_KEY` auth only; Claude/OpenAI/Copilot OAuth inside prime-agent is
  out of policy for dispatched use (S)
  **Dependencies**: 5.1

- [ ] 5.4 Checkpoint: `openspec validate --all --strict` green; doc roster prose
  consistent with `agents.yaml` (XS)
  **Dependencies**: 5.1, 5.2, 5.3

## Phase 6 — Integration and validation

- [ ] 6.1 Run `bash skills/install.sh` mirror sync; confirm runtime skill trees
  carry the updated rosters (S)
  **Dependencies**: 5.4

- [ ] 6.2 Full four-tree suite (coordinator, skills, agent-scenarios, kanban
  frontend); zero new failures vs the Phase 0 baseline (M)
  **Dependencies**: 6.1

- [ ] 6.3 Live smoke dispatch (operator-authorized, billed): one dispatch per
  enabled mode against `prime-local`; parseable envelope, expected sentinel output,
  zero resident `prime-agent` processes afterward (D6); evidence saved under
  `validation/smoke-6.3/` (M)
  **Dependencies**: 6.2

- [ ] 6.4 File the recorded follow-ups: Prime Inference `endpoint_kind` lane under
  `add-adaptive-model-router` (design D7); ACP adapter spike (design D3); review-mode
  unblock work if 1.3 withheld it (XS)
  **Dependencies**: 6.2
