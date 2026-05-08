# Tasks — Factory Missions Architecture Alignment

## Phase 0: Contracts (wp-contracts)

- [x] 0.1 Add `behavioral_failure` to the `type` enum in `openspec/schemas/review-findings.schema.json`
  **Spec scenarios**: evaluation-framework: "behavioral_failure type validates against schema"
  **Contracts**: `openspec/schemas/review-findings.schema.json` (modify enum)
  **Design decisions**: D3
  **Dependencies**: None

- [x] 0.2 Create `contracts/frontend-descriptor.schema.json` with required fields `base_url`, `auth_flow`, `selectors`, `browsers`
  **Spec scenarios**: gen-eval-framework: "Sample frontend exercise validates the full path", "Browser matrix executes all configured browsers"
  **Contracts**: `contracts/frontend-descriptor.schema.json` (new)
  **Design decisions**: D2, D6
  **Dependencies**: None

- [x] 0.3 Create `contracts/agents-policy-schema.json` for `policies.vendor_diversity` block
  **Spec scenarios**: agent-archetypes: "Worker and validator dispatch to different vendors", "Policy disabled allows same-vendor dispatch"
  **Contracts**: `contracts/agents-policy-schema.json` (new)
  **Design decisions**: D4
  **Dependencies**: None

- [x] 0.4 Create `contracts/gen-eval-cli.md` documenting `--openspec-change` flag and the `source.openspec_scenario` metadata field
  **Spec scenarios**: gen-eval-framework: "OpenSpec scenarios augment cli-augmented prompt"
  **Contracts**: `contracts/gen-eval-cli.md` (new)
  **Dependencies**: None

- [x] 0.5 Create `contracts/findings-vendor-source.md` documenting the `findings-<vendor>.json` naming convention and the consensus synthesizer's vendor-source input format
  **Spec scenarios**: evaluation-framework: "Synthesizer merges gen-eval and reviewer findings"
  **Contracts**: `contracts/findings-vendor-source.md` (new)
  **Dependencies**: None

## Phase 1: WP1 — README Attention Bottleneck (wp1-readme)

- [x] 1.1 Write a markdown lint test or doc-content assertion for `README.md` that fails if (a) "human attention" appears later than line 10 OR (b) no "Three Roles" section exists OR (c) any of `/plan-feature`, `/implement-feature`, `/parallel-review-plan`, `/parallel-review-implementation`, `/gen-eval` is missing from the role mapping
  **Spec scenarios**: skill-workflow: "README opener leads with attention bottleneck", "Each skill mapped to exactly one role"
  **Dependencies**: None

- [x] 1.2 Rewrite `README.md` opener with attention-bottleneck framing; add Three-Roles section mapping each skill onto Orchestrator/Workers/Validators
  **Spec scenarios**: skill-workflow: "README opener leads with attention bottleneck", "Each skill mapped to exactly one role"
  **Design decisions**: D1
  **Dependencies**: 1.1

## Phase 2: WP2 — Docs Vocabulary (wp2-docs-vocabulary)

- [x] 2.1 Write a doc-content assertion test for `docs/parallel-agentic-development.md` that fails if (a) no "Five-Tier" section exists OR (b) the section omits any of the 5 patterns OR (c) no "Scope-Isolated Parallelism" section exists OR (d) the Scope-Isolated section does not name the Factory Missions talk
  **Spec scenarios**: skill-workflow: "Taxonomy table present and complete", "Section names the talk and the divergence"
  **Dependencies**: None

- [x] 2.2 Write a doc-content assertion for `docs/lessons-learned.md` and `docs/skills-workflow.md` that fails if (a) no "Self-Healing at Milestone Boundaries" heading exists OR (b) no "Mission" glossary entry exists
  **Spec scenarios**: skill-workflow: "New heading anchors existing content", "Glossary entry exists and is searchable"
  **Dependencies**: None

- [x] 2.3 Add "Five-Tier Multi-Agent Taxonomy" section to `docs/parallel-agentic-development.md` (additive append; no edits to existing sections)
  **Spec scenarios**: skill-workflow: "Taxonomy table present and complete"
  **Design decisions**: D1
  **Dependencies**: 2.1

- [x] 2.4 Add "Scope-Isolated Parallelism" section engaging the talk's diagnosis directly
  **Spec scenarios**: skill-workflow: "Section names the talk and the divergence"
  **Dependencies**: 2.1

