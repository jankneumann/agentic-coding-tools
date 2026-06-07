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

**Why.** The platform's core value is vendor diversity and cross-checking. Rather than treat
multi-vendor operation as a reproducibility *liability* to tolerate, Sentinel treats it as a
*consensus mechanism* — the same way this repository already synthesizes vendor-diverse code
reviews (`parallel-infrastructure`'s `ConsensusSynthesizer`). A verdict corroborated across
calibrated vendors is more stable and more defensible than a single provider's verdict.

The governing rule that makes this sound: **never place raw outputs from different vendors on
one shared scale.** Inconsistency comes from cross-vendor scale-mixing, not from multi-vendor
itself. Each vendor must be internally consistent; only calibrated, then synthesized, results
are combined.

**Mitigations (binding):**
1. **Verdict-provenance** — every verdict records the vendor, model, and rule/corpus version
   that produced it (see `sentinel-security-eval` requirement "Verdict Provenance"). A verdict
   without provenance is invalid.
2. **Within-vendor consistency** — a given verdict and its severity are produced by one vendor
   applying the rubric uniformly, so each vendor's scale is self-consistent. Raw outputs from
   different vendors are never compared or merged on a shared scale before calibration.
3. **Cross-vendor calibration** — before results from different vendors are combined, their
   scales are calibrated to a common reference so that, e.g., one vendor's CVSS band maps to
   another's. Calibration is owned configuration, not per-run model whim.
4. **Principled synthesis** — per-vendor verdicts are integrated via the consensus model
   (`confirmed` / `unconfirmed` / `disagreement`, with per-vendor dispositions recorded),
   reusing the same `ConsensusSynthesizer` substrate as code review. The synthesized consensus
   verdict — not a lone vendor's — is what reaches the Reporter (see `sentinel-security-eval`
   requirement "Multi-Vendor Verdict Consensus and Calibration").
5. **Shared, per-provider backoff** — Principle V's rate-arbiter behavior is preserved
   *per provider*: backoff state is shared across all agents calling the same provider, so
   the multi-vendor fan-out does not rediscover each provider's limit N times.

**Residual risk (accepted).** Stability now rests on calibration quality rather than on a
single provider. Mis-calibration between vendors is the residual risk; it is mitigated by
treating calibration as owned, versioned configuration and by surfacing cross-vendor
`disagreement` (rather than silently averaging it) for human attention.
