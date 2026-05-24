-- Migration 026: Remote worker feature registry and handoff permissions
--
-- Earlier profile seeds limited feature-registry operations to high-trust
-- orchestrators. Remote trust-2 workers also need to register resource claims
-- and write handoffs through API-key-bound HTTP sessions.

UPDATE agent_profiles
SET allowed_operations = (
        SELECT ARRAY(
            SELECT DISTINCT op
            FROM unnest(
                allowed_operations
                || ARRAY['register_feature', 'deregister_feature']
            ) AS t(op)
            ORDER BY op
        )
    ),
    updated_at = now()
WHERE name IN ('claude_code_web_implementer', 'codex_cloud_worker');

UPDATE agent_profiles
SET allowed_operations = (
        SELECT ARRAY(
            SELECT DISTINCT op
            FROM unnest(
                allowed_operations
                || ARRAY['write_handoff', 'read_handoff']
            ) AS t(op)
            ORDER BY op
        )
    ),
    updated_at = now()
WHERE name = 'codex_cloud_worker';

INSERT INTO cedar_policies (name, policy_text, description, priority, enabled)
VALUES (
    'write-operations',
    '
permit(principal, action == Action::"acquire_lock", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"release_lock", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"complete_work", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"submit_work", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"remember", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"write_handoff", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"register_feature", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"deregister_feature", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"check_guardrails", resource) when { principal.trust_level >= 2 };
',
    'Allow trusted agents (level 2+) to perform write operations',
    20,
    TRUE
)
ON CONFLICT (name) DO UPDATE
SET
    policy_text = EXCLUDED.policy_text,
    description = EXCLUDED.description,
    priority = EXCLUDED.priority,
    enabled = EXCLUDED.enabled,
    updated_at = now();
