## ADDED Requirements

### Requirement: Subscription Headless Dispatch Gate

`discover_reviewers` SHALL NOT select a CLI lane whose `cli.auth` is `subscription` unless the
lane's `policy_vendor` appears in `policies.subscription_headless.allow`. A CLI lane whose
dispatch configuration carries no `auth` value SHALL be treated as `subscription`, and an absent
`policies.subscription_headless` block SHALL be treated as an empty allow list. The gate SHALL be
evaluated before tier selection and on every discovery; its outcome SHALL NOT be read from or
written to the probe cache, and `AGENTIC_PROBE_IGNORE_CACHE=1` SHALL NOT disable it. Each excluded
lane SHALL be logged and recorded in `last_exclusions` and in the review manifest's
`excluded_lanes` as `{vendor, mode, reason: "policy_subscription_headless_denied", since: null}`.
After a policy exclusion the vendor's remaining lanes (SDK, `api_key` CLI, OpenAI-compatible)
SHALL be considered in the existing tier order, and when none can dispatch the vendor SHALL be
skipped. No environment variable or command-line option SHALL re-enable an excluded lane.
`--check-vendors` SHALL report an excluded lane under `unverified` with the same reason and SHALL
NOT count it toward `--min-vendors`.

#### Scenario: A denied subscription lane falls through to the vendor's SDK lane
- **WHEN** `claude-local` declares `auth: subscription`, `claude` is not in the allow list, the `claude` binary is on `PATH`, and `claude-remote` has an SDK block whose API key resolves
- **THEN** `discover_reviewers` SHALL return the `claude_code` reviewer with `dispatch_tier` `sdk`
- **AND** `last_exclusions` SHALL contain `claude-local` with reason `policy_subscription_headless_denied`

#### Scenario: A denied vendor with no metered lane is skipped
- **WHEN** `antigravity-local` declares `auth: subscription`, `antigravity` is not in the allow list, and no SDK or OpenAI-compatible lane exists for that vendor
- **THEN** `discover_reviewers` SHALL return no reviewer for `antigravity`
- **AND** no `agy` subprocess SHALL be started

#### Scenario: An allowed subscription lane is selected as before
- **WHEN** `grok-local` declares `auth: subscription` and `grok` is in the allow list
- **THEN** `discover_reviewers` SHALL return `grok-local` with `dispatch_tier` `cli`

#### Scenario: A lane with no auth value is denied
- **WHEN** a dispatch configuration from an older coordinator carries a `cli` block with no `auth` key and the lane's vendor is not in the allow list
- **THEN** the lane SHALL be excluded with reason `policy_subscription_headless_denied`

#### Scenario: The gate cannot be bypassed from the environment
- **WHEN** `AGENTIC_PROBE_IGNORE_CACHE=1` is set and a subscription lane's vendor is not in the allow list
- **THEN** the lane SHALL still be excluded

#### Scenario: Check-vendors does not count a policy-excluded lane
- **WHEN** `--check-vendors --json --min-vendors 2` runs with one allowed lane verified and one lane excluded by policy
- **THEN** the excluded lane SHALL appear under `unverified` with reason `policy_subscription_headless_denied` and the process SHALL exit 2

### Requirement: Credential Isolation by Lane Auth

`vendor_subprocess_env` SHALL build a CLI lane's environment according to its `cli.auth`. For a
`subscription` lane it SHALL omit `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY`,
`GEMINI_API_KEY`, `GOOGLE_API_KEY`, and `XAI_API_KEY` even when the vendor prefix allowlist or
`REVIEW_DISPATCH_ENV_PASSTHROUGH` would otherwise pass them. For an `api_key` lane it SHALL pass
the lane's declared `api_key_env` and SHALL omit every other name in that list. `can_dispatch`
SHALL return false for an `api_key` lane whose declared variable is unset or empty. A `none` lane's
environment SHALL be unchanged by this requirement.

#### Scenario: A subscription lane never receives an API key
- **WHEN** `OPENAI_API_KEY` is set and `codex-local` declares `auth: subscription`
- **THEN** the environment built for `codex-local` SHALL NOT contain `OPENAI_API_KEY`

#### Scenario: Passthrough cannot re-add a key to a subscription lane
- **WHEN** `REVIEW_DISPATCH_ENV_PASSTHROUGH=XAI_API_KEY` is set and `grok-local` declares `auth: subscription`
- **THEN** the environment built for `grok-local` SHALL NOT contain `XAI_API_KEY`

