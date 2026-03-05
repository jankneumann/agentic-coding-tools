# Change: add-ci-skills-tests

## Why

The bug-scrub and fix-scrub skills have 341 unit tests (214 + 127) that validate core diagnostic and remediation logic, but none of these tests run in CI. Regressions in skill scripts are completely invisible — a broken collector, classifier, or renderer would only be caught during manual skill execution. Since these skills are part of the standard workflow (used by `/bug-scrub` and `/fix-scrub`), silent breakage degrades the entire project health diagnostic pipeline.

The fix is minimal: add one new CI job that runs these tests using the existing agent-coordinator venv, with no new dependencies or infrastructure required.

## What Changes

- Add a `test-skills` job to `.github/workflows/ci.yml` that runs bug-scrub and fix-scrub tests
- The job installs the agent-coordinator venv (which already includes pytest) and runs tests from the repo root to preserve the cross-skill `importlib` path resolution that fix-scrub uses to import bug-scrub models
- The new job runs in parallel with the existing `test`, `test-scripts`, and `validate-specs` jobs — no sequential dependencies

## Impact

- **Affected spec**: `skill-workflow` — adds implicit CI coverage requirement for skill test suites
- **Code touchpoint**: `.github/workflows/ci.yml` (add ~15 lines for new job)
- **Architecture layer**: Execution (CI pipeline only — no runtime code changes)
- **No breaking changes**
- **No spec delta needed** — the skill-workflow spec does not currently specify CI job structure; this change adds coverage without modifying any spec requirements
