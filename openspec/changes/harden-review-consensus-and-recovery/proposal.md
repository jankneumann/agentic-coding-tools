# Change: harden-review-consensus-and-recovery

## Why

The review apparatus can currently report `blocking_count=0` while actionable findings remain because lexical-only matching fails to cross-confirm paraphrases and unmatched findings are rewritten to `accept`. Separately, malformed vendor output loses its diagnostics and bypasses retry/model fallback, while review dispatch ignores the reviewer archetype's resolved model tier; together these defects can silently reduce review quorum and produce a false convergence signal.

This change hardens the Trust and Coordination layers so review matching is never a safety gate, actionable findings remain blocking until explicitly adjudicated, malformed output follows a bounded recovery path with durable evidence, and each review attempt records the model routing that was actually used.

## What Changes

- Separate finding deduplication/cross-confirmation from blocking policy. Matching confidence may group equivalent reports, but failure to match MUST NOT suppress an actionable finding.
- Preserve every reviewer's original disposition and add machine-readable adjudication (`fixed`, `false_positive`, `accepted_risk`, or `deferred`) with rationale and evidence.
- Replace the ambiguous summary with explicit confirmed, provisional, disagreement, integration-blocking, convergence-blocking, and effective-blocking counts. Preserve the legacy report envelope and per-finding fields as derived aliases, including `status=unconfirmed` alongside canonical `policy_status=provisional`; preserve `unconfirmed_count` as an alias of `provisional_count`; and make compatibility `blocking_count` equal `effective_blocking_count` so old and new readers cannot observe a false zero.
- Make matching deterministic and order-invariant, using structured evidence (location, affected symbol/requirement, normalized concern, and type aliases) before lexical similarity. Record match method and evidence in the consensus artifact.
- **BREAKING**: Autopilot final-round convergence will no longer relax unadjudicated medium-or-higher actionable findings. Exhausted rounds transition to an inconclusive/escalated outcome instead of converged.
- Classify invalid vendor output distinctly from capacity/auth/transient failures and retain bounded, redacted stdout/stderr diagnostics in attempt records.
- Add a bounded invalid-output recovery chain: parse locally, perform one corrective redispatch for the initial vendor/model, try each configured same-provider model fallback once, then try at most one not-yet-dispatched replacement vendor in deterministic configured order. One monotonic per-vendor deadline bounds the whole model chain, terminal results persist progressively so a slow vendor cannot hide later state, and no failed attempt can count toward quorum.
- Apply the resolved `reviewer` archetype tier and thinking setting to CLI/SDK/async review attempts instead of silently using static vendor defaults. Record requested archetype/tier, resolved provider model, requested/applied thinking, translation status, attempt reason, and fallback reason. A non-null thinking request that an adapter cannot represent is an explicit configuration failure, not a silently downgraded success.
- Add regression fixtures for paraphrased findings, input-order changes, unmatched actionable findings, the rejected `write_allow` false positive, invalid JSON output, fallback exhaustion, and reviewer-tier routing.
- Remain compatible with the planned structured vendor-result channel: this change owns policy, recovery state, and provenance fields, but does not replace CLI output scraping with a new transport.

## Approaches Considered

### Approach 1: Deterministic fail-closed policy with bounded recovery

Introduce a shared blocker/adjudication policy independent of matching, strengthen matching with deterministic structured evidence, and extend the existing dispatcher with a small attempt state machine. Reuse the coordinator-owned archetype/model aliases rather than hard-coding provider model IDs.

**Pros:**

- Fixes the dangerous false-zero condition even when semantic grouping is imperfect.
- Deterministic, auditable, and straightforward to regression-test.
- Preserves existing integration semantics while making autopilot convergence explicitly fail closed.
- Can ship now without depending on the typed-result-channel or adaptive-router proposals.
- Produces provenance fields those later proposals can reuse.

**Cons:**

- Structured heuristics and type aliases will still miss some semantic duplicates.
- Adds explicit policy fields that consumers must adopt.
- Corrective redispatch adds latency when a vendor emits malformed output.

**Effort:** M

### Approach 2: Model-judged semantic consensus

