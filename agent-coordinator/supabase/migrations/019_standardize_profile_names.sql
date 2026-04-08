-- Migration 019: Standardize profile names to match agents.yaml convention
-- Dependencies: 007_agent_profiles.sql, 018_agent_profile_assignments.sql
--
-- Old names were inconsistent (cli/web vs local/cloud, claude_code vs codex).
-- New convention: <agent_type>_<local|remote|reviewer>

UPDATE agent_profiles SET name = 'claude_code_local'    WHERE name = 'claude_code_cli';
UPDATE agent_profiles SET name = 'claude_code_remote'   WHERE name = 'claude_code_web_implementer';
UPDATE agent_profiles SET name = 'claude_code_reviewer'  WHERE name = 'claude_code_web_reviewer';
UPDATE agent_profiles SET name = 'codex_local'          WHERE name = 'codex_local_worker';
UPDATE agent_profiles SET name = 'codex_remote'         WHERE name = 'codex_cloud_worker';
UPDATE agent_profiles SET name = 'gemini_local'         WHERE name = 'gemini_local_worker';
UPDATE agent_profiles SET name = 'gemini_remote'        WHERE name = 'gemini_cloud_worker';
UPDATE agent_profiles SET name = 'strands_local'        WHERE name = 'strands_orchestrator';
