-- Extended Schema: Agent Memory and Coordination
-- Supports both cloud and local agents with appropriate access controls

-- =============================================================================
-- FILE LOCKS: Prevent concurrent edits
-- =============================================================================

CREATE TABLE file_locks (
    file_path TEXT PRIMARY KEY,
    locked_by TEXT NOT NULL,          -- agent_id
    agent_type TEXT NOT NULL,         -- claude_code, codex, gemini_jules, etc.
    session_id TEXT,                  -- Link to agent_sessions
    locked_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '30 minutes'),
    lock_reason TEXT,
    
    -- Metadata for debugging
    lock_context JSONB DEFAULT '{}'   -- What task is the agent working on?
);

CREATE INDEX idx_file_locks_agent ON file_locks(locked_by);
CREATE INDEX idx_file_locks_expires ON file_locks(expires_at);

-- =============================================================================
-- AGENT MEMORY: Three-layer cognitive architecture (like CM)
-- =============================================================================

-- Episodic Memory: Specific experiences and their outcomes
CREATE TABLE memory_episodic (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    session_id TEXT,
    
    -- What happened
    event_type TEXT NOT NULL,         -- 'task_completed', 'error_resolved', 'discovery'
    summary TEXT NOT NULL,            -- Brief description
    details JSONB,                    -- Full context
    
    -- Outcome tracking
    outcome TEXT,                     -- 'success', 'failure', 'partial'
    lessons_learned TEXT[],           -- Extracted insights
    
    -- Retrieval metadata
    embedding VECTOR(384),            -- For semantic search (if using pgvector)
    tags TEXT[],
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    relevance_score FLOAT DEFAULT 1.0 -- Decays over time
);

CREATE INDEX idx_memory_episodic_agent ON memory_episodic(agent_id);
CREATE INDEX idx_memory_episodic_type ON memory_episodic(event_type);
CREATE INDEX idx_memory_episodic_tags ON memory_episodic USING GIN(tags);

-- Working Memory: Active context for current tasks
CREATE TABLE memory_working (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    
    -- Current task context
    task_id TEXT,
    task_description TEXT,
    relevant_files TEXT[],
    
    -- Accumulated context (compressed periodically)
    context_items JSONB DEFAULT '[]', -- Array of {type, content, timestamp}
    total_tokens INTEGER DEFAULT 0,
    max_tokens INTEGER DEFAULT 8000,  -- Budget before compression
    
    -- State
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'completed')),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '24 hours')
);

CREATE INDEX idx_memory_working_agent ON memory_working(agent_id);
CREATE INDEX idx_memory_working_session ON memory_working(session_id);
CREATE INDEX idx_memory_working_status ON memory_working(status);

