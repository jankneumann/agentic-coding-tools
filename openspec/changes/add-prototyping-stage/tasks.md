# Tasks — add-prototyping-stage

Tasks are ordered TDD-first within each phase: test tasks precede implementation tasks they verify. Phase 1 (contracts) comes first because downstream packages depend on the `VariantDescriptor` schema.

## Phase 1 — Contracts (wp-contracts)

- [ ] 1.1 Write JSON Schema validation tests for `VariantDescriptor`
  **Spec scenarios**: skill-workflow.VariantDescriptorSchema.published
  **Contracts**: contracts/schemas/variant-descriptor.schema.json
  **Design decisions**: D9
  **Dependencies**: None

- [ ] 1.2 Author `contracts/schemas/variant-descriptor.schema.json` — fields per D9
  **Dependencies**: 1.1

- [ ] 1.3 Write `contracts/README.md` documenting evaluated contract sub-types (no OpenAPI/DB/event contracts apply to this skill-definition change; VariantDescriptor is the only contract)
  **Dependencies**: 1.2

- [ ] 1.4 Add synthesis-plan schema stub (`contracts/schemas/synthesis-plan.schema.json`) describing the output of `synthesize_variants()`
  **Spec scenarios**: skill-workflow.VariantDescriptorSchema.synthesis_plan
  **Design decisions**: D9
  **Dependencies**: 1.2

## Phase 2 — Worktree Extension (wp-worktree)

- [ ] 2.1 Write tests for `worktree.py setup --branch-prefix prototype` composition with `--agent-id`
  **Spec scenarios**: skill-workflow.PrototypeWorktreeSupport.branch-creation, branch-override-composition
  **Design decisions**: D4
  **Dependencies**: None

- [ ] 2.2 Write tests for prototype worktree pinning (survives 24h GC timer)
  **Spec scenarios**: skill-workflow.PrototypeWorktreeSupport.worktree-pin
  **Design decisions**: D4
  **Dependencies**: None

- [ ] 2.3 Add `--branch-prefix` flag to `skills/worktree/scripts/worktree.py` setup subcommand
  **Dependencies**: 2.1

- [ ] 2.4 Extend `resolve_branch` to honor `--branch-prefix prototype` alongside `OPENSPEC_BRANCH_OVERRIDE` precedence
  **Dependencies**: 2.3

- [ ] 2.5 Auto-pin worktrees created with `--branch-prefix prototype`
  **Dependencies**: 2.2, 2.3

## Phase 3 — Parallel Infrastructure Schema (wp-parallel-infra)

- [ ] 3.1 Write unit tests for `synthesize_variants(descriptors) -> synthesis_plan`
  **Spec scenarios**: skill-workflow.VariantDescriptorSchema.synthesis_plan
  **Contracts**: contracts/schemas/variant-descriptor.schema.json, contracts/schemas/synthesis-plan.schema.json
  **Design decisions**: D9
  **Dependencies**: 1.2, 1.4

- [ ] 3.2 Write test covering variant grouping by aspect (data_model, api, tests, layout)
  **Spec scenarios**: skill-workflow.PrototypeFindingsArtifact.human-pick-and-choose
  **Design decisions**: D7, D9
  **Dependencies**: None

- [ ] 3.3 Add `VariantDescriptor` dataclass/TypedDict in `skills/parallel-infrastructure/scripts/variant_descriptor.py`
  **Dependencies**: 3.1, 3.2

- [ ] 3.4 Implement `synthesize_variants()` — produces synthesis_plan from list of descriptors
  **Dependencies**: 3.3

## Phase 4 — Prototype Feature Skill (wp-prototype-skill)

- [ ] 4.1 Write tests for variant dispatch — count validation, angle-count matching, out-of-bounds rejection
  **Spec scenarios**: skill-workflow.PrototypeFeatureSkill.default-variant-dispatch, custom-variant-count-and-angles, variant-count-out-of-bounds
  **Design decisions**: D2, D5
  **Dependencies**: None

- [ ] 4.2 Write tests for isolated worktree per variant — no cross-branch writes
  **Spec scenarios**: skill-workflow.PrototypeFeatureSkill.isolated-worktree-per-variant
  **Design decisions**: D4
  **Dependencies**: 2.3

- [ ] 4.3 Write tests for vendor diversity — sufficient, insufficient, recorded policy
  **Spec scenarios**: skill-workflow.VendorDiversityPolicy.sufficient, insufficient, recorded
  **Design decisions**: D3
  **Dependencies**: None

- [ ] 4.4 Write tests for scoring — smoke/spec phases invoked, heavy phases not invoked, skeleton-deploy failure surfaces
  **Spec scenarios**: skill-workflow.VariantScoring.smoke-and-spec, skeleton-fails-to-deploy
  **Design decisions**: D6
  **Dependencies**: None

- [ ] 4.5 Write tests for `prototype-findings.md` production — schema conformance, human-picks recorded
  **Spec scenarios**: skill-workflow.PrototypeFindingsArtifact.findings-artifact-produced, human-pick-and-choose
  **Contracts**: contracts/schemas/variant-descriptor.schema.json
  **Design decisions**: D7
  **Dependencies**: 1.2, 3.3

- [ ] 4.6 Create `skills/prototype-feature/SKILL.md` — full skill definition with steps, gates, inputs, outputs
  **Dependencies**: 4.1, 4.2, 4.3, 4.4, 4.5

