# Sandboxed Flow: Yolo Inside the Box, Decisions in One Inbox

*Proposal, 2026-11-19. Status: draft for operator review.*

## Motivation

The operator's work is interrupted constantly by Bash approvals. The cause is
structural. Agents run on the operator's filesystem under the operator's uid,
because that is where the OAuth logins for the Claude, Codex, Antigravity and
Grok subscriptions live. With no enforced boundary around a task, the only
safety mechanism left is prefix-matched permission rules in
`.claude/settings.json`, and anything that does not match a rule prompts.

Isolation is declared but not enforced. `agents.yaml` marks agents
`isolation: sandbox`, and `agent-coordinator/src/isolation_contract.py` says
"`sandbox` is a posture label here; enforcement remains a separate concern".
The enforcing change (`dispatch-governance:dg-07`) is a candidate. The cloud
sandbox lane in `add-sandboxed-harness-execution` brokers API keys and gateway
virtual keys, which subscription OAuth logins cannot use, so it does not
remove the reason agents run on the host.

The target flow has three parts:

1. Each task runs in an isolated sandbox with task-specific file and network
   access, and inside that boundary the vendor CLI runs without permission
   prompts.
2. A separate read-only agent reviews the output and its verdict decides
   whether low-risk work lands.
3. The operator specifies and reviews goals, designs and outcomes in one
   interface that spans every project.

Success is measured by what the operator is asked: zero prompts for reversible
actions inside a sandbox, and every remaining decision arriving in one inbox as
a goal, a design or an outcome.

This roadmap is deliberately thin. Most of the mechanism is already specified
in other roadmaps, and this one sequences that work toward the flow above and
adds only the pieces no existing item covers. It must not duplicate:

| Existing work | Reference | State | Role here |
|---|---|---|---|
| Isolation posture detection | `dispatch-governance:dg-03` | candidate | prerequisite of dg-07 |
| Orchestrator obeys the router | `dispatch-governance:dg-06` | approved | prerequisite of dg-07 |
| OS-level sandbox at dispatch (srt renderer, `wrap_command()`) | `dispatch-governance:dg-07` | candidate | the enforcement primitive everything here builds on |
| Egress gateway with boundary-side secret swap | `dispatch-governance:dg-08` | candidate | explicitly not deployed on the local uid; the OAuth spike below decides whether that changes |
| Unified dispatch posture, session credentials | `principal-credential-architecture:pca-03`, `pca-04` | candidate | API-key and proxy-token credentials; not OAuth files |
| Review queue across hosts | `docs/proposals/factory-local-cloud-split.md` Phase 1 | applied; per-lane sandbox wrapping deferred | the read-only reviewer lane |
| Merge verdicts bound to head SHA | `verification-enforcement-discipline:ri-01` | in progress | prerequisite for any automatic merge |
| Headless merge-pull-requests | `roadmap-always-on-agent-automation:ri-12` | candidate | the merge executor |
| Approval gate service | `roadmap-always-on-agent-automation:ri-05` | completed | the one store of gate decisions |
| Trust clamp by isolation posture | change `clamp-trust-by-isolation-posture` | proposed, no roadmap | agent trust level; complementary to gate coupling |
| Visual plan review | change `add-visual-plan-review` | proposed, no roadmap | the design-review surface the inbox links to |
| Escalation inbox per principal, attention digests | `multiplayer-collaboration:ri-09`, `ri-10` | approved | team-mode routing; the inbox here must stay compatible |
| Kanban board | `apps/kanban-viz` | shipped, multi-repo | host of the inbox view |

## Capabilities

### Capability: Sandbox the interactive lead session

The operator's own interactive Claude Code session on the laptop and the GX10
is where most prompts occur today, and it is not a dispatched vendor CLI, so
dg-07 does not cover it. Enable the harness's native Bash sandbox for those
sessions so that sandboxed commands run without asking, and reduce the
permission rules to the irreversible set: force-push, deletion, merge, deploy,
migration and secret writes keep `ask` or `deny`. The exact setting names must
be confirmed against current harness documentation before they are written.
This item has no dependencies and delivers relief before any other item lands.

**Acceptance Outcomes:**
- A local interactive session runs `uv run`, `pytest`, git read commands and worktree-scoped writes with no approval prompt.
- A sandboxed command cannot read `~/.ssh`, `~/.aws` or another repository's checkout; a test demonstrates the denial.
- Every command class in the irreversible set still prompts or is denied, verified by a test that enumerates the set.
- The allow list in `.claude/settings.json` shrinks, and the guide that explains how to write matchable Bash commands is updated to match.

