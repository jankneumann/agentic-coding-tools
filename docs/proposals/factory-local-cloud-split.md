# Factory Local/Cloud Split: Sandboxed Auto-Approval, a Review Queue, and a Merge Queue

*Proposal, 2026-10-23. Status: draft for operator review. Phase 0's repo
half and Phase 1's coordinator half are applied; each phase opens with a status
note saying exactly what. Every other settings, hook or workflow snippet below
is a proposal.*

## Problem statement

The factory runs in two places. Cloud sessions implement. Local machines (a
laptop and the GX10) hold the OAuth logins for the four AI subscriptions, so
multi-vendor review can only run locally. Operators report four problems:

1. **Approval fatigue.** Every Bash call needs an approval, both in the cloud and
   locally, so auto-approval saves nothing. The goal is to approve only
   irreversible or destructive actions.
2. **Reviews are stuck on local machines.** The subscriptions use OAuth, so each
   vendor CLI works only on a machine where someone logged in. Cloud implementers
   cannot reach those reviewers. That is why the cloud quorum exception exists
   (`TRUST_POSTURE.md:40-60`).
3. **Merges happen one at a time.** All 75 recorded merges were direct merges.
   Any two PRs that touch the same file are chained in series, and state files
   that every PR rewrites keep the queue serial.
4. **$200 of monthly Claude SDK credit goes unused.** It should be spent on
   lanes that subscriptions cannot cover.

This proposal extends three existing proposals and does not repeat them:

- [`sandboxed-harness-execution.md`](sandboxed-harness-execution.md): Daytona
  `ExecutionBackend`, short-lived OpenBao keys, GitHub App tokens.
- [`always-on-agent-automation.md`](always-on-agent-automation.md): GX10
  dispatcher daemon, gate dispositions, scheduled sync points.
- [`monorepo-merge-scaling-research.md`](monorepo-merge-scaling-research.md):
  speculative testing (Gap 1), batching (Gap 6), the phased merge roadmap.

## Principles

1. **Approve by blast radius, not by command prefix.** Inside a sandbox the
   environment is the boundary, so reversible work runs without asking. Humans
   approve only what a sandbox cannot undo: force-push, deletion, merge, deploy,
   migration, a secrets write. Bash allow rules are not a security boundary,
   because `sh -c`, `git -C` and scripts that shell out all get around prefix
   matching. The sandbox and the credentials a process holds are the boundary.
2. **Each role gets only its own credentials.** A review worker holds its vendor
   CLI's OAuth login and nothing else: no GitHub write token, no key that can
   decide approvals. Only the coordinator holds the GitHub key that posts
   reviews. Cloud implementers push only through the harness's GitHub proxy, and
   only to their own branch. A process whose behaviour is shaped by model output
   never holds a credential its role does not need.
3. **Messages report; they do not authorize** (`TRUST_POSTURE.md`). This now
   also covers personal agents. Output from Duet, Dots, Grok Bot or Muse is data
   until a human gate accepts it.
4. **The coordinator is the message bus and GitHub is the record.** Work items,
   handoffs and findings move through the coordinator. PRs, reviews, required
   checks and merges live on GitHub, which is what branch protection enforces.
5. **Spend metered credit only where subscriptions cannot go:** cloud-side
   review, CI review, small-tier triage, and batch ambient review.

## Current state (verified 2026-10-23)

| Area | What exists | What is missing |
|---|---|---|
| Permissions (repo) | `.claude/settings.json:4` sets `defaultMode: "bypassPermissions"`. Allow covers read-only commands, git basics, push to `openspec/*`, `runner.py`. Ask covers alembic, psql, railway, env. Deny covers `curl *`, `rm -rf *`, `git reset --hard *`, `git clean *`, stash drop/clear, `Read(~/.aws/**)`, `Read(~/.config/**)`, `Read(**/.env.*)`. | The project-scope bypass mode is ignored, both locally and in the cloud. Pushes to `claude/*`, `uv run`, `pytest` and the venv's python all prompt. Not denied: `rm -fr`, `find -delete`, `git push --force`, `git -C … push`. No `PreToolUse` hook. |
| Guardrail patterns | `agent-coordinator/src/guardrails.py:64-138` `FALLBACK_PATTERNS`: force push, reset --hard, clean -fd, branch -D/push --delete, rm -rf, DROP/TRUNCATE, `.env`/credential files, `kubectl apply`/`terraform apply`/`docker push`. Warn-level. | Nothing on the agent side enforces them. |
| Work queue | `/work/submit` (`coordination_api.py:1369`), `/work/claim` (`:1299`), `/work/complete` (`:1331`), SSE `/events/work` (`:3490`). Self-review is already excluded for `review`/`evaluate` (`work_queue.py:431-436`). | Nothing submits review jobs and nothing claims them. |
| Handoffs/approvals | `/handoffs/write` (`:1955`), `/approvals/request` (`:3301`), `/approvals/{id}/decide` (`:2162`). Notifiers in `src/notifications/` (Gmail, Telegram, webhook, relay). | `TRUST_POSTURE.md` still says no approval-notification channel exists, so `notify_with_timeout` fails closed. |
| GitHub intake | `handle_push_webhook` (`github_coordination.py:265`), `handle_issues_webhook` (`:294`), `/github/prs` (`:3864`). | No `pull_request` webhook. Findings are never posted back to the PR. |
| Review dispatch | `ReviewOrchestrator` (`skills/parallel-infrastructure/scripts/review_dispatcher.py:2490`): CLI first, then SDK (`:1846`), then skip. OpenAI-compatible adapter at `:2600-2632`. | Every vendor-CLI `subprocess.run` passed no `env=`, so the CLIs inherited the GitHub token and coordinator key. Fixed in 0.6. |
| Convergence | `converge()` (`skills/autopilot/scripts/convergence_loop.py:709`). The quorum guard (`:778-794`) returns `capability_unavailable` when verified lanes < `min_quorum`. | It assumes every lane runs on one host. A cloud round cannot count a local lane's verdict. |
| Routing | `agent-coordinator/routing.yaml` cost tiers: `subscription-local` (vendor-cli), `subscription-cloud` (vendor-sdk), `metered-api` (openrouter, local). | No metered Anthropic tier, so the $200 has nowhere to route. |
| Merge | `merge_pr.py:319-331` `_has_merge_queue()` always returns `True`. `_try_merge_queue` (`:461-487`) falls back to a direct merge. `ci.yml:3-8` already triggers on `merge_group`. | The queue is not enabled on the repo. `--merge-queue` is not a real `gh` flag. `_has_github_merge_queue` (`merge_backend.py:222-236`) is wrong, and `detect_merge_backend` (`:239`) is only called from tests. `execute_wave_merge` (`merge_train.py:1017`) is unused. The active-agent guard blocks every merge. `build_plan.py:95-101` chains any PRs that share a file. |

