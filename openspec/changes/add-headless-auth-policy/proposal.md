# Add headless auth policy for vendor dispatch

> Change ID: `add-headless-auth-policy`
> Status: Draft (proposal, design, spec deltas, tasks; not yet run through `/plan-feature` review)
> Created: 2026-11-20
> Effort: M
> Layers: Execution (dispatcher, probe, quick-task), Trust (agents.yaml policy), Governance (decision record)

## Why

Review and quick-task dispatch selects one route per vendor in the order
local CLI → SDK → OpenAI-compatible endpoint → skip
(`skills/parallel-infrastructure/scripts/review_dispatcher.py`, `discover_reviewers`).
A logged-in vendor CLI therefore always wins, and every vendor CLI lane in
`agent-coordinator/agents.yaml` except `pi-local` authenticates with the maintainer's
flat-rate consumer subscription. The effect is that an orchestrating agent
shells out to `claude --print`, `agy --prompt`, `codex exec` and `grok --prompt-file`
on subscription credentials, unattended and in parallel.

Vendors treat that pattern differently. A third-party summary of the consumer terms
(recorded in `design.md`, **not yet verified against the primary sources**) reads
them as:

| Vendor | Headless CLI on a consumer subscription, driven by another agent |
|---|---|
| Anthropic (`claude`) | Restricted: automated access expected to use an API key |
| Google (`agy` / Gemini) | Restricted: treated as wrapping the CLI in a third-party agent |
| OpenAI (`codex`) | Not explicitly addressed; general automated-use clause applies |
| xAI (`grok`) | Marketed for scripts and orchestration under the subscription |

Whatever the exact reading turns out to be, the repository has no way to express it.
Nothing in `agents.yaml` says which credential a CLI lane uses, nothing says for which
vendors unattended subscription use is acceptable, and the tier order actively prefers
the riskiest route. Account suspension on a primary subscription is a high-cost,
hard-to-reverse outcome, so the default has to be closed.

## What Changes

1. **Declare the credential each CLI lane uses.** Every `cli` block gains a required
   `auth` field: `subscription`, `api_key`, or `none`.
2. **Declare where unattended subscription use is allowed.** A new
   `policies.subscription_headless` block lists the `policy_vendor`s allowed to be
   dispatched headlessly on a subscription, each with a `basis` and a `reviewed` date.
   Anything not listed is denied. Initial allow list: `codex`, `grok`
   (subject to task 1.1 confirming the terms).
3. **Gate discovery on the policy.** `discover_reviewers` never selects a
   `subscription` CLI lane whose vendor is not allowed. It falls through to that
   vendor's API-key lanes (SDK, API-key CLI, OpenAI-compatible) or skips the vendor.
   It never falls back to the subscription CLI. **BREAKING** for anyone relying on
   `claude-local` or `antigravity-local` as headless reviewers.
4. **Isolate credentials in the subprocess environment.** A `subscription` lane's
   environment has the vendor's API-key variables removed, so a subscription run cannot
   silently bill the API. An `api_key` lane requires its declared key and fails closed
   without it.
5. **Provide metered replacements for the two denied vendors.** Add a Gemini SDK lane
   (`google` joins `credential_vendors`); Claude keeps its existing `claude-remote` SDK
   lane. An API-key Claude CLI lane is added only if an empirical probe shows the CLI
   uses the key and not the stored login (task 4.3).
6. **Offer a manual handoff for denied lanes.** `--handoff` writes the prompt and the
   exact command to a file for the human to run in their own terminal. A handoff does
   not count toward quorum.
7. **Make the policy visible.** `vendor_health.py`, `/vendor-status`,
   `--check-vendors` and the review manifest report each lane's `auth` and, for a
   policy exclusion, the reason `policy_subscription_headless_denied`.

The intended operating model after this change:

| Use | Route |
|---|---|
| Human starts and steers a plan | Claude Code or Gemini/Antigravity CLI or app, interactive, on subscription |
| Host-native sub-agents (`Agent(...)`) | Unchanged; inside the vendor's own product |
| Automated review / quick-task fan-out | Codex and Grok CLIs on subscription; pi and OpenAI-compatible lanes via OpenRouter; Claude and Gemini via API key |
| Work the human wants on Claude or Gemini quota | Manual handoff file |

## Non-Goals

- No runtime override (environment variable or flag) that re-enables a denied
  subscription lane. The policy changes only by editing `agents.yaml`.
- No change to host-native sub-agent dispatch or to coordinator work-queue claiming.
  Whether long-running queue workers on subscription CLIs need the same gate is an
  open question in `design.md`.
- No new throttle. Subscription lanes keep the existing quota-window throttle
  (model-routing decision D4).
- No new cost table. Metered Claude/Gemini spend is recorded by the usage ledger from
  `add-model-usage-ledger`; this change only depends on it.

## Impact

Affected specs (one delta file each):

- `parallel-infrastructure` — `specs/parallel-infrastructure/spec.md`
- `agent-identity` — `specs/agent-identity/spec.md`
- `vendor-ux` — `specs/vendor-ux/spec.md`

Affected code:

- `agent-coordinator/agents.yaml`, `agent-coordinator/src/agents_config.py`
- `skills/parallel-infrastructure/scripts/review_dispatcher.py`, `vendor_probe.py`,
  `vendor_health.py`
- `skills/quick-task/scripts/quick_task.py`, `skills/quick-task/SKILL.md`,
  `skills/vendor-status/SKILL.md`
- `docs/decisions/`, `docs/guides/workflow.md`, `AGENTS.md` (data-sharing grant gains
  the Anthropic and Google APIs as named providers)

Related active changes:

- `openrouter-review-lane` — complementary; supplies non-CLI reviewer lanes that keep
  quorum when Claude and Gemini subscription lanes are denied. Both touch
  `discover_reviewers`; land sequentially.
- `add-live-vendor-capability-and-cost-registry` — `GET /vendors` should project the
  new `auth` field; additive.
- `add-dispatch-sandbox-enforcement`, `make-the-orchestrator-obey-the-router` — touch
  the dispatch path; no semantic conflict.
- `add-model-usage-ledger` — dependency for metered-spend visibility only.

## Quorum effect

On the maintainer's workstation with no Anthropic or Google API key configured, the
`review` roster becomes `codex`, `grok`, `pi` (and `ocr` when configured), which still
meets `min_quorum=2`. Cloud containers are unchanged: the temporary single-vendor
section of `TRUST_POSTURE.md` already governs them.

## Rollback

The gate is driven entirely by `agents.yaml`. To roll back behaviour without reverting
code, add the vendor to `policies.subscription_headless.allow`. To roll back fully,
revert the change; the `auth` field is additive and ignored by older dispatchers.