- [x] 2.5 Add "Self-Healing at Milestone Boundaries" heading to `docs/lessons-learned.md` (cross-reference existing escalation_handler.py docs without duplicating)
  **Spec scenarios**: skill-workflow: "New heading anchors existing content"
  **Dependencies**: 2.2

- [x] 2.6 Add "Mission" glossary entry to `docs/skills-workflow.md`
  **Spec scenarios**: skill-workflow: "Glossary entry exists and is searchable"
  **Dependencies**: 2.2

## Phase 3: WP3 — Gen-Eval OpenSpec Seeds (wp3-gen-eval-openspec-seeds)

- [x] 3.1 Write unit tests for OpenSpec scenario parser (parsing Requirement + Scenario blocks from spec.md, preserving file:line)
  **Spec scenarios**: gen-eval-framework: "OpenSpec scenarios augment cli-augmented prompt"
  **Contracts**: `contracts/gen-eval-cli.md`
  **Dependencies**: 0.4

- [x] 3.2 Write integration test for `--openspec-change <id>` flag end-to-end against a fixture change
  **Spec scenarios**: gen-eval-framework: "OpenSpec scenarios augment cli-augmented prompt", "Missing OpenSpec change degrades to descriptor-only", "Backward compatibility without flag"
  **Dependencies**: 3.1

- [x] 3.3 Implement OpenSpec scenario parser in `agent-coordinator/evaluation/gen_eval/openspec_seed.py` (new module)
  **Spec scenarios**: gen-eval-framework: "OpenSpec scenarios augment cli-augmented prompt"
  **Dependencies**: 3.1

- [x] 3.4 Wire `--openspec-change` flag into `agent-coordinator/evaluation/gen_eval/__main__.py` argparser (insertion point: lines 14-96)
  **Spec scenarios**: gen-eval-framework: "Backward compatibility without flag"
  **Dependencies**: 3.3

- [x] 3.5 Extend cli-augmented prompt builder to include OpenSpec scenarios as constraints; preserve `source.openspec_scenario` field on emitted Scenario objects
  **Spec scenarios**: gen-eval-framework: "OpenSpec scenarios augment cli-augmented prompt"
  **Dependencies**: 3.3, 3.4

- [x] 3.6 Update `skills/gen-eval/SKILL.md` to document the new flag
  **Dependencies**: 3.5

## Phase 4: WP4 — Validate-Feature Gen-Eval Cli-Augmented (wp4-validate-gen-eval-extend)

- [x] 4.1 Write integration test for `validate-feature --phase gen-eval` mode-selection branching: descriptor-only → template-only; descriptor + change → cli-augmented; no descriptor → skip
  **Spec scenarios**: evaluation-framework: "Both artifacts present → cli-augmented", "Descriptor only → template-only fallback", "No descriptor → phase skipped"
  **Contracts**: `contracts/gen-eval-cli.md`
  **Dependencies**: 0.4, 3.5

- [x] 4.2 Write test for cli-augmented failure non-blocking semantics
  **Spec scenarios**: evaluation-framework: "cli-augmented failure does not halt pipeline"
  **Dependencies**: 4.1

- [x] 4.3 Modify `skills/validate-feature/SKILL.md` lines 260-307 to wrap the existing template-only invocation in a mode-selection conditional. Concretely: replace the `if [ -z "$GENEVAL_DESCRIPTORS" ]` / `else` block at lines 271-307 with an outer conditional that branches on whether `openspec/changes/<change-id>/specs/` exists, calling cli-augmented mode in the new branch and the existing template-only block in the fallback branch (preserving lines 274-306 as the fallback path per D5).
  **Spec scenarios**: evaluation-framework: "Both artifacts present → cli-augmented", "Descriptor only → template-only fallback"
  **Design decisions**: D5
  **Dependencies**: 4.1, 4.2

- [x] 4.4 Add mode-selection logging per spec ("gen-eval: cli-augmented mode (descriptor + OpenSpec change present)" etc.)
  **Spec scenarios**: evaluation-framework: "Both artifacts present → cli-augmented"
  **Dependencies**: 4.3

## Phase 5: WP5 — Consensus Gen-Eval Vendor (wp5-consensus-gen-eval)

