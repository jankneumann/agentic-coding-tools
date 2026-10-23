# Factory Local/Cloud Split: Sandboxed Auto-Approval, a Review Queue, and a Merge Queue

*Proposal, 2026-10-23. Status: draft for operator review. Nothing in this
document has been applied: every settings, hook or workflow snippet below is a
proposal.*

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
| Review dispatch | `ReviewOrchestrator` (`skills/parallel-infrastructure/scripts/review_dispatcher.py:2490`): CLI first, then SDK (`:1846`), then skip. OpenAI-compatible adapter at `:2600-2632`. | Every vendor-CLI `subprocess.run` (`:1012`, `:1526`, `:1673`, `:2780`) passes no `env=`, so the CLIs inherit the GitHub token and coordinator key. |
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

### 0.1 The irreversible set and where each class is caught

| Action class | Examples | Mechanism | Local | Cloud |
|---|---|---|---|---|
| History rewrite | `git push --force`, `-f`, `+ref`, `--force-with-lease`, `git -C <p> push -f`, `git reset --hard`, `git clean -fd` | deny rule + `PreToolUse` hook (deny); the classifier also blocks them | ✓ | ✓ |
| Remote deletion | `git push --delete`, `branch -D` on a pushed branch, `gh repo delete`, `gh api -X DELETE`, `gh release delete` | hook (deny) | ✓ | ✓ |
| Merge | `gh pr merge` (ask), `gh pr merge --admin` (deny) | hook, plus the existing `merge: block` gate and branch protection | ✓ | ✓ |
| Filesystem deletion outside the sandbox | `rm -rf /`, `rm -fr`, `find … -delete` | deny rule + sandbox write scope | ✓ | ✓ (container) |
| Data destruction | `DROP`, `TRUNCATE`, `alembic downgrade`, `psql` writes against Railway | hook (ask) + the existing ask rules | ✓ | ✓ |
| Deploy/infra | `railway up/down/delete`, `kubectl apply`, `terraform apply`, `docker push` | hook (ask) | ✓ | ✓ |
| Secrets | `bao kv delete/put`, writes to `.env*` or credential files | hook (ask) + `Read()` deny rules | ✓ | ✓ |
| Remote code execution | `curl … \| sh`, `wget … \| bash` | existing `curl *` deny + hook (deny) | ✓ | ✓ |
| Exfiltration | network to unlisted hosts | sandbox `network.allowedDomains` (local), Custom network level (cloud) | ✓ | ✓ |

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

### 0.4 Repo settings changes (proposal, not applied)

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
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/irreversible_guard.py\"",
            "onFailure": "block"
          }
        ]
      }
    ]
  }
}
```

Leave `defaultMode: "bypassPermissions"` alone or remove it. It does nothing at
project scope, and removing it means nobody is misled about the mode in force.

### 0.5 `irreversible_guard.py`: one pattern list, enforced on both sides

The hook imports the same pattern list as `guardrails.py` `FALLBACK_PATTERNS`,
so the coordinator's warn-level check and the agent-side block cannot drift
apart. It adds the variants that list lacks (`-f`, `+ref`, `--force-with-lease`,
`git -C <path>`, `gh api -X DELETE`, `rm -fr`, `find -delete`,
`alembic downgrade`, `railway up|down|delete`, `bao kv delete`,
`curl|wget … | sh`).

```python
# Sketch. Reads the PreToolUse JSON on stdin.
cmd = normalize(payload["tool_input"]["command"])   # strip `git -C <p>`, `env X=…`, `sh -c '…'`
for part in split_compound(cmd):                   # && || ; | and newlines
    m = match(part, PATTERNS)
    if m and m.severity == "deny":
        print(m.reason, file=sys.stderr); sys.exit(2)          # exit 2 blocks
    if m and m.severity == "ask":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": m.reason}}))
        sys.exit(0)
sys.exit(0)                                         # no opinion: normal rules apply
```

With `onFailure: "block"`, a crashing hook fails closed. When several hooks
disagree, the strictest answer wins (deny, then defer, then ask, then allow), so
adding hooks later cannot weaken this one.

**Limit of this layer.** Hooks and Bash rules see only the command Claude Code
runs. A script that shells out, such as `python merge_pr.py` calling `gh`, is
invisible to them. That is why principle 2 (credential scope) and the sandbox
come first, with hooks and rules as a second layer.

### 0.6 Scrub vendor-CLI environments in the review dispatcher

Pass an explicit `env=` at `review_dispatcher.py:1012`, `:1526`, `:1673` and
`:2780`. The allowlist is `PATH`, `HOME`, `LANG`, `TERM`, the vendor's own
config directory variable, and the output directory. `GH_TOKEN`, `GITHUB_TOKEN`,
`COORDINATION_API_KEY*` and `BAO_*` are never passed. This is a small,
test-covered change that closes the largest credential leak in the current
design.

## Phase 1: Review queue across hosts (about one week)

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

A new push to the PR supersedes jobs for the old `head_sha`. The worker checks
`head_sha` before it posts, so it never reviews a stale head.

### 1.2 Producer

- **Preferred:** a small GitHub Action triggered by `pull_request`
  (`opened`, `synchronize`, `ready_for_review`) that calls `/work/submit` with a
  **submit-only** key stored as a repo secret. That key can only enqueue.
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
     (Phase 3), not the subscription, in line with the subscription terms
     recorded in `sandboxed-harness-execution.md:9`.
4. `/work/complete` with structured findings keyed
   `(pr, head_sha, round, vendor)`. That needs a small findings table, or
   findings stored on the work-item result.
5. The **coordinator** posts one consolidated PR review using a GitHub App
   installation token from OpenBao, scoped to `pull_requests: write`. The
   worker never holds that key. The review uses the `COMMENT` event and never
   `APPROVE`: approval stays human.

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
(Phase 3) satisfies the API-based alternative. Once either has run for a week,
delete the exception as an operator decision. Until then, keep it and keep
recording `single_vendor_review`.

## Phase 2: Unblock merge linearization (about one week, then follow-ups)

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

## Phase 3: Spending the $200 of metered Claude credit

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

## Phase 4: Persistent personal agents

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
| 2.1–2.2 merge queue | 1–2 days | parallel merges | repo admin enables the queue |
| 2.3–2.4 state-file hotspots, narrower guard | 2–3 days | stops false chaining | 2.1 |
| 3 metered Claude lanes and gateway | 2–3 days | two-vendor quorum without a second CLI, CI first pass | 1 (for lane 1) |
| 4 personal agents | incremental | notification channel, cloud non-Claude lane | 1, scoped keys |

Phase 4's Duet or notifier digest can also clear the `TRUST_POSTURE.md` note
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
  documented. If the credit is tied to the subscription, Phase 3 lanes 1 and 4
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
