-- Migration 014: Fix approval_queue schema conflict
--
-- Migration 005 created approval_queue for the (now-retired) verification
-- gateway with columns: changeset_id, requested_by, reviewed_by, etc.
-- Migration 013 assumed the table didn't exist and defined a new schema
-- for dynamic authorization: agent_id, operation, resource, expires_at, etc.
-- Because 013 used CREATE TABLE IF NOT EXISTS, the old table survived and
-- the runtime code (src/approval.py) breaks on column mismatches.
--
-- Fix: drop the stale 005 table and recreate with the 013 schema.

-- Drop old RLS policies (from 005)
DROP POLICY IF EXISTS approval_queue_read ON approval_queue;
DROP POLICY IF EXISTS approval_queue_write ON approval_queue;

-- Drop old indexes (from 005)
DROP INDEX IF EXISTS idx_approval_queue_status;

-- Drop old table (from 005 — verification gateway is retired)
DROP TABLE IF EXISTS approval_queue;

-- Recreate with the dynamic authorization schema (from 013)
CREATE TABLE approval_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id TEXT NOT NULL,
  agent_type TEXT,
  operation TEXT NOT NULL,
  resource TEXT,
  context JSONB DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'denied', 'expired')),
  decided_by TEXT,
  decided_at TIMESTAMPTZ,
  reason TEXT,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_approval_queue_status
  ON approval_queue (status, created_at)
  WHERE status = 'pending';

CREATE INDEX idx_approval_queue_agent
  ON approval_queue (agent_id, created_at);

-- Re-enable RLS
ALTER TABLE approval_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY approval_queue_read ON approval_queue FOR SELECT USING (true);
CREATE POLICY approval_queue_write ON approval_queue FOR ALL
  USING (current_setting('role') = 'service_role');
