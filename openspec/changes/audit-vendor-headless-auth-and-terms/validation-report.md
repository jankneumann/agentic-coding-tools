# Validation Report: audit-vendor-headless-auth-and-terms

**Date**: 2026-11-19
**Commit**: c15c3d6d4242bb6d7ab4b0e691522dbc5cf7df62
**Validated tree**: e935bcfcace6fef3e1ffbcdcb113637013d31fac
**Branch**: claude/eloquent-edison-tn8alg

Validated in a cloud container. Only the Claude CLI is installed there, no CLI
is signed in, and the legal pages of three vendors are blocked by the
environment's network policy. The checks below show that the audit table, the
script and the guide are internally consistent. They do not show that the
table's contents are true on a host.

## Phase Results

○ Deploy: not applicable (no deployable surface)
○ Smoke: not applicable (no deployable surface)
○ Gen-Eval: skipped (the only descriptor covers `agent-coordinator`, which this change does not touch)
○ Security: not applicable (no deployable surface)
○ E2E: not applicable (no deployable surface)
⚠ Architecture: advisory mode, status pass; 0 new cycles; 0 flow findings; 1 linter finding (a file-length nit on a proposal document)
✓ Traceability: gate passed (change scope; 78 operations cite 45 requirements repository-wide)
✓ Spec Compliance: 5/5 requirements verified by tests; host observation and three vendors' licence text not verified
✗ Task Drift: 1 unchecked task (4.1)
○ Log Analysis: skipped (no services were started)
○ CI/CD: not checked (no pull request exists for this branch)
○ Choices: no ledger

## Task Drift

**Status**: fail

Task 4.1 is unchecked: run the observation script and the host procedure for
each vendor on an operator host, and raise the evidence levels in the table. It
cannot be done in the container. It was not moved to a deferred-tasks file,
because the change's purpose is evidence for later roadmap items and that
evidence does not exist yet. Tasks 1.1 to 3.4 are checked and committed.

## Spec Compliance

**Status**: pass by test, with unverified content

Commands:

- `skills/.venv/bin/python -m pytest skills/tests/vendor-status -q`: 39 passed
- `openspec validate audit-vendor-headless-auth-and-terms --strict`: valid
- `python3 skills/vendor-status/scripts/observe_vendor_auth.py claude`: exit 0; printed metadata lines only
- `python3 skills/vendor-status/scripts/observe_vendor_auth.py nosuch`: exit 2

| Requirement | Result | Verified by |
|---|---|---|
| vendor-auth-audit.1 Vendor Auth Audit Table | pass | 6 tests in `test_vendor_auth_audit_table.py` |
| vendor-auth-audit.2 Unattended Lanes Without Permission Require a Keyed Lane | pass | 2 tests in `test_vendor_auth_audit_table.py` |
| vendor-auth-audit.3 Credential Mechanics With Evidence Level | pass | 4 tests in `test_vendor_auth_audit_table.py` |
| vendor-auth-audit.4 Credential Observation Script | pass | 14 tests in `test_observe_vendor_auth.py`; one run in the container |
| vendor-auth-audit.5 Audit Guide and Corrected Statements | pass | 13 tests in `test_vendor_auth_audit_docs.py` |

### Not verified

- No mechanics field is `observed`. All 16 are `documented` or `not_observed`.
- The script was not run against a signed-in CLI, and `--watch` was exercised
  only against temporary directories.
- No licence text was read for Codex, Antigravity or Grok. Their verdicts rest
  on product documentation. Blocked hosts: `openai.com`,
  `developers.openai.com`, `help.openai.com`, `antigravity.google`,
  `ai.google.dev`, `policies.google.com`, `x.ai`, `docs.x.ai`.
- Three lanes rest on `summarised` quotes: Codex CI, Antigravity attended
  headless, and the Antigravity FAQ sentence about wrapping `agy` in
  third-party coding agents.
- The tests check the table's shape and rules, not whether a quoted sentence
  still appears on the vendor's page.

## Smoke Tests

**Status**: not applicable

## Security

**Status**: not applicable

The observation script was reviewed for the one risk it carries: it uses
`lstat` and `listdir` only, and a test fails if it calls `open`.

## E2E Tests

**Status**: not applicable

## Architecture

**Status**: pass (advisory mode)

- Artifacts: fresh (`run_architecture.py --ensure`).
- Baseline diff against `f8a7da6`: 0 new cycles. The node and edge deltas come
  from baseline staleness; this change adds one script and three test files.
- Flow validation on the changed files: 0 findings.
- Linters: 1 nit, `docs/proposals/factory-local-cloud-split.md` has 771 lines.
  The file was 771 lines before this change edited one statement in it.

## Result

**Incomplete.** The implemented tasks pass every check that could run. The
change is not ready to archive: task 4.1 is open, and the table's verdicts for
three vendors have not been checked against licence text. Roadmap item ri-02
stays in progress until an operator host has been observed.
