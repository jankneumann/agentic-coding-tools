## ADDED Requirements

### Requirement: Fail-Closed Consensus Blocking Policy

Consensus synthesis SHALL preserve source dispositions and SHALL derive blocking state independently from cross-vendor match status.

The report SHALL expose `confirmed_count`, `provisional_count`, compatibility `unconfirmed_count`, `disagreement_count`, `integration_blocking_count`, `convergence_blocking_count`, `effective_blocking_count`, and compatibility `blocking_count`. `provisional_count` SHALL equal `unconfirmed_count`; `effective_blocking_count` SHALL count the unique union of integration and convergence blockers; and `blocking_count` SHALL equal `effective_blocking_count`. Canonical item `policy_status=provisional` SHALL serialize with deprecated `status=unconfirmed`; confirmed and disagreement values SHALL be identical in both fields.

Revision-2 reports SHALL preserve the legacy `reviewers`, flat quorum fields, per-finding identifiers/match fields, `agreed_type`, `agreed_criticality`, and `recommended_disposition` as derived compatibility aliases. `validate_consensus_report()` SHALL reject any report whose compatibility aliases disagree with canonical revision-2 fields or whose quorum fields violate their relational invariants.

For medium-or-higher source dispositions `fix`, `regenerate`, or `escalate`, the policy SHALL apply this matrix:

| Adjudication | Integration policy | Convergence policy |
|---|---|---|
| `unreviewed` + confirmed | block | block |
| `unreviewed` + unconfirmed/provisional | warn | block |
| `unreviewed` + disagreement | escalate | escalate |
| valid `fixed`, `false_positive`, or human-authorized `accepted_risk` | do not block | do not block |
| `deferred` or invalid adjudication | preserve normal status behavior | block |

#### Scenario: Unmatched actionable finding remains effective blocker
- **WHEN** a vendor reports an unmatched medium-or-higher finding with disposition `fix`, `regenerate`, or `escalate`
- **THEN** the consensus item SHALL retain that source disposition
- **AND** `summary.convergence_blocking_count` and compatibility `summary.blocking_count` SHALL include the finding until it is adjudicated

#### Scenario: Matching failure cannot produce a false zero
- **WHEN** multiple vendors describe actionable defects with wording or taxonomy that does not meet the match threshold
- **THEN** each unmatched actionable finding SHALL remain represented as provisional
- **AND** `summary.blocking_count` SHALL NOT be zero while any represented medium-or-higher actionable finding is unadjudicated

#### Scenario: Integration policy remains explicit
- **WHEN** a report contains only unconfirmed actionable findings
- **THEN** `summary.integration_blocking_count` SHALL follow the integration gate's warning-only policy
- **AND** `summary.convergence_blocking_count` SHALL follow the fail-closed autopilot policy

#### Scenario: Summary compatibility aliases are exact
- **WHEN** a consensus report is serialized
- **THEN** `summary.unconfirmed_count` SHALL equal `summary.provisional_count`
- **AND** `summary.blocking_count` SHALL equal `summary.effective_blocking_count`
- **AND** `summary.effective_blocking_count` SHALL count each group at most once even when both policies block it

#### Scenario: Legacy and revision-2 consensus readers agree
- **WHEN** a revision-2 report is serialized
- **THEN** legacy `reviewers`, flat quorum, `status`, type, criticality, match, and disposition fields SHALL remain present
- **AND** canonical `policy_status`, nested quorum, source findings, adjudication, and blocker counts SHALL remain present
- **AND** `validate_consensus_report()` SHALL reject any disagreement between the legacy aliases and canonical fields

#### Scenario: False quorum aliases are rejected
- **WHEN** `received` exceeds `requested`, differs from the distinct eligible-vendor count, or `met` differs from `received >= minimum_required`
- **THEN** `validate_consensus_report()` SHALL reject the report
- **AND** nested and deprecated flat quorum fields SHALL not be persisted

### Requirement: Evidence-Backed Finding Adjudication

Each consensus finding SHALL record source dispositions and an adjudication state of `unreviewed`, `fixed`, `false_positive`, `accepted_risk`, or `deferred` with rationale and evidence where applicable.

Adjudications SHALL be read from an atomically persisted ledger keyed by the stable consensus `group_id` and exact sorted concern fingerprints. Unknown identifiers, changed fingerprints, missing evidence, and fabricated authorization SHALL fail closed. Only a trusted human approval resolver may validate `accepted_risk`; review vendors and the synthesizer SHALL NOT originate that authorization.

