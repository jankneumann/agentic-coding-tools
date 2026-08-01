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

- `integration_blocking`: existing behavior—confirmed actionable findings and unadjudicated disagreements block; provisional findings warn.
- `convergence_blocking`: medium-or-higher findings with source disposition `fix`, `regenerate`, or `escalate` block until a valid `fixed`, `false_positive`, or human-authorized `accepted_risk` adjudication; deferred findings and unadjudicated disagreements block.
- `effective_blocking`: the deduplicated union of the two policies, used by compatibility `blocking_count` and operator summaries.

The summary exposes `confirmed_count`, `provisional_count`, `disagreement_count`, `integration_blocking_count`, `convergence_blocking_count`, and `effective_blocking_count`. Deprecated `unconfirmed_count` aliases `provisional_count`; compatibility `blocking_count` aliases `effective_blocking_count`. At the item boundary, canonical `policy_status=provisional` is accompanied by deprecated `status=unconfirmed`; confirmed and disagreement values are identical in both fields. Counts are over unique consensus groups, so the effective count is a set union rather than the arithmetic sum of the policy counts.

Revision 2 remains additive for code consumers: it retains `reviewers`, flat `quorum_met`/`quorum_requested`/`quorum_received`, and legacy per-finding identifiers, match fields, `agreed_type`, `agreed_criticality`, and `recommended_disposition` as derived compatibility aliases. New policy code consumes the nested quorum, `policy_status`, source findings, adjudication, and explicit blocker counts. Producer validation enforces equality between each legacy alias and its revision-2 source so old and new readers cannot observe different safety states.

Alternative: redefine every gate to share one policy. Rejected because integration currently has an intentional warning-only rule for unconfirmed findings, while autopilot convergence promises stronger iterative review.

### D2 — Adjudication is explicit evidence, not a rewritten disposition

Every consensus item gets an adjudication state:

- `unreviewed` — default synthesized state;
- `fixed` — a fix landed and verification evidence is attached;
- `false_positive` — evidence refutes reachability/impact;
- `accepted_risk` — a human-authorized waiver with rationale;
- `deferred` — tracked elsewhere and still blocking unless policy explicitly permits it.

The original `vendor_dispositions` map is always present, including unmatched findings. The synthesizer never changes an unmatched `fix` to `accept`. Adjudications enter synthesis through an explicit ledger keyed by the stable consensus-group identifier; unknown identifiers and invalid evidence shapes fail validation rather than being ignored. A later synthesis carries an adjudication only when the stable identifier still names the same normalized concern. The rejected `write_allow` recommendation becomes a golden `false_positive` fixture with source-reachability and byte-identity evidence.

Only `fixed`, `false_positive`, and `accepted_risk` are non-blocking, and only after their required evidence/authorization validates. `deferred` is tracking metadata, not a waiver, and remains convergence-blocking. An unadjudicated disagreement escalates; a valid non-blocking adjudication resolves the policy blocker without rewriting the original disagreement or vendor dispositions.

Alternative: use `recommended_disposition=accept` as adjudication. Rejected because it destroys provenance and cannot distinguish refutation from risk acceptance.

### D3 — Matching is deterministic, structured-first, and non-authoritative

The matcher creates candidate edges using normalized file paths, overlapping/nearby line ranges, normalized type families, package/requirement tokens, and description tokens with a small owned synonym map. It scores all cross-vendor edges, sorts them by stable keys, and builds deterministic connected groups without a primary-vendor greedy pass. Each group identifier is derived from a versioned hash of the sorted normalized concern fingerprints, not an input index. Match provenance records the method, algorithm version, and contributing evidence.

Exact location can cross type-family boundaries; taxonomy differences lower confidence but are not an absolute veto. Description-only matching still requires a conservative threshold. Any finding that remains unmatched stays independently actionable, so recall errors cannot create false convergence.

Alternative: embedding or LLM clustering. Rejected for the authoritative path because results would be nondeterministic and introduce a new dependency. Such a judge can later add advisory group suggestions.

### D4 — Invalid output uses a bounded attempt state machine

All CLI, SDK, and async-poll completions normalize into an attempt record. The state machine is:

```text
invoke → parse/validate
  ├─ valid → success
  └─ invalid_output → one corrective redispatch
       ├─ valid → success
       └─ invalid_output → each configured model fallback once
            ├─ valid → success
            └─ exhausted → at most one not-yet-dispatched replacement vendor
                 ├─ valid → success
                 └─ exhausted/unavailable → explicit logical-request failure
```

Capacity errors continue directly through configured model fallbacks. Auth errors remain terminal and actionable for that vendor. Transient process errors retain their existing bounded retry behavior. The invalid-output budget for one vendor is exactly the initial attempt, one corrective attempt on the initial model, and one attempt per configured fallback model. The orchestrator may then select at most one replacement from available vendors that were not already dispatched, using stable configured order; the replacement gets the same bounded vendor-local chain. A corrective redispatch is never recursive, and a logical result contributes at most one quorum unit.

The public per-vendor timeout is one monotonic deadline for the complete primary/corrective/fallback chain, not a fresh timeout for each model subprocess. Every adapter call receives only the remaining budget; the outer dispatcher enforces the same deadline, persists a terminal timeout result, and continues to the next scheduled vendor. Attempt/checkpoint artifacts are persisted as each vendor reaches a terminal state rather than only after the full sequential loop returns. A model fallback can therefore never multiply the documented vendor bound or prevent later vendors from being observed.

