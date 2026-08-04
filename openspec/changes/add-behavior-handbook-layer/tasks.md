# Tasks: add-behavior-handbook-layer

Requirement key (specs/codebase-analysis/spec.md): R1 Behavior Handbook Artifact Schema · R2 Verified Evidence Locators · R3 Handbook Provenance and Freshness · R4 Progressive Disclosure Query Interface · R5 Handbook HTML Drill-Down View · R6 Behavior Seeding From Existing Artifacts.

## 1. Schema and Locator Foundation

- [ ] 1.1 Write tests for handbook schema validator — accepts well-formed L1/L2/L3 artifact; rejects dangling `member_nodes[]` / evidence node IDs; rejects over-budget L1/L2/L3 sections; requires `snapshot` block
  **Spec scenarios**: R1 (validate well-formed handbook; reject unknown graph nodes), R1 budget clauses per D5
  **Design decisions**: D1, D5
  **Dependencies**: None
  **Files**: `skills/refresh-architecture/scripts/tests/test_handbook_schema.py`, `skills/refresh-architecture/scripts/tests/fixtures/handbook/*.json`

- [ ] 1.2 Implement handbook schema module + validator CLI — JSON schema for `architecture.behaviors.json` (system_flows, behavior_units, unit_details, uncovered, snapshot, budget_estimate), cross-check node IDs against `architecture.graph.json`, token-budget caps
  **Dependencies**: 1.1
  **Files**: `skills/refresh-architecture/scripts/handbook_schema.py`

- [ ] 1.3 Write tests for locator resolver — `verified` on identical tree; `drifted` on edited span (normalized digest, formatting-only churn stays verified); `unresolvable` on deleted file/symbol; diagnostics findings shape
  **Spec scenarios**: R2 (all three scenarios)
  **Design decisions**: D3
  **Dependencies**: None
  **Files**: `skills/refresh-architecture/scripts/tests/test_verify_locators.py`

- [ ] 1.4 Implement locator resolver — resolve node ID via graph, load file span, compute normalized SHA-256, classify, emit findings for `architecture.diagnostics.json`; exit codes: 0 all verified/drifted, 1 any unresolvable
  **Dependencies**: 1.3
  **Files**: `skills/refresh-architecture/scripts/verify_locators.py`

## 2. Synthesis (deterministic seeding + LLM structuring)

- [ ] 2.1 Write tests for deterministic seeder — clusters root at entrypoints and expand along call/api_call/db_access edges; >50%-overlap merge; high-impact hub annotation; exception-pattern attachment; unabsorbed entrypoints land in `uncovered[]` with `no_traced_flow`
  **Spec scenarios**: R6 (disconnected endpoint gains a home; exception handling surfaces as exception path)
  **Design decisions**: D4
  **Dependencies**: None
  **Files**: `skills/refresh-architecture/scripts/tests/test_behavior_seeder.py`, `skills/refresh-architecture/scripts/tests/fixtures/handbook/seed_graph.json`

- [ ] 2.2 Implement deterministic seeder — pure function of graph + insights JSON, no LLM; emits `behavior_seeds.json` (clusters, hubs, exception attachments, uncovered)
  **Dependencies**: 2.1
  **Files**: `skills/refresh-architecture/scripts/behavior_seeder.py`

- [ ] 2.3 Write tests for synthesis assembler — LLM output merged onto fixed skeleton only (cannot add members); narrative sentences without resolvable locators rejected; snapshot records prompt hash + model ID; output passes 1.2 validator; failure preserves prior committed artifact (staged, not in-place)
  **Spec scenarios**: R1 (well-formed output), R3 (synthesis failure preserves last known-good)
  **Design decisions**: D2, D4
  **Dependencies**: 1.2
  **Files**: `skills/refresh-architecture/scripts/tests/test_synthesize_behaviors.py`

- [ ] 2.4 Implement `synthesize_behaviors.py` — orchestrates seeder → LLM structuring (pluggable backend; offline/fixture mode for tests) → locator stamping (content digests at synthesis revision) → validation → staged write
  **Dependencies**: 2.2, 2.3, 1.4
  **Files**: `skills/refresh-architecture/scripts/synthesize_behaviors.py`

## 3. Pipeline, Provenance, and Freshness Integration

- [ ] 3.1 Write tests for provenance + freshness coverage — handbook digest and input fingerprint recorded; absence of handbook = fresh-by-absence; byte-identical repeat refresh; `handbook_locator_drift` stale reason; unresolvable → check exits non-zero
  **Spec scenarios**: R3 (repeat refresh no diff), R2 (check fails on unresolvable)
  **Design decisions**: D2, D3; migration step 1 (graceful absence)
  **Dependencies**: 1.4
  **Files**: `skills/refresh-architecture/scripts/tests/test_handbook_provenance.py`

