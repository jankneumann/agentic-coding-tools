-- 044: persist incumbent retention on routing decisions.
--
-- retain-static-model-until-routing-evidence (design D8). A decision made with
-- an incumbent carries a `retention` record; when the incumbent is kept but no
-- feasible catalog row represents it, `selected` is null. Everything here is
-- additive: pre-044 code never writes `retention` and always writes `selected`.

BEGIN;

ALTER TABLE routing_decisions ADD COLUMN IF NOT EXISTS retention JSONB;

ALTER TABLE routing_decisions ALTER COLUMN selected DROP NOT NULL;

-- A null selection is only representable alongside the retention record that
-- explains it.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'routing_decisions_selected_or_retention'
          AND conrelid = 'routing_decisions'::regclass
    ) THEN
        ALTER TABLE routing_decisions
            ADD CONSTRAINT routing_decisions_selected_or_retention
            CHECK (selected IS NOT NULL OR retention IS NOT NULL);
    END IF;
END;
$$;

-- Same contract as 042, plus `retention`. With a null selection the audit
-- link has no agent or model, and its policy fields come from the decision's
-- top-level provenance.
CREATE OR REPLACE FUNCTION record_routing_decision_with_audit(
    p_decision JSONB,
    p_audit_link JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_expected_link JSONB;
    v_decision_id UUID;
BEGIN
    v_decision_id := (p_decision ->> 'decision_id')::UUID;

    INSERT INTO routing_decisions (
        decision_id,
        created_at,
        request,
        selected,
        alternatives,
        excluded,
        exploration,
        fallback,
        policy_version,
        budget_state,
        outcome_ref,
        retention
    ) VALUES (
        v_decision_id,
        COALESCE((p_decision ->> 'created_at')::TIMESTAMPTZ, now()),
        p_decision -> 'request',
        NULLIF(p_decision -> 'selected', 'null'::JSONB),
        COALESCE(p_decision -> 'alternatives', '[]'::JSONB),
        COALESCE(p_decision -> 'excluded', '[]'::JSONB),
        COALESCE((p_decision ->> 'exploration')::BOOLEAN, FALSE),
        COALESCE((p_decision ->> 'fallback')::BOOLEAN, FALSE),
        p_decision ->> 'policy_version',
        COALESCE(p_decision -> 'budget_state', '{}'::JSONB),
        p_decision ->> 'outcome_ref',
        NULLIF(p_decision -> 'retention', 'null'::JSONB)
    );

    v_expected_link := jsonb_build_object(
        'decision_id', p_decision ->> 'decision_id',
        'selected_agent_id', p_decision #>> '{selected,assignment,agent_id}',
        'selected_model', p_decision #>> '{selected,model}',
        'routing_policy_version', COALESCE(
            p_decision #>> '{selected,provenance,policy_version}',
            p_decision #>> '{provenance,policy_version}'
        ),
        'routing_policy_checksum', COALESCE(
            p_decision #>> '{selected,provenance,policy_checksum}',
            p_decision #>> '{provenance,policy_checksum}'
        ),
        'source', 'coordinator',
        'success', TRUE
    );
    IF p_audit_link IS DISTINCT FROM v_expected_link THEN
        RAISE EXCEPTION 'invalid routing audit link' USING ERRCODE = '22023';
    END IF;

    INSERT INTO audit_log (
        agent_id,
        agent_type,
        operation,
        parameters,
        result,
        success
    ) VALUES (
        'coordinator',
        'coordinator',
        'routing_decision',
        '{}'::JSONB,
        p_audit_link,
        TRUE
    );

    RETURN jsonb_build_object('decision_id', v_decision_id::TEXT);
END;
$$;

REVOKE ALL ON FUNCTION record_routing_decision_with_audit(JSONB, JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION record_routing_decision_with_audit(JSONB, JSONB) TO service_role;

COMMIT;
