Review the dg-01 OpenSpec plan for correctness, architecture, security, resilience, compatibility, observability, readability, and performance. Read: openspec/changes/add-live-vendor-capability-and-cost-registry/proposal.md, design.md, tasks.md, specs/vendor-registry/spec.md, work-packages.yaml, change-context.md, and every file under openspec/changes/add-live-vendor-capability-and-cost-registry/contracts/. Compare the plan to existing AgentEntry/agents.yaml, /agents/dispatch-configs, vendor_health.py, WatchdogService vendor events, model_routing CatalogService/local probes, coordination_bridge.py, autopilot-roadmap policy.py/orchestrator.py, and provider_dispatch.py.

Pay special attention to lane identity versus provider grouping; how legacy vendor_limit:claude outcomes become unambiguous lane observations; first-probe persistence; expiry/staleness; model-catalog-only pricing; deterministic conversion of model prices into policy deltas; authentication; coordinator-unavailable behavior; TDD ordering; and whether work-package scopes contain every required caller without colliding. Return only one JSON object.

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
