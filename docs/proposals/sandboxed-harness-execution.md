# Sandboxed Harness Execution: Local and Cloud Sandbox Lanes for Dispatched Agents

## Context

The system is converging on a supervisor pattern: the user talks to one interactive
lead agent (the "first mate"), and that agent dispatches work to other harnesses —
`codex`, `agy`, `grok`, `pi`, headless `claude` — via the skills dispatch layer. The
`cross-vendor-arbitrage-instrument` change already records the economic shape of this
(Claude's subscription terms force it into the lead/interactive role; other vendors
permit programmatic CLI use), and the `symphony` roadmap's dispatcher daemon is the
always-on version of the same pattern.

Increased autonomy is the goal — `TRUST_POSTURE.md` exists so human gates can flip
from `block` to `auto`. Every gate flipped removes a human from the loop, and the
`dispatch-governance` roadmap names the consequence: machine-level containment must
backfill the removed human. Today it does not:

- Dispatched vendor CLIs are spawned by `CliVendorAdapter` in
  `skills/parallel-infrastructure/scripts/review_dispatcher.py` via `subprocess.run()`
  **with no `env=` argument** — every child inherits the developer's full environment,
  `~/.ssh`, cloud credentials, and unrestricted egress.
- `isolation: sandbox` in `agents.yaml` is schema-validated, stored, exposed via
  `get_agent_isolation()`, and read by no production caller.
- `network_policies.py` is advisory: an agent must volunteer the question.

Two sandbox families are on the table:

- **Local OS/container sandboxes** — srt (Seatbelt/bubblewrap, already the recommended
  Approach 1 of `add-dispatch-sandbox-enforcement`), and container control planes like
  OpenShell (explicitly deferred by that proposal as Approach 3).
- **Cloud sandboxes** — vendor-native (`claude --remote`, `codex cloud exec`, already
  plumbed as async dispatch modes in `agents.yaml`) and **generic sandbox providers
  (Daytona, E2B)** that can run *any* harness CLI in an ephemeral remote workspace.
  E2B is already named by the sentinel and verification-gateway specs; Daytona appears
  nowhere in the repo yet. This proposal makes the generic cloud lane a first-class,
  routable execution backend.

This proposal does **not** replace the `dispatch-governance` epic. It extends it: the
router still decides, the orchestrator still carries the decision, dispatch still
enforces. What it adds is (a) a pinned *execution backend* seam under the existing
isolation contract, (b) the design of the cloud-sandbox backend, and (c) the
credential and trust-posture coupling that makes higher autonomy defensible.

## Design principles

1. **Isolation is a routing decision, enforced at dispatch.** The dg-04 router already
   returns `vendor, location, model, isolation, dispatch_mode`. Backend selection is a
   pure function of `(location, isolation)` — no second decision point.
2. **Policy is authored once and rendered per backend.** Network allowlists live in
   `network_policies.py`; credential scopes live in OpenBao; each backend gets a
   `render_*` function in `skills/shared/sandbox_profile.py`, never its own policy file.
3. **Autonomy and containment move together.** A trust-posture gate may only be flipped
   to `auto` for work executing at or above a declared minimum isolation. This coupling
   is policy, checked in code, not prose.
4. **The supervisor keeps ambient authority; workers get least privilege.** The
   interactive lead session runs where the user runs it, with the user's credentials
   and the merge gates. Every *dispatched* worker gets the narrowest workspace,
   credentials, and egress that its task profile needs.
5. **Local and cloud sandboxes solve different problems with one contract.** A local
   sandbox protects the host from the agent. A cloud sandbox removes the host: there is
   no `~/.ssh`, no shell rc, no developer keychain inside it. The strongest simple move
   for worker security is therefore *placement* (cloud), and the local sandbox is the
   fallback when placement rules keep work local.

## The two-axis model

Keep the axes the router already carries, and give each a closed vocabulary pinned by
`pin-isolation-contract` (dg-05):

| Axis | Values | Meaning |
|---|---|---|
| `location` | `local` \| `cloud` | Where the harness process runs relative to the supervisor's host |
| `isolation` | `none` \| `worktree` \| `sandbox` \| `container` | Strength of the boundary around the process |

`worktree` remains what it is today — concurrency isolation, not security. `sandbox`
means OS-level restriction (srt locally; provider-enforced boundary in cloud).
`container` is admitted to `VALID_ISOLATION_MODES` now, while the vocabulary is being
pinned, even though its local backend (OpenShell) is deferred — re-opening a pinned
contract later is the expensive path.

Valid combinations resolve to execution backends:

| location | isolation | Backend | Status |
|---|---|---|---|
| local | none / worktree | `subprocess.run()` as today | exists |
| local | sandbox | srt-wrapped argv (`wrap_command()`) | dg-07, designed |
| local | container | OpenShell gateway | deferred (Phase 3, optional) |
| cloud | sandbox / container | vendor-native (`claude --remote`, `codex cloud`) | exists as CLI flags |
| cloud | sandbox / container | **generic cloud sandbox (Daytona)** | this proposal |

