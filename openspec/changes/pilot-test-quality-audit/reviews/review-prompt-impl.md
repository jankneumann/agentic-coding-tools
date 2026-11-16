Review the IMPLEMENTATION on this branch (openspec/pilot-test-quality-audit) against its OpenSpec proposal.

Scope (read these; ignore everything else):
- Source: packages/test-oracle-audit/src/test_oracle_audit/*.py
- Tests: packages/test-oracle-audit/tests/*.py (skip tests/fixtures/)
- Skill lens: skills/skill-audit/scripts/test_policy_lens.py, skills/skill-audit/scripts/audit_findings.py, skills/skill-audit/scripts/skill_audit.py, skills/skill-audit/SKILL.md, openspec/schemas/skill-audit-findings.schema.json
- CI: .github/workflows/ci.yml job `test-oracle-audit-tests`, .github/dependabot.yml, skills/tests/ci_coverage/*
- Requirements: openspec/changes/pilot-test-quality-audit/proposal.md, design.md, specs/**/spec.md, contracts/
Use `git diff origin/main...HEAD -- <path>` to see changes. Do NOT review docs/reports/** (generated pilot output) or docs/architecture-analysis/**.

Focus: correctness bugs (wrong logic, crashes on edge inputs, subprocess/git handling, path handling), spec/contract compliance (records validate against contracts/schemas, read-only invariant over audited repos, deterministic output), security (subprocess injection, writing outside output dir), and tests that do not actually pin the behaviour they claim.
Report only concrete, verifiable findings with file and line. Output ONLY valid JSON conforming to review-findings.schema.json.