Merge hotspots, by commits touching the file: `checkpoint.json` (50),
`supervisor-record.json` (36), `roadmap.yaml` (34), `runner.py` (18),
`loop-state.json` (11-16), `dispatch_contract.py` (13). Most of these are
state files, not source code.

## Target topology

```
              GitHub (record: PRs, reviews, required checks, merge queue)
                ▲  PR events          ▲ one review per round      ▲ push claude/*
                │                     │ (GitHub App key held      │ (harness GitHub proxy)
                │                     │  only by the coordinator) │
   ┌────────────┴───────┐     ┌───────┴──────────────┐     ┌───────┴───────────────────┐
   │ Action: on PR       │────▶│ Coordinator (bus)    │◀────│ Cloud implementer sessions │
   │ opened/synchronize  │submit│ work queue, handoffs,│fix  │ Auto mode, repo settings,  │
   └─────────────────────┘ key │ findings, approvals, │pack-│ custom network allowlist,  │
                               │ notifier, LLM gateway│ets  │ coord key as network secret│
                               └──┬───────────▲───────┘     └──────────▲────────────────┘
                     SSE /events/work│  findings │                      │ /fire (scheduled task)
                                  ▼           │                      │
   ┌──────────────────────────────────────────┴───┐            ┌───────┴─────────┐
   │ Review worker (GX10 / laptop)                 │            │ Personal agents │
   │ detached read-only worktree @ head_sha        │            │ Duet · Dots ·   │
   │ sandbox-runtime per lane: write=out dir only, │            │ Grok Bot · Muse │
   │ egress = vendor API + coord, env allowlist,   │            │ review-only keys│
   │ each CLI uses its own OAuth login, no push key│            └─────────────────┘
   └───────────────────────────────────────────────┘
```

## Phase 0: Approvals only for irreversible actions (one to two days)

**Status (2026-10-23): the repo half is applied.** That covers the 0.4
settings, the 0.5 hook and the 0.6 env scrub. The user-level settings (0.3)
and the cloud environment settings (0.2) are set by hand outside the repo.

### 0.1 The irreversible set and where each class is caught

| Action class | Examples | Mechanism | Local | Cloud |
|---|---|---|---|---|
| History rewrite | `git push --force`, `-f`, `+ref`, `--force-with-lease`, `git -C <p> push -f`, `git reset --hard`, `git clean -fd` | deny rule + `PreToolUse` hook (deny); the classifier also blocks them | ✓ | ✓ |
| Remote deletion | `git push --delete`, `git push origin :ref`, `gh repo delete`, `gh api -X DELETE`, `gh release delete` | hook (deny) | ✓ | ✓ |
| Merge | `gh pr merge` (ask), `gh pr merge --admin` (deny) | hook, plus the existing `merge: block` gate and branch protection | ✓ | ✓ |
| Filesystem deletion outside the sandbox | `rm -rf /`, `rm -fr`, `find … -delete` | deny rule + sandbox write scope | ✓ | ✓ (container) |
| Data destruction | `DROP`, `TRUNCATE`, `alembic downgrade`, `psql` writes against Railway | hook (ask) + the existing ask rules | ✓ | ✓ |
| Deploy/infra | `railway up/down/delete`, `kubectl apply`, `terraform apply`, `docker push` | hook (ask) | ✓ | ✓ |
| Secrets | `bao kv delete/put`, writes to `.env*` or credential files | hook (ask) + `Read()` deny rules | ✓ | ✓ |
| Remote code execution | `curl … \| sh`, `wget … \| bash` | existing `curl *` deny + hook (deny) | ✓ | ✓ |
| Exfiltration | network to unlisted hosts | sandbox `network.allowedDomains` (local), Custom network level (cloud) | ✓ | ✓ |

Local `git branch -D` is deliberately left out. The reflog recovers it, and
worktree teardown deletes branches routinely. Deleting the *remote* branch is
what loses work, and that is denied.

Everything else (edits, tests, builds, `uv run`, pushes to the session's own
`claude/*` or `openspec/*` branch, coordinator HTTP calls) runs without asking.

### 0.2 Cloud sessions

