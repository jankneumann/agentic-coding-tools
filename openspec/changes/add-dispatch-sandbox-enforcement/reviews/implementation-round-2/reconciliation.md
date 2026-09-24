# Implementation review round 2 reconciliation

The configured vendor panel was attempted against the authorized worktree.
Claude Code and Codex SDK dispatch were unavailable because their API keys were
not configured. Pi completed a substantive review, but its 5.5 MB NDJSON
transcript was classified as a vendor failure by the wrapper instead of being
ingested as a result envelope. Its concrete stale-test-double finding was
retained and fixed. The raw transcript, metadata, and manifest remain in this
round's evidence directory.

Per the operator's escalation instruction, three independent Codex Sol reviews
then covered contract fidelity, adversarial behavior, and end-to-end
integration. Their findings drove these remediations:

- process results now carry typed status/degradation metadata through evaluation,
  review, and provider adapters, including prelaunch enforcement failures;
- every caller uses the exact routed lane, worktree root, correlation fields,
  and current audit event rather than a caller-prepared or stale launch;
- redirects, invalid endpoints, credential/state environment collisions, and
  malformed standalone lane projections fail closed before vendor launch;
- the second capability preflight records its typed degradation and durable
  audit before any permitted unsandboxed fallback;
- read-only snapshot retries record the exact snapshot content digest, and
  asynchronous submissions are explicitly ineligible for host commit until
  collection;
- legacy process-result test doubles remain compatible while production
  results expose the full typed contract.

All three Sol reviewers reported zero blockers after the final remediation.

Final local validation:

- affected skill suites: 1,089 passed, 3 capability skips;
- coordinator suite: 2,923 passed, 43 skipped, with only the same 32 documented
  pre-existing Cedar/native-equivalence failures;
- coordinator strict mypy: 109 source files passed;
- Ruff, install-mirror freshness, dependency direction, strict OpenSpec (114
  artifacts), and diff checks passed;
- focused final regression groups independently passed 204 tests locally and
  321-339 tests in each Sol review lane.

Authoritative Linux/macOS evidence is intentionally verified from the GitHub
workflow for the exact pushed head rather than checked in recursively.
