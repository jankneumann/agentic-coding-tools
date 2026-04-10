-- Migration 017: Add missing operations to agent profiles
-- Dependencies: 007_agent_profiles.sql
--
-- The /work/get endpoint uses operation="get_task" but the seed profiles
-- only include "get_work". Similarly, feature registry and merge queue
-- endpoints introduced new operations not in the original profiles.

-- =============================================================================
-- Add get_task to profiles that already have get_work
-- =============================================================================

UPDATE agent_profiles
SET allowed_operations = array_append(allowed_operations, 'get_task'),
    updated_at = now()
WHERE 'get_work' = ANY(allowed_operations)
  AND NOT ('get_task' = ANY(allowed_operations));

-- =============================================================================
-- Add feature registry and merge queue operations to high-trust profiles
-- (trust_level >= 3: claude_code_cli, strands_orchestrator)
-- =============================================================================

UPDATE agent_profiles
SET allowed_operations = allowed_operations
    || ARRAY['register_feature', 'deregister_feature',
             'enqueue_merge', 'run_pre_merge_checks',
             'mark_merged', 'remove_from_merge_queue'],
    updated_at = now()
WHERE trust_level >= 3
  AND NOT ('register_feature' = ANY(allowed_operations));
