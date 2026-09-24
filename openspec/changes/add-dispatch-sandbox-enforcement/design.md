# Design: Dispatch sandbox enforcement

## Context

dg-02 supplies structured vendor results, dg-03 supplies factual environment posture, dg-05
pins isolation vocabulary and fallback, and dg-06 carries one immutable routing decision. dg-07
is the execution consumer. The current two subprocess call families are the multi-vendor review
dispatcher and autopilot's local Pi provider.

## Decisions

### D1 — Consume one immutable execution context

`DispatchExecutionContext` is a normative enforcement projection of dg-06: decision id, item id,
phase, attempt, dispatch work id, every assignment field, and a canonical digest of the full
persisted routing context, plus enforcement scope and canonical root. The roadmap host constructs
it at the dispatch boundary and passes it through `PhaseDispatchPayload.execution_context`.
Payload v2 removes the legacy top-level isolation authority; a compatibility reader rejects any
legacy isolation value that disagrees with the embedded context. `CliVendorAdapter.dispatch()`,
`dispatch_async()`, and `poll_for_result()` receive the same explicit context. Standalone panel
callers construct one context at their adapter boundary from the exact lane's mode override, then
entry value. A router-sourced context requires router correlation and the assignment digest. No
renderer or backend calls routing or derives a sandbox root from ambient process cwd. Root safety
checks apply only while preparing `sandbox`; `none` and `worktree` preserve legacy cwd behavior.

Context producers are explicit:

| Caller | Assignment fields | Execution root |
| --- | --- | --- |
| Routed roadmap/autopilot phase | Copy the dg-06 enforcement projection and digest into payload v2; it overrides the old phase-level `worktree` default | Host adds the validated managed-worktree root |
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
XDG state/config/cache, and runtime temporary files. dg-07 sandbox lanes are eligible only when
authentication is environment-backed; file-backed login state is denied and remains rollout-
ineligible until dg-08 can broker it safely. Per-lane state variables and credential environment
keys are authored in `agents.yaml`; no renderer hard-codes a vendor. The root must exist, equal `git
rev-parse --show-toplevel`, pass the existing `checkout_policy.py` managed-worktree check, and
must not be `/`, the user's home, or the shared checkout.

The worktree `.git` pointer and linked-worktree common Git metadata are explicitly denied for
writes. A sandboxed worker may edit files but skill prompts do not ask it to commit; the host
orchestrator validates and creates the save-point commit after collecting the worker result. This
avoids granting one agent write access to shared objects and refs.
Symlink escapes are rejected/tested; hardlink aliasing is measured and documented as a residual
same-user risk rather than overstated as contained.

Reads deny the platform user-home region (`/home` on Linux, `/Users` on macOS) and explicitly
re-allow only the canonical worktree, read-only common Git metadata, pinned runtime/tool paths,
and authored credential-free inputs. Named credential paths and sibling checkouts remain denied.
System/runtime reads outside the user-home region are a documented residual. Tests cover `git
status` readability, denied Git mutation, credential/sibling/arbitrary-home reads, and the
read-only common-git carve-out.

### D4 — Exact-agent, default-deny network export

The coordinator exports a snapshot from the exact agent's profile assignment plus global rules.
The snapshot uses a closed SRT-compatible hostname plus separately range-checked port grammar,
explicit scope and priority, schema revision, and canonical SHA-256 digest. Migration 044 adds
`updated_at` and an atomic exact-agent export function; `policy_revision` is
`v1:<maximum-updated-at-UTC>:<row-count>`. `policy_digest` is SHA-256 over UTF-8 canonical JSON
(lexicographically sorted object keys, preserved rule-array order, no insignificant whitespace,
no floats), excluding the digest field itself.
Disabled rules are absent.

SRT's deny-first semantics cannot represent every ordered SQL policy exactly. Rendering therefore
keeps every applicable deny and only authored allows; conflicts become narrower. New writes are
validated against the export grammar. Any legacy malformed applicable rule makes the entire export
unrenderable; rules are never silently omitted. Malformed or unavailable export fails closed before
vendor launch; it never becomes a fail-open reason or a synthetic destination list. An authored,
successfully exported empty allow set remains a valid deny-all policy. A default-allow snapshot is
not renderable by this backend and fails closed. The
export contract is authoritative for sandbox execution; the older advisory SQL matcher is not used
to construct SRT settings. Renderer tests pin SRT 0.0.77 wildcard apex/multi-label behavior and
prove every rendered allow is a subset of the authored effective policy. DNS names, IPv4 literals,
and bracketed IPv6 literals are supported; CIDR belongs only to denied-resolved-address policy and
is not accepted as a destination rule.

