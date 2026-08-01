# Dispatch Governance: From Routing Decision to Enforced Isolation

## Motivation

The coordinator decides a great deal about how agents run and enforces almost none of it.

`agents.yaml` declares an `isolation` mode per agent. `agent-coordinator/src/agents_config.py:264`
validates it against `{"worktree", "sandbox", "none"}`, stores it, exposes it through
`get_agent_isolation()` at `:979`, and `tests/test_agents_config_isolation.py:170` asserts that
`codex` resolves to `"sandbox"`. No production caller reads the value. An agent declared
`isolation: sandbox` runs today exactly like one declared `isolation: none`.

The same pattern repeats across the dispatch path. `network_policies.py` can answer
"may this agent reach this domain?" — but only if the agent volunteers the question; nothing
enforces the answer at the socket. `agents.yaml:60-66` and `:131-137` encode per-mode sandbox
intent (`--allowedTools Read,Grep,Glob` for Claude, `exec -s read-only` for Codex) in three
mutually unintelligible vendor dialects, enforced by whatever each vendor chose to implement
and verifiable by us in no way at all. The file's own header comment asserts that "the dispatch
mode controls sandbox permissions," which is aspiration rather than description.

The planned task router is about to make this sharper rather than better. It returns "vendor,
location, model, **isolation**, dispatch mode, and rationale" — a fifth consumer of a field that
still means nothing at the point of execution. Building a careful deterministic router that emits
an inert value is the failure mode this epic exists to prevent.