- **Choose Auto from the mode dropdown when you start a cloud session.** Cloud
  sessions offer Accept edits, Plan and Auto. Bypass and dontAsk are ignored,
  so the repo's `defaultMode: "bypassPermissions"` has no effect in the cloud.
  Under Accept edits, every Bash call prompts. This is the main cause of cloud
  approval fatigue.
- In a single-repo session, the repo's shared `.claude/settings.json` is read;
  user and local settings are not. So narrow allow rules and the hook have to
  live in the repo file (0.4).
- Auto mode drops broad allows (`Bash(*)`, interpreter wildcards,
  package-manager `run`) and keeps narrow ones. Content `ask` rules such as
  `Bash(git push *)` still prompt in Auto, so do not add a broad push ask.
- The classifier allows pushes to any branch of the working repo, including the
  default branch. Branch protection on `main` (required reviews, required
  checks, no direct pushes, no admin bypass) is the backstop and has to be on.
- Environment settings:
  - **Network:** use the Custom level, allowing `coord.rotkohl.ai` plus the
    package mirrors and vendor APIs the setup script needs.
  - **Coordinator key:** store it as a *network secret* attached to
    `coord.rotkohl.ai` as `Authorization: Bearer …`, not as an environment
    variable. Environment variables are visible to anyone using the
    environment. A network secret is attached by the proxy after the request
    leaves the VM, so the key never appears in the container. The coordinator
    already checks `Authorization: Bearer` first (`coordination_api.py:695-712`).
  - **Scope:** give the cloud identity a key limited to work, handoffs and
    findings. It must not be able to call `approvals/{id}/decide`.

### 0.3 Local sessions (laptop and GX10)

Put these at **user level** (`~/.claude/settings.json`). The project-level
`defaultMode` values `auto` and `bypassPermissions` are ignored, and
`network.strictAllowlist` is honoured only at user or managed scope.

```jsonc
// ~/.claude/settings.json (proposal, not applied)
{
  "permissions": {
    "defaultMode": "auto"
  },
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,          // refuse to start rather than silently run unsandboxed
    "autoAllowBashIfSandboxed": true,   // the default; sandboxed Bash runs without a prompt
    "allowUnsandboxedCommands": false,  // no escape hatch the model can choose
    "filesystem": {
      "denyRead": ["~/.ssh", "~/.aws", "~/.config/gh", "~/.config/openbao", "~/.netrc"]
    },
    "network": {
      "allowedDomains": [
        "github.com", "api.github.com", "codeload.github.com",
        "coord.rotkohl.ai",
        "pypi.org", "files.pythonhosted.org", "registry.npmjs.org"
      ],
      "strictAllowlist": true
    }
  }
}
```

Notes:

- Linux needs `bubblewrap` and `socat`. macOS uses Seatbelt.
- `denyRead` limits sandboxed processes but **not** the Read tool, so keep the
  `Read(...)` deny rules in the repo file.
- Do not put `docker` in `excludedCommands`. Access to `docker.sock` is access
  to the host, so let it prompt.
- Writes to `PATH` directories or shell rc files are a known way out of the
  sandbox. The sandbox's default write scope (cwd, temp, added directories)
  already excludes them, so keep it that way.
- Headless `claude -p` and Agent SDK runs start in Manual mode regardless of
  these settings. The review worker in Phase 1 therefore wraps each lane in
  `@anthropic-ai/sandbox-runtime` directly, instead of relying on the
  interactive mode.

### 0.4 Repo settings changes (applied)

```jsonc
// .claude/settings.json: additions only
{
  "permissions": {
    "allow": [
      "Bash(git push -u origin claude/*)",
      "Bash(uv run *)",
      "Bash(pytest *)",
      "Bash(skills/.venv/bin/python -m pytest *)",
      "Bash(agent-coordinator/.venv/bin/python -m pytest *)"
    ],
    "deny": [
      "Bash(rm -fr *)",
      "Bash(git push --force *)",
      "Bash(git push -f *)",
      "Bash(find * -delete*)",
      "Bash(gh repo delete *)",
      "Bash(gh pr merge --admin *)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/skills/session-bootstrap/scripts/hooks/irreversible_guard.py",
            "timeout": 10,
            "onFailure": "block"
          }
        ]
      }
    ]
  }
}
```

`defaultMode: "bypassPermissions"` is removed. It did nothing at project scope,
and removing it means nobody is misled about the mode in force.

The hook lives in canonical `skills/session-bootstrap/`, not in `.claude/`.
In this repo `.claude/skills/` is a gitignored mirror that a resume can wipe,
and a guard has to survive that. Consumer repos with committed mirrors use the
`.claude/skills/...` path; see the session-bootstrap SKILL.md.

### 0.5 `irreversible_guard.py`: own rules, parity enforced by a test

`skills/session-bootstrap/scripts/hooks/irreversible_guard.py` is stdlib-only
and does not import the coordinator. Hooks have to run in containers where the
coordinator's venv does not exist. The coordinator's regexes are also
unanchored: they match `git push --force` inside a `grep` argument or a commit
message, which is fine for a warning but would make a blocking hook unusable.

The hook matches on the command word instead:

- It strips heredoc bodies, then splits on `&&`, `||`, `;`, `|`, `&` and
  newlines.
- It peels wrappers: `env`, `sudo`, `timeout`, `nice`, `xargs`, `command`,
  assignments, `(`, `{` and `if`/`then`/`do`.
- It recurses into `sh -c`, `eval`, `$(…)` and backticks.
- It then applies per-tool rules for git, rm, find, gh, the database clients,
  the deploy tools and secret paths.