## Execution backend seam

`add-dispatch-sandbox-enforcement` already puts a seam between `build_command()` and
`subprocess.run()`. That seam is sufficient for argv *wrapping* (srt) but not for
backends where the process runs elsewhere. Widen it minimally: an `ExecutionBackend`
protocol modeled on the two working precedents in the repo —
`agent-coordinator/evaluation/backends/registry.py` (`SUPPORTED_BACKENDS`, the
documented pluggable-adapter seam) and symphony's `agent-runner-port`
(`start(workspace, prompt) -> session`, `stream_events()`, `cancel()`).

```python
class ExecutionBackend(Protocol):
    def run(self, spec: DispatchSpec) -> DispatchHandle: ...
    def poll(self, handle: DispatchHandle) -> DispatchStatus: ...
    def cancel(self, handle: DispatchHandle) -> None: ...
```

`DispatchSpec` is the existing `PhaseDispatchPayload` / `build_command()` output plus
the rendered policy: workspace ref (branch + change-id), argv or prompt, env
allowlist, network allowlist, credential grants. `CliVendorAdapter.dispatch()` selects
the backend from the routing decision; the local backend is byte-identical to today's
behavior when `(local, none|worktree)` resolves.

Two hard constraints carried over from the dispatch-governance epic:

- **Sequencing**: `build-structured-vendor-result-channel` (dg-02) rewrites the same
  `CliVendorAdapter` methods. It lands first. The cloud backend *requires* it anyway —
  you cannot regex the stdout of a process on another machine; the coordinator
  completion ledger is the only workable result channel for remote dispatch.
- **No control plane of our own.** The coordinator never gains
  `sandbox_create`/`sandbox_destroy`. Local containers target OpenShell's gateway API
  if ever needed; cloud sandboxes target the provider's API. We write renderers and a
  backend adapter, not a scheduler.

## The cloud sandbox backend (Daytona)

RI-10 ("the cloud lane") already defines the mechanics for Claude-native cloud
sessions: fresh isolated session per task, self-contained prompt (change-id,
work-package, branch, resume-contract entry point), results as pushes/PRs on
`openspec/<change-id>--<agent-id>`, event-driven collection. The Daytona backend
generalizes exactly this to any harness CLI:

**Provisioning.** A prebuilt snapshot image containing the vendor CLIs (`codex`,
`grok`, `pi`, headless `claude`), `uv`, and the skills bootstrap. Per dispatch:
create sandbox from snapshot → shallow-clone the repo at the work branch → write the
dispatch spec → exec the harness CLI headless. Sandbox auto-stop bounds runaway cost.

**Environment detection composes for free.** Inside the sandbox,
`AGENT_EXECUTION_ENV=cloud` is set explicitly (the documented harness-author
integration in `docs/cloud-vs-local-execution.md`), so `worktree.py` short-circuits
and `checkout_policy.py` classifies the checkout as `isolated_harness`. No skill
changes needed — this is the payoff of the existing detection ladder, plus the dg-03
posture widening so the profile can say "filesystem isolated, egress governed".

**Control plane vs data plane.** The coordinator HTTP API (already exposed for cloud
agents with `X-API-Key`) is the control plane: registration with a distinct
`AGENT_ID`, wall-clock heartbeats, the dg-02 completion ledger as the single source of
dispatch state. Git is the data plane: work arrives as a branch, results leave as a
push on the existing branch convention. Nothing new is invented; the transport ladder
in `coordination_bridge.py` already degrades gracefully.

**Egress.** Rendered from `network_policies.py` via a new export path (the same
single-source constraint dg-07 imposes on srt): coordinator host, git remote, the
vendor's API endpoints, nothing else. Where the provider's egress controls are coarser
than a domain allowlist, front the sandbox with an authenticating egress proxy — the
same pattern this repo's own cloud harness uses — and verify exact provider
granularity in the Phase 2 spike before committing to one enforcement point.

**Why a generic provider at all**, when `claude --remote` and `codex cloud` exist:
those cover two vendors on their vendors' terms. The arbitrage design depends on
cheap programmatic vendors (`grok`, `pi`, planned `opencode`) that have no cloud
offering — the generic lane is what makes *placement* (the strongest isolation move)
available to the whole roster, uniformly, under one policy rendering. E2B remains a
candidate for the same slot; the backend adapter plus renderer is the only
Daytona-specific code, and the sentinel/verification specs' E2B usage should share
whichever provider wins to keep one ops surface.

## Credentials: from ambient to brokered

This is the largest single security win, and it is independent of which sandbox runtime
is chosen. Today every spawned CLI inherits everything. Target state, per dispatch:

1. **Explicit env construction.** Every backend—including the local one—builds the
   child environment from an allowlist (`get_mcp_env()` is the existing precedent),
   never by inheritance. This is a small, high-value change that can land with dg-07.