That router does not start from nothing. `add-adaptive-model-router` merged on 2026-07-14
(PR #237, 3,794 lines) and landed the routing *intelligence*: `model_routing/resolver.py` scoring
candidates on a success-adjusted cost-per-completed-task utility, feedback posteriors,
epsilon-greedy exploration under a spend ceiling, OpenAPI contracts for five `/routing/*` paths,
DB contracts for four tables, and an `OpenAICompatAdapter` for OpenRouter and local endpoints. It
also replaced the hardcoded `_estimate_cost_delta` stub in `skills/autopilot-roadmap/scripts/policy.py`
with catalog-aware pricing.

Every wiring task was deliberately deferred to an environment with Postgres and a Node toolchain.
The consequence is that the intelligence is **inert**: there is no `/routing/*` endpoint, no
`ROUTING_ADAPTIVE` flag, and no applied migration anywhere in `agent-coordinator/src`. The change
sits at 21 of 71 task checkboxes with a documented backlog. This epic therefore begins by wiring
what already merged, and extends that single resolver rather than standing up a second one beside
it — two resolvers scoring overlapping decisions would be a worse outcome than the inert field
this epic set out to fix.

Meanwhile the pressure toward unattended operation is increasing. `TRUST_POSTURE.md` exists
specifically so operators can flip human gates from `block` to `auto`, and symphony's
`trust-posture-binding` item commits to a posture artifact declaring "sandbox mode, network
allowlist" bound to `policy_engine.py` so posture is "enforceable, not just documented."
There is currently no mechanism by which it could be enforceable. Every gate flipped to `auto`
removes a human from the loop; machine-level containment is what should backfill the removed
human.

**Success looks like**: a single decision path where the router decides isolation, the
orchestrator carries that decision into dispatch, and the dispatch layer enforces it at the
operating system — with the whole chain observable in the audit trail and degrading loudly,
never silently, where the platform cannot support it.

## Capabilities

### Capability: Wired model-routing core

The deferred half of `add-adaptive-model-router`: the `model_routing` DB migration and catalog
service, the `/routing/*` HTTP endpoints plus MCP tool matching the already-merged OpenAPI
contract, `ROUTING_ADAPTIVE` delegation in `agents_config.resolve_archetype_for_phase` with
static-tier fallback, `endpoint_kind` / `base_url` fields in the `agents.yaml` schema, local
endpoint registration and health probe, refresher and ledger scheduling in `WatchdogService`,
and `OpenAICompatAdapter` threaded into `review_dispatcher`'s discovery order.

This is the substrate the rest of the epic assumes. The scoring logic already exists and is
unit-tested; what is missing is every path by which anything can reach it.

**Acceptance Outcomes:**
- The `/routing/*` paths in the merged OpenAPI contract are served by real endpoints and a matching MCP tool
- The `model_routing` migration is applied and `catalog.py` reads from it with no external call on the read path
- `ROUTING_ADAPTIVE` off reproduces today's static-tier behavior exactly, and on delegates to the resolver
- `OpenAICompatAdapter` is reachable through `review_dispatcher`'s discovery order

### Capability: Vendor capability and availability registry

A coordinator `vendor_registry` surface holding static capabilities from `agents.yaml` plus
dynamic availability and rate-limit windows with known reset times, exposed as `GET /vendors`
and `GET /vendors/{id}/availability`.

Cost is deliberately **not** part of this capability. The versioned cost table this item
originally carried was delivered by PR #237, which replaced the `policy.py` stub tiers with
catalog-aware pricing; vendor cost is read from that catalog rather than stored a second time.
What remains unbuilt is the availability half — nothing in the coordinator answers "is this
vendor reachable right now, and when does its rate limit reset?"

**Acceptance Outcomes:**
- `GET /vendors` returns capabilities, availability, and rate-limit reset times for every configured vendor
- Availability reflects probed vendor state rather than static configuration alone
- Cost figures are read from the routing catalog, with no second cost table introduced

### Capability: Structured vendor result channel

Every CLI adapter switches to its vendor's structured JSON output mode with typed envelopes.
Stdout-regex completion polling is replaced by a coordinator completion ledger, with
`submit_work` / `complete_work` as the single source of dispatch state. Adds
`GET /locks?agent_id=` plus bulk release to fix the cloud lock leak, and extends or explicitly
documents `SdkVendorAdapter` coverage beyond review-only.

This lands before any change that wraps or rewrites dispatch, because it rewrites the same
`CliVendorAdapter` methods. Sequencing it first converts a merge conflict into an ordering.

**Acceptance Outcomes:**
- No dispatch result is obtained by regex over stdout
- Dispatch state is readable from the coordinator ledger alone
- Cloud sessions no longer leak locks

### Capability: Routing extended to location, isolation, and dispatch mode

The merged resolver scores *model* choice on cost and quality utility. It does not carry
location, isolation, or dispatch mode. This capability adds those dimensions to the existing
resolver and the existing `/routing/*` contract namespace, driven by a task routing profile
(phase and archetype signals, duration, scope, interactivity, secret needs, parallelism, repo
shape, roadmap policy). Rules stay deterministic and unit-testable, versioned in `routing.yaml`,
with every decision recorded as a routing audit event and a static fallback table for when the
coordinator is unreachable.

Extending rather than adding is the point. The original framing introduced a parallel
`POST /route/task`, but `/routing/*` is already claimed by a merged contract, and two resolvers
scoring overlapping decisions is precisely the kind of split-brain this epic exists to remove.

**Acceptance Outcomes:**
- Routing returns location, isolation, and dispatch mode alongside the vendor and model the merged resolver already selects
- Exactly one resolver scores routing decisions, reachable through the existing `/routing/*` namespace
- Rules are deterministic and unit-testable, with no model call in the decision path
- A documented static fallback table produces a decision when the coordinator is down

### Capability: A pinned isolation contract between router and dispatch

The router emits `isolation` and the dispatch layer consumes it, but nothing today defines the
vocabulary, the resolution precedence, or the fallback. This capability pins that seam before
either side is built against it: the enum, the resolution order (router when reachable →
`agents.yaml` via `get_agent_isolation()` → `none`), and per-`(agent_type, dispatch_mode)`
resolution so that `review` and `alternative` can carry different postures under one agent
entry — which `agents.yaml` already implies and currently cannot express.

Small in effort and disproportionate in leverage: it is the interface two larger items on
either side of it must agree on, and the cheapest moment to get it right is before either
is written.

**Acceptance Outcomes:**
- The isolation vocabulary and its precedence ladder are specified in one place and referenced by both producer and consumer
- `(agent_type, dispatch_mode)` resolves to an effective isolation mode, with per-mode overrides expressible in `agents.yaml`
- A coordinator-unreachable path yields a defined decision rather than an error

### Capability: Orchestrator obedience to the router

Call the routing resolver before each `dispatch_fn` and pass the decision into the dispatch
context as a contract. Execute switch decisions with ledger-verified re-dispatch to the alternate
vendor. Add a global iteration cap and a no-progress detector to the roadmap loop, and un-stub the
wall-clock estimator — the cost-delta estimator is already un-stubbed by PR #237.

This is where the routing decision — including its isolation field — actually arrives at the
point of execution. Until it lands, enforcement has nothing to enforce.

**Acceptance Outcomes:**
- No dispatch occurs without a routing decision attached to its context
- Vendor switches are verified against the completion ledger before being treated as done
- The roadmap loop cannot spin indefinitely without progress

### Capability: Execution-environment isolation posture

`skills/shared/environment_profile.py` currently answers a single boolean, `isolation_provided`,
and its heuristic layer has a demonstrated gap: planning this epic inside a cloud harness
returned `isolation_provided=False source=default`, because the container exposes none of
`/.dockerenv`, `KUBERNETES_SERVICE_HOST`, or `CODESPACES`. `worktree.py setup` consequently
attempted a real worktree and failed against the already-checked-out branch.

The boolean is also the wrong shape. A container provides strong filesystem isolation and
entirely open egress; enforcement needs to say "skip the filesystem sandbox here, still apply
the network allowlist." The field widens to separate filesystem and network dimensions, with a
compatibility property so existing boolean callers are unaffected.

**Acceptance Outcomes:**
- Filesystem and network isolation are reported as independent dimensions
- The cloud harness that currently reports `source=default` is detected correctly
- `worktree.py` and `merge_worktrees.py` read the filesystem dimension with no behavior change

### Capability: OS-level isolation enforcement at dispatch

A `skills/shared/sandbox_profile.py` renderer turns a resolved isolation decision plus the
coordinator's network policy and worktree root into a runtime-specific policy document and an
argv wrapper. `CliVendorAdapter` applies the wrapper between `build_command()` and
`subprocess.run()` — one injection site covering every current and future vendor CLI.

The initial runtime target is `srt` (Seatbelt on macOS, bubblewrap plus seccomp on Linux), the
same mechanism behind Claude Code's own `/sandbox`. The renderer sits behind a `render_*` seam
so a container or OpenShell backend is an addition rather than a rewrite — a requirement, not
speculative generality, given that both candidate runtimes are explicitly pre-1.0.

**Acceptance Outcomes:**
- `isolation: sandbox` produces observable filesystem and network restriction on a dispatched vendor CLI
- The coordinator's existing network policy is enforced at the socket without policy being re-authored anywhere
- Missing runtime or unsupported platform degrades to unsandboxed dispatch with a warning and an audit event
- Adding a second runtime backend requires only a new renderer function

## Constraints

- **Enforcement must not re-author policy.** Network policy is authored once, in the
  coordinator. Runtime policy documents are *renderings* of it. A second source of truth for
  allowed domains is a failure of this epic.
- **One resolver, one cost table.** The merged `model_routing` resolver and catalog are extended,
  never paralleled. A second scoring path or a second vendor cost store is a failure of this epic
  on the same grounds as a second policy source.
- **Degradation must be loud, never silent.** `srt` requires macOS or Linux with bubblewrap,
  socat, and ripgrep. Where unavailable, dispatch proceeds unsandboxed with a warning and an
  audit event, following the pattern already established in `vendor_health.py`. Failing closed
  would break every developer on an unsupported platform for a control that its own authors
  describe as a defense against confused agents rather than determined ones.
- **The threat model is bounded and must be stated as such.** `srt`'s documentation is explicit
  that an allowlist containing `github.com` is an exfiltration channel, that domain fronting
  works, and that an exposed Docker socket is a full escape. This repository's workflow requires
  `github.com`. Specs must claim protection against accidental credential reads and unplanned
  egress — not containment of a determined adversary.
- **One execution surface per change-id.** Items re-homed from `repo-improvement` must not be
  tracked as active in two roadmaps simultaneously.
- **Ordering resolves the conflict.** The structured vendor result channel and the dispatch
  wrapper modify the same `CliVendorAdapter` methods and must not run concurrently.
- **Existing callers keep working.** Widening `isolation_provided` to a posture must not break
  `worktree.py` or `merge_worktrees.py`.

## Phases

**Phase 1 — Substrate.** Wiring the merged model-routing core, the structured result channel,
and the environment posture fix. Three independent roots with no dependencies between them;
they can run in parallel. The routing-core wiring is the long pole.

**Phase 2 — Decision.** The vendor availability registry, then the routing extension, then the
pinned isolation contract. Each needs the previous: the registry needs somewhere to read cost
from, the extension needs live vendor facts, and the contract needs the extension's isolation
output to exist before it can be pinned.

**Phase 3 — Delivery.** The orchestrator obeys the router, carrying the decision into dispatch
context.

**Phase 4 — Enforcement.** The dispatch wrapper turns the delivered isolation field into an
operating-system restriction. Depends on both the decision arriving (Phase 3) and the posture
being expressible (Phase 1).

## Out of Scope

- **Sandbox lifecycle management in the coordinator.** No `sandbox_create` / `sandbox_destroy`
  / connection brokering. That is a control plane — a Rust gateway plus k3s in OpenShell's case
  — and rebuilding it is disproportionate to the threat model. If containerized isolation is
  needed later, dispatch should target an existing gateway's API. Related: `docker_manager.py`
  handles ParadeDB and Colima lifecycle and must not grow into an agent sandbox manager.
- **Wrapping Bash inside skill scripts.** Many call sites, much broader blast radius. Deferred
  by explicit scope decision.
- **Declaring the deployment posture artifact.** Symphony's `trust-posture-binding` owns
  declaration of sandbox mode and network allowlist. This epic delivers the enforcement its
  acceptance criterion requires, and consumes whatever that item declares.
- **Enforced spend ceilings.** `add-coordinator-llm-gateway` applies the same
  advisory-to-enforced argument to model spend. Same shape, different resource, separate epic.
- **The cloud lane as a routable target** (`repo-improvement` ri-10) and downstream scheduling
  work, which depend on this epic's items but are not part of it.
