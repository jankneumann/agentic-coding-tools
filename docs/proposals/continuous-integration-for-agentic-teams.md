# Continuous Integration for Agentic Teams: Proposal Review and Plan

**Status**: Draft for discussion, 2026-11-01
**Reviews**: [handoff-continuous-integration-for-agentic-workflows.md](handoff-continuous-integration-for-agentic-workflows.md) (Jan Neumann with Grok)
**Audience**: Jan as repository owner; later, a 5-10 person team using this toolkit on greenfield work
**Operating constraint**: cloud agents plan and implement; on-device agents (multi-vendor subscriptions, the GX10) review and merge

---

## 1. Summary

The proposal's diagnosis is right and its mechanism is wrong. Merges are blocked, but not
by coordinator claims. Three things block them:

1. **A repo-wide worktree-liveness guard in the merge kernel.** `execute_plan.py` calls
   `guard_sync_point` before any merge, which blocks when *any* entry in
   `.git-worktrees/.registry.json` is pinned or heartbeated within one hour, regardless of
   overlap, with no override flag (`skills/merge-pull-requests/scripts/execute_plan.py:358-370`,
   `skills/shared/active_agents.py:90-101`). The coordinator's claim check, which the
   proposal targets, already blocks only on more than 50 percent key overlap
   (`agent-coordinator/src/feature_registry.py:277-303`).
2. **A human authorization on every OpenSpec PR.** Every `openspec/` PR carries the
   `proposal_acceptance` gate that only `--proposal-accepted` releases
   (`skills/merge-pull-requests/scripts/build_plan.py:39-56`), and `TRUST_POSTURE.md`
   sets `merge: block`. AI review can block a merge but can never authorize one.
3. **Integration is a session-shaped human ritual.** Merges happen in bursts when the
   owner runs a sync-point pass (75 commits on main on October 11, zero on 21 of the last
   30 days). Between passes, cloud agents keep planning, and WIP inflates.

The deeper constraint is the one the user named: verification attention is the scarce
resource, and the current design routes all of it to one human at one gate at the end,
on PRs whose size (p90 14.5k lines) makes human verification impossible.

The plan below keeps the proposal's direction (small slices, AI-primary gates,
overlap-scoped blocking, a continuous mode) and changes its targets. It adds four things
the proposal omits: a planning WIP limit, a local review queue as the cloud-to-local
bridge, an explicit experimentation path, and a measurement baseline.

---

## 2. Where the time actually goes

Numbers from GitHub and git as of 2026-11-01 (60-day window unless noted).

| Metric | Value |
|---|---|
| Merged PRs, last 60 days | 157 (September 124, October 33, one since October 15) |
| Branch-to-merge time | median 2.1 h, p90 96 h, max 27 d |
| Lines changed per merged PR | median 617, p90 14,502, 27 PRs over 5k lines |
| Commits on main, last 30 days | 111 on 9 distinct days, 75 of them on one day |
| Open PRs | 37: 20 Dependabot, 9 `openspec/`, 6 `claude/`, 2 `feat/`; median age 26 d |
| Active OpenSpec changes | 120, of which 93 have no task checked and 11 are done but unarchived |
| Archived changes per month | Aug 18, Sep 43, Oct 7 |
| Roadmaps | 13, most in `planning` with dozens of approved-but-unstarted items |
| CI | 2 workflows, 6 required checks, about 10-12 min wall-clock per PR run |

Four readings of these numbers:

- **The median is fast; the tail is the pain.** Three quarters of PRs merge inside a day.
  The multi-day tail is made of large PRs and PRs that wait for the next sync-point pass.
- **Throughput collapsed, planning did not.** One merge in the last two weeks, while ten
  new agent PRs opened October 23-26 and the change backlog kept growing. The archive
  rate fell from 43 to 7 per month. The system is producing proposals six times faster
  than it closes them.
- **The open-PR backlog is mostly noise.** Twenty Dependabot PRs sit at 35-43 days even
  though they are already `auto_executable` in the merge plan. They wait only because
  nobody runs the pass.