#### Scenario: Source refutation records false positive
- **WHEN** source reachability and byte-identity evidence refute a review recommendation
- **THEN** the finding SHALL be adjudicated `false_positive` with the evidence references and rationale
- **AND** the original vendor disposition SHALL remain in provenance while the finding no longer blocks

#### Scenario: Unsupported dismissal remains blocking
- **WHEN** an actionable finding is marked `false_positive` without rationale/evidence or `accepted_risk` without a trusted human approval record
- **THEN** adjudication validation SHALL fail
- **AND** the finding SHALL remain effective-blocking

#### Scenario: Deferred finding remains visible
- **WHEN** an actionable finding is adjudicated `deferred`
- **THEN** the report SHALL retain its tracking reference and source dispositions
- **AND** convergence SHALL remain blocked; risk waivers SHALL use `accepted_risk` instead

#### Scenario: Fabricated accepted-risk authorization is rejected
- **WHEN** a vendor, synthesizer, or edited artifact supplies `accepted_risk` with an actor string but no trusted approval record
- **THEN** adjudication validation SHALL reject the authorization
- **AND** the finding SHALL remain effective-blocking

#### Scenario: Stale adjudication is not carried forward
- **WHEN** a ledger entry's group identifier or concern fingerprints no longer match the synthesized concern
- **THEN** the synthesizer SHALL reject the entry as stale
- **AND** the current finding SHALL default to `unreviewed`

### Requirement: Deterministic Match Provenance

Cross-vendor grouping SHALL use deterministic structured evidence before description similarity, SHALL tolerate configured taxonomy aliases, and SHALL record match method, algorithm version, and evidence. Stable group identifiers SHALL be versioned hashes of sorted normalized concern fingerprints and SHALL NOT depend on vendor or input position.

The matcher SHALL reject over-limit input before quadratic work. Defaults SHALL cap each vendor result at 500 findings and 2 MiB of parsed output. Candidate comparison SHALL first bucket by normalized location, symbol/requirement, and type family. Description-only grouping SHALL process stable fingerprints in sorted order and admit a candidate only when it meets threshold against the stable anchor and every existing group member, preventing weak A-B/B-C transitive bridges.

#### Scenario: Paraphrased same-location defect is grouped
- **WHEN** two vendors report the same affected location with different wording or compatible type families
- **THEN** the matcher SHALL group them when structured evidence reaches the configured threshold
- **AND** the report SHALL record the match method, evidence, and score

#### Scenario: Input order does not change grouping
- **WHEN** the same vendor findings are synthesized in different vendor or finding orders
- **THEN** consensus groups, statuses, and summary counts SHALL be identical
- **AND** stable group identifiers SHALL not depend on the primary input order

#### Scenario: Ambiguous description stays separate
- **WHEN** two findings share generic wording but lack compatible structured evidence
- **THEN** the matcher SHALL keep them separate
- **AND** both findings SHALL retain their independent blocker state

#### Scenario: Weak transitive bridge does not merge unrelated findings
- **WHEN** A matches B and B matches C but A does not meet the configured threshold against C
- **THEN** deterministic grouping SHALL NOT place all three findings in one description-only group
- **AND** all output groups and identifiers SHALL remain input-order invariant

#### Scenario: Vendor output exceeds matching limit
- **WHEN** a vendor result exceeds 500 findings or 2 MiB after parsing
- **THEN** the result SHALL be classified `invalid_output`
- **AND** unbounded pairwise matching SHALL NOT run

### Requirement: Invalid Review Output Recovery

CLI, SDK, and async review dispatch SHALL classify malformed, empty, or schema-invalid completion output as `invalid_output` and SHALL execute a bounded recovery chain before final failure.

For each vendor, the invalid-output chain SHALL contain one initial attempt, at most one corrective redispatch on the initial model, and at most one attempt for each deduplicated configured fallback model. All attempts SHALL share one monotonic per-vendor deadline. The public per-vendor timeout SHALL bound the entire primary/corrective/fallback chain rather than reset for each model subprocess. The outer dispatcher SHALL enforce the deadline, persist the terminal vendor result immediately, and continue to the next scheduled vendor. After vendor-local exhaustion, the orchestrator MAY try at most one available vendor that was not already dispatched, selected in stable configured order; that replacement receives the same vendor-local bound. The logical request SHALL contribute at most one quorum unit.