### Capability: Vendor headless-auth and terms audit

Before any subscription login is used unattended, record for each of Claude,
Codex, Antigravity and Grok: whether the subscription terms permit programmatic
or headless use; where the OAuth material lives on disk; whether token refresh
needs a writable path; which hosts inference and token refresh contact; and
whether the CLI accepts a base-URL or proxy override. The repository already
records that Claude's subscription terms push it into the lead or interactive
role and that the Claude review lane therefore uses an API key. The audit
either confirms or updates that for each vendor. The result is a checked-in
table that later items read; it is a spike, not production code.

**Acceptance Outcomes:**
- A checked-in document states, per vendor, the permitted headless use under its subscription, with the source of each statement.
- For each vendor the OAuth material paths, refresh-write requirement, inference hosts and proxy-override support are recorded from an observed run, not from memory.
- Any vendor whose terms forbid unattended subscription use is marked as requiring an API-key or gateway-key lane.

### Capability: Per-vendor credential profile

Add a `credential_profile` to each vendor entry in `agents.yaml`: the auth
mode (`subscription-oauth`, `api-key` or `gateway-key`), the OAuth material
paths to bind into the sandbox, whether those binds are read-only, the
inference and refresh hosts for the egress allowlist, and whether unattended
use is permitted. dg-07's renderer reads the profile so that a sandboxed
dispatch of one vendor sees that vendor's login and no other credential: not
another vendor's login, not the GitHub token, not the coordinator key beyond
its own per-dispatch identity. This is the piece that lets subscription logins
work inside a sandbox, which neither dg-07 nor the credential roadmap covers.

**Acceptance Outcomes:**
- A sandboxed dispatch of each `subscription-oauth` vendor completes an authenticated inference call.
- Inside that sandbox, the other vendors' credential paths, `~/.ssh` and the operator's GitHub token are unreadable; a test asserts each.
- Egress from the sandbox reaches only the hosts in the profile, the coordinator and the hosts the task declares.
- A vendor with unattended use not permitted is refused for headless dispatch with an audit event naming the profile field.

### Capability: Task-scoped file and network grants

A sandbox profile today would be per vendor. The target is per task. Render
each dispatch's writable paths from the work package's declared scope in
`work-packages.yaml` and its network allowlist from the task's declared needs
plus the coordinator's network policy, so that policy stays authored in one
place. A task that declares no network need gets the vendor's inference hosts
and the coordinator and nothing else.

**Acceptance Outcomes:**
- A dispatched work package can write inside its declared scope and its own worktree and nowhere else in the repository.
- A write outside the declared scope fails at the operating system, and the failure is recorded on the dispatch result.
- Two work packages in one change with different declared network needs get different egress allowlists.
- No allowlist or path grant is hand-authored outside `work-packages.yaml` and the coordinator's network policy.

### Capability: Fail-closed yolo mode for sandboxed implementers

Vendor permission-bypass flags are passed only when the dispatch's resolved
isolation is `sandbox` and the wrapper confirms the sandbox is active. dg-07
degrades to unsandboxed dispatch with a warning when the runtime is missing;
that degradation must never coincide with a bypass flag. When the sandbox is
not enforced the dispatch either runs in the vendor's prompting or restricted
mode or is refused, according to posture, and the degradation is recorded.

**Acceptance Outcomes:**
- With an enforced sandbox, an implementer dispatch of each vendor runs to completion with no permission prompt.
- With the sandbox runtime removed, the same dispatch carries no permission-bypass flag; a test asserts the rendered argv.
- Every dispatch result records the isolation that was actually enforced, distinct from the isolation requested.
- A degraded dispatch emits an audit event and appears as a degradation in the session log.

### Capability: Sandbox the read-only review lanes

The review worker runs each vendor lane with the per-lane sandbox that Phase 1
of the local/cloud split deferred: the reviewed tree mounted read-only, write
access only to the lane's output directory, egress only to that vendor's hosts
and the coordinator, and no GitHub write credential. Lanes keep reporting
through the coordinator, which alone publishes the consolidated review.

**Acceptance Outcomes:**
- A review lane cannot modify the tree under review; a test attempts a write and observes the denial.
- A review lane holds no credential able to push, post a review or decide an approval.
- A lane whose sandbox could not be enforced reports as unverified and does not count toward quorum.
- Review results are still recorded per vendor and per head SHA through the existing review-queue endpoints.

### Capability: OAuth token injection spike

