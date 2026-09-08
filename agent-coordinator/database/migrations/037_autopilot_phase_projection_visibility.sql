-- 037: make Autopilot phase projections board-visible but never claimable.

BEGIN;

-- Remove historical overloads so every SQL caller reaches the one claim
-- implementation that enforces issue-row exclusion.
DROP FUNCTION IF EXISTS claim_task(TEXT, TEXT, TEXT[]);
DROP FUNCTION IF EXISTS claim_task(TEXT, TEXT, TEXT[], TEXT[], INTEGER);

CREATE OR REPLACE FUNCTION claim_task(
    p_agent_id TEXT,
    p_agent_type TEXT,
    p_task_types TEXT[] DEFAULT NULL,
    p_agent_archetypes TEXT[] DEFAULT NULL,
    p_agent_trust_level INTEGER DEFAULT NULL,
    p_exclude_submitted_by TEXT DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_task RECORD;
BEGIN
    SELECT * INTO v_task
    FROM work_queue
    WHERE status = 'pending'
      -- Issues are projection/display records, never executable work.
      AND task_type <> 'issue'
      AND (p_task_types IS NULL OR task_type = ANY(p_task_types))
      AND (depends_on IS NULL OR NOT EXISTS (
          SELECT 1 FROM work_queue dep
          WHERE dep.id = ANY(work_queue.depends_on)
          AND dep.status NOT IN ('completed')
      ))
      AND (
          agent_requirements IS NULL
          OR agent_requirements->>'archetype' IS NULL
          OR p_agent_archetypes IS NULL
          OR agent_requirements->>'archetype' = ANY(p_agent_archetypes)
      )
      AND (
          agent_requirements IS NULL
          OR (agent_requirements->>'min_trust_level') IS NULL
          OR p_agent_trust_level IS NULL
          OR p_agent_trust_level >= (agent_requirements->>'min_trust_level')::INTEGER
      )
      AND (
          p_exclude_submitted_by IS NULL
          OR input_data IS NULL
          OR input_data->>'submitted_by' IS DISTINCT FROM p_exclude_submitted_by
      )
    ORDER BY priority ASC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'reason', 'no_tasks_available');
    END IF;

    UPDATE work_queue
    SET status = 'claimed', claimed_by = p_agent_id, claimed_at = NOW(),
        attempt_count = attempt_count + 1
    WHERE id = v_task.id;

    RETURN jsonb_build_object(
        'success', true,
        'task_id', v_task.id,
        'task_type', v_task.task_type,
        'description', v_task.description,
        'input_data', v_task.input_data,
        'priority', v_task.priority,
        'deadline', v_task.deadline,
        'agent_requirements', v_task.agent_requirements
    );
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION notify_work_queue_change() RETURNS TRIGGER AS $$
DECLARE
    v_change_id TEXT;
    v_label TEXT;
BEGIN
    IF OLD.labels IS DISTINCT FROM NEW.labels
       AND (
          'projection:autopilot-phase' = ANY(COALESCE(NEW.labels, ARRAY[]::TEXT[]))
          OR 'projection:autopilot-phase' = ANY(COALESCE(OLD.labels, ARRAY[]::TEXT[]))
       )
    THEN
        -- Prefer the current correlation label, but removal must remain routable.
        FOREACH v_label IN ARRAY COALESCE(NEW.labels, ARRAY[]::TEXT[]) LOOP
            IF v_label LIKE 'change:%' THEN
                v_change_id := substr(v_label, 8);
                EXIT;
            END IF;
        END LOOP;
        IF v_change_id IS NULL THEN
            FOREACH v_label IN ARRAY COALESCE(OLD.labels, ARRAY[]::TEXT[]) LOOP
                IF v_label LIKE 'change:%' THEN
                    v_change_id := substr(v_label, 8);
                    EXIT;
                END IF;
            END LOOP;
        END IF;
        PERFORM coordinator_notify(
            'coordinator_task',
            'projection.labels_changed',
            NEW.id::TEXT,
            COALESCE(NEW.claimed_by, 'autopilot'),
            'Autopilot projection labels changed',
            v_change_id,
            jsonb_build_object('snapshot_required', true)
        );
    END IF;

    IF OLD.status IS DISTINCT FROM NEW.status
       AND NEW.status IN ('completed', 'failed', 'claimed', 'running', 'blocked')
    THEN
        v_change_id := NULL;
        FOREACH v_label IN ARRAY COALESCE(NEW.labels, ARRAY[]::TEXT[]) LOOP
            IF v_label LIKE 'change:%' THEN
                v_change_id := substr(v_label, 8);
                EXIT;
            END IF;
        END LOOP;
        PERFORM coordinator_notify(
            'coordinator_task',
            'task.' || NEW.status,
            NEW.id::TEXT,
            COALESCE(NEW.claimed_by, 'unknown'),
            'Task ' || NEW.status || ': ' || COALESCE(LEFT(NEW.description, 100), ''),
            v_change_id,
            jsonb_build_object('from_status', OLD.status, 'to_status', NEW.status)
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_work_queue_notify ON work_queue;
CREATE TRIGGER trg_work_queue_notify
    AFTER UPDATE ON work_queue
    FOR EACH ROW
    EXECUTE FUNCTION notify_work_queue_change();

COMMIT;
