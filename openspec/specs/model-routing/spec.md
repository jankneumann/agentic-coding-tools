# model-routing Specification

## Purpose
Wire the already-merged routing computation core to durable catalog storage, coordinator
transports, local/OpenRouter endpoints, watchdog scheduling, and a bounded static-tier fallback.
The preserved full proposal is in `deferred-specs/`; it is not a dg-00 delivery claim.
## Requirements
### Requirement: Model Catalog

The system SHALL maintain a durable catalog keyed by `(vendor, model, endpoint_kind)`, where
`endpoint_kind` is one of `vendor-cli`, `vendor-sdk`, `openrouter`, or `local`. Catalog reads
MUST be served from coordinator storage without calling an external API on the read path, and
rows older than the configured threshold SHALL be reported as stale.

#### Scenario: Catalog row served without external calls

- **WHEN** a routing request loads candidates
- **THEN** candidate rows SHALL be returned from coordinator storage
- **AND** no OpenRouter or vendor API call SHALL occur on the read path

#### Scenario: Catalog row is stale by age

- **WHEN** a stored row's refresh timestamp is older than the configured stale threshold
- **THEN** the read SHALL return that stored row with `stale: true`
- **AND** the read SHALL NOT trigger an external refresh

### Requirement: OpenRouter Catalog Refresher

The system SHALL refresh OpenRouter model pricing and availability on a schedule using a
standing key. A failed refresh MUST leave previously stored rows available to readers.

#### Scenario: Scheduled refresh updates pricing

- **WHEN** OpenRouter reports a changed price
- **THEN** the stored row SHALL receive the new price and refresh timestamp

#### Scenario: Refresh failure preserves rows

- **WHEN** the OpenRouter API is unavailable
- **THEN** existing catalog rows SHALL remain served and become stale by age

### Requirement: Local Endpoint Registration

The system SHALL register local OpenAI-compatible endpoints declared with `endpoint_kind` and
`base_url`, health-probe them, and exclude unavailable rows from resolver candidates.

#### Scenario: Unhealthy local endpoint is excluded

- **WHEN** a local endpoint fails its health probe
- **THEN** its catalog row SHALL be marked unavailable
- **AND** the resolver SHALL exclude it until a probe succeeds

### Requirement: Adaptive Selection Resolver Surface

The coordinator SHALL expose the merged resolver through `select_model_for_task`, returning a
selected candidate, ranked alternatives, exclusions, and a durable decision ID.

#### Scenario: Selection is persisted

- **WHEN** the resolver selects a feasible candidate
- **THEN** the response SHALL include a decision ID
- **AND** querying that decision ID SHALL return the persisted selection record

### Requirement: Metered-Counterfactual Cost Ledger

The system SHALL record actual and counterfactual spend rows and SHALL label estimated-token
rows. The watchdog SHALL schedule a current-month ledger rollup independently of refresh/probe
jobs.

#### Scenario: Ledger distinguishes estimates

- **WHEN** usage is recorded from estimated token counts
- **THEN** the ledger row SHALL retain `tokens_estimated: true`

#### Scenario: Ledger records actual and counterfactual spend

- **WHEN** a completed routing decision reports usage and baseline pricing
- **THEN** one ledger row SHALL record both `actual_usd` and `counterfactual_usd`
- **AND** usage summaries SHALL compute savings from those recorded values

### Requirement: Static-Tier Fallback and Kill Switch

Adaptive resolution SHALL be default-off. When `ROUTING_ADAPTIVE` is off, the exact static
resolution object SHALL be returned. When enabled, resolver error or timeout MUST return that
same static object within the configured bound.

#### Scenario: Flag off preserves the exact result

- **WHEN** `ROUTING_ADAPTIVE` is absent or off
- **THEN** phase resolution SHALL return the exact pre-change static result

#### Scenario: Resolver timeout is bounded

- **WHEN** the adaptive resolver does not respond within its configured timeout
- **THEN** the caller SHALL receive the exact static result within the bounded fallback window

#### Scenario: Resolver unavailability or error is bounded

- **WHEN** adaptive routing is enabled and the resolver is unavailable or raises an error
- **THEN** the caller SHALL receive the exact static result within the configured fallback bound

### Requirement: Incumbent Retention Until Routing Evidence

`select_model_for_task` SHALL accept an optional incumbent identity (`vendor`, `model`). When an
incumbent is supplied, the resolver SHALL keep it unless a feasible challenger is evidenced
(posterior sample size of at least 1, or a benchmark prior greater than 0) and scores strictly more than
`ROUTING_INCUMBENT_MARGIN` (default 0.05) above the incumbent's best feasible score. The resolver
MUST NOT select a challenger without evidence while an incumbent is supplied. Every response and
persisted decision made with an incumbent SHALL carry a `retention` record stating whether the
incumbent was kept and why. When no incumbent is supplied, selection SHALL be identical to the
behavior before this requirement.

#### Scenario: Empty evidence keeps the incumbent

- **WHEN** an incumbent is supplied and no feasible challenger has posterior samples or a positive benchmark prior
- **THEN** the incumbent SHALL be selected
- **AND** `retention` SHALL be `{retained: true, reason: "no-evidence"}`

#### Scenario: Evidenced challenger below margin keeps the incumbent

- **WHEN** the top evidenced challenger's score exceeds the incumbent's score by no more than `ROUTING_INCUMBENT_MARGIN`
- **THEN** the incumbent SHALL be selected with reason `below-margin`

#### Scenario: Evidenced challenger above margin displaces the incumbent

- **WHEN** the top evidenced challenger's score exceeds the incumbent's score by more than `ROUTING_INCUMBENT_MARGIN`
- **THEN** that challenger SHALL be selected
- **AND** `retention` SHALL be `{retained: false, reason: "challenger-evidenced-above-margin"}`

#### Scenario: Ties go to the incumbent

- **WHEN** `ROUTING_INCUMBENT_MARGIN` is 0 and an evidenced challenger scores exactly equal to the incumbent
- **THEN** the incumbent SHALL be selected

#### Scenario: Unresolvable incumbent keeps static

- **WHEN** the supplied incumbent matches no catalog candidate by `(vendor, model)`
- **THEN** `selected` SHALL be null
- **AND** `retention` SHALL be `{retained: true, reason: "incumbent-unresolved"}`
- **AND** the decision SHALL still be persisted

#### Scenario: Infeasible incumbent with an evidenced alternative

- **WHEN** the incumbent is excluded as infeasible and at least one feasible challenger is evidenced
- **THEN** the top evidenced feasible challenger SHALL be selected with reason `incumbent-infeasible-evidenced-alternative`

#### Scenario: Infeasible incumbent without an evidenced alternative

- **WHEN** the incumbent is excluded as infeasible and no feasible challenger is evidenced
- **THEN** `selected` SHALL be null
- **AND** `retention` SHALL be `{retained: true, reason: "incumbent-infeasible-no-evidenced-alternative"}`

#### Scenario: Exploration only among evidenced challengers

- **WHEN** an incumbent is supplied, exploration is allowed, and fewer than two candidates are evidenced
- **THEN** exploration SHALL NOT fire
- **AND** when exploration does fire, the explored candidate SHALL be evidenced and `retention.reason` SHALL be `exploration-evidenced`

#### Scenario: No incumbent preserves prior selection

- **WHEN** a request omits `incumbent`
- **THEN** the selected candidate and exploration outcome SHALL equal the pre-change result for the same catalog and random seed
- **AND** the response SHALL NOT include `retention`

