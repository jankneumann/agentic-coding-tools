-- Dynamic Authorization: Database Contract
-- Migration: 013_dynamic_authorization.sql
-- All changes are additive (no breaking modifications to existing tables)

-- 1. Delegated identity on agent_sessions
ALTER TABLE agent_sessions
  ADD COLUMN IF NOT EXISTS delegated_from TEXT DEFAULT NULL;

COMMENT ON COLUMN agent_sessions.delegated_from IS
  'Principal (human user or parent agent) that authorized this session. NULL = self-authorized.';

-- 2. Approval queue
CREATE TABLE IF NOT EXISTS approval_queue (
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

CREATE INDEX IF NOT EXISTS idx_approval_queue_status
  ON approval_queue (status, created_at)
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_approval_queue_agent
  ON approval_queue (agent_id, created_at);

-- 3. Cedar policies history
CREATE TABLE IF NOT EXISTS cedar_policies_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  policy_id UUID NOT NULL,
  policy_name TEXT NOT NULL,
  version INTEGER NOT NULL,
  policy_text TEXT NOT NULL,
  changed_by TEXT,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  change_type TEXT NOT NULL CHECK (change_type IN ('create', 'update', 'delete', 'rollback'))
);

CREATE INDEX IF NOT EXISTS idx_cedar_policies_history_name_version
  ON cedar_policies_history (policy_name, version DESC);

-- 4. Policy version column on cedar_policies
ALTER TABLE cedar_policies
  ADD COLUMN IF NOT EXISTS policy_version INTEGER NOT NULL DEFAULT 1;

-- 5. Trigger: capture policy changes to history
CREATE OR REPLACE FUNCTION capture_policy_history()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    INSERT INTO cedar_policies_history (policy_id, policy_name, version, policy_text, changed_by, change_type)
    VALUES (OLD.id, OLD.name, OLD.policy_version, OLD.policy_text, current_setting('app.changed_by', true), 'delete');
    RETURN OLD;
  ELSIF TG_OP = 'UPDATE' THEN
    INSERT INTO cedar_policies_history (policy_id, policy_name, version, policy_text, changed_by, change_type)
    VALUES (OLD.id, OLD.name, OLD.policy_version, OLD.policy_text, current_setting('app.changed_by', true), 'update');
    NEW.policy_version := OLD.policy_version + 1;
    RETURN NEW;
  ELSIF TG_OP = 'INSERT' THEN
    INSERT INTO cedar_policies_history (policy_id, policy_name, version, policy_text, changed_by, change_type)
    VALUES (NEW.id, NEW.name, NEW.policy_version, NEW.policy_text, current_setting('app.changed_by', true), 'create');
    RETURN NEW;
  END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_cedar_policies_history
  AFTER INSERT OR UPDATE OR DELETE ON cedar_policies
  FOR EACH ROW EXECUTE FUNCTION capture_policy_history();

-- 6. Trigger: NOTIFY on policy changes (for LISTEN/NOTIFY sync)
CREATE OR REPLACE FUNCTION notify_policy_changed()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    PERFORM pg_notify('policy_changed', OLD.name);
  ELSE
    PERFORM pg_notify('policy_changed', NEW.name);
  END IF;
  RETURN NULL;  -- after trigger, return value ignored
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_notify_policy_changed
  AFTER INSERT OR UPDATE OR DELETE ON cedar_policies
  FOR EACH ROW EXECUTE FUNCTION notify_policy_changed();

-- 7. Session-scoped permission grants
CREATE TABLE IF NOT EXISTS session_permission_grants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  justification TEXT,
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ,
  approved_by TEXT,
  UNIQUE (session_id, operation)
);

CREATE INDEX IF NOT EXISTS idx_session_grants_agent
  ON session_permission_grants (agent_id, granted_at);

CREATE INDEX IF NOT EXISTS idx_session_grants_session
  ON session_permission_grants (session_id);
