## ADDED Requirements

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
