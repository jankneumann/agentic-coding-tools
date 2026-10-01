# Tasks: Split the `no-evidence` retention reason

> Change ID: `split-no-evidence-retention-reason`
> Tier: coordinated (single `wp-main` package)
> Scenario IDs: `model-routing.1`–`.10` are the scenarios of "Incumbent Retention Until Routing
> Evidence", in order. `.1` is the tightened "Empty evidence keeps the incumbent" and `.2` is the
> new "Evidenced incumbent without an evidenced challenger".
> **Start only after `implement-the-task-router-vendor-x-location-x-model` has merged (D6).**

## 1. Contracts

- [ ] 1.1 Repoint `tests/model_routing/test_incumbent_retention_contracts.py` to this change
  with `change_dir()`. Extend `_KEPT` with `no-evidenced-challenger` and assert that the new
  value is not in the null-selected set. Confirm the tests fail against the current
  contracts. [S]
  **Spec scenarios**: model-routing.2
  **Contracts**: contracts/openapi/v1.3.yaml, contracts/events/routing-decision-record.schema.json
  **Design decisions**: D3
  **Dependencies**: None
- [ ] 1.2 Add the failing parity test: the `RetentionReason` Literal equals the v1.3 enum,
  the record-schema enum and the generated Literal. [S]
  **Spec scenarios**: model-routing.1, model-routing.2
  **Contracts**: contracts/openapi/v1.3.yaml, contracts/events/routing-decision-record.schema.json, contracts/generated/models.py
  **Design decisions**: D4
  **Dependencies**: 1.1
- [ ] 1.3 Check that the v1.3 overlay, the record schema and the generated models in this
  change make 1.1 pass. Diff each against its v1.2 counterpart; only the three D3
  differences may appear. [XS]
  **Dependencies**: 1.1
- [ ] Checkpoint: run tests, review diff, verify scope

## 2. Retention reason

- [ ] 2.1 Write failing resolver tests in `test_incumbent_retention.py`:
  - an evidenced held row with no evidenced challenger gives `no-evidenced-challenger`;
  - an unevidenced held row with no evidenced challenger still gives `no-evidence`;
  - with several matching rows, only the **held** (best-scoring) row's evidence counts. [S]
  **Spec scenarios**: model-routing.1, model-routing.2
  **Design decisions**: D1, D2
  **Dependencies**: None
- [ ] 2.2 In `apply_incumbent_retention`, return `no-evidenced-challenger` when
  `best_challenger is None` and `held.evidenced`. Add the value to `RetentionReason` in
  `api.py`. 1.2 and 2.1 should then pass. [XS]
  **Dependencies**: 1.2, 2.1
- [ ] 2.3 Write a service-level test in `test_service_incumbent.py`: an evidenced incumbent
  with only unevidenced challengers returns and persists `no-evidenced-challenger`, and the
  persisted record validates against the v1.3 record schema. [S]
  **Spec scenarios**: model-routing.2
  **Contracts**: contracts/events/routing-decision-record.schema.json
  **Dependencies**: 2.2
- [ ] Checkpoint: run tests, review diff, verify scope

## 3. Compatibility and docs

- [ ] 3.1 Run the full retention matrix (`tests/model_routing`) and confirm that every
  pre-existing selection assertion (`selected`, `retained`, exploration) is unchanged, with
  no other test edits. [XS]
  **Spec scenarios**: model-routing.3 through model-routing.10
  **Design decisions**: D2
  **Dependencies**: 2.2
- [ ] 3.2 Add `no-evidenced-challenger` to the reason list in `agent-coordinator/CLAUDE.md`,
  including the one-line distinction from `no-evidence`. [XS]
  **Dependencies**: 2.2
- [ ] 3.3 Run the coordinator suite (`-m "not e2e and not integration"`), `mypy --strict src/`
  and `ruff check .`. [XS]
  **Dependencies**: 3.1, 3.2
- [ ] Checkpoint: run tests, review diff, verify scope