Provider endpoints are not hard-coded in the renderer. Current seed policy lacks several vendor
API domains, so dg-07 does not flip existing local lanes to `sandbox`; rollout requires an
authored endpoint inventory and a successful preflight. The controlled acceptance CLI exercises
enforcement independently of production vendor endpoints.

The autopilot `local` provider is rollout-ineligible under `sandbox` until its authored hostname
and port are exportable, its Node client is proven to use SRT's proxy path, and SRT supports the
destination class. Loopback, link-local, private-IP, or mDNS rejection is a fail-closed
policy/capability outcome, never a fail-open reason.

### D5 — Sanitize boundary-shaping environment, do not claim secret brokering

The environment passed to SRT itself removes uppercase/lowercase `HTTP_PROXY`, `HTTPS_PROXY`,
`ALL_PROXY`, and `NO_PROXY`; `NODE_OPTIONS`; `LD_PRELOAD`, `LD_LIBRARY_PATH`,
`DYLD_INSERT_LIBRARIES`, `DYLD_LIBRARY_PATH`; `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`,
`RUBYOPT`, `RUBYLIB`, `PERL5OPT`, `PERL5LIB`, `BASH_ENV`, and `ENV`; Git directory, worktree,
index, object, alternate-object, and config override variables; and `TMPDIR`, `TEMP`, and `TMP`.
SRT may then author the proxy variables its child needs. This prevents an ambient parent proxy
from bypassing address checks. The unsandboxed compatibility path retains the caller's original
environment byte for byte. Runtime discovery records absolute Node, SRT entrypoint, `bwrap`,
`socat`, and `rg` paths and constructs PATH from their parents, fixed root-owned non-writable
system directories, and explicitly configured tool directories inside the canonical worktree;
vendor executables are absolute and inherited descriptors are closed. Environment-backed vendor
credentials remain readable by the vendor process; dg-08 owns request-time substitution and the
downstream sandboxed-harness change owns broader credential brokering.

### D6 — Narrow fail-open with durable evidence

Only unsupported OS, missing/incompatible pinned runtime, or failed pre-launch capability probe
may run the original command. The backend first writes a durable coordinator event; if unavailable,
it appends a caller-generated stable `event_id` and fsyncs canonical JSONL under
`${XDG_STATE_HOME:-~/.local/state}/agentic-coding-tools/sandbox-events/outbox.jsonl`, with a 0700
parent, 0600 file, advisory lock, and directory fsync. The state root must be absolute,
operator-owned, no-follow/no-symlink, and outside every checkout; relative, wrong-owner,
checkout-contained, or symlinked roots fail closed. It is never exposed as sandbox-writable.
Failure of both blocks dispatch. Unsafe root,
unrenderable policy, materialization failure, and all post-SRT-start failures fail closed.

Each later event attempt drains older outbox entries before writing the new one, removing a record
only after the endpoint acknowledges its `event_id`. Compaction holds the lock, writes a
same-directory 0600 temporary file, fsyncs it, atomically replaces the outbox, and fsyncs the
directory. Migration 044 makes `event_id` unique; replay returns the original durable audit row id.
Only connection failures, timeouts, and 5xx responses may use or retain the outbox. Authentication,
authorization, and schema 4xx failures on a live event fail closed. A permanently rejected queued
record moves atomically to a mode-0600 dead-letter file with its response metadata, then drain
continues; it is never silently deleted or allowed to block all later evidence. Audit payloads
contain key names and digests, never prompt/argv bodies, settings bodies, or secret values.

### D7 — Pin and probe SRT

The repository pins `@anthropic-ai/sandbox-runtime` 0.0.77 with lockfile integrity and Node
>=20.11.0. `install.sh` and CI may run `npm ci` in the primary checkout's
`tools/sandbox-runtime`; dispatch performs no installation. Discovery order is an explicit
absolute override, then the primary checkout derived from `git rev-parse --git-common-dir`, then
unavailable. Linked worktrees therefore use one pinned ignored installation rather than looking
for their own `node_modules`; runtime copies never resolve relative to `__file__`. The backend
launches the absolute Node binary and pinned absolute SRT JS entrypoint only after the package
version and exact package-lock resolved URL/integrity entry match installed metadata. Versions before
0.0.16 are forbidden by the official network-escape advisory.