A login file readable inside the sandbox can still leave through any allowed
host. The stronger design keeps the token outside and injects it at a proxy on
the sandbox boundary. `dispatch-governance:dg-08` already builds a boundary
secret swap but excludes the local uid, because a same-uid workload can bypass
a resolver-only gateway. This spike tests whether the OS sandbox from dg-07
gives real interception on the local hosts, and whether each vendor CLI works
when its bearer token is injected rather than read from disk, including across
a token refresh. It ends in a decision record: extend dg-08 to the
local-sandbox posture, or keep read-only binds with a tight allowlist.

**Acceptance Outcomes:**
- For each vendor, a recorded result states whether an injected-token dispatch authenticates and survives a token refresh.
- A recorded result states whether a sandboxed process on macOS and on Linux can reach a host without passing the proxy.
- A decision record chooses between extending dg-08 and keeping read-only binds, with the residual exfiltration paths named.

### Capability: Couple gate dispositions to enforced isolation

Let each gate in `TRUST_POSTURE.md` declare a `min_isolation`. A disposition of
`auto` or `notify_with_timeout` holds only when the dispatch that produced the
work ran with enforced isolation at or above that level; otherwise the gate
degrades to `block` with an audit event. This is specified inside
`add-sandboxed-harness-execution` Phase 3, behind the cloud backend. It is
carved out here because it depends only on the local sandbox, and that change
should reference this item instead of restating it. It complements
`clamp-trust-by-isolation-posture`, which caps an agent's trust level and does
not touch gate dispositions.

**Acceptance Outcomes:**
- A gate with `min_isolation: sandbox` and disposition `auto` proceeds for work produced under an enforced sandbox.
- The same gate blocks, with an audit event, for work produced under `worktree` or `none`.
- The enforced isolation is read from the dispatch record, never from a session's self-report or an environment variable.
- A posture file that omits `min_isolation` behaves exactly as it does today.

### Capability: Reviewer-approved landing for low-risk work

Today the coordinator posts reviews with the `COMMENT` event and never
`APPROVE`, and `merge` is `block`: approval stays human by recorded operator
decision. The target flow has a read-only reviewer approve the output. Add a
risk-tiered merge policy: a change merges without the operator when its risk
tier is low, at least two distinct vendors hold verified approving verdicts on
the current head SHA, the implementing dispatch ran under an enforced sandbox,
and required checks pass. Anything else stays `block` and arrives in the inbox
as an outcome. Turning this on is itself an operator decision recorded in
`TRUST_POSTURE.md`; the item ships the mechanism with the gate still `block`.

**Acceptance Outcomes:**
- With the policy enabled, a low-risk change meeting all four conditions merges with no operator action, and the merge record cites the verdicts and head SHA.
- A change missing any one condition does not merge and surfaces as a pending outcome with the unmet condition named.
- A push after the verdicts invalidates them; a test shows the stale verdict does not authorize a merge.
- With the policy absent from the posture file, merge behaviour is unchanged.

### Capability: Project-keyed gate projection

Gate state lives in per-repository files (`checkpoint.json`, `loop-state.json`,
`TRUST_POSTURE.md`) and in the coordinator's approval service, with no view
across repositories. Project every pending gate from each enrolled repository
into the coordinator, keyed by project, and expose one listing of everything
awaiting the operator. Git remains authoritative per repository: the
projection is rebuilt from the repositories and is never written back as a
second source of truth. Decisions go through the existing approval gate
service and the owning repository records them as it does today.

**Acceptance Outcomes:**
- One coordinator request returns every pending gate across at least two enrolled repositories, each with project, gate type, subject, options and deadline.
- Deleting the projection and rebuilding it from the repositories yields the same pending set.
- A decision made through the listing reaches the owning repository's gate record through the existing approval service, with no new decision store.
- A repository the coordinator cannot reach is reported as degraded, not silently omitted.

### Capability: Outcome evidence packet

An outcome decision needs the evidence in one place. For each completed task,
assemble a compact packet: what was asked, a diff summary, the review verdicts
by vendor with their head SHA, validation results, the isolation that was
actually enforced, and any degradations. The packet is a view assembled from
existing records, not a new authority.

**Acceptance Outcomes:**
- Every task that reaches a merge or outcome gate has a packet reachable from its gate record.
- The packet states the enforced isolation and lists every recorded degradation, including a single-vendor review.
- Each claim in the packet links to the record it was read from.

### Capability: Decision inbox view

