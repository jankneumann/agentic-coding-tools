-- 046: make POST /routing/spend's generation_id dedupe atomic.
--
-- generation_id is the idempotency key of POST /routing/spend. The route used
-- to look the key up and then insert, so two concurrent posts of one
-- generation could both miss the lookup and both insert, double-counting the
-- spend. The dedupe now belongs to the database: a partial unique index on
-- generation_id, and record_spend_once(), which inserts with
-- ON CONFLICT DO NOTHING and otherwise returns the row already recorded.
--
-- The index is partial (WHERE generation_id IS NOT NULL) because generation_id
-- is nullable: rows written through LedgerService.record by other callers may
-- carry no generation and must not collide with each other.

BEGIN;

-- Duplicates may already exist: the race above could produce them. Each one
-- is the same generation counted twice, so keep the earliest row (lowest id)
-- and drop the rest; otherwise the unique index below cannot be built.
DELETE FROM routing_spend_ledger AS later
USING routing_spend_ledger AS earlier
WHERE later.generation_id IS NOT NULL
  AND later.generation_id = earlier.generation_id
  AND later.id > earlier.id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_spend_ledger_generation_id
    ON routing_spend_ledger (generation_id)
    WHERE generation_id IS NOT NULL;

-- Insert one spend row unless its generation_id is already recorded.
--
-- Returns {"created": true, "row": <inserted row>} on a fresh insert and
-- {"created": false, "row": <existing row>} when the generation was already
-- recorded. Under READ COMMITTED, ON CONFLICT DO NOTHING waits for a
-- concurrent inserter of the same key to commit, and the follow-up SELECT
-- runs with a fresh snapshot, so it sees that row. Returns jsonb (not a
-- composite) so both database clients decode it (see 045).
CREATE OR REPLACE FUNCTION record_spend_once(p_row JSONB)
RETURNS JSONB
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_in routing_spend_ledger;
    v_row routing_spend_ledger;
BEGIN
    v_in := jsonb_populate_record(NULL::routing_spend_ledger, p_row);

    INSERT INTO routing_spend_ledger (
        occurred_at,
        decision_id,
        vendor,
        model,
        endpoint_kind,
        prompt_tokens,
        completion_tokens,
        tokens_estimated,
        actual_usd,
        counterfactual_usd,
        exploration,
        generation_id,
        work_unit_ref
    )
    VALUES (
        COALESCE(v_in.occurred_at, now()),
        v_in.decision_id,
        v_in.vendor,
        v_in.model,
        v_in.endpoint_kind,
        v_in.prompt_tokens,
        v_in.completion_tokens,
        COALESCE(v_in.tokens_estimated, FALSE),
        COALESCE(v_in.actual_usd, 0),
        COALESCE(v_in.counterfactual_usd, 0),
        COALESCE(v_in.exploration, FALSE),
        v_in.generation_id,
        v_in.work_unit_ref
    )
    ON CONFLICT (generation_id) WHERE generation_id IS NOT NULL DO NOTHING
    RETURNING * INTO v_row;

    IF FOUND THEN
        RETURN jsonb_build_object('created', TRUE, 'row', to_jsonb(v_row));
    END IF;

    SELECT * INTO v_row
    FROM routing_spend_ledger
    WHERE generation_id = v_in.generation_id
    ORDER BY id
    LIMIT 1;

    RETURN jsonb_build_object('created', FALSE, 'row', to_jsonb(v_row));
END;
$$;

REVOKE ALL ON FUNCTION record_spend_once(JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION record_spend_once(JSONB) TO service_role;

COMMIT;