- [ ] 3.2 Integrate handbook verify stage into refresh/check + Make targets — `architecture-refresh` runs schema validation + locator verification on a committed handbook; `architecture-check` gains handbook drift reasons; new `architecture-handbook-synthesize` and `architecture-handbook-validate` targets
  **Dependencies**: 3.1, 2.4
  **Files**: `Makefile`, `skills/refresh-architecture/scripts/refresh_architecture.sh`, `skills/refresh-architecture/scripts/run_architecture.py`

- [ ] 3.3 First scoped synthesis run — generate, review, and commit `architecture.behaviors.json` for `agent-coordinator/` only; record uncovered-entrypoint count in synthesis summary; provenance updated
  **Spec scenarios**: R6 (uncovered accounting), R3 (provenance recorded)
  **Design decisions**: Migration steps 2–3
  **Dependencies**: 3.2
  **Files**: `docs/architecture-analysis/architecture.behaviors.json`, `docs/architecture-analysis/architecture.provenance.json`

## 4. Consumption Surfaces (query CLI + HTML)

- [ ] 4.1 Write tests for query CLI — L1 within budget; L2 cards filterable by files and free text; L3 returns single unit with per-entry verification marks including `drifted`; `--locate` ranks units with member evidence; JSON output shape
  **Spec scenarios**: R4 (planner localizes; L3 against drifted source)
  **Design decisions**: D5; BGPD sequence in design.md
  **Dependencies**: 1.2, 1.4
  **Files**: `skills/refresh-architecture/scripts/tests/test_handbook_query.py`

- [ ] 4.2 Implement `handbook_query.py` — level-at-a-time reads over the committed artifact; lexical + member-node ranking for `--locate`; inline locator verification on L3; token-budget accounting in output metadata
  **Dependencies**: 4.1
  **Files**: `skills/refresh-architecture/scripts/handbook_query.py`

- [ ] 4.3 Write tests for HTML generator — emits self-contained page from valid artifact; refuses invalid artifact (non-zero, no output, errors printed); JSON island embeds artifact; persona presets present in markup
  **Spec scenarios**: R5 (both scenarios)
  **Design decisions**: D6
  **Dependencies**: 1.2
  **Files**: `skills/refresh-architecture/scripts/tests/test_generate_handbook_html.py`

- [ ] 4.4 Implement `generate_handbook_html.py` + template — single-file drill-down (L1 flow → L2 cards → lazy L3 panes), persona entry presets via URL hash (`#l1`, `#l2?files=`, `#locate`, `#exceptions`), locator status badges; wire into `architecture-views`
  **Dependencies**: 4.3
  **Files**: `skills/refresh-architecture/scripts/reports/generate_handbook_html.py`, `skills/refresh-architecture/scripts/reports/templates/handbook.html.j2`, `Makefile`

## 5. Documentation and Context Wiring

- [ ] 5.1 Document the handbook layer — new "Layer 2.5 — Behavior Handbook" section in architecture-artifacts doc (artifacts, commands, freshness semantics, persona entry points); usage guidance for planning
  **Spec scenarios**: traces R1–R5 as reference documentation
  **Dependencies**: 3.2
  **Files**: `docs/architecture-artifacts.md`

- [ ] 5.2 Wire handbook into context-engineering packing guidance — add handbook levels as a named packing source with budget guidance (L1 for newcomer/orientation packs, `--locate` + L3 for worker dispatch)
  **Dependencies**: 4.2, 5.1
  **Files**: `skills/context-engineering/SKILL.md`

## 6. Evaluation

- [ ] 6.1 Write behavior-localization scenario pack — ~20 archived changes with still-existing touched files as ground truth; two arms (graph-only vs. handbook BGPD); excluded-scenario coverage reported
  **Spec scenarios**: R4 (locate) end-to-end; design D7 adoption gate
  **Design decisions**: D7
  **Dependencies**: 4.2, 3.3
  **Files**: `packages/agent-scenarios/scenarios/behavior-localization/*.yaml`, `packages/agent-scenarios/scenarios/behavior-localization/README.md`

- [ ] 6.2 Run eval and record results — localization precision/recall/F1 and tokens-to-localization per arm via the evaluation harness; write results into the validation report; record go/no-go for whole-repo expansion as a deferred task
  **Dependencies**: 6.1
  **Files**: `openspec/changes/add-behavior-handbook-layer/validation-report.md`, `openspec/changes/add-behavior-handbook-layer/deferred-tasks.md`
