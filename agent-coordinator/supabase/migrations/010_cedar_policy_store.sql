-- Cedar Policy Store
-- Stores Cedar policies and entity mappings for the optional Cedar policy engine.
-- Only used when POLICY_ENGINE=cedar.

-- =============================================================================
-- Cedar policies table
-- =============================================================================
CREATE TABLE IF NOT EXISTS cedar_policies (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    policy_text TEXT NOT NULL,
    description TEXT DEFAULT '',
    priority INTEGER DEFAULT 100,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_cedar_policies_enabled ON cedar_policies (enabled, priority);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_cedar_policies_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER cedar_policies_updated_at
    BEFORE UPDATE ON cedar_policies
    FOR EACH ROW
    EXECUTE FUNCTION update_cedar_policies_timestamp();

-- =============================================================================
-- Cedar entity mappings
-- =============================================================================
CREATE TABLE IF NOT EXISTS cedar_entities (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    attributes JSONB DEFAULT '{}'::JSONB,
    parents JSONB DEFAULT '[]'::JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (entity_type, entity_id)
);

CREATE INDEX idx_cedar_entities_type ON cedar_entities (entity_type);

-- Auto-update updated_at
CREATE TRIGGER cedar_entities_updated_at
    BEFORE UPDATE ON cedar_entities
    FOR EACH ROW
    EXECUTE FUNCTION update_cedar_policies_timestamp();

-- =============================================================================
-- Seed default Cedar policies (same as cedar/default_policies.cedar)
-- =============================================================================

-- Read operations — permit all agents
INSERT INTO cedar_policies (name, policy_text, description, priority) VALUES
('read-operations', '
permit(principal, action == Action::"check_locks", resource);
permit(principal, action == Action::"get_work", resource);
permit(principal, action == Action::"recall", resource);
permit(principal, action == Action::"discover_agents", resource);
permit(principal, action == Action::"read_handoff", resource);
permit(principal, action == Action::"query_audit", resource);
', 'Allow all agents to perform read operations', 10);

-- Write operations — trust >= 2
INSERT INTO cedar_policies (name, policy_text, description, priority) VALUES
('write-operations', '
permit(principal, action == Action::"acquire_lock", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"release_lock", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"complete_work", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"submit_work", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"remember", resource) when { principal.trust_level >= 2 };
permit(principal, action == Action::"write_handoff", resource) when { principal.trust_level >= 2 };
', 'Allow trusted agents (level 2+) to perform write operations', 20);

-- Admin operations — trust >= 3
INSERT INTO cedar_policies (name, policy_text, description, priority) VALUES
('admin-operations', '
permit(principal, action == Action::"force_push", resource) when { principal.trust_level >= 3 };
permit(principal, action == Action::"delete_branch", resource) when { principal.trust_level >= 3 };
permit(principal, action == Action::"cleanup_agents", resource) when { principal.trust_level >= 3 };
', 'Allow high-trust agents (level 3+) to perform admin operations', 30);

-- Suspended agents — forbid all
INSERT INTO cedar_policies (name, policy_text, description, priority) VALUES
('suspended-agents', '
forbid(principal, action, resource) when { principal.trust_level == 0 };
', 'Deny all operations for suspended agents (trust level 0)', 1);

-- Network access — known domains
INSERT INTO cedar_policies (name, policy_text, description, priority) VALUES
('network-access', '
permit(principal, action == Action::"network_access", resource == Domain::"github.com");
permit(principal, action == Action::"network_access", resource == Domain::"api.github.com");
permit(principal, action == Action::"network_access", resource == Domain::"raw.githubusercontent.com");
permit(principal, action == Action::"network_access", resource == Domain::"registry.npmjs.org");
permit(principal, action == Action::"network_access", resource == Domain::"pypi.org");
', 'Allow network access to known package registries', 40);

-- =============================================================================
-- RLS
-- =============================================================================
ALTER TABLE cedar_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE cedar_entities ENABLE ROW LEVEL SECURITY;

-- Policies: service_role can read/write, anon can read
CREATE POLICY "cedar_policies_service_all" ON cedar_policies
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "cedar_policies_anon_read" ON cedar_policies
    FOR SELECT TO anon USING (true);

CREATE POLICY "cedar_entities_service_all" ON cedar_entities
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "cedar_entities_anon_read" ON cedar_entities
    FOR SELECT TO anon USING (true);
