"""Adaptive model routing (OpenSpec: add-adaptive-model-router).

Coordinator-owned model catalog, selection resolver, spend ledger, feedback
aggregation, and probes. This package is the Coordination-layer decision home;
skills remain the Execution-layer dispatch consumers (design D1).

The scoring core (`resolver`, `exploration`) is pure and dependency-free so the
routing intelligence is unit-testable without a database; the catalog/ledger/
refresher layers (added by wp-db-catalog) provide the DB-backed inputs.
"""