Every attempt chain SHALL pass JSON Schema validation and `validate_review_attempt_chain()` before persistence or quorum evaluation. The schema SHALL enforce exactly one initial attempt, at most one corrective attempt per vendor-local chain, at most one replacement-vendor attempt, one terminal attempt, and no successful non-terminal attempt. The application validator SHALL enforce unique monotonically increasing indexes, configured fallback membership and deduplication, remaining-deadline use, legal vendor transitions, terminal attribution, and no attempts after success.

The round scheduler SHALL assign a vendor to at most one logical review slot. If an undispatched primary vendor is consumed as a replacement, its original slot SHALL be transferred or cancelled before dispatch, the manifest SHALL record the allocation change, and the vendor SHALL NOT be dispatched again in that round. Quorum SHALL count at most one eligible result per distinct vendor.

#### Scenario: Corrective redispatch succeeds
- **WHEN** a review attempt exits successfully but returns malformed findings output
- **THEN** the dispatcher SHALL retain a redacted diagnostic and perform at most one corrective redispatch to the same vendor/model
- **AND** a valid corrective response SHALL become the single quorum-eligible result with both attempts recorded

#### Scenario: Model fallback succeeds after invalid output
- **WHEN** the initial attempt and corrective redispatch both return invalid output
- **THEN** the dispatcher SHALL try configured fallback models in order within the logical request budget
- **AND** the successful fallback model plus fallback reason SHALL be recorded

#### Scenario: Invalid output chain is exhausted
- **WHEN** corrective redispatch and all configured model fallbacks fail validation
- **THEN** the vendor SHALL end with `success=false` and `error_class=invalid_output`
- **AND** the orchestrator MAY dispatch a replacement vendor but SHALL NOT count any failed attempt toward quorum

#### Scenario: Replacement vendor succeeds within global bound
- **WHEN** the requested vendor exhausts invalid-output recovery and an undispatched replacement is available
- **THEN** the orchestrator SHALL choose the first eligible replacement in stable configured order and SHALL start at most one replacement chain
- **AND** a valid replacement result SHALL be the single terminal quorum-eligible result for the logical request

#### Scenario: No replacement vendor remains
- **WHEN** the requested vendor exhausts recovery and every other available vendor was already dispatched or is ineligible
- **THEN** the logical request SHALL end `invalid_output_exhausted`
- **AND** no additional dispatch SHALL occur

#### Scenario: Replacement vendor cannot vote twice
- **GIVEN** vendor A fails and not-yet-dispatched vendor B is selected as A's replacement
- **WHEN** B returns a schema-valid result
- **THEN** B's original logical slot SHALL be transferred or cancelled before dispatch
- **AND** B SHALL contribute at most one to both `quorum_requested` and `quorum_received`
- **AND** the round manifest SHALL record that B was consumed as a replacement

#### Scenario: Capacity failure uses configured model fallback
- **WHEN** any CLI, SDK, or async attempt is classified as a capacity failure
- **THEN** the dispatcher SHALL skip corrective redispatch and try each deduplicated configured model fallback at most once under the same deadline
- **AND** terminal exhaustion SHALL remain classified `capacity_exhausted`

#### Scenario: Authentication failure is terminal for the vendor
- **WHEN** any CLI, SDK, or async attempt is classified as an authentication failure
- **THEN** the dispatcher SHALL NOT retry that vendor or its model fallbacks
- **AND** replacement eligibility and the terminal `auth` outcome SHALL be recorded explicitly

#### Scenario: Transient failure exhausts its bounded retry budget
- **WHEN** any CLI, SDK, or async attempt repeatedly fails with a transient process error
- **THEN** retries SHALL stop at the existing configured transient limit or the monotonic logical-request deadline, whichever occurs first
- **AND** the terminal attempt SHALL remain ineligible with a non-null `transient` or `timeout` error class

#### Scenario: Routing configuration failure is explicit
- **WHEN** any transport cannot translate the requested model or thinking configuration
- **THEN** the attempt SHALL fail before vendor invocation with `error_class=configuration`
- **AND** replacement policy MAY continue without counting the failed logical result toward quorum

