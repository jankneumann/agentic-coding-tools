# Architecture Impact: implement-idempotent-queue-submission-and-outbox-ordering

**Validated commit**: `b0907df98c04af88f7c72cd5043823c533154844`

## Status

**DEGRADED (advisory)** — Current architecture artifacts could not be produced. The refresh configuration expects root `src`, `database/migrations`, and `web` inputs; those paths do not exist, so refresh stopped before promotion and left committed architecture artifacts untouched. The configured architecture gate mode is advisory.

## Evidence

- Freshness was stale (`INPUT_FINGERPRINT_MISMATCH`, `ARTIFACT_DIGEST_MISMATCH`).
- The staged refresh found no analyzer output and failed before graph compilation or promotion.
- Structural linters returned 14 medium advisory file-size findings.
- Package scope and lock overlap validation passed independently; `wp-coordinator-queue` and `wp-bridge-projection` remain the only declared parallel pair.

Correct the architecture source-root configuration, refresh the graph, and rerun baseline diff and scoped flows before treating architecture evidence as current. This baseline is not accepted as current architecture evidence for ri-08.
