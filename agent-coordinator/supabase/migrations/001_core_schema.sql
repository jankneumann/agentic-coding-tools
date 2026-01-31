-- Agent Coordinator Core Schema (Phase 1 MVP)
-- File locking + work queue for local agent coordination via MCP

-- =============================================================================
-- FILE LOCKS: Prevent concurrent edits to same files
-- =============================================================================

CREATE TABLE file_locks (
    file_path TEXT PRIMARY KEY,
    locked_by TEXT NOT NULL,           -- agent_id
    agent_type TEXT NOT NULL,          -- claude_code, codex, gemini_jules, etc.
    session_id TEXT,                   -- Optional link to agent_sessions
    locked_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    reason TEXT,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_file_locks_agent ON file_locks(locked_by);
CREATE INDEX idx_file_locks_expires ON file_locks(expires_at);
CREATE INDEX idx_file_locks_session ON file_locks(session_id);


-- =============================================================================
-- WORK QUEUE: Task assignment and tracking
-- =============================================================================

CREATE TABLE work_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Task definition
    task_type TEXT NOT NULL,           -- 'summarize', 'refactor', 'test', 'verify'
    description TEXT NOT NULL,
    input_data JSONB,                  -- Task-specific input

    -- Assignment
    claimed_by TEXT,                   -- agent_id (null = unclaimed)
    claimed_at TIMESTAMPTZ,

    -- Priority and dependencies
    priority INTEGER DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),
    depends_on UUID[],                 -- Other work_queue IDs that must complete first

    -- Status
    status TEXT DEFAULT 'pending' CHECK (
        status IN ('pending', 'claimed', 'running', 'completed', 'failed', 'cancelled')
    ),

    -- Results
    result JSONB,
    error_message TEXT,

    -- Timing
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    deadline TIMESTAMPTZ,

    -- Retry handling
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3
);

CREATE INDEX idx_work_queue_status ON work_queue(status);
CREATE INDEX idx_work_queue_claimed ON work_queue(claimed_by);
CREATE INDEX idx_work_queue_priority ON work_queue(priority, created_at);
CREATE INDEX idx_work_queue_pending ON work_queue(status, priority, created_at)
    WHERE status = 'pending';


-- =============================================================================
-- AGENT SESSIONS: Track agent work sessions for correlation
-- =============================================================================