#### Scenario: An API-key lane without its key cannot dispatch
- **WHEN** a CLI lane declares `auth: api_key` and `api_key_env: ANTHROPIC_API_KEY`, and that variable is unset
- **THEN** `can_dispatch` SHALL return false for every mode

#### Scenario: An API-key lane receives only its own key
- **WHEN** `pi-local` declares `auth: api_key` with `api_key_env: OPENROUTER_API_KEY`, and both `OPENROUTER_API_KEY` and `OPENAI_API_KEY` are set
- **THEN** the environment built for `pi-local` SHALL contain `OPENROUTER_API_KEY` and SHALL NOT contain `OPENAI_API_KEY`

### Requirement: Probe Auth Follows Lane Credential

For a CLI lane declaring `auth: api_key`, the tiered probe's L2 SHALL be `auth_ok` when the lane's
declared `api_key_env` variable is set and non-empty and `auth_failed` otherwise, and SHALL NOT run
the lane's `auth_status_args` or inspect its `credential_files`. The probe SHALL NOT print, log,
cache, or return the variable's value. Lanes declaring `subscription` or `none` SHALL keep the
existing L2 method.

#### Scenario: An API-key lane is auth_ok on key presence alone
- **WHEN** a lane declares `auth: api_key`, its key variable is set, and its `auth_status_args` command would exit 1
- **THEN** the probe SHALL report L2 `auth_ok` and SHALL NOT have run the status command

#### Scenario: An API-key lane without its key fails L2
- **WHEN** a lane declares `auth: api_key` and its key variable is unset
- **THEN** the probe SHALL report L2 `auth_failed`

#### Scenario: The key value is not disclosed
- **WHEN** the key variable holds `sk-test-SENTINEL-1234567890` and the probe runs with `--json`
- **THEN** the sentinel SHALL NOT appear in stdout, stderr, or the probe cache file

### Requirement: Manual Handoff for Policy-Excluded Lanes

`review_dispatcher.py` SHALL accept `--handoff`. When set, for each lane excluded with reason
`policy_subscription_headless_denied` it SHALL write `handoffs/<agent_id>-<mode>.md` under the
change or output directory containing the full prompt, the exact command a human would run, and a
statement that results are not ingested automatically. It SHALL NOT start the lane's CLI. A handoff
SHALL NOT count toward quorum and SHALL NOT appear as a reviewer result; the manifest SHALL list
written handoffs under `handoffs` as `{vendor, mode, path}`. Without `--handoff` no handoff file
SHALL be written.

#### Scenario: A handoff file is written for a denied lane
- **WHEN** `--handoff` is set and `claude-local` is excluded by policy for mode `review`
- **THEN** `handoffs/claude-local-review.md` SHALL exist and contain the prompt and the `claude` command line
- **AND** no `claude` subprocess SHALL have been started

#### Scenario: A handoff does not satisfy quorum
- **WHEN** `--handoff` is set, one lane dispatches successfully, one handoff is written, and `min_quorum` is 2
- **THEN** the round SHALL be reported below quorum

#### Scenario: No handoff without the flag
- **WHEN** `--handoff` is not set and a lane is excluded by policy
- **THEN** no file SHALL be written under `handoffs/`

## MODIFIED Requirements

### Requirement: OpenAI-Compatible Dispatcher Discovery

The review dispatcher SHALL construct an OpenAI-compatible adapter for configured `local` or
`openrouter` endpoints with a `base_url` after CLI and SDK discovery. A usable CLI SHALL retain
precedence over the endpoint adapter for the same agent, except that a CLI lane excluded by the
*Subscription Headless Dispatch Gate* is not usable and SHALL NOT take precedence.

#### Scenario: Endpoint-only agent is discoverable

- **WHEN** dispatch configuration contains a local/OpenRouter endpoint with no CLI or SDK block
- **THEN** review discovery SHALL return an OpenAI-compatible reviewer for that endpoint

#### Scenario: CLI retains precedence

- **WHEN** an agent has both a usable CLI and an OpenAI-compatible endpoint
- **THEN** review discovery SHALL select the CLI tier first

#### Scenario: A policy-excluded CLI yields to the endpoint

- **WHEN** a vendor has a `subscription` CLI lane excluded by policy and an OpenAI-compatible endpoint that can dispatch
- **THEN** review discovery SHALL select the OpenAI-compatible tier for that vendor
