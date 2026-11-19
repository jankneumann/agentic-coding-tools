# Change Context: sandbox-the-interactive-lead-session

## Requirement Traceability Matrix

Tests live in `skills/tests/session-bootstrap/`. Contract Ref is `---` throughout:
`contracts/` holds only a README, because the change exposes no interface.

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| harness-engineering.1 | specs/harness-engineering/spec.md "Lead Session Bash Sandbox Configuration" | Project settings enable the Bash sandbox with auto-allow, do not require it, and make toolchain caches writable | --- | D1, D2, D9 | `.claude/settings.json` | `test_lead_session_sandbox_settings.py`: `test_sandbox_and_auto_allow_are_on`, `test_sandbox_is_not_required`, `test_toolchain_caches_are_writable`, `test_local_binding_is_allowed` | --- |
| harness-engineering.2 | "Sandboxed Commands Cannot Read Credentials or Sibling Checkouts" | Credential locations and the checkout's parent are read-denied; the project is re-allowed | --- | D3, D8 | `.claude/settings.json`, `skills/session-bootstrap/scripts/sandbox_probe.py` | `test_credential_location_is_denied`, `test_parent_is_denied_and_project_is_allowed`, `test_whole_config_and_claude_dirs_are_not_denied`; `test_sandbox_probe.py::test_sandboxed_host_reports_enforced` (faked filesystem) | --- |
| harness-engineering.3 | "Outward Commands Run Outside the Sandbox Under Permission Rules" | Push, fetch, pull, `gh`, `railway`, `docker` are excluded; no Git host is on the network allowlist | --- | D4 | `.claude/settings.json` | `test_outward_command_is_excluded`, `test_git_hosts_are_not_reachable`, `test_allowed_domains_are_recorded` | --- |
| harness-engineering.4 | "Irreversible Command Classes Remain Gated" | Every irreversible class, and gate recording, keeps a deny rule, a content-scoped ask rule or a guard verdict | --- | D6, D10, D11 | `.claude/settings.json` | `test_irreversible_set_gated.py`: `test_irreversible_command_is_gated`, `test_development_command_is_not_gated`, `test_guard_hook_is_registered_and_fails_closed`, `test_no_setting_skips_the_hook`; `test_ask_rules_are_content_scoped` | --- |
| harness-engineering.5 | "Allow List Grants No General Reader or Interpreter" | The allow list holds no reader, interpreter or test runner, is under half its former size, and keeps fetch and pull promptless | --- | D5 | `.claude/settings.json` | `test_no_reader_or_interpreter_is_allowed`, `test_allow_list_is_less_than_half`, `test_fetch_and_pull_stay_promptless`, `test_kept_rules_are_still_present` | --- |
| harness-engineering.6 | "Sandbox Probe" | A probe reads its targets from settings, reports each as enforced or not, prints no content, and is skipped where isolation is provided | --- | D7, D8 | `skills/session-bootstrap/scripts/sandbox_probe.py` | `test_sandbox_probe.py` (15 tests) | --- |
| harness-engineering.7 | "Lead Session Sandbox Guidance" | `CLAUDE.md` and an operator guide describe the sandbox consistently with the settings | --- | --- | `CLAUDE.md`, `docs/guides/lead-session-sandbox.md`, `docs/guides/documentation.md` | `test_lead_session_sandbox_docs.py` (10 tests) | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Versioned and testable from the repository | `sandbox` block in `.claude/settings.json` | User-level settings cannot be tested or reviewed |
| D2 | Hosts without prerequisites and cloud sessions must keep working | `failIfUnavailable` and `allowUnsandboxedCommands` left unset | With the reduced allow list the fallback prompts instead of running freely |
| D3 | Hide credentials and sibling checkouts from sandboxed commands | `filesystem.denyRead` (ten credential paths and `..`), `allowRead: ["."]` | `~/.config` and `~/.claude` are read by tools, so only named paths are denied. Precedence of `.` over `..` is unverified |
| D4 | Outward actions stay under the existing push rules | `excludedCommands`; `github.com` absent from `allowedDomains` | The network allowlist is the boundary; command-text matching alone can be wrapped |
| D5 | An allow rule approves the unsandboxed retry of the same command | `permissions.allow` cut from 100 to 35 entries | Keeping readers would undo D3 |
| D6 | Keep the guard hook as second layer | No change to `irreversible_guard.py`; agreement asserted by test | The hook is paired by tests with `guardrails.py`, outside this change |
| D7 | No second settings file for cloud | Probe calls `environment_profile.detect()` and reports `skipped` | Local settings are reportedly not read in cloud sessions |
| D8 | One list of denied paths | Probe reads `denyRead` from settings; prints path and verdict only | A second list would drift |
| D9 | Suites that bind localhost run sandboxed | `network.allowLocalBinding: true` | Avoids a prompt for every such suite |
| D10 | Gate recording was gated only by absence from the allow list | Ask rules `*runner.py* gate-answer*`, `*cycle_state.py* gate-answer*` | Auto-allow would otherwise record approvals unprompted |
| D11 | Close guard gaps without touching the guard | Ask rules for `alembic upgrade/downgrade`, `gh secret`, `gh api … merge`, `git branch -D` | Guard changes must stay in step with the coordinator |

## Coverage Summary

- **Requirements traced**: 7/7
- **Tests mapped**: 7 requirements have at least one test
- **Evidence collected**: 0/7 requirements have pass/fail evidence
- **Gaps identified**: Scenario "The denial is demonstrated on a sandboxed host" is tested against a faked filesystem only; no sandbox exists in the container where this was written
- **Deferred items**: Host verification with the probe and the guide's checklist, on the operator's machines