Add a gate-first view to `apps/kanban-viz` over the projection: three lanes,
goals (roadmap approvals), designs (plan and proposal reviews) and outcomes
(merge and validation gates), across all projects, ordered by deadline. The
operator decides from the view. A design opens its visual plan review where
one exists; an outcome opens its evidence packet and pull request. The existing
board stays as the observation surface. The view must remain compatible with
the per-principal escalation inbox and attention digests planned for team mode
and adds no prompt or gate in solo mode.

**Acceptance Outcomes:**
- The view lists pending decisions from at least two repositories in one screen, grouped as goals, designs and outcomes.
- Approving or rejecting from the view records the decision through the approval service and the item leaves the view within one refresh.
- An outcome entry opens its evidence packet; a design entry opens its plan review artifact when present.
- With no pending gates the view is empty and creates no work for the operator.

### Capability: Approval notifications with inbox deep links

`TRUST_POSTURE.md` records that `notify_with_timeout` cannot proceed because no
approval-notification channel exists, while notifiers already exist under
`agent-coordinator/src/notifications/`. Wire those notifiers to gate creation
and deadline events with a deep link into the inbox entry, so that
`notify_with_timeout` becomes a usable disposition and the operator does not
need to watch the inbox.

**Acceptance Outcomes:**
- Creating a gate that needs the operator sends one notification carrying a link that opens that inbox entry.
- A `notify_with_timeout` gate proceeds on timeout only after its notification was delivered; an undelivered notification leaves the gate blocked.
- Notification volume respects a per-day limit, with the overflow collected into one digest.

## Constraints

- The roadmap must not restate or fork work owned by another roadmap; it references those items as cross-roadmap dependencies.
- A permission-bypass flag must never be passed to a vendor CLI whose sandbox is not enforced.
- A process shaped by model output must hold only the credentials its role needs; reviewers must hold no write credential.
- Enforced isolation must be read from dispatch records, never from session self-report or environment variables.
- Network and path policy must be authored once, in the coordinator's network policy and `work-packages.yaml`, and only rendered elsewhere.
- Git must remain the authoritative record per repository; coordinator projections must be rebuildable from it.
- Subscription logins must be used unattended only where the vendor audit records that the terms permit it.
- Solo mode must gain no new prompt, gate or pull-request checkpoint.
- Every gate change must default to today's behaviour when the posture file does not opt in.
- The managed cloud harness already provides its own sandbox and proxy; items here must detect it and skip local sandbox wrapping.

## Phases

### Phase 0: Immediate relief (no dependencies)

- Sandbox the interactive lead session
- Vendor headless-auth and terms audit

### Phase 1: Yolo inside the box (after dispatch-governance dg-07)

- Per-vendor credential profile (needs the audit and `dispatch-governance:dg-07`)
- Task-scoped file and network grants (needs the credential profile and `dispatch-governance:dg-07`)
- Fail-closed yolo mode for sandboxed implementers (needs the credential profile)
- Sandbox the read-only review lanes (needs the credential profile)
- OAuth token injection spike (needs the audit and the credential profile; informs `dispatch-governance:dg-08`)

### Phase 2: Let the reviewer decide low-risk work

- Couple gate dispositions to enforced isolation (needs fail-closed yolo mode)
- Reviewer-approved landing for low-risk work (needs gate coupling and sandboxed review lanes, plus `verification-enforcement-discipline:ri-01` and `roadmap-always-on-agent-automation:ri-12`)

### Phase 3: One inbox across projects (can start in parallel with Phase 1)

- Project-keyed gate projection (no dependency inside this roadmap)
- Outcome evidence packet (needs the projection and fail-closed yolo mode, which records enforced isolation)
- Decision inbox view (needs the projection and the evidence packet)
- Approval notifications with inbox deep links (needs the inbox view)

## Out of Scope

- Building the OS sandbox renderer or `wrap_command()`; that is `dispatch-governance:dg-07`.
- The cloud sandbox backend, credential brokering through OpenBao and gateway virtual keys; that is `add-sandboxed-harness-execution` and the `principal-credential-architecture` roadmap.
- Building the egress gateway; this roadmap only decides, by spike, whether `dispatch-governance:dg-08` should extend to the local-sandbox posture.
- The dispatcher daemon and scheduled sync points; that is `roadmap-always-on-agent-automation`.
- Owner-routed escalation, attention budgets and other team-mode routing; that is `multiplayer-collaboration`.
- The visual plan review surface itself; that is `add-visual-plan-review`.
- A new web application; the inbox is a view in `apps/kanban-viz`.
- Enabling automatic merge; this roadmap ships the mechanism and leaves the posture decision to the operator.