CREATE TABLE agent_sessions (
    id TEXT PRIMARY KEY,               -- Session ID (from environment or generated)
    agent_id TEXT NOT NULL,
    agent_type TEXT NOT NULL,

    -- Session info
    task_description TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,

    -- Metrics
    tasks_completed INTEGER DEFAULT 0,
    files_modified TEXT[] DEFAULT '{}',

    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_agent_sessions_agent ON agent_sessions(agent_id);
CREATE INDEX idx_agent_sessions_type ON agent_sessions(agent_type);
CREATE INDEX idx_agent_sessions_started ON agent_sessions(started_at DESC);


-- =============================================================================
-- FUNCTIONS: Atomic operations for coordination
-- =============================================================================

-- Acquire a file lock with automatic cleanup of expired locks
CREATE OR REPLACE FUNCTION acquire_lock(
    p_file_path TEXT,
    p_agent_id TEXT,
    p_agent_type TEXT,
    p_session_id TEXT DEFAULT NULL,
    p_reason TEXT DEFAULT NULL,
    p_ttl_minutes INTEGER DEFAULT 120
) RETURNS JSONB AS $$
DECLARE
    v_existing RECORD;
    v_expires_at TIMESTAMPTZ;
BEGIN
    -- Clean up expired locks first
    DELETE FROM file_locks WHERE expires_at < NOW();

    -- Calculate new expiry
    v_expires_at := NOW() + (p_ttl_minutes || ' minutes')::INTERVAL;

    -- Try to acquire via INSERT (handles concurrent races via ON CONFLICT)
    INSERT INTO file_locks (file_path, locked_by, agent_type, session_id, expires_at, reason)
    VALUES (p_file_path, p_agent_id, p_agent_type, p_session_id, v_expires_at, p_reason)
    ON CONFLICT (file_path) DO NOTHING;

    IF FOUND THEN
        RETURN jsonb_build_object(
            'success', true,
            'action', 'acquired',
            'file_path', p_file_path,
            'expires_at', v_expires_at
        );
    END IF;

    -- Lock exists (INSERT conflicted) - check ownership for refresh vs conflict
    SELECT * INTO v_existing FROM file_locks WHERE file_path = p_file_path FOR UPDATE;

    IF v_existing.locked_by = p_agent_id THEN
        -- Same agent - refresh the lock
        UPDATE file_locks
        SET
            expires_at = v_expires_at,
            reason = COALESCE(p_reason, reason)
        WHERE file_path = p_file_path;

        RETURN jsonb_build_object(
            'success', true,
            'action', 'refreshed',
            'file_path', p_file_path,
            'expires_at', v_expires_at
        );
    ELSE
        -- Locked by another agent
        RETURN jsonb_build_object(
            'success', false,
            'reason', 'locked_by_other',
            'locked_by', v_existing.locked_by,
            'agent_type', v_existing.agent_type,
            'locked_at', v_existing.locked_at,
            'expires_at', v_existing.expires_at,
            'lock_reason', v_existing.reason
        );
    END IF;
END;
$$ LANGUAGE plpgsql;


-- Release a file lock (only if owned by the requesting agent)
CREATE OR REPLACE FUNCTION release_lock(
    p_file_path TEXT,
    p_agent_id TEXT
) RETURNS JSONB AS $$
DECLARE
    v_deleted INTEGER;
BEGIN
    DELETE FROM file_locks
    WHERE file_path = p_file_path AND locked_by = p_agent_id;

    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    IF v_deleted > 0 THEN
        RETURN jsonb_build_object(
            'success', true,
            'action', 'released',
            'file_path', p_file_path
        );
    ELSE
        RETURN jsonb_build_object(
            'success', false,
            'reason', 'lock_not_found_or_not_owner'
        );
    END IF;
END;
$$ LANGUAGE plpgsql;


-- Claim a task from the work queue (atomic, prevents double-claiming)
CREATE OR REPLACE FUNCTION claim_task(
    p_agent_id TEXT,
    p_agent_type TEXT,
    p_task_types TEXT[] DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_task RECORD;
BEGIN
    -- Find highest priority unclaimed task that:
    -- 1. Matches requested task types (if specified)
    -- 2. Has no unfinished dependencies
    SELECT * INTO v_task
    FROM work_queue
    WHERE status = 'pending'
      AND (p_task_types IS NULL OR task_type = ANY(p_task_types))
      AND (depends_on IS NULL OR NOT EXISTS (
          SELECT 1 FROM work_queue dep
          WHERE dep.id = ANY(work_queue.depends_on)
          AND dep.status NOT IN ('completed')
      ))
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
        'deadline', v_task.deadline
    );
END;
$$ LANGUAGE plpgsql;


-- Complete a task (success or failure)
CREATE OR REPLACE FUNCTION complete_task(
    p_task_id UUID,
    p_agent_id TEXT,
    p_success BOOLEAN,
    p_result JSONB DEFAULT NULL,
    p_error_message TEXT DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_status TEXT;
    v_updated INTEGER;
BEGIN
    v_status := CASE WHEN p_success THEN 'completed' ELSE 'failed' END;

    UPDATE work_queue
    SET
        status = v_status,
        result = p_result,
        error_message = p_error_message,
        completed_at = NOW()
    WHERE id = p_task_id AND claimed_by = p_agent_id;

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    IF v_updated > 0 THEN
        RETURN jsonb_build_object(
            'success', true,
            'status', v_status,
            'task_id', p_task_id
        );
    ELSE
        RETURN jsonb_build_object(
            'success', false,
            'reason', 'task_not_found_or_not_claimed_by_agent'
        );
    END IF;
END;
$$ LANGUAGE plpgsql;


-- Submit a new task to the work queue
CREATE OR REPLACE FUNCTION submit_task(
    p_task_type TEXT,
    p_description TEXT,
    p_input_data JSONB DEFAULT NULL,
    p_priority INTEGER DEFAULT 5,
    p_depends_on UUID[] DEFAULT NULL,
    p_deadline TIMESTAMPTZ DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_task_id UUID;
BEGIN
    INSERT INTO work_queue (task_type, description, input_data, priority, depends_on, deadline)
    VALUES (p_task_type, p_description, p_input_data, p_priority, p_depends_on, p_deadline)
    RETURNING id INTO v_task_id;

    RETURN jsonb_build_object(
        'success', true,
        'task_id', v_task_id
    );
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- ROW LEVEL SECURITY
-- =============================================================================

ALTER TABLE file_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE work_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_sessions ENABLE ROW LEVEL SECURITY;

-- Read access for all authenticated users
CREATE POLICY "Allow read access" ON file_locks FOR SELECT USING (true);
CREATE POLICY "Allow read access" ON work_queue FOR SELECT USING (true);
CREATE POLICY "Allow read access" ON agent_sessions FOR SELECT USING (true);

-- Service role has full access (for MCP server and API)
CREATE POLICY "Service role full access" ON file_locks
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON work_queue
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON agent_sessions
    FOR ALL USING (auth.role() = 'service_role');


-- =============================================================================
-- REALTIME SUBSCRIPTIONS (for dashboards and notifications)
-- =============================================================================

ALTER PUBLICATION supabase_realtime ADD TABLE file_locks;
ALTER PUBLICATION supabase_realtime ADD TABLE work_queue;
