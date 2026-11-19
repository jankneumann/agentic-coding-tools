# Vendor Auth Audit

Which credential each vendor CLI may use in each lane, and how each CLI stores
and refreshes that credential. Retrieved 2026-11-19.

The data is in [`vendor-auth-audit.yaml`](vendor-auth-audit.yaml). This page
explains it. Where the two disagree, the YAML is right and a test fails
(`skills/tests/vendor-status/`).

**This is an engineering reading of published text, not legal advice.**

## What was and was not read

| Vendor | Read in the page's own text | Not reachable from where the audit ran |
|---|---|---|
| `claude` | Claude Code documentation, Consumer Terms, Usage Policy, two support articles | — |
| `codex` | The `openai/codex` and `openai/codex-action` repositories | `openai.com`, `developers.openai.com`, `help.openai.com` |
| `antigravity` | The `google-antigravity/antigravity-cli` README and changelog | `antigravity.google`, `ai.google.dev`, `policies.google.com` |
| `grok` | The documentation embedded in npm `@xai-official/grok` 1.0.89 | `x.ai`, `docs.x.ai` |

For three of the four vendors, no licence text was read directly. Their
verdicts rest on product documentation, which shows what the vendor supports,
not what its terms allow. Each lane's `source_kind` in the YAML says which
kind of text it rests on.

A quote marked `raw` was read in the page's or file's own text. A quote marked
`summarised` came through a tool that summarises pages: it is a paraphrase and
is not verified. Do not rely on a `summarised` row for a decision that risks
an account. To close these gaps, allow the hosts above in the environment's
network settings, or paste the pages, and re-run the audit.

## Lanes

- `interactive`: the operator at the CLI's own prompt.
- `attended_headless`: a non-interactive run (`claude -p`, `codex exec`,
  `agy -p`, `grok -p`) started from a session the operator is running.
- `unattended_daemon`: an always-on worker with no operator session.
- `ci`: a hosted runner.

## Verdicts

`permitted` and `prohibited` mean a sentence says so. `unaddressed` means the
pages listed under `searched` in the YAML say nothing about the lane. An
unattended lane that is not `permitted` uses a keyed lane instead: silence is
not treated as permission, because the cost of guessing wrong is the account
every other lane uses.

| Vendor | Lane | Subscription | Quote | Use instead | Basis |
|---|---|---|---|---|---|
| `claude` | `interactive` | permitted | `raw` | | OAuth "is designed to support ordinary use of Claude Code" |
| `claude` | `attended_headless` | permitted | `raw` | | "`claude -p` still draw[s] from your subscription limits". Fan-out from an orchestrator is not addressed |
| `claude` | `unattended_daemon` | unaddressed | | `api-key` | Nothing mentions an always-on worker; "ordinary, individual usage" is undefined |
| `claude` | `ci` | permitted | `raw` | | A `claude setup-token` token as `CLAUDE_CODE_OAUTH_TOKEN`, documented for GitHub Actions |
| `codex` | `interactive` | permitted | `raw` | | README recommends ChatGPT sign-in |
| `codex` | `attended_headless` | permitted | `raw` | | "`codex exec` will use the same authentication method", from documentation at a superseded tag |
| `codex` | `unattended_daemon` | unaddressed | | `api-key` | Nothing found; two of the pages searched were not read directly |
| `codex` | `ci` | permitted | `summarised` | `api-key` | An "advanced" path for trusted private runners, relayed and not verified. Use a key until the page is read |
| `antigravity` | `interactive` | permitted | `raw` | | README: keyring, then Google Sign-In |
| `antigravity` | `attended_headless` | permitted | `summarised` | | Relayed FAQ. **Not cleared for orchestrator dispatch**; see below |
| `antigravity` | `unattended_daemon` | unaddressed | | `api-key` | Nothing found |
| `antigravity` | `ci` | unaddressed | | `api-key` | No environment-variable subscription credential exists |
| `grok` | `interactive` | permitted | `raw` | | Embedded documentation: browser sign-in with grok.com |
| `grok` | `attended_headless` | permitted | `raw` | | "cached credentials are used automatically". Product documentation only |
| `grok` | `unattended_daemon` | unaddressed | | `api-key` | Documentation points automation to an API key |
| `grok` | `ci` | unaddressed | | `api-key` | "`XAI_API_KEY`: simplest for CI" |

### Conditions that change how a lane is used

- **Antigravity, attended headless.** The relayed FAQ says headless mode is for
  direct scripting and CI, and that wrapping `agy` inside third-party coding
  agents or applications is not supported under consumer plans, with account
  suspension as the consequence. This repository's orchestrator launches `agy`
  from inside another vendor's coding agent. Whether that is "wrapping" is
  undecided. The changelog confirms that accounts are blocked for terms
  violations. Read the FAQ in its own text before dispatching `agy` on a
  subscription.
- **Claude, CI and attended headless.** `--bare` never reads OAuth credentials
  or `CLAUDE_CODE_OAUTH_TOKEN`, and the documentation says it "will become the
  default for `-p` in a future release". `ANTHROPIC_API_KEY`, when set, is used
  instead of the subscription in `-p` mode. A dispatch that must stay on the
  subscription has to leave the key unset and not pass `--bare`.
