# Tasks: add-headless-auth-policy

> Change ID: `add-headless-auth-policy`
> Tests are written before the code they cover. Test trees: `skills/tests/parallel-infrastructure/`,
> `skills/tests/quick-task/`, `agent-coordinator/tests/`.

## 1. Terms review and decision record

- [ ] 1.1 Read the current consumer terms and CLI documentation for Anthropic, Google, OpenAI and xAI; record per vendor the clause relied on, its URL and the date read, and the resulting allow/deny decision. Replace the unverified table in `design.md`.
  - Requirement: Declarative Lane Auth and Subscription Headless Policy (supplies `basis`/`reviewed`)
  - Files: `docs/decisions/parallel-infrastructure.md`, `openspec/changes/add-headless-auth-policy/design.md`
  - Dependencies: none

## 2. Registry schema and configuration

- [ ] 2.1 Tests: `cli.auth` required and enum-checked; `api_key` needs `api_key_env` and non-empty `vendor_credentials`; allow-entry validation (basis, reviewed, unknown vendor, duplicate); `get_dispatch_configs()` carries `auth` and the allow list.
  - Requirement: Declarative Lane Auth and Subscription Headless Policy
  - Files: `agent-coordinator/tests/test_agents_config_headless_auth.py`
  - Dependencies: none
- [ ] 2.2 Implement schema, `CliConfig.auth`, `validate` rules and dispatch-config projection.
  - Requirement: Declarative Lane Auth and Subscription Headless Policy
  - Files: `agent-coordinator/src/agents_config.py`
  - Dependencies: 2.1
- [ ] 2.3 Add `auth` to all eight `cli` blocks (`pi-local`: `api_key`; `ocr-local`: `none`; the rest `subscription`) and add `policies.subscription_headless` with an empty allow list.
  - Requirement: Declarative Lane Auth and Subscription Headless Policy
  - Files: `agent-coordinator/agents.yaml`
  - Dependencies: 2.2

## 3. Dispatcher gate, environment and probe

- [ ] 3.1 Tests: gate scenarios (fall-through to SDK, skip, allowed lane, missing `auth`, env bypass attempt, `--check-vendors` count, OpenAI-compatible precedence).
  - Requirement: Subscription Headless Dispatch Gate; OpenAI-Compatible Dispatcher Discovery
  - Files: `skills/tests/parallel-infrastructure/test_headless_auth_gate.py`
  - Dependencies: none
- [ ] 3.2 Implement the gate as a pre-filter in `discover_reviewers`, exclusion recording, manifest `excluded_lanes`, and `--check-vendors` reason.
  - Requirement: Subscription Headless Dispatch Gate; OpenAI-Compatible Dispatcher Discovery
  - Files: `skills/parallel-infrastructure/scripts/review_dispatcher.py`
  - Dependencies: 2.2, 3.1
- [ ] 3.3 Tests: environment isolation per `auth` (subscription strips keys, passthrough cannot re-add, `api_key` lane needs and receives only its key).
  - Requirement: Credential Isolation by Lane Auth
  - Files: `skills/tests/parallel-infrastructure/test_vendor_env_scrub.py`
  - Dependencies: none
- [ ] 3.4 Implement `vendor_subprocess_env` isolation and the `can_dispatch` key check.
  - Requirement: Credential Isolation by Lane Auth
  - Files: `skills/parallel-infrastructure/scripts/review_dispatcher.py`
  - Dependencies: 3.2, 3.3
- [ ] 3.5 Tests then implementation: L2 by key presence for `api_key` lanes, no status command, no value disclosure.
  - Requirement: Probe Auth Follows Lane Credential
  - Files: `skills/tests/parallel-infrastructure/test_vendor_probe.py`, `skills/parallel-infrastructure/scripts/vendor_probe.py`
  - Dependencies: 2.2
- [ ] 3.6 Tests then implementation: `--handoff` file contents, no subprocess, manifest `handoffs`, quorum unaffected.
  - Requirement: Manual Handoff for Policy-Excluded Lanes
  - Files: `skills/tests/parallel-infrastructure/test_headless_handoff.py`, `skills/parallel-infrastructure/scripts/review_dispatcher.py`
  - Dependencies: 3.4

## 4. Metered replacement lanes

- [ ] 4.1 Add `google` to `credential_vendors` and an `antigravity-remote` agent with an `sdk` block (`google` package); cover with a registry test and a `_call_google` dispatch test using an injected client.
  - Requirement: Subscription Headless Dispatch Gate (scenario: denied lane falls through to SDK)
  - Files: `agent-coordinator/agents.yaml`, `agent-coordinator/tests/test_agents_config_headless_auth.py`, `skills/tests/parallel-infrastructure/test_headless_auth_gate.py`
  - Dependencies: 2.3, 3.2
- [ ] 4.2 Refresh `claude-remote`'s SDK model and fallbacks to current model IDs and confirm it is selected when `claude-local` is denied.
  - Requirement: Subscription Headless Dispatch Gate
  - Files: `agent-coordinator/agents.yaml`
  - Dependencies: 4.1
- [ ] 4.3 Empirical probe: with a stored `claude` login present and `ANTHROPIC_API_KEY` set, determine which credential `claude --print` uses. Record the finding in `design.md`. Add a `claude-api-local` lane (`auth: api_key`) only if the key is used.
  - Requirement: Credential Isolation by Lane Auth
  - Files: `openspec/changes/add-headless-auth-policy/design.md`, `agent-coordinator/agents.yaml`
  - Dependencies: 4.2
- [ ] 4.4 After 1.1, add the confirmed vendors to `policies.subscription_headless.allow` with `basis` and `reviewed`.
  - Requirement: Declarative Lane Auth and Subscription Headless Policy
  - Files: `agent-coordinator/agents.yaml`
  - Dependencies: 1.1, 4.3

## 5. Vendor UX

- [ ] 5.1 Tests then implementation: `vendor_health.py` reports `auth`, `headless_dispatch`, replacement route and stale-review warning, in table and `--json`.
  - Requirement: Headless Auth Policy Reporting; Health Check Dimensions
  - Files: `skills/tests/parallel-infrastructure/test_vendor_health.py`, `skills/parallel-infrastructure/scripts/vendor_health.py`
  - Dependencies: 3.2
- [ ] 5.2 Tests then implementation: `/quick-task` refuses a named denied lane, supports `--handoff`, and skips denied lanes by default.
  - Requirement: Quick Task Honors Headless Auth Policy
  - Files: `skills/tests/quick-task/test_quick_task_headless_policy.py`, `skills/quick-task/scripts/quick_task.py`
  - Dependencies: 3.6
- [ ] 5.3 Update skill instructions for the new report columns, the refusal message and `--handoff`.
  - Requirement: Headless Auth Policy Reporting; Quick Task Honors Headless Auth Policy
  - Files: `skills/quick-task/SKILL.md`, `skills/vendor-status/SKILL.md`
  - Dependencies: 5.1, 5.2

## 6. Documentation and rollout

- [ ] 6.1 Document the operating model (interactive on subscription, automated on allowed CLIs / API keys / gateway, manual handoff) and extend the data-sharing grant to name the Anthropic and Google APIs.
  - Requirement: Manual Handoff for Policy-Excluded Lanes
  - Files: `docs/guides/workflow.md`, `AGENTS.md`
  - Dependencies: 4.4
- [ ] 6.2 Run `openspec validate add-headless-auth-policy --strict`, both test suites, `ruff` and `mypy`; run `/vendor-status` on the workstation and confirm quorum with the final allow list.
  - Requirement: Subscription Headless Dispatch Gate
  - Files: none
  - Dependencies: all above
