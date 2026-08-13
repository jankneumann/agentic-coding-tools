# Tasks: strengthen-simplify-behavior-preservation

## 1. OpenSpec artifacts

- [x] 1.1 Write `proposal.md` with operator decisions A+B+C / manual / OpenSpec / keep `/simplify`
- [x] 1.2 Write `design.md` (D1–D7)
- [x] 1.3 Write `specs/skill-workflow/spec.md` delta
- [x] 1.4 Write this `tasks.md`

## 2. Phase A — Skill contract

- [x] 2.1 Expand `skills/simplify/SKILL.md` (coverage gate, dual-run, patterns, when-not, related, triggers)
- [x] 2.2 Extend `skills/tests/simplify/test_skill_md.py` content invariants

## 3. Phase B — Scripts

- [x] 3.1 Implement `skills/simplify/scripts/check_scope.py`
- [x] 3.2 Implement `skills/simplify/scripts/check_test_contract.py`
- [x] 3.3 Implement `skills/simplify/scripts/verify_behavior_preservation.py`
- [x] 3.4 Unit tests under `skills/tests/simplify/` for scripts
- [x] 3.5 Document script invocation in SKILL.md (`<skill-base-dir>`)

## 4. Phase C — Ecosystem hooks

- [x] 4.1 `skills/tech-debt-analysis/SKILL.md` remediation routing
- [x] 4.2 `skills/implement-feature/SKILL.md` optional Next Step `/simplify`
- [x] 4.3 `skills/iterate-on-implementation/SKILL.md` optional Next Step `/simplify`
- [x] 4.4 `docs/skills-catalogue.md` blurb update
- [x] 4.5 `docs/skill-flow/README.md` polish edge note

## 5. Verification

- [x] 5.1 Run `skills/.venv/bin/python -m pytest skills/tests/simplify/ -q` (23 passed)
- [x] 5.2 Sync portable skill via `bash skills/install.sh --mode rsync --deps none --python-tools none` if runtime mirrors need refresh