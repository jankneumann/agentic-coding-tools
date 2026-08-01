# Add Dispatch Sandbox Enforcement

> Parent roadmap: `dispatch-governance` (item `dg-07`)
> Change ID: `add-dispatch-sandbox-enforcement`
> Effort: M
> Depends on: `dg-03` (isolation posture), `dg-06` (orchestrator obeys router)
> Related: `symphony/trust-posture-binding` (priority 12) — declaration layer

## Why

The coordinator has an `isolation` field that means nothing.

`agent-coordinator/src/agents_config.py:264` declares
`VALID_ISOLATION_MODES = {"worktree", "sandbox", "none"}`. The value is schema-validated,
stored on `AgentEntry`, exposed through `get_agent_isolation()` (`agents_config.py:979`),
and asserted in `tests/test_agents_config_isolation.py:170` — which pins `codex` to
`"sandbox"`. **No production caller reads it.** An agent declared `isolation: sandbox`
today runs exactly like one declared `isolation: none`.

Three adjacent gaps compound it:

**Worktree isolation is concurrency isolation, not security isolation.** The invariant in
`docs/guides/worktree-management.md` is rigorously enforced — one agent, one worktree, one
branch, guarded by `checkout_policy.py require-mutation`. It stops agents corrupting each
other's git state. It does not stop a dispatched agent reading `~/.ssh/id_rsa` or POSTing
the repository to a pastebin, because a worktree is an ordinary directory owned by the
ordinary uid.

**Network policy is advisory.** `network_policies.py` (90 lines) answers `check_domain()`
through `policy_engine.py:361`. An agent must *voluntarily ask permission*. Nothing
enforces the answer at the socket. This is the same defect `add-coordinator-llm-gateway`
names for spend: *"that ceiling is advisory — enforced by post-hoc reconciliation, not at
request time."* Same shape, different resource.

**Sandbox intent is already expressed, in three incompatible dialects, enforced by nobody.**
`agents.yaml:60-66` and `:131-137`:

```yaml
review:      { args: ["--print", "--allowedTools", "Read,Grep,Glob"] }   # claude
review:      { args: ["exec", "-s", "read-only"] }                        # codex
alternative: { args: ["exec", "-s", "workspace-write"] }
```

The file's own header comment says "the dispatch mode controls sandbox permissions." That
is a policy statement per dispatch mode, written three different ways, enforced by whatever
each vendor felt like implementing, verifiable by us in no way at all.

Meanwhile `symphony/trust-posture-binding` commits to a posture artifact declaring
"sandbox mode, network allowlist" bound to `policy_engine.py` so posture is
"**enforceable, not just documented**." There is currently no mechanism that could make
it enforceable. This change is that mechanism.

### Why now, and why at dispatch

Dispatched vendor CLIs are the sharpest edge in the system: `review_dispatcher.py`
spawns `claude`, `codex`, `gemini` and friends with prompts assembled from repository
content, and every one of them inherits the full ambient authority of the developer's
uid — SSH keys, cloud credentials, shell rc files, unrestricted egress. That is code we
did not write, driven by prompts we do not fully review.

It is also, conveniently, a single chokepoint. `CliVendorAdapter.build_command()`
(`review_dispatcher.py:218`) constructs `cmd`; `subprocess.run(cmd, ...)` at `:279` and
`:521` executes it. One injection site covers every vendor.

The pressure is increasing, not static. `TRUST_POSTURE.md` exists precisely to let
operators flip human gates from `block` to `auto`. Every gate flipped removes a human
from the loop. Machine-level containment is what should backfill the removed human, and
right now nothing does.

## What Changes

### New: `skills/shared/sandbox_profile.py`

A pure, side-effect-free renderer. Takes a resolved isolation decision plus the
coordinator's network policy and worktree root; returns a runtime-specific policy
document plus an argv wrapper.

- `resolve_isolation(agent_type, dispatch_mode, ...) -> IsolationDecision` — consults
  the task router when reachable, falls back to `get_agent_isolation()` from
  `agents.yaml`, then to `none`. Mirrors the precedence ladder already established in
  `environment_profile.py`.
- `render_srt_settings(decision, worktree_root, network_policy) -> dict` — emits srt's
  JSON settings shape: `allowWrite` scoped to the worktree root, `denyRead` covering
  credential paths, `network.allowedDomains` from the coordinator's policy.
- `wrap_command(cmd, decision) -> list[str]` — returns `cmd` unchanged when isolation is
  not `sandbox` or the runtime is unavailable; otherwise returns the wrapped argv.

