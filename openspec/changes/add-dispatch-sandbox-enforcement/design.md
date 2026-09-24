# Design: Dispatch sandbox enforcement

## Context

dg-02 supplies structured vendor results, dg-03 supplies factual environment posture, dg-05
pins isolation vocabulary and fallback, and dg-06 carries one immutable routing decision. dg-07
is the execution consumer. The current two subprocess call families are the multi-vendor review
dispatcher and autopilot's local Pi provider.

## Decisions

### D1 — Consume one immutable execution context

`DispatchExecutionContext` carries the exact agent id, dispatch mode, isolation, decision id,
provenance, location, enforcement scope, and canonical root. The roadmap host constructs it at
the dispatch boundary from dg-06's validated assignment plus the managed worktree root and passes
it through `PhaseDispatchPayload.execution_context`. `CliVendorAdapter.dispatch()`,
`dispatch_async()`, and `poll_for_result()` receive the same explicit context. Standalone panel
callers construct one context at their adapter boundary from the exact lane's mode override, then
entry value, and the invocation cwd validated through `checkout_policy.py`. A router-sourced
context requires a non-null decision id. No renderer or backend calls routing or derives a root
from ambient process cwd.

Context producers are explicit:

| Caller | Assignment fields | Execution root |
| --- | --- | --- |
| Routed roadmap/autopilot phase | Copy decision id, agent, isolation, location, and mode from the persisted dg-06 decision into payload v2 | Host adds the validated managed-worktree root |
| Standalone vendor panel | Resolve exact-lane mode override, then entry isolation, exactly once | Adapter validates its explicit invocation cwd |
| Autopilot local provider | Consume payload v2 unchanged; no legacy reconstruction | Required in the embedded context |

dg-03 posture is diagnostic evidence only. Its filesystem bit means a per-session workspace, not
credential containment; its network bit does not prove equivalence to the active coordinator
policy. Neither bit satisfies `isolation=sandbox`.

### D2 — One local process backend, not one list wrapper

All vendor CLI execution sites call `skills/shared/local_process_backend.py`. The pure renderer in
`sandbox_profile.py` returns settings and a digest; an impure prepared-command context manager
validates runtime/root/policy and materializes a unique 0600 file. The backend constructs argv and
environment and owns process-group termination and cleanup. `build_command()` remains pure and
vendor-specific.

The argv is `[absolute_srt, "--settings", settings_path, "--", absolute_vendor, ...]` as
documented by SRT. Options that weaken nested, network, Unix-socket, local-binding, or Apple Event
isolation are never project-configurable.

### D3 — Mode-aware filesystem policy

Review and validation-shaped commands receive no project write roots. Alternative, quick,
implementation, and documentation-shaped commands may write only the strict canonical worktree
root. Every sandboxed command receives a backend-owned, per-launch state root used for HOME,
XDG state/config/cache, and runtime temporary files, so vendor CLIs do not need write access to
the operator's home. Read-only credential inputs and required environment credential keys remain
explicit per-vendor configuration; no renderer hard-codes them. The root must exist, equal `git
rev-parse --show-toplevel`, pass the existing `checkout_policy.py` managed-worktree check, and
must not be `/`, the user's home, or the shared checkout.

The worktree `.git` pointer and linked-worktree common Git metadata are explicitly denied for
writes. A sandboxed worker may edit files but skill prompts do not ask it to commit; the host
orchestrator validates and creates the save-point commit after collecting the worker result. This
avoids granting one agent write access to shared objects and refs.
Symlink escapes are rejected/tested; hardlink aliasing is measured and documented as a residual
same-user risk rather than overstated as contained.

### D4 — Exact-agent, default-deny network export

The coordinator exports a snapshot from the exact agent's profile assignment plus global rules.
The snapshot uses a closed SRT-compatible hostname plus separately range-checked port grammar,
explicit scope and priority, schema revision, and canonical SHA-256 digest. Migration 044 adds
`updated_at` and an atomic exact-agent export function; `policy_revision` is the maximum included
row update timestamp plus row count, while the digest is the canonical content change detector.
Disabled rules are absent.

SRT's deny-first semantics cannot represent every ordered SQL policy exactly. Rendering therefore
keeps every applicable deny and only authored allows; conflicts become narrower. New writes are
validated against the export grammar. Any legacy malformed applicable rule makes the entire export
unrenderable and therefore deny-all; rules are never silently omitted. An unavailable snapshot
becomes deny-all. A default-allow snapshot is not renderable by this backend and fails closed. The
export contract is authoritative for sandbox execution; the older advisory SQL matcher is not used
to construct SRT settings.

Provider endpoints are not hard-coded in the renderer. Current seed policy lacks several vendor
API domains, so dg-07 does not flip existing local lanes to `sandbox`; rollout requires an
authored endpoint inventory and a successful preflight. The controlled acceptance CLI exercises
enforcement independently of production vendor endpoints.

The autopilot `local` provider is rollout-ineligible under `sandbox` until its authored hostname
and port are exportable and SRT supports the destination class. Loopback, link-local, private-IP,
or mDNS rejection is a fail-closed policy/capability outcome, never a fail-open reason.

