-- Migration 033: add the delegated_from column audit writes have always sent
--
-- Dependencies: 008_audit_log.sql
--
-- AuditService.log_operation() has always built its payload with a
-- `delegated_from` key (src/audit.py), and AuditEntry carries the field, but
-- 008 never created the column and migration 013 added `delegated_from` to
-- `agent_sessions` instead. Every insert into audit_log therefore failed with
--
--     column "delegated_from" of relation "audit_log" does not exist
--
-- and the coordinator's entire audit trail silently recorded nothing on the
-- PostgreSQL backend. The failure was invisible because log_operation's
-- fire-and-forget path discards the AuditResult and _insert_audit_entry
-- swallows the exception, so callers were told success=True either way.
--
-- The column is the intended shape, not the payload: delegation is a real
-- concept in this system (see 013's COMMENT on agent_sessions.delegated_from
-- and ProfileResult.delegated_from), and an audit row that cannot record which
-- principal delegated the authority is missing the fact that matters most for
-- a delegated operation.

ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS delegated_from TEXT DEFAULT NULL;

COMMENT ON COLUMN audit_log.delegated_from IS
    'Agent ID that delegated authority for this operation, when the acting '
    'agent was operating on another principal''s behalf. NULL for direct '
    'operations. Mirrors agent_sessions.delegated_from (migration 013).';

-- Down migration (paired, per design D8):
-- ALTER TABLE audit_log DROP COLUMN IF EXISTS delegated_from;
