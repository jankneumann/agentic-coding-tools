# Design: harden-review-consensus-and-recovery

## Context

The review path crosses three existing components identified in the architecture inventory: `review_dispatcher.py` produces per-vendor results, `consensus_synthesizer.py` groups them, and `convergence_loop.py` decides whether an autopilot phase may advance. The current interfaces conflate four independent questions:

1. Did a vendor return a parseable, schema-valid result?
2. Do two findings describe the same concern?
3. Has an actionable finding been resolved or explicitly waived?
4. Which policy is asking whether the finding blocks?

That conflation creates the observed false-zero path. A finding that fails lexical matching becomes `unconfirmed`, its source disposition is rewritten to `accept`, `blocking_count` ignores it, and final-round convergence relaxes it. Independently, an exit-zero process whose output cannot be parsed becomes an opaque failure with no `error_class`, no retained diagnostics, and no model fallback. Review dispatch also bypasses the coordinator-owned `reviewer` archetype resolution even though the adapter already accepts a model override.

The architecture analysis groups model resolution as a high-impact dependency and shows the review components in the Trust/Coordination layers. The design therefore adds narrow contracts at their current boundaries rather than introducing a new result transport or a model judge.

## Goals / Non-Goals

### Goals

- Make it impossible for matching failure alone to reduce the effective blocker count.
- Preserve reviewer intent and require evidence-backed adjudication before an actionable finding stops blocking convergence.
- Make grouping deterministic and independent of vendor/input ordering.
- Distinguish integration-gate policy from autopilot-convergence policy.
- Recover from malformed vendor output with a bounded, observable attempt chain.
- Apply and record the coordinator-owned reviewer tier/model/thinking values on every supported dispatch path.
- Keep new fields compatible with the future typed-result channel and adaptive router.

### Non-Goals

- Replacing CLI scraping with a coordinator completion ledger.
- Using an LLM as the authoritative consensus or blocker judge.
- Guaranteeing that every semantic paraphrase is grouped.
- Changing the static Pi standard model; only reviewer/premium routing changes.
- Applying the rejected InterfaceDescriptor `write_allow` suggestion or modifying the trace-requirements feature branch.

## Decisions

### D1 — Blocking policy is independent of match status

Each synthesized finding retains its source dispositions. A shared pure policy function derives:

- `integration_blocking`: existing behavior—confirmed actionable findings and disagreements block; unconfirmed findings warn.
- `convergence_blocking`: medium-or-higher findings with source disposition `fix`, `regenerate`, or `escalate` block until adjudicated; disagreements always block.
- `effective_blocking`: the conservative union used by compatibility `blocking_count` and operator summaries.

The summary exposes all three counts plus confirmed/provisional/disagreement counts. Existing consumers of `blocking_count` become safer without having to adopt new fields immediately.

Alternative: redefine every gate to share one policy. Rejected because integration currently has an intentional warning-only rule for unconfirmed findings, while autopilot convergence promises stronger iterative review.

### D2 — Adjudication is explicit evidence, not a rewritten disposition

Every consensus item gets an adjudication state:

- `unreviewed` — default synthesized state;
- `fixed` — a fix landed and verification evidence is attached;
- `false_positive` — evidence refutes reachability/impact;
- `accepted_risk` — a human-authorized waiver with rationale;
- `deferred` — tracked elsewhere and still blocking unless policy explicitly permits it.

The original `vendor_dispositions` map is always present, including unmatched findings. The synthesizer never changes an unmatched `fix` to `accept`. The rejected `write_allow` recommendation becomes a golden `false_positive` fixture with source-reachability and byte-identity evidence.

Alternative: use `recommended_disposition=accept` as adjudication. Rejected because it destroys provenance and cannot distinguish refutation from risk acceptance.

### D3 — Matching is deterministic, structured-first, and non-authoritative

The matcher creates candidate edges using normalized file paths, overlapping/nearby line ranges, normalized type families, package/requirement tokens, and description tokens with a small owned synonym map. It scores all cross-vendor edges, sorts them by stable keys, and builds deterministic connected groups without a primary-vendor greedy pass. Match provenance records the method and contributing evidence.

Exact location can cross type-family boundaries; taxonomy differences lower confidence but are not an absolute veto. Description-only matching still requires a conservative threshold. Any finding that remains unmatched stays independently actionable, so recall errors cannot create false convergence.

Alternative: embedding or LLM clustering. Rejected for the authoritative path because results would be nondeterministic and introduce a new dependency. Such a judge can later add advisory group suggestions.

### D4 — Invalid output uses a bounded attempt state machine

All CLI, SDK, and async-poll completions normalize into an attempt record. The state machine is:

```text
invoke → parse/validate
  ├─ valid → success
  └─ invalid_output → one corrective redispatch
       ├─ valid → success
       └─ invalid_output → configured model fallback(s)
            ├─ valid → success
            └─ exhausted → vendor failure; orchestrator may select replacement vendor
```

