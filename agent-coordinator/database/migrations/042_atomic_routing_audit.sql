-- 042: atomically persist a routing decision and its bounded audit link.

BEGIN;

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
        outcome_ref
    ) VALUES (
        v_decision_id,
        COALESCE((p_decision ->> 'created_at')::TIMESTAMPTZ, now()),
        p_decision -> 'request',
        p_decision -> 'selected',
        COALESCE(p_decision -> 'alternatives', '[]'::JSONB),
        COALESCE(p_decision -> 'excluded', '[]'::JSONB),
        COALESCE((p_decision ->> 'exploration')::BOOLEAN, FALSE),
        COALESCE((p_decision ->> 'fallback')::BOOLEAN, FALSE),
        p_decision ->> 'policy_version',
        COALESCE(p_decision -> 'budget_state', '{}'::JSONB),
        p_decision ->> 'outcome_ref'
    );

    v_expected_link := jsonb_build_object(
        'decision_id', p_decision ->> 'decision_id',
        'selected_agent_id', p_decision #>> '{selected,assignment,agent_id}',
        'selected_model', p_decision #>> '{selected,model}',
        'routing_policy_version', p_decision #>> '{selected,provenance,policy_version}',
        'routing_policy_checksum', p_decision #>> '{selected,provenance,policy_checksum}',
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
