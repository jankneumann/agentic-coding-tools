# Design: add-sandboxed-harness-execution

## Context

The user talks to one interactive lead agent (supervisor); work fans out to other
harnesses (`codex`, `agy`, `grok`, `pi`, headless `claude`) through
`CliVendorAdapter` in `skills/parallel-infrastructure/scripts/review_dispatcher.py`.
Today that fan-out inherits full ambient authority (`subprocess.run()` with no
`env=`), the schema-validated `isolation` field is enforced by nobody, and
`network_policies.py` is advisory. The always-on GX10 host runs the supervisor
sessions, dispatcher daemon, coordinator, OpenBao, and local validation, and is
reachable only over Tailscale; the coordinator is additionally exposed through an
outbound cloudflared named tunnel (`coord.rotkohl.ai`).

The dispatch-governance epic already defines the decision chain (router decides
`vendor × location × model × isolation × dispatch_mode`; orchestrator carries;
dispatch enforces) and the srt-based local sandbox (dg-07). This change layers the
execution-backend seam, credential brokering, and the generic cloud lane on top.
Full narrative: `docs/proposals/sandboxed-harness-execution.md`.

## Goals / Non-Goals

**Goals**

- One `ExecutionBackend` seam selecting purely on the routing decision's
  `(location, isolation)` pair; legacy local dispatch byte-identical.
- Credentials move from ambient inheritance to per-dispatch brokered leaves
  (Phase 2, ahead of the cloud lane that depends on it).
- A generic cloud sandbox backend (Daytona primary candidate, E2B evaluated in the
  same spike) available to every vendor CLI, under a zero-inbound-to-tailnet
  topology.
- Trust-posture autonomy structurally coupled to resolved isolation
  (`min_isolation` per gate).

**Non-Goals**

- A coordinator-owned sandbox control plane (provider APIs / OpenShell gateway own
  lifecycle).
- Re-implementing dg-02/dg-03/dg-05/dg-07 — they are consumed, with one amendment
  (vocabulary widening) to dg-05 before it pins.
- Wrapping Bash inside skill scripts; multi-tenant isolation between users.
- Containment of a determined adversary while `github.com` is on the allowlist —
  claims stay bounded to confused agents and blast-radius reduction.

## Decisions

1. **Backend seam shape.** `ExecutionBackend` protocol (`run`/`poll`/`cancel` over
   a `DispatchSpec`) registered in a `SUPPORTED_BACKENDS`-style registry
   (precedent: `agent-coordinator/evaluation/backends/registry.py`), selected
   inside `CliVendorAdapter` after `build_command()`. The srt path (dg-07) is the
   `(local, sandbox)` backend; symphony's `agent-runner-port` remains the future
   session-lifecycle abstraction if one-shot argv stops sufficing.
2. **Push-model secrets (broker), not pull-model (vault access).** The dispatcher
   resolves secrets against OpenBao locally and injects leaves at workspace
   creation. Decisive fact: response-wrapping — the textbook pull-model
   mitigation — is unusable here because unwrapping itself requires vault
   reachability, which is exactly what the zero-inbound invariant forbids
   granting to workers.
3. **Gateway virtual keys for inference.** `add-coordinator-llm-gateway` (LiteLLM)
   is the data plane; raw vendor keys stop being distributed. Per-CLI base-URL
   support is a spike item; the audited fallback is a capped per-lane vendor key.
4. **Vocabulary widened at pin time.** `container` and the `location` axis enter
   the isolation contract while `pin-isolation-contract` is being written, because
   re-opening a pinned producer/consumer contract later is the expensive path.
5. **Sequencing behind dg-02.** The structured result channel rewrites the same
   `CliVendorAdapter` methods this change touches, and remote backends cannot
   exist without ledger-based state anyway; dg-02 lands first, converting a merge
   conflict into an ordering.
6. **Egress enforcement provider-first.** Sandbox egress is a rendering of the
   exported coordinator policy into provider network controls; an adjacent cloud
   egress proxy only if the spike shows provider granularity insufficient; never
   proxied through the tailnet host (residential bandwidth coupling + turns the
   tailnet-only box into an internet-facing proxy).
7. **Phased flags, loud degradation.** Backend selection and the env allowlist are
   feature-flagged; every degradation (allowlist off, gateway bypass, egress
   coarse, unhardened vault) emits a warning plus a coordinator audit event,
   following the `vendor_health.py` pattern.

## Alternatives Considered

- **Vendor-native only** (proposal Approach 2): rejected — leaves credentials
  ambient, covers only vendors with their own cloud, nothing to couple posture to.
- **Direct sandbox→OpenBao** (proposal Approach 3): rejected — exposes the secret
  store beyond the tailnet and plants a credential-store credential in the
  highest-injection-surface location.
- **Tailnet ephemeral nodes in sandboxes**: documented fallback if the coordinator
  tunnel is ever deemed unacceptable; not default (tailnet key inside sandbox;
  cloud capacity coupled to home bandwidth).
- **Egress proxy on the GX10**: rejected outright (see Decision 6).
- **`docker_manager.py` growing into a sandbox manager**: explicitly forbidden by
  the dg-07 proposal; unchanged here.

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|---|---|---|
| Provider egress controls too coarse for a domain allowlist | Weakened exfiltration bound in cloud lane | Spike gate before Phase 3 build; adjacent egress proxy fallback; posture-gated degradation, audited |
| Env allowlist breaks a consumer relying on inherited vars | Dispatch failures on rollout | Feature flag `DISPATCH_ENV_ALLOWLIST=off` (audited); pilot on review fan-out first |
| CLI lacks base-URL override → raw key in sandbox | Long-lived vendor key exposed to worker | Dedicated per-lane key + spend cap + audit; revocation cheap by construction |
| OpenBao becomes single point of failure for all dispatch | Availability | Hardening verification (persistence/TLS/audit) as precondition; local lane continues on degradation; existing env-var fallback ladder retained for local |
| Leaf credentials are still real credentials for their TTL | Bounded exfiltration window | Short TTLs, per-dispatch identities, one-use where the backend supports it; blast radius bounded to one dispatch scope |
| Sandbox startup latency vs subprocess spawn | Throughput of fan-out phases | Spike measures create/exec/teardown; snapshot prebuild; route latency-sensitive interactive work local via routing rules |
| Cloudflared tunnel outage severs cloud control plane | Cloud dispatches unobservable | Ledger-park rule: no remote dispatch without ledger reachability; local lane unaffected |

## Migration Plan

1. **Phase 0**: dg-02 lands (or is sequenced ahead); dg-03 posture; dg-05 pinned
   with widened vocabulary. No behavior change.
2. **Phase 1**: Backend seam introduced with only the legacy backend registered —
   a pure refactor, verified byte-identical by the existing dispatch tests — then
   the srt backend behind `isolation: sandbox`.
3. **Phase 2**: Env allowlist on (flagged), broker AppRole provisioned, OpenBao
   hardening verified, GitHub App created and key stored, gateway virtual keys for
   capable CLIs. Each independently revertible by flag or by unregistering the
   broker path (falls back to `ApiKeyResolver`'s existing ladder).
4. **Phase 3**: Spike gate → `CloudSandboxBackend` piloted on review fan-out
   (read-only archetypes) → implementer work-packages → `min_isolation` coupling
   enforced in the approval-gate service.
5. **Rollback**: at every phase the `(local, none|worktree)` backend is the
   untouched legacy path; disabling a backend deregisters it and routing falls
   back per the pinned precedence ladder, loudly. The one BREAKING item (env
   allowlist) rolls back via its audited flag.
