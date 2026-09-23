# Design: retain-static-model-until-routing-evidence

## Context

The selection pipeline in `RoutingService.select_model` (`agent-coordinator/src/model_routing/api.py`)
runs in this order:

```
list_candidates → [build_feasible_assignments] → score_and_rank → choose (exploration) → payload → record_decision
```

Retention adds one step between `score_and_rank` and `choose`, and narrows the candidate set
that `choose` may explore over. Nothing upstream changes: catalog, feasibility, assignment and
scoring all behave exactly as they do today.

## Decisions

### D1: Evidence predicate

A candidate is **evidenced** when `posterior.sample_size >= 1` **or** `benchmark_prior > 0`.
The predicate is a pure function in `resolver.py` (`has_evidence(candidate)`) so that exploration
and retention share one definition.

- Rationale: these are exactly the two inputs `blend_quality` reads (resolver.py:343). When both are
  empty, the candidate's quality is the `0.0` default, and its score says nothing about the
  model.
- Rejected: using `cost_source == "posterior"`. That needs `sample_size >= 5`
  (`DEFAULT_COST_SAMPLE_THRESHOLD`), which would ignore priors entirely. The user's discovery answer
  counts priors as evidence.

### D2: Incumbent identity is `(vendor, model)`, where vendor is the catalog vendor

The request field is `incumbent: {vendor: str | null, model: str}`. Server-side matching is exact on
`(vendor, model)` against scored candidates. `endpoint_kind` and `base_url` are ignored because
the static resolution has no such fields. If several rows share `(vendor, model)` (for example a
CLI row and an SDK row), the incumbent's score is the **maximum** over the matching rows.

- The client sends `vendor = agents_config[provider].catalog_vendor` (so pi maps to `openrouter`) and
  `model = static.model`. With `provider is None`, it sends `vendor = null` and
  `model = static.model` (a tier name). That can never match, and it produces
  `incumbent-unresolved` (D5).
- Rejected: a tier→model alias table on the server. That is out of scope per the discovery
  answer, and the catalog already stores concrete model strings from `model_aliases`.

### D3: Retention rule (applied after ranking, before exploration)

Let `M = ROUTING_INCUMBENT_MARGIN` (server environment variable, default `0.05`, read with the
existing `_nonnegative_env_float`). Let `I` be the incumbent's best feasible score and `C*` the
top **evidenced** feasible challenger (a candidate that is not the incumbent).

| Situation | Outcome | `retention.reason` | `retained` |
|---|---|---|---|
| Incumbent not in scored or excluded candidates | keep static | `incumbent-unresolved` | true |
| Incumbent feasible, no evidenced challenger | keep incumbent | `no-evidence` | true |
| Incumbent feasible, `score(C*) - I <= M` | keep incumbent | `below-margin` | true |
| Incumbent feasible, `score(C*) - I > M` | select `C*` | `challenger-evidenced-above-margin` | false |
| Incumbent infeasible, `C*` exists | select `C*` | `incumbent-infeasible-evidenced-alternative` | false |
| Incumbent infeasible, no `C*` | keep static | `incumbent-infeasible-no-evidenced-alternative` | true |

An infeasible incumbent is one that appears in `excluded` (from `feasibility_reason` or
`build_feasible_assignments`) but not in `ranked`. The margin is compared strictly (`>`), so
`M = 0` means any strict improvement wins, and ties always go to the incumbent.

### D4: Exploration is restricted to evidenced challengers

When an incumbent is supplied, `choose()` receives an exploration pool made of the evidenced
candidates only. Exploration can therefore fire only when there are at least 2 evidenced candidates, which is the
existing `len >= 2` guard applied to the filtered pool. An exploration pick overrides retention
(`exploration: true`, `retained: false`, reason `exploration-evidenced`). The budget accounting
is unchanged.

- Without an incumbent, `choose()` behaves exactly as today, which meets the compatibility NFR.
- Rejected: disabling exploration only for phase resolution. The user chose evidenced-only
  exploration, which keeps the learning mechanism available to every caller.

