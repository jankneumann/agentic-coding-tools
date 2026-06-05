-- Migration 026: Evaluator agent profile
-- Seeds the agent_profiles table with a built-in evaluator profile
-- that has read-only permissions for generation/evaluation separation.
-- See design decision D5 in openspec/changes/harness-engineering-features/design.md

INSERT INTO agent_profiles (
    name,
    agent_type,
    trust_level,
    allowed_operations,
    blocked_operations,
    max_file_modifications,
    max_execution_time_seconds,
    max_api_calls_per_hour,
    enabled
) VALUES (
    'evaluator',
    'evaluator',
    2,
    ARRAY['read', 'review', 'evaluate'],
    ARRAY['write', 'commit', 'push', 'delete'],
    0,
    600,
    500,
    true
);
