-- Migration 025: enrich NOTIFY payloads with change_id and from/to status
--
-- IMPL_REVIEW codex#4 + claude_code#8 (high behavioral_failure / contract_mismatch):
-- The SSE handler in event_stream.py filters incoming events by change_id:
--
--     if not evt.change_id or evt.change_id not in change_ids:
--         return
--
-- but neither work_queue nor audit_log triggers emit change_id in the NOTIFY
-- payload. As a result, evt.change_id is None for every live event, the
-- filter drops everything, and the SSE stream effectively delivers only the
-- initial snapshot — no live transition or audit events ever reach clients.
--
-- claude_code#8 (related): _make_transition reads `from_status`/`to_status`
-- from the event context, but the triggers don't populate either. The
-- resulting transition payload emits `from: ""` (empty string) and a `to`
-- value derived from `event_type.split('.')[-1]` which can be arbitrary.
--
-- This migration:
--   1. Extends coordinator_notify() with an optional context JSONB parameter
--      that lands inside the NOTIFY payload as `context` (alongside the
--      existing `change_id` top-level field).
--   2. Updates notify_work_queue_change() to compute change_id from
--      NEW.labels (the `change:<id>` prefix convention) and pass
--      {from_status, to_status} as context.
--   3. Updates notify_audit_log_change() to extract change_id from
--      NEW.parameters->>'change_id' (when present) and emit it.
--
-- All existing callers of coordinator_notify(channel, event_type, entity_id,
-- agent_id [, summary]) remain compatible — the new parameters are optional
-- with sensible defaults. Existing tests, watchdog, notifier, and other
-- triggers that don't pass change_id/context will continue to NOTIFY with
-- those fields as NULL/{} just as before.

-- 1. Extended coordinator_notify with optional change_id + context
CREATE OR REPLACE FUNCTION coordinator_notify(
    channel TEXT,
    event_type TEXT,
    entity_id TEXT,
    agent_id TEXT,
    summary TEXT DEFAULT '',
    change_id TEXT DEFAULT NULL,
    context JSONB DEFAULT '{}'::jsonb
) RETURNS VOID AS $$
BEGIN
    -- Skip if this is an internal coordinator operation
    IF current_setting('app.coordinator_internal', true) = 'true' THEN
        RETURN;
    END IF;

    PERFORM pg_notify(channel, json_build_object(
        'event_type', event_type,
        'channel', channel,
        'entity_id', entity_id,
        'agent_id', agent_id,
        'urgency', CASE
            WHEN event_type IN ('approval.submitted', 'agent.stale') THEN 'high'
            WHEN event_type IN ('task.completed', 'task.failed', 'approval.decided', 'approval.reminder') THEN 'medium'
            ELSE 'low'
        END,
        'summary', LEFT(summary, 200),
        'timestamp', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
        'change_id', change_id,
        'context', context
    )::text);
END;
$$ LANGUAGE plpgsql;


-- 2. Work queue trigger: compute change_id from labels, pass from/to status
CREATE OR REPLACE FUNCTION notify_work_queue_change() RETURNS TRIGGER AS $$
DECLARE
    v_change_id TEXT;
    v_label TEXT;
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.status IS DISTINCT FROM NEW.status THEN
        IF NEW.status IN ('completed', 'failed', 'claimed', 'running', 'blocked') THEN
            -- Extract change_id from NEW.labels (first label of form 'change:<id>')
            v_change_id := NULL;
            IF NEW.labels IS NOT NULL THEN
                FOREACH v_label IN ARRAY NEW.labels LOOP
                    IF v_label LIKE 'change:%' THEN
                        v_change_id := substr(v_label, 8); -- strip 'change:' prefix
                        EXIT;
                    END IF;
                END LOOP;
            END IF;

            PERFORM coordinator_notify(
                'coordinator_task',
                'task.' || NEW.status,
                NEW.id::text,
                COALESCE(NEW.claimed_by, 'unknown'),
                CASE NEW.status
                    WHEN 'completed' THEN 'Task completed: '
                    WHEN 'failed' THEN 'Task failed: '
                    WHEN 'claimed' THEN 'Task claimed: '
                    WHEN 'running' THEN 'Task running: '
                    WHEN 'blocked' THEN 'Task blocked: '
                END || COALESCE(LEFT(NEW.description, 100), ''),
                v_change_id,
                jsonb_build_object(
                    'from_status', OLD.status,
                    'to_status', NEW.status
                )
            );
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Re-bind trigger to the updated function (function body changed, not signature)
DROP TRIGGER IF EXISTS trg_work_queue_notify ON work_queue;
CREATE TRIGGER trg_work_queue_notify
    AFTER UPDATE ON work_queue
    FOR EACH ROW
    EXECUTE FUNCTION notify_work_queue_change();


-- 3. Audit-log trigger: extract change_id from parameters JSONB when present
CREATE OR REPLACE FUNCTION notify_audit_log_change() RETURNS TRIGGER AS $$
DECLARE
    v_change_id TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- audit_log.parameters is JSONB and may carry change_id under
        -- 'change_id' or 'target_change_id'; check both for compatibility
        -- with both kick_agent (target_change_id) and write_audit_event
        -- (change_id) call sites.
        IF NEW.parameters IS NOT NULL THEN
            v_change_id := NEW.parameters->>'change_id';
            IF v_change_id IS NULL THEN
                v_change_id := NEW.parameters->>'target_change_id';
            END IF;
        END IF;

        PERFORM coordinator_notify(
            'coordinator_audit',
            'audit.logged',
            NEW.id::text,
            COALESCE(NEW.agent_id, 'unknown'),
            COALESCE(NEW.operation, 'unknown'),
            v_change_id,
            jsonb_build_object(
                'operation', NEW.operation,
                'args_summary',
                    COALESCE(LEFT(NEW.parameters::text, 200), '')
            )
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
