# Validation Report: sandbox-the-interactive-lead-session

**Date**: 2026-11-19
**Commit**: 7f4fa503890b39f411f8647a08c7cb7d9e151808
**Validated tree**: 89b043f552b8685f69238b2860f8efd06ab640ee
**Branch**: claude/eloquent-edison-tn8alg

Validated in a cloud container (`AGENT_EXECUTION_ENV=cloud`). The container has
no Bash sandbox, so the sandbox's behaviour on a host was not exercised. What
passed here is the configuration, the probe's logic and the guidance.

## Phase Results

○ Deploy: not applicable (no deployable surface)
○ Smoke: not applicable (no deployable surface)
○ Gen-Eval: skipped (the only descriptor covers `agent-coordinator`, which this change does not touch)
○ Security: not applicable (no deployable surface)
○ E2E: not applicable (no deployable surface)
⚠ Architecture: advisory mode, status pass; 0 new cycles; 0 flow findings; 3 linter findings on test data (see below)
✓ Traceability: gate passed (change scope; 78 operations cite 45 requirements repository-wide)
✓ Spec Compliance: 7/7 requirements verified by tests; 1 scenario deferred to a sandboxed host
○ Log Analysis: skipped (no services were started)
○ CI/CD: not checked (no pull request exists for this branch)
○ Choices: no ledger

## Task Drift

`tasks.md` has no unchecked task. The branch is 12 commits ahead of `main`.

## Spec Compliance

**Status**: pass

`skills/.venv/bin/python -m pytest skills/tests/session-bootstrap -q`: 376 passed.
`openspec validate sandbox-the-interactive-lead-session --strict`: valid.

| Requirement | Result | Verified by |
|---|---|---|
| Lead Session Bash Sandbox Configuration | pass | `test_lead_session_sandbox_settings.py` against the real `.claude/settings.json` |
| Sandboxed Commands Cannot Read Credentials or Sibling Checkouts | pass (configuration); host demonstration deferred | Settings tests; `test_sandbox_probe.py` with a faked filesystem |
| Outward Commands Run Outside the Sandbox Under Permission Rules | pass | Settings tests |
| Irreversible Command Classes Remain Gated | pass | `test_irreversible_set_gated.py` |
| Allow List Grants No General Reader or Interpreter | pass | Settings tests |
| Sandbox Probe | pass | `test_sandbox_probe.py`; the probe run here printed `skipped	detection=env_var`, exit 0 |
| Lead Session Sandbox Guidance | pass | `test_lead_session_sandbox_docs.py` |

### Not verified

These depend on harness behaviour that only a sandboxed host can show. The
operator checklist in `docs/guides/lead-session-sandbox.md` covers each.

- Scenario "The denial is demonstrated on a sandboxed host": the probe has not
  run inside a real sandbox.
- Whether `allowRead: ["."]` takes precedence over `denyRead: [".."]`.
- Whether ask rules and the guard hook's `ask` verdict still prompt for a
  sandboxed command under auto-allow. The irreversible-set test checks rule
  text with its own matcher, not the harness's matcher.
- Whether ask patterns with a leading `*` match as the test assumes.

If the third item fails on a host, migrations and gate recording would run
without a prompt. The guide tells the operator to switch the sandbox off in
that case.

## Smoke Tests

**Status**: not applicable

All changed paths are settings, skills, documentation or OpenSpec artifacts.
There is no service to start.

## Security

**Status**: not applicable

No deployable surface, so the dependency and ZAP scanners have no target. The
change is itself a security control; its checks are under Spec Compliance.

## E2E Tests

**Status**: not applicable

No deployable surface and no user interface.

## Architecture

**Status**: pass (advisory mode)

- Artifacts: fresh (`run_architecture.py --ensure`, nothing rewritten).
- Baseline diff against `f8a7da6`: 0 new cycles. The diff also reports 150
  added nodes, 2 high-impact modules, 3 untested routes and 2 database tables.
  This branch changes no file under `agent-coordinator/`, so those come from
  the baseline graph being older than `main`, not from this change.
- Flow validation scoped to the changed files: 0 errors, 0 warnings.
- Structural linters: 3 findings rated critical, all in
  `skills/tests/session-bootstrap/test_irreversible_set_gated.py` (lines 75,
  88, 89), for "canonical `skills/` runtime path". The lines are command
  strings used as test data for the permission rules; nothing executes them.
  Left unchanged. 6 size nits on generated architecture artifacts.

## Result

**PASS**, with the host verification deferred to the operator.

Next step: run the checklist in `docs/guides/lead-session-sandbox.md` on one
macOS and one Linux host before relying on the sandbox.
