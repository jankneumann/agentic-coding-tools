-- Contract for migration 044_routing_decision_retention.sql (design D8).
-- Additive over 040_model_routing.sql and 042_atomic_routing_audit.sql.

ALTER TABLE routing_decisions ADD COLUMN IF NOT EXISTS retention JSONB;
ALTER TABLE routing_decisions ALTER COLUMN selected DROP NOT NULL;
ALTER TABLE routing_decisions
    ADD CONSTRAINT routing_decisions_selected_or_retention
    CHECK (selected IS NOT NULL OR retention IS NOT NULL);

-- record_routing_decision_with_audit(p_decision JSONB, p_audit_link JSONB):
--   * inserts p_decision -> 'retention' into routing_decisions.retention
--   * expected audit link:
--       selected_agent_id      = p_decision #>> '{selected,assignment,agent_id}'        (NULL when selected is null)
--       selected_model         = p_decision #>> '{selected,model}'                      (NULL when selected is null)
--       routing_policy_version = COALESCE({selected,provenance,policy_version}, {provenance,policy_version})
--       routing_policy_checksum= COALESCE({selected,provenance,policy_checksum}, {provenance,policy_checksum})