#### Scenario: Model fallback does not multiply the vendor timeout
- **GIVEN** a vendor has a primary model and one or more fallbacks
- **WHEN** the primary consumes the per-vendor deadline
- **THEN** no fallback SHALL receive a fresh timeout budget
- **AND** the outer dispatcher SHALL persist a terminal timeout result and continue to the next scheduled vendor

#### Scenario: Structurally invalid attempt chain fails closed
- **WHEN** a chain contains duplicate or non-monotonic indexes, repeated corrective/replacement attempts, an unconfigured or duplicate fallback, an illegal vendor transition, or any attempt after success
- **THEN** schema or `validate_review_attempt_chain()` validation SHALL reject it
- **AND** the result SHALL not be persisted as successful or count toward quorum

### Requirement: Review Attempt Diagnostics

Every logical vendor review SHALL persist bounded attempt provenance without persisting unredacted or unbounded process output.

#### Scenario: Manifest records attempt provenance
- **WHEN** a review request uses corrective or model fallback attempts
- **THEN** its manifest entry SHALL record requested archetype/tier, resolved provider model, thinking, parser stage, elapsed time, error class, attempt reason, and fallback reason for each attempt
- **AND** the final logical result SHALL identify exactly one terminal outcome

#### Scenario: Diagnostic text contains a secret-like value
- **WHEN** stdout or stderr contains credential-like or otherwise sensitive text
- **THEN** the manifest excerpt SHALL be redacted and truncated by the shared diagnostic helper
- **AND** logs, memory, and handoffs SHALL receive only the sanitized form
- **AND** any referenced diagnostic artifact SHALL also be bounded and sanitized; raw unredacted output SHALL NOT be persisted

### Requirement: Shared Quorum Eligibility

The dispatcher, checkpoint writer, synthesizer, and convergence loop SHALL use one quorum-eligibility predicate that requires attributable, parsed, schema-valid completion output. A successful logical result SHALL identify a non-null terminal vendor and model, and `terminal_vendor` SHALL equal the unique terminal successful attempt's vendor.

#### Scenario: Valid zero-finding review counts toward quorum
- **WHEN** a vendor returns a schema-valid findings document with an empty findings array
- **THEN** the logical result SHALL count once toward quorum
- **AND** `quorum_received` SHALL not depend on a non-empty finding count

#### Scenario: Exit-zero malformed output does not count
- **WHEN** a process exits zero but all recovery attempts fail output validation
- **THEN** its logical result SHALL not count toward quorum
- **AND** convergence SHALL fail closed with `quorum_lost` when the minimum eligible reviewer count is not met

#### Scenario: Valid empty review is checkpointed as eligible
- **WHEN** a schema-valid logical result contains `findings=[]`
- **THEN** the checkpoint manifest SHALL retain an eligibility/index record for that vendor even if no findings file is necessary
- **AND** `quorum_received` SHALL include it by calling the shared predicate rather than counting findings or truthy payloads

#### Scenario: Successful output without terminal routing provenance is ineligible
- **WHEN** a nominally successful result has a null terminal model or its `terminal_vendor` differs from the unique terminal successful attempt vendor
- **THEN** contract/application validation SHALL reject the result
- **AND** the shared predicate SHALL not count it toward quorum

## MODIFIED Requirements

### Requirement: Review Convergence Loop

The convergence loop SHALL dispatch reviews through `ReviewOrchestrator.dispatch_and_wait()`, persist every logical result before synthesis, synthesize findings through `ConsensusSynthesizer.synthesize()`, validate the report through `validate_consensus_report()`, and declare convergence only when the shared predicate reports quorum met and `summary.convergence_blocking_count == 0`. It SHALL enforce a maximum iteration cap (default 3 rounds per phase). Exhaustion with a convergence blocker SHALL return an explicit inconclusive/escalated result and SHALL NOT relax provisional findings in the final round.

#### Scenario: Convergence achieved after adjudication
- **GIVEN** quorum is met and all medium-or-higher actionable findings have valid non-blocking adjudications
- **WHEN** the exit condition is checked
- **THEN** `summary.convergence_blocking_count` SHALL be zero
- **AND** convergence SHALL be declared even if historical confirmation status remains visible

#### Scenario: Convergence blocked by insufficient eligible quorum
- **GIVEN** fewer than the configured minimum logical results satisfy the shared eligibility predicate
- **WHEN** the exit condition is checked
- **THEN** convergence SHALL NOT be declared
- **AND** the result SHALL be `quorum_lost`

