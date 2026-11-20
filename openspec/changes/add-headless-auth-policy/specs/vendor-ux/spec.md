## ADDED Requirements

### Requirement: Headless Auth Policy Reporting

For each CLI lane, `vendor_health.py` SHALL report the lane's declared `auth` and a
`headless_dispatch` value of `allowed`, `denied_by_policy`, or `not_applicable` (for `none`). For a
vendor with at least one lane denied by policy it SHALL report which lane, if any, will carry
headless dispatch instead. For each `policies.subscription_headless.allow` entry whose `reviewed`
date is older than `review_after_days`, it SHALL emit a warning naming the vendor and the date; a
stale entry SHALL NOT change the lane's `headless_dispatch` value or the exit code. `--json`
output SHALL carry the same fields.

#### Scenario: A denied lane is reported with its replacement
- **WHEN** `claude-local` is denied by policy and `claude-remote`'s SDK lane can dispatch
- **THEN** the report SHALL show `claude-local` as `denied_by_policy` and name `claude-remote` (`sdk`) as the headless route

#### Scenario: A denied vendor with no replacement is reported as having no headless route
- **WHEN** `antigravity-local` is denied by policy and the vendor has no other lane that can dispatch
- **THEN** the report SHALL show the vendor's headless route as none

#### Scenario: A stale terms review produces a warning only
- **WHEN** the allow entry for `codex` has `reviewed` 200 days in the past and `review_after_days` is 180
- **THEN** the report SHALL contain a warning naming `codex` and the review date
- **AND** `codex-local` SHALL still be reported as `allowed`

### Requirement: Quick Task Honors Headless Auth Policy

`/quick-task` SHALL NOT dispatch to a lane excluded by the subscription headless dispatch gate,
including when that lane is named with `--vendor`. When the named lane is excluded it SHALL exit
non-zero with a message naming the policy and the `--handoff` option, and SHALL NOT substitute a
different vendor. With `--handoff` it SHALL write the handoff file for the named or first excluded
lane, print its path, and exit zero without starting a vendor CLI.

#### Scenario: An explicitly named denied vendor is refused
- **WHEN** the user invokes `/quick-task --vendor claude-local "list files"` and `claude-local` is denied by policy
- **THEN** the command SHALL exit non-zero, name `policy_subscription_headless_denied`, and start no subprocess

#### Scenario: Handoff for a named denied vendor
- **WHEN** the user invokes `/quick-task --vendor claude-local --handoff "list files"`
- **THEN** a handoff file SHALL be written and its path printed

#### Scenario: Default selection skips denied lanes
- **WHEN** no `--vendor` is given and the first lane in roster order is denied by policy
- **THEN** the task SHALL be dispatched to the first lane that is not excluded

## MODIFIED Requirements

### Requirement: Health Check Dimensions

For each vendor in `agents.yaml`, the health check SHALL verify:
- **CLI availability, capability, and auth**: from the shared tiered probe (`vendor_probe.py`) — L0 presence, per-mode L1 capability, and L2 auth (requirement *Health Check Delegates to the Tiered Probe*)
- **API key resolution**: `ApiKeyResolver` can resolve a key (OpenBao or env var)
- **Dispatch modes**: Which modes have `can_dispatch()` returning true and pass L1
- **Model access**: Lightweight endpoint probe (vendor-specific) confirms model availability
- **Headless auth policy**: each CLI lane's declared `auth` and whether headless dispatch is allowed (requirement *Headless Auth Policy Reporting*)

#### Scenario: Health check verifies all dimensions

- **WHEN** the health check runs for a vendor with its CLI installed and an API key configured
- **THEN** all five dimensions (CLI availability/capability/auth, API key, modes, model, headless auth policy) SHALL be reported

#### Scenario: A lane denied by policy is not reported as a dispatchable mode

- **WHEN** a subscription lane passes L0 through L2 and its vendor is not in the allow list
- **THEN** the health check SHALL report the lane as `denied_by_policy` and SHALL NOT list any of its modes as dispatchable
