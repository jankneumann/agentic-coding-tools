# Implementation review round 1 reconciliation

The configured panel dispatch was degraded: Pi returned findings, while the
Claude and Codex SDK adapters reported that no API key was available. Per the
operator's escalation instruction, three independent Codex Sol reviewers then
performed contract, adversarial-security, and end-to-end integration reviews.

The reviews converged on the following blockers, all fixed in the remediation
that followed this round:

- Production callers selected `sandbox` but did not construct the runtime,
  exact-agent policy, audit port/event, or `SandboxLaunch`; the new portable
  `sandbox_activation` boundary now prepares every registered production
  surface and the central backend fails closed on missing/incomplete context.
- Routed v2 payloads did not bind every flattened enforcement field to the
  digested assignment; validation now rejects unknown fields, floats, invalid
  source/location/root values, digest mismatches, and every duplicated
  projection mismatch.
- Policy snapshots were rendered without closed-schema, exact-agent, rule,
  revision, order, or digest validation; the renderer now validates and
  recomputes the canonical digest before SRT preparation.
- Database/API trust was weaker than the contract: export/event storage is now
  service-role-only, replay conflicts compare actor/target/content, event
  metadata is bounded and typed, and mode enforcement fields are explicit.
- Audit transport followed redirects and dead-letter telemetry could read the
  full retained byte budget; redirects are refused and telemetry streams with
  a bounded buffer.
- The capable-host probes used nondiscriminating closed ports and the verifier
  did not require filesystem outcomes; probes now prove reachable baselines,
  private/DNS-private denial, filesystem confinement, and verifier enforcement.
- The subprocess guard saw only registered files and missed imported aliases;
  it now discovers production sinks and requires explicit classification.

Accepted/nonblocking observations: the five-second audit lock timeout, the
30-minute provider-slot timeout, standard linked-worktree-only runtime
discovery, and existing Cedar/native policy failures are outside this change.
Pi's claim that the controlled fixture was absent was rejected: the fixture and
all network probes were present, although the private-network proof itself was
strengthened as described above.

Remediation validation before round 2:

- runtime/audit/activation/evidence: 69 passed, 3 local capability skips;
- vendor wiring and registered surfaces: 368 passed;
- coordinator/evaluation/live migration focus: 170 passed;
- Ruff, coordinator mypy, mirror/install portability, dependency direction,
  strict OpenSpec, JSON Schema, and diff checks passed;
- full coordinator: 2912 passed, 43 skipped, with only the pre-existing 32
  Cedar/native-equivalence failures remaining;
- the monolithic all-skills pytest invocation retains pre-existing top-level
  module-name collection collisions; all affected dg-07 skill suites pass in
  their supported grouped invocations above.