Linux preflight checks `bwrap`, `socat`, `rg`, supported architecture/seccomp conditions,
user-namespace/AppArmor viability, and a no-op sandbox launch. macOS checks the Seatbelt backend,
`sandbox-exec`, violation reporting, and a no-op launch. This host currently lacks `socat` and restricts unprivileged user
namespaces, so real enforcement evidence must run on a capable host; local tests must report the
skip reason, never manufacture a pass.

Sources:

- https://github.com/anthropics/sandbox-runtime/blob/main/README.md
- https://github.com/anthropics/sandbox-runtime/blob/main/package.json
- https://github.com/anthropics/sandbox-runtime/security/advisories/GHSA-9gqj-5w7c-vx47

### D8 — Backend coverage and timeout ownership

Sync submit, async submit, poll, repair retry, read-only snapshot fallback, and autopilot local-provider
launch all use the backend exactly once per process attempt. There is no cancellation subprocess
today; any future configured cancellation command is covered by the same structural guard. The
actual invocation cwd is the policy root. The backend returns a typed
`prelaunch_enforcement_blocked` result. For polling, policy outage or another prelaunch enforcement
failure is a retryable collection condition until the existing poll deadline and then becomes
`remote_state_unknown`; it must not close a still-running remote task as a vendor failure. Snapshot
fallback is forbidden for write-capable modes because cleanup would discard edits. Read-only
snapshot retries construct a new attempt context with the same routing digest and the snapshot
execution root. On timeout the backend starts a new session, sends TERM to the
process group, waits a bounded grace period, sends KILL if required, waits, and then cleans owned
material. It never replays unsandboxed after process start. Cleanup failures emit durable
`cleanup_status=failed` metadata with owned residual paths and block reuse of those paths; cleanup
claims are never manufactured.

### D9 — Ownership relative to sandboxed-harness execution

dg-07 owns the local process seam, local SRT backend, network export, and sandbox execution audit.
`add-sandboxed-harness-execution` consumes them and retains cloud backends, credential brokering,
and trust-gate coupling. Its duplicate local-backend/export task groups are reconciled after dg-07
lands.

### D10 — Applicability is explicit

dg-07 enforces local CLI processes. A routed sandbox assignment is authoritative over
`agents.yaml`; YAML mode/entry fallback is consulted only for standalone calls. SDK, Agent-tool,
and cloud-worker lanes do not traverse this backend and must not emit a fake local-SRT event or
claim dg-07 enforcement; their containment evidence remains a harness/downstream contract.
Sandbox execution events are emitted only when
`requested_isolation=sandbox`; `none` and `worktree` retain their no-coordinator compatibility
path. `enforcement_scope=execution` means the wrapped process performs the work locally;
`submission` covers local submit and poll CLIs for remote work.

## Validation strategy

Tests begin RED at each contract boundary. Unit and integration tests cover decision immutability,
policy normalization, deterministic rendering, root validation, environment stripping, hostile
argv, durable degradation, cleanup, and every subprocess sink. A static AST guard prevents new
vendor process launches outside the backend.

A capability-gated real-runtime test must demonstrate read/write and egress restrictions from a
linked worktree and run at least one configured real vendor executable through the same backend.
A pull-request-triggered GitHub Actions matrix uses `ubuntu-24.04` (with the documented AppArmor
user-namespace setup) and `macos-14`; each supported backend family must pass before its lanes are
rollout-eligible. Jobs upload `sandbox-runtime-evidence.json`; the validator uses `gh run view` and
`gh run download` and verifies conclusion, workflow path, head SHA, platform, artifact digest, and
run id before the checked-in completion record is accepted at
at `openspec/changes/add-dispatch-sandbox-enforcement/evidence/sandbox-runtime-evidence.json` and
includes workflow/run identity. The gate reports `unsupported` with exact prerequisites on an
incapable host; roadmap completion requires both supported backend-family passes.

## Residual risks

- A permitted destination such as GitHub remains an exfiltration channel.
- A child can read credentials intentionally supplied to it.
- Hardlinks and same-user races may exceed path-only containment.
- SRT is pre-1.0 and its config may change; the exact pin and renderer tests bound that risk.
