## MODIFIED Requirements

### Requirement: Incumbent Retention Until Routing Evidence

`select_model_for_task` SHALL accept an optional incumbent identity (`vendor`, `model`). When an
incumbent is supplied, the resolver SHALL keep it unless a feasible challenger is evidenced
(posterior sample size of at least 1, or a benchmark prior greater than 0) and scores strictly more than
`ROUTING_INCUMBENT_MARGIN` (default 0.05) above the incumbent's best feasible score. The resolver
MUST NOT select a challenger without evidence while an incumbent is supplied, except for the
configured fallback below, which selects by operator configuration and never by score. Every response and
persisted decision made with an incumbent SHALL carry a `retention` record stating whether the
incumbent was kept and why. When no incumbent is supplied, selection SHALL be identical to the
behavior before this requirement.

#### Scenario: Empty evidence keeps the incumbent

- **WHEN** an incumbent is supplied, its held catalog row has no posterior samples and no positive benchmark prior, and no feasible challenger has posterior samples or a positive benchmark prior
- **THEN** the incumbent SHALL be selected
- **AND** `retention` SHALL be `{retained: true, reason: "no-evidence"}`

#### Scenario: Evidenced incumbent without an evidenced challenger

- **WHEN** an incumbent is supplied, its held catalog row has posterior samples or a positive benchmark prior, and no feasible challenger has posterior samples or a positive benchmark prior
- **THEN** the incumbent SHALL be selected
- **AND** `retention` SHALL be `{retained: true, reason: "no-evidenced-challenger"}`
- **AND** the reason SHALL NOT be `no-evidence`, which is reserved for decisions where no candidate, the incumbent included, is evidenced

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

#### Scenario: Transiently unavailable incumbent falls back to the configured order

- **WHEN** every excluded row of the incumbent carries a transient availability reason (`lane:unavailable`, `unavailable`, `quota:exhausted`, or `lane:model-rate-limited`), the incumbent is not excluded by cost policy, no feasible challenger is evidenced, the routing policy configures a non-empty `fallback.vendor_order`, lane assignments are enabled, and at least one eligible candidate exists (a feasible candidate other than the incumbent's rows that has an assignment whose agent type is in `fallback.vendor_order` and whose location, isolation and dispatch mode are enumerated in `location_order`, `isolation_order` and `dispatch_mode_order`)
- **THEN** the eligible candidate that ranks first by `fallback.vendor_order`, then `location_order`, `isolation_order`, `dispatch_mode_order`, then `agent_id` SHALL be selected, independent of score and random draws
- **AND** the router SHALL NOT select a candidate that has no assignment, whose agent type is absent from `fallback.vendor_order`, or whose location, isolation or dispatch mode is not enumerated in the corresponding list
- **AND** `retention` SHALL be `{retained: false, reason: "incumbent-infeasible-configured-fallback"}` and `selected` SHALL NOT be null
- **AND** `retention.fallback` SHALL record `incumbent_exclusion_reasons` (the unique reasons of the incumbent's excluded rows, which the router SHALL emit in sorted order) and `order_applied` (a verbatim copy of the policy's `fallback:` block: all four lists)
- **AND** the response's top-level `fallback` SHALL remain `false`
- **AND** the same inputs SHALL yield the same selection on every call, and enabling exploration SHALL NOT change the selection or the reason

#### Scenario: Infeasible incumbent without an evidenced alternative

- **WHEN** the incumbent is excluded as infeasible, no feasible challenger is evidenced, and the configured-fallback scenario does not apply: at least one of the incumbent's excluded rows carries a permanent reason (the design D3 list, such as `lane:archetype-ineligible`, `lane:location-mismatch`, a `roadmap:` exclusion, or `registry:no-catalog-projection`); or `fallback.vendor_order` is absent; or lane assignments are disabled; or no candidate is eligible under the configured lists
- **THEN** `selected` SHALL be null
- **AND** `retention` SHALL be `{retained: true, reason: "incumbent-infeasible-no-evidenced-alternative"}`
- **AND** `retention` SHALL NOT carry a `fallback` record

#### Scenario: Exploration only among evidenced challengers

- **WHEN** an incumbent is supplied, exploration is allowed, and fewer than two candidates are evidenced
- **THEN** exploration SHALL NOT fire
- **AND** when exploration does fire, the explored candidate SHALL be evidenced and `retention.reason` SHALL be `exploration-evidenced`

#### Scenario: No incumbent preserves prior selection

- **WHEN** a request omits `incumbent`
- **THEN** the selected candidate and exploration outcome SHALL equal the pre-change result for the same catalog and random seed
- **AND** the response SHALL NOT include `retention`