Send all findings to a dedicated judge model that clusters semantic duplicates, resolves taxonomy differences, and decides which findings block. Invalid outputs would be repaired through the same judge.

**Pros:**

- Highest potential recall for differently worded findings.
- Can produce richer explanations for cross-confirmation.
- Requires fewer hand-maintained type aliases.

**Cons:**

- Makes the safety gate probabilistic and harder to reproduce.
- Introduces another vendor/model failure path into consensus itself.
- Higher cost and latency, with circular dependence on the recovery machinery being hardened.
- A judge error could still suppress a live blocker unless a separate fail-closed policy is retained.

**Effort:** L

### Approach 3: Defer to the router and structured-result initiatives

Wait for `build-structured-vendor-result-channel`, `add-adaptive-model-router`, and related orchestrator-routing changes, then implement consensus hardening on top of their final interfaces.

**Pros:**

- Avoids interim adapter changes and potential merge conflicts.
- Could use a typed completion ledger instead of extending scraped-output manifests.

**Cons:**

- Leaves a known false-convergence path live until several larger changes land.
- Those proposals do not independently fix disposition rewriting, blocker semantics, or final-round relaxation.
- Couples a bounded safety fix to broader transport and routing redesigns.

**Effort:** L, with external dependencies

### Recommended

Proceed with **Approach 1**. Its central safety property does not depend on perfect semantic matching: every actionable finding remains visible and blocking until evidence-backed adjudication. It also addresses issue #286 and reviewer model routing through bounded, compatible extensions rather than waiting for unrelated transports to stabilize. Approach 2 may later augment clustering, but it should not own the blocking decision; Approach 3 delays remediation of an observed dangerous failure.

### Selected Approach

The user selected **Approach 1: Deterministic fail-closed policy with bounded recovery** without modifications. The implementation will keep the safety decision independent of semantic grouping, preserve current integration-gate warning behavior through an explicit integration count, and make autopilot convergence fail closed for unadjudicated actionable findings.

## Impact

- **Affected specification capability: `skill-workflow`** — add a delta at `specs/skill-workflow/spec.md` for fail-closed convergence, explicit blocker counts, adjudication, deterministic match provenance, invalid-output recovery, diagnostics, quorum eligibility, and attempt manifests.
- **Affected specification capability: `agent-archetypes`** — add a delta at `specs/agent-archetypes/spec.md` requiring review dispatch to apply and record the resolved reviewer tier/model/thinking values.
- **Trust layer:** `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`, `openspec/schemas/consensus-report.schema.json`, the installed schema asset, and consensus tests/fixtures.
- **Coordination layer:** transport-neutral review-attempt, routing, redaction, and quorum helpers; `skills/parallel-infrastructure/scripts/review_dispatcher.py`; checkpoint integration; dispatcher tests; and compatibility callers in autopilot, merge-pull-requests, and quick-task.
- **Execution layer:** `skills/autopilot/scripts/convergence_loop.py` and its tests for fail-closed final-round and quorum behavior.
- **Coordinator configuration:** existing `agent-coordinator/archetypes.yaml`/`agents_config.py` resolution is consumed as the source of truth; static Pi standard routing remains Qwen, while reviewer/premium resolves to Qwen Plus.
- **Documentation:** recovery/operator guidance and the expanded scope of GitHub issue #286.
- **Governance:** no automatic merge behavior changes; the mandatory human merge gate remains.

## Compatibility and Rollback

Existing callers may continue reading the legacy reviewer envelope, flat quorum fields, per-finding identifiers/match/type/criticality/disposition fields, `status`, and `blocking_count`. All are derived compatibility aliases validated against canonical revision-2 fields; `blocking_count` becomes conservative and equals `effective_blocking_count`, while callers that intentionally preserve warning-only integration behavior MUST migrate to `integration_blocking_count`. New dispatcher arguments remain optional: explicit routing context wins over phase mapping, review-mode calls without a phase default to the `reviewer` archetype, quick-mode calls retain static routing unless explicitly overridden, and static defaults remain available only when coordinator and local archetype resolution both fail. Rollback is a revert of the policy/recovery changes plus the schema delta; retained sanitized attempt artifacts and adjudication data remain forward-compatible evidence even if consumers temporarily ignore the added fields.