Deny means exit 2, and covers history rewrite, remote deletion, `rm -rf`,
`find -delete`, `curl | sh` and `mkfs`/`dd of=/dev/`. Ask is a JSON
`permissionDecision` covering merges, `DROP`/`TRUNCATE`, deploys and secret
writes. An internal error asks rather than denies.

`skills/tests/session-bootstrap/test_irreversible_guard.py` keeps the two lists
honest. It reads `FALLBACK_PATTERNS` from `guardrails.py` with `ast`, no import.
Every coordinator pattern needs a parity case that the coordinator regex
matches and the hook denies or asks. A new server-side pattern therefore fails
the suite until the hook learns it.

With `onFailure: "block"`, a crashing hook fails closed. When several hooks
disagree, the strictest answer wins (deny, then defer, then ask, then allow), so
adding hooks later cannot weaken this one.

**Limit of this layer.** Hooks and Bash rules see only the command Claude Code
runs. A script that shells out, such as `python merge_pr.py` calling `gh`, is
invisible to them. That is why principle 2 (credential scope) and the sandbox
come first, with hooks and rules as a second layer.

### 0.6 Scrub vendor-CLI environments in the review dispatcher (applied)

Every `subprocess.run` in `CliVendorAdapter` now passes
`env=vendor_subprocess_env(self.cli_config)`. That covers synchronous dispatch,
async submit and status polling.

The allowlist has three parts:

- Basics: `PATH`, `HOME`, locale, proxy and CA-bundle variables, and
  `VIRTUAL_ENV`.
- The vendor's own prefixes: `ANTHROPIC_`/`CLAUDE_`, `OPENAI_`/`CODEX_`,
  `XAI_`/`GROK_`, `OPENROUTER_`/`PI_`, `GEMINI_`/`GOOGLE_` and `OCR_`/`REVIEW_`.
- Its configured `api_key_env`.

A missing name can be added through `REVIEW_DISPATCH_ENV_PASSTHROUGH`. Some
names are never passed, even through that variable: `GH_TOKEN`, `GITHUB_TOKEN`,
`SSH_AUTH_SOCK`, `COORDINATION_API_KEY*`, `BAO_*` and `VAULT_*`.

Two calls are left alone:

- The `get_dispatch_configs.py` call runs coordinator code that needs the
  coordinator's environment, and no vendor sees it.
- `_dry_invoke` probes `--version`/`--help` and discards the output.

`test_vendor_env_scrub.py` covers the helper and the dispatch path. It also
checks with `ast` that no `subprocess.run` in the adapter lacks `env=`.

## Phase 1: Review queue across hosts (about one week)

