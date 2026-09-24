# Design: Dispatch sandbox enforcement

## Context

dg-02 supplies structured vendor results, dg-03 supplies factual environment posture, dg-05
pins isolation vocabulary and fallback, and dg-06 carries one immutable routing decision. dg-07
is the execution consumer. The current two subprocess call families are the multi-vendor review
dispatcher and autopilot's local Pi provider.

## Decisions

### D1 — Consume one immutable execution context

`DispatchExecutionContext` is a normative enforcement projection of dg-06: decision id, item id,
phase, attempt, dispatch work id, every assignment field (including nullable normalized
`base_url`), and a canonical digest of the full persisted routing context, plus authored
`enforcement_scope`, authored `write_capable`, and canonical root. The roadmap host constructs
it at the dispatch boundary and passes it through `PhaseDispatchPayload.execution_context`.
Payload v2 removes the legacy top-level isolation authority; a compatibility reader rejects any
legacy isolation value that disagrees with the embedded context. `CliVendorAdapter.dispatch()`,
`dispatch_async()`, and `poll_for_result()` receive the same explicit context. Standalone panel
callers construct one context at their adapter boundary from the exact lane's mode override, then
entry value. A router-sourced context requires router correlation and the assignment digest. No
renderer or backend calls routing or derives a sandbox root from ambient process cwd. Root safety
checks apply only while preparing `sandbox`; `none` and `worktree` preserve legacy cwd behavior.

The digest source document is exactly the validated dg-06 `RoutingDispatchContext` contract:
`schema_version`, `decision_id`, `item_id`, `phase`, `attempt`, `dispatch_work_id`, the complete
assignment object (including extension fields and normalized `base_url`), and optional provenance.
Mutable lifecycle fields such as status and `prepared_at` are excluded. It is SHA-256 over UTF-8
canonical JSON with lexicographically sorted object keys, compact separators, and no floats.
Payload v2 carries that validated lossless routing-context object alongside the flattened
enforcement projection. The host computes the digest immediately after dg-06 validation; the
backend canonicalizes the carried object, recomputes the digest, and verifies every duplicated
flattened field against it before launch. Any float in the digest source is a typed host-side
validation error. Payload-v2 `provider`, `model`, `agent_id`, and isolation duplicates are removed
where compatible or must exactly equal the embedded context before any selection or launch. A
router-sourced capacity fallback returns `vendor_limit` for a new router decision and
never silently substitutes a model. A standalone retry may create a new standalone per-attempt
context.

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
root. `agents.yaml` authors `enforcement_scope` and `write_capable` per mode; these properties are
never inferred from assignment location. Autopilot maps each phase explicitly. Every sandboxed
command receives a backend-owned, per-launch state root beneath a secure OS temporary parent
outside both the user-home region and every checkout. That root is explicitly allowed for reads
and writes and is used for HOME,
XDG state/config/cache, and runtime temporary files. dg-07 sandbox lanes are eligible only when
authentication is environment-backed; a sandbox lane with no authored `api_key_env`, or whose
selected key is absent, fails closed as rollout-ineligible until dg-08 can broker it safely.
Per-lane `state_env_keys` and credential environment keys are authored in `agents.yaml`; the
backend points only those state keys into the ephemeral root and no renderer hard-codes a vendor.
The root must exist, equal `git rev-parse --show-toplevel`, and pass a new pure
`is_managed_execution_root(root, common_repo)` predicate independent of environment posture. It
accepts only registered `.git-worktrees/<change>[/<agent>]` roots and the read-only snapshot shape
defined in D8, and
must not be `/`, the user's home, or the shared checkout.

The worktree `.git` pointer and linked-worktree common Git metadata are explicitly denied for
writes. A sandboxed worker may edit files but skill prompts do not ask it to commit; the host
orchestrator validates and creates the save-point commit after collecting the worker result. This
avoids granting one agent write access to shared objects and refs.
Symlink escapes are rejected/tested; hardlink aliasing is measured and documented as a residual
same-user risk rather than overstated as contained.

