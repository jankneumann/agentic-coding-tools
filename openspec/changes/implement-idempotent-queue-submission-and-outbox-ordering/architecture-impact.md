# Architecture Impact: implement-idempotent-queue-submission-and-outbox-ordering

**Validated commit**: `a6df5c18bbef57cb0d27875c8f95e83e4ebf1076`

## Status

**DEGRADED** — Current architecture artifacts could not be produced. The refresh configuration expects root `src`, `database/migrations`, and `web` inputs; those paths do not exist, so refresh stopped before promotion and left the last-known graph untouched.

## Evidence

- Freshness was stale (`INPUT_FINGERPRINT_MISMATCH`, `ARTIFACT_DIGEST_MISMATCH`).
- Scoped validation against the stale graph covered 83 changed files and returned 0 findings, but this is explicitly unverified.
- Structural linters returned 14 medium advisory file-size findings.

Correct the architecture source-root configuration, refresh the graph, and rerun baseline diff and scoped flows before treating architecture evidence as current.
