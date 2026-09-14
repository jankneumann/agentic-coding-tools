# Tasks: retire-skill-literal-model-hints

TDD order within each WP: tests before implementation. Approach A (Gate 1).

## WP1 — CI guard (D3)

- [x] 1.1 Write failing tests: string-literal `model="…"` in fenced Task() is
  invalid; `model=<variable>` remains valid; `{opus,sonnet,haiku}` allowlist
  removed (S)
  **Spec scenarios**: agent-archetypes — String-literal model pins are rejected;
  Skill Task() missing model parameter
  **Design decisions**: D3
  **Dependencies**: None
  **Files**: `skills/validate-packages/scripts/tests/test_skill_model_hints.py`

- [x] 1.2 Write failing tests: `Agent(..., model="…")` string literals in
  fenced dispatch examples fail with file+line (S)
  **Spec scenarios**: agent-archetypes — String-literal model pins are rejected
  **Design decisions**: D3
  **Dependencies**: None
  **Files**: `skills/validate-packages/scripts/tests/test_skill_model_hints.py`

- [x] 1.3 Write failing tests: vendor CLI `-m <literal>` in fenced dispatch
  examples fail with file+line (S)
  **Spec scenarios**: skill-workflow — Dispatch examples do not hardcode model
  versions
  **Design decisions**: D3
  **Dependencies**: None
  **Files**: `skills/validate-packages/scripts/tests/test_skill_model_hints.py`

- [x] 1.4 Implement guard changes so 1.1–1.3 pass while lifecycle
  resolve-pattern skills stay green (false-positive target: 0) (M)
  **Dependencies**: 1.1, 1.2, 1.3
  **Files**: `skills/validate-packages/scripts/tests/test_skill_model_hints.py`

- [x] Checkpoint: run `skills/.venv/bin/python -m pytest skills/validate-packages/scripts/tests/test_skill_model_hints.py -q`, review diff, verify scope

## WP2 — Skill authored vocabulary (D1, D2, D4)

- [x] 2.1 Rewrite `cite-requirements` dual-annotation to resolve two
  economy-tier models for distinct providers (M)
  **Spec scenarios**: skill-workflow — Dual-vendor annotation resolves two
  economy tiers
  **Design decisions**: D1, D2
  **Dependencies**: 1.4
  **Files**: `skills/cite-requirements/SKILL.md`

- [x] 2.2 Remove hardcoded `haiku` / `gpt-5.6-luna` selection-policy text from
  cite-requirements examples and sample JSON labels where they encode policy (S)
  **Spec scenarios**: skill-workflow — Dispatch examples do not hardcode model
  versions
  **Design decisions**: D1, D2
  **Dependencies**: 2.1
  **Files**: `skills/cite-requirements/SKILL.md`

- [x] 2.3 Replace plan-roadmap narrative default model versions with
  archetype/tier language in SKILL.md (S)
  **Spec scenarios**: skill-workflow — Narrative defaults use tier or
  vendor-role language
  **Design decisions**: D1
  **Dependencies**: 1.4
  **Files**: `skills/plan-roadmap/SKILL.md`

- [x] 2.4 Replace plan-roadmap generation-prompt template narrative model
  versions with archetype/tier language (S)
  **Spec scenarios**: skill-workflow — Narrative defaults use tier or
  vendor-role language
  **Design decisions**: D1
  **Dependencies**: 1.4
  **Files**: `skills/plan-roadmap/templates/generation-prompt.md`

- [x] 2.5 Rewrite lifecycle illustrative comments that name sonnet/opus to
  archetype/tier language (S)
  **Spec scenarios**: agent-archetypes — Plan-feature / Implement-feature
  resolve scenarios
  **Design decisions**: D4
  **Dependencies**: 1.4
  **Files**: `skills/implement-feature/SKILL.md`,
  `skills/iterate-on-implementation/SKILL.md`, `skills/fix-scrub/SKILL.md`

- [x] 2.6 Label AUTOPILOT model-override examples as explicit escape hatches
  that bypass YAML selection (XS)
  **Spec scenarios**: skill-workflow — Dispatch examples do not hardcode
  model versions (escape-hatch exception)
  **Design decisions**: D4
  **Dependencies**: 1.4
  **Files**: `skills/autopilot/SKILL.md`

- [x] Checkpoint: re-run guard tests + spot-check inventory grep for raw
  model-version policy pins in edited skills; review diff; verify scope

## WP3 — Spec lock-in verify (D5)

- [ ] 3.1 Confirm delta specs match implementation and
  `openspec validate retire-skill-literal-model-hints --strict` passes (S)
  **Spec scenarios**: all scenarios in this change’s spec deltas
  **Design decisions**: D5
  **Dependencies**: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
  **Files**: `openspec/changes/retire-skill-literal-model-hints/specs/**`

- [ ] Checkpoint: run tests, review full diff vs main, verify write scope