-- Procedural Memory: Learned skills and patterns
CREATE TABLE memory_procedural (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Skill identification
    skill_name TEXT NOT NULL,
    skill_category TEXT,              -- 'code_pattern', 'debugging', 'refactoring', etc.
    
    -- The actual skill content
    description TEXT NOT NULL,
    trigger_conditions TEXT[],        -- When to apply this skill
    steps JSONB,                      -- How to execute
    example_applications JSONB,       -- Past successful uses
    
    -- Effectiveness tracking (Thompson sampling style)
    times_suggested INTEGER DEFAULT 0,
    times_successful INTEGER DEFAULT 0,
    success_rate FLOAT GENERATED ALWAYS AS (
        CASE WHEN times_suggested > 0 
        THEN times_successful::FLOAT / times_suggested 
        ELSE 0.5 END
    ) STORED,
    
    -- Metadata
    source TEXT,                      -- 'manual', 'extracted', 'learned'
    created_by TEXT,                  -- agent_id or 'system'
    tags TEXT[],
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_memory_procedural_category ON memory_procedural(skill_category);
CREATE INDEX idx_memory_procedural_tags ON memory_procedural USING GIN(tags);
CREATE INDEX idx_memory_procedural_success ON memory_procedural(success_rate DESC);

-- =============================================================================
-- WORK QUEUE: Task assignment for agents
-- =============================================================================

CREATE TABLE work_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Task definition
    task_type TEXT NOT NULL,          -- 'summarize', 'refactor', 'test', 'verify'
    task_description TEXT NOT NULL,
    input_data JSONB,                 -- Task-specific input
    
    -- Assignment
    assigned_to TEXT,                 -- agent_id (null = unassigned)
    assigned_at TIMESTAMPTZ,
    preferred_agent_type TEXT,        -- Hint for assignment
    
    -- Priority and dependencies
    priority INTEGER DEFAULT 5,       -- 1=highest, 10=lowest
    depends_on UUID[],                -- Other work_queue IDs that must complete first
    
    -- Status
    status TEXT DEFAULT 'pending' CHECK (
        status IN ('pending', 'assigned', 'running', 'completed', 'failed', 'cancelled')
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
CREATE INDEX idx_work_queue_assigned ON work_queue(assigned_to);
CREATE INDEX idx_work_queue_priority ON work_queue(priority, created_at);

-- =============================================================================
-- NEWSLETTER-SPECIFIC: Processing state
-- =============================================================================

CREATE TABLE newsletter_processing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Source
    gmail_message_id TEXT UNIQUE,
    sender TEXT,
    subject TEXT,
    received_at TIMESTAMPTZ,
    
    -- Content
    raw_content TEXT,
    parsed_content JSONB,             -- Structured extraction
    
    -- Processing stages
    fetch_status TEXT DEFAULT 'pending',
    parse_status TEXT DEFAULT 'pending', 
    summarize_status TEXT DEFAULT 'pending',
    
    -- Results
    haiku_summary TEXT,
    haiku_tokens_used INTEGER,
    processing_agent TEXT,            -- Which agent processed this
    
    -- Timing
    fetched_at TIMESTAMPTZ,
    parsed_at TIMESTAMPTZ,
    summarized_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_newsletter_received ON newsletter_processing(received_at DESC);
CREATE INDEX idx_newsletter_status ON newsletter_processing(summarize_status);

-- Weekly synthesis tracking
CREATE TABLE weekly_synthesis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    
    -- Input
    newsletter_ids UUID[],            -- References to newsletter_processing
    newsletter_count INTEGER,
    
    -- Processing
    synthesis_agent TEXT,             -- Usually 'sonnet'
    synthesis_prompt_tokens INTEGER,
    synthesis_output_tokens INTEGER,
    
    -- Output
    executive_summary TEXT,
    key_themes JSONB,
    strategic_implications JSONB,
    
    -- Approval workflow
    draft_created_at TIMESTAMPTZ,
    human_reviewed_by TEXT,
    human_reviewed_at TIMESTAMPTZ,
    approved BOOLEAN,
    final_version TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(week_start)
);

-- =============================================================================
-- ROW LEVEL SECURITY: Cloud vs Local access
-- =============================================================================

-- Cloud agents get anon key (read-only for most tables)
-- Local agents/Coordination API get service_role key (full access)

ALTER TABLE file_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_episodic ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_working ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_procedural ENABLE ROW LEVEL SECURITY;
ALTER TABLE work_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE newsletter_processing ENABLE ROW LEVEL SECURITY;

-- Read policies (anon can read)
CREATE POLICY "anon_read" ON file_locks FOR SELECT USING (true);
CREATE POLICY "anon_read" ON memory_episodic FOR SELECT USING (true);
CREATE POLICY "anon_read" ON memory_working FOR SELECT USING (true);
CREATE POLICY "anon_read" ON memory_procedural FOR SELECT USING (true);
CREATE POLICY "anon_read" ON work_queue FOR SELECT USING (true);
CREATE POLICY "anon_read" ON newsletter_processing FOR SELECT USING (true);

-- Write policies (service_role only)
CREATE POLICY "service_write" ON file_locks FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_write" ON memory_episodic FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_write" ON memory_working FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_write" ON memory_procedural FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_write" ON work_queue FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_write" ON newsletter_processing FOR ALL USING (auth.role() = 'service_role');

-- =============================================================================
-- FUNCTIONS: Coordination API helpers
-- =============================================================================

-- Atomic lock acquisition with policy checks
CREATE FUNCTION acquire_file_lock(
    p_file_path TEXT,
    p_agent_id TEXT,
    p_agent_type TEXT,
    p_session_id TEXT DEFAULT NULL,
    p_reason TEXT DEFAULT NULL,
    p_ttl_minutes INTEGER DEFAULT 30
) RETURNS JSONB AS $$
DECLARE
    v_existing RECORD;
    v_result JSONB;
BEGIN
    -- Clean up expired locks
    DELETE FROM file_locks WHERE expires_at < NOW();
    
    -- Check for existing lock
    SELECT * INTO v_existing FROM file_locks WHERE file_path = p_file_path;
    
    IF FOUND THEN
        -- Lock exists - check if same agent (allow refresh)
        IF v_existing.locked_by = p_agent_id THEN
            UPDATE file_locks 
            SET expires_at = NOW() + (p_ttl_minutes || ' minutes')::INTERVAL
            WHERE file_path = p_file_path;
            
            RETURN jsonb_build_object(
                'success', true,
                'action', 'refreshed',
                'expires_at', NOW() + (p_ttl_minutes || ' minutes')::INTERVAL
            );
        ELSE
            RETURN jsonb_build_object(
                'success', false,
                'reason', 'locked_by_other',
                'locked_by', v_existing.locked_by,
                'locked_at', v_existing.locked_at,
                'expires_at', v_existing.expires_at
            );
        END IF;
    END IF;
    
    -- No existing lock - acquire
    INSERT INTO file_locks (file_path, locked_by, agent_type, session_id, lock_reason, expires_at)
    VALUES (
        p_file_path, 
        p_agent_id, 
        p_agent_type, 
        p_session_id, 
        p_reason,
        NOW() + (p_ttl_minutes || ' minutes')::INTERVAL
    );
    
    RETURN jsonb_build_object(
        'success', true,
        'action', 'acquired',
        'expires_at', NOW() + (p_ttl_minutes || ' minutes')::INTERVAL
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Claim work from queue (atomic)
CREATE FUNCTION claim_work(
    p_agent_id TEXT,
    p_agent_type TEXT,
    p_task_types TEXT[] DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_task RECORD;
BEGIN
    -- Find highest priority unassigned task that this agent can handle
    SELECT * INTO v_task
    FROM work_queue
    WHERE status = 'pending'
      AND (p_task_types IS NULL OR task_type = ANY(p_task_types))
      AND (preferred_agent_type IS NULL OR preferred_agent_type = p_agent_type)
      AND (depends_on IS NULL OR NOT EXISTS (
          SELECT 1 FROM work_queue dep 
          WHERE dep.id = ANY(work_queue.depends_on) 
          AND dep.status != 'completed'
      ))
    ORDER BY priority, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1;
    
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'reason', 'no_work_available');
    END IF;
    
    -- Claim it
    UPDATE work_queue
    SET 
        status = 'assigned',
        assigned_to = p_agent_id,
        assigned_at = NOW(),
        attempt_count = attempt_count + 1
    WHERE id = v_task.id;
    
    RETURN jsonb_build_object(
        'success', true,
        'task_id', v_task.id,
        'task_type', v_task.task_type,
        'task_description', v_task.task_description,
        'input_data', v_task.input_data,
        'deadline', v_task.deadline
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Store episodic memory with deduplication
CREATE FUNCTION store_episodic_memory(
    p_agent_id TEXT,
    p_session_id TEXT,
    p_event_type TEXT,
    p_summary TEXT,
    p_details JSONB DEFAULT NULL,
    p_outcome TEXT DEFAULT NULL,
    p_lessons TEXT[] DEFAULT NULL,
    p_tags TEXT[] DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_existing UUID;
    v_new_id UUID;
BEGIN
    -- Check for very similar recent memory (dedup)
    SELECT id INTO v_existing
    FROM memory_episodic
    WHERE agent_id = p_agent_id
      AND event_type = p_event_type
      AND summary = p_summary  -- Exact match (could use similarity for fuzzy)
      AND created_at > NOW() - INTERVAL '1 hour';
    
    IF FOUND THEN
        -- Update existing rather than create duplicate
        UPDATE memory_episodic
        SET 
            details = COALESCE(p_details, details),
            outcome = COALESCE(p_outcome, outcome),
            lessons_learned = COALESCE(p_lessons, lessons_learned),
            relevance_score = 1.0  -- Refresh relevance
        WHERE id = v_existing;
        
        RETURN v_existing;
    END IF;
    
    -- Create new memory
    INSERT INTO memory_episodic (
        agent_id, session_id, event_type, summary, details, 
        outcome, lessons_learned, tags
    ) VALUES (
        p_agent_id, p_session_id, p_event_type, p_summary, p_details,
        p_outcome, p_lessons, p_tags
    ) RETURNING id INTO v_new_id;
    
    RETURN v_new_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Retrieve relevant memories for a task
CREATE FUNCTION get_relevant_memories(
    p_agent_id TEXT,
    p_task_description TEXT,
    p_tags TEXT[] DEFAULT NULL,
    p_limit INTEGER DEFAULT 10
) RETURNS TABLE (
    memory_type TEXT,
    content JSONB,
    relevance FLOAT
) AS $$
BEGIN
    -- Episodic memories (recent experiences)
    RETURN QUERY
    SELECT 
        'episodic'::TEXT,
        jsonb_build_object(
            'event_type', e.event_type,
            'summary', e.summary,
            'outcome', e.outcome,
            'lessons', e.lessons_learned
        ),
        e.relevance_score * (1.0 - EXTRACT(EPOCH FROM (NOW() - e.created_at)) / 604800.0)  -- Decay over week
    FROM memory_episodic e
    WHERE e.agent_id = p_agent_id
      AND (p_tags IS NULL OR e.tags && p_tags)
    ORDER BY relevance_score DESC, created_at DESC
    LIMIT p_limit / 2;
    
    -- Procedural memories (skills)
    RETURN QUERY
    SELECT 
        'procedural'::TEXT,
        jsonb_build_object(
            'skill_name', p.skill_name,
            'description', p.description,
            'steps', p.steps,
            'success_rate', p.success_rate
        ),
        p.success_rate
    FROM memory_procedural p
    WHERE p.tags IS NULL OR p.tags && p_tags
    ORDER BY success_rate DESC
    LIMIT p_limit / 2;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- REALTIME SUBSCRIPTIONS
-- =============================================================================

ALTER PUBLICATION supabase_realtime ADD TABLE work_queue;
ALTER PUBLICATION supabase_realtime ADD TABLE file_locks;
ALTER PUBLICATION supabase_realtime ADD TABLE newsletter_processing;
