-- 039: close projection collision/replay gaps and notify first labelled inserts.

BEGIN;

CREATE TABLE IF NOT EXISTS work_queue_projection_ownership (
  task_id UUID PRIMARY KEY REFERENCES work_queue(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed durable ownership for projection rows produced by migrations 037/038.
INSERT INTO work_queue_projection_ownership(task_id)
SELECT id FROM work_queue
WHERE task_type='issue'
  AND input_data ? 'change_id' AND input_data ? 'phase'
  AND input_data ? 'transition_sequence'
  AND 'projection:autopilot-phase'=ANY(COALESCE(labels,ARRAY[]::TEXT[]))
ON CONFLICT DO NOTHING;

DROP FUNCTION IF EXISTS submit_task(TEXT,TEXT,JSONB,INTEGER,UUID[],TIMESTAMPTZ,JSONB);
DROP FUNCTION IF EXISTS submit_task(TEXT,TEXT,JSONB,INTEGER,UUID[],TIMESTAMPTZ,JSONB,TEXT[]);
CREATE OR REPLACE FUNCTION submit_task(
  p_task_type TEXT, p_description TEXT, p_input_data JSONB DEFAULT NULL,
  p_priority INTEGER DEFAULT 5, p_depends_on UUID[] DEFAULT NULL,
  p_deadline TIMESTAMPTZ DEFAULT NULL, p_agent_requirements JSONB DEFAULT NULL,
  p_projection_labels TEXT[] DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
  v_id UUID; v_status TEXT; v_created BOOLEAN:=TRUE;
  v_change TEXT; v_phase TEXT; v_seq INTEGER;
  v_head_phase TEXT; v_head_seq INTEGER; v_any BOOLEAN; v_complete BOOLEAN;
  v_head_missing BOOLEAN:=FALSE; v_existing_task_type TEXT;
  v_existing_owned BOOLEAN:=FALSE;
  v_reactivated INTEGER:=0;
BEGIN
  v_any:=COALESCE(p_input_data ?| ARRAY['change_id','phase','transition_sequence'],FALSE);
  v_complete:=COALESCE(p_input_data ? 'change_id' AND p_input_data ? 'phase'
                       AND p_input_data ? 'transition_sequence',FALSE);
  IF NOT v_any THEN
    IF p_projection_labels IS NOT NULL THEN
      RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_labels',
        'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
    END IF;
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
    OR (CASE WHEN COALESCE(p_input_data->>'transition_sequence','') ~ '^(0|[1-9][0-9]{0,9})$'
            THEN (p_input_data->>'transition_sequence')::BIGINT > 2147483647 ELSE FALSE END)
  THEN
    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_key',
      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
  END IF;

  v_change:=p_input_data->>'change_id'; v_phase:=p_input_data->>'phase';
  v_seq:=(p_input_data->>'transition_sequence')::INTEGER;
  IF p_projection_labels IS NOT NULL AND (
    p_task_type <> 'issue'
    OR p_projection_labels <> ARRAY['change:' || v_change, 'projection:autopilot-phase']
  ) THEN
    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_labels',
      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(v_change,0));
  SELECT phase,transition_sequence INTO v_head_phase,v_head_seq
  FROM work_queue_projection_heads WHERE change_id=v_change FOR UPDATE;
  IF NOT FOUND THEN
    v_head_missing:=TRUE;
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

  INSERT INTO work_queue(task_type,description,input_data,priority,depends_on,deadline,
                         agent_requirements,labels)
  VALUES(p_task_type,p_description,p_input_data,p_priority,p_depends_on,p_deadline,
         p_agent_requirements,COALESCE(p_projection_labels,ARRAY[]::TEXT[]))
  ON CONFLICT ((input_data ->> 'change_id'),(input_data ->> 'phase'),
               (input_data ->> 'transition_sequence'))
  WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
    AND jsonb_typeof(input_data -> 'transition_sequence') = 'number'
  DO NOTHING RETURNING id,status INTO v_id,v_status;
  IF v_id IS NULL THEN
    v_created:=FALSE;
    SELECT id,status,task_type,
      (EXISTS (SELECT 1 FROM work_queue_projection_ownership AS ownership
               WHERE ownership.task_id=work_queue.id))
      INTO v_id,v_status,v_existing_task_type,v_existing_owned FROM work_queue
    WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
      AND jsonb_typeof(input_data->'transition_sequence')='number'
      AND input_data->>'change_id'=v_change AND input_data->>'phase'=v_phase
      AND input_data->>'transition_sequence'=v_seq::TEXT;
    IF p_projection_labels IS NOT NULL AND p_task_type='issue'
       AND (v_existing_task_type<>'issue' OR NOT v_existing_owned) THEN
      RETURN jsonb_build_object('success',FALSE,'reason','projection_key_collision',
        'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
    END IF;
  END IF;
  IF p_projection_labels IS NOT NULL THEN
    INSERT INTO work_queue_projection_ownership(task_id) VALUES(v_id)
    ON CONFLICT DO NOTHING;
  END IF;
  IF v_head_missing THEN
    INSERT INTO work_queue_projection_heads(change_id,phase,transition_sequence)
    VALUES(v_change,v_phase,v_seq);
  END IF;
  IF p_projection_labels IS NOT NULL THEN
    UPDATE work_queue SET labels=ARRAY[]::TEXT[]
    WHERE id<>v_id AND task_type='issue'
      AND input_data ? 'change_id' AND input_data ? 'phase'
      AND input_data ? 'transition_sequence'
      AND input_data->>'change_id'=v_change
      AND 'projection:autopilot-phase'=ANY(COALESCE(labels,ARRAY[]::TEXT[]));
    UPDATE work_queue SET labels=p_projection_labels WHERE id=v_id;
    UPDATE work_queue SET
      status='pending', claimed_by=NULL, claimed_at=NULL, started_at=NULL,
      completed_at=NULL, result=NULL, error_message=NULL,
      closed_at=NULL, close_reason=NULL, attempt_count=0
    WHERE id=v_id AND status IN ('cancelled','completed','failed');
    GET DIAGNOSTICS v_reactivated = ROW_COUNT;
    IF v_reactivated > 0 THEN
      PERFORM coordinator_notify(
        'coordinator_task', 'projection.labels_changed', v_id::TEXT,
        'autopilot', 'Autopilot projection reactivated', v_change,
        jsonb_build_object('snapshot_required',TRUE)
      );
    END IF;
    SELECT status INTO v_status FROM work_queue WHERE id=v_id;
  END IF;
  RETURN jsonb_build_object('success',TRUE,'task_id',v_id,'status',v_status,
    'created',v_created,'deduplicated',NOT v_created,'cancelled_task_ids','[]'::JSONB);
END;
$$ LANGUAGE plpgsql;

DROP FUNCTION IF EXISTS reconcile_work_projection(TEXT,TEXT,INTEGER,TEXT,TEXT,JSONB,INTEGER,JSONB);
DROP FUNCTION IF EXISTS reconcile_work_projection(TEXT,TEXT,INTEGER,TEXT,TEXT,JSONB,INTEGER,JSONB,TEXT[]);
CREATE OR REPLACE FUNCTION reconcile_work_projection(
  p_change_id TEXT, p_phase TEXT, p_transition_sequence INTEGER,
  p_task_type TEXT, p_description TEXT, p_input_data JSONB,
  p_priority INTEGER DEFAULT 5, p_agent_requirements JSONB DEFAULT NULL,
  p_projection_labels TEXT[] DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
  v_id UUID; v_status TEXT; v_created BOOLEAN:=TRUE;
  v_head_seq INTEGER; v_cancelled UUID[]:=ARRAY[]::UUID[]; v_payload JSONB;
  v_existing_task_type TEXT; v_existing_owned BOOLEAN:=FALSE;
  v_reactivated INTEGER:=0;
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
  IF p_projection_labels IS NOT NULL AND (
    p_task_type <> 'issue'
    OR p_projection_labels <> ARRAY['change:' || p_change_id, 'projection:autopilot-phase']
  ) THEN
    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_labels',
      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_change_id,0));
  SELECT transition_sequence INTO v_head_seq FROM work_queue_projection_heads
  WHERE change_id=p_change_id FOR UPDATE;
  IF FOUND AND p_transition_sequence < v_head_seq THEN
    RETURN jsonb_build_object('success',FALSE,'reason','stale_projection','created',FALSE,
      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
  END IF;

  v_payload:=(COALESCE(p_input_data,'{}'::JSONB)-'change_id'-'phase'-'transition_sequence')
    || jsonb_build_object('change_id',p_change_id,'phase',p_phase,
                          'transition_sequence',p_transition_sequence);
  INSERT INTO work_queue(task_type,description,input_data,priority,agent_requirements,labels)
  VALUES(p_task_type,p_description,v_payload,p_priority,p_agent_requirements,
         COALESCE(p_projection_labels,ARRAY[]::TEXT[]))
  ON CONFLICT ((input_data ->> 'change_id'),(input_data ->> 'phase'),
               (input_data ->> 'transition_sequence'))
  WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
    AND jsonb_typeof(input_data -> 'transition_sequence') = 'number'
  DO NOTHING RETURNING id,status INTO v_id,v_status;
  IF v_id IS NULL THEN
    v_created:=FALSE;
    SELECT id,status,task_type,
      (EXISTS (SELECT 1 FROM work_queue_projection_ownership AS ownership
               WHERE ownership.task_id=work_queue.id))
      INTO v_id,v_status,v_existing_task_type,v_existing_owned FROM work_queue
    WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
      AND jsonb_typeof(input_data->'transition_sequence')='number'
      AND input_data->>'change_id'=p_change_id AND input_data->>'phase'=p_phase
      AND input_data->>'transition_sequence'=p_transition_sequence::TEXT;
    IF p_projection_labels IS NOT NULL AND p_task_type='issue'
       AND (v_existing_task_type<>'issue' OR NOT v_existing_owned) THEN
      RETURN jsonb_build_object('success',FALSE,'reason','projection_key_collision',
        'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
    END IF;
  END IF;
  IF p_projection_labels IS NOT NULL THEN
    INSERT INTO work_queue_projection_ownership(task_id) VALUES(v_id)
    ON CONFLICT DO NOTHING;
  END IF;

  INSERT INTO work_queue_projection_heads(change_id,phase,transition_sequence)
  VALUES(p_change_id,p_phase,p_transition_sequence)
  ON CONFLICT(change_id) DO UPDATE SET phase=EXCLUDED.phase,
    transition_sequence=EXCLUDED.transition_sequence,updated_at=NOW();

  WITH cancelled AS (
    UPDATE work_queue SET status='cancelled',completed_at=NOW(),
      labels=CASE
        WHEN p_projection_labels IS NOT NULL AND task_type='issue'
          AND 'projection:autopilot-phase'=ANY(COALESCE(labels,ARRAY[]::TEXT[]))
        THEN ARRAY[]::TEXT[] ELSE labels END,
      result=jsonb_build_object('reason','cancelled_by_projection_reconcile',
        'change_id',p_change_id,'phase',p_phase,'transition_sequence',p_transition_sequence)
    WHERE status IN ('pending','claimed','running')
      AND input_data ? 'change_id' AND input_data->>'change_id'=p_change_id
      AND NOT (input_data->>'phase'=p_phase
               AND input_data->>'transition_sequence'=p_transition_sequence::TEXT)
    RETURNING id)
  SELECT COALESCE(array_agg(id ORDER BY id::TEXT),ARRAY[]::UUID[])
    INTO v_cancelled FROM cancelled;

  IF p_projection_labels IS NOT NULL THEN
    UPDATE work_queue SET labels=ARRAY[]::TEXT[]
    WHERE id<>v_id AND task_type='issue'
      AND input_data ? 'change_id' AND input_data ? 'phase'
      AND input_data ? 'transition_sequence'
      AND input_data->>'change_id'=p_change_id
      AND 'projection:autopilot-phase'=ANY(COALESCE(labels,ARRAY[]::TEXT[]));
    UPDATE work_queue SET labels=p_projection_labels WHERE id=v_id;
    UPDATE work_queue SET
      status='pending', claimed_by=NULL, claimed_at=NULL, started_at=NULL,
      completed_at=NULL, result=NULL, error_message=NULL,
      closed_at=NULL, close_reason=NULL, attempt_count=0
    WHERE id=v_id AND status IN ('cancelled','completed','failed');
    GET DIAGNOSTICS v_reactivated = ROW_COUNT;
    IF v_reactivated > 0 THEN
      PERFORM coordinator_notify(
        'coordinator_task', 'projection.labels_changed', v_id::TEXT,
        'autopilot', 'Autopilot projection reactivated', p_change_id,
        jsonb_build_object('snapshot_required',TRUE)
      );
    END IF;
    SELECT status INTO v_status FROM work_queue WHERE id=v_id;
  END IF;
  RETURN jsonb_build_object('success',TRUE,'task_id',v_id,'status',v_status,
    'created',v_created,'deduplicated',NOT v_created,'cancelled_task_ids',to_jsonb(v_cancelled));
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION notify_projection_insert() RETURNS TRIGGER AS $projection$
DECLARE
  v_change_id TEXT;
  v_label TEXT;
BEGIN
  IF 'projection:autopilot-phase'=ANY(COALESCE(NEW.labels,ARRAY[]::TEXT[])) THEN
    FOREACH v_label IN ARRAY NEW.labels LOOP
      IF v_label LIKE 'change:%' THEN
        v_change_id:=substr(v_label,8);
        EXIT;
      END IF;
    END LOOP;
    PERFORM coordinator_notify(
      'coordinator_task',
      'projection.labels_changed',
      NEW.id::TEXT,
      COALESCE(NEW.claimed_by,'autopilot'),
      'Autopilot projection labels added',
      v_change_id,
      jsonb_build_object('snapshot_required',TRUE)
    );
  END IF;
  RETURN NEW;
END;
$projection$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_work_queue_projection_insert_notify ON work_queue;
CREATE TRIGGER trg_work_queue_projection_insert_notify
  AFTER INSERT ON work_queue
  FOR EACH ROW
  EXECUTE FUNCTION notify_projection_insert();

-- Repair only terminal rows carrying the reserved projection marker and complete
-- projection identity. Ordinary change-labelled issues are not selected.
UPDATE work_queue SET labels=ARRAY[]::TEXT[]
WHERE status='cancelled' AND task_type='issue'
  AND input_data ? 'change_id' AND input_data ? 'phase'
  AND input_data ? 'transition_sequence'
  AND 'projection:autopilot-phase'=ANY(COALESCE(labels,ARRAY[]::TEXT[]));

COMMIT;
