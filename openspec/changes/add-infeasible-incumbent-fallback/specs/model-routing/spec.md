## MODIFIED Requirements

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

- **WHEN** the incumbent is excluded for transient availability (`lane:unavailable`, `unavailable`, `quota:exhausted`, or `lane:model-rate-limited`), no feasible challenger is evidenced, the routing policy configures `fallback.vendor_order`, and at least one feasible candidate exists
- **THEN** the feasible candidate that ranks first by `fallback.vendor_order`, then `location_order`, `isolation_order`, `dispatch_mode_order`, then `agent_id` SHALL be selected, independent of score and random draws
- **AND** `retention` SHALL be `{retained: false, reason: "incumbent-infeasible-configured-fallback"}`
- **AND** the persisted decision SHALL record the exclusion reason of the incumbent and the fallback order applied

#### Scenario: Infeasible incumbent without an evidenced alternative

- **WHEN** the incumbent is excluded as infeasible, no feasible challenger is evidenced, and the configured-fallback scenario does not apply (the exclusion is a permanent mismatch such as `lane:archetype-ineligible`, `lane:location-mismatch`, a `roadmap:` exclusion, or `registry:no-catalog-projection`; or no `fallback.vendor_order` is configured; or no feasible candidate exists)
- **THEN** `selected` SHALL be null
- **AND** `retention` SHALL be `{retained: true, reason: "incumbent-infeasible-no-evidenced-alternative"}`
- **AND** the router SHALL NOT select a candidate that a permanent-mismatch exclusion would bypass

#### Scenario: Exploration only among evidenced challengers

- **WHEN** an incumbent is supplied, exploration is allowed, and fewer than two candidates are evidenced
- **THEN** exploration SHALL NOT fire
- **AND** when exploration does fire, the explored candidate SHALL be evidenced and `retention.reason` SHALL be `exploration-evidenced`

#### Scenario: No incumbent preserves prior selection

- **WHEN** a request omits `incumbent`
- **THEN** the selected candidate and exploration outcome SHALL equal the pre-change result for the same catalog and random seed
- **AND** the response SHALL NOT include `retention`