Capacity errors continue directly through configured model fallbacks. Auth errors remain terminal and actionable. Transient process errors retain their existing retry behavior. Retry budgets are bounded per logical review request; a corrective redispatch is never recursive.

Alternative: run the same parser again. Rejected because identical input cannot produce a different result and the shipped checkpoint design intentionally provides durability, not automatic recovery.

### D5 — Diagnostics are bounded and redacted

Each attempt records `error_class`, `error_detail`, bounded stdout/stderr excerpts, parser stage, elapsed time, requested archetype/tier, resolved model/thinking, and fallback reason. Excerpts use one shared truncation/redaction helper before entering memory, manifests, or logs. Full raw output may be written only to the existing review artifact directory with restrictive local semantics; manifests reference it rather than embedding unbounded content.

Alternative: store raw output verbatim in the manifest. Rejected because vendor output may contain secrets, prompts, or very large payloads.

### D6 — Reviewer routing consumes the existing source of truth

`ReviewOrchestrator.dispatch_and_wait()` accepts a logical phase/archetype routing context, resolves `reviewer`/`premium` through the existing coordinator/config path, and passes provider-specific model plus thinking to CLI, SDK, and async adapters. Static `agents.yaml` model values are fallback defaults only when archetype resolution genuinely fails. Manifest entries distinguish requested tier from resolved model and record why fallback occurred.

For Pi this means standard remains `qwen/qwen3-coder`, while a review request resolves to premium `qwen/qwen3-coder-plus`. No provider model IDs are hard-coded in the dispatcher.

Alternative: change Pi's static default to Kimi. Rejected because the current configuration spec intentionally defines Pi standard as Qwen and Kimi is the frontier mapping, not the default reviewer tier.

### D7 — Quorum eligibility is a shared predicate

A result counts toward quorum only when dispatch completed, parsing/schema validation succeeded, and the result is attributable to a vendor/model attempt. A valid zero-finding review counts; malformed or empty output does not. The dispatcher, checkpoint manifest, synthesizer, and convergence loop call the same predicate rather than reimplementing `success` checks.

Alternative: count non-empty findings. Rejected because a valid reviewer may correctly report zero findings.

## Cross-Layer Sequences

### Successful review

```text
Autopilot        Coordinator config       Dispatcher          Synthesizer       Convergence
   | resolve reviewer/premium |                |                    |                  |
   |-------------------------->|                |                    |                  |
   |<-- provider model/thinking|                |                    |                  |
   | dispatch routing context ---------------->|                    |                  |
   |                                           | parse + validate   |                  |
   |                                           | attempt record ---->|                  |
   |                                           |                    | group + policy   |
   |                                           |                    | report ---------->|
   |                                           |                    |                  | gate on convergence count
```

### Invalid-output recovery

```text
Dispatcher          Vendor/model A         Vendor/model fallback       Manifest/quorum
    | invoke              |                           |                        |
    |-------------------->|                           |                        |
    |<-- malformed output |                           |                        |
    | corrective prompt ->|                           |                        |
    |<-- malformed output |                           |                        |
    |------------------------- fallback invoke ------>|                        |
    |<------------------------ valid findings --------|                        |
    | attempt chain + final provenance -------------------------------------->|
    | valid final result counts once; failed attempts never count             |
```

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|---|---|---|
| Conservative blockers increase escalations | More human attention at max rounds | Explicit adjudication and trend evidence make the escalation actionable |
| Matching changes alter grouping | Review artifacts differ from historical output | Order-invariance tests and the archived false-zero round as a golden fixture |
| Retry chain increases latency/cost | Slow malformed-output rounds | One corrective retry, existing configured fallback bounds, per-attempt timing |
| Diagnostics expose sensitive text | Security/privacy regression | Central redaction, strict truncation, artifact references instead of raw manifest payloads |
| Router proposals change APIs | Merge conflicts or duplicate resolution | Optional compatibility parameters and config-derived adapters; no hard-coded model table |
| Schema additions break strict consumers | Validation failures | Additive fields first, schema version bump, compatibility `blocking_count`, consumer tests |

## Migration Plan

1. Land additive contract/schema fields and shared policy/quorum helpers with characterization tests.
2. Switch consensus synthesis to disposition preservation, deterministic grouping, and explicit counts; validate old and new fixtures.
3. Add dispatcher attempt records, invalid-output classification, bounded recovery, and redacted diagnostics behind optional routing context.
4. Wire reviewer archetype resolution across CLI/SDK/async paths and record provenance.
5. Switch convergence to `convergence_blocking_count`; remove final-round relaxation and return inconclusive/escalated on exhaustion.
6. Update operator recovery documentation and issue #286 evidence.

Rollback reverts consumers in reverse order. Additive artifacts remain readable; older consumers can ignore new fields. If recovery causes vendor-specific regressions, disable corrective redispatch while retaining diagnostics and fail-closed quorum. The human merge gate remains mandatory throughout rollout.
