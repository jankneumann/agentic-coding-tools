# Contracts: bind-merge-verdicts-to-head-sha-and-patch-id

No new contract sub-types apply to this change:

- **OpenAPI:** none — the merge path is a set of local CLIs with no HTTP surface.
- **Database:** none.
- **Events:** none new. The merge event record (`merge_events.MergeEvent`) gains
  two optional fields, `waiver_source` and `waiver_reason`. `to_dict` drops
  `None`, so records written without a waiver are byte-identical to today's
  and no reader changes (design D6).

The interface changes this change does make, and where each is pinned:

| Interface | Normative source | Pinned by |
|---|---|---|
| Merge plan `schema_version` `1.1 → 1.2`: adds `state.review_waiver`, removes `state.iterate_consensus_path`; any other version is rejected with a rebuild message | `skills/merge-pull-requests/contracts/merge-plan.schema.json` (existing file, edited in place) and `specs/merge-pull-requests/spec.md` "Durable Merge Plan Artifact" | `scripts/tests/test_merge_plan_contract.py` |
| Verdict binding inside `state.vendor_verdict.binding` (`head_sha`, `patch_id`, `reviewers[]`, `author`, `same_family`, `bound_at`) | design D1; `specs/merge-pull-requests/spec.md` "Verdict Binding and Currency" | `scripts/tests/test_verdict_binding.py` (`validate_binding`) |
| `execute_plan.py --waive-review "<reason>"` | design D7; spec "Recorded Review Waivers" | `scripts/tests/test_execute_plan.py` |
| `review_dispatcher` `exclude_vendor: str \| Collection[str] \| None` | design D5 | `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher_exclude_vendor.py` |

The binding is deliberately **not** described in the plan schema:
`vendor_verdict` stays `additionalProperties: true` because
`add-orchestrator-adjudication-review-gate` will extend the same object, and its
shape is checked by `verdict_binding.validate_binding` instead (design D8). A
separate JSON Schema file for the binding would have a single reader and would
need editing again by that change.
