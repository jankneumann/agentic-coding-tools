# Skill audit, test-policy lens: test-driven-development

- lens: test-policy
- generated_at: 2026-10-13T00:00:00+00:00
- instructions: 56
- findings: 1

Findings are proposals; the lens never edits the audited skill. This report is not the rightsizing audit and does not count as the skill's freshness report.

## Findings

| id | kind | section | remediation | rationale |
|---|---|---|---|---|
| F001 | test_same_context_authorship | SKILL.md#01-overview | add_reason | one agent writes both the tests and the implementation in the same context (1 instruction(s)): "Write a failing test before writing the code that makes it pass." |

## Instructions

| section | oracle_source | authorship | instruction |
|---|---|---|---|
| SKILL.md#01-overview | unspecified | same_agent | Write a failing test before writing the code that makes it pass. |
| SKILL.md#01-overview | unclassified | unclassified | For bug fixes, reproduce the bug with a test before attempting a fix. |
| SKILL.md#01-overview | unclassified | unclassified | Tests are proof — "seems right" is not done. |
| SKILL.md#01-overview | unclassified | unclassified | A codebase with good tests is an AI agent's superpower; a codebase without tests is a liability. |
| SKILL.md#02-when-to-use | unclassified | unclassified | **Related:** For browser-based changes, combine TDD with runtime verification using Chrome DevTools MCP — see the Bro... |
| SKILL.md#02-when-to-use | unclassified | unclassified | For systematic root-cause work after a test fails, hand off to `debugging-and-error-recovery`. |
| SKILL.md#04-step-1-red-write-a-failing-test | unclassified | unclassified | Write the test first. |
| SKILL.md#04-step-1-red-write-a-failing-test | unclassified | unclassified | A test that passes immediately proves nothing. |
| SKILL.md#04-step-1-red-write-a-failing-test | unclassified | unclassified | **Python (pytest):** |
| SKILL.md#04-step-1-red-write-a-failing-test | unclassified | unclassified | Run the new test in isolation to confirm it fails for the right reason: |
| SKILL.md#05-step-2-green-make-it-pass | unclassified | unclassified | Write the minimum code to make the test pass. |
| SKILL.md#06-step-3-refactor-clean-up | unclassified | unclassified | With tests green, improve the code without changing behavior: |
| SKILL.md#07-the-prove-it-pattern-bug-fixes | unclassified | unclassified | When a bug is reported, **do not start by trying to fix it.** Start by writing a test that reproduces it. |
| SKILL.md#08-the-test-pyramid | unclassified | unclassified | Invest testing effort according to the pyramid — most tests should be small and fast, with progressively fewer tests... |
| SKILL.md#08-the-test-pyramid | unclassified | unclassified | **The Beyonce Rule:** If you liked it, you should have put a test on it. |
| SKILL.md#08-the-test-pyramid | unclassified | unclassified | Infrastructure changes, refactoring, and migrations are not responsible for catching your bugs — your tests are. |
| SKILL.md#08-the-test-pyramid | unclassified | unclassified | If a change breaks your code and you didn't have a test for it, that's on you. |
| SKILL.md#09-test-sizes-resource-model | unclassified | unclassified | Beyond the pyramid levels, classify tests by what resources they consume: |
| SKILL.md#09-test-sizes-resource-model | unclassified | unclassified | Small tests should make up the vast majority of your suite. |
| SKILL.md#11-writing-good-tests | unclassified | unclassified | For a deeper catalogue of patterns and per-framework examples, see `references/testing-patterns.md`. |
| SKILL.md#12-test-state-not-interactions | unclassified | unclassified | Assert on the *outcome* of an operation, not on which methods were called internally. |
| SKILL.md#12-test-state-not-interactions | unclassified | unclassified | Tests that verify method call sequences break when you refactor, even if the behavior is unchanged. |
| SKILL.md#13-damp-over-dry-in-tests | unclassified | unclassified | In tests, **DAMP (Descriptive And Meaningful Phrases)** is better. |
| SKILL.md#13-damp-over-dry-in-tests | unclassified | unclassified | A test should read like a specification — each test should tell a complete story without requiring the reader to trac... |
| SKILL.md#13-damp-over-dry-in-tests | unclassified | unclassified | Duplication in tests is acceptable when it makes each test independently understandable. |
| SKILL.md#14-prefer-real-implementations-over-mocks | unclassified | unclassified | Use the simplest test double that gets the job done. |
| SKILL.md#14-prefer-real-implementations-over-mocks | unclassified | unclassified | The more your tests use real code, the more confidence they provide. |
| SKILL.md#14-prefer-real-implementations-over-mocks | unclassified | unclassified | **Use mocks only when:** the real implementation is too slow, non-deterministic, or has side effects you can't contro... |
| SKILL.md#14-prefer-real-implementations-over-mocks | unclassified | unclassified | Over-mocking creates tests that pass while production breaks. |
| SKILL.md#14-prefer-real-implementations-over-mocks | unclassified | unclassified | In Python, prefer `unittest.mock` (or `pytest-mock`'s `mocker` fixture) only at the boundary you can't control: |
| SKILL.md#19-coverage-and-targeted-runs | unclassified | unclassified | For async Python code, install and enable `pytest-asyncio` (see `references/testing-patterns.md`). |
| SKILL.md#19-coverage-and-targeted-runs | unclassified | unclassified | For Python mocking, prefer `unittest.mock.patch` scoped to the narrowest context that works (`with patch(...)` over m... |
| SKILL.md#20-browser-testing-with-devtools | unclassified | unclassified | For anything that runs in a browser, unit tests alone aren't enough — you need runtime verification. |
| SKILL.md#20-browser-testing-with-devtools | unclassified | unclassified | The full workflow lives in the `browser-testing-with-devtools` skill. |
| SKILL.md#21-security-boundaries | unclassified | unclassified | See the `browser-testing-with-devtools` skill for the full security contract. |
| SKILL.md#22-when-to-use-subagents-for-testing | unspecified | separate_context | For complex bug fixes, spawn a subagent to write the reproduction test: |
| SKILL.md#22-when-to-use-subagents-for-testing | unclassified | unclassified | This separation ensures the test is written without knowledge of the fix, making it more robust. |
| SKILL.md#23-see-also | unclassified | unclassified | `references/testing-patterns.md` — patterns, examples, and anti-patterns across frameworks (Jest, Vitest, pytest) |
| SKILL.md#23-see-also | unclassified | unclassified | `references/security-checklist.md` — security checks to fold into your test plan |
| SKILL.md#23-see-also | unclassified | unclassified | `references/performance-checklist.md` — perf budgets and assertions for end-to-end tests |
| SKILL.md#23-see-also | unclassified | unclassified | `references/accessibility-checklist.md` — a11y assertions for UI tests |
| SKILL.md#23-see-also | unclassified | unclassified | `debugging-and-error-recovery` skill — what to do *after* a test goes red |
| SKILL.md#23-see-also | unclassified | unclassified | `browser-testing-with-devtools` skill — runtime verification for UI work |
| SKILL.md#25-red-flags | unclassified | unclassified | A new feature commit that touches `src/`/`app/` but not `tests/` |
| SKILL.md#25-red-flags | unclassified | unclassified | Tests that pass on the first run of the RED phase (they may not be testing what you think) |
| SKILL.md#25-red-flags | unclassified | unclassified | "All tests pass" reported but the runner output isn't shown (`npm test` / `pytest` exit 0 must be visible) |
| SKILL.md#25-red-flags | unclassified | unclassified | Bug fixes without a reproduction test that fails on the parent commit |
| SKILL.md#25-red-flags | unclassified | unclassified | Tests that exercise the framework (`expect(jest).toBeDefined()`) instead of application behavior |
| SKILL.md#25-red-flags | unclassified | unclassified | Test names like `it('works')`, `def test_thing()` — vague names hide what's being verified |
| SKILL.md#25-red-flags | unclassified | unclassified | Tests skipped (`.skip`, `@pytest.mark.skip`, `xit`) or disabled to make the suite green |
| SKILL.md#26-verification | unclassified | unclassified | Every new behavior has a corresponding test that fails on the parent commit and passes on this commit. |
| SKILL.md#26-verification | unclassified | unclassified | The full suite runs green locally: `npm test` (or `npx jest`) AND/OR `pytest` (whichever applies). |
| SKILL.md#26-verification | unclassified | unclassified | Bug fixes include a reproduction test added in the same change; cite the test path and node id. |
| SKILL.md#26-verification | unclassified | unclassified | Test names describe the behavior under test (read like a spec line). |
| SKILL.md#26-verification | unclassified | unclassified | No tests were skipped or disabled to land the change; if any were marked xfail/skip, link to the follow-up issue. |
| SKILL.md#26-verification | unclassified | unclassified | Coverage hasn't decreased (when tracked): show `pytest --cov` or `jest --coverage` deltas if available. |