The frozen schema enforces the structural bounds it can express: exactly one initial attempt, at most one corrective and one replacement-vendor attempt, exactly one terminal attempt, and no successful non-terminal attempt. The shared `validate_review_attempt_chain()` application validator additionally enforces unique monotonically increasing indexes, fallback membership/deduplication, remaining-deadline checks, legal vendor transitions, terminal-vendor equality, and no attempt after success. Every producer and consumer calls this validator before persistence or quorum evaluation.

Vendor allocation is also bounded at the review-round level. A vendor may own at most one logical review slot in a round. When a not-yet-dispatched primary is consumed as another slot's replacement, the scheduler transfers and cancels that vendor's original slot before dispatch, records the transfer in the round manifest, and never dispatches the vendor again for that round. `quorum_requested` is the number of remaining logical slots after deterministic transfers; `quorum_received` counts at most one eligible result per distinct vendor and per logical slot. This prevents one replacement result from impersonating independent vendor agreement.

Alternative: run the same parser again. Rejected because identical input cannot produce a different result and the shipped checkpoint design intentionally provides durability, not automatic recovery.

### D5 — Diagnostics are bounded and redacted

Each attempt records a logical request identifier, attempt index, terminal flag, `error_class`, `error_detail`, bounded stdout/stderr excerpts, parser stage, elapsed time, requested archetype/tier, resolved model, requested/applied thinking, translation status, and fallback reason. Excerpts use one shared truncation/redaction helper before entering artifacts, memory, manifests, logs, or handoffs. Raw unredacted output is never persisted by this recovery path; any `artifact_ref` names a bounded sanitized artifact.

Alternative: store raw output verbatim in the manifest. Rejected because vendor output may contain secrets, prompts, or very large payloads.

### D6 — Reviewer routing consumes the existing source of truth

`ReviewOrchestrator.dispatch_and_wait()` accepts a logical phase/archetype routing context and applies this precedence: explicit resolved routing context; autopilot review-phase mapping; the default `reviewer` archetype for review-mode calls such as direct CLI and pull-request review; then static vendor configuration only if coordinator and local archetype resolution both fail. Quick-mode calls retain their existing static routing unless a caller explicitly supplies routing context. Provider resolution passes model plus thinking to CLI, SDK, and async adapters. Manifest entries distinguish requested tier from resolved model and record why fallback occurred.

Thinking translation is configuration-driven at the adapter boundary. Providers without a non-null thinking setting need no flag. When a requested setting is non-null, the adapter must either translate and record it or fail the attempt with a configuration error so replacement/quorum policy can act; it must not silently omit the setting or claim it was applied. Same-provider model fallbacks retain the requested thinking setting unless provider configuration explicitly maps a fallback-specific value.

For Pi this means standard remains `qwen/qwen3-coder`, while a review request resolves to premium `qwen/qwen3-coder-plus`. No provider model IDs are hard-coded in the dispatcher.

Alternative: change Pi's static default to Kimi. Rejected because the current configuration spec intentionally defines Pi standard as Qwen and Kimi is the frontier mapping, not the default reviewer tier.

### D7 — Quorum eligibility is a shared predicate

A logical result counts toward quorum only when dispatch completed, parsing/schema validation succeeded, the terminal attempt is attributable to a non-null vendor/model execution, `terminal_vendor` equals the terminal attempt's vendor, and the shared predicate marks it eligible. A valid zero-finding review counts; malformed, empty, configuration-failed, and non-terminal attempts do not. A replacement success counts once for the logical request, never once per attempt. Across a review round, the same vendor cannot satisfy more than one logical slot even when it was selected as a replacement. Nested and flat quorum fields are derived from the same eligible distinct-vendor set; `received <= requested`, and `met`/`quorum_met` are true exactly when `received >= minimum_required`. The dispatcher, checkpoint writer, synthesizer, and convergence loop import the same predicate from a transport-neutral policy module rather than reimplementing `success` checks. The consensus producer calls `validate_consensus_report()` before persistence so relational invariants that JSON Schema cannot express fail closed.

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
| Adjudication attaches to the wrong regrouped finding | A stale waiver could suppress a live blocker | Versioned stable concern identifiers; reject unknown/stale ledger entries |
| Replacement retries inflate quorum or spend | Duplicate votes and unbounded cost | One replacement maximum, one logical quorum unit, explicit attempt budget |
| Package-level checkpoint edits collide | Parallel worktrees conflict on `tasks.md` | Coordinator owns checkpoint updates after package integration |

## Migration Plan

1. Land additive contract/schema fields plus transport-neutral blocker, adjudication, attempt, diagnostic, routing, and quorum helpers with characterization tests.
2. Switch consensus synthesis to disposition preservation, deterministic grouping, and explicit counts; validate old and new fixtures.
3. Add dispatcher attempt records, invalid-output classification, bounded recovery, deterministic replacement selection, and redacted diagnostics behind optional routing context.
4. Wire reviewer archetype resolution and explicit thinking translation across CLI/SDK/async paths; verify direct review, pull-request review, and quick-task compatibility.
5. Switch convergence and checkpoint quorum accounting to the shared predicates and explicit counts; remove final-round relaxation and return inconclusive/escalated on exhaustion.
6. Update operator recovery documentation and issue #286 evidence. Package agents never edit `tasks.md`; the coordinator records checkpoint completion after package integration.

Rollback reverts consumers in reverse order. Additive artifacts remain readable; older consumers can ignore new fields. If recovery causes vendor-specific regressions, disable corrective redispatch while retaining diagnostics and fail-closed quorum. The human merge gate remains mandatory throughout rollout.