- **Codex, CI.** Refresh tokens rotate. Two jobs that share one `auth.json`
  invalidate each other, so the relayed guidance is one file per machine or
  serialized job stream.
- **Grok, any keyed lane.** A stored session token takes precedence over
  `XAI_API_KEY`. Where `~/.grok/auth.json` exists, setting the key does not
  switch lanes; run `grok logout` or point `GROK_HOME` elsewhere.

## Credential mechanics

Every row below is `documented` or `not_observed`. None is `observed`: only the
Claude CLI was installed where the audit ran, and credential files were not
read there. These mechanics are **not yet observed** on a host, and a later
roadmap item that binds or injects a credential should not depend on a row
until it is.

| Vendor | Field | Evidence | What the source says |
|---|---|---|---|
| `claude` | `credential_material` | documented | macOS Keychain; on Linux `~/.claude/.credentials.json`, mode 0600. `CLAUDE_CONFIG_DIR` moves it |
| `claude` | `refresh_writes` | documented | Yes for a saved login, under a shared lock. `CLAUDE_CODE_OAUTH_TOKEN` is not refreshed |
| `claude` | `hosts` | documented | `api.anthropic.com`, `platform.claude.com`, `claude.ai`, `claude.com` |
| `claude` | `proxy_override` | documented | `HTTPS_PROXY`; `ANTHROPIC_BASE_URL`. No SOCKS |
| `codex` | `credential_material` | documented | `$CODEX_HOME/auth.json`, or the OS keyring by setting |
| `codex` | `refresh_writes` | documented | Yes, by file replacement, so the directory must be writable. From source code |
| `codex` | `hosts` | documented | `chatgpt.com`, `auth.openai.com`; `api.openai.com` with a key. From source code |
| `codex` | `proxy_override` | documented | `openai_base_url`. Its effect under ChatGPT login is an inference |
| `antigravity` | `credential_material` | documented | OS keyring; file storage where there is no D-Bus session. File path not documented |
| `antigravity` | `refresh_writes` | documented | Yes, five minutes before expiry |
| `antigravity` | `hosts` | not_observed | No host list found for a consumer login |
| `antigravity` | `proxy_override` | documented | Key mode only (`GOOGLE_GEMINI_BASE_URL`). None found for subscription login |
| `grok` | `credential_material` | documented | `~/.grok/auth.json`, mode 0600. `GROK_HOME` moves it |
| `grok` | `refresh_writes` | documented | Yes, in the background, with lock files beside the credential |
| `grok` | `hosts` | documented | `cli-chat-proxy.grok.com`, `auth.x.ai`, `accounts.x.ai`, `api.x.ai` |
| `grok` | `proxy_override` | documented | `GROK_CLI_CHAT_PROXY_BASE_URL`, documented for enterprise OIDC only |

Three consequences for sandbox design follow from the documented rows:

- A read-only bind of a login store cannot refresh. All four CLIs write when
  they refresh, and Codex and Grok need the directory writable, not only the
  file.
- A refresh inside a sandbox changes the host's login. Claude and Codex state
  that a refresh token works once, so a copy of the file goes stale as soon as
  either side refreshes.
- Antigravity falls back to file storage in a container, at a path that is not
  documented. It has to be observed before it can be bound.

## Observing a host

Run these on a machine where the vendor CLI is signed in. The script prints
metadata only. It calls `lstat` and lists directories; it never opens a
credential file, so its output is safe to paste.

Where the credential is, and its mode:

```bash
python3 skills/vendor-status/scripts/observe_vendor_auth.py codex
```

Whether a run writes to it:

```bash
python3 skills/vendor-status/scripts/observe_vendor_auth.py codex --watch -- codex exec "say ok"
```

`changed: <path>` names each path whose type, mode, size or modification time
differs after the command. `changed: none` means no candidate path changed,
which does not prove the CLI never refreshes: tokens refresh only near expiry,
so repeat the run after the access token's lifetime has passed. On macOS a
keychain write is invisible to this script.

Hosts are not captured by the script. Capture them by hand:

- Linux: `strace -f -e trace=connect -o /tmp/connect.log <command>`, then
  resolve the addresses, or run the command with `HTTPS_PROXY` pointing at a
  logging proxy and read the `CONNECT` lines. A CLI that ignores the proxy
  shows up as a missing host, which is itself the answer for `proxy_override`.
- macOS: `sudo tcpdump -n -i any port 443` during the command, or the same
  logging proxy.

Record what you see in the YAML: set the field's `evidence` to `observed` and
add `observed_on` (the date) and `observed_host_os`. Task 4.1 of the change
`audit-vendor-headless-auth-and-terms` stays open until that is done for each
vendor.

## Related

- [Claude: subscription login or API key, per lane](../../openspec/roadmaps/sandboxed-flow/claude-auth-strategy.md):
  the strategy this audit feeds.
- [Lead-Session Sandbox](lead-session-sandbox.md): the sandbox whose credential
  rules depend on these mechanics.