Reads deny the platform user-home region (`/home` on Linux, `/Users` on macOS) and explicitly
re-allow only the canonical worktree, read-only common Git metadata, pinned runtime/tool paths,
the realpath-resolved vendor executable and deterministic install root, and authored
credential-free inputs. Preflight proves those executable/install roots are readable before start.
Named credential paths and direct sibling-checkout filesystem reads remain denied. Because linked
worktrees share a common object database, committed objects and refs belonging to sibling branches
remain readable through the required read-only common-Git carve-out; this is an explicit residual,
not a claim of branch-content confidentiality.
System/runtime reads outside the user-home region are a documented residual. Tests cover `git
status` readability with backend-authored `GIT_OPTIONAL_LOCKS=0`, denied Git mutation,
credential/sibling/arbitrary-home reads, and the
read-only common-git carve-out.

### D4 — Exact-agent, default-deny network export

The coordinator exports a snapshot from the exact agent's profile assignment plus global rules.
The snapshot uses a closed SRT-compatible hostname plus separately range-checked port grammar,
explicit scope and priority, schema revision, and canonical SHA-256 digest. Migration 044 adds
`updated_at` and an atomic exact-agent export function; `policy_revision` is
`v1:<maximum-updated-at-UTC>:<row-count>`; an empty snapshot uses the stable sentinel
`v1:none:0`. Migration 044 backfills `updated_at` from `created_at` and installs an update trigger.
`policy_digest` is SHA-256 over UTF-8 canonical JSON
(lexicographically sorted object keys, preserved rule-array order, no insignificant whitespace,
no floats), excluding the digest field itself.
Disabled rules are absent.

Only an enabled exact profile assignment is exportable. Unknown, disabled, or unassigned agents
receive a typed 404/409 response and never a global-only snapshot. Export ordering is total and
stable: agent-profile before global, legacy priority ascending (lower number is higher priority),
deny before allow on ties, then
`policy_id` ascending. Migration 044 adds constrained `destination_kind`,
`destination_pattern`, `port`, and `updated_at` columns, parses/backfills legacy rows, and validates
all new writes; any malformed applicable legacy row fails the whole export.

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

The renderer always supplies `deniedResolvedAddresses` for loopback, link-local, cloud metadata,
RFC1918, CGNAT, and IPv6 ULA ranges. An explicit allow whose literal target is private is
unrenderable and fails closed. DNS resolution into any baseline-denied range remains denied.

### D5 — Sanitize boundary-shaping environment, do not claim secret brokering

The child environment is constructed from a positive allowlist rather than copied from the
coordinator. It contains only safe locale/terminal/time variables (`LANG`, `LC_*`, `TERM`, `TZ`),
backend-authored `HOME`, XDG, temporary and `PATH` variables, `GIT_OPTIONAL_LOCKS=0`, and the
selected lane's single authored credential key. Proxy variables are set exclusively by SRT for a
sandboxed child; the backend never injects them. Coordinator/API/database/Cloudflare variables and credentials for
other vendors are absent. As defense in depth, the environment passed to SRT itself removes
uppercase/lowercase `HTTP_PROXY`, `HTTPS_PROXY`,
`ALL_PROXY`, and `NO_PROXY`; `NODE_OPTIONS`; `LD_PRELOAD`, `LD_LIBRARY_PATH`,
`DYLD_INSERT_LIBRARIES`, `DYLD_LIBRARY_PATH`; `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`,
`RUBYOPT`, `RUBYLIB`, `PERL5OPT`, `PERL5LIB`, `BASH_ENV`, and `ENV`; Git directory, worktree,
index, object, alternate-object, and config override variables; and ambient `TMPDIR`, `TEMP`, and
`TMP`. After stripping, the backend replaces only those temporary variables with paths inside the
per-launch state root before SRT starts, so SRT and its descendant see trusted values rather than
the parent's values.
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
The shared `skills/shared/sandbox_audit.py` client/outbox is the frozen audit port consumed by the
process backend; `skills/shared` owns both modules, `wp-policy-audit` implements the port, and
`wp-runtime` depends on it rather than inventing a second persistence path. It uses a small stdlib
HTTP transport compatible with the coordinator API, so it creates no dependency on coordinator
source or the coordination-bridge skill. Coordinator evaluation backends load the shared process
backend through the existing explicit `SKILLS_ROOT` file-loader pattern. Only connection failures,
timeouts, and 5xx responses
may use or retain the outbox. Authentication,
authorization, and schema 4xx failures on a live event fail closed. A permanently rejected queued
record moves atomically to `${state_root}/dead-letter.jsonl` with mode 0600 and response metadata,
using the same lock, temporary-file, fsync, replace, and directory-fsync rules, then drain
continues; it is never silently deleted or allowed to block all later evidence. Audit payloads
contain key names and digests, never prompt/argv bodies, settings bodies, or secret values. The
dispatch-host service principal must have coordinator trust level 3 or greater for cross-agent
export/audit. Rejection is reported distinctly as `authorization_failed`; if the endpoint rejects
the event, no audit row is claimed and the vendor process does not start.

