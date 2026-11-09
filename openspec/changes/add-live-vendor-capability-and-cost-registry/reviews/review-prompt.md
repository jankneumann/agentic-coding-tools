Final plan convergence review for dg-01 revision 3. Review current proposal/design/tasks/spec/contracts/work-packages/change-context only; historical rounds are evidence, not current input. Compare current artifacts with implementation seams. Focus on any remaining deterministic contradiction or missing owner after revisions: explicit identity/location; exact model join; endpoint-kind local gating; lane vs model limits; probe deployment/startup/freshness; atomic RPC replay/compaction; report-operation authorization; exact dispatcher attribution; bridge dependency/error codes; legacy provider-scope behavior; request quotes/unknown cost guard; and executable gates. Do not repeat issues closed in current normative text. Return JSON only.

REQUIRED on every finding — output is REJECTED if any is missing: id, type, criticality, description, disposition, axis, severity
These fields use DIFFERENT vocabularies. Do not reuse one value for another:
  criticality: low|medium|high|critical — how much it matters
  severity: critical|nit|optional|fyi|none — review-gate grading (NOT the same scale as criticality)
  axis: correctness|readability|architecture|security|performance|observability|resilience|compatibility
  type: spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure
  disposition: fix|regenerate|accept|escalate
Use exactly one value from each listed set; do not invent values.
OPTIONAL: report which selected files you actually reviewed as a top-level `coverage` object: `{"reviewed": ["path", ...], "skipped": [{"path": "path", "reason": "why"}, ...]}`. Omitting `coverage` is treated as full coverage, never as a penalty.
Output ONLY a JSON object with a top-level `findings` array.
