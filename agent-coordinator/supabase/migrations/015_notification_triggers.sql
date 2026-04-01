-- Notification triggers for the coordinator event bus.
-- Emits NOTIFY on INSERT/UPDATE to approval_queue, work_queue, and agent_discovery.
-- Skips NOTIFY when current_setting('app.coordinator_internal') = 'true'
-- to prevent self-notification loops from watchdog/notifier actions.

-- Helper: build JSON payload and emit NOTIFY, respecting coordinator_internal flag.
CREATE OR REPLACE FUNCTION coordinator_notify(
    channel TEXT,
    event_type TEXT,
    entity_id TEXT,
    agent_id TEXT,
    summary TEXT DEFAULT ''
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
        'timestamp', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    )::text);
END;
$$ LANGUAGE plpgsql;


-- Approval queue trigger
CREATE OR REPLACE FUNCTION notify_approval_queue_change() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM coordinator_notify(
            'coordinator_approval',
            'approval.submitted',
            NEW.id::text,
            COALESCE(NEW.agent_id, 'unknown'),
            'Approval needed: ' || COALESCE(NEW.operation, 'unknown operation')
        );
    ELSIF TG_OP = 'UPDATE' AND OLD.status IS DISTINCT FROM NEW.status THEN
        IF NEW.status IN ('approved', 'denied') THEN
            PERFORM coordinator_notify(
                'coordinator_approval',
                'approval.decided',
                NEW.id::text,
                COALESCE(NEW.agent_id, 'unknown'),
                'Approval ' || NEW.status || ': ' || COALESCE(NEW.operation, '')
            );
        ELSIF NEW.status = 'expired' THEN
            PERFORM coordinator_notify(
                'coordinator_approval',
                'approval.expired',
                NEW.id::text,
                COALESCE(NEW.agent_id, 'unknown'),
                'Approval expired: ' || COALESCE(NEW.operation, '')
            );
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_approval_queue_notify ON approval_queue;
CREATE TRIGGER trg_approval_queue_notify
    AFTER INSERT OR UPDATE ON approval_queue
    FOR EACH ROW
    EXECUTE FUNCTION notify_approval_queue_change();


-- Work queue trigger
CREATE OR REPLACE FUNCTION notify_work_queue_change() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.status IS DISTINCT FROM NEW.status THEN
        IF NEW.status IN ('completed', 'failed', 'claimed') THEN
            PERFORM coordinator_notify(
                'coordinator_task',
                'task.' || NEW.status,
                NEW.id::text,
                COALESCE(NEW.claimed_by, 'unknown'),
                CASE NEW.status
                    WHEN 'completed' THEN 'Task completed: '
                    WHEN 'failed' THEN 'Task failed: '
                    WHEN 'claimed' THEN 'Task claimed: '
                END || COALESCE(LEFT(NEW.description, 100), '')
            );
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_work_queue_notify ON work_queue;
CREATE TRIGGER trg_work_queue_notify
    AFTER UPDATE ON work_queue
    FOR EACH ROW
    EXECUTE FUNCTION notify_work_queue_change();


-- Agent discovery trigger
CREATE OR REPLACE FUNCTION notify_agent_discovery_change() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM coordinator_notify(
            'coordinator_agent',
            'agent.registered',
            NEW.agent_id,
            NEW.agent_id,
            'Agent registered: ' || NEW.agent_id || ' (' || COALESCE(NEW.agent_type, 'unknown') || ')'
        );
    ELSIF TG_OP = 'UPDATE' AND OLD.status IS DISTINCT FROM NEW.status THEN
        PERFORM coordinator_notify(
            'coordinator_agent',
            'agent.' || NEW.status,
            NEW.agent_id,
            NEW.agent_id,
            'Agent ' || NEW.status || ': ' || NEW.agent_id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_discovery_notify ON agent_sessions;
CREATE TRIGGER trg_agent_discovery_notify
    AFTER INSERT OR UPDATE ON agent_sessions
    FOR EACH ROW
    EXECUTE FUNCTION notify_agent_discovery_change();