### D5 — Sanitize boundary-shaping environment, do not claim secret brokering

The environment passed to SRT itself and inherited by its child removes inherited proxy variables,
loader/startup injection variables, Git path/config overrides, and untrusted temp settings that
can alter SRT or its child. This prevents an ambient parent proxy from bypassing SRT address
checks. The unsandboxed compatibility path retains the caller's original environment byte for
byte. Runtime discovery records absolute Node, SRT entrypoint, `bwrap`, `socat`, and `rg` paths and
constructs a minimal trusted PATH from their parent directories; vendor executables are absolute
and inherited descriptors are closed. Remaining required vendor
credentials are still readable by the vendor process; dg-08 owns request-time substitution and
the downstream sandboxed-harness change owns broader credential brokering.

### D6 — Narrow fail-open with durable evidence

Only unsupported OS, missing/incompatible pinned runtime, or failed pre-launch capability probe
may run the original command. The backend first writes a durable coordinator event; if unavailable,
it appends and fsyncs JSONL under
`${XDG_STATE_HOME:-~/.local/state}/agentic-coding-tools/sandbox-events/outbox.jsonl`, with a 0700
parent, 0600 file, advisory lock, and directory fsync. The path is outside every checkout and is
never exposed as sandbox-writable. Failure of both blocks dispatch. Unsafe root,
unrenderable policy, materialization failure, and all post-SRT-start failures fail closed.

Each later event attempt drains older outbox entries before writing the new one, removing a record
only after the endpoint acknowledges its `event_id`. Migration 044 makes `event_id` unique; replay
returns the original durable audit row id. Audit payloads
contain key names and digests, never prompt/argv bodies, settings bodies, or secret values.

### D7 — Pin and probe SRT

The repository pins `@anthropic-ai/sandbox-runtime` 0.0.77 with lockfile integrity and Node
>=20.11.0. `install.sh` and CI may run `npm ci` in `tools/sandbox-runtime`; dispatch performs no
installation. Discovery order is an explicit absolute override, then the dispatcher's own Git
top-level `tools/sandbox-runtime` installation, then unavailable. Runtime copies never resolve
relative to `__file__`. The backend launches the absolute Node binary and pinned absolute SRT JS
entrypoint only after package version and lockfile integrity metadata match. Versions before
0.0.16 are forbidden by the official network-escape advisory.

Linux preflight checks `bwrap`, `socat`, `rg`, supported architecture/seccomp conditions,
user-namespace/AppArmor viability, and a no-op sandbox launch. macOS checks the supported native
backend and a no-op launch. This host currently lacks `socat` and restricts unprivileged user
namespaces, so real enforcement evidence must run on a capable host; local tests must report the
skip reason, never manufacture a pass.

Sources:

- https://github.com/anthropics/sandbox-runtime/blob/main/README.md
- https://github.com/anthropics/sandbox-runtime/blob/main/package.json
- https://github.com/anthropics/sandbox-runtime/security/advisories/GHSA-9gqj-5w7c-vx47

### D8 — Backend coverage and timeout ownership

Sync submit, async submit, poll, repair retry, snapshot fallback, and autopilot local-provider
launch all use the backend exactly once per process attempt. There is no cancellation subprocess
today; any future configured cancellation command is covered by the same structural guard. The
actual invocation cwd is the policy root. A pre-launch enforcement denial during polling is a
retryable collection condition until the existing poll deadline; it must not close a still-running
remote task as a vendor failure. On timeout the backend starts a new session, sends TERM to the
process group, waits a bounded grace period, sends KILL if required, waits, and then cleans owned
material. It never replays unsandboxed after process start.

### D9 — Ownership relative to sandboxed-harness execution

dg-07 owns the local process seam, local SRT backend, network export, and sandbox execution audit.
`add-sandboxed-harness-execution` consumes them and retains cloud backends, credential brokering,
and trust-gate coupling. Its duplicate local-backend/export task groups are reconciled after dg-07
lands.

## Validation strategy

Tests begin RED at each contract boundary. Unit and integration tests cover decision immutability,
policy normalization, deterministic rendering, root validation, environment stripping, hostile
argv, durable degradation, cleanup, and every subprocess sink. A static AST guard prevents new
vendor process launches outside the backend.

A capability-gated real-runtime test must demonstrate read/write and egress restrictions on a
supported Ubuntu or macOS runner and run at least one configured real vendor executable through
the same backend. A manually dispatched GitHub Actions workflow uses `macos-14` as the canonical
capable runner and uploads `sandbox-runtime-evidence.json`; the checked-in completion record lives
at `openspec/changes/add-dispatch-sandbox-enforcement/evidence/sandbox-runtime-evidence.json` and
includes workflow/run identity. The gate reports `unsupported` with exact prerequisites on an
incapable host; roadmap completion requires at least one recorded capable-host pass.

## Residual risks

- A permitted destination such as GitHub remains an exfiltration channel.
- A child can read credentials intentionally supplied to it.
- Hardlinks and same-user races may exceed path-only containment.
- SRT is pre-1.0 and its config may change; the exact pin and renderer tests bound that risk.
