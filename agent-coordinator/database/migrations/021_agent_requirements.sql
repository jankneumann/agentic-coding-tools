-- Migration: Add agent_requirements column to work_queue table
-- Enables archetype-aware task routing (Phase 3 of specialized-workflow-agents)
--
-- The agent_requirements JSONB column stores optional routing constraints:
--   { "archetype": "implementer", "min_trust_level": 3 }
--
-- When present, claim_task() filters by these requirements.
-- When absent, any agent can claim (backward compatible).

ALTER TABLE work_queue ADD COLUMN IF NOT EXISTS
    agent_requirements JSONB;

-- Index for efficient archetype filtering during claim
CREATE INDEX IF NOT EXISTS idx_work_queue_archetype
    ON work_queue ((agent_requirements->>'archetype'))
    WHERE agent_requirements IS NOT NULL;

-- Update claim_task to support agent_requirements filtering
CREATE OR REPLACE FUNCTION claim_task(
    p_agent_id TEXT,
    p_agent_type TEXT,
    p_task_types TEXT[] DEFAULT NULL,
    p_agent_archetypes TEXT[] DEFAULT NULL,
    p_agent_trust_level INTEGER DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_task RECORD;
BEGIN
    -- Find highest priority unclaimed task that:
    -- 1. Matches requested task types (if specified)
    -- 2. Has no unfinished dependencies
    -- 3. Matches agent archetype capabilities (if task has requirements)
    -- 4. Agent meets minimum trust level (if task has requirements)
    SELECT * INTO v_task
    FROM work_queue
    WHERE status = 'pending'
      AND (p_task_types IS NULL OR task_type = ANY(p_task_types))
      AND (depends_on IS NULL OR NOT EXISTS (
          SELECT 1 FROM work_queue dep
          WHERE dep.id = ANY(work_queue.depends_on)
          AND dep.status NOT IN ('completed')
      ))
      -- Archetype filtering: skip tasks requiring an archetype the agent doesn't support
      AND (
          agent_requirements IS NULL
          OR agent_requirements->>'archetype' IS NULL
          OR p_agent_archetypes IS NULL  -- agents without declared archetypes can claim anything
          OR agent_requirements->>'archetype' = ANY(p_agent_archetypes)
      )
      -- Trust level filtering: skip tasks requiring higher trust than the agent has
      AND (
          agent_requirements IS NULL
          OR (agent_requirements->>'min_trust_level') IS NULL
          OR p_agent_trust_level IS NULL  -- agents without trust level can claim anything
          OR p_agent_trust_level >= (agent_requirements->>'min_trust_level')::INTEGER
      )
    ORDER BY priority ASC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'reason', 'no_tasks_available'
        );
    END IF;

    -- Claim the task
    UPDATE work_queue
    SET
        status = 'claimed',
        claimed_by = p_agent_id,
        claimed_at = NOW(),
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

-- Update submit_task to accept agent_requirements
CREATE OR REPLACE FUNCTION submit_task(
    p_task_type TEXT,
    p_description TEXT,
    p_input_data JSONB DEFAULT NULL,
    p_priority INTEGER DEFAULT 5,
    p_depends_on UUID[] DEFAULT NULL,
    p_deadline TIMESTAMPTZ DEFAULT NULL,
    p_agent_requirements JSONB DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_task_id UUID;
BEGIN
    INSERT INTO work_queue (task_type, description, input_data, priority, depends_on, deadline, agent_requirements)
    VALUES (p_task_type, p_description, p_input_data, p_priority, p_depends_on, p_deadline, p_agent_requirements)
    RETURNING id INTO v_task_id;

    RETURN jsonb_build_object(
        'success', true,
        'task_id', v_task_id
    );
END;
$$ LANGUAGE plpgsql;