#### Scenario: Maximum rounds retain provisional blocker
- **GIVEN** the final round contains an unadjudicated medium-or-higher provisional finding
- **WHEN** the iteration cap is reached
- **THEN** the loop SHALL return an inconclusive/escalated result with that finding
- **AND** it SHALL NOT declare convergence

### Requirement: Quorum Reporting

Quorum reporting SHALL derive `quorum_received` exclusively by applying the shared quorum-eligibility predicate to distinct-vendor logical review results. A schema-valid zero-finding result SHALL count; malformed, unattributable, non-terminal, and configuration-failed attempts SHALL not. `quorum_requested` SHALL count logical review slots rather than physical attempts, so corrective, fallback, and replacement attempts never inflate quorum. The report SHALL record `minimum_required`; `quorum_received` SHALL be no greater than `quorum_requested`; and quorum SHALL be met exactly when `quorum_received >= minimum_required`. Nested and flat compatibility quorum fields SHALL be identical.

#### Scenario: Corrective attempts do not inflate quorum
- **GIVEN** two logical vendor requests produce five physical attempts and both end in schema-valid terminal results
- **WHEN** the consensus report is generated
- **THEN** `quorum_requested` SHALL be 2 and `quorum_received` SHALL be 2

#### Scenario: Valid zero-finding result satisfies a quorum slot
- **GIVEN** a logical vendor result is schema-valid, attributable, terminal, and contains zero findings
- **WHEN** quorum is calculated
- **THEN** that result SHALL contribute one to `quorum_received`

### Requirement: Vendor Findings Checkpoint Layout

The canonical checkpoint layout and atomic-write guarantees SHALL remain unchanged, except the manifest vendor index SHALL represent every terminal logical result, including schema-valid results with `findings=[]`. Each index entry SHALL record `quorum_eligible` and MAY set `findings_path=null` for a valid empty review. `quorum_received` SHALL be the count of indexed logical results accepted by the shared predicate, never the count of non-empty findings arrays or physical attempts. Dispatch metadata SHALL retain the complete bounded attempt chain.

#### Scenario: Empty eligible vendor remains enumerable
- **WHEN** an eligible vendor returns a schema-valid empty findings array
- **THEN** `vendors[]` SHALL contain that vendor with `finding_count=0`, `findings_path=null`, and `quorum_eligible=true`
- **AND** replay SHALL reproduce the original quorum count without inventing a finding file

#### Scenario: Malformed completion remains auditable but ineligible
- **WHEN** a logical request exhausts recovery without schema-valid output
- **THEN** its bounded sanitized attempt chain SHALL remain in `dispatches[]`
- **AND** it SHALL not appear as quorum-eligible or increment `quorum_received`

### Requirement: Finding Trend Tracking and Stall Detection

The convergence loop SHALL track effective blocking finding counts per round and escalate if findings are not decreasing over a 3-round sliding window (that is, count at round N >= count at round N-2). Unadjudicated medium-or-higher findings with source disposition `fix`, `regenerate`, or `escalate` SHALL block in every round, including the final round. Unadjudicated findings with `disagreement` status SHALL trigger escalation; a valid non-blocking adjudication SHALL resolve the policy blocker without erasing the historical disagreement.

#### Scenario: Decreasing trend continues
- **WHEN** round 1 has 10 effective blockers, round 2 has 5, and round 3 has 6
- **THEN** trend analysis SHALL not classify the sequence as stalled because round 3 is below round 1
- **AND** remaining round-3 blockers SHALL still prevent convergence

#### Scenario: Flat trend triggers stall
- **WHEN** round 1 has 5 effective blockers, round 2 has 5, and round 3 has 5
- **THEN** the system SHALL escalate because round 3 is not below round 1
- **AND** the escalation SHALL retain the effective blocker details

#### Scenario: Unconfirmed actionable finding in final round
- **WHEN** the final round contains a single-vendor medium-or-higher actionable finding without a non-blocking adjudication
- **THEN** the finding SHALL block convergence
- **AND** exhausted iterations SHALL produce an inconclusive/escalated outcome rather than convergence

#### Scenario: Vendor disagreement
- **WHEN** vendors recommend conflicting dispositions for the same grouped finding and no valid non-blocking adjudication exists
- **THEN** consensus SHALL classify the finding as `disagreement`
- **AND** the system SHALL transition to escalation regardless of round number
