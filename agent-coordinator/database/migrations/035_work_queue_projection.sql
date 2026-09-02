-- 035: idempotent loop-state work-queue projection
-- Sources: https://www.postgresql.org/docs/current/sql-insert.html#SQL-ON-CONFLICT
-- https://www.postgresql.org/docs/current/indexes-expressional.html
-- https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS

LOCK TABLE work_queue IN SHARE ROW EXCLUSIVE MODE;

DO $migration$
DECLARE v_bad TEXT;
BEGIN
  SELECT string_agg(id::TEXT, ',' ORDER BY id::TEXT) INTO v_bad
  FROM work_queue
  WHERE input_data ?| ARRAY['change_id','phase','transition_sequence'] AND (
    NOT (input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence')
    OR COALESCE(input_data->>'change_id','') !~ '^[a-z0-9][a-z0-9-]{0,127}$'
    OR COALESCE(input_data->>'phase','') <> ALL (ARRAY[
      'INIT','GATEKEEPER','PLAN','PLAN_ITERATE','PLAN_REVIEW','PLAN_FIX',
      'IMPLEMENT','IMPL_ITERATE','IMPL_REVIEW','IMPL_FIX','VALIDATE',
      'VAL_REVIEW','VAL_FIX','SUBMIT_PR','ESCALATE','DONE'])
    OR jsonb_typeof(input_data->'transition_sequence') IS DISTINCT FROM 'number'
    OR COALESCE(input_data->>'transition_sequence','') !~ '^(0|[1-9][0-9]{0,9})$'
    OR CASE WHEN COALESCE(input_data->>'transition_sequence','') ~ '^(0|[1-9][0-9]{0,9})$'
            THEN (input_data->>'transition_sequence')::BIGINT > 2147483647 ELSE FALSE END);
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE='23514',
      MESSAGE='invalid work queue projection keys: '||v_bad,
      HINT='quarantine or normalize the listed rows, then rerun migration 035';
  END IF;

  SELECT string_agg(ids, ';' ORDER BY ids) INTO v_bad FROM (
    SELECT string_agg(id::TEXT, ',' ORDER BY id::TEXT) ids FROM work_queue
    WHERE input_data ? 'change_id' AND input_data ? 'phase'
      AND input_data ? 'transition_sequence'
      AND jsonb_typeof(input_data->'transition_sequence')='number'
    GROUP BY input_data->>'change_id', input_data->>'phase', input_data->>'transition_sequence'
    HAVING count(*) > 1) d;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE='23505',
      MESSAGE='duplicate work queue projection keys: '||v_bad,
      HINT='retain one canonical row per tuple, then rerun migration 035';
  END IF;
END
$migration$;

CREATE TABLE work_queue_projection_heads (
  change_id TEXT PRIMARY KEY,
  phase TEXT NOT NULL,
  transition_sequence INTEGER NOT NULL CHECK (transition_sequence >= 0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX work_queue_projection_key_uidx
ON work_queue ((input_data ->> 'change_id'),(input_data ->> 'phase'),
               (input_data ->> 'transition_sequence'))
WHERE input_data ? 'change_id' AND input_data ? 'phase'
  AND input_data ? 'transition_sequence'
  AND jsonb_typeof(input_data -> 'transition_sequence') = 'number';

DROP FUNCTION IF EXISTS submit_task(TEXT,TEXT,JSONB,INTEGER,UUID[],TIMESTAMPTZ,JSONB);
CREATE OR REPLACE FUNCTION submit_task(
  p_task_type TEXT, p_description TEXT, p_input_data JSONB DEFAULT NULL,
  p_priority INTEGER DEFAULT 5, p_depends_on UUID[] DEFAULT NULL,
  p_deadline TIMESTAMPTZ DEFAULT NULL, p_agent_requirements JSONB DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
  v_id UUID; v_status TEXT; v_created BOOLEAN:=TRUE;
  v_change TEXT; v_phase TEXT; v_seq INTEGER;
  v_head_phase TEXT; v_head_seq INTEGER; v_any BOOLEAN; v_complete BOOLEAN;
BEGIN
  v_any:=COALESCE(p_input_data ?| ARRAY['change_id','phase','transition_sequence'],FALSE);
  v_complete:=COALESCE(p_input_data ? 'change_id' AND p_input_data ? 'phase'
                       AND p_input_data ? 'transition_sequence',FALSE);
  IF NOT v_any THEN
    INSERT INTO work_queue(task_type,description,input_data,priority,depends_on,deadline,agent_requirements)
    VALUES(p_task_type,p_description,p_input_data,p_priority,p_depends_on,p_deadline,p_agent_requirements)
    RETURNING id,status INTO v_id,v_status;
    RETURN jsonb_build_object('success',TRUE,'task_id',v_id,'status',v_status,
      'created',TRUE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
  END IF;

  IF NOT v_complete OR jsonb_typeof(p_input_data->'transition_sequence') IS DISTINCT FROM 'number'
    OR COALESCE(p_input_data->>'change_id','') !~ '^[a-z0-9][a-z0-9-]{0,127}$'
    OR COALESCE(p_input_data->>'phase','') <> ALL (ARRAY[
      'INIT','GATEKEEPER','PLAN','PLAN_ITERATE','PLAN_REVIEW','PLAN_FIX',
      'IMPLEMENT','IMPL_ITERATE','IMPL_REVIEW','IMPL_FIX','VALIDATE',
      'VAL_REVIEW','VAL_FIX','SUBMIT_PR','ESCALATE','DONE'])
    OR COALESCE(p_input_data->>'transition_sequence','') !~ '^(0|[1-9][0-9]{0,9})$'
    OR CASE WHEN COALESCE(p_input_data->>'transition_sequence','') ~ '^(0|[1-9][0-9]{0,9})$'
            THEN (p_input_data->>'transition_sequence')::BIGINT > 2147483647 ELSE FALSE END
  THEN
    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_key',
      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
  END IF;

  v_change:=p_input_data->>'change_id'; v_phase:=p_input_data->>'phase';
  v_seq:=(p_input_data->>'transition_sequence')::INTEGER;
  PERFORM pg_advisory_xact_lock(hashtextextended(v_change,0));
  SELECT phase,transition_sequence INTO v_head_phase,v_head_seq
  FROM work_queue_projection_heads WHERE change_id=v_change FOR UPDATE;
  IF NOT FOUND THEN
    INSERT INTO work_queue_projection_heads(change_id,phase,transition_sequence)
    VALUES(v_change,v_phase,v_seq);
  ELSIF v_seq < v_head_seq THEN
    RETURN jsonb_build_object('success',FALSE,'reason','stale_projection','created',FALSE,
      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
  ELSIF v_seq = v_head_seq AND v_phase <> v_head_phase THEN
    RETURN jsonb_build_object('success',FALSE,'reason','projection_generation_mismatch','created',FALSE,
      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
  ELSIF v_seq > v_head_seq THEN
    RETURN jsonb_build_object('success',FALSE,'reason','reconciliation_required','created',FALSE,
      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
  END IF;

  INSERT INTO work_queue(task_type,description,input_data,priority,depends_on,deadline,agent_requirements)
  VALUES(p_task_type,p_description,p_input_data,p_priority,p_depends_on,p_deadline,p_agent_requirements)
  ON CONFLICT ((input_data ->> 'change_id'),(input_data ->> 'phase'),
               (input_data ->> 'transition_sequence'))
  WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
    AND jsonb_typeof(input_data -> 'transition_sequence') = 'number'
  DO NOTHING RETURNING id,status INTO v_id,v_status;
  IF v_id IS NULL THEN
    v_created:=FALSE;
    SELECT id,status INTO v_id,v_status FROM work_queue
    WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
      AND jsonb_typeof(input_data->'transition_sequence')='number'
      AND input_data->>'change_id'=v_change AND input_data->>'phase'=v_phase
      AND input_data->>'transition_sequence'=v_seq::TEXT;
  END IF;
  RETURN jsonb_build_object('success',TRUE,'task_id',v_id,'status',v_status,
    'created',v_created,'deduplicated',NOT v_created,'cancelled_task_ids','[]'::JSONB);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION reconcile_work_projection(
  p_change_id TEXT, p_phase TEXT, p_transition_sequence INTEGER,
  p_task_type TEXT, p_description TEXT, p_input_data JSONB,
  p_priority INTEGER DEFAULT 5, p_agent_requirements JSONB DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
  v_id UUID; v_status TEXT; v_created BOOLEAN:=TRUE;
  v_head_seq INTEGER; v_cancelled UUID[]:=ARRAY[]::UUID[]; v_payload JSONB;
BEGIN
  IF p_change_id !~ '^[a-z0-9][a-z0-9-]{0,127}$'
    OR p_phase <> ALL (ARRAY[
      'INIT','GATEKEEPER','PLAN','PLAN_ITERATE','PLAN_REVIEW','PLAN_FIX',
      'IMPLEMENT','IMPL_ITERATE','IMPL_REVIEW','IMPL_FIX','VALIDATE',
      'VAL_REVIEW','VAL_FIX','SUBMIT_PR','ESCALATE','DONE'])
    OR p_transition_sequence IS NULL OR p_transition_sequence < 0
  THEN
    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_key',
      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_change_id,0));
  SELECT transition_sequence INTO v_head_seq FROM work_queue_projection_heads
  WHERE change_id=p_change_id FOR UPDATE;
  IF FOUND AND p_transition_sequence < v_head_seq THEN
    RETURN jsonb_build_object('success',FALSE,'reason','stale_projection','created',FALSE,
      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
  END IF;
  INSERT INTO work_queue_projection_heads(change_id,phase,transition_sequence)
  VALUES(p_change_id,p_phase,p_transition_sequence)
  ON CONFLICT(change_id) DO UPDATE SET phase=EXCLUDED.phase,
    transition_sequence=EXCLUDED.transition_sequence,updated_at=NOW();

  v_payload:=(COALESCE(p_input_data,'{}'::JSONB)-'change_id'-'phase'-'transition_sequence')
    || jsonb_build_object('change_id',p_change_id,'phase',p_phase,
                          'transition_sequence',p_transition_sequence);
  WITH cancelled AS (
    UPDATE work_queue SET status='cancelled',completed_at=NOW(),
      result=jsonb_build_object('reason','cancelled_by_projection_reconcile',
        'change_id',p_change_id,'phase',p_phase,'transition_sequence',p_transition_sequence)
    WHERE status IN ('pending','claimed','running')
      AND input_data ? 'change_id' AND input_data->>'change_id'=p_change_id
      AND NOT (input_data->>'phase'=p_phase
               AND input_data->>'transition_sequence'=p_transition_sequence::TEXT)
    RETURNING id)
  SELECT COALESCE(array_agg(id ORDER BY id::TEXT),ARRAY[]::UUID[])
    INTO v_cancelled FROM cancelled;

  INSERT INTO work_queue(task_type,description,input_data,priority,agent_requirements)
  VALUES(p_task_type,p_description,v_payload,p_priority,p_agent_requirements)
  ON CONFLICT ((input_data ->> 'change_id'),(input_data ->> 'phase'),
               (input_data ->> 'transition_sequence'))
  WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
    AND jsonb_typeof(input_data -> 'transition_sequence') = 'number'
  DO NOTHING RETURNING id,status INTO v_id,v_status;
  IF v_id IS NULL THEN
    v_created:=FALSE;
    SELECT id,status INTO v_id,v_status FROM work_queue
    WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
      AND jsonb_typeof(input_data->'transition_sequence')='number'
      AND input_data->>'change_id'=p_change_id AND input_data->>'phase'=p_phase
      AND input_data->>'transition_sequence'=p_transition_sequence::TEXT;
  END IF;
  RETURN jsonb_build_object('success',TRUE,'task_id',v_id,'status',v_status,
    'created',v_created,'deduplicated',NOT v_created,'cancelled_task_ids',to_jsonb(v_cancelled));
END;
$$ LANGUAGE plpgsql;
