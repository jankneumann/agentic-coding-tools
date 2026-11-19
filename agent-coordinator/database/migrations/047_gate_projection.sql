-- 047: project-keyed gate projection.
--
-- Pending human gates live in each repository: parked dispatch attempts in
-- openspec/roadmaps/*/checkpoint.json and pending_gate in
-- openspec/changes/*/loop-state.json. A collector that runs in the repository
-- pushes the whole pending set here, so one read can list what awaits a
-- decision across every enrolled project.
--
-- The table is a cache of what repositories last reported, nothing more:
--   * one row per project, replaced whole on every push, so a gate that was
--     answered in its repository disappears with the next push and there is
--     no per-gate row to reconcile;
--   * the snapshot is one JSONB value ({"gates": [...], "source_errors":
--     [...]}), because it is only ever read and written as a unit;
--   * no column records a decision. A decision is made through the approval
--     service (approval_queue) or in the repository, and reaches this table
--     only as the absence of the gate in a later snapshot.
-- Deleting every row loses nothing that the next push does not restore.
--
-- collected_at is the collector's clock; received_at is the coordinator's and
-- is the one staleness is measured against.

BEGIN;

CREATE TABLE IF NOT EXISTS gate_projection_snapshots (
    project TEXT PRIMARY KEY CHECK (project ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'),
    collected_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL,
    digest TEXT NOT NULL
);

COMMIT;
