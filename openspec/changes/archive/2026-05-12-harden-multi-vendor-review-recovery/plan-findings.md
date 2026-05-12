# Plan Findings — harden-multi-vendor-review-recovery

This file accumulates findings across iterate-on-plan iterations. Each section is one iteration; findings within an iteration are listed by criticality and type.

## Iteration 1 (2026-05-08)

Self-review pass. Four parallel analysis agents covered: completeness+scope, clarity+consistency+testability, feasibility+parallelizability+assumptions, security+performance+observability.

### Critical (verified against actual code; both confirmed)

| # | Type | Description | Fix applied? |
|---|------|-------------|--------------|
| C1 | assumptions | `consensus_synthesizer.py main()` argparse requires `--findings <file1>...` (`nargs="+"`), NOT `--findings-dir` as design.md assumes (line 113). The proposed subprocess fallback invocation cannot run as designed. | Yes — add `--findings-dir` mode to the CLI as part of Phase 2 (extracted loader work). Update design.md and spec.md R3.S4 to use the correct flag. |
| C2 | consistency | `review_dispatcher.py:1180-1208` writes manifest with shape `{review_type, target, dispatches[], quorum_requested, quorum_received}` — different from proposed `{schema_version, change_id, vendors[].findings_path}`. Naive replacement loses forensically valuable dispatch metadata (model_used, elapsed_seconds, error_class). | Yes — make the new manifest schema a SUPERSET: keep all existing fields, add `schema_version`, `change_id`, `created_at`, and `vendors[]` index. Phase 1 becomes "migration adding fields" not "pure refactor". |

### High (5 findings, all addressed)

| # | Type | Description | Fix applied? |
|---|------|-------------|--------------|
| H1 | security | `artifacts_dir` is caller-controlled; vendor name interpolates into filenames. No path-traversal protection. | Yes — add R6 "Checkpoint Path Safety" with normalization + rejection scenarios. |
| H2 | security | finding.schema.json defines structure but no spec requirement to validate findings against it before checkpoint write. | Yes — add scenario to R1 requiring schema validation before write. |
| H3 | consistency | proposal.md:30 says `load_findings_from_dir() -> list[ReviewFinding]`; design.md says `dict[str, list[ReviewFinding]]`. The vendor-keyed dict form is correct (consensus needs to know each finding's source vendor). | Yes — fix proposal.md. |
| H4 | testability | Task 3.3 says "run all converge() callers' tests" but doesn't enumerate them. | Yes — add explicit grep-based caller-discovery step. |
| H5 | testability | Spec scenario R3.S4 (subprocess uses canonical layout) covered only by Phase 7 integration test, bundled with unrelated assertions. | Yes — add dedicated test task to Phase 5. |

### Medium (8 findings; 6 addressed, 2 deferred)

| # | Type | Description | Fix applied? |
|---|------|-------------|--------------|
| M1 | completeness | No spec scenario for manifest-write permission errors. Design.md mentions it; spec doesn't. | Yes — add to R2. |
| M2 | completeness | No scenario for "subprocess executable not found / version mismatch". | Yes — add to R3. |
| M3 | completeness | Audit event payload doesn't include `checkpoint_dir` for forensic location. | Yes — add to R5. |
| M4 | security | `subprocess_stderr_tail` and `original_exception_message` could leak secrets/PII. | Yes — add sanitization requirement to R3. |
| M5 | testability | R5 has no happy-path no-emission scenario (the spec implicitly assumes silence on success but doesn't require it). | Yes — add R5.S4. |
| M6 | clarity | `.review-cache/` lifecycle mentioned in proposal.md but not encoded in spec. | Yes — add to R1. |
| M7 | performance | No file-locking or atomic-write guarantee for manifest. | Yes — add atomic-rename requirement to R1. |
| M8 | testability | R2.S2 says operator can invoke `consensus_synthesizer.py` manually but doesn't show the command. | Yes — add concrete command example to R2.S2. |

### Low (deferred to /implement-feature judgment or out of scope)

| # | Type | Description | Disposition |
|---|------|-------------|-------------|
| L1 | observability | Add `fallback_latency_seconds` metric to audit event. | Defer — nice-to-have, not load-bearing. Implementation may add. |
| L2 | observability | Cardinality bound on `original_exception_class`. | Defer — bounded in practice by Python exception class names; not a near-term issue. |
| L3 | observability | Audit emission failure logging level (warning vs error). | Defer — implementation detail; design.md D5 says "logger.warning" which is acceptable. |
| L4 | scope | Phase 8.3 (file follow-up bug fix) is bundled as a task but creates a new proposal. | Yes — reframe as "Post-merge action" section in proposal.md, remove from tasks numbered list. |

### Rejected findings

| # | Description | Reason for rejection |
|---|-------------|----------------------|
| R1 | "Lazy checkpoint" (write only on synthesis failure) instead of pre-synthesis | Contradicts the load-bearing architectural decision in design.md D1/D2. The whole point of the proposal is that checkpointing BEFORE synthesis runs is what gives durability. Lazy checkpoint = same failure mode we're fixing. |
| R2 | Adaptive subprocess timeout based on finding count | Speculative. 300s matches existing vendor-adapter convention. Out of scope — file as follow-up if observed in practice. |
| R3 | Split wp-converge-recovery into two packages | Tight but workable at 350 LOC. Add buffer to 400; one merge of related changes is cleaner than two. |
