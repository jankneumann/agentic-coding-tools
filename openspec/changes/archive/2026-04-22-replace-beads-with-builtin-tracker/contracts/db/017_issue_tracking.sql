-- Issue Tracking Extension for work_queue
-- Adds issue-specific columns to work_queue and creates issue_comments table

-- =============================================================================
-- WORK QUEUE EXTENSIONS: Issue tracking columns
-- =============================================================================

-- Labels for categorization and filtering
ALTER TABLE work_queue ADD COLUMN IF NOT EXISTS labels TEXT[] DEFAULT '{}';

-- Parent-child hierarchy (epics)
ALTER TABLE work_queue ADD COLUMN IF NOT EXISTS parent_id UUID REFERENCES work_queue(id);

-- Issue sub-type classification
ALTER TABLE work_queue ADD COLUMN IF NOT EXISTS issue_type TEXT DEFAULT 'task'
    CHECK (issue_type IN ('task', 'epic', 'bug', 'feature'));

-- Human assignee
ALTER TABLE work_queue ADD COLUMN IF NOT EXISTS assignee TEXT;

-- Closure tracking
ALTER TABLE work_queue ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
ALTER TABLE work_queue ADD COLUMN IF NOT EXISTS close_reason TEXT;

-- Extensible metadata
ALTER TABLE work_queue ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

-- Indexes for issue queries
CREATE INDEX IF NOT EXISTS idx_work_queue_labels ON work_queue USING GIN (labels);
CREATE INDEX IF NOT EXISTS idx_work_queue_parent ON work_queue(parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_work_queue_issue_type ON work_queue(issue_type);
CREATE INDEX IF NOT EXISTS idx_work_queue_assignee ON work_queue(assignee) WHERE assignee IS NOT NULL;

-- =============================================================================
-- ISSUE COMMENTS: Discussion thread per issue
-- =============================================================================

CREATE TABLE IF NOT EXISTS issue_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES work_queue(id) ON DELETE CASCADE,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_issue_comments_issue ON issue_comments(issue_id);
CREATE INDEX IF NOT EXISTS idx_issue_comments_created ON issue_comments(created_at);

-- RLS for issue_comments
ALTER TABLE issue_comments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow read access" ON issue_comments FOR SELECT USING (true);
CREATE POLICY "Service role full access" ON issue_comments
    FOR ALL USING (current_setting('role') = 'service_role');
