-- Seed data for Agent Coordinator — Live Service Testing
-- Idempotent: all INSERTs use ON CONFLICT DO NOTHING
-- Run after migrations to populate representative test fixtures.
--
-- Tables seeded (7 cleanable tables from conftest.py):
--   agent_sessions, file_locks, work_queue,
--   memory_episodic, memory_working, memory_procedural,
--   handoff_documents

-- =============================================================================
-- AGENT SESSIONS (2 minimum)
-- =============================================================================

INSERT INTO agent_sessions (id, agent_id, agent_type, task_description, metadata)
VALUES
    ('seed-session-1', 'seed-agent-1', 'claude_code', 'Seed session for live service testing', '{"seed": true}'),
    ('seed-session-2', 'seed-agent-2', 'codex', 'Secondary seed session for multi-agent testing', '{"seed": true}')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- FILE LOCKS (1 active)
-- =============================================================================

INSERT INTO file_locks (file_path, locked_by, agent_type, session_id, expires_at, reason, metadata)
VALUES
    ('test/seed-lock.txt', 'seed-agent-1', 'claude_code', 'seed-session-1', NOW() + INTERVAL '2 hours', 'Seed lock for live service testing', '{"seed": true}')
ON CONFLICT (file_path) DO NOTHING;

-- =============================================================================
-- WORK QUEUE (2 items: 1 pending, 1 claimed)
-- =============================================================================

INSERT INTO work_queue (id, task_type, description, priority, status, input_data)
VALUES
    ('a0000000-0000-0000-0000-000000000001', 'test', 'Seed pending task for live service testing', 3, 'pending', '{"seed": true}'),
    ('a0000000-0000-0000-0000-000000000002', 'verify', 'Seed claimed task for live service testing', 5, 'claimed', '{"seed": true}')
ON CONFLICT (id) DO NOTHING;

-- Mark the second task as claimed by seed-agent-2
UPDATE work_queue
SET claimed_by = 'seed-agent-2', claimed_at = NOW()
WHERE id = 'a0000000-0000-0000-0000-000000000002'
  AND claimed_by IS NULL;

-- =============================================================================
-- MEMORY — EPISODIC (1 minimum)
-- =============================================================================

INSERT INTO memory_episodic (id, agent_id, session_id, event_type, summary, details, outcome, tags)
VALUES
    ('b0000000-0000-0000-0000-000000000001', 'seed-agent-1', 'seed-session-1', 'discovery', 'Seed episodic memory for live service testing', '{"seed": true}', 'positive', ARRAY['seed', 'test'])
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- MEMORY — WORKING (1 minimum)
-- =============================================================================

INSERT INTO memory_working (id, agent_id, session_id, key, value)
VALUES
    ('c0000000-0000-0000-0000-000000000001', 'seed-agent-1', 'seed-session-1', 'seed-context', '{"description": "Seed working memory for live service testing", "seed": true}')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- MEMORY — PROCEDURAL (1 minimum)
-- =============================================================================

INSERT INTO memory_procedural (id, skill_name, description, steps)
VALUES
    ('d0000000-0000-0000-0000-000000000001', 'seed-test-skill', 'Seed procedural memory for live service testing', '["step-1: observe", "step-2: act"]')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- HANDOFF DOCUMENTS (1 minimum)
-- =============================================================================

INSERT INTO handoff_documents (id, agent_name, session_id, summary, completed_work, next_steps)
VALUES
    ('e0000000-0000-0000-0000-000000000001', 'seed-agent-1', 'seed-session-1', 'Seed handoff document for live service testing', '["Created seed data fixtures"]', '["Run live service validation"]')
ON CONFLICT (id) DO NOTHING;
