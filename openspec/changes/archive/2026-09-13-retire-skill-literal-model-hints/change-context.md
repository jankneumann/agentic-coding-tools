# Change Context: retire-skill-literal-model-hints

<!-- 3-phase incremental artifact:
     Phase 1 (pre-implementation): Req ID, Spec Source, Description, Contract Ref, Design Decision,
       Test(s) planned. Files Changed = "---". Evidence = "---".
     Phase 2 (implementation): Files Changed populated. Tests pass (GREEN).
     Phase 3 (validation): Evidence filled with "pass <SHA>", "fail <SHA>", or "deferred <reason>". -->

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-archetypes.1 | specs/agent-archetypes/spec.md — Skill Model Hint Integration | Skills author archetype/tier vocabulary; resolve to harness model id at dispatch (`model=<var>` or omit); no raw model versions as policy | --- | D1, D5 | skills/validate-packages/scripts/tests/test_skill_model_hints.py; skills/implement-feature/SKILL.md; skills/iterate-on-implementation/SKILL.md; skills/fix-scrub/SKILL.md; skills/cite-requirements/SKILL.md; skills/autopilot/SKILL.md; openspec/changes/retire-skill-literal-model-hints/specs/agent-archetypes/spec.md | test_skill_model_hints.py (presence + resolve patterns) | pass 02a98ded |
| agent-archetypes.1.s1 | Scenario: Plan-feature resolves analyst before Explore tasks | plan-feature resolves analyst; Task uses `model=<var>` or omits; no hardcoded raw model id | --- | D1 | skills/validate-packages/scripts/tests/test_skill_model_hints.py | test_plan_feature_resolves_analyst_archetype | pass 02a98ded |
| agent-archetypes.1.s2 | Scenario: Implement-feature resolves runner for quality checks | implement-feature resolves runner; no `model="haiku"` policy pin | --- | D1 | skills/validate-packages/scripts/tests/test_skill_model_hints.py; skills/implement-feature/SKILL.md | test_implement_feature_resolves_runner_archetype | pass 02a98ded |
| agent-archetypes.1.s3 | Scenario: Skill Task() call missing model parameter | Fenced Task( without model= fails with file+line | --- | D3 | skills/validate-packages/scripts/tests/test_skill_model_hints.py | test_all_task_calls_have_model | pass 02a98ded |
| agent-archetypes.1.s4 | Scenario: String-literal model pins are rejected | `model="…"` and CLI `-m <literal>` fail; `model=<var>` OK | --- | D3 | skills/validate-packages/scripts/tests/test_skill_model_hints.py | TestLiteralRejectionUnit; TestSkillInventoryScans; test_task_model_values_are_not_string_literals | pass 02a98ded |
| skill-workflow.1 | specs/skill-workflow/spec.md — Skill-Authored Model Vocabulary | Skills treat archetypes.yaml as vocabulary source; dispatch examples resolve at runtime | --- | D1, D5 | skills/cite-requirements/SKILL.md; skills/plan-roadmap/SKILL.md; skills/plan-roadmap/templates/generation-prompt.md; skills/implement-feature/SKILL.md; skills/iterate-on-implementation/SKILL.md; skills/fix-scrub/SKILL.md; skills/autopilot/SKILL.md; openspec/changes/retire-skill-literal-model-hints/specs/skill-workflow/spec.md | guard + skill body rewrites | pass 02a98ded |
| skill-workflow.1.s1 | Scenario: Dispatch examples do not hardcode model versions | Fenced harness dispatch selection policy is archetype/tier resolve, not string literal | --- | D1, D3 | skills/validate-packages/scripts/tests/test_skill_model_hints.py; skills/cite-requirements/SKILL.md | literal rejection tests + cite-requirements rewrite | pass 02a98ded |
| skill-workflow.1.s2 | Scenario: Narrative defaults use tier or vendor-role language | Prose defaults name archetype/tier/vendor role, not concrete model version | --- | D1, D4 | skills/plan-roadmap/SKILL.md; skills/plan-roadmap/templates/generation-prompt.md; skills/validate-packages/scripts/tests/test_skill_model_hints.py | test_plan_roadmap_narrative_avoids_version_pins | pass 02a98ded |
| skill-workflow.1.s3 | Scenario: Dual-vendor annotation resolves two economy tiers | cite-requirements resolves economy for two providers; no hardcoded model ids as policy | --- | D2 | skills/cite-requirements/SKILL.md | cite-requirements SKILL rewrite + Agent/CLI inventory scans | pass 02a98ded |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 — Authored vocabulary vs dispatch payload | Harnesses need model ids; skills must not author them as policy | Skill prose uses archetype/tier; dispatch uses resolved `model=<var>` | Approach A — no harness `archetype=` needed |
| D2 — Dual cheap-tier resolution | cite-requirements needs vendor diversity at economy cost | Resolve economy for two providers, then dispatch | Keeps dual-vendor without pinning roster ids |
| D3 — Harden test_skill_model_hints in place | Ban literals; keep resolve-pattern green (0 FP) | Replace VALID_MODELS allowlist; add Agent/CLI literal checks | Smallest durable CI change |
| D4 — Comments and escape hatches | Illustrative sonnet/opus comments + override examples | Rewrite comments to tier language; label override as escape hatch | Stops comment drift without removing operator escape |
| D5 — Spec end-state | Phase 1 literals no longer valid | Delta specs already authored at plan time | Lock-in via openspec validate --strict |
| D6 — Stay off concurrent roster surfaces | Avoid conflict with adaptive router / frontier tier | Do not edit archetypes.yaml or review_dispatcher | Scope discipline |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 9/9
- **Tests mapped**: 9 requirements have at least one test
- **Evidence collected**: 9/9 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