### D5: Response shape when static is kept

- `retention: {retained: bool, reason: str, margin: float, incumbent_score: float | null}` is
  added to `SelectModelResponse` and to the persisted decision row. It is optional, and absent
  when no incumbent was supplied.
- When the incumbent is kept and resolved, `selected` is the incumbent's own scored candidate.
- When the reason is `incumbent-unresolved` or `incumbent-infeasible-no-evidenced-alternative`, no
  feasible catalog row represents the incumbent, so `selected` is **null**. This makes
  `selected` nullable in the contract, but only in combination with `retention.retained == true`.
  Old clients such as the pre-change `resolve_phase_model`, which raise on a non-dict `selected`,
  therefore fall back to the exact static result through the existing D2 path. That keeps it
  backward-compatible by construction.
- Rejected: synthesizing a fake `CandidateResponse` for the static model. `EndpointKind` is a
  closed literal, `score` is required, and a made-up candidate would put fabricated data in the ledger.

### D6: Client returns the exact static object on retention

In `resolve_archetype_for_phase`, when `retention.retained` is true the client returns the
**exact static object**: the same identity as the flag-off path, not a copy rebuilt from
`selected`. Only a non-retained selection builds a new `ResolvedArchetype`. With an empty catalog,
the "zero differences from static" NFR therefore holds by identity, not by string comparison.
Errors and timeouts still go through the unchanged D2 fallback.

### D7: Contract overlay, not an edit to the archive

Following the pattern set by `implement-the-task-router-vendor-x-location-x-model` (`v1.1.yaml`
overlay), this change adds `contracts/openapi/v1.2.yaml` (the `select_model` request and response
delta) and a revised `contracts/events/routing-decision-record.schema.json` under its own change
directory. Tests locate them with `change_dir()`, so there are no literal `openspec/changes/<id>/`
paths (a guard test enforces this). The archived `add-adaptive-model-router` contract stays untouched.

### D8: Persist retention in a new column (migration 044), added during implementation

Planning assumed decisions are stored as a free-form JSON document. They are not.
`routing_decisions` (migration 040) has fixed columns, with no `retention` and with
`selected JSONB NOT NULL`, and the assignment-path RPC `record_routing_decision_with_audit`
(migration 042) inserts named columns and derives its audit link from `selected`. The user chose
a migration over nesting the data in `budget_state` (2026-09-23, during implementation).

`044_routing_decision_retention.sql`:
- `ALTER TABLE routing_decisions ADD COLUMN retention JSONB` (nullable).
- `ALTER COLUMN selected DROP NOT NULL`, plus `CHECK (selected IS NOT NULL OR retention IS NOT NULL)`,
  so a null selection is only representable when it carries a retention record.
- `CREATE OR REPLACE FUNCTION record_routing_decision_with_audit`, which also inserts `retention`.
  When `selected` is null, the audit link's policy version and checksum fall back to the decision's
  top-level `provenance`, and `CatalogService.record_decision_and_audit` builds the matching link
  with a null agent and model.

Deployment order is safe both ways. A decision without an incumbent never writes the `retention`
key, so it works before and after 044. A decision with an incumbent that reaches an un-migrated
database fails its insert, and the client falls back to the exact static result through D2. After
044, pre-change code keeps working, because every change is additive.

## Risks

- **Harbor rebase**: `add-harbor-benchmark-routing` (plan only) will need its "flag on ranks by
  priors" scenario rebased onto the ADDED requirement. This is noted in the proposal's Impact section.
- **Margin scale drift**: `M` is absolute on the utility scale. If objective-profile weights change
  the scale, `0.05` may need retuning. That is acceptable, because the value is an environment knob and appears in
  every decision row (`retention.margin`).
- **Duplicate rows per `(vendor, model)`**: using the maximum score (D2) favors the incumbent, which
  is the conservative direction.