2. **Short-TTL vendor keys from OpenBao.** The AppRole machinery exists
   (`_resolve_api_key_from_openbao()`, `ApiKeyResolver`). Cloud dispatch injects a
   response-wrapped, short-TTL secret for exactly one vendor, not the developer's
   long-lived keys. Local sandboxed dispatch uses the same resolver with `denyRead`
   covering credential paths (already in the srt settings design).
3. **Scoped git credentials.** Cloud sandboxes push with a short-lived, repo-scoped
   token (e.g. a GitHub App installation token minted at dispatch), never the user's
   PAT or SSH key. The user's SSH key simply never leaves the supervisor's host.
4. **Per-agent coordinator keys.** `COORDINATION_API_KEY_IDENTITIES` already supports
   distinct identities; each sandbox gets its own, so revocation and audit are
   per-dispatch.

The stated threat model stays honest, as the dispatch-governance constraints require:
an allowlist containing `github.com` is an exfiltration channel for *repo content* no
matter where the agent runs. What the cloud lane changes is the blast radius — a
prompt-injected worker in a Daytona sandbox can leak the repo and burn one short-TTL
key; it cannot read the developer's home directory, because there isn't one.

## Trust-posture coupling: autonomy priced in isolation

The missing link between the trust-posture work (symphony `trust-posture-binding`, the
approval-gate service) and the sandbox work is a rule that binds them:

> A gate disposition of `auto` or `notify_with_timeout` is valid only if the executing
> dispatch's resolved isolation meets the gate's declared minimum; otherwise the
> effective disposition degrades to `block`, loudly, with an audit event.

Concretely, `TRUST_POSTURE.md` gains a `min_isolation` column per gate, e.g.:

| Gate | `auto` requires |
|---|---|
| review fan-out dispatch | `sandbox` (any location) |
| implementer work-package dispatch | `sandbox` local / any cloud |
| proposal approval, merge | human (never auto-eligible below `container`/cloud) |

The check lives in the approval-gate service, which already consults the posture file;
it reads the routing decision attached to the dispatch context (dg-06 guarantees one
exists). This inverts the current risk direction: today, flipping a gate to `auto`
silently widens what an unsandboxed subprocess can do; under the coupling, flipping a
gate *creates pressure to improve isolation*, and the system refuses to be more
autonomous than it is contained.

## Routing rules

Additions to `routing.yaml` (dg-04's config), deterministic and unit-testable:

- `interactivity: high` → `local` (the supervisor's own session or an srt-wrapped
  subprocess; round-trips to a cloud sandbox are the wrong latency class).
- `secret_needs: local_docker | local_services` → `local, sandbox` (validation stacks
  that only exist on the host stay on the host — RI-10's rule, kept).
- `parallelism: high` or `duration: long` → `cloud` (N sandboxes beat N worktrees on a
  laptop; this is the always-on proposal's dispatch daemon lane too).
- `untrusted_input: true` (third-party PR review, web-research phases — the highest
  prompt-injection surface) → `cloud` with the tightest egress rendering.
- Fallback table when the coordinator is down: `(local, sandbox)` where srt is
  available, `(local, worktree)` otherwise — never silently `(local, none)`.

## Phasing

**Phase 0 — prerequisites (all already-scoped dispatch-governance items).**
dg-02 structured result channel; dg-03 isolation posture; dg-05 pinned contract,
amended to admit `container` and the `location` axis now. Plus the explicit-env
change from the credentials section (small enough to ride with dg-07).

**Phase 1 — local lane.** dg-07 exactly as designed: srt renderer + `wrap_command()`
at the chokepoint, fail-open with audit on unsupported platforms. This makes
`(local, sandbox)` real and gives `isolation: sandbox` its meaning.

**Phase 2 — cloud lane.** A one-week spike first: snapshot build with the CLI roster,
egress-control granularity, sandbox create/exec/teardown latency vs subprocess spawn,
OpenBao short-TTL injection end-to-end. Then the `DaytonaBackend` behind the
`ExecutionBackend` seam, piloted on **review fan-out** (read-only archetypes, lowest
blast radius, highest parallelism benefit), then implementer work-packages per RI-10's
acceptance shape. Trust-posture `min_isolation` coupling lands here — it is what the
cloud lane buys.

**Phase 3 — local containers, only on demonstrated need.** OpenShell (or whatever
matures first) as an additional renderer + backend, if placement rules keep enough
sensitive work local that srt's boundary is insufficient. Explicitly a re-evaluation
point, not a commitment — the seam is the deliverable that keeps it cheap.

## Non-goals

- A coordinator-owned sandbox control plane (unchanged from dispatch-governance).
- Wrapping Bash inside skill scripts (unchanged; separate blast radius).
- Multi-tenant isolation between different users' supervisors.
- Containment of a determined adversary with `github.com` on the allowlist — the specs
  must keep claiming exactly what the mechanism delivers: containment of confused
  agents, bounded blast radius for compromised ones.
