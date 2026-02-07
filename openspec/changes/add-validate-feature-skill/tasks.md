## 1. Create validate-feature Skill
**Dependencies**: None
**Files**: `skills/validate-feature/SKILL.md`

- [x] 1.1 Create `skills/validate-feature/SKILL.md` with frontmatter (name, description, category, tags, triggers)
- [x] 1.2 Write Step 1: Determine Change ID and Configuration (parse args, detect branch, support `--skip-e2e` / `--skip-playwright` / `--skip-ci` / `--phase <name>` flags)
- [x] 1.3 Write Step 2: Verify Prerequisites (check Docker available, feature branch exists, implementation commits exist)
- [x] 1.4 Write Step 3: Deploy Phase — start services via docker-compose with `LOG_LEVEL=DEBUG`, redirect logs to file, wait for health checks
- [x] 1.5 Write Step 4: Smoke Phase — CLI-based health checks (API reachable, MCP server responds, database migrations applied)
- [x] 1.6 Write Step 5: E2E Phase — run pytest-playwright tests if present, skip gracefully if no web UI or Playwright not installed
- [x] 1.7 Write Step 6: Spec Compliance Phase — read OpenSpec scenarios, verify each against live system via API calls / MCP tool invocations
- [x] 1.8 Write Step 7: Log Analysis Phase — scan collected log file for WARNING/ERROR/CRITICAL, deprecation notices, unhandled exceptions, stack traces
- [x] 1.9 Write Step 8: CI/CD Status Phase — check GitHub Actions status via `gh run list` / `gh pr checks`, report pass/fail
- [x] 1.10 Write Step 9: Teardown — stop docker-compose services, clean up log files
- [x] 1.11 Write Step 10: Validation Report — structured summary of all phases with pass/fail and actionable findings
- [x] 1.12 Write Step 11: Persist Report — write report to `openspec/changes/<change-id>/validation-report.md` with timestamp and commit SHA
- [x] 1.13 Write Step 12: PR Comment — post report as PR comment via `gh pr comment` (skip gracefully if no PR exists)
- [x] 1.14 Write After Validation section with next-step guidance (iterate if failures, cleanup if all pass)

## 2. Symlink Skill for Global Availability
**Dependencies**: Task 1
**Files**: `~/.claude/skills/validate-feature` (symlink)

- [x] 2.1 Create symlink from `~/.claude/skills/validate-feature` → `<repo>/skills/validate-feature`
- [x] 2.2 Verify skill appears in Claude Code skill list

## 3. Scaffold CI/CD Workflow Stub
**Dependencies**: None (can run parallel with Task 1)
**Files**: `.github/workflows/ci.yml`

- [x] 3.1 Create `.github/workflows/ci.yml` with basic Python CI (checkout, install deps, pytest, mypy, ruff)
- [x] 3.2 Add OpenSpec validation step (`openspec validate --strict`)
- [x] 3.3 Verify workflow syntax with `gh workflow view` or `act` if available

## 4. Scaffold Playwright E2E Infrastructure
**Dependencies**: None (can run parallel with Task 1 and 3)
**Files**: `agent-coordinator/pyproject.toml`, `agent-coordinator/tests/e2e/conftest.py`

- [x] 4.1 Add `pytest-playwright` to dev dependencies in `pyproject.toml`
- [x] 4.2 Create `agent-coordinator/tests/e2e/conftest.py` with Playwright fixtures (base_url, browser setup)
- [x] 4.3 Create `agent-coordinator/tests/e2e/test_health.py` — minimal smoke test that verifies the REST API responds
- [x] 4.4 Document Playwright browser installation in README (`playwright install chromium`)

## 5. Update Workflow Documentation
**Dependencies**: Task 1
**Files**: `CLAUDE.md`, `skills/cleanup-feature/SKILL.md`, `skills/iterate-on-implementation/SKILL.md`

- [x] 5.1 Update `CLAUDE.md` workflow section to include `/validate-feature` in the workflow diagram
- [x] 5.2 Update `iterate-on-implementation` SKILL.md "Next Step" section to reference `/validate-feature`
- [x] 5.3 Update `cleanup-feature` SKILL.md prerequisites to mention `/validate-feature` as a recommended prior step
- [x] 5.4 Add lessons learned about deployment validation to `CLAUDE.md` if applicable

## 6. Validate Spec Deltas and Final Review
**Dependencies**: Tasks 1-5
**Files**: `openspec/changes/add-validate-feature-skill/specs/skill-workflow/spec.md`

- [x] 6.1 Run `openspec validate add-validate-feature-skill --strict` to confirm integrity
- [x] 6.2 Review that spec scenarios are testable against the implemented skill
- [x] 6.3 Verify all cross-references between skill, specs, and documentation are consistent

## Parallelization Summary

| Task | Can Parallelize With |
|------|---------------------|
| 1 (Skill SKILL.md) | 3, 4 |
| 2 (Symlink) | None — depends on 1 |
| 3 (CI/CD stub) | 1, 4 |
| 4 (Playwright scaffold) | 1, 3 |
| 5 (Docs update) | None — depends on 1 |
| 6 (Final review) | None — depends on 1-5 |

**Execution waves:**
- Wave 1: Task 1 + Task 3 + Task 4 (parallel — no shared files)
- Wave 2: Task 2 + Task 5 (parallel after Task 1 completes)
- Wave 3: Task 6 (final review)
