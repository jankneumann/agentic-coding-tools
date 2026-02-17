-- Ensure Cedar DB policy seed includes check_guardrails in write-operations.
-- Required because Cedar runtime prefers cedar_policies table over file fallback.

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