**Status (2026-10-24): applied end to end; the cloud lane opts in per run.**
Built: migration `046_review_queue.sql` (`review_jobs`, `review_lane_results`),
`POST /reviews/jobs`, `POST /reviews/results`, `GET /reviews/rounds`, the
single publisher (`agent-coordinator/src/review_publisher.py`), the producer
workflow (`.github/workflows/review-queue.yml`), the review worker
(`skills/merge-pull-requests/scripts/review_worker.py`, 1.3 steps 1–3) and
remote rounds in `converge()` (`skills/autopilot/scripts/remote_rounds.py`
plus the `remote_results` parameter, 1.5). When `remote_results` is wired,
the pre-dispatch quorum guard is deferred to the per-round count, because
remote lanes are only known after the round runs. `agent_lane.py converge
--remote-repo <owner/name> --remote-pr <n>` passes a `coordinator_round_source`
(through the bridge's `CoordinatorHttpClient`, which the worker shares) and
logs each round's remote vendors as a `remote_round` event. It still resolves
the quorum policy with `verified_review_lanes=1`, so the TRUST_POSTURE
exception and the `single_vendor_review` record stay until an operator
deletes them (1.5); after that, `min_quorum` 2 must be met by remote lanes.
Deferred: the SSE subscription (the worker polls `/work/claim` first), the
per-lane sandbox wrapping, recovery of a pass whose worker died mid-claim, and
the scheduled-task fire path (1.4).

### 1.1 Job contract

`task_type: review`. The payload:

```yaml
repo: jankneumann/agentic-coding-tools
pr: 512
head_sha: 3f9c…
base_sha: a1b2…
round: 2
lanes_required: 2          # vendors, not hosts
risk: medium               # from risk_scorer.py
deadline: 2026-10-23T18:00Z
dedup_key: [repo, pr, head_sha, round]
```

The coordinator assigns `round`. A round can take up to `REVIEW_MAX_PASSES`
passes; each pass is one `review` work item, and a residual pass excludes the
vendors already verified. A new push to the PR supersedes jobs for the old
`head_sha`. Workers read `GET /reviews/rounds` before running lanes and skip a
superseded job, so they need no GitHub credential to notice. The coordinator
re-reads the PR head from GitHub just before it posts and records `head_moved`
instead of posting, so a review never lands on a stale head.

### 1.2 Producer

- **Preferred (applied):** `.github/workflows/review-queue.yml`, triggered by
  `pull_request` (`opened`, `synchronize`, `reopened`, `ready_for_review`). It
  calls `POST /reviews/jobs` with the producer token in
  `X-Review-Producer-Token`, stored as the repo secret `REVIEW_PRODUCER_TOKEN`.
  That token can only enqueue, and only for repositories in
  `REVIEW_ALLOWED_REPOS`. The workflow holds no repository permissions, uses
  `pull_request` rather than `pull_request_target`, and skips forks and drafts.
- **Alternative:** add `handle_pull_request_webhook` next to
  `handle_push_webhook` (`github_coordination.py:265`). This adds work to the
  public 8081 surface, so the Action is simpler and keeps the coordinator's
  public surface unchanged.

### 1.3 Consumer: the review worker (GX10 first, laptop as overflow)

This is the GX10 dispatcher daemon from `always-on-agent-automation.md`
Phase 2, cut down to one job type.

1. Subscribe to SSE `/events/work`. Claim with `/work/claim`
   (`task_types=[review]`). Self-review exclusion already applies.
2. `git worktree add --detach <tmp> <head_sha>` and make the tree read-only.
   No branch is checked out and no push credential is present.
3. Run each lane through `ReviewOrchestrator` with the per-lane sandbox:
   - Write access only to `<out>/<vendor>/`.
   - Egress only to that vendor's API host and `coord.rotkohl.ai`.
   - The env allowlist from 0.6.
   - Each vendor CLI uses its own OAuth login. Codex, Gemini and opencode
     permit programmatic CLI use. The Claude lane uses the **API key**
     (Phase 4), not the subscription, in line with the subscription terms
     recorded in `sandboxed-harness-execution.md:9`.
4. `POST /reviews/results` with one entry per lane
   (`vendor, verified, verdict, model, findings, error`), stored in
   `review_lane_results` keyed `(job, vendor)`, then `/work/complete`. Only the
   agent that claimed the pass can record it, and a verified lane is never
   replaced by an unverified one.
5. The **coordinator** posts one consolidated PR review using a GitHub App
   installation token minted per publication, scoped to
   `pull_requests: write`. The App key sits in the coordinator's environment
   (`REVIEW_GITHUB_APP_*`) for now; moving it to OpenBao is a follow-up. The
   worker never holds that key. The review uses the `COMMENT` event and never
   `APPROVE`: approval stays human. A round that runs out of passes without
   quorum is still posted, marked as a partial review.

### 1.4 Waking the cloud implementer

Two options, cheapest first:

- **PR-activity subscription.** The cloud session that opened the PR is
  subscribed to it, so the coordinator's posted review wakes it directly. No
  new code is needed.
- **Scheduled-task fire.** For fixes that should start in a fresh session, the
  coordinator writes a fix-packet handoff (`/handoffs/write`). It then calls
  `POST https://api.anthropic.com/v1/claude_code/routines/<trig_id>/fire`
  (bearer token, beta header `experimental-cc-routine-2026-04-01`) with the
  packet ID as the fire text. Fire text arrives wrapped as untrusted
  (`<routine-fire-payload>`), so the saved prompt must say explicitly: "fetch
  handoff <id> from the coordinator and implement only its findings". This is a
  research preview, so keep the PR-activity path as the default.

### 1.5 Quorum across hosts (removes the cloud exception)

Define a review **round** as the set of lane results for a given `head_sha`.
Quorum is at least two distinct *vendors* with verified results on that
`head_sha`, whichever host ran them. `converge()` reads round results from the
coordinator instead of only from local dispatch. The `:778-794` guard keeps its
meaning, with "verified lanes" now counted per round.

The `TRUST_POSTURE.md` sunset clause names the condition: "API-based
multi-vendor review … or the GX10 review lane is available to cloud workers".
The queue makes the GX10 lane available to cloud workers. An OpenRouter lane
(Phase 4) satisfies the API-based alternative. Once either has run for a week,
delete the exception as an operator decision. Until then, keep it and keep
recording `single_vendor_review`.

## Phase 2: Research lane — search without open web access (about one week)

Agents often need current information: a library's latest release, an API
that changed last week, an error message someone else already hit. Opening the
web to implementer sessions is the wrong way to get it. This phase adds
`research` as a second task type on the Phase 1 queue, next to `review`, and
keeps general web access out of every session that holds a repo, a push path
or a key.

### 2.1 Three risks, not one

"Web access" bundles three separate risks:

| Risk | What it is | What controls it |
|---|---|---|
| Untrusted input | Any page or snippet the model reads can carry instructions (prompt injection). | Who reads the content, and what that reader can do. |
| Egress | Data leaving the sandbox: a secret in a URL's query string, a POST to an attacker's host. | The network allowlist, and which secrets the process holds. |
| Capability | What an injected instruction could make the agent do: push, call the coordinator, read keys. | Credentials and tools held by the role (Principle 2). |

Injection does real harm only when all three meet in one process: untrusted
content, something worth stealing or doing, and a way out (the "lethal
trifecta"). Remove any one and an injected page can at worst corrupt the
answer. A domain allowlist addresses only egress.

### 2.2 Is a search-API allowlist enough?

Allowing only a search API (Tavily, Brave, or the model provider's server-side
web search tool) narrows *where* traffic goes, not *what comes back*. Snippets
and extracted pages are third-party content, chosen by whoever ranks well for
the query.

- **For security, no.** It closes exfiltration to arbitrary hosts (the query
  itself still reaches the search provider), but the injection surface is the
  same as browsing. An agent that holds a push path and reads search results is
  still exposed.
- **For quality, mostly.** Snippets answer version lookups, "does this flag
  exist" and error-message searches. A full changelog, migration guide or issue
  thread needs the page itself. Search APIs with extraction (Tavily `extract`,
  a provider's web fetch tool) fetch on their side: that removes the sandbox's
  egress, not the untrusted content.
- **A cached trusted index with no live access** is the safest and the most
  reproducible, but it is stale exactly when research matters most: yesterday's
  release, this morning's advisory. As the only source it fails the main use
  case.

So the answer is a split by role, not one web policy for every session.

### 2.3 Sources in tiers

Use the lowest tier that answers the question:

1. **Structured APIs.** PyPI, npm and crates metadata, GitHub releases and
   advisories, OSV. These return data, not prose, so the injection surface is
   small. Most "is there a newer version" questions stop here.
2. **Coordinator read-through cache.** A trusted index of pinned sources
   (official docs for the stack in `pyproject.toml`, vendor changelogs, the
   specs this repo depends on), keyed by URL and retrieval date, with a content
   hash. The research worker refreshes it; every role may read it.
3. **Live search** through the allowlisted search API, only inside the
   research worker.
4. **Full page fetch**, only inside the research worker, bounded by
   `max_fetches`.

### 2.4 `task_type: research`

Same queue and claim path as `review` (`/work/claim` with
`task_types=[research]`). The payload:

```yaml
question: "Does httpx 0.28 still accept `proxies=`?"
scope: dependency          # dependency | api | incident | vendor-terms
allowed_sources: [pypi, github-releases, docs-cache, search]
max_fetches: 5
deadline: 2026-10-24T18:00Z
requester_task_id: 8c1d…   # the implementer or review job that asked
dedup_key: [question_hash, scope]
```

The result is a size-limited, schema-checked artifact, not free text:

```yaml
answer: "No. `proxies=` was removed in 0.28; use `proxy=` or transport mounts."
citations:
  - {url: https://…/CHANGELOG.md, retrieved_at: 2026-10-24T09:12Z, sha256: …, tier: 2}
confidence: high           # high | medium | low
```

Rules:

- **The research worker holds almost nothing.** Egress to the search API, the
  allowlisted fetch targets and the coordinator. Credentials: the search API
  key and a coordinator key that can only claim `research` and post its
  result. No repo checkout, no GitHub token, no vendor OAuth logins.
- **Requesters treat the answer as data** (Principle 3), as with fire payloads
  in 1.4. The answer is short and schema-checked, which limits how much
  injected text can ride along, and the citations let a human check the claim.
- **Dedup across agents.** Ten implementers asking about the same release make
  one job, and a fresh tier-2 entry answers without a job at all.
- **Reviewers can ask too.** A lane that flags "this API is deprecated" can
  attach a research citation instead of a recollection.

### 2.5 Grants per role

| Role | Web access | Why |
|---|---|---|
| Cloud implementer | Tiers 1–2 through the coordinator; asks `research` for the rest | Holds a push path and the coordinator key |
| Review worker lanes | None, or tier 2 | Hold vendor OAuth logins; they review code, not the web |
| Research worker | Tiers 1–4 | Holds only the search key and a research-only coordinator key |
| Personal agents (Phase 5) | Their own browsing | Already outside the factory's credentials; their outputs are data |

For cloud sessions this is the Custom network level from 0.2: implementer
environments allow the coordinator and the package mirrors, not search or
arbitrary hosts.

### 2.6 Opportunities

- **A shared docs cache.** Tier 2 doubles as a changelog watcher: when a pinned
  dependency publishes a release, one research job summarizes the breaking
  changes for every agent.
- **Provenance in findings.** Review findings and fix packets can cite a
  retrieved, hashed source, so a human sees why an agent believes an API
  changed.
- **Replay and evals.** Cached retrievals make a research answer reproducible:
  an eval can rerun a session against the same pages, which live search cannot
  offer.
- **Spend control.** Search and fetch calls are counted per lane with a monthly
  cap, alongside the LLM gateway in Phase 4, so a runaway loop shows up in the
  existing reports.
- **A home for the terms watcher.** The Muse role in Phase 5 ("tracks vendor
  term changes") becomes a scheduled `research` job with
  `scope: vendor-terms`, whichever agent runs it.
- **Quarantine as a pattern.** The same split, a reader with no capability and
  a doer with no untrusted input, applies to issue bodies and PR comments from
  outside contributors.

Build order: the worker with tiers 1 and 3 first (the job contract, the result
schema, dedup), then the tier-2 cache once repeated questions show which
sources to pin.

## Phase 3: Unblock merge linearization (about one week, then follow-ups)

1. **Turn on GitHub's merge queue** for `main`. `ci.yml` already triggers on
   `merge_group`. Require the 6 existing checks. Under a merge queue,
   `strict: false` is fine, because the queue tests each PR on top of the PRs
   ahead of it.
2. **Make `merge_pr.py` use the queue for real.** Replace the optimistic
   `_has_merge_queue()` with `detect_merge_backend()` (`merge_backend.py:239`).
   Fix `_has_github_merge_queue` to query GraphQL `repository.mergeQueue(branch:)`.
   Merge with
   `gh pr merge <n> --auto --squash|--rebase --match-head-commit <sha>`. With
   `--auto`, the PR enters the queue once required approvals and checks pass,
   so the human gate is still the code-owner approval.
3. **Remove the state-file hotspots.** `checkpoint.json`,
   `supervisor-record.json`, `loop-state.json` and the generated parts of
   `roadmap.yaml` either move to the coordinator, which already persists loop
   state, or get a `.gitattributes` merge driver (`union`, or a small JSON
   merge). Exclude them from the overlap check in `build_plan.py:95-101`, so
   that sharing one of them no longer chains two PRs.
4. **Narrow the active-agent guard** to real overlap: a live worktree blocks a
   merge only if its changed paths intersect the PR's paths.
5. **Later:** batching, then speculative lanes, following
   `monorepo-merge-scaling-research.md` Gaps 6 and 1. Mergify-style merge
   batches and bisection, or Trunk multi-queue, are the external options if the
   built-in queue saturates.

## Phase 4: Spending the $200 of metered Claude credit

**Assumption:** the $200 is API-key credit on the Claude Console. If it turns
out to be a pool tied to the subscription, the authentication differs (see
Risks).

Add a tier to `routing.yaml`:

```yaml
    - id: metered-anthropic
      location: any            # cloud or local
      endpoint_kinds: [anthropic-api]
```

Estimated cost per review, assuming about 60k input and 5k output tokens:

| Tier | Price per MTok (input / output) | Per review | Reviews per $200 |
|---|---|---|---|
| Large | $4 / $20 | ≈ $0.34 | ≈ 550 |
| Mid | $2 / $10 | ≈ $0.17 | ≈ 1,100 |
| Small (≤100K context) | $0.10 / $0.50 | ≈ $0.01 | ≈ 20,000 |

Prompt caching (cache reads cost a tenth of the input price, $0.20 per MTok on
the mid tier) and the Batch API (50% off) lower these further.

Lanes, in priority order:

1. **Claude lane in the review worker.** This restores two-vendor quorum when
   only one other vendor CLI is logged in. It uses the mid tier, and the large
   tier for `risk: high`.
2. **CI first pass.** `claude-code-action` with `anthropic_api_key` runs a
   cheap first-pass review on each PR, so the local queue spends its time on
   PRs that already passed. Use the API key rather than an OAuth token here:
   the token is tied to one person.
3. **Small-tier triage.** Classify findings, dedupe across vendors, and write
   the fix packet the cloud implementer consumes.
4. **Nightly ambient review** through the Batch API over the day's merged
   diff. Results feed the `ambient-review-ledger` idea.

Controls:

- Route everything through the proposed `add-coordinator-llm-gateway`
  (LiteLLM), with a $200 hard monthly cap and a tag per lane, so spend shows up
  per lane in the existing reports.
- Set a Console spend limit as a second safeguard.
- Never export `ANTHROPIC_API_KEY` in a shell where interactive Claude Code
  runs. It overrides the subscription login.

## Phase 5: Persistent personal agents

All four have launched or entered preview since August 2026. Each has its own
always-on cloud computer and memory. Each is a natural place for one bounded
role, and none should be a merge authority.

| Agent | What it is (as of 2026-10) | Role in the factory | Integration | Limits |
|---|---|---|---|---|
| **Claude Duet** (Anthropic, preview from 2026-10-21) | Personal agent with its own cloud computer. Asks before it sends, pays, signs or deletes. Checks in every few hours. Counts against subscription usage. | **Chief of staff for the merge gate.** Twice a day: "these PRs are green and reviewed and need your approval; these are blocked on X". | Reads the coordinator's status digest (existing notifier, webhook or Gmail channel). Read-only GitHub. | US Pro/Max only, waitlisted. No approval-deciding key. |
| **OpenAI Dots** (2026-09-29) | Always-on cloud computer, 4,000+ connectors, a shared ChatGPT Space, read-only mode. | **PR concierge and defect memory.** It watches PRs read-only, can ask for an `@codex` review, and remembers recurring defects that it proposes as `REVIEW.md` rules. | GitHub connector in read-only mode, and posting a comment to request a review. | Codex/MCP delegation is not shipped yet (codex #55568). Its rule proposals go through a normal PR. |
| **Grok Bot** (xAI, beta from 2026-08-11) | Persistent VM, routines, bot groups of 2-6, takeover mode. Grok Build CLI with headless runs, hooks and sandboxing. | **A non-Claude review lane in the cloud.** Grok Build runs headless on the bot's VM as a second queue consumer, so a cloud round can reach quorum with no local machine online. | The same queue contract as 1.3, with a review-only coordinator key. | Needs SuperGrok Heavy or about $120 per seat. Verify the programmatic-use terms. |
| **Meta Muse** (2026-09-08) | Free, $20 and $100 tiers. The Muse Code CLI has parallel workers, background reviewers, worktree isolation and `muse exec` headless mode. | **Extra review lane, plus research and a terms-of-service watcher.** It also tracks vendor term changes that affect this design. | `muse exec` called over the coordinator's HTTP API with a review-only key. **Not over MCP**, because Muse runs MCP tools outside its sandbox. | Newer product with a thin track record. Treat it as an optional lane. |

Guardrails common to all four:

- **Per-agent keys.** Each agent gets its own coordinator key in
  `COORDINATION_API_KEY_IDENTITIES`, or an OpenBao identity, scoped to read,
  submit, findings and handoffs. None gets `approvals/{id}/decide`.
- **No repo write.** None gets a GitHub token that can write the repo.
- **Outputs are data.** A Duet digest saying "ready to merge" is a report. The
  merge happens only after a human approves on GitHub.
- **Audit.** Their findings carry `vendor` and `agent_id`, so quorum counts
  them as their own vendor, never as a second vote for the same vendor.

## Sequencing

| Phase | Effort | Unblocks | Depends on |
|---|---|---|---|
| 0.2 Auto mode in cloud, network secret, Custom network | minutes | cloud approval fatigue | nothing |
| 0.3 / 0.4 / 0.5 local sandbox, repo rules, guard hook | 1–2 days | local approval fatigue | operator applies the settings |
| 0.6 env scrub | ½ day | credential separation | nothing |
| 1 review queue and cross-host quorum | ~1 week | reviews from the cloud, removing the cloud exception | 0.6 |
| 2 research lane (worker, tiers 1 and 3, then the cache) | 3–5 days | current information without web access in implementer sessions | 1 (queue), 0.2 (network level) |
| 3.1–3.2 merge queue | 1–2 days | parallel merges | repo admin enables the queue |
| 3.3–3.4 state-file hotspots, narrower guard | 2–3 days | stops false chaining | 3.1 |
| 4 metered Claude lanes and gateway | 2–3 days | two-vendor quorum without a second CLI, CI first pass | 1 (for lane 1) |
| 5 personal agents | incremental | notification channel, cloud non-Claude lane | 1, scoped keys |

Phases 2 and 3 are independent and can run in parallel.

Phase 5's Duet or notifier digest can also clear the `TRUST_POSTURE.md` note
that no approval-notification channel exists. That is what lets
`notify_with_timeout` dispositions work at all.

## Risks and open questions

- **Subscription terms.** The Agent SDK documentation says third-party products
  may not offer claude.ai login or subscription rate limits. Personal-script
  use is not documented either way. This design keeps the Claude subscription
  in interactive and cloud-session roles and uses API-key credit for automated
  Claude review. Verify the terms of the other three vendors before making them
  unattended queue consumers.
- **Where the $200 comes from.** No subscription-tied SDK credit pool is
  documented. If the credit is tied to the subscription, Phase 4 lanes 1 and 4
  need a different credential path.
- **The classifier allows pushes to the default branch.** Branch protection is
  the only control here, so verify it before turning on Auto mode in the cloud.
- **Network secrets with non-Anthropic CLIs** are untested. Test with `curl`
  against the coordinator before relying on them for vendor-API traffic.
- **Scheduled tasks** are a research preview behind a beta header, and the fire
  payload is untrusted by design. PR-activity wake-up stays the default.
- **Auto mode pauses** after 3 consecutive or 20 total classifier blocks. If the
  guard hook and the classifier both fire often, the session stalls. Track the
  block counts in session logs during the first week.
- **Classifier cost.** On API and Enterprise accounts, classifier calls are
  billed. On Pro and Max they count against usage.
- **Personal-agent maturity.** Duet is waitlisted. Grok Bot is beta and its
  price is unclear. Dots lacks Codex delegation. Plan for any of them to be
  missing and keep each optional.
- **Research answers are still untrusted.** An answer can be wrong, or carry
  injected text inside its `answer` field. The size limit, the schema and the
  citations reduce this; they do not remove it. Nothing a research answer
  proposes runs without the gates any other agent output goes through.
- **Search queries leave the factory.** A query can name private code or an
  unreleased feature. Keep research questions about public artifacts, and
  check the search provider's retention terms.
- **Managed Code Review** (Anthropic's hosted reviewer) needs a Team or
  Enterprise plan. `/code-review` runs locally on any plan and can be a manual
  lane meanwhile.

## Sources

- Claude Code docs: [permission modes](https://code.claude.com/docs/en/permission-modes),
  [permissions](https://code.claude.com/docs/en/permissions),
  [sandboxing](https://code.claude.com/docs/en/sandboxing),
  [hooks](https://code.claude.com/docs/en/hooks),
  [authentication](https://code.claude.com/docs/en/authentication),
  [scheduled tasks](https://code.claude.com/docs/en/routines),
  [cloud environments](https://code.claude.com/docs/en/cloud-environments),
  [GitHub Actions](https://code.claude.com/docs/en/github-actions),
  [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)
- Prompt injection: [Simon Willison, "The lethal trifecta for AI agents"](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)
- Merge queues: [tianpan, "The merge queue is the new bottleneck"](https://tianpan.co/blog/2026-07-02-the-merge-queue-is-the-new-bottleneck),
  [Mergify, merge queues and AI coding agents](https://mergify.com/blog/merge-queues-and-ai-coding-agents),
  [Mergify merge-batch changelog](https://docs.mergify.com/changelog/2026-04-07-new-merge-batch-merge-method-for-merge-queue.md),
  [Trunk merge queue changelog](https://docs.trunk.io/merge-queue/changelog)
- Claude Duet: [product](https://claude.com/product/claude-duet),
  [blog](https://claude.com/blog/claude-duet),
  [CNBC](https://www.cnbc.com/2026/10/21/anthropic-preview-of-claude-duet-personal-ai-agent-take-on-muse-dots.html),
  [support](https://support.claude.com/en/articles/17631495)
- OpenAI Dots: [announcement](https://openai.com/index/introducing-dots/),
  [TechCrunch](https://techcrunch.com/2026/09/29/openai-launches-dots-its-bubbly-agentic-avatar/),
  [VentureBeat](https://venturebeat.com/technology/openai-launches-dots-always-on-ai-agent-coworkers-and-chatgpt-space-where-they-can-collaborate-with-human-teams),
  [Al Jazeera](https://www.aljazeera.com/economy/2026/9/30/openai-launches-dots-personal-ai-assistant-built-to-handle-everything),
  [codex #55568](https://github.com/openai/codex/issues/55568)
- xAI Grok Bot / Grok Build: [nexforce](https://nexforce.ai/en/blog/xai-launches-grok-bot-persistent-cloud-agents),
  [techjacksolutions](https://techjacksolutions.com/ai-brief/xai-grok-bot-beta-grok-build-persistent-agent/),
  [Grok Build CLI](https://x.ai/news/grok-build-cli),
  [xai-org/grok-build](https://github.com/xai-org/grok-build)
- Meta Muse: [CNBC](https://www.cnbc.com/2026/09/08/meta-personal-ai-agents-public-reckoning-privacy-safety.html),
  [Muse Code](https://developer.meta.com/ai/products/muse-code/),
  [layer3labs explainer](https://www.layer3labs.io/guides/muse-code-explained)
