# Claude: subscription login or API key, per lane

*Research note, 2026-11-19. Input to `sandboxed-flow` ri-02 (vendor audit) and
ri-03 (credential profile). Covers Claude only; Codex, Antigravity and Grok
terms are still to be audited under ri-02.*

**This is an engineering reading of published terms, not legal advice.** The
quotes were extracted through a fetch tool that summarises pages, then
re-fetched to confirm; the raw HTML was not inspected. ri-02 must re-verify
each quote against the live page before any lane depends on it.

## What the text says

The working assumption in this repository was "subscription for interactive
use, API key for automation". The published text does not draw the line
there. It draws it between **your own use of the official client** and
**anything that shares, proxies or intermediates a subscription credential**.

Explicitly permitted on a subscription:

- Headless runs. "When you're signed in with your Claude plan, the Claude
  Agent SDK and claude -p still draw from your subscription limits."
  ([support article 15036540](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan), update of 2026-10-07)
- Scripts and CI through a purpose-made token. "For CI pipelines, scripts, or
  other environments where interactive browser login isn't available,
  generate a one-year OAuth token with claude setup-token." That token "can
  only make model requests".
  ([authentication](https://code.claude.com/docs/en/authentication.md))
- Cloud sessions and Anthropic-hosted scheduled tasks, which "always use your
  subscription credentials"; an API key set in the cloud environment does not
  override them. ([authentication](https://code.claude.com/docs/en/authentication.md),
  [routines](https://code.claude.com/docs/en/routines.md))

Explicitly prohibited on a subscription:

- "Anthropic does not permit third-party developers to offer Claude.ai login
  into their own applications, or to route requests through Free, Pro, Max, or
  Ultra plan credentials on behalf of their users. Moreover, developers may
  not collect, store, or intermediate Claude.ai credentials or session
  tokens." ([legal and compliance](https://code.claude.com/docs/en/legal-and-compliance.md))
- "Resell, proxy, or otherwise provide access to Claude through unauthorized
  means", including "services that route requests through consumer
  subscriptions". ([usage policy](https://www.anthropic.com/legal/aup), effective 2026-11-12)
- Sharing account credentials with anyone else.
  ([consumer terms](https://www.anthropic.com/legal/consumer-terms), section 2)

The ceiling, and the ambiguity:

- OAuth "is designed to support ordinary use of Claude Code and other native
  Anthropic applications", and plan limits "assume ordinary, individual usage
  of Claude Code and the Agent SDK". "Ordinary, individual" is not defined.
- The consumer terms forbid access "through automated or non-human means"
  except with an API key "or where we otherwise explicitly permit it". The
  support article and the `setup-token` documentation are the explicit
  permissions for `claude -p`, scripts and CI. No text addresses an
  always-on dispatcher daemon on the operator's own machine, an orchestrator
  that spawns many `claude` workers, or reading the login file out of
  `~/.claude` for one's own scripts.
- Anthropic "reserves the right to take measures to enforce these
  restrictions and may do so without prior notice". The cost of guessing wrong
  in an ambiguous lane is loss of the subscription that every lane uses.

Relevant to cost: Max, Ultra and Team plans include monthly API credits that
cover `claude -p` and the Agent SDK when run with an API key from the linked
Console organisation; Pro does not.
([support article 17154008](https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-ultra-and-team-plans))

## Strategy

The rule: use the subscription where the text permits the lane in terms; use
an API key where the text is silent and the lane runs without the operator;
never handle the subscription credential in a way the text prohibits.

| Lane | Auth | Basis |
|---|---|---|
| Interactive lead session, laptop and GX10 | Subscription login, unmodified binary | Permitted in terms |
| Cloud sessions and Anthropic-hosted scheduled tasks | Subscription | The only option; API keys are ignored there |
| Sandboxed `claude -p` implementer or reviewer dispatched from a session the operator is running | Subscription, through a `claude setup-token` token passed as `CLAUDE_CODE_OAUTH_TOKEN` | Headless use and scripts are permitted in terms; the operator is the individual user. Bounded by a concurrency cap (below) |
| GitHub Actions on the operator's own repositories | `setup-token` token as a repository secret | Documented by Anthropic for CI |
| Always-on dispatcher daemon, review worker with no operator session | **API key**, funded first by the plan's monthly API credits | Text is silent; "ordinary, individual usage" is the undefined ceiling; an account action here would take every other lane with it |
| Any second human principal (team mode) | API key per principal, never a shared subscription | Credential sharing and shared-secret use are prohibited or advised against in terms |

Credential handling rules, which bind the roadmap items:

1. **Do not bind `~/.claude` into a sandbox.** Pass a `setup-token` token as an
   environment variable instead. It is the documented mechanism, and it is a
   narrower credential than the login file: it can make model requests and
   nothing else, so a sandbox escape yields less. This changes ri-03: the
   Claude profile is an environment-variable grant, not a file bind.
2. **Do not put a Claude subscription token behind an injecting proxy.** The
   text forbids intermediating session tokens and proxying consumer
   subscriptions; whether that reaches a personal single-user proxy is
   unstated, and nothing is gained over rule 1. This narrows ri-07: for
   Claude, boundary injection is tested with an API key only.
3. **Do not store a subscription token in the coordinator or OpenBao.** Those
   hold API keys and gateway keys. The subscription token lives in the
   operator's own environment or keychain and in the operator's own CI
   secrets.
4. **Do not distribute tooling that asks other people for a claude.ai login.**
   Anyone else running this repository signs in to their own unmodified
   binary or supplies their own API key.
5. **Cap subscription-authenticated workers.** A per-host limit on concurrent
   `claude -p` dispatches under the subscription, with overflow routed to the
   API-key lane, keeps use arguably "ordinary, individual". The operator
   set it at five; the text gives no number.
6. **Record the auth mode on every dispatch**, so that a change in Anthropic's
   terms can be answered by a routing change and an audit query, not a code
   change.

## What this changes in the repository

- `docs/proposals/factory-local-cloud-split.md` states that the Claude review
  lane uses an API key "in line with the subscription terms". That remains the
  right choice for the unattended review worker, but the reason is the
  undefined ceiling and the daemon's silence in the text, not a prohibition on
  headless use. ri-02 should correct the wording when it lands the audit.
- Bare mode (`claude --bare`) never reads OAuth credentials, so any dispatch
  argv that uses it must be on the API-key lane.

## Operator decisions (2026-11-19)

1. Attended orchestrator-spawned Claude workers authenticate with the
   subscription, through a `setup-token` value.
2. The concurrency cap is five subscription-authenticated `claude -p`
   dispatches per host; overflow goes to the API-key lane.
3. No written request to Anthropic support for now. The always-on daemon and
   the unattended review worker stay on the API key.
