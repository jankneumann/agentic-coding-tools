# Tasks — add-skillify-and-resolver-audit

## Phase 1 — Resolver audit (foundation; lands first to expose existing dark skills)

- [ ] 1.1 Write tests for `resolver_audit.py` covering: dark skill detection, identical trigger overlap, substring trigger overlap (warning severity), missing script reference, JSON output shape, --fail-on-findings exit codes
  **Spec scenarios**: resolver-audit.1 (dark missing), .2 (dark passes), .3 (identical overlap), .4 (distinct pass), .5 (substring warning), .6 (script exists), .7 (script missing), .8 (JSON valid), .9 (JSON metadata), .a (fail on errors), .b (warnings exit 0), .c (no findings exit 0)
  **Contracts**: contracts/resolver-finding.schema.json
  **Dependencies**: None
- [ ] 1.2 Implement `skills/resolver-audit/scripts/resolver_audit.py` (pure-stdlib Python; `pathlib.Path.glob` for skill discovery; `re` + minimal YAML frontmatter parser to avoid pyyaml dependency, or use the project's existing pyyaml if already available; argparse for `--json`/`--fail-on-findings`)
  **Dependencies**: 1.1
- [ ] 1.3 Write `skills/resolver-audit/SKILL.md` (frontmatter with `triggers: ["audit resolver", "resolver audit", "check skills"]`; usage section; pointer to script)
  **Dependencies**: 1.2

## Phase 2 — Validate-feature integration

- [ ] 2.1 Write integration test that invokes `/validate-feature --phase resolver` against a fixture skills directory containing one dark skill, asserts non-zero exit and finding in report
  **Spec scenarios**: resolver-audit.d (resolver phase runs), .e (fails on errors)
  **Dependencies**: 1.2
- [ ] 2.2 Extend `skills/validate-feature/scripts/` to dispatch the new `resolver` phase, calling `resolver_audit.py --json --fail-on-findings` and merging output into the validation report
  **Dependencies**: 2.1
- [ ] 2.3 Update `skills/validate-feature/SKILL.md` to document the `--phase resolver` selector and its CI use
  **Dependencies**: 2.2

## Phase 3 — Skillify scaffold

- [ ] 3.1 Write tests for `skillify.py` covering: default invocation infers target-repo from git remote, explicit --target-repo override, kebab-case validation rejects bad names, existing skill rejected, scaffolded SKILL.md frontmatter is valid YAML with required keys, scaffolded openspec change discoverable by `openspec list`, files staged but not committed
  **Spec scenarios**: skillify-promotion.1 (default infer), .2 (explicit override mismatch), .3 (invalid kebab), .4 (existing skill), .5 (frontmatter parses), .6 (openspec list), .7 (next-steps text), .8 (staged), .9 (no auto-commit)
  **Dependencies**: None (parallel with Phase 1)
- [ ] 3.2 Implement `skills/skillify/scripts/skillify.py` (argparse for `<name>` and `--target-repo`; subprocess `git remote get-url origin` for inference; `openspec new change` shell-out for stub; templated SKILL.md and proposal.md)
  **Dependencies**: 3.1
- [ ] 3.3 Write `skills/skillify/SKILL.md` (frontmatter with `triggers: ["skillify", "skillify it"]`; usage section walking through the workflow; pointer to script)
  **Dependencies**: 3.2

## Phase 4 — CI wiring

- [ ] 4.1 Audit existing CI workflow files (likely `.github/workflows/*.yml`) and identify the right job to extend
  **Dependencies**: 2.2
- [ ] 4.2 Add a CI step that runs `/validate-feature --phase resolver` (via the venv'd python invocation) on every PR; gate merge on success
  **Dependencies**: 4.1

## Phase 5 — Initial audit and triage (housekeeping; do not block on findings)

- [ ] 5.1 Run `python3 skills/resolver-audit/scripts/resolver_audit.py --json` against the current `skills/` tree and capture findings
  **Dependencies**: 1.2
- [ ] 5.2 If findings exist, file a separate housekeeping change to fix them; do NOT fix in this PR (keeps scope clean and gives those fixes their own review)
  **Dependencies**: 5.1
- [ ] 5.3 Verify CI gate (Phase 4) only enables after housekeeping change lands, OR add a baseline-suppression file so this PR can land without those fixes
  **Dependencies**: 5.2

## Phase 6 — Propagate to runtime and verify

- [ ] 6.1 Run `/update-skills` (lands in Change A) to propagate `skills/skillify/`, `skills/resolver-audit/`, and updated `skills/validate-feature/` into `.claude/skills/` and `.agents/skills/`
  **Dependencies**: 1.3, 2.3, 3.3, ri-01 (Change A) merged
- [ ] 6.2 Run full skill test suite: `skills/.venv/bin/python -m pytest skills/tests/skillify/ skills/tests/resolver-audit/ -v`
  **Dependencies**: 1.2, 3.2
- [ ] 6.3 Run `openspec validate add-skillify-and-resolver-audit --strict`
  **Dependencies**: All phases

## Phase 7 — Smoke test

- [ ] 7.1 Use `/skillify smoke-test-skill` end-to-end: scaffold succeeds, generated SKILL.md is valid, openspec list shows new change, files staged. Then `git restore --staged` and `rm -rf` the test artifacts.
  **Dependencies**: 6.1