- [x] 5.1 Write unit test for `consensus_synthesizer.py` accepting `findings-gen-eval.json` as a vendor-source input, merging with reviewer findings, ranking uniformly
  **Spec scenarios**: evaluation-framework: "Synthesizer merges gen-eval and reviewer findings"
  **Contracts**: `contracts/findings-vendor-source.md`, `openspec/schemas/review-findings.schema.json`
  **Dependencies**: 0.1, 0.5

- [x] 5.2 Write test for missing-findings-file graceful handling
  **Spec scenarios**: evaluation-framework: "Missing gen-eval findings file is not an error"
  **Dependencies**: 5.1

- [x] 5.3 Write test that gen-eval emits `findings-gen-eval.json` conforming to schema (with `behavioral_failure` type and OpenSpec source-location pointer when applicable)
  **Spec scenarios**: gen-eval-framework: "Findings file produced and schema-valid", "OpenSpec-sourced finding points back to spec"
  **Dependencies**: 0.1, 3.5

- [x] 5.4 Implement `findings-gen-eval.json` emitter in gen-eval's report-format=json path
  **Spec scenarios**: gen-eval-framework: "Findings file produced and schema-valid", "OpenSpec-sourced finding points back to spec"
  **Dependencies**: 5.3

- [x] 5.5 Extend `skills/parallel-infrastructure/scripts/consensus_synthesizer.py` lines 200-258 to add gen-eval as a vendor source (additive — do not modify existing reviewer-finding merge logic per proposal's conflict-avoidance stance)
  **Spec scenarios**: evaluation-framework: "Synthesizer merges gen-eval and reviewer findings", "Missing gen-eval findings file is not an error"
  **Dependencies**: 5.1, 5.2, 5.4

## Phase 6: WP6 — Worker Vendor Rotation (wp6-worker-vendor-rotation)

- [x] 6.1 Write unit test for vendor-diversity dispatcher logic: worker-validator pair on same change excludes worker's vendor when selecting validator
  **Spec scenarios**: agent-archetypes: "Worker and validator dispatch to different vendors", "Vendor exhaustion within a session is tracked"
  **Contracts**: `contracts/agents-policy-schema.json`
  **Dependencies**: 0.3

- [x] 6.2 Write test for single-vendor fallback (warn-and-continue, no block)
  **Spec scenarios**: agent-archetypes: "Single-vendor environment falls back gracefully"
  **Dependencies**: 6.1

- [x] 6.3 Write test for policy-disabled mode (config opt-out)
  **Spec scenarios**: agent-archetypes: "Policy disabled allows same-vendor dispatch"
  **Dependencies**: 6.1

- [x] 6.4 Add `policies.vendor_diversity` block to `agent-coordinator/agents.yaml` (default: enforce_for: [worker_vs_validator], fallback: warn_and_continue)
  **Spec scenarios**: agent-archetypes: "Worker and validator dispatch to different vendors"
  **Design decisions**: D4
  **Dependencies**: 6.1

- [x] 6.5 Implement vendor-exclusion logic in `skills/parallel-infrastructure/scripts/review_dispatcher.py` (insertion point: discover_reviewers, lines 998-1063, extending existing exclude_vendor pattern)
  **Spec scenarios**: agent-archetypes: "Worker and validator dispatch to different vendors", "Single-vendor environment falls back gracefully"
  **Dependencies**: 6.1, 6.2, 6.4

- [x] 6.6 Implement worker-side vendor selection in `skills/implement-feature/` so workers track their vendor in change session state
  **Spec scenarios**: agent-archetypes: "Vendor exhaustion within a session is tracked"
  **Dependencies**: 6.5

- [x] 6.7 Add a leading comment block to `agent-coordinator/agents.yaml` (above the new `policies` block) explaining the vendor-diversity rationale (avoid shared training-data biases). Documenting inline in agents.yaml rather than docs/skills-workflow.md keeps WP6 scope-isolated from WP2 and gives operators reading the policy config immediate context.
  **Dependencies**: 6.5

## Phase 7: WP7 — Playwright Validator (wp7-playwright-validator)

- [ ] 7.1 Write contract test for `frontend-descriptor.schema.json`: valid descriptors validate, invalid ones fail (missing base_url, invalid browser names, malformed selectors)
  **Spec scenarios**: gen-eval-framework: "Sample frontend exercise validates the full path", "Browser matrix executes all configured browsers"
  **Contracts**: `contracts/frontend-descriptor.schema.json`
  **Dependencies**: 0.2

- [ ] 7.2 Write integration test for sample-frontend Playwright run (start http.server, run validator, assert findings-playwright.json shape)
  **Spec scenarios**: gen-eval-framework: "Sample frontend exercise validates the full path"
  **Design decisions**: D2, D6
  **Dependencies**: 0.1, 0.2, 5.4

- [ ] 7.3 Write test for browser-matrix execution (chromium + firefox both run, both produce findings)
  **Spec scenarios**: gen-eval-framework: "Browser matrix executes all configured browsers"
  **Dependencies**: 7.2

- [ ] 7.4 Write test for missing-Playwright-CLI degradation (exit 127, no findings file)
  **Spec scenarios**: gen-eval-framework: "Missing Playwright CLI degrades cleanly"
  **Dependencies**: 7.2

- [ ] 7.5 Create sample frontend at `evaluation/gen_eval/fixtures/sample-frontend/index.html` (static HTML + inline JS, no framework per D6)
  **Design decisions**: D6
  **Dependencies**: None

- [ ] 7.6 Create sample frontend descriptor at `evaluation/gen_eval/descriptors/sample-frontend.yaml` conforming to frontend-descriptor schema
  **Contracts**: `contracts/frontend-descriptor.schema.json`
  **Dependencies**: 0.2, 7.5

- [ ] 7.7 Create sample OpenSpec scenarios for the sample frontend (in fixtures/sample-frontend/specs/)
  **Dependencies**: 7.5

- [ ] 7.8 Create `skills/playwright-validator/SKILL.md` with command spec, dependency check (npx playwright install), and pipeline orchestration. Authored AFTER the runner is implemented (7.10) so the SKILL.md documents real behavior, not an interface skeleton.
  **Spec scenarios**: gen-eval-framework: "Missing Playwright CLI degrades cleanly"
  **Design decisions**: D2
  **Dependencies**: 7.1, 7.10

- [ ] 7.9 Implement Playwright-test-script generator that consumes OpenSpec scenarios + frontend descriptor → produces `.spec.ts` test files
  **Spec scenarios**: gen-eval-framework: "Sample frontend exercise validates the full path"
  **Dependencies**: 7.8

- [ ] 7.10 Implement Playwright runner: starts local http.server for static descriptors, executes `npx playwright test --reporter=json`, parses results
  **Spec scenarios**: gen-eval-framework: "Sample frontend exercise validates the full path", "Browser matrix executes all configured browsers"
  **Dependencies**: 7.9

- [ ] 7.11 Implement findings-emission shim that converts Playwright JSON output to `findings-gen-eval.json` (or `findings-playwright.json`) shape per schema
  **Spec scenarios**: gen-eval-framework: "Sample frontend exercise validates the full path"
  **Contracts**: `openspec/schemas/review-findings.schema.json`
  **Dependencies**: 7.10, 0.1

- [ ] 7.12 Hook playwright-validator into `validate-feature --phase gen-eval` so the phase auto-detects frontend descriptors and dispatches to the playwright skill
  **Dependencies**: 4.3, 7.11

## Phase 8: Integration (wp-integration)

- [ ] 8.1 Run full `validate-feature` end-to-end on the sample frontend: deploy → smoke → gen-eval (Playwright path) → security → e2e
  **Dependencies**: 7.12

- [ ] 8.2 Verify `consensus_synthesizer.py` produces a single ranked finding list combining scrutiny + behavioral findings on a synthetic test change
  **Spec scenarios**: evaluation-framework: "Synthesizer merges gen-eval and reviewer findings"
  **Dependencies**: 5.5

- [ ] 8.3 Verify `harness-engineering-features` rebases cleanly: cherry-pick its open commits onto this branch's HEAD and confirm no conflicts in `docs/lessons-learned.md`, `docs/parallel-agentic-development.md`, `consensus_synthesizer.py`, or `validate-feature/SKILL.md`
  **Dependencies**: 2.6, 5.5, 4.4

- [ ] 8.4 Run `openspec validate factory-missions-architecture-alignment --strict` and fix any spec-format issues
  **Dependencies**: 8.1, 8.2

- [ ] 8.5 Run `validate_work_packages.py` and `parallel_zones.py --validate-packages` to confirm no scope overlap
  **Dependencies**: All implementation tasks

- [ ] 8.6 Update `skills/install.sh` consumers if any new skill (`skills/playwright-validator/`) needs rsync targets
  **Dependencies**: 7.8
