# Claude: subscription login or API key, per lane

*Research note, 2026-11-19. Input to `sandboxed-flow` ri-03 (credential
profile). Covers Claude only. The audit of all four vendors is in
`docs/guides/vendor-auth-audit.md`.*

**This is an engineering reading of published terms, not legal advice.** The
quotes below were checked against the live pages on 2026-11-19, in each page's
own text, under ri-02. Where a quote was wrong or incomplete, it was corrected
here.

## What the text says

The working assumption in this repository was "subscription for interactive
use, API key for automation". The published text does not draw the line
there. It draws it between **your own use of the official client** and
**anything that shares, proxies or intermediates a subscription credential**.

Explicitly permitted on a subscription:

- Headless runs. "Nothing changes for your plan: when you're signed in with
  your Claude plan, the Claude Agent SDK and claude -p still draw from your
  subscription limits."
  ([support article 15036540](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan), update of 2026-10-07)
- Scripts and CI through a purpose-made token. "For CI pipelines, scripts, or
  other environments where interactive browser login isn't available,
  generate a one-year OAuth token with `claude setup-token`:" That token "can
  only make model requests".
  ([authentication](https://code.claude.com/docs/en/authentication.md))
- Cloud sessions, which "always use your subscription credentials"; an API key
  set in the cloud environment does not override them.
  ([authentication](https://code.claude.com/docs/en/authentication.md))
- Anthropic-hosted scheduled tasks. "`/schedule` requires a claude.ai
  subscription login." and "Scheduled tasks draw down subscription usage the
  same way interactive sessions do."
  ([routines](https://code.claude.com/docs/en/routines.md))

Explicitly prohibited on a subscription:

- "Anthropic does not permit third-party developers to offer Claude.ai login
  into their own applications, or to route requests through Free, Pro, Max, or
  Ultra plan credentials on behalf of their users. Moreover, developers may
  not collect, store, or intermediate Claude.ai credentials or session
  tokens." ([legal and compliance](https://code.claude.com/docs/en/legal-and-compliance.md))
  This sentence addresses people who build products. The same page says: "Nor
  does it prevent an end user from signing in to the unmodified Claude Code
  binary with their own Claude subscription".
- "Resell, proxy, or otherwise provide access to Claude through unauthorized
  means", including "services that route requests through consumer
  subscriptions". ([usage policy](https://www.anthropic.com/legal/aup), effective 2026-11-12)
- Sharing account credentials with anyone else.
  ([consumer terms](https://www.anthropic.com/legal/consumer-terms), section 2)

The ceiling, and the ambiguity:

- OAuth "is designed to support ordinary use of Claude Code and other native
  Anthropic applications". "Advertised usage limits for Pro, Max, and Ultra
  plans assume ordinary, individual usage of Claude Code and the Agent SDK."
  "Ordinary, individual" is not defined.
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
Console organisation. "Free, Pro, and Enterprise plans aren't eligible". Runs
from the GitHub Action, an IDE extension or the desktop app are not covered,
"even with -p".
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
   unstated, and nothing is gained over rule 1. The documentation does describe
   a pass-through gateway used with a saved claude.ai login: such a gateway
   "must forward `Authorization` and the OAuth capability in `anthropic-beta`"
   ([LLM gateway](https://code.claude.com/docs/en/llm-gateway.md)). That is a
   proxy that forwards the client's own header. A proxy that holds the token
   and adds it is not described anywhere. This narrows ri-07: for Claude,
   boundary injection is tested with an API key only.
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

- `docs/proposals/factory-local-cloud-split.md` stated that the Claude review
  lane uses an API key because the subscription terms require it. The API key
  remains the right choice for the unattended review worker, but the reason is
  the undefined ceiling and the text's silence about a daemon, not a
  prohibition on headless use. ri-02 corrected the wording there.
- Bare mode never reads the subscription. "In bare mode, Claude Code never
  reads OAuth credentials or the system keychain." A dispatch argv that uses
  `--bare` must be on the API-key lane. This will matter more later: "`--bare`
  is the recommended mode for scripted and SDK calls, and will become the
  default for `-p` in a future release."
  ([headless](https://code.claude.com/docs/en/headless.md)) When that happens,
  a subscription dispatch has to opt out of bare mode explicitly, and a test
  should fail if it does not.
- An API key outranks the `setup-token` token. "In non-interactive mode
  (`-p`), the key is always used when present."
  ([authentication](https://code.claude.com/docs/en/authentication.md)) A
  subscription dispatch must run with `ANTHROPIC_API_KEY` unset, or it bills
  the key without saying so.

## Operator decisions (2026-11-19)

1. Attended orchestrator-spawned Claude workers authenticate with the
   subscription, through a `setup-token` value.
2. The concurrency cap is five subscription-authenticated `claude -p`
   dispatches per host; overflow goes to the API-key lane.
3. No written request to Anthropic support for now. The always-on daemon and
   the unattended review worker stay on the API key.