- **PR size defeats the review model.** A multi-vendor review of a 14k-line PR produces
  findings nobody can act on, so the human either rubber-stamps or defers.

The proposal's "10-20 unresolved mergers" is nine agent PRs plus Dependabot. The real
backlog is upstream of the PRs: 120 changes, 93 of them never started.

---

## 3. Review of the proposal, section by section

### 3.1 Decouple active work from merge eligibility

**Direction: agree. Target: wrong.** `merge_queue.py`, `merge_train.py` and the claim
tables already block only on overlap. The global gate lives in:

- `skills/shared/active_agents.py` (the liveness check),
- `skills/merge-pull-requests/scripts/execution_safety.py:12-34` (`default_sync_point_guard`),
- `skills/merge-pull-requests/scripts/execute_plan.py:358-370` (kernel call, no override),
- `skills/merge-pull-requests/scripts/main_convergence.py:538-571` (post-merge convergence),
- `skills/expedite/scripts/expedite.py:90-98` (readiness gate),
- `agent-coordinator/src/sync_points.py:60-78` (the read-only status mirror),
- `openspec/specs/skill-workflow/spec.md`, requirement "Main Receives Work Through PR
  Sync Points" (the normative text that makes the guard mandatory).

Two facts sharpen the fix. First, merging a PR on GitHub does not disturb any local
worktree; the only local side effects are the fast-forward of the shared checkout's
`main` and the post-merge cleanup of the *merged change's own* worktree. So the guard
protects far more than it needs to. Second, prototype worktrees auto-pin
(`skills/worktree/scripts/worktree.py:764-768`) and block until torn down, which is why
an exploration session can freeze merging for days.

**Acceptance as written is already true today** in the coordinator and false in the
skill. The acceptance test should be rewritten against the skill path: "with an active
worktree for change A on this host, `execute_plan.py --execute` merges PR for change B."

### 3.2 Force smaller integration units

**Agree, and the gap is larger than the proposal states.** Work packages are units of
parallel *execution*, never of *integration*. `implement-feature` merges every package
branch back into the feature branch and opens one PR
(`skills/implement-feature/SKILL.md:150,431,648-655`). The schema already has
`decomposition: stacked` meaning "lands on main independently behind a flag"
(`openspec/schemas/work-packages.schema.json:333-343`), but `plan-feature` never emits it
and none of the three `enqueue` callers pass it, so the hint is dead. The schema says
`stack_position` is 0-indexed; `merge_queue.py:139` says 1-based.

What is missing is a planning artifact that names a *mergeable subset*: a set of packages
whose dependencies are closed, whose contracts are present, whose tests run on main
alone, and whose incomplete paths are flagged off. Section 5, workstream 4 designs it.

### 3.3 Elevate AI review and CI to the primary merge gate

