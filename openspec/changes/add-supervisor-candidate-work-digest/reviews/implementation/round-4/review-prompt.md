Review ONLY the committed delta `85c3118f..94f902d6` for OpenSpec change
`add-supervisor-candidate-work-digest`, and ONLY the two behaviors below. This is
an operator-authorized, post-cap verification round. Do not inspect for, report,
or suggest any other issue or work (including cleanup, refactoring, docs, style,
performance, security, architecture, or additional tests).

Evaluate each behavior independently as PASS or FAIL:

1. `decide` rejects every malformed, non-null `roadmap_ref` supplied with an
   approved `refine-roadmap` route before any mirror mutation, while canonical
   references matching `<roadmap-id>:ri-<nn>` still succeed and persist the
   approval.
2. A persisted candidate-store key absent from the prior digest's `ranked` set
   is treated as lifecycle composition drift. In the interrupted sequence
   "score A; store unscored B; terminally prune A; stop before Rank; run the
   next unchanged preflight", B must not be hidden by unchanged empty-digest
   reuse: the next preflight remains lifecycle-changed and `prepare_batch`
   requests B.

Inspect only these files and the relevant lines in this delta:

- `skills/supervise/scripts/digest.py`
- `skills/tests/supervise/test_digest.py`

You may run only these regressions:

```text
skills/tests/supervise/test_digest.py::test_decide_rejects_malformed_refine_roadmap_ref_without_writing_mirror
skills/tests/supervise/test_digest.py::test_decide_accepts_canonical_refine_roadmap_ref
skills/tests/supervise/test_digest.py::test_lifecycle_marks_unranked_survivor_as_changed_after_interrupted_empty_rebuild
```

Return ONLY one JSON document conforming to
`openspec/schemas/review-findings.schema.json` with
`review_type: "implementation"`, `target: "whole-branch"`, your actual
reviewer vendor, and exactly two findings in the order above. Each finding is
the verdict for one named behavior:

- PASS: `severity: "none"`, `criticality: "low"`, `disposition: "accept"`,
  and a description beginning `none: PASS —`.
- FAIL: `severity: "critical"`, `criticality: "critical"`,
  `disposition: "fix"`, and a description beginning `Critical: FAIL —` that
  states only how that named behavior remains broken.

Use `type: "correctness"`, `axis: "correctness"` for behavior 1 and
`type: "resilience"`, `axis: "resilience"` for behavior 2. Use
`package_id: "whole-branch"`, repository-relative `file_path`, exact
`line_range`, and `evidence_class: "deterministic"` on both findings. Do not
emit a third finding, even a positive observation.