Outbox resource use is bounded: each canonical record is at most 64 KiB; the active outbox is at
most 10,000 records or 64 MiB; one launch drains at most 100 records or five seconds with explicit
connect/read deadlines and a five-second lock wait. Reaching an active-outbox bound fails closed.
Dead letters rotate at 64 MiB, are retained for 30 days, and are capped at 16 rotated files or 1
GiB aggregate, whichever comes first; reaching the aggregate ceiling fails closed until an
operator archives or removes retained evidence. Structured counters/logs report active
record count/bytes, oldest age, drain failures, permanent rejections, and dead-letter count/bytes.

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
snapshot retries are accepted only when the root is a registered Git worktree beneath
`.git-worktrees/.review-snapshots`, belongs to the same common repository, and equals its own Git
toplevel. Snapshot materialization must include the exact tracked/index/worktree and eligible
untracked review inputs; source and snapshot content digests must match or fallback is rejected.
The attempt records that content digest and constructs a new context with the same routing digest
and the snapshot execution root. On timeout the backend starts a new session, sends TERM to the
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

Payload v1 continues legacy `none`/`worktree` behavior but fails closed with `upgrade_required`
when it requests `sandbox`; only payload v2 can carry the embedded immutable execution context.
`source=default` is valid only with `isolation=none`; every non-router source has null router
correlation fields. Sandbox events therefore never carry `context_source=default`.

The production process-surface registry includes review dispatcher submit/poll/repair/snapshot,
autopilot providers, `fact_check.py`, evaluation backends for Antigravity, Claude Code, Codex,
Grok, and Pi,
quick-task, and phase-fixer mutation flows. Configuration validation requires every local CLI
surface to register. The AST guard rejects process APIs in registered production surfaces except
the shared backend, exact named Git/coordinator control-plane helpers, and the exact
`(ocr_adapter.py, run_ocr)` inherited-sandbox descendant described below.
`ocr_adapter.py` is registered as a nested vendor process whose parent Python command is launched
through the backend; tests prove the nested process inherits the applied SRT boundary rather than
granting it a second unsandboxed launch.

`endpoint_digest` is SHA-256 over canonical UTF-8 JSON
`{"base_url": <normalized-string-or-null>, "endpoint_kind": <string>}` using sorted keys and compact
separators. URI userinfo and fragments are rejected during normalization. Null base URLs therefore
produce a stable non-null digest without exposing an endpoint in audit data.

## Validation strategy

Tests begin RED at each contract boundary. Unit and integration tests cover decision immutability,
policy normalization, deterministic rendering, root validation, environment stripping, hostile
argv, durable degradation, cleanup, and every subprocess sink. A static AST guard prevents new
vendor process launches outside the backend.

A capability-gated real-runtime test must demonstrate read/write and egress restrictions from a
linked worktree and run at least one pinned configured vendor executable (`--version`) through the
same backend with a controlled network fixture. Authenticated per-lane real network-client success
is a rollout precondition, not a generic pull-request secret dependency.
A push/pull-request-triggered GitHub Actions matrix uses `ubuntu-24.04` (with the documented AppArmor
user-namespace setup) and `macos-14`; each supported backend family must pass before its lanes are
rollout-eligible. Jobs upload immutable evidence containing executable/version, event id, applied
status, all digests, controlled network outcome, platform, and run/job/head/artifact identity. The
GitHub workflow or check result is authoritative: no run-specific evidence bound to its own final
commit is checked in. The landing step, after push, uses `gh run view`/`gh run download` to verify
conclusion, workflow path, exact head SHA, both platforms, artifact digest, and run id through the
checked-in verifier; the terminal integration command fails unless that verifier succeeds. The gate
reports `unsupported` with exact prerequisites on an incapable host; roadmap completion requires
both supported backend-family passes.

## Residual risks

- A permitted destination such as GitHub remains an exfiltration channel.
- A child can read credentials intentionally supplied to it.
- Hardlinks and same-user races may exceed path-only containment.
- SRT is pre-1.0 and its config may change; the exact pin and renderer tests bound that risk.
