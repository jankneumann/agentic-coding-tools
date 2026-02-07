# Change: Add validate-feature skill

## Why

The current skill workflow has a gap between code refinement (`/iterate-on-implementation`) and merge/cleanup (`/cleanup-feature`). Static quality checks (pytest, mypy, ruff) verify code correctness in isolation, but nothing verifies the feature works correctly when **deployed and running**. This means issues like misconfigured Docker services, runtime import errors, broken API contracts, log-level noise, and spec-violating behavior slip through to the PR review stage where they're expensive to catch.

A `/validate-feature` skill fills this gap by deploying locally with DEBUG logging, running behavioral tests against live services, checking CI/CD status, and verifying that each OpenSpec scenario holds against the actual running system.

## What Changes

- **New skill**: `skills/validate-feature/SKILL.md` — orchestrates deployment, testing, log analysis, and spec compliance verification
- **Modified spec**: `skill-workflow` — updates the workflow position requirement to include `/validate-feature` and adds requirements for the validation skill itself
- Infrastructure scaffolding tasks for Playwright config, validation test helpers, and CI/CD workflow stubs

## Impact

- Affected specs: `skill-workflow`
- Affected code:
  - `skills/validate-feature/SKILL.md` (new)
  - `~/.claude/skills/validate-feature` symlink (new)
  - Project-level `playwright.config.ts` or `conftest.py` for E2E (new, optional)
  - `.github/workflows/ci.yml` (new stub)
- No breaking changes to existing skills — `/validate-feature` is an optional step in the workflow
