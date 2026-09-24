# Add Dispatch Sandbox Enforcement

> Parent roadmap: `dispatch-governance` (`dg-07`)
> Change ID: `add-dispatch-sandbox-enforcement`
> Prerequisites: dg-02, dg-03, dg-05, and dg-06 are landed

## Why

The router now chooses an isolation posture and the orchestrator carries that immutable
decision to execution, but local vendor CLI processes still run with the host user's OS
authority. A `worktree` prevents concurrent agents from sharing one checkout; it does not
prevent reads outside that checkout, writes elsewhere, or arbitrary egress. The coordinator's
network policy is likewise advisory because it is checked only by callers that volunteer a
domain.

dg-07 closes the local execution gap. A shared local-process backend consumes the exact dg-06
decision, renders the coordinator's policy for Anthropic Sandbox Runtime (SRT), and applies the
result to every vendor CLI lifecycle command: synchronous invocation, asynchronous submission,
polling, and the autopilot local-provider harness.

## What Changes

### Immutable execution context

Dispatch receives a versioned execution context containing the routing decision identifier,
exact agent/lane identifier, isolation, dispatch mode, canonical worktree root, and provenance.
The enforcement layer never re-runs routing. Standalone review-panel calls that have no routed
context resolve the already-landed dg-05 fallback once from the exact `agents.yaml` lane.
Routed callers carry the complete context in phase payload v2; every adapter lifecycle method
accepts that context explicitly instead of reconstructing it from cwd.

### Coordinator-owned network-policy export and audit

`NetworkPolicyService` gains an exact-agent export. It returns the active profile-specific and
global rules, a closed default-deny contract, schema revision, and a deterministic digest.
Rendering is conservative: SRT denies take precedence, so conflicting authored rules may become
narrower but never wider. A malformed or unavailable cold-start export renders deny-all; it does
not invent destinations.

A narrow sandbox-execution audit endpoint durably and idempotently records applied and degraded
outcomes. If the coordinator is unavailable, a locked mode-0600 JSONL outbox under the operator's
XDG state directory is fsynced and retried oldest-first on later calls. An unsandboxed fallback is
allowed only after either the coordinator event or the durable outbox record succeeds.

### Pure renderer and lifecycle-owning backend

`skills/shared/sandbox_profile.py` provides:

- pure, deterministic SRT settings rendering;
- mode-aware filesystem policy (`review` has no project write roots; write-capable modes are
  confined to the canonical worktree root; every lane gets an ephemeral vendor-state root);
- a prepared-command lifecycle that owns a unique mode-0600 settings file, sanitized environment,
  runtime identity, policy digest, process group, and cleanup;
- an additive renderer seam for future runtimes.

The reviewed runtime is `@anthropic-ai/sandbox-runtime` 0.0.77 on Node >=20.11.0. The repository
pins the package and integrity and never installs it during dispatch. Setup/CI install the pin;
runtime discovery is explicit absolute override, then the dispatcher's Git-root installation,
then unavailable. The runtime is accepted only when package metadata and integrity match. On Linux
the preflight also verifies `bubblewrap`, `socat`,
`ripgrep`, user-namespace capability, architecture/seccomp support, and a real no-op SRT launch.

Official runtime sources:

- https://github.com/anthropics/sandbox-runtime
- https://github.com/anthropics/sandbox-runtime/blob/main/README.md
- https://github.com/anthropics/sandbox-runtime/blob/main/package.json
- https://github.com/anthropics/sandbox-runtime/security/advisories/GHSA-9gqj-5w7c-vx47

### One local command backend

The shared backend replaces direct vendor subprocess launches in `CliVendorAdapter` sync submit,
async submit and poll paths, and in `autopilot/scripts/provider_dispatch.py`. Poll enforcement
failures are collection failures retried to the existing deadline, not terminal remote-task
failures. A structural guard
prevents future vendor CLI subprocess sinks outside the backend. Non-sandbox decisions preserve
argv, stdin, cwd, timeout, and result behavior.

### Loud, bounded degradation

Fail-open is restricted to facts known before a vendor process starts: unsupported OS, missing or
incompatible pinned runtime, or failed platform capability preflight. Those cases warn, durably
audit `applied=false`, and run the original command. Unsafe roots, malformed policy, settings
materialization errors, and audit/outbox failures fail closed. Once SRT starts, a timeout or
unknown failure never triggers an unsandboxed retry because doing so could execute work twice.

## Scope Boundary

This change protects against accidental or confused local tool behavior after sandbox startup.
It does not claim containment of a malicious vendor executable, a compromised runtime, same-user
races, damage inside an authorized writable root, or exfiltration through an allowed destination
such as GitHub. It strips proxy and code-injection environment variables required to preserve the
SRT boundary, but vendor credentials deliberately supplied to a CLI remain readable by that CLI.
Request-time secret substitution is dg-08; broader credential brokering and cloud execution remain
owned by `add-sandboxed-harness-execution`.

dg-03's factual `posture.filesystem` means a per-session workspace exists; it is not a security
attestation and never satisfies a router request for `sandbox`. Wrapping a local submission CLI
also does not imply that a remote worker is sandboxed.

## Approaches Considered

### Shared SRT local-process backend (selected)

One policy renderer and one lifecycle-owning runner cover every current local CLI sink. It enforces
the already-authored isolation and network decisions without creating a second router.

### Vendor-native flags only

Rejected. Vendor flags differ, omit network enforcement, and leave vendors without a native
sandbox unprotected.

### Coordinator-managed containers

Deferred. A container/control-plane backend belongs to the downstream sandboxed-harness change;
dg-07 supplies the local backend and renderer seam it consumes.

## Impact

- New shared runtime: `skills/shared/sandbox_profile.py` and local process backend helpers.
- Modified execution sinks: review dispatcher and autopilot local-provider dispatch.
- Modified coordinator: exact-agent policy export and durable sandbox audit endpoint.
- Modified config projection: effective per-mode isolation reaches standalone adapters.
- New pinned optional tool dependency: SRT 0.0.77.
- New contracts, tests, operational documentation, and real-runtime probes.
- New capable-host GitHub Actions evidence gate, with a recorded configured-vendor CLI pass.

## Rollback

Removing a mode's `sandbox` decision restores the byte-compatible local process path. Removing or
breaking the runtime does not silently claim enforcement: the preflight records a durable degraded
event before the legacy command may run.
