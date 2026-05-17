-- Migration 024: coordinator_audit NOTIFY trigger
-- Adds a NOTIFY trigger on audit_log emitting to the new coordinator_audit
-- channel. Mirrors the existing trg_work_queue_notify pattern from
-- migration 015_notification_triggers.sql.
--
-- The coordinator_notify() helper is already installed by migration 015 and
-- is idempotently redefined there via CREATE OR REPLACE. No change needed.
--
-- Skips NOTIFY when current_setting('app.coordinator_internal') = 'true'
-- (same skip flag as all other triggers) to prevent self-notification loops.

CREATE OR REPLACE FUNCTION notify_audit_log_change() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM coordinator_notify(
            'coordinator_audit',
            'audit.logged',
            NEW.id::text,
            COALESCE(NEW.agent_id, 'unknown'),
            COALESCE(NEW.operation, 'unknown')
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_log_notify ON audit_log;
CREATE TRIGGER trg_audit_log_notify
    AFTER INSERT ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION notify_audit_log_change();
