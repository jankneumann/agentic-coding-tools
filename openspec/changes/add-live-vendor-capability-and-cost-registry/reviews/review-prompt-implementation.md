You are an independent, read-only implementation reviewer for OpenSpec change add-live-vendor-capability-and-cost-registry (dispatch-governance dg-01).

Review the actual implementation diff from base c24c7aced1607d11fb7f0e796328a9b5644366e0 through head e0f73771, plus the proposal, design, normative spec, contracts, work-packages.yaml, choices ledger, and tests. Do not modify files. Inspect the code and tests directly; validation evidence is supporting evidence, not a substitute for review.

Implementation packages:
- wp-contracts: executable OpenAPI, SQL, and event parity.
- wp-registry-core: typed configured lanes, durable probe/limit registry, catalog projection and decimal quotes.
- wp-api-watchdog: authenticated routes, RFC7807 errors, watchdog persistence/compaction, deployed probe packaging.
- wp-dispatch-reporting: bridge helpers and exact-lane capacity propagation/reporting.
- wp-roadmap-policy: registry-derived lane filtering/selection, cost guard, explicit fallback posture, no hardcoded roster.

Validate especially:
1. Contract compliance for GET /vendors, GET /vendors/{agent_id}/availability, POST /vendors/{agent_id}/rate-limit-observations, three auth headers, authorization, reset/model/metadata bounds, and RFC7807 errors.
2. SQL replay atomicity, finite reset expiry, staleness boundaries, compaction, one-probe/one-limit/one-catalog batching, and no second price store.
3. Exact identity mapping among agent_id, vendor_type, policy_vendor, catalog_vendor, explicit location, and multi-publisher model joins without heuristics.
4. Watchdog first-poll/all-lane persistence, no_probe_method, per-lane failure isolation, preserved transitions, independent startup, and Docker probe availability.
5. Dispatcher exact-once terminal capacity reporting, per-model intermediate callbacks across successful fallback, exact lane propagation, and no provider-to-lane inference.
6. Roadmap filtering and selection, lane/model limit semantics, exact catalog quotes, static-tier non-USD behavior, fail-closed registry outage, bounded explicit agents.yaml fallback, and provider-only legacy current-run behavior.
7. Backward compatibility of additive optional fields and callback seams; security, performance, observability, and resilience.
8. Scope: identify any missing acceptance outcome, untested branch, race, authorization bypass, hidden hardcoded vendor list, or behavior contradicting the contracts.

Reported green evidence before review:
- contract parity: 19 passed.
- registry core: 25 required PostgreSQL tests with zero skips plus 151 config regressions.
- API/watchdog: 35 package/catalog tests, 113 coordinator auth regressions, 12 vendor-health tests.
- dispatch reporting: 229 exact package, 544 parallel-infrastructure, 868 autopilot/provider/phase.
- roadmap policy: 53 declared and 99 full autopilot-roadmap.
- Ruff and strict OpenSpec 93/0 passed at package boundaries.
- Choices ledger records explicit ROUND_HALF_UP at six decimals as a sound implementation-time decision.

Return JSON only conforming to openspec/schemas/review-findings.schema.json:
- review_type: implementation
- target: add-live-vendor-capability-and-cost-registry
- reviewer_vendor: your vendor/model name
- findings: array
Each finding must include id, type, criticality, description, disposition, axis, severity, package_id, file_path and line_range when code-local. Description must begin with the matching severity prefix: Critical:, Nit:, Optional:, FYI:, or none:. Use severity critical only for merge-blocking defects and disposition fix or escalate. Security findings cannot be accepted. If no defect is found, include at least one positive severity none finding naming concrete reviewed behavior. Cover multiple axes where evidence supports them. Do not mark judgment as deterministic; reviewers are judgment-class unless citing a reproducible failing command you actually ran.
