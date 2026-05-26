# Sentinel Constitution

> Adapted from the Cisco [foundry-security-spec](https://github.com/CiscoDevNet/foundry-security-spec)
> constitution v0.2.0. These principles are **inviolable** — they encode production
> failures and their fixes. Any requirement, design, or implementation in the
> `sentinel-security-eval` capability that contradicts a principle is wrong, except
> where the **Deviations** section below records an explicit, mitigated exception.

## Principles

### I. Evidence Over Assertion
Findings are backed by mechanically verifiable evidence with resolving code citations, never by model confidence alone. A verdict without a satisfied evidence gate is not a finding.

### II. Surface Only What Survives
Only findings that pass triage gates reach operators. Unvetted detections stay in internal storage; the human reviewer's queue is a privilege earned by surviving the gate.

### III. Liveness By Heartbeat, Never By Clock
Agent health is determined by recent heartbeat activity, not wall-clock runtime. Absence of heartbeat — not elapsed time — signals a dead agent and triggers claim release. Wall-clock may rotate sessions but never reclaims work.

### IV. Claims Are Atomic And Mortal
Concurrent agents receive different work units (atomic claiming). A dead agent's claims release automatically within a bounded heartbeat-stale window, with no operator intervention.

### V. The Provider Is The Rate Arbiter
The system adapts to upstream provider backpressure (HTTP 429, quota errors) rather than enforcing static internal rate caps. Backoff is shared across all agents calling a provider. *(See Deviation D-1 regarding multi-provider operation.)*

### VI. Coverage Before Yield
Auto-stop requires **both** coverage-complete **and** yield-below-threshold. Low yield before coverage is complete continues the run; coverage-complete with nonzero yield resets the yield timer.

### VII. Exploited Means Demonstrated
The `exploited` flag requires independent, clean-room reproduction of headline impact on a live testbed. Agent self-verification, argument, or inference never qualifies.

### VIII. Fingerprints Are Stable Under Edit
Finding identity derives from code structure — `(normalized_path, symbol, vulnerability_class)` — not from text position (line number, snippet hash). The same finding survives edits to the surrounding file.

### IX. Sandbox By Infrastructure, Not By Prompt
The runtime environment (container, gateway, firewall, security groups) enforces network and filesystem boundaries. Prompt-level rules are defense-in-depth only, never the boundary itself.

### X. The Operator Outranks Every Agent
Operator configuration is authoritative. Agent consensus, peer messages, and self-suggestions are hints. The operator's hard-rules and config always win.

### XI. Persist Atomically
Artifacts read by multiple components update by complete write-then-atomic-replace, never delete-then-write. No reader ever observes partial state.

## Deviations

This adoption of Sentinel records the following **explicit, mitigated** exceptions to the
constitution. They exist because this repository's platform is multi-vendor by design.
A deviation is only legitimate while its mitigation holds; remove the deviation or
strengthen the mitigation, never let it go silent.

### D-1 — Multi-vendor LLM routing (exception to Principle V and foundry §11.2)

**The invariant being relaxed.** Foundry assumes a single LLM provider so that a finding's
verdict is *reproducible*: re-run the triage, get the same answer. Principle V also frames
"the provider" (singular) as the rate arbiter.

**What Sentinel does instead.** Sentinel reuses this repository's existing **multi-vendor
routing** (Claude, Codex, and other configured vendors). Verdicts may therefore be produced
by different models across runs, which weakens bit-for-bit reproducibility.

**Why.** The platform's core value is vendor diversity and cross-checking; forcing a single
provider for Sentinel alone would fork the dispatch layer and discard that strength.

**Mitigations (binding):**
1. **Verdict-provenance** — every verdict records the vendor, model, and rule/corpus version
   that produced it (see `sentinel-security-eval` requirement "Verdict Provenance"). A verdict
   without provenance is invalid.
2. **Shared, per-provider backoff** — Principle V's rate-arbiter behavior is preserved
   *per provider*: backoff state is shared across all agents calling the same provider, so
   the multi-vendor fan-out does not rediscover each provider's limit N times.
3. **Provenance-aware diffing** — re-run comparisons (fingerprint dedup, SC-005) account for
   provenance: a verdict change between runs is only flagged as a regression when the
   provenance is held constant, isolating genuine target changes from model variance.

**Residual risk (accepted).** Cross-run verdict stability is statistical, not guaranteed.
Reviewers must treat a lone verdict as provider-conditioned; high-stakes verdicts should be
corroborated across providers before publication.
