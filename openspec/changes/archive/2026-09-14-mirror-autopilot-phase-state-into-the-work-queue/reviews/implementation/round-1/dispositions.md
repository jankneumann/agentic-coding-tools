# Implementation review round 1 dispositions

Quorum was not reached: Grok succeeded (12 findings, 348.3s) and Claude Code
timed out after 600.1s. This round is preserved as independent evidence and is
not represented as cross-vendor consensus.

- Grok 1 — fixed: reset the projection-refresh flag after a backpressure drain;
  a RED/GREEN SSE regression proves later label events still refresh.
- Grok 2 — deferred to VALIDATE: live PostgreSQL evidence requires the configured
  integration service; static migration guards remain in the affected suite.
- Grok 3 — fixed: OpenAPI problem responses now use
  `application/problem+json` and declare the runtime problem fields.
- Grok 4 — verified and guarded: an explicit coordinator-free run test installs
  fail-fast transport spies and observes zero projection calls.
- Grok 5 — fixed: contract helper names match the shipped
  `try_projection_issue_*` API.
- Grok 6 — fixed: canonical skill sources were reinstalled into both runtime
  mirrors and verified byte-identical.
- Grok 7–12 — accepted positive observations.
