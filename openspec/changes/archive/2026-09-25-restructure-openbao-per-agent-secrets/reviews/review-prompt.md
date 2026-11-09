Review the pca-02 plan in this checkout independently. Read proposal.md, design.md, tasks.md, specs/**/spec.md, contracts/**, and work-packages.yaml under openspec/changes/restructure-openbao-per-agent-secrets. Check correctness, security, architecture, resilience, compatibility, testability, and package feasibility against current code. Output only schema-valid JSON findings; do not modify plan artifacts. Focus on concrete defects with actionable resolutions. Target: restructure-openbao-per-agent-secrets. Review type: plan.

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