The renderer is deliberately runtime-shaped but not runtime-bound: `render_srt_settings`
is one function beside a `render_*` seam, so an OpenShell YAML or container-args renderer
is an addition rather than a rewrite. Both candidate runtimes are pre-1.0 (srt is a
"research preview"; OpenShell is "alpha — single-player mode"), which makes the seam a
requirement rather than speculative generality.

### Modified: `skills/parallel-infrastructure/scripts/review_dispatcher.py`

`CliVendorAdapter.dispatch()` and `dispatch_async()` call `wrap_command()` between
`build_command()` and `subprocess.run()`. No other logic moves.

### Modified: `skills/shared/environment_profile.py`

`isolation_provided: bool` widens to a two-dimensional posture — filesystem and network
isolation reported separately — because a container gives strong filesystem isolation and
wide-open egress, and this change must be able to say "skip the filesystem sandbox here,
still enforce the network allowlist."

The existing detection ladder also has a live bug: planning this change inside a cloud
harness returned `isolation_provided=False source=default`, because the container exposes
none of `/.dockerenv`, `KUBERNETES_SERVICE_HOST`, or `CODESPACES`. `worktree.py setup`
consequently attempted a real worktree and failed on the already-checked-out branch. The
heuristic layer gains the missing signals.

Existing `bool` callers keep working through a compatibility property; `worktree.py` and
`merge_worktrees.py` read the filesystem dimension.

### Modified: `agent-coordinator/src/agents_config.py`

`get_agent_isolation()` gains a companion that resolves *effective* isolation for an
`(agent_type, dispatch_mode)` pair, so `review` and `alternative` can carry different
postures under one agent entry — which `agents.yaml` already implies and cannot express.

### Modified: `agent-coordinator/src/network_policies.py`

An export path that serializes the active policy into the shape `sandbox_profile.py`
consumes. The policy stays authored in one place; enforcement becomes a rendering of it.

### Degradation

srt requires macOS (Seatbelt) or Linux (bubblewrap + socat + ripgrep). When the runtime
is absent or the platform is unsupported, dispatch **proceeds unsandboxed**, emits a
warning, and writes a coordinator audit event. This follows the degradation pattern
already used in `vendor_health.py`. Fail-closed would break every developer on an
unsupported platform for a control that is, by its authors' own account, a defense
against confused agents rather than determined ones.

## Non-Goals

- **Sandbox lifecycle management in the coordinator.** No `sandbox_create` / `sandbox_destroy`
  / connection brokering. That is OpenShell's entire product (a Rust gateway plus k3s); if
  containerized isolation is needed later, dispatch should target OpenShell's API rather
  than reimplementing a control plane. Related: `docker_manager.py` handles ParadeDB and
  Colima lifecycle and must not grow into an agent sandbox manager — different problem,
  different failure modes.
- **Wrapping Bash inside skill scripts.** Many call sites, much broader blast radius,
  deferred by explicit scope decision.
- **Declaring the posture artifact.** `symphony/trust-posture-binding` owns declaration.
  This change owns enforcement and consumes whatever that item declares.
- **Protection against a determined exfiltrator.** See Trade-offs.

## Approaches Considered

### Approach 1 — OS-level wrapper at the dispatch chokepoint (**Recommended**)

Render coordinator policy into an srt settings document and wrap the vendor argv in
`CliVendorAdapter`.

**Pros**
- One injection site (`review_dispatcher.py:218` → `:279`) covers every current and
  future vendor CLI, including vendors that ship no sandbox of their own.
- Gives the existing advisory `network_policies.py` real teeth at the socket without
  rewriting the policy model or moving where policy is authored.
- Finally gives `isolation: sandbox` — already declared, validated, and tested — a
  meaning, closing a gap the schema has advertised for some time.
- srt is a single npm dependency with no daemon, no control plane, and no ops burden;
  it is what Claude Code's own `/sandbox` uses.
- Vendor-neutral: the same posture applies to `codex`, `gemini`, and any adapter added
  later, rather than depending on each vendor's flags.