- [ ] 4.7 Create `skills/prototype-feature/scripts/dispatch_variants.py` — worktree setup, Task() agent dispatch, vendor-diversity policy
  **Dependencies**: 4.6, 2.3, 3.3

- [ ] 4.8 Create `skills/prototype-feature/scripts/collect_outcomes.py` — run `/validate-feature --phase smoke,spec` per variant; aggregate VariantDescriptors
  **Dependencies**: 4.7

- [ ] 4.9 Create `skills/prototype-feature/angles.yaml` — default angle prompts per D5
  **Dependencies**: 4.6

## Phase 5 — Iterate-on-Plan Extension (wp-iterate-convergence)

- [ ] 5.1 Write tests for `--prototype-context` flag parsing and context loading
  **Spec scenarios**: skill-workflow.ConvergenceViaIterateOnPlan.convergence-mode-activated
  **Design decisions**: D1
  **Dependencies**: 4.8

- [ ] 5.2 Write tests that existing iterate-on-plan behavior is unchanged when flag absent
  **Spec scenarios**: skill-workflow.ConvergenceViaIterateOnPlan.convergence-without-context
  **Design decisions**: D1
  **Dependencies**: None

- [ ] 5.3 Write tests for missing-artifact fail-fast path
  **Spec scenarios**: skill-workflow.ConvergenceViaIterateOnPlan.missing-prototype-artifacts
  **Dependencies**: None

- [ ] 5.4 Write tests for `workflow.prototype-recommended` threshold (emits at ≥3 high clarity+feasibility findings; silent below)
  **Spec scenarios**: skill-workflow.PrototypeRecommendationSignal.threshold-met, threshold-not-met, advisory-only
  **Design decisions**: D8
  **Dependencies**: None

- [ ] 5.5 Extend `skills/iterate-on-plan/SKILL.md` — document convergence mode step, `convergence.*` finding types, prototype-recommended signal
  **Dependencies**: 5.1, 5.2, 5.3, 5.4

- [ ] 5.6 Add prototype-context loader to `skills/iterate-on-plan/scripts/` — reads `prototype-findings.md`, variant diffs, validation reports
  **Dependencies**: 5.5, 4.8

- [ ] 5.7 Add `convergence.*` finding types to iterate-on-plan's finding taxonomy
  **Dependencies**: 5.6

- [ ] 5.8 Add `workflow.prototype-recommended` advisory finding emitter
  **Dependencies**: 5.5

## Phase 6 — Cleanup Extension (wp-cleanup)

- [ ] 6.1 Write tests for prototype branch cleanup — local and remote deletion alongside feature branch
  **Spec scenarios**: skill-workflow.CleanupIncludesPrototypeBranches.prototype-cleanup-on-merge, stale-state-without-findings
  **Design decisions**: D4
  **Dependencies**: 2.3

- [ ] 6.2 Extend `skills/cleanup-feature/SKILL.md` — prototype cleanup step before archive
  **Dependencies**: 6.1

## Phase 7 — Documentation (wp-docs)

- [ ] 7.1 Write doc-lint test verifying `/prototype-feature` appears in skills-workflow flow diagram and has a "Divergence is first-class" principle section
  **Spec scenarios**: skill-workflow.WorkflowDocumentationUpdates.workflow-doc-describes-prototype-stage
  **Dependencies**: None

- [ ] 7.2 Write doc-lint test verifying CLAUDE.md workflow diagram references `/prototype-feature` and `/iterate-on-plan --prototype-context`
  **Spec scenarios**: skill-workflow.WorkflowDocumentationUpdates.claude-md-workflow-diagram-updated
  **Dependencies**: None

- [ ] 7.3 Update `docs/skills-workflow.md` — add prototype stage to flow diagram; add "Divergence is first-class on both sides of the approval gate" under Design Principles
  **Dependencies**: 7.1

- [ ] 7.4 Update `CLAUDE.md` — add `/prototype-feature` to the workflow section; add `--prototype-context` note under `/iterate-on-plan`
  **Dependencies**: 7.2

- [ ] 7.5 Add a short example to `docs/skills-workflow.md` showing a full invocation: plan → prototype → iterate-on-plan (convergence) → implement
  **Dependencies**: 7.3

## Phase 8 — Integration (wp-integration)

- [ ] 8.1 End-to-end integration test: small synthetic change runs `/plan-feature` → `/prototype-feature` (3 variants, single vendor) → `/iterate-on-plan --prototype-context` → verify `design.md` and `tasks.md` were refined with `convergence.*` findings
  **Spec scenarios**: skill-workflow.ConvergenceViaIterateOnPlan.convergence-mode-activated + scoring + findings scenarios
  **Design decisions**: D1, D3, D6, D7
  **Dependencies**: 4.8, 5.7, 5.8

- [ ] 8.2 Install skills to runtime mirrors (`.claude/skills/`, `.agents/skills/`) via `bash skills/install.sh --mode rsync --agents claude,agents --deps none --python-tools none`
  **Dependencies**: 4.6, 5.5, 6.2

- [ ] 8.3 Run full test suite (`skills/.venv/bin/python -m pytest skills/tests/`) and `openspec validate add-prototyping-stage --strict`
  **Dependencies**: all prior

- [ ] 8.4 Verify merge-log phase captures prototype-stage artifacts when present
  **Dependencies**: 8.1
