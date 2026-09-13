# Architecture Impact: implement-idempotent-queue-submission-and-outbox-ordering

**Validated commit**: `59fdb05f65e2a38d3ad75263a6a51f950edb7be2`

## Status

**DEGRADED (advisory)** — Current architecture artifacts could not be produced. The refresh configuration expects root `src`, `database/migrations`, and `web` inputs; those paths do not exist, so refresh stopped before promotion and left committed architecture artifacts untouched. The configured architecture gate mode is advisory.

## Evidence

- Freshness was stale (`INPUT_FINGERPRINT_MISMATCH`, `ARTIFACT_DIGEST_MISMATCH`).
- The staged refresh found no analyzer output and failed before graph compilation or promotion.
- Structural linters returned 16 medium advisory file-size findings.
- Package scope and lock overlap validation passed independently; `wp-coordinator-queue` and `wp-bridge-projection` remain the only declared parallel pair.

Correct the architecture source-root configuration, refresh the graph, and rerun baseline diff and scoped flows before treating architecture evidence as current. This baseline is not accepted as current architecture evidence for ri-08.

## Canonical Validation 5 Audit

At commit `0106b8fab44c6c7e61eb0c045205afb2779fb764` (tree `04610c62774d7b1dffe5aa62e3d6849823daf39a`), the architecture status remains **DEGRADED (advisory)** for the same source-root configuration reason. Fresh package schema, DAG, lock, parallel-overlap, and context-impact gates passed, and the bounded CI-remediation diff adds no blocking architecture finding. No architecture artifact was refreshed or promoted during this audit.

## Canonical Validation 6 Audit

At commit `d07699d0bcb7419375ade797c895164805f147f7` (tree `a37851937da4993d2b764bdbf36a1bb96a62f3eb`), the architecture status remains **DEGRADED (advisory)** for the same pre-existing source-root configuration reason. Fresh package schema, DAG, lock, parallel-overlap, and context-impact gates passed for all four declared packages, and the product diff since Validation 5 (`http_proxy.py`, `work_queue.py`, `036_terminal_completion_guard.sql`, `autopilot.py`) adds no blocking architecture finding. This round's overall VALIDATE result is **FAIL** on unrelated grounds — a real `TestCompleteTaskTerminalCancellation` regression against live PostgreSQL, reproduced both locally and in GitHub's required `test-integration` job — not an architecture finding. No architecture artifact was refreshed or promoted during this audit.

## Canonical Validation 7 Audit

At commit `377b9deb80d2c5f7869b5151d63d63b0d71824d0` (tree `d403701f6c32a7fbb406391d8d5e200a7df32ca2`), the architecture status remains **DEGRADED (advisory)** for the same pre-existing source-root configuration reason — unchanged since Validation 5. Fresh package schema, DAG, lock, parallel-overlap, and context-impact gates passed for all four declared packages, and the sole product diff since Validation 6 (`agent-coordinator/src/db_postgres.py`, the Validation Fix 6 jsonb-codec registration) adds no blocking architecture finding. This round's overall VALIDATE result is **PASS**: a fresh live-PostgreSQL run confirms `TestCompleteTaskTerminalCancellation::test_late_complete_after_reconcile_cancel_is_refused` (the Validation 6 regression) now passes, and GitHub's required `test-integration` check is green at this exact head. No architecture artifact was refreshed or promoted during this audit.