**Cons**
- Adds a Node dependency to a Python dispatch path.
- Unsupported on Windows outside WSL2 (srt's Windows support is alpha).
- OS-level sandboxing falls to a kernel bug; containers would be stronger.
- srt is a research preview with an unstable interface.

**Effort**: M

### Approach 2 — Normalize vendor-native sandbox flags only

Define a portable mode vocabulary (`read-only`, `workspace-write`) and map it onto each
vendor's own flags, extending what `agents.yaml` already does.

**Pros**
- No new dependency; works on every platform the vendor CLIs work on.
- Smallest diff by a wide margin; effort S.
- Zero risk of breaking dispatch on unsupported platforms.

**Cons**
- Enforces nothing we control — we are trusting each vendor's implementation, with no way
  to verify it and no recourse when it is weak or absent.
- Vendors without a sandbox mode get no protection at all.
- Does not cover `SdkVendorAdapter`, which makes direct API calls with no CLI to flag.
- Leaves `isolation: sandbox` still meaningless, and leaves `network_policies.py` still
  advisory — neither of the two gaps that motivate this change actually closes.

**Effort**: S

### Approach 3 — Coordinator-managed container sandboxes (OpenShell or bespoke)

Give the coordinator sandbox lifecycle primitives; run dispatched agents inside containers
with policy-enforced egress and injected credential providers.

**Pros**
- Strongest isolation boundary of the three; survives a kernel bug that defeats Seatbelt
  or bubblewrap.
- Credentials never touch the sandbox filesystem (OpenShell's provider model).
- Handles the multi-tenant case this repo may eventually reach.

**Cons**
- Rebuilds, or takes a hard dependency on, an alpha "single-player mode" control plane.
- Per-dispatch container startup latency against a review path that is currently a
  subprocess spawn.
- Substantial ops burden: image builds, registry, gateway lifecycle, k3s.
- Overwhelmingly disproportionate to the threat model — the realistic failure is a
  prompt-injected agent reading credentials, not a container escape.

**Effort**: XL

### Recommendation

**Approach 1.** Approach 2 is cheaper but closes neither motivating gap: `isolation: sandbox`
stays inert and network policy stays advisory, so it buys a vocabulary rather than a
control. Approach 3 buys a stronger boundary than the threat model needs, at the cost of
depending on an alpha control plane and adding container latency to every review dispatch.

Approach 1 sits where the leverage is: one chokepoint, one dependency, enforcement of a
policy model that already exists. It also leaves Approach 3 open — `render_srt_settings`
sits behind a seam, so adopting OpenShell later means adding a renderer, not redoing the
integration.

## Trade-offs

**Accepted: containment of confused agents over containment of determined ones.** srt's own
documentation is explicit that an allowlist containing `github.com` is an exfiltration
channel, that domain fronting works, and that an exposed Docker socket is a full escape.
This repository's workflow *requires* `github.com`. What this change buys is protection
against accidental credential reads and unplanned egress. It is not a containment boundary
against an adversary who knows GitHub is reachable, and the specs must not claim otherwise.

**Accepted: a Node dependency in a Python path** over building OS-sandboxing bindings
ourselves.

**Accepted: fail-open** over a hard guarantee, so unsupported platforms degrade instead of
breaking. The audit event is what makes the degradation visible rather than silent.

## Impact

- **Specs**: `agent-coordinator` (isolation resolution, policy export), `skill-workflow`
  (dispatch wrapping), `worktree` (posture dimensions)
- **Code**: `skills/shared/sandbox_profile.py` (new), `skills/shared/environment_profile.py`,
  `skills/parallel-infrastructure/scripts/review_dispatcher.py`,
  `agent-coordinator/src/agents_config.py`, `agent-coordinator/src/network_policies.py`
- **Config**: `agents.yaml` per-mode isolation
- **Docs**: `docs/guides/worktree-management.md` (posture, not bool)

### Coordination with in-flight changes

- **`implement-the-task-router-vendor-x-location-x-model`** — `POST /route/task` returns
  `isolation` among its outputs. That change is the **producer** of the decision; this one
  is the **consumer**. `resolve_isolation()` calls the router when reachable. Because the
  router change already specifies "a local static fallback table when the coordinator is
  down," this change is interface-bound to the router without being schedule-blocked by it:
  the fallback is `get_agent_isolation()`, which exists today. The contract between them
  must be pinned before either merges.
- **`build-structured-vendor-result-channel`** — rewrites the same `CliVendorAdapter`
  methods this change modifies. Direct merge-conflict risk; the two must not run
  concurrently against `review_dispatcher.py`. Sequencing to be recorded in `design.md`.
- **`add-coordinator-llm-gateway`** — same advisory-to-enforced argument applied to spend.
  This change should follow its established shape rather than invent a parallel one.
- **`symphony/trust-posture-binding`** — declaration layer. This change supplies the
  enforcement its acceptance criterion ("enforceable, not just documented") requires.