**Agree with a condition.** Today AI review is a veto, never an authorization
(`skills/merge-pull-requests/SKILL.md:140-143`: "Unanimous agreement does not release
`proposal_acceptance`"). Making it the primary gate for low-risk changes is the right
move, but two preconditions are not met:

- **Quorum is one vendor in cloud containers** (`TRUST_POSTURE.md`, "Review quorum in
  cloud containers"). A single-vendor Claude review of Claude-written code is not an
  independent signal. The human merge gate is explicitly the compensating control. Auto-
  merge cannot be turned on until a second lane exists for cloud-produced PRs. The
  `openrouter-review-lane` change (in progress) and the local review queue (workstream 3)
  both close this.
- **Risk classification is judged, not declared.** `_classify_pr_risk` in
  `vendor_review.py:181-256` is an LLM judgment used only to decide review eligibility.
  An auto-merge policy needs a deterministic path-based class first, with the judgment
  as a refinement that can only raise risk, never lower it.

The proposal's "optional one-click confirmation" is the `notify_with_timeout`
disposition that `TRUST_POSTURE.md` already defines. It needs a notification channel, which
the posture file notes does not exist yet.

### 3.4 Continuous rebase-and-land

**Partly disagree.** The speculative merge train only simulates. `execute_wave_merge`
has no production caller, `CoordinatorTrainBackend` is dead code, and real merges go
through `gh pr merge` (`agent-coordinator/src/merge_train.py:1017-1109`,
`skills/merge-pull-requests/scripts/merge_backend.py:109-178`). Finishing the train is
the highest-complexity item in `monorepo-merge-scaling-research.md` and it solves a
100-PR-per-day problem. A 5-10 person team with 10-minute CI does not have that
problem. GitHub's merge queue already triggers CI here (`merge_group` is in `ci.yml`),
and `update_pull_request_branch` plus auto-merge give cascading rebase for free.

Recommendation: use GitHub's merge queue and auto-merge as the landing mechanism, keep
the coordinator train as a planning and partitioning tool (its `compute_partitions`
by lock prefix is useful for overlap detection), and freeze the train-landing code.
Fast revert stays first-class and is cheap: a revert PR is just another low-risk slice.

### 3.5 Explicit solo / small-team continuous mode

**Agree. Do not add a new flag system.** The mode vocabulary exists (solo and team in
`docs/guides/multiplayer-collaboration.md`), gate dispositions exist (`TRUST_POSTURE.md`),
and sync windows with an `auto_merge_ceiling` exist in the template. "Continuous mode"
is a posture file plus a few config defaults, documented as a reference profile.

### 3.6 What the proposal omits

1. **Planning WIP.** Nothing in the proposal slows the inflow. With `proposal_approval:
   auto`, a cloud agent can mint a change in minutes, and 93 of 120 changes are untouched.
   Small slices without a WIP limit produce more small things waiting.
2. **The Dependabot stream.** Twenty of 37 open PRs. Separate it entirely.
3. **The cloud-to-local bridge.** The proposal does not say where review runs. The user's
   constraint is that subscriptions (Codex, Gemini, Grok, OpenRouter via pi) live on the
   device, so multi-vendor review must run there. There is no built mechanism for a local
   agent to pull review work for a cloud-produced PR, though every piece exists: location-
   tagged lanes in `agents.yaml`, the `subscription-local` tier in `routing.yaml`, work-
   queue review claims that exclude the submitter (`work_queue.py:431-436`), and the
   `capability_unavailable` park in the supervisor-worker contract.
4. **Experimentation.** Greenfield exploration needs a path cheaper than `plan-feature`
   and more durable than a chat. Today the lightest path is `quick-task --write`, which
   warns at 5 files and never opens the PR.
5. **A baseline.** The success criteria say "drops significantly" with no number.

---

## 4. Target operating model

For one person now and 5-10 people later, exploring greenfield ideas, with cloud agents
implementing and local agents verifying.

**Principles**

- **Main is always releasable; slices land behind flags.** No feature branch lives more
  than two working days. A feature is a sequence of slice PRs, not one PR.
- **Verification is routed, not gated.** Deterministic checks run first, AI review with
  real vendor diversity runs second, humans see only high-risk surfaces and reviewer
  disagreements. Humans verify *intent* at plan time (is this what we want) and at demo
  time (does it do that), not line-level code at merge time.
- **WIP is capped at the planning level.** A change that nobody starts within 30 days is
  archived as abandoned. New changes are refused above the cap.
- **Cloud implements, local verifies.** Cloud sessions are isolated and parallel, so
  planning and implementation go there. Subscriptions and the GX10 are on the device, so
  review, validation that needs Docker, and the merge pass go there. The local review
  queue connects the two.
- **Experiments are cheap and disposable.** A spike is a time-boxed branch with no
  ceremony. Only a spike that survives becomes a proposal, and the proposal reuses the
  spike's diff as its first slice.

**The flow**

```
idea
 └─ spike (cloud, ≤1 day, quick-task --spike)            no OpenSpec, PR auto-closes at TTL
     └─ proposal-lite (cloud, plan-feature --lite)        proposal + spec deltas + slices
         └─ slice PRs (cloud, implement-feature)          one PR per slice, flagged, stacked when needed
             └─ local review queue (device)               subscription lanes, quorum 2, findings to ledger
                 └─ merge policy (device or scheduled)    low risk auto, medium notify, high human
                     └─ demo / validation signals         human verifies intent, not code
```

---

## 5. Workstreams

Ordered so that each unblocks the next. Effort is in working days of agent time plus
owner review.

### WS0. Baseline and declutter (1-2 days)

- **Metrics.** Extend `agent-metrics` with an `integration` report: time from first
  commit to merge, lines per PR, open-PR age, active changes by task state, merges per
  day. Run it now to pin the baseline, and run it weekly.
- **Archive the done.** Archive the 11 fully checked changes.
- **Expire the untouched.** Move the 93 changes with no checked task to
  `openspec/changes/archive/<date>-<id>/` with `status: abandoned` in `proposal.md`
  unless they are referenced by a roadmap item in `approved` or `in_progress`. This is
  reversible: an abandoned change can be re-opened by copying it back. Rough target:
  under 20 active changes.
- **Cap roadmaps.** Mark all but two or three roadmaps `paused`. Thirteen roadmaps in
  `planning` is a backlog of intentions, not a plan.
- **Drain Dependabot.** Run the merge pass with `--execute` on the 20 Dependabot PRs
  (they are already `auto_executable`), then enable workstream 1b so they never
  accumulate again.

Acceptance: metrics report committed under `docs/reports/`; active changes under 20;
zero Dependabot PRs older than 7 days.

### WS1. Fix the gate (2-3 days)

**1a. Scope the active-agent guard to what it protects.** Replace the repo-wide check
with an overlap check:

- Block when an active worktree sits on the branch being merged (the merge would delete
  or rebase under a live agent).
- Block when another sync-point writer holds `sync-point:main-convergence` (already a
  coordinator lock).
- Do not block on worktrees for other changes. Fast-forwarding the shared checkout's
  `main` is safe for them.
- Add a posture knob `sync_point.active_agent_guard: repo-wide | overlap | off`
  (default `overlap`) in `TRUST_POSTURE.md` so a team that wants the old behavior can
  keep it.

Touch: `active_agents.py` (add a `--scope` argument and a `branches` filter),
`execution_safety.py`, `execute_plan.py`, `main_convergence.py`, `expedite.py`,
`sync_points.py`, the skill-workflow spec requirement, and the three SKILL.md files that
quote the condition. Unpin prototype worktrees on prototype completion rather than on
teardown.

Acceptance: with an active worktree for change A on the host, `execute_plan.py --execute`
merges the PR for change B; with an active worktree on B's own branch, it blocks and names
the worktree.

**1b. Separate the Dependabot stream.** Declare a `sync_windows` entry in
`TRUST_POSTURE.md` with `auto_merge_ceiling: automation`, run it as a scheduled task
(daily), and turn on GitHub auto-merge for Dependabot PRs whose required checks pass.
Grouped Dependabot updates (one PR per ecosystem per week) cut the count further.

**1c. Use GitHub's merge queue for landing.** Enable the merge queue on `main` with the
six required checks. `execute_plan.py` enqueues instead of merging directly (the
`--merge-queue` path in `merge_pr.py:461-466` exists). Freeze the coordinator train-
landing code behind a comment and a decision record; keep `compute_partitions` as a
read-only overlap report.

Acceptance: a ready, non-overlapping slice lands within one CI cycle of being approved,
without a human running a pass.

### WS2. Risk-tiered merge authorization (3-4 days)

**2a. Deterministic risk classes.** Add `openspec/merge-policy.yaml`:

```yaml
schema_version: 1
risk_classes:
  low:
    paths: ["docs/**", "skills/*/SKILL.md", "**/tests/**", "openspec/changes/**", "*.md"]
  medium:
    paths: ["skills/**", "apps/**", "packages/**"]
  high:
    paths: ["agent-coordinator/src/**", "agent-coordinator/migrations/**",
            "TRUST_POSTURE.md", ".github/**", "openspec/specs/**", "skills/shared/**"]
# A PR's class is the highest class of any file it touches.
# The judged classification in vendor_review.py may raise the class, never lower it.
```

**2b. Per-class merge disposition.** Extend the trust-posture schema so `merge` can be
keyed by class:

```yaml
merge:
  low:    { disposition: auto }
  medium: { disposition: notify_with_timeout, timeout_seconds: 7200, default_action: proceed }
  high:   { disposition: block }
```

`auto` for a class requires all of: required checks green, review quorum met with at
least two distinct vendors, no open blocking ledger item, no overlap with an active
claim above the sequential threshold, and the PR body carrying a change-id or spike-id.
Missing any one falls back to `block` and records which one.

**2c. Retire the second human acceptance for slices.** `proposal_approval` is already
`auto`; demanding `--proposal-accepted` at merge is the same decision asked twice. For a
slice PR whose plan review converged and whose slice acceptance scenarios pass, release
`proposal_acceptance` automatically. Keep it for PRs that change `openspec/specs/`
(those are high-risk anyway).

**2d. Get to quorum two everywhere.** Land `openrouter-review-lane` (already in progress)
so cloud containers have a second vendor, and route cloud-produced PRs to the local
review queue (WS3). Delete the cloud quorum-one exception from `TRUST_POSTURE.md` when
either is live.

**2e. Notification channel.** `notify_with_timeout` is unusable until something sends the
notification. The coordinator's notification service (Gmail, Telegram, webhook with
reply-to-approve) exists; wire the merge gate to it. For the solo owner, Telegram with a
reply-to-approve token is enough.

Acceptance: a docs-only slice with green CI and two-vendor review lands with no human
action; a coordinator slice waits for a human; the audit trail names the class and the
rule that fired.

### WS3. Local review queue: the cloud-to-local bridge (4-5 days)

This is the user's earlier idea, specified so it composes with what exists.

**Producer side (cloud).** When `implement-feature` or `autopilot` opens a slice PR, it
calls `submit_work(task_type="review", pr=N, change_id, slice_id, required_lanes=[...],
head_sha)`. `required_lanes` comes from `routing.yaml`'s cost ladder: prefer
`subscription-local`, then `subscription-cloud`, then `metered-api`. The cloud session
then subscribes to PR activity and ends its turn; it does not poll.

**Consumer side (device).** A `review-worker` process on the GX10 or a laptop runs under
`/loop` or a cron entry. Each tick it claims the oldest ready review task whose
`required_lanes` it can serve (the work queue already excludes the submitter from
claiming its own review), checks out the PR head in a managed worktree, runs
`review_dispatcher.py` with the local lanes, writes findings to the change's review
ledger and as a PR review, and calls `complete_work` with the consensus verdict and
`head_sha`. If the head moved, it re-submits rather than completing.

**Heavier validation on the same worker.** The Docker-dependent phases of
`validate-feature` (deploy, smoke, security, e2e) run on the same worker as a second task
type, `validate`. This is the "local CI" the user described: it scales with devices and
subscriptions rather than with GitHub minutes, and it leaves the six required checks on
GitHub as the floor.

**Merge side.** The merge policy (WS2) reads the verdict from the ledger keyed by
`head_sha`. The merge pass itself can run on the device (subscription-local) or as a
scheduled sync window, whichever is on.

**Failure modes to design for.** Worker offline: tasks age, the kanban board shows
`review: waiting for lane`, and after a configurable delay the task falls through to the
next tier of the ladder. Head moved mid-review: verdict is bound to `head_sha` and simply
does not apply. Self-review: already excluded by the queue.

Acceptance: a PR opened by a cloud session receives a two-vendor review from the device
within 30 minutes of the worker's next tick, with no human involvement, and the merge
policy sees the verdict.

### WS4. Mergeable slices in OpenSpec (5-6 days)

**4a. The artifact.** Add a `slices` section to `work-packages.yaml` (schema change, not a
new file, so existing validators extend rather than fork):

```yaml
slices:
  - slice_id: s1-contracts
    packages: [wp-contracts]
    lands_behind: none            # none | flag:<name>
    depends_on_slices: []
    risk_class: medium            # defaults to the highest class of its packages' write_allow
    acceptance:                   # scenario IDs from this change's spec deltas
      - skill-workflow.slice-contract-published
    size_budget_lines: 800
  - slice_id: s2-core
    packages: [wp-core, wp-core-tests]
    lands_behind: flag:continuous_mode
    depends_on_slices: [s1-contracts]
    acceptance: [...]
```

**4b. Slice closure validator** in `validate-packages`: every `depends_on` of a package
in a slice is inside the slice, in an earlier slice, or already on main; write scopes of
slices that may land in parallel are disjoint; every slice has at least one acceptance
scenario and at least one verification step that can run on main alone; a slice with
`lands_behind: flag:` names a flag that `flags.yaml` will carry.

**4c. Planning emits slices.** `plan-feature` Step 8 adds a slicing pass after the DAG:
contracts first, then one slice per module group, integration last. An L change must
have at least two slices, an XL at least three. `iterate-on-plan` gains a `landability`
axis next to `parallelizability`: can each slice merge on its own, and is each under its
size budget. `reviewer-shaped-prs` gets its size budget from here instead of defining its
own.

**4d. One PR per slice.** `implement-feature` opens `openspec/<id>--<slice_id>` per slice
and a PR per branch. A slice with `depends_on_slices` bases its PR on the previous slice's
branch (stacked) and GitHub retargets to `main` when the base merges. Pass
`decomposition="stacked"` and `stack_position` to `enqueue` and fix the 0-versus-1 index
mismatch. The PR body carries the slice's acceptance scenarios and the `DIDN'T TOUCH`
section lists the later slices by id.

**4e. Flags.** `lands_behind: flag:<name>` is the contract that lets an incomplete feature
land. The flag registry already exists (`flags.yaml`, created automatically by
`merge_queue.enqueue` for stacked packages). Add a cleanup task to the final slice that
removes the flag, so flags do not accumulate.

Acceptance: `plan-feature` on an L-sized change produces at least two slices that pass the
closure validator; `implement-feature` opens one PR per slice; the first slice merges
while the second is still being implemented.

### WS5. Faster planning and experimentation (3-4 days)

**5a. Spikes.** `quick-task --spike <slug>` creates `spike/<slug>` in a cloud session,
opens a draft PR labelled `spike` with a 3-day TTL in the body, and skips every OpenSpec
artifact. The merge policy never merges a spike. A scheduled task closes expired spikes.
Promotion is `plan-feature --from-spike <slug>`, which reads the diff, drafts the proposal
and spec deltas from it, and makes the spike diff the first slice. `prototype-feature`
stays for the case where the decision is between competing designs.

**5b. Proposal-lite.** `plan-feature --lite` for XS and S changes: proposal, spec deltas,
a single slice, no `design.md`, no contracts. Lite plans skip multi-vendor plan review and
go straight to implementation; their slice PR gets the full implementation review. This
replaces most of what people use `quick-task --write` for today.

**5c. WIP limits.** In `openspec/config.yaml`:

```yaml
wip:
  active_changes_max: 15
  per_principal_max: 5
  abandon_after_days_untouched: 30
```

`plan-feature` refuses to create a change above the cap unless `--override` is given with
a reason, and `prioritize-proposals` lists the changes closest to expiry. Expiry runs as a
scheduled task and archives with `status: abandoned`.

**5d. Decide at plan time what the human verifies.** The `verification-signals` section
that `add-verification-signals-contract-to-plan-feature` proposes becomes per slice: for
each slice, what observable signal tells the owner it works (a demo URL, a scenario
output, a metric). That is where human attention goes, instead of the diff.

Acceptance: an idea goes from chat to a spike PR in one command; a surviving spike becomes
a sliced plan in one command; the change count cannot exceed the cap without an
explicit override in the audit trail.

### WS6. Documentation and the reference profile (1-2 days)

- `docs/guides/continuous-integration.md`: the external note. Principles, the flow
  diagram, the posture profile, what a team gives up (line-level human review of low-risk
  code) and what it keeps (required checks, two-vendor review, high-risk human gate, flags,
  fast revert, change-id linkage).
- A `continuous` column in the skill table of `docs/guides/multiplayer-collaboration.md`,
  and a `TRUST_POSTURE.continuous.md` profile next to the template.
- `docs/guides/git-conventions.md`: slice branches, stacked PR rules, spike branches,
  rebase-merge stays for agent slices and squash for Dependabot.
- `docs/guides/workflow.md`: the spike and lite paths in the command tree.

### WS7. Observability (1-2 days)

A per-PR merge-readiness record with a single `blocked_by` reason from a closed set:
`ci`, `review_quorum`, `blocking_finding`, `overlap`, `risk_gate`, `active_worktree`,
`stale`, `human_gate`. Surface it in the kanban board's sync-point banner and in the
`agent-metrics` integration report. The distinction the proposal asks for, "blocked only
by overlap" versus "blocked by the global guard", falls out of this.

---

## 6. Sequencing

| Phase | Workstreams | Exit test |
|---|---|---|
| A: unblock (days 1-5) | WS0, WS1a, WS1b, WS1c | Dependabot backlog zero; a non-overlapping PR merges while another change has an active worktree; active changes under 20 |
| B: route verification (days 6-15) | WS2, WS3, WS7 | A cloud-produced docs slice auto-merges after a two-vendor review that ran on the device; a coordinator slice waits for the owner |
| C: slice at the source (days 16-30) | WS4, WS5 | A real L change lands as three slice PRs; a spike is promoted into a sliced plan; the WIP cap holds |
| D: write it down (days 31-35) | WS6, retrospective against the WS0 baseline | A newcomer can enable the profile from the docs alone |

Phase A is deliberately small and mostly configuration and one guard change. It should be
visible in the metrics within a week.

**Targets against the baseline** (to make "significantly" measurable):

| Metric | Baseline | Target after phase C |
|---|---|---|
| Branch-to-merge p90 | 96 h | under 24 h |
| Lines per merged PR, median / p90 | 617 / 14,502 | under 400 / under 2,000 |
| Days with a merge, per 30 | 9 | 20 or more |
| Open PR median age | 26 d | under 3 d |
| Active changes | 120 | under 20 |
| Changes with no task started | 93 | under 5 |

---

## 7. Decisions made so far, revisited

| Decision | Where | Verdict |
|---|---|---|
| Sync-point skills are user-invoked and run a repo-wide active-agent guard | skill-workflow spec; `active_agents.py` | **Change.** Scope to overlap (WS1a); allow scheduled sync windows, which the spec already permits |
| One PR per OpenSpec change | `implement-feature`, `autopilot` | **Change.** One PR per slice (WS4d) |
| Rebase-merge for agent PRs, squash for automation | `git-conventions.md` | **Keep.** Rebase suits small logical slices; squash suits Dependabot |
| Coordinator speculative merge train lands waves | `merge_train.py`, never wired | **Freeze.** Use GitHub merge queue; keep partitioning as a report (WS1c) |
| File-tier merge plan is authoritative, coordinator is projection | `merge-infrastructure` decisions | **Keep.** The merge policy reads and writes the plan |
| Trust posture as typed gate dispositions | `TRUST_POSTURE.md` | **Keep and extend** with per-class merge dispositions and a guard knob (WS2b, WS1a) |
| Cloud containers accept quorum one | `TRUST_POSTURE.md` temporary section | **Retire** once the local review queue or OpenRouter lane is live (WS2d) |
| Every OpenSpec PR needs `--proposal-accepted` at merge | `build_plan.py` | **Retire for slices** whose plan review converged; keep for spec changes (WS2c) |
| Work packages are execution units with locks and scopes | `work-packages.schema.json` | **Keep;** add slices on top rather than replacing packages |
| `decomposition: stacked` per package | schema, unused | **Repurpose** as the per-slice stacking signal; fix the index mismatch |
| Full OpenSpec ceremony for every change | `plan-feature` | **Tier it.** Spike, lite, full (WS5) |
| `proposal_approval: auto` with no inflow limit | posture, config | **Keep auto, add a WIP cap** (WS5c) |
| Thirteen roadmaps, most in planning | `openspec/roadmaps/` | **Cap at two or three active** (WS0) |
| Six required checks; drift gate and coverage ratchet advisory | branch protection | **Keep.** Continuous mode wants fewer mandatory gates, not more. Leave the drift-gate promotion unapplied for now |
| Multi-vendor review with `vendor_diversity` routing and a review ledger | `parallel-infrastructure` | **Keep.** It becomes the primary gate for low risk; the ledger becomes the merge policy's input |
| Worktree registry heartbeats as liveness | `worktree.py` | **Keep for local isolation,** stop using it as a merge gate |
| Cost ladder subscription-local, subscription-cloud, metered | `routing.yaml` | **Keep.** It is the routing rule for review tasks in the queue (WS3) |

---

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Auto-merge lands a bad low-risk change | Path-based class caps what "low" can touch; revert is a one-command slice; the audit trail names the rule that fired |
| Single-vendor review disguised as quorum | Quorum counts distinct vendors, verified by dispatch result not by configuration; cloud exception deleted (WS2d) |
| Slices multiply PRs and reviewer noise | Reviews are AI-first and routed to a queue; humans see only high-risk and disagreement; size budget keeps each slice readable |
| Flags accumulate | Flag removal is a task of the final slice; `flags.yaml` is checked in CI for flags older than 30 days |
| Scoped guard races a local agent on the same branch | The on-branch check stays, as does the coordinator convergence lock and the compare-and-swap push |
| WIP cap frustrates exploration | Spikes do not count toward the cap; the cap applies to OpenSpec changes only |
| Abandoned-change archival loses good ideas | Archival is a move, not a delete, and `prioritize-proposals` can list abandoned changes on request |
| Device review worker is offline for days | Review tasks fall through the cost ladder to the OpenRouter lane after a delay; readiness shows `review_quorum` as the blocker |

---

## 9. Decisions for the owner

These change the shape of the work and are not resolvable from the code.

1. **The high-risk path list.** The draft in WS2a treats `agent-coordinator/src/**`,
   migrations, `skills/shared/**`, `openspec/specs/**`, `.github/**` and
   `TRUST_POSTURE.md` as human-gated. Is that the right set for greenfield work, or
   should the coordinator core be medium?
2. **WIP numbers.** Fifteen active changes and 30 days to abandonment are starting
   values. Lower is better for one person; a team of ten might want per-principal five.
3. **Where the review worker lives.** The GX10 is the obvious host. If it is not always
   on, a laptop under `/loop` works but makes the fall-through delay matter more.
4. **Medium-risk default.** `notify_with_timeout` with `default_action: proceed` after
   two hours is the aggressive choice. `default_action: block` is the conservative one
   and keeps today's behavior for anything the owner does not answer.
5. **Whether to archive the 93 untouched changes now** or run the expiry task once with
   a 60-day threshold first and see what survives.

---

## 10. Suggested OpenSpec changes

Each is one change, sized so it can itself land as one or two slices.

1. `scope-active-agent-guard-to-overlap` (WS1a) — guard semantics, posture knob, spec
   requirement rewrite. Unblocks everything.
2. `declare-dependabot-sync-window-and-merge-queue` (WS1b, WS1c)
3. `add-integration-metrics-report` (WS0, WS7)
4. `add-merge-policy-risk-classes` (WS2a, WS2b, WS2c)
5. `wire-merge-gate-notifications` (WS2e)
6. `add-local-review-queue-worker` (WS3)
7. `add-slices-to-work-packages` (WS4a, WS4b)
8. `emit-slices-from-plan-feature` (WS4c)
9. `open-one-pr-per-slice` (WS4d, WS4e)
10. `add-spike-path-to-quick-task` (WS5a)
11. `add-plan-feature-lite-and-wip-limits` (WS5b, WS5c, WS5d)
12. `document-continuous-integration-profile` (WS6)

Existing changes this plan absorbs or depends on: `openrouter-review-lane` (depends),
`judge-multi-vendor-review-eligibility-for-pull-requests` (depends, nearly done),
`reviewer-shaped-prs` (absorbed into WS4c), `declare-early-draft-pr` (absorbed: the
contracts slice is the early draft PR), `add-verification-signals-contract-to-plan-feature`
(absorbed into WS5d), `ambient-review-ledger` (complementary; the review worker can
consume its per-commit entries), `team-work-queue` and `queue-dispatch-owner-acceptance`
(later; team mode on top of the same queue).
