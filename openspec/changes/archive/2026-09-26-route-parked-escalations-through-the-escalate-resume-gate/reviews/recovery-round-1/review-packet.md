## Review Round 4

This packet exceeds the size budget and was truncated. You MAY use Read/Grep to recover truncated context.

Review the attached artifacts for correctness, completeness, and adherence to project standards.

### Prompt contract
REQUIRED on every finding — output is REJECTED if any is missing: id, type, criticality, description, disposition, axis, severity
These fields use DIFFERENT vocabularies. Do not reuse one value for another:
  criticality: low|medium|high|critical — how much it matters
  severity: critical|nit|optional|fyi|none — review-gate grading (NOT the same scale as criticality)
  axis: correctness|readability|architecture|security|performance|observability|resilience|compatibility
  type: spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure
  disposition: fix|regenerate|accept|escalate
Use exactly one value from each listed set; do not invent values.
Output ONLY a JSON object with a top-level `findings` array.

### Diff
```diff
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index fc398c0c..c53002aa 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -102,6 +102,7 @@ jobs:
 
       - name: Validate standalone skill install payload
         run: |
+          bash install.sh --mode copy --force --deps none --openspec-assets none --openspec-cli none --python-tools none
           bash install.sh --check
           uv run python validate-feature/scripts/linters/dependency_direction.py --skills-root .
 
diff --git a/agent-coordinator/agents.yaml b/agent-coordinator/agents.yaml
index 89df644d..f65dccb3 100644
--- a/agent-coordinator/agents.yaml
+++ b/agent-coordinator/agents.yaml
@@ -272,7 +272,7 @@ agents:
           #
           # --json-schema verified 2026-09-12 (agy 1.2.2 --help: schema string
           # or path). Sentinel injected by CliVendorAdapter._resolve_args.
-          args: ["--mode", "plan", "--dangerously-skip-permissions", "--json-schema", "@review-findings-schema"]
+          args: ["--mode", "plan", "--dangerously-skip-permissions", "--output-format", "json", "--json-schema", "@review-findings-schema"]
         alternative:
           args: ["--mode", "accept-edits", "--dangerously-skip-permissions"]
         quick:
diff --git a/agent-coordinator/cedar/default_policies.cedar b/agent-coordinator/cedar/default_policies.cedar
index e880aa16..a05b1f1f 100644
--- a/agent-coordinator/cedar/default_policies.cedar
+++ b/agent-coordinator/cedar/default_policies.cedar
@@ -152,6 +152,14 @@ permit(
     principal.trust_level >= 3
 };
 
+permit(
+    principal,
+    action == Action::"publish_work_projection",
+    resource
+) when {
+    principal.trust_level >= 3
+};
+
 // ============================================================
 // APPROVAL & POLICY READ — Permit for trust_level >= 1
 // ============================================================
diff --git a/agent-coordinator/cedar/schema.cedarschema b/agent-coordinator/cedar/schema.cedarschema
index f551499f..ef00e012 100644
--- a/agent-coordinator/cedar/schema.cedarschema
+++ b/agent-coordinator/cedar/schema.cedarschema
@@ -125,6 +125,11 @@ action "cleanup_agents" appliesTo {
     resource: Task,
 };
 
+action "publish_work_projection" appliesTo {
+    principal: Agent,
+    resource: Task,
+};
+
 // Approval actions
 action "request_approval" appliesTo {
     principal: Agent,
diff --git a/agent-coordinator/database/migrations/037_autopilot_phase_projection_visibility.sql b/agent-coordinator/database/migrations/037_autopilot_phase_projection_visibility.sql
new file mode 100644
index 00000000..1a39c8e3
--- /dev/null
+++ b/agent-coordinator/database/migrations/037_autopilot_phase_projection_visibility.sql
@@ -0,0 +1,142 @@
+-- 037: make Autopilot phase projections board-visible but never claimable.
+
+BEGIN;
+
+-- Remove historical overloads so every SQL caller reaches the one claim
+-- implementation that enforces issue-row exclusion.
+DROP FUNCTION IF EXISTS claim_task(TEXT, TEXT, TEXT[]);
+DROP FUNCTION IF EXISTS claim_task(TEXT, TEXT, TEXT[], TEXT[], INTEGER);
+
+CREATE OR REPLACE FUNCTION claim_task(
+    p_agent_id TEXT,
+    p_agent_type TEXT,
+    p_task_types TEXT[] DEFAULT NULL,
+    p_agent_archetypes TEXT[] DEFAULT NULL,
+    p_agent_trust_level INTEGER DEFAULT NULL,
+    p_exclude_submitted_by TEXT DEFAULT NULL
+) RETURNS JSONB AS $$
+DECLARE
+    v_task RECORD;
+BEGIN
+    SELECT * INTO v_task
+    FROM work_queue
+    WHERE status = 'pending'
+      -- Issues are projection/display records, never executable work.
+      AND task_type <> 'issue'
+      AND (p_task_types IS NULL OR task_type = ANY(p_task_types))
+      AND (depends_on IS NULL OR NOT EXISTS (
+          SELECT 1 FROM work_queue dep
+          WHERE dep.id = ANY(work_queue.depends_on)
+          AND dep.status NOT IN ('completed')
+      ))
+      AND (
+          agent_requirements IS NULL
+          OR agent_requirements->>'archetype' IS NULL
+          OR p_agent_archetypes IS NULL
+          OR agent_requirements->>'archetype' = ANY(p_agent_archetypes)
+      )
+      AND (
+          agent_requirements IS NULL
+          OR (agent_requirements->>'min_trust_level') IS NULL
+          OR p_agent_trust_level IS NULL
+          OR p_agent_trust_level >= (agent_requirements->>'min_trust_level')::INTEGER
+      )
+      AND (
+          p_exclude_submitted_by IS NULL
+          OR input_data IS NULL
+          OR input_data->>'submitted_by' IS DISTINCT FROM p_exclude_submitted_by
+      )
+    ORDER BY priority ASC, created_at ASC
+    FOR UPDATE SKIP LOCKED
+    LIMIT 1;
+
+    IF NOT FOUND THEN
+        RETURN jsonb_build_object('success', false, 'reason', 'no_tasks_available');
+    END IF;
+
+    UPDATE work_queue
+    SET status = 'claimed', claimed_by = p_agent_id, claimed_at = NOW(),
+        attempt_count = attempt_count + 1
+    WHERE id = v_task.id;
+
+    RETURN jsonb_build_object(
+        'success', true,
+        'task_id', v_task.id,
+        'task_type', v_task.task_type,
+        'description', v_task.description,
+        'input_data', v_task.input_data,
+        'priority', v_task.priority,
+        'deadline', v_task.deadline,
+        'agent_requirements', v_task.agent_requirements
+    );
+END;
+$$ LANGUAGE plpgsql;
+
+CREATE OR REPLACE FUNCTION notify_work_queue_change() RETURNS TRIGGER AS $$
+DECLARE
+    v_change_id TEXT;
+    v_label TEXT;
+BEGIN
+    IF OLD.labels IS DISTINCT FROM NEW.labels
+       AND (
+          'projection:autopilot-phase' = ANY(COALESCE(NEW.labels, ARRAY[]::TEXT[]))
+          OR 'projection:autopilot-phase' = ANY(COALESCE(OLD.labels, ARRAY[]::TEXT[]))
+       )
+    THEN
+        -- Prefer the current correlation label, but removal must remain routable.
+        FOREACH v_label IN ARRAY COALESCE(NEW.labels, ARRAY[]::TEXT[]) LOOP
+            IF v_label LIKE 'change:%' THEN
+                v_change_id := substr(v_label, 8);
+                EXIT;
+            END IF;
+        END LOOP;
+        IF v_change_id IS NULL THEN
+            FOREACH v_label IN ARRAY COALESCE(OLD.labels, ARRAY[]::TEXT[]) LOOP
+                IF v_label LIKE 'change:%' THEN
+                    v_change_id := substr(v_label, 8);
+                    EXIT;
+                END IF;
+            END LOOP;
+        END IF;
+        PERFORM coordinator_notify(
+            'coordinator_task',
+            'projection.labels_changed',
+            NEW.id::TEXT,
+            COALESCE(NEW.claimed_by, 'autopilot'),
+            'Autopilot projection labels changed',
+            v_change_id,
+            jsonb_build_object('snapshot_required', true)
+        );
+    END IF;
+
+    IF OLD.status IS DISTINCT FROM NEW.status
+       AND NEW.status IN ('completed', 'failed', 'claimed', 'running', 'blocked')
+    THEN
+        v_change_id := NULL;
+        FOREACH v_label IN ARRAY COALESCE(NEW.labels, ARRAY[]::TEXT[]) LOOP
+            IF v_label LIKE 'change:%' THEN
+                v_change_id := substr(v_label, 8);
+                EXIT;
+            END IF;
+        END LOOP;
+        PERFORM coordinator_notify(
+            'coordinator_task',
+            'task.' || NEW.status,
+            NEW.id::TEXT,
+            COALESCE(NEW.claimed_by, 'unknown'),
+            'Task ' || NEW.status || ': ' || COALESCE(LEFT(NEW.description, 100), ''),
+            v_change_id,
+            jsonb_build_object('from_status', OLD.status, 'to_status', NEW.status)
+        );
+    END IF;
+    RETURN NEW;
+END;
+$$ LANGUAGE plpgsql;
+
+DROP TRIGGER IF EXISTS trg_work_queue_notify ON work_queue;
+CREATE TRIGGER trg_work_queue_notify
+    AFTER UPDATE ON work_queue
+    FOR EACH ROW
+    EXECUTE FUNCTION notify_work_queue_change();
+
+COMMIT;
diff --git a/agent-coordinator/database/migrations/038_atomic_projection_labels.sql b/agent-coordinator/database/migrations/038_atomic_projection_labels.sql
new file mode 100644
index 00000000..b8815aa8
--- /dev/null
+++ b/agent-coordinator/database/migrations/038_atomic_projection_labels.sql
@@ -0,0 +1,197 @@
+-- 038: atomically maintain Autopilot projection labels with projection head state.
+
+
+BEGIN;
+
+DROP FUNCTION IF EXISTS submit_task(TEXT,TEXT,JSONB,INTEGER,UUID[],TIMESTAMPTZ,JSONB);
+DROP FUNCTION IF EXISTS submit_task(TEXT,TEXT,JSONB,INTEGER,UUID[],TIMESTAMPTZ,JSONB,TEXT[]);
+CREATE OR REPLACE FUNCTION submit_task(
+  p_task_type TEXT, p_description TEXT, p_input_data JSONB DEFAULT NULL,
+  p_priority INTEGER DEFAULT 5, p_depends_on UUID[] DEFAULT NULL,
+  p_deadline TIMESTAMPTZ DEFAULT NULL, p_agent_requirements JSONB DEFAULT NULL,
+  p_projection_labels TEXT[] DEFAULT NULL
+) RETURNS JSONB AS $$
+DECLARE
+  v_id UUID; v_status TEXT; v_created BOOLEAN:=TRUE;
+  v_change TEXT; v_phase TEXT; v_seq INTEGER;
+  v_head_phase TEXT; v_head_seq INTEGER; v_any BOOLEAN; v_complete BOOLEAN;
+BEGIN
+  v_any:=COALESCE(p_input_data ?| ARRAY['change_id','phase','transition_sequence'],FALSE);
+  v_complete:=COALESCE(p_input_data ? 'change_id' AND p_input_data ? 'phase'
+                       AND p_input_data ? 'transition_sequence',FALSE);
+  IF NOT v_any THEN
+    IF p_projection_labels IS NOT NULL THEN
+      RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_labels',
+        'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+    END IF;
+    INSERT INTO work_queue(task_type,description,input_data,priority,depends_on,deadline,agent_requirements)
+    VALUES(p_task_type,p_description,p_input_data,p_priority,p_depends_on,p_deadline,p_agent_requirements)
+    RETURNING id,status INTO v_id,v_status;
+    RETURN jsonb_build_object('success',TRUE,'task_id',v_id,'status',v_status,
+      'created',TRUE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+
+  IF NOT v_complete OR jsonb_typeof(p_input_data->'transition_sequence') IS DISTINCT FROM 'number'
+    OR COALESCE(p_input_data->>'change_id','') !~ '^[a-z0-9][a-z0-9-]{0,127}$'
+    OR COALESCE(p_input_data->>'phase','') <> ALL (ARRAY[
+      'INIT','GATEKEEPER','PLAN','PLAN_ITERATE','PLAN_REVIEW','PLAN_FIX',
+      'IMPLEMENT','IMPL_ITERATE','IMPL_REVIEW','IMPL_FIX','VALIDATE',
+      'VAL_REVIEW','VAL_FIX','SUBMIT_PR','ESCALATE','DONE'])
+    OR COALESCE(p_input_data->>'transition_sequence','') !~ '^(0|[1-9][0-9]{0,9})$'
+    OR (CASE WHEN COALESCE(p_input_data->>'transition_sequence','') ~ '^(0|[1-9][0-9]{0,9})$'
+            THEN (p_input_data->>'transition_sequence')::BIGINT > 2147483647 ELSE FALSE END)
+  THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_key',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+
+  v_change:=p_input_data->>'change_id'; v_phase:=p_input_data->>'phase';
+  v_seq:=(p_input_data->>'transition_sequence')::INTEGER;
+  IF p_projection_labels IS NOT NULL AND (
+    p_task_type <> 'issue'
+    OR p_projection_labels <> ARRAY['change:' || v_change, 'projection:autopilot-phase']
+  ) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_labels',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  PERFORM pg_advisory_xact_lock(hashtextextended(v_change,0));
+  SELECT phase,transition_sequence INTO v_head_phase,v_head_seq
+  FROM work_queue_projection_heads WHERE change_id=v_change FOR UPDATE;
+  IF NOT FOUND THEN
+    INSERT INTO work_queue_projection_heads(change_id,phase,transition_sequence)
+    VALUES(v_change,v_phase,v_seq);
+  ELSIF v_seq < v_head_seq THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','stale_projection','created',FALSE,
+      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  ELSIF v_seq = v_head_seq AND v_phase <> v_head_phase THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','projection_generation_mismatch','created',FALSE,
+      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  ELSIF v_seq > v_head_seq THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','reconciliation_required','created',FALSE,
+      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+
+  INSERT INTO work_queue(task_type,description,input_data,priority,depends_on,deadline,
+                         agent_requirements,labels)
+  VALUES(p_task_type,p_description,p_input_data,p_priority,p_depends_on,p_deadline,
+         p_agent_requirements,COALESCE(p_projection_labels,ARRAY[]::TEXT[]))
+  ON CONFLICT ((input_data ->> 'change_id'),(input_data ->> 'phase'),
+               (input_data ->> 'transition_sequence'))
+  WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
+    AND jsonb_typeof(input_data -> 'transition_sequence') = 'number'
+  DO NOTHING RETURNING id,status INTO v_id,v_status;
+  IF v_id IS NULL THEN
+    v_created:=FALSE;
+    SELECT id,status INTO v_id,v_status FROM work_queue
+    WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
+      AND jsonb_typeof(input_data->'transition_sequence')='number'
+      AND input_data->>'change_id'=v_change AND input_data->>'phase'=v_phase
+      AND input_data->>'transition_sequence'=v_seq::TEXT;
+    IF p_projection_labels IS NOT NULL THEN
+      UPDATE work_queue SET labels=p_projection_labels WHERE id=v_id;
+    END IF;
+  END IF;
+  RETURN jsonb_build_object('success',TRUE,'task_id',v_id,'status',v_status,
+    'created',v_created,'deduplicated',NOT v_created,'cancelled_task_ids','[]'::JSONB);
+END;
+$$ LANGUAGE plpgsql;
+
+DROP FUNCTION IF EXISTS reconcile_work_projection(TEXT,TEXT,INTEGER,TEXT,TEXT,JSONB,INTEGER,JSONB);
+DROP FUNCTION IF EXISTS reconcile_work_projection(TEXT,TEXT,INTEGER,TEXT,TEXT,JSONB,INTEGER,JSONB,TEXT[]);
+CREATE OR REPLACE FUNCTION reconcile_work_projection(
+  p_change_id TEXT, p_phase TEXT, p_transition_sequence INTEGER,
+  p_task_type TEXT, p_description TEXT, p_input_data JSONB,
+  p_priority INTEGER DEFAULT 5, p_agent_requirements JSONB DEFAULT NULL,
+  p_projection_labels TEXT[] DEFAULT NULL
+) RETURNS JSONB AS $$
+DECLARE
+  v_id UUID; v_status TEXT; v_created BOOLEAN:=TRUE;
+  v_head_seq INTEGER; v_cancelled UUID[]:=ARRAY[]::UUID[]; v_payload JSONB;
+BEGIN
+  IF p_change_id !~ '^[a-z0-9][a-z0-9-]{0,127}$'
+    OR p_phase <> ALL (ARRAY[
+      'INIT','GATEKEEPER','PLAN','PLAN_ITERATE','PLAN_REVIEW','PLAN_FIX',
+      'IMPLEMENT','IMPL_ITERATE','IMPL_REVIEW','IMPL_FIX','VALIDATE',
+      'VAL_REVIEW','VAL_FIX','SUBMIT_PR','ESCALATE','DONE'])
+    OR p_transition_sequence IS NULL OR p_transition_sequence < 0
+  THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_key',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  IF p_projection_labels IS NOT NULL AND (
+    p_task_type <> 'issue'
+    OR p_projection_labels <> ARRAY['change:' || p_change_id, 'projection:autopilot-phase']
+  ) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_labels',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  PERFORM pg_advisory_xact_lock(hashtextextended(p_change_id,0));
+  SELECT transition_sequence INTO v_head_seq FROM work_queue_projection_heads
+  WHERE change_id=p_change_id FOR UPDATE;
+  IF FOUND AND p_transition_sequence < v_head_seq THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','stale_projection','created',FALSE,
+      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  INSERT INTO work_queue_projection_heads(change_id,phase,transition_sequence)
+  VALUES(p_change_id,p_phase,p_transition_sequence)
+  ON CONFLICT(change_id) DO UPDATE SET phase=EXCLUDED.phase,
+    transition_sequence=EXCLUDED.transition_sequence,updated_at=NOW();
+
+  v_payload:=(COALESCE(p_input_data,'{}'::JSONB)-'change_id'-'phase'-'transition_sequence')
+    || jsonb_build_object('change_id',p_change_id,'phase',p_phase,
+                          'transition_sequence',p_transition_sequence);
+  WITH cancelled AS (
+    UPDATE work_queue SET status='cancelled',completed_at=NOW(),
+      labels=CASE
+        WHEN p_projection_labels IS NOT NULL AND task_type='issue'
+          AND 'projection:autopilot-phase'=ANY(COALESCE(labels,ARRAY[]::TEXT[]))
+        THEN ARRAY[]::TEXT[] ELSE labels END,
+      result=jsonb_build_object('reason','cancelled_by_projection_reconcile',
+        'change_id',p_change_id,'phase',p_phase,'transition_sequence',p_transition_sequence)
+    WHERE status IN ('pending','claimed','running')
+      AND input_data ? 'change_id' AND input_data->>'change_id'=p_change_id
+      AND NOT (input_data->>'phase'=p_phase
+               AND input_data->>'transition_sequence'=p_transition_sequence::TEXT)
+    RETURNING id)
+  SELECT COALESCE(array_agg(id ORDER BY id::TEXT),ARRAY[]::UUID[])
+    INTO v_cancelled FROM cancelled;
+
+  INSERT INTO work_queue(task_type,description,input_data,priority,agent_requirements,labels)
+  VALUES(p_task_type,p_description,v_payload,p_priority,p_agent_requirements,
+         COALESCE(p_projection_labels,ARRAY[]::TEXT[]))
+  ON CONFLICT ((input_data ->> 'change_id'),(input_data ->> 'phase'),
+               (input_data ->> 'transition_sequence'))
+  WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
+    AND jsonb_typeof(input_data -> 'transition_sequence') = 'number'
+  DO NOTHING RETURNING id,status INTO v_id,v_status;
+  IF v_id IS NULL THEN
+    v_created:=FALSE;
+    SELECT id,status INTO v_id,v_status FROM work_queue
+    WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
+      AND jsonb_typeof(input_data->'transition_sequence')='number'
+      AND input_data->>'change_id'=p_change_id AND input_data->>'phase'=p_phase
+      AND input_data->>'transition_sequence'=p_transition_sequence::TEXT;
+  END IF;
+  IF p_projection_labels IS NOT NULL THEN
+    UPDATE work_queue SET labels=ARRAY[]::TEXT[]
+    WHERE id<>v_id AND task_type='issue'
+      AND input_data ? 'change_id' AND input_data ? 'phase'
+      AND input_data ? 'transition_sequence'
+      AND input_data->>'change_id'=p_change_id
+      AND 'projection:autopilot-phase'=ANY(COALESCE(labels,ARRAY[]::TEXT[]));
+    UPDATE work_queue SET labels=p_projection_labels WHERE id=v_id;
+  END IF;
+  RETURN jsonb_build_object('success',TRUE,'task_id',v_id,'status',v_status,
+    'created',v_created,'deduplicated',NOT v_created,'cancelled_task_ids',to_jsonb(v_cancelled));
+END;
+$$ LANGUAGE plpgsql;
+
+-- Repair only terminal rows carrying the reserved projection marker and complete
+-- projection identity. Ordinary change-labelled issues are not selected.
+UPDATE work_queue SET labels=ARRAY[]::TEXT[]
+WHERE status='cancelled' AND task_type='issue'
+  AND input_data ? 'change_id' AND input_data ? 'phase'
+  AND input_data ? 'transition_sequence'
+  AND 'projection:autopilot-phase'=ANY(COALESCE(labels,ARRAY[]::TEXT[]));
+
+COMMIT;
diff --git a/agent-coordinator/database/migrations/039_projection_integrity_and_insert_events.sql b/agent-coordinator/database/migrations/039_projection_integrity_and_insert_events.sql
new file mode 100644
index 00000000..c3038ecb
--- /dev/null
+++ b/agent-coordinator/database/migrations/039_projection_integrity_and_insert_events.sql
@@ -0,0 +1,577 @@
+-- 039: close projection collision/replay gaps and enforce ownership integrity.
+
+BEGIN;
+
+CREATE TABLE IF NOT EXISTS work_queue_projection_ownership (
+  task_id UUID PRIMARY KEY REFERENCES work_queue(id) ON DELETE CASCADE,
+  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
+);
+
+UPDATE agent_profiles
+SET allowed_operations = ARRAY(
+      SELECT DISTINCT operation
+      FROM unnest(allowed_operations || ARRAY['publish_work_projection']) operation
+      ORDER BY operation
+    ),
+    updated_at = NOW()
+WHERE trust_level >= 3;
+
+INSERT INTO cedar_policies (name, policy_text, description, priority, enabled)
+VALUES (
+  'work-projection-operations',
+  'permit(principal, action == Action::"publish_work_projection", resource) when { principal.trust_level >= 3 };',
+  'Allow only elevated agents to publish authoritative work projections',
+  30,
+  TRUE
+)
+ON CONFLICT (name) DO UPDATE SET
+  policy_text=EXCLUDED.policy_text,
+  description=EXCLUDED.description,
+  priority=EXCLUDED.priority,
+  enabled=EXCLUDED.enabled,
+  updated_at=NOW();
+
+-- Ownership cannot be inferred safely from mutable payloads or labels. Existing
+-- 038-era rows remain unowned and therefore fail closed until a database
+-- administrator verifies provenance out of band and explicitly registers every complete
+-- keyed row for the change, including cancelled historical generations; adopting
+-- only the current row is insufficient.
+COMMENT ON TABLE work_queue_projection_ownership IS
+  'Database-owned Autopilot projection identities. Upgrade from 038: after '
+  'verifying provenance out of band, a database administrator must adopt every verified keyed row for the change, including cancelled historical generations; adopting only the current row is insufficient; '
+  'with INSERT INTO work_queue_projection_ownership(task_id) VALUES (<verified-id>). '
+  'Runtime projection functions never infer ownership from work_queue fields.';
+
+DROP FUNCTION IF EXISTS submit_task(TEXT,TEXT,JSONB,INTEGER,UUID[],TIMESTAMPTZ,JSONB);
+DROP FUNCTION IF EXISTS submit_task(TEXT,TEXT,JSONB,INTEGER,UUID[],TIMESTAMPTZ,JSONB,TEXT[]);
+CREATE OR REPLACE FUNCTION submit_task(
+  p_task_type TEXT, p_description TEXT, p_input_data JSONB DEFAULT NULL,
+  p_priority INTEGER DEFAULT 5, p_depends_on UUID[] DEFAULT NULL,
+  p_deadline TIMESTAMPTZ DEFAULT NULL, p_agent_requirements JSONB DEFAULT NULL,
+  p_projection_labels TEXT[] DEFAULT NULL
+) RETURNS JSONB AS $$
+DECLARE
+  v_id UUID; v_status TEXT; v_created BOOLEAN:=TRUE;
+  v_change TEXT; v_phase TEXT; v_seq INTEGER;
+  v_head_phase TEXT; v_head_seq INTEGER; v_any BOOLEAN; v_complete BOOLEAN;
+  v_head_missing BOOLEAN:=FALSE; v_existing_task_type TEXT;
+  v_existing_owned BOOLEAN:=FALSE;
+  v_reactivated INTEGER:=0;
+BEGIN
+  v_any:=COALESCE(p_input_data ?| ARRAY['change_id','phase','transition_sequence'],FALSE);
+  v_complete:=COALESCE(p_input_data ? 'change_id' AND p_input_data ? 'phase'
+                       AND p_input_data ? 'transition_sequence',FALSE);
+  IF NOT v_any THEN
+    IF p_projection_labels IS NOT NULL THEN
+      RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_labels',
+        'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+    END IF;
+    INSERT INTO work_queue(task_type,description,input_data,priority,depends_on,deadline,agent_requirements)
+    VALUES(p_task_type,p_description,p_input_data,p_priority,p_depends_on,p_deadline,p_agent_requirements)
+    RETURNING id,status INTO v_id,v_status;
+    RETURN jsonb_build_object('success',TRUE,'task_id',v_id,'status',v_status,
+      'created',TRUE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+
+  IF NOT v_complete OR jsonb_typeof(p_input_data->'transition_sequence') IS DISTINCT FROM 'number'
+    OR COALESCE(p_input_data->>'change_id','') !~ '^[a-z0-9][a-z0-9-]{0,127}$'
+    OR COALESCE(p_input_data->>'phase','') <> ALL (ARRAY[
+      'INIT','GATEKEEPER','PLAN','PLAN_ITERATE','PLAN_REVIEW','PLAN_FIX',
+      'IMPLEMENT','IMPL_ITERATE','IMPL_REVIEW','IMPL_FIX','VALIDATE',
+      'VAL_REVIEW','VAL_FIX','SUBMIT_PR','ESCALATE','DONE'])
+    OR COALESCE(p_input_data->>'transition_sequence','') !~ '^(0|[1-9][0-9]{0,9})$'
+    OR (CASE WHEN COALESCE(p_input_data->>'transition_sequence','') ~ '^(0|[1-9][0-9]{0,9})$'
+            THEN (p_input_data->>'transition_sequence')::BIGINT > 2147483647 ELSE FALSE END)
+  THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_key',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+
+  v_change:=p_input_data->>'change_id'; v_phase:=p_input_data->>'phase';
+  v_seq:=(p_input_data->>'transition_sequence')::INTEGER;
+  IF p_projection_labels IS NOT NULL AND (
+    p_task_type <> 'issue'
+    OR p_projection_labels <> ARRAY['change:' || v_change, 'projection:autopilot-phase']
+  ) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_labels',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  PERFORM pg_advisory_xact_lock(hashtextextended(v_change,0));
+  IF EXISTS (
+    SELECT 1 FROM work_queue AS candidate
+    WHERE 'projection:autopilot-phase'=ANY(COALESCE(candidate.labels,ARRAY[]::TEXT[]))
+      AND (
+        candidate.input_data->>'change_id'=v_change
+        OR 'change:' || v_change=ANY(COALESCE(candidate.labels,ARRAY[]::TEXT[]))
+      )
+      AND NOT EXISTS (
+        SELECT 1 FROM work_queue_projection_ownership AS ownership
+        WHERE ownership.task_id=candidate.id
+      )
+  ) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','projection_key_collision',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  IF p_projection_labels IS NOT NULL AND EXISTS (
+    SELECT 1 FROM work_queue AS candidate
+    WHERE candidate.input_data ? 'change_id'
+      AND candidate.input_data ? 'phase'
+      AND candidate.input_data ? 'transition_sequence'
+      AND jsonb_typeof(candidate.input_data->'transition_sequence')='number'
+      AND candidate.input_data->>'change_id'=v_change
+      AND NOT EXISTS (
+        SELECT 1 FROM work_queue_projection_ownership AS ownership
+        WHERE ownership.task_id=candidate.id
+      )
+  ) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','projection_key_collision',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  IF p_projection_labels IS NULL AND EXISTS (
+    SELECT 1 FROM work_queue_projection_ownership AS ownership
+    JOIN work_queue AS owned ON owned.id=ownership.task_id
+    WHERE owned.input_data->>'change_id'=v_change
+  ) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','projection_mode_mismatch',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  SELECT phase,transition_sequence INTO v_head_phase,v_head_seq
+  FROM work_queue_projection_heads WHERE change_id=v_change FOR UPDATE;
+  IF NOT FOUND THEN
+    v_head_missing:=TRUE;
+  ELSIF v_seq < v_head_seq THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','stale_projection','created',FALSE,
+      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  ELSIF v_seq = v_head_seq AND v_phase <> v_head_phase THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','projection_generation_mismatch','created',FALSE,
+      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  ELSIF v_seq > v_head_seq THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','reconciliation_required','created',FALSE,
+      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+
+  INSERT INTO work_queue(task_type,description,input_data,priority,depends_on,deadline,
+                         agent_requirements,labels)
+  VALUES(p_task_type,p_description,p_input_data,p_priority,p_depends_on,p_deadline,
+         p_agent_requirements,ARRAY[]::TEXT[])
+  ON CONFLICT ((input_data ->> 'change_id'),(input_data ->> 'phase'),
+               (input_data ->> 'transition_sequence'))
+  WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
+    AND jsonb_typeof(input_data -> 'transition_sequence') = 'number'
+  DO NOTHING RETURNING id,status INTO v_id,v_status;
+  IF v_id IS NULL THEN
+    v_created:=FALSE;
+    SELECT id,status,task_type,
+      (EXISTS (SELECT 1 FROM work_queue_projection_ownership AS ownership
+               WHERE ownership.task_id=work_queue.id))
+      INTO v_id,v_status,v_existing_task_type,v_existing_owned FROM work_queue
+    WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
+      AND jsonb_typeof(input_data->'transition_sequence')='number'
+      AND input_data->>'change_id'=v_change AND input_data->>'phase'=v_phase
+      AND input_data->>'transition_sequence'=v_seq::TEXT;
+    IF p_projection_labels IS NOT NULL AND p_task_type='issue'
+       AND (v_existing_task_type<>'issue' OR NOT v_existing_owned) THEN
+      RETURN jsonb_build_object('success',FALSE,'reason','projection_key_collision',
+        'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+    END IF;
+  END IF;
+  IF p_projection_labels IS NOT NULL THEN
+    INSERT INTO work_queue_projection_ownership(task_id) VALUES(v_id)
+    ON CONFLICT DO NOTHING;
+  END IF;
+  IF v_head_missing THEN
+    INSERT INTO work_queue_projection_heads(change_id,phase,transition_sequence)
+    VALUES(v_change,v_phase,v_seq);
+  END IF;
+  IF p_projection_labels IS NOT NULL THEN
+    UPDATE work_queue SET labels=ARRAY[]::TEXT[]
+    WHERE id<>v_id AND task_type='issue'
+      AND input_data ? 'change_id' AND input_data ? 'phase'
+      AND input_data ? 'transition_sequence'
+      AND input_data->>'change_id'=v_change
+      AND EXISTS (SELECT 1 FROM work_queue_projection_ownership AS ownership
+                  WHERE ownership.task_id=work_queue.id)
+      AND 'projection:autopilot-phase'=ANY(COALESCE(labels,ARRAY[]::TEXT[]));
+    UPDATE work_queue SET labels=p_projection_labels WHERE id=v_id;
+    UPDATE work_queue SET
+      status='pending', claimed_by=NULL, claimed_at=NULL, started_at=NULL,
+      completed_at=NULL, result=NULL, error_message=NULL,
+      closed_at=NULL, close_reason=NULL, attempt_count=0
+    WHERE id=v_id
+      AND EXISTS (SELECT 1 FROM work_queue_projection_ownership AS ownership
+                  WHERE ownership.task_id=work_queue.id)
+      AND status IN ('cancelled','completed','failed');
+    GET DIAGNOSTICS v_reactivated = ROW_COUNT;
+    IF v_reactivated > 0 THEN
+      PERFORM coordinator_notify(
+        'coordinator_task', 'projection.labels_changed', v_id::TEXT,
+        'autopilot', 'Autopilot projection reactivated', v_change,
+        jsonb_build_object('snapshot_required',TRUE)
+      );
+    END IF;
+    SELECT status INTO v_status FROM work_queue WHERE id=v_id;
+  END IF;
+  RETURN jsonb_build_object('success',TRUE,'task_id',v_id,'status',v_status,
+    'created',v_created,'deduplicated',NOT v_created,'cancelled_task_ids','[]'::JSONB);
+END;
+$$ LANGUAGE plpgsql;
+
+DROP FUNCTION IF EXISTS reconcile_work_projection(TEXT,TEXT,INTEGER,TEXT,TEXT,JSONB,INTEGER,JSONB);
+DROP FUNCTION IF EXISTS reconcile_work_projection(TEXT,TEXT,INTEGER,TEXT,TEXT,JSONB,INTEGER,JSONB,TEXT[]);
+CREATE OR REPLACE FUNCTION reconcile_work_projection(
+  p_change_id TEXT, p_phase TEXT, p_transition_sequence INTEGER,
+  p_task_type TEXT, p_description TEXT, p_input_data JSONB,
+  p_priority INTEGER DEFAULT 5, p_agent_requirements JSONB DEFAULT NULL,
+  p_projection_labels TEXT[] DEFAULT NULL
+) RETURNS JSONB AS $$
+DECLARE
+  v_id UUID; v_status TEXT; v_created BOOLEAN:=TRUE;
+  v_head_seq INTEGER; v_cancelled UUID[]:=ARRAY[]::UUID[]; v_payload JSONB;
+  v_existing_task_type TEXT; v_existing_owned BOOLEAN:=FALSE;
+  v_reactivated INTEGER:=0;
+BEGIN
+  IF p_change_id !~ '^[a-z0-9][a-z0-9-]{0,127}$'
+    OR p_phase <> ALL (ARRAY[
+      'INIT','GATEKEEPER','PLAN','PLAN_ITERATE','PLAN_REVIEW','PLAN_FIX',
+      'IMPLEMENT','IMPL_ITERATE','IMPL_REVIEW','IMPL_FIX','VALIDATE',
+      'VAL_REVIEW','VAL_FIX','SUBMIT_PR','ESCALATE','DONE'])
+    OR p_transition_sequence IS NULL OR p_transition_sequence < 0
+  THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_key',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  IF p_projection_labels IS NOT NULL AND (
+    p_task_type <> 'issue'
+    OR p_projection_labels <> ARRAY['change:' || p_change_id, 'projection:autopilot-phase']
+  ) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','invalid_projection_labels',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  PERFORM pg_advisory_xact_lock(hashtextextended(p_change_id,0));
+  IF EXISTS (
+    SELECT 1 FROM work_queue AS candidate
+    WHERE 'projection:autopilot-phase'=ANY(COALESCE(candidate.labels,ARRAY[]::TEXT[]))
+      AND (
+        candidate.input_data->>'change_id'=p_change_id
+        OR 'change:' || p_change_id=ANY(COALESCE(candidate.labels,ARRAY[]::TEXT[]))
+      )
+      AND NOT EXISTS (
+        SELECT 1 FROM work_queue_projection_ownership AS ownership
+        WHERE ownership.task_id=candidate.id
+      )
+  ) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','projection_key_collision',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  IF p_projection_labels IS NOT NULL AND EXISTS (
+    SELECT 1 FROM work_queue AS candidate
+    WHERE candidate.input_data ? 'change_id'
+      AND candidate.input_data ? 'phase'
+      AND candidate.input_data ? 'transition_sequence'
+      AND jsonb_typeof(candidate.input_data->'transition_sequence')='number'
+      AND candidate.input_data->>'change_id'=p_change_id
+      AND NOT EXISTS (
+        SELECT 1 FROM work_queue_projection_ownership AS ownership
+        WHERE ownership.task_id=candidate.id
+      )
+  ) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','projection_key_collision',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  IF p_projection_labels IS NULL AND EXISTS (
+    SELECT 1 FROM work_queue_projection_ownership AS ownership
+    JOIN work_queue AS owned ON owned.id=ownership.task_id
+    WHERE owned.input_data->>'change_id'=p_change_id
+  ) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','projection_mode_mismatch',
+      'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+  SELECT transition_sequence INTO v_head_seq FROM work_queue_projection_heads
+  WHERE change_id=p_change_id FOR UPDATE;
+  IF FOUND AND p_transition_sequence < v_head_seq THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','stale_projection','created',FALSE,
+      'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+  END IF;
+
+  v_payload:=(COALESCE(p_input_data,'{}'::JSONB)-'change_id'-'phase'-'transition_sequence')
+    || jsonb_build_object('change_id',p_change_id,'phase',p_phase,
+                          'transition_sequence',p_transition_sequence);
+  INSERT INTO work_queue(task_type,description,input_data,priority,agent_requirements,labels)
+  VALUES(p_task_type,p_description,v_payload,p_priority,p_agent_requirements,
+         ARRAY[]::TEXT[])
+  ON CONFLICT ((input_data ->> 'change_id'),(input_data ->> 'phase'),
+               (input_data ->> 'transition_sequence'))
+  WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
+    AND jsonb_typeof(input_data -> 'transition_sequence') = 'number'
+  DO NOTHING RETURNING id,status INTO v_id,v_status;
+  IF v_id IS NULL THEN
+    v_created:=FALSE;
+    SELECT id,status,task_type,
+      (EXISTS (SELECT 1 FROM work_queue_projection_ownership AS ownership
+               WHERE ownership.task_id=work_queue.id))
+      INTO v_id,v_status,v_existing_task_type,v_existing_owned FROM work_queue
+    WHERE input_data ? 'change_id' AND input_data ? 'phase' AND input_data ? 'transition_sequence'
+      AND jsonb_typeof(input_data->'transition_sequence')='number'
+      AND input_data->>'change_id'=p_change_id AND input_data->>'phase'=p_phase
+      AND input_data->>'transition_sequence'=p_transition_sequence::TEXT;
+    IF p_projection_labels IS NOT NULL AND p_task_type='issue'
+       AND (v_existing_task_type<>'issue' OR NOT v_existing_owned) THEN
+      RETURN jsonb_build_object('success',FALSE,'reason','projection_key_collision',
+        'created',FALSE,'deduplicated',FALSE,'cancelled_task_ids','[]'::JSONB);
+    END IF;
+  END IF;
+  IF p_projection_labels IS NOT NULL THEN
+    INSERT INTO work_queue_projection_ownership(task_id) VALUES(v_id)
+    ON CONFLICT DO NOTHING;
+  END IF;
+
+  INSERT INTO work_queue_projection_heads(change_id,phase,transition_sequence)
+  VALUES(p_change_id,p_phase,p_transition_sequence)
+  ON CONFLICT(change_id) DO UPDATE SET phase=EXCLUDED.phase,
+    transition_sequence=EXCLUDED.transition_sequence,updated_at=NOW();
+
+  IF p_projection_labels IS NULL THEN
+    WITH cancelled AS (
+      UPDATE work_queue SET status='cancelled',completed_at=NOW(),
+        result=jsonb_build_object('reason','cancelled_by_projection_reconcile',
+          'change_id',p_change_id,'phase',p_phase,'transition_sequence',p_transition_sequence)
+      WHERE status IN ('pending','claimed','running')
+        AND input_data ? 'change_id' AND input_data->>'change_id'=p_change_id
+        AND NOT (input_data->>'phase'=p_phase
+                 AND input_data->>'transition_sequence'=p_transition_sequence::TEXT)
+      RETURNING id)
+    SELECT COALESCE(array_agg(id ORDER BY id::TEXT),ARRAY[]::UUID[])
+      INTO v_cancelled FROM cancelled;
+  ELSE
+    WITH cancelled AS (
+      UPDATE work_queue SET status='cancelled',completed_at=NOW(),
+        labels=CASE
+          WHEN task_type='issue'
+            AND 'projection:autopilot-phase'=ANY(COALESCE(labels,ARRAY[]::TEXT[]))
+          THEN ARRAY[]::TEXT[] ELSE labels END,
+        result=jsonb_build_object('reason','cancelled_by_projection_reconcile',
+          'change_id',p_change_id,'phase',p_phase,'transition_sequence',p_transition_sequence)
+      WHERE status IN ('pending','claimed','running')
+        AND EXISTS (
+          SELECT 1 FROM work_queue_projection_ownership AS ownership
+          WHERE ownership.task_id=work_queue.id
+        )
+        AND input_data ? 'change_id' AND input_data->>'change_id'=p_change_id
+        AND NOT (input_data->>'phase'=p_phase
+                 AND input_data->>'transition_sequence'=p_transition_sequence::TEXT)
+      RETURNING id)
+    SELECT COALESCE(array_agg(id ORDER BY id::TEXT),ARRAY[]::UUID[])
+      INTO v_cancelled FROM cancelled;
+  END IF;
+
+  IF p_projection_labels IS NOT NULL THEN
+    UPDATE work_queue SET labels=ARRAY[]::TEXT[]
+    WHERE id<>v_id AND task_type='issue'
+      AND input_data ? 'change_id' AND input_data ? 'phase'
+      AND input_data ? 'transition_sequence'
+      AND input_data->>'change_id'=p_change_id
+      AND EXISTS (SELECT 1 FROM work_queue_projection_ownership AS ownership
+                  WHERE ownership.task_id=work_queue.id)
+      AND 'projection:autopilot-phase'=ANY(COALESCE(labels,ARRAY[]::TEXT[]));
+    UPDATE work_queue SET labels=p_projection_labels WHERE id=v_id;
+    UPDATE work_queue SET
+      status='pending', claimed_by=NULL, claimed_at=NULL, started_at=NULL,
+      completed_at=NULL, result=NULL, error_message=NULL,
+      closed_at=NULL, close_reason=NULL, attempt_count=0
+    WHERE id=v_id
+      AND EXISTS (SELECT 1 FROM work_queue_projection_ownership AS ownership
+                  WHERE ownership.task_id=work_queue.id)
+      AND status IN ('cancelled','completed','failed');
+    GET DIAGNOSTICS v_reactivated = ROW_COUNT;
+    IF v_reactivated > 0 THEN
+      PERFORM coordinator_notify(
+        'coordinator_task', 'projection.labels_changed', v_id::TEXT,
+        'autopilot', 'Autopilot projection reactivated', p_change_id,
+        jsonb_build_object('snapshot_required',TRUE)
+      );
+    END IF;
+    SELECT status INTO v_status FROM work_queue WHERE id=v_id;
+  END IF;
+  RETURN jsonb_build_object('success',TRUE,'task_id',v_id,'status',v_status,
+    'created',v_created,'deduplicated',NOT v_created,'cancelled_task_ids',to_jsonb(v_cancelled));
+END;
+$$ LANGUAGE plpgsql;
+
+CREATE OR REPLACE FUNCTION enforce_projection_label_ownership() RETURNS TRIGGER AS $ownership$
+BEGIN
+  IF 'projection:autopilot-phase'=ANY(COALESCE(NEW.labels,ARRAY[]::TEXT[]))
+     AND NOT EXISTS (
+       SELECT 1 FROM work_queue_projection_ownership AS ownership
+       WHERE ownership.task_id=NEW.id
+     )
+  THEN
+    RAISE EXCEPTION 'reserved_projection_label'
+      USING ERRCODE='42501';
+  END IF;
+  RETURN NEW;
+END;
+$ownership$ LANGUAGE plpgsql;
+
+DROP TRIGGER IF EXISTS trg_work_queue_projection_label_ownership ON work_queue;
+CREATE TRIGGER trg_work_queue_projection_label_ownership
+  BEFORE INSERT OR UPDATE OF labels ON work_queue
+  FOR EACH ROW
+  EXECUTE FUNCTION enforce_projection_label_ownership();
+
+CREATE OR REPLACE FUNCTION mutate_issue_if_unowned(
+  p_issue_id UUID,
+  p_patch JSONB
+) RETURNS JSONB AS $mutation$
+DECLARE
+  v_issue work_queue%ROWTYPE;
+BEGIN
+  SELECT * INTO v_issue FROM work_queue
+  WHERE id=p_issue_id AND task_type='issue'
+  FOR UPDATE;
+  IF NOT FOUND THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','issue_not_found');
+  END IF;
+  IF EXISTS (
+    SELECT 1 FROM work_queue_projection_ownership AS ownership
+    WHERE ownership.task_id=p_issue_id
+  ) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','projection_issue_immutable');
+  END IF;
+  IF 'projection:autopilot-phase'=ANY(COALESCE(v_issue.labels,ARRAY[]::TEXT[])) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','reserved_projection_label');
+  END IF;
+  IF p_patch ? 'labels' AND EXISTS (
+    SELECT 1 FROM jsonb_array_elements_text(p_patch->'labels') AS label(value)
+    WHERE label.value='projection:autopilot-phase'
+  ) THEN
+    RETURN jsonb_build_object('success',FALSE,'reason','reserved_projection_label');
+  END IF;
+
+  UPDATE work_queue SET
+    description=CASE WHEN p_patch ? 'description' THEN p_patch->>'description' ELSE description END,
+    status=CASE WHEN p_patch ? 'status' THEN p_patch->>'status' ELSE status END,
+    priority=CASE WHEN p_patch ? 'priority' THEN (p_patch->>'priority')::INTEGER ELSE priority END,
+    labels=CASE WHEN p_patch ? 'labels' THEN ARRAY(
+      SELECT jsonb_array_elements_text(p_patch->'labels')
+    ) ELSE labels END,
+    assignee=CASE WHEN p_patch ? 'assignee' THEN p_patch->>'assignee' ELSE assignee END,
+    issue_type=CASE WHEN p_patch ? 'issue_type' THEN p_patch->>'issue_type' ELSE issue_type END,
+    metadata=CASE WHEN p_patch ? 'metadata' THEN p_patch->'metadata' ELSE metadata END,
+    completed_at=CASE WHEN p_patch ? 'completed_at' THEN (p_patch->>'completed_at')::TIMESTAMPTZ ELSE completed_at END,
+    closed_at=CASE WHEN p_patch ? 'closed_at' THEN (p_patch->>'closed_at')::TIMESTAMPTZ ELSE closed_at END,
+    close_reason=CASE WHEN p_patch ? 'close_reason' THEN p_patch->>'close_reason' ELSE close_reason END
+  WHERE id=p_issue_id
+  RETURNING * INTO v_issue;
+
+  RETURN jsonb_build_object('success',TRUE,'issue',to_jsonb(v_issue));
+END;
+$mutation$ LANGUAGE plpgsql;
+
+CREATE OR REPLACE FUNCTION close_issues_if_unowned(
+  p_request JSONB
+) RETURNS JSONB AS $batch$
+DECLARE
+  p_issue_ids UUID[]:=ARRAY(
+    SELECT value::UUID
+    FROM jsonb_array_elements_text(p_request->'issue_ids') AS item(value)
+  );
+  p_closed_at TIMESTAMPTZ:=(p_request->>'closed_at')::TIMESTAMPTZ;
+  p_reason TEXT:=p_request->>'reason';
+  v_reason TEXT;
+  v_issues JSONB;
+BEGIN
+  IF COALESCE(array_length(p_issue_ids, 1), 0)=0 THEN
+    RETURN jsonb_build_object('success',TRUE,'issues','[]'::JSONB);
+  END IF;
+
+  -- Lock the complete batch in UUID order before checking any ownership
+  -- boundary. Either every ordinary issue closes, or none of them do.
+  PERFORM issue.id FROM work_queue AS issue
+  WHERE issue.id=ANY(p_issue_ids) AND issue.task_type='issue'
+  ORDER BY issue.id
+  FOR UPDATE;
+
+  SELECT CASE
+    WHEN ownership.task_id IS NOT NULL THEN 'projection_issue_immutable'
+    ELSE 'reserved_projection_label'
+  END INTO v_reason
+  FROM unnest(p_issue_ids) WITH ORDINALITY AS requested(id, ordinal)
+  JOIN work_queue AS issue
+    ON issue.id=requested.id AND issue.task_type='issue'
+  LEFT JOIN work_queue_projection_ownership AS ownership
+    ON ownership.task_id=issue.id
+  WHERE ownership.task_id IS NOT NULL
+     OR 'projection:autopilot-phase'=ANY(
+       COALESCE(issue.labels,ARRAY[]::TEXT[])
+     )
+  ORDER BY requested.ordinal
+  LIMIT 1;
+
+  IF FOUND THEN
+    RETURN jsonb_build_object('success',FALSE,'reason',v_reason);
+  END IF;
+
+  UPDATE work_queue AS issue SET
+    status='completed',
+    completed_at=p_closed_at,
+    closed_at=p_closed_at,
+    close_reason=CASE
+      WHEN p_reason IS NOT NULL THEN p_reason ELSE issue.close_reason
+    END
+  WHERE issue.id=ANY(p_issue_ids) AND issue.task_type='issue';
+
+  SELECT COALESCE(
+    jsonb_agg(to_jsonb(issue) ORDER BY requested.ordinal),
+    '[]'::JSONB
+  ) INTO v_issues
+  FROM unnest(p_issue_ids) WITH ORDINALITY AS requested(id, ordinal)
+  JOIN work_queue AS issue
+    ON issue.id=requested.id AND issue.task_type='issue';
+
+  RETURN jsonb_build_object('success',TRUE,'issues',v_issues);
+END;
+$batch$ LANGUAGE plpgsql;
+
+CREATE OR REPLACE FUNCTION notify_projection_insert() RETURNS TRIGGER AS $projection$
+DECLARE
+  v_change_id TEXT;
+  v_label TEXT;
+BEGIN
+  IF 'projection:autopilot-phase'=ANY(COALESCE(NEW.labels,ARRAY[]::TEXT[])) THEN
+    FOREACH v_label IN ARRAY NEW.labels LOOP
+      IF v_label LIKE 'change:%' THEN
+        v_change_id:=substr(v_label,8);
+        EXIT;
+      END IF;
+    END LOOP;
+    PERFORM coordinator_notify(
+      'coordinator_task',
+      'projection.labels_changed',
+      NEW.id::TEXT,
+      COALESCE(NEW.claimed_by,'autopilot'),
+      'Autopilot projection labels added',
+      v_change_id,
+      jsonb_build_object('snapshot_required',TRUE)
+    );
+  END IF;
+  RETURN NEW;
+END;
+$projection$ LANGUAGE plpgsql;
+
+DROP TRIGGER IF EXISTS trg_work_queue_projection_insert_notify ON work_queue;
+CREATE TRIGGER trg_work_queue_projection_insert_notify
+  AFTER INSERT ON work_queue
+  FOR EACH ROW
+  EXECUTE FUNCTION notify_projection_insert();
+
+-- Repair only terminal rows carrying the reserved projection marker and complete
+-- projection identity. Ordinary change-labelled issues are not selected.
+UPDATE work_queue SET labels=ARRAY[]::TEXT[]
+WHERE status='cancelled' AND task_type='issue'
+  AND input_data ? 'change_id' AND input_data ? 'phase'
+  AND input_data ? 'transition_sequence'
+  AND EXISTS (SELECT 1 FROM work_queue_projection_ownership AS ownership
+              WHERE ownership.task_id=work_queue.id)
+  AND 'projection:autopilot-phase'=ANY(COALESCE(labels,ARRAY[]::TEXT[]));
+
+COMMIT;
diff --git a/agent-coordinator/src/agents_config.py b/agent-coordinator/src/agents_config.py
index f9e8c3f9..c42ee622 100644
--- a/agent-coordinator/src/agents_config.py
+++ b/agent-coordinator/src/agents_config.py
@@ -1048,6 +1048,7 @@ TRUST_DERIVED_OPERATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
             "run_pre_merge_checks",
             "mark_merged",
             "remove_from_merge_queue",
+            "publish_work_projection",
         ),
     ),
 )
diff --git a/agent-coordinator/src/coordination_api.py b/agent-coordinator/src/coordination_api.py
index 5bb13ba1..349a9ee7 100644
--- a/agent-coordinator/src/coordination_api.py
+++ b/agent-coordinator/src/coordination_api.py
@@ -14,7 +14,7 @@ from __future__ import annotations
 import os
 import sys
 import time
-from typing import Any, Literal
+from typing import Annotated, Any, Literal
 from uuid import UUID
 
 from fastapi import Depends, FastAPI, Header, HTTPException, Request
@@ -95,7 +95,9 @@ class _CodeSearchProblemError(Exception):
 _PROJECTION_CONFLICTS = {
     "stale_projection",
     "projection_generation_mismatch",
+    "projection_mode_mismatch",
     "reconciliation_required",
+    "projection_key_collision",
 }
 _PROJECTION_FORBIDDEN = {
     "operation_not_permitted",
@@ -106,6 +108,7 @@ _PROJECTION_INVALID = {
     "invalid_projection_key",
     "reserved_projection_key",
     "guardrail_denied",
+    "invalid_projection_labels",
 }
 
 
@@ -127,6 +130,8 @@ def _projection_mutation_payload(result: Any) -> dict[str, Any]:
         if result.reason in _PROJECTION_INVALID:
             raise _ProjectionProblemError(result.reason, status=422)
         raise _ProjectionProblemError(result.reason or "projection_mutation_failed", status=422)
+    if result.task_id is None:
+        raise _ProjectionProblemError("canonical_task_id_missing", status=422)
     return {
         "success": True,
         "task_id": str(result.task_id),
@@ -213,12 +218,23 @@ class ProjectionKeyRequest(BaseModel):
     transition_sequence: StrictInt = Field(ge=0, le=2147483647)
 
 
+ProjectionChangeLabel = Annotated[
+    str,
+    Field(max_length=135, pattern=r"^change:[a-z0-9][a-z0-9-]{0,127}$"),
+]
+ProjectionLabels = tuple[
+    ProjectionChangeLabel,
+    Literal["projection:autopilot-phase"],
+]
+
+
 class WorkSubmitRequest(BaseModel):
     model_config = ConfigDict(extra="forbid")
 
     task_type: str = Field(min_length=1)
     task_description: str = Field(min_length=1)
     projection_key: ProjectionKeyRequest | None = None
+    projection_labels: ProjectionLabels | None = None
     input_data: dict[str, Any] | None = None
     priority: int = Field(default=5, ge=1, le=10)
     depends_on: list[UUID] | None = None
@@ -229,6 +245,7 @@ class WorkReconcileRequest(BaseModel):
     model_config = ConfigDict(extra="forbid")
 
     projection_key: ProjectionKeyRequest
+    projection_labels: ProjectionLabels | None = None
     task_type: str = Field(min_length=1)
     task_description: str = Field(min_length=1)
     input_data: dict[str, Any] | None = None
@@ -376,14 +393,17 @@ class StatusReportRequest(BaseModel):
     # (defense in depth) and the report_status.py client-side validation.
     # Older clients omit this field (no 400 — backward compatible) — the
     # ``| None`` admits both omission and explicit ``null``.
-    phase_archetype: Literal[
-        "architect",
-        "reviewer",
-        "implementer",
-        "analyst",
-        "runner",
-        "gatekeeper",
-    ] | None = Field(default=None)
+    phase_archetype: (
+        Literal[
+            "architect",
+            "reviewer",
+            "implementer",
+            "analyst",
+            "runner",
+            "gatekeeper",
+        ]
+        | None
+    ) = Field(default=None)
 
 
 class ResolveForPhaseRequest(BaseModel):
@@ -500,6 +520,7 @@ class AffectedTestsRequest(BaseModel):
 
 # ── Kanban-viz request models ──────────────────────────────────────────────
 
+
 class EventsAuthRequest(BaseModel):
     change_ids: list[str] = Field(min_length=1, description="change-ids to scope the token")
     ttl: int = Field(default=300, ge=1, le=600, description="Token TTL in seconds")
@@ -616,11 +637,7 @@ def resolve_identity(
             status_code=403,
             detail="API key is not permitted to act as requested agent_id",
         )
-    if (
-        bound_agent_type
-        and request_agent_type
-        and request_agent_type != bound_agent_type
-    ):
+    if bound_agent_type and request_agent_type and request_agent_type != bound_agent_type:
         raise HTTPException(
             status_code=403,
             detail="API key is not permitted to act as requested agent_type",
@@ -746,13 +763,15 @@ def create_coordination_api() -> FastAPI:
                 await notifier.start_digest_loop()
             except Exception:  # noqa: BLE001
                 logging.getLogger(__name__).warning(
-                    "Notifier digest loop startup failed.", exc_info=True,
+                    "Notifier digest loop startup failed.",
+                    exc_info=True,
                 )
             try:
                 await watchdog.start()
             except Exception:  # noqa: BLE001
                 logging.getLogger(__name__).warning(
-                    "Watchdog startup failed.", exc_info=True,
+                    "Watchdog startup failed.",
+                    exc_info=True,
                 )
 
         # Start merge-train sweeper (R1/R2 — task 5.9). Disable via
@@ -765,7 +784,8 @@ def create_coordination_api() -> FastAPI:
                 await sweeper.start()
             except Exception:  # noqa: BLE001
                 logging.getLogger(__name__).warning(
-                    "MergeTrainSweeper startup failed.", exc_info=True,
+                    "MergeTrainSweeper startup failed.",
+                    exc_info=True,
                 )
 
         from .merge_watcher import get_merge_watcher
@@ -776,7 +796,8 @@ def create_coordination_api() -> FastAPI:
                 await merge_watcher.start()
             except Exception:  # noqa: BLE001
                 logging.getLogger(__name__).warning(
-                    "MergeWatcher startup failed.", exc_info=True,
+                    "MergeWatcher startup failed.",
+                    exc_info=True,
                 )
 
         yield
@@ -952,9 +973,7 @@ def create_coordination_api() -> FastAPI:
         principal: dict[str, Any] = Depends(verify_api_key),
     ) -> dict[str, Any]:
         """Acquire a file lock. Cloud agents call this before modifying files."""
-        agent_id, agent_type = resolve_identity(
-            principal, request.agent_id, request.agent_type
-        )
+        agent_id, agent_type = resolve_identity(principal, request.agent_id, request.agent_type)
         await authorize_operation(
             agent_id=agent_id,
             agent_type=agent_type,
@@ -989,9 +1008,7 @@ def create_coordination_api() -> FastAPI:
         principal: dict[str, Any] = Depends(verify_api_key),
     ) -> dict[str, Any]:
         """Release a file lock."""
-        agent_id, _agent_type = resolve_identity(
-            principal, request.agent_id, None
-        )
+        agent_id, _agent_type = resolve_identity(principal, request.agent_id, None)
         await authorize_operation(
             agent_id=agent_id,
             agent_type=_agent_type,
@@ -1107,9 +1124,7 @@ def create_coordination_api() -> FastAPI:
             }
             for m in memories
         ]
-        return list_envelope(
-            "memories", rows, limit=request.limit, truncated=truncated
-        )
+        return list_envelope("memories", rows, limit=request.limit, truncated=truncated)
 
     # --------------------------------------------------------------------- #
     # WORK QUEUE
@@ -1121,9 +1136,7 @@ def create_coordination_api() -> FastAPI:
         principal: dict[str, Any] = Depends(verify_api_key),
     ) -> dict[str, Any]:
         """Claim a task from the work queue."""
-        agent_id, agent_type = resolve_identity(
-            principal, request.agent_id, request.agent_type
-        )
+        agent_id, agent_type = resolve_identity(principal, request.agent_id, request.agent_type)
         await authorize_operation(
             agent_id=agent_id,
             agent_type=agent_type,
@@ -1189,11 +1202,25 @@ def create_coordination_api() -> FastAPI:
         """Submit new work to the queue."""
 
         agent_id, agent_type = resolve_identity(principal, None, None)
+        projection_change_id = (
+            request.projection_key.change_id if request.projection_key else None
+        )
         await authorize_operation(
             agent_id=agent_id,
             agent_type=agent_type,
-            operation="submit_work",
-            context={"task_type": request.task_type, "priority": request.priority},
+            operation=(
+                "publish_work_projection" if projection_change_id else "submit_work"
+            ),
+            resource=projection_change_id or "",
+            context={
+                "task_type": request.task_type,
+                "priority": request.priority,
+                **(
+                    {"mode": "submit", "change_id": projection_change_id}
+                    if projection_change_id
+                    else {}
+                ),
+            },
         )
 
         depends_on_uuids = request.depends_on
@@ -1210,6 +1237,9 @@ def create_coordination_api() -> FastAPI:
             projection_key=(
                 request.projection_key.model_dump() if request.projection_key else None
             ),
+            projection_labels=(
+                list(request.projection_labels) if request.projection_labels else None
+            ),
         )
         payload = _projection_mutation_payload(result)
         if request.projection_key is None:
@@ -1225,9 +1255,11 @@ def create_coordination_api() -> FastAPI:
         await authorize_operation(
             agent_id=agent_id,
             agent_type=agent_type,
-            operation="submit_work",
+            operation="publish_work_projection",
+            resource=request.projection_key.change_id,
             context={
                 "mode": "reconcile",
+                "change_id": request.projection_key.change_id,
                 "task_type": request.task_type,
                 "priority": request.priority,
             },
@@ -1236,6 +1268,9 @@ def create_coordination_api() -> FastAPI:
 
         result = await get_work_queue_service().reconcile_projection(
             projection_key=request.projection_key.model_dump(),
+            projection_labels=(
+                list(request.projection_labels) if request.projection_labels else None
+            ),
             task_type=request.task_type,
             description=request.task_description,
             input_data=request.input_data,
@@ -1299,13 +1334,11 @@ def create_coordination_api() -> FastAPI:
         """Create a new issue."""
         from uuid import UUID
 
-        from .issue_service import get_issue_service
+        from .issue_service import ProjectionIssueMutationError, get_issue_service
 
         service = get_issue_service()
         parent_uuid = UUID(request.parent_id) if request.parent_id else None
-        depends_uuids = (
-            [UUID(d) for d in request.depends_on] if request.depends_on else None
-        )
+        depends_uuids = [UUID(d) for d in request.depends_on] if request.depends_on else None
 
         try:
             issue = await service.create(
@@ -1319,6 +1352,8 @@ def create_coordination_api() -> FastAPI:
                 depends_on=depends_uuids,
             )
             return {"success": True, "issue": issue.to_dict()}
+        except ProjectionIssueMutationError as e:
+            raise HTTPException(status_code=403, detail=str(e)) from e
         except ValueError as e:
             return {"success": False, "reason": str(e)}
         except Exception as e:  # noqa: BLE001
@@ -1394,7 +1429,7 @@ def create_coordination_api() -> FastAPI:
         """Update an issue."""
         from uuid import UUID
 
-        from .issue_service import get_issue_service
+        from .issue_service import ProjectionIssueMutationError, get_issue_service
 
         service = get_issue_service()
         try:
@@ -1408,6 +1443,8 @@ def create_coordination_api() -> FastAPI:
                 assignee=request.assignee,
                 issue_type=request.issue_type,
             )
+        except ProjectionIssueMutationError as e:
+            raise HTTPException(status_code=403, detail=str(e)) from e
         except ValueError as e:
             return {"success": False, "reason": str(e)}
         except Exception as e:  # noqa: BLE001
@@ -1426,7 +1463,7 @@ def create_coordination_api() -> FastAPI:
         """Close one or more issues."""
         from uuid import UUID
 
-        from .issue_service import get_issue_service
+        from .issue_service import ProjectionIssueMutationError, get_issue_service
 
         service = get_issue_service()
         id_uuid = UUID(request.issue_id) if request.issue_id else None
@@ -1438,6 +1475,8 @@ def create_coordination_api() -> FastAPI:
                 issue_ids=ids_uuids,
                 reason=request.reason,
             )
+        except ProjectionIssueMutationError as e:
+            raise HTTPException(status_code=403, detail=str(e)) from e
         except ValueError as e:
             return {"success": False, "reason": str(e)}
         except Exception as e:  # noqa: BLE001
@@ -1628,9 +1667,7 @@ def create_coordination_api() -> FastAPI:
         principal: dict[str, Any] = Depends(verify_api_key),
     ) -> dict[str, Any]:
         """Write a handoff document for session continuity."""
-        agent_id, agent_type = resolve_identity(
-            principal, request.agent_id, request.agent_type
-        )
+        agent_id, agent_type = resolve_identity(principal, request.agent_id, request.agent_type)
 
         from .handoffs import get_handoff_service
 
@@ -1689,9 +1726,7 @@ def create_coordination_api() -> FastAPI:
         # No top-level ``next_steps`` here: each handoff row already carries a
         # semantic ``next_steps`` field, so reusing the key for command
         # suggestions would be ambiguous.
-        return list_envelope(
-            "handoffs", rows, limit=request.limit, truncated=result.truncated
-        )
+        return list_envelope("handoffs", rows, limit=request.limit, truncated=result.truncated)
 
     # --------------------------------------------------------------------- #
     # POLICY
@@ -1703,9 +1738,7 @@ def create_coordination_api() -> FastAPI:
         principal: dict[str, Any] = Depends(verify_api_key),
     ) -> dict[str, Any]:
         """Check if an operation is authorized by the policy engine."""
-        agent_id, agent_type = resolve_identity(
-            principal, request.agent_id, request.agent_type
-        )
+        agent_id, agent_type = resolve_identity(principal, request.agent_id, request.agent_type)
 
         from .policy_engine import get_policy_engine
 
@@ -1798,9 +1831,7 @@ def create_coordination_api() -> FastAPI:
                 "realtime_port": alloc.realtime_port,
                 "api_port": alloc.api_port,
                 "compose_project_name": alloc.compose_project_name,
-                "remaining_ttl_minutes": max(
-                    0, (alloc.expires_at - time.time()) / 60
-                ),
+                "remaining_ttl_minutes": max(0, (alloc.expires_at - time.time()) / 60),
             }
             for alloc in allocations
         ]
@@ -1902,9 +1933,7 @@ def create_coordination_api() -> FastAPI:
         principal: dict[str, Any] = Depends(verify_api_key),
     ) -> dict[str, Any]:
         """Register a feature with resource claims."""
-        agent_id, agent_type = resolve_identity(
-            principal, request.agent_id, None
-        )
+        agent_id, agent_type = resolve_identity(principal, request.agent_id, None)
         await authorize_operation(
             agent_id=agent_id,
             agent_type=agent_type,
@@ -2209,9 +2238,7 @@ def create_coordination_api() -> FastAPI:
         from .merge_train_service import get_merge_train_service
 
         try:
-            composition = await get_merge_train_service().compose_train(
-                caller_trust_level=trust
-            )
+            composition = await get_merge_train_service().compose_train(caller_trust_level=trust)
         except TrainAuthorizationError as exc:
             raise HTTPException(status_code=403, detail=str(exc))
 
@@ -2391,18 +2418,9 @@ def create_coordination_api() -> FastAPI:
         except Exception:
             entries = []
 
-        merge_count = sum(
-            1 for e in entries
-            if (e.result or {}).get("event_type") == "merge"
-        )
-        revert_count = sum(
-            1 for e in entries
-            if (e.result or {}).get("event_type") == "revert"
-        )
-        rebase_count = sum(
-            1 for e in entries
-            if (e.result or {}).get("event_type") == "rebase"
-        )
+        merge_count = sum(1 for e in entries if (e.result or {}).get("event_type") == "merge")
+        revert_count = sum(1 for e in entries if (e.result or {}).get("event_type") == "revert")
+        rebase_count = sum(1 for e in entries if (e.result or {}).get("event_type") == "rebase")
 
         return {
             "total_events": len(entries),
@@ -2454,6 +2472,7 @@ def create_coordination_api() -> FastAPI:
                 )
             except Exception:  # noqa: BLE001
                 import logging as _logging
+
                 _logging.getLogger(__name__).debug(
                     "Audit logging failed for resolve_archetype_for_phase",
                     exc_info=True,
@@ -2676,9 +2695,7 @@ def create_coordination_api() -> FastAPI:
         principal: dict[str, Any] = Depends(verify_api_key),
     ) -> dict[str, Any]:
         """Register an agent session for discovery."""
-        agent_id, agent_type = resolve_identity(
-            principal, request.agent_id, request.agent_type
-        )
+        agent_id, agent_type = resolve_identity(principal, request.agent_id, request.agent_type)
         await authorize_operation(
             agent_id=agent_id,
             agent_type=agent_type,
@@ -2722,9 +2739,7 @@ def create_coordination_api() -> FastAPI:
                     "capabilities": a.capabilities,
                     "status": a.status,
                     "current_task": a.current_task,
-                    "last_heartbeat": a.last_heartbeat.isoformat()
-                    if a.last_heartbeat
-                    else None,
+                    "last_heartbeat": a.last_heartbeat.isoformat() if a.last_heartbeat else None,
                     "started_at": a.started_at.isoformat() if a.started_at else None,
                     # wire-autopilot-phase-subagents (D-1): surface the resolved
                     # archetype for the agent's current phase. None for legacy
@@ -2741,9 +2756,7 @@ def create_coordination_api() -> FastAPI:
         principal: dict[str, Any] = Depends(verify_api_key),
     ) -> dict[str, Any]:
         """Send a heartbeat for an agent session."""
-        agent_id, agent_type = resolve_identity(
-            principal, request.agent_id, request.agent_type
-        )
+        agent_id, agent_type = resolve_identity(principal, request.agent_id, request.agent_type)
         await authorize_operation(
             agent_id=agent_id,
             agent_type=agent_type,
@@ -2964,9 +2977,7 @@ def create_coordination_api() -> FastAPI:
 
         config = get_config()
         if not config.session_grants.enabled:
-            raise HTTPException(
-                status_code=400, detail="Session grants are not enabled"
-            )
+            raise HTTPException(status_code=400, detail="Session grants are not enabled")
 
         from .session_grants import get_session_grant_service
 
@@ -2993,9 +3004,7 @@ def create_coordination_api() -> FastAPI:
         principal: dict[str, Any] = Depends(verify_api_key),
     ) -> dict[str, Any]:
         """Submit a human-in-the-loop approval request."""
-        agent_id, agent_type = resolve_identity(
-            principal, request.agent_id, request.agent_type
-        )
+        agent_id, agent_type = resolve_identity(principal, request.agent_id, request.agent_type)
         await authorize_operation(
             agent_id=agent_id,
             agent_type=agent_type,
@@ -3006,9 +3015,7 @@ def create_coordination_api() -> FastAPI:
 
         config = get_config()
         if not config.approval.enabled:
-            raise HTTPException(
-                status_code=400, detail="Approval gates are not enabled"
-            )
+            raise HTTPException(status_code=400, detail="Approval gates are not enabled")
 
         service = get_approval_service()
         approval_request = await service.submit_request(
@@ -3227,9 +3234,7 @@ def create_coordination_api() -> FastAPI:
             return EventSourceResponse(generator)
         except Exception as exc:
             logger.error("SSE stream setup failed: %s", exc)
-            return JSONResponse(
-                status_code=500, content={"error": "stream setup failed"}
-            )
+            return JSONResponse(status_code=500, content={"error": "stream setup failed"})
 
     @app.patch("/issues/{issue_id}/labels")
     async def patch_issue_labels(
@@ -3239,13 +3244,13 @@ def create_coordination_api() -> FastAPI:
     ) -> dict[str, Any]:
         """Add or remove labels on a work_queue row (drag-to-Ready interaction).
 
-        Wraps IssueService.update with a labels-only mutation path.
+        Wraps IssueService.update with a labels-only mutation path on an issue row.
         Reversibility: reversible-write; audit emitted.
         """
         from uuid import UUID
 
         from .audit import get_audit_service
-        from .issue_service import IssueService
+        from .issue_service import IssueService, ProjectionIssueMutationError
 
         service = IssueService()
         try:
@@ -3259,10 +3264,13 @@ def create_coordination_api() -> FastAPI:
         current_labels.update(request.add)
         current_labels.difference_update(request.remove)
 
-        updated = await service.update(
-            issue_id=UUID(issue_id),
-            labels=list(current_labels),
-        )
+        try:
+            updated = await service.update(
+                issue_id=UUID(issue_id),
+                labels=list(current_labels),
+            )
+        except ProjectionIssueMutationError as e:
+            raise HTTPException(status_code=403, detail=str(e)) from e
         if updated is None:
             raise HTTPException(status_code=404, detail=f"Issue {issue_id!r} not found")
 
@@ -3394,6 +3402,7 @@ def create_coordination_api() -> FastAPI:
         # 2. Update agent_sessions
         try:
             from .db import get_db
+
             db = get_db()
             await db.update(
                 "agent_sessions",
@@ -3409,6 +3418,7 @@ def create_coordination_api() -> FastAPI:
         held_locks: list[str] = []
         try:
             from .locks import get_lock_service
+
             locks = await get_lock_service().check(locked_by=agent_id)
             held_locks = [lk.file_path for lk in locks]
         except Exception:
@@ -3605,8 +3615,7 @@ def create_coordination_api() -> FastAPI:
                 content={
                     "error": error_code,
                     "message": (
-                        "This coordinator instance has no .git directory in its "
-                        "runtime checkout."
+                        "This coordinator instance has no .git directory in its runtime checkout."
                         if error_code == "git_unavailable"
                         else str(exc)
                     ),
diff --git a/agent-coordinator/src/coordination_mcp.py b/agent-coordinator/src/coordination_mcp.py
index 9be62bd8..fb583533 100644
--- a/agent-coordinator/src/coordination_mcp.py
+++ b/agent-coordinator/src/coordination_mcp.py
@@ -328,6 +328,7 @@ async def submit_work(
     depends_on: list[str] | None = None,
     agent_requirements: dict[str, Any] | None = None,
     projection_key: dict[str, Any] | None = None,
+    projection_labels: list[str] | None = None,
 ) -> dict[str, Any]:
     """
     Submit a new task to the work queue.
@@ -363,6 +364,7 @@ async def submit_work(
             depends_on=depends_on,
             agent_requirements=agent_requirements,
             projection_key=projection_key,
+            projection_labels=projection_labels,
         )
     from uuid import UUID
 
@@ -380,6 +382,7 @@ async def submit_work(
         depends_on=depends_on_uuids,
         agent_requirements=agent_requirements,
         projection_key=projection_key,
+        projection_labels=projection_labels,
     )
 
     if not result.success:
@@ -402,6 +405,7 @@ async def reconcile_work_projection(
     input_data: dict[str, Any] | None = None,
     priority: int = 5,
     agent_requirements: dict[str, Any] | None = None,
+    projection_labels: list[str] | None = None,
 ) -> dict[str, Any]:
     """Reconcile derived work rows to an authoritative loop-state generation."""
     if _transport == "http":
@@ -412,6 +416,7 @@ async def reconcile_work_projection(
             input_data=input_data,
             priority=priority,
             agent_requirements=agent_requirements,
+            projection_labels=projection_labels,
         )
     result = await get_work_queue_service().reconcile_projection(
         projection_key=projection_key,
@@ -420,6 +425,7 @@ async def reconcile_work_projection(
         input_data=input_data,
         priority=priority,
         agent_requirements=agent_requirements,
+        projection_labels=projection_labels,
     )
     if not result.success:
         return {"success": False, "reason": result.reason}
diff --git a/agent-coordinator/src/event_stream.py b/agent-coordinator/src/event_stream.py
index 09ba86c6..b87e174b 100644
--- a/agent-coordinator/src/event_stream.py
+++ b/agent-coordinator/src/event_stream.py
@@ -216,6 +216,7 @@ async def sse_event_generator(
     from .event_bus import CoordinatorEvent
 
     queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
+    projection_refresh_pending = False
 
     # IMPL_REVIEW claude_code#8 (high contract_mismatch): the SSE transition
     # payload's `from`/`to` fields must come from the enum
@@ -269,8 +270,14 @@ async def sse_event_generator(
         }
 
     async def _on_task_event(evt: CoordinatorEvent) -> None:
+        nonlocal projection_refresh_pending
         if not evt.change_id or evt.change_id not in change_ids:
             return
+        if evt.event_type == "projection.labels_changed":
+            if not projection_refresh_pending:
+                projection_refresh_pending = True
+                await queue.put({"event": "projection_snapshot", "data": ""})
+            return
         await queue.put(_make_transition(evt))
 
     async def _on_audit_event(evt: CoordinatorEvent) -> None:
@@ -310,6 +317,16 @@ async def sse_event_generator(
                     yield {"event": "ping", "data": "{}"}
                     continue
 
+                if item["event"] == "projection_snapshot":
+                    # Label repair can update 100 stale rows. Collapse that burst
+                    # before doing the database-backed snapshot work; clear first
+                    # so an update arriving during the query queues one follow-up.
+                    projection_refresh_pending = False
+                    item = {
+                        "event": "snapshot",
+                        "data": await _build_snapshot(change_ids),
+                    }
+
                 now = asyncio.get_event_loop().time()
                 if now - window_start > 1.0:
                     window_start = now
@@ -323,6 +340,10 @@ async def sse_event_generator(
                             queue.get_nowait()
                         except asyncio.QueueEmpty:
                             break
+                    # A queued projection marker may have been drained. Reset
+                    # only after the synchronous drain so an update arriving
+                    # during snapshot construction can enqueue one follow-up.
+                    projection_refresh_pending = False
                     snapshot_data = await _build_snapshot(change_ids)
                     yield {"event": "snapshot", "data": snapshot_data}
                     window_count = 0
diff --git a/agent-coordinator/src/http_proxy.py b/agent-coordinator/src/http_proxy.py
index a8bb7157..0dbbb4dd 100644
--- a/agent-coordinator/src/http_proxy.py
+++ b/agent-coordinator/src/http_proxy.py
@@ -478,6 +478,7 @@ async def proxy_submit_work(
     depends_on: list[str] | None = None,
     agent_requirements: dict[str, Any] | None = None,
     projection_key: dict[str, Any] | None = None,
+    projection_labels: list[str] | None = None,
 ) -> dict[str, Any]:
     """Proxy submit_work to POST /work/submit.
 
@@ -497,6 +498,8 @@ async def proxy_submit_work(
     }
     if projection_key is not None:
         body["projection_key"] = projection_key
+    if projection_labels is not None:
+        body["projection_labels"] = projection_labels
     return await _request("POST", "/work/submit", json_body=body)
 
 
@@ -507,6 +510,7 @@ async def proxy_reconcile_work_projection(
     input_data: dict[str, Any] | None = None,
     priority: int = 5,
     agent_requirements: dict[str, Any] | None = None,
+    projection_labels: list[str] | None = None,
 ) -> dict[str, Any]:
     """Proxy projection reconciliation to POST /work/reconcile.
 
@@ -514,7 +518,7 @@ async def proxy_reconcile_work_projection(
     extra fields and the route takes identity from the principal, so no identity is
     injected into the body.
     """
-    body = {
+    body: dict[str, Any] = {
         "projection_key": projection_key,
         "task_type": task_type,
         "task_description": description,
@@ -522,6 +526,8 @@ async def proxy_reconcile_work_projection(
         "priority": priority,
         "agent_requirements": agent_requirements,
     }
+    if projection_labels is not None:
+        body["projection_labels"] = projection_labels
     return await _request("POST", "/work/reconcile", json_body=body)
 
 
diff --git a/agent-coordinator/src/issue_service.py b/agent-coordinator/src/issue_service.py
index ab6a6ca1..f91ac908 100644
--- a/agent-coordinator/src/issue_service.py
+++ b/agent-coordinator/src/issue_service.py
@@ -41,6 +41,16 @@ STATUS_WRITE_MAP: dict[str, str] = {
 }
 
 VALID_ISSUE_TYPES = {"task", "epic", "bug", "feature"}
+RESERVED_PROJECTION_LABEL = "projection:autopilot-phase"
+
+
+class ProjectionIssueMutationError(PermissionError):
+    """Ordinary issue CRUD attempted to cross the projection ownership boundary."""
+
+
+def _reject_reserved_projection_label(labels: list[str] | None) -> None:
+    if labels and RESERVED_PROJECTION_LABEL in labels:
+        raise ProjectionIssueMutationError("reserved_projection_label")
 
 
 def _postgrest_array_literal(values: list[str]) -> str:
@@ -72,12 +82,7 @@ def _encode_query_value(literal: str) -> str:
     encoded first, which is what makes ``urllib.parse.unquote`` an exact
     inverse; ``db_postgres._decode_query_value`` is the other half.
     """
-    return (
-        literal.replace("%", "%25")
-        .replace("&", "%26")
-        .replace("#", "%23")
-        .replace("+", "%2B")
-    )
+    return literal.replace("%", "%25").replace("&", "%26").replace("#", "%23").replace("+", "%2B")
 
 
 @dataclass
@@ -261,6 +266,7 @@ class IssueService:
             )
         if not 1 <= priority <= 10:
             raise ValueError(f"Priority must be 1-10, got {priority}")
+        _reject_reserved_projection_label(labels)
 
         metadata: dict[str, Any] = {}
         if description:
@@ -316,6 +322,8 @@ class IssueService:
         if status and status != "all":
             statuses = STATUS_MAP.get(status, [status])
             parts.append(f"status=in.({','.join(statuses)})")
+        elif labels and status is None:
+            parts.append("status=in.(pending,claimed,running,completed,failed,blocked)")
 
         if issue_type:
             parts.append(f"issue_type=eq.{issue_type}")
@@ -338,10 +346,7 @@ class IssueService:
         issues = [Issue.from_row(r) for r in rows]
 
         if labels:
-            issues = [
-                i for i in issues
-                if all(label in i.labels for label in labels)
-            ]
+            issues = [i for i in issues if all(label in i.labels for label in labels)]
 
         return issues
 
@@ -407,6 +412,7 @@ class IssueService:
             issue_type: New type
         """
         data: dict[str, Any] = {}
+        _reject_reserved_projection_label(labels)
 
         if title is not None:
             data["description"] = title
@@ -435,19 +441,18 @@ class IssueService:
             if isinstance(metadata, str):
                 metadata = json.loads(metadata)
             metadata["body"] = description
-            data["metadata"] = json.dumps(metadata)
+            data["metadata"] = metadata
 
         if not data:
             # Nothing to update, just return current state
             rows = await self.db.query("work_queue", f"id=eq.{issue_id}")
             return Issue.from_row(rows[0]) if rows else None
 
-        rows = await self.db.update(
-            "work_queue",
-            match={"id": issue_id},
-            data=data,
+        result = await self.db.rpc(
+            "mutate_issue_if_unowned",
+            {"p_issue_id": str(issue_id), "p_patch": data},
         )
-        return Issue.from_row(rows[0]) if rows else None
+        return self._issue_from_mutation_result(result)
 
     async def close(
         self,
@@ -470,27 +475,47 @@ class IssueService:
         if not ids:
             raise ValueError("Must provide issue_id or issue_ids")
 
-        now = datetime.now(UTC)
-        results: list[Issue] = []
+        now = datetime.now(UTC).isoformat()
+        result = await self.db.rpc(
+            "close_issues_if_unowned",
+            {
+                "p_request": {
+                    "issue_ids": [str(iid) for iid in ids],
+                    "closed_at": now,
+                    "reason": reason,
+                }
+            },
+        )
+        return self._issues_from_close_result(result)
 
-        for iid in ids:
-            data: dict[str, Any] = {
-                "status": "completed",
-                "completed_at": now.isoformat(),
-                "closed_at": now.isoformat(),
-            }
-            if reason:
-                data["close_reason"] = reason
+    @staticmethod
+    def _issue_from_mutation_result(result: Any) -> Issue | None:
+        if not isinstance(result, dict):
+            raise RuntimeError("invalid_issue_mutation_result")
+        if not result.get("success"):
+            reason = str(result.get("reason") or "issue_mutation_failed")
+            if reason in {"projection_issue_immutable", "reserved_projection_label"}:
+                raise ProjectionIssueMutationError(reason)
+            if reason == "issue_not_found":
+                return None
+            raise RuntimeError(reason)
+        row = result.get("issue")
+        if not isinstance(row, dict):
+            raise RuntimeError("invalid_issue_mutation_result")
+        return Issue.from_row(row)
 
-            rows = await self.db.update(
-                "work_queue",
-                match={"id": iid},
-                data=data,
-            )
-            if rows:
-                results.append(Issue.from_row(rows[0]))
-
-        return results
+    def _issues_from_close_result(self, result: Any) -> list[Issue]:
+        if not isinstance(result, dict):
+            raise RuntimeError("invalid_issue_close_result")
+        if not result.get("success"):
+            reason = str(result.get("reason") or "issue_close_failed")
+            if reason in {"projection_issue_immutable", "reserved_projection_label"}:
+                raise ProjectionIssueMutationError(reason)
+            raise RuntimeError(reason)
+        rows = result.get("issues")
+        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
+            raise RuntimeError("invalid_issue_close_result")
+        return [Issue.from_row(row) for row in rows]
 
     async def comment(
         self,
@@ -553,9 +578,7 @@ class IssueService:
                 # Check if all dependencies are completed
                 all_resolved = True
                 for dep_id in issue.depends_on:
-                    dep_rows = await self.db.query(
-                        "work_queue", f"id=eq.{dep_id}"
-                    )
+                    dep_rows = await self.db.query("work_queue", f"id=eq.{dep_id}")
                     if dep_rows and dep_rows[0]["status"] != "completed":
                         all_resolved = False
                         break
@@ -584,9 +607,7 @@ class IssueService:
                 continue
             # Check if any dependency is unresolved
             for dep_id in issue.depends_on:
-                dep_rows = await self.db.query(
-                    "work_queue", f"id=eq.{dep_id}"
-                )
+                dep_rows = await self.db.query("work_queue", f"id=eq.{dep_id}")
                 if dep_rows and dep_rows[0]["status"] != "completed":
                     blocked_issues.append(issue)
                     break
diff --git a/agent-coordinator/src/policy_engine.py b/agent-coordinator/src/policy_engine.py
index 5855de8e..759e051e 100644
--- a/agent-coordinator/src/policy_engine.py
+++ b/agent-coordinator/src/policy_engine.py
@@ -71,7 +71,7 @@ WRITE_ACTIONS = frozenset({
 # Admin actions requiring trust_level >= MIN_ADMIN_TRUST (TrustLevel.ELEVATED)
 ADMIN_ACTIONS = frozenset({
     "force_push", "delete_branch", "cleanup_agents",
-    "rollback_policy",
+    "rollback_policy", "publish_work_projection",
 })
 
 # Known-allowed network domains (matches default Cedar policies)
@@ -732,7 +732,24 @@ class CedarPolicyEngine:
     ) -> PolicyDecision:
         """Internal check_operation logic (no metrics)."""
         ctx = context or {}
-        trust_level = ctx.get("trust_level", 1)
+        trust_level = ctx.get("trust_level")
+        if trust_level is None:
+            from .trust_resolution import TrustResolutionError, resolve_trust_level
+
+            try:
+                trust_level = await resolve_trust_level(agent_id, agent_type)
+            except TrustResolutionError as exc:
+                decision = PolicyDecision.deny(f"trust_resolution_failed: {exc}")
+                await self._log_policy_decision(
+                    agent_id=agent_id,
+                    agent_type=agent_type,
+                    operation=operation,
+                    resource=resource,
+                    context=ctx,
+                    decision=decision,
+                    engine="cedar",
+                )
+                return decision
 
         try:
             policies = await self._load_policies()
diff --git a/agent-coordinator/src/work_queue.py b/agent-coordinator/src/work_queue.py
index cbde4544..34b69213 100644
--- a/agent-coordinator/src/work_queue.py
+++ b/agent-coordinator/src/work_queue.py
@@ -252,6 +252,21 @@ class ProjectionKey:
         }
 
 
+def _projection_labels_are_valid(
+    key: ProjectionKey | None, task_type: str, labels: list[str] | None
+) -> bool:
+    if labels is None:
+        return True
+    return (
+        key is not None
+        and task_type == "issue"
+        and labels == [
+            f"change:{key.change_id}",
+            "projection:autopilot-phase",
+        ]
+    )
+
+
 @dataclass
 class SubmitResult:
     """Result of submitting a task, including projection replay metadata."""
@@ -717,6 +732,7 @@ class WorkQueueService:
         deadline: datetime | None = None,
         agent_requirements: dict[str, Any] | None = None,
         projection_key: ProjectionKey | dict[str, Any] | None = None,
+        projection_labels: list[str] | None = None,
     ) -> SubmitResult:
         """Submit a new task to the work queue.
 
@@ -742,6 +758,12 @@ class WorkQueueService:
             if parsed_projection is None:
                 return SubmitResult(success=False, created=False, reason="invalid_projection_key")
             input_data = {**(input_data or {}), **parsed_projection.as_input_data()}
+        if not _projection_labels_are_valid(
+            parsed_projection, task_type, projection_labels
+        ):
+            return SubmitResult(
+                success=False, created=False, reason="invalid_projection_labels"
+            )
 
         config = get_config()
         resolved_agent_id = config.agent.agent_id
@@ -755,11 +777,26 @@ class WorkQueueService:
             decision = await get_policy_engine().check_operation(
                 agent_id=resolved_agent_id,
                 agent_type=resolved_agent_type,
-                operation="submit_work",
+                operation=(
+                    "publish_work_projection"
+                    if parsed_projection is not None
+                    else "submit_work"
+                ),
+                resource=(
+                    parsed_projection.change_id if parsed_projection is not None else ""
+                ),
                 context={
                     "task_type": task_type,
                     "priority": priority,
                     "has_dependencies": bool(depends_on),
+                    **(
+                        {
+                            "mode": "submit",
+                            "change_id": parsed_projection.change_id,
+                        }
+                        if parsed_projection is not None
+                        else {}
+                    ),
                 },
             )
             if not decision.allowed:
@@ -828,6 +865,7 @@ class WorkQueueService:
                     "p_depends_on": depends_on_str,
                     "p_deadline": deadline_str,
                     "p_agent_requirements": agent_req_json,
+                    "p_projection_labels": projection_labels,
                 },
             )
 
@@ -866,6 +904,7 @@ class WorkQueueService:
         input_data: dict[str, Any] | None = None,
         priority: int = 5,
         agent_requirements: dict[str, Any] | None = None,
+        projection_labels: list[str] | None = None,
     ) -> ReconcileResult:
         """Converge derived queue rows to one authoritative loop-state generation."""
         key = ProjectionKey.parse(projection_key)
@@ -873,15 +912,21 @@ class WorkQueueService:
             return ReconcileResult(success=False, created=False, reason="invalid_projection_key")
         if input_data and _RESERVED_PROJECTION_KEYS.intersection(input_data):
             return ReconcileResult(success=False, created=False, reason="reserved_projection_key")
+        if not _projection_labels_are_valid(key, task_type, projection_labels):
+            return ReconcileResult(
+                success=False, created=False, reason="invalid_projection_labels"
+            )
         config = get_config()
         from .policy_engine import get_policy_engine
 
         decision = await get_policy_engine().check_operation(
             agent_id=config.agent.agent_id,
             agent_type=config.agent.agent_type,
-            operation="submit_work",
+            operation="publish_work_projection",
+            resource=key.change_id,
             context={
                 "mode": "reconcile",
+                "change_id": key.change_id,
                 "task_type": task_type,
                 "priority": priority,
             },
@@ -924,6 +969,8 @@ class WorkQueueService:
                     created=False,
                     reason="guardrail_denied",
                 )
+        except TrustResolutionError:
+            raise
         except Exception:
             logger.error("Guardrails check failed during reconcile", exc_info=True)
 
@@ -943,6 +990,7 @@ class WorkQueueService:
                 "p_agent_requirements": (
                     _json.dumps(agent_requirements) if agent_requirements is not None else None
                 ),
+                "p_projection_labels": projection_labels,
             },
         )
         reconcile_result = ReconcileResult.from_dict(result)
diff --git a/agent-coordinator/tests/e2e/postgres/conftest.py b/agent-coordinator/tests/e2e/postgres/conftest.py
index a5c30a81..f9d4324e 100644
--- a/agent-coordinator/tests/e2e/postgres/conftest.py
+++ b/agent-coordinator/tests/e2e/postgres/conftest.py
@@ -18,6 +18,7 @@ POSTGRES_DSN = os.environ.get(
 )
 
 _API_KEY = "e2e-test-key"
+_WORK_QUEUE_API_KEY = "e2e-work-queue-key"
 
 # Tables to truncate between tests (audit_log is immutable)
 _TABLES = [
@@ -88,10 +89,14 @@ def _make_app():
     """Create a fresh FastAPI app wired to DirectPostgresClient."""
     os.environ["DB_BACKEND"] = "postgres"
     os.environ["POSTGRES_DSN"] = POSTGRES_DSN
-    os.environ["COORDINATION_API_KEYS"] = _API_KEY
-    os.environ["COORDINATION_API_KEY_IDENTITIES"] = "{}"
-    os.environ["AGENT_ID"] = "e2e-agent"
-    os.environ["AGENT_TYPE"] = "test_agent"
+    os.environ["COORDINATION_API_KEYS"] = f"{_API_KEY},{_WORK_QUEUE_API_KEY}"
+    os.environ["COORDINATION_API_KEY_IDENTITIES"] = (
+        '{"e2e-test-key":{"agent_id":"e2e-agent","agent_type":"test_agent"},'
+        '"e2e-work-queue-key":{"agent_id":"claude-local",'
+        '"agent_type":"claude_code"}}'
+    )
+    os.environ["AGENT_ID"] = "claude-local"
+    os.environ["AGENT_TYPE"] = "claude_code"
     os.environ["COORDINATOR_PROFILE"] = "local"
     # Ensure SESSION_ID is unset so handoff writes don't hit FK constraint
     os.environ.pop("SESSION_ID", None)
@@ -122,6 +127,12 @@ def auth_headers():
     return {"X-API-Key": _API_KEY}
 
 
+@pytest.fixture
+def work_queue_auth_headers():
+    """Privileged identity used for guarded work-queue lifecycle operations."""
+    return {"X-API-Key": _WORK_QUEUE_API_KEY}
+
+
 @pytest.fixture(autouse=True)
 async def cleanup_tables():
     """Truncate test data before/after each test."""
diff --git a/agent-coordinator/tests/e2e/postgres/test_work_queue_live.py b/agent-coordinator/tests/e2e/postgres/test_work_queue_live.py
index 8b13c56c..b3ecef3a 100644
--- a/agent-coordinator/tests/e2e/postgres/test_work_queue_live.py
+++ b/agent-coordinator/tests/e2e/postgres/test_work_queue_live.py
@@ -7,10 +7,10 @@ import pytest
 class TestWorkQueueSubmitLive:
     """Work queue submit endpoint against live database."""
 
-    def test_submit_task(self, api_client, auth_headers) -> None:
+    def test_submit_task(self, api_client, work_queue_auth_headers) -> None:
         response = api_client.post(
             "/work/submit",
-            headers=auth_headers,
+            headers=work_queue_auth_headers,
             json={
                 "task_type": "test",
                 "task_description": "Write unit tests for cache module",
@@ -23,15 +23,68 @@ class TestWorkQueueSubmitLive:
         assert data["task_id"] is not None
 
 
+@pytest.mark.e2e
+class TestWorkQueueProjectionLive:
+    def test_projection_submit_reconcile_and_board_query(
+        self, api_client, work_queue_auth_headers
+    ) -> None:
+        change_id = "e2e-phase-projection"
+        labels = [f"change:{change_id}", "projection:autopilot-phase"]
+        first = {
+            "task_type": "issue",
+            "task_description": "Autopilot phase PLAN",
+            "priority": 1,
+            "projection_key": {
+                "change_id": change_id,
+                "phase": "PLAN",
+                "transition_sequence": 1,
+            },
+            "projection_labels": labels,
+        }
+        second = {
+            **first,
+            "task_description": "Autopilot phase IMPLEMENT",
+            "projection_key": {
+                "change_id": change_id,
+                "phase": "IMPLEMENT",
+                "transition_sequence": 2,
+            },
+        }
+
+        created = api_client.post("/work/submit", headers=work_queue_auth_headers, json=first)
+        assert created.status_code == 200
+        stale_id = created.json()["task_id"]
+
+        advance = api_client.post("/work/submit", headers=work_queue_auth_headers, json=second)
+        assert advance.status_code == 409
+        assert advance.json()["detail"] == "reconciliation_required"
+
+        reconciled = api_client.post(
+            "/work/reconcile", headers=work_queue_auth_headers, json=second
+        )
+        assert reconciled.status_code == 200
+        current_id = reconciled.json()["task_id"]
+        assert stale_id in reconciled.json()["cancelled_task_ids"]
+
+        board = api_client.post(
+            "/issues/list",
+            headers=work_queue_auth_headers,
+            json={"labels": [f"change:{change_id}"]},
+        )
+        assert board.status_code == 200
+        assert [issue["id"] for issue in board.json()["issues"]] == [current_id]
+        assert board.json()["issues"][0]["labels"] == labels
+
+
 @pytest.mark.e2e
 class TestWorkQueueLifecycleLive:
     """Full work queue lifecycle against live database."""
 
-    def test_submit_claim_complete(self, api_client, auth_headers) -> None:
+    def test_submit_claim_complete(self, api_client, work_queue_auth_headers) -> None:
         # Submit
         submit_resp = api_client.post(
             "/work/submit",
-            headers=auth_headers,
+            headers=work_queue_auth_headers,
             json={
                 "task_type": "refactor",
                 "task_description": "Simplify error handling in locks.py",
@@ -44,10 +97,10 @@ class TestWorkQueueLifecycleLive:
         # Claim
         claim_resp = api_client.post(
             "/work/claim",
-            headers=auth_headers,
+            headers=work_queue_auth_headers,
             json={
-                "agent_id": "e2e-agent",
-                "agent_type": "test_agent",
+                "agent_id": "claude-local",
+                "agent_type": "claude_code",
                 "task_types": ["refactor"],
             },
         )
@@ -59,10 +112,10 @@ class TestWorkQueueLifecycleLive:
         # Complete
         complete_resp = api_client.post(
             "/work/complete",
-            headers=auth_headers,
+            headers=work_queue_auth_headers,
             json={
                 "task_id": task_id,
-                "agent_id": "e2e-agent",
+                "agent_id": "claude-local",
                 "success": True,
                 "result": {"files_modified": ["src/locks.py"]},
             },
@@ -70,13 +123,13 @@ class TestWorkQueueLifecycleLive:
         assert complete_resp.status_code == 200
         assert complete_resp.json()["success"] is True
 
-    def test_claim_empty_queue(self, api_client, auth_headers) -> None:
+    def test_claim_empty_queue(self, api_client, work_queue_auth_headers) -> None:
         response = api_client.post(
             "/work/claim",
-            headers=auth_headers,
+            headers=work_queue_auth_headers,
             json={
-                "agent_id": "e2e-agent",
-                "agent_type": "test_agent",
+                "agent_id": "claude-local",
+                "agent_type": "claude_code",
                 "task_types": ["nonexistent"],
             },
         )
diff --git a/agent-coordinator/tests/integration/postgres/conftest.py b/agent-coordinator/tests/integration/postgres/conftest.py
index 4ae4915a..9395f989 100644
--- a/agent-coordinator/tests/integration/postgres/conftest.py
+++ b/agent-coordinator/tests/integration/postgres/conftest.py
@@ -92,8 +92,11 @@ def setup_postgres_env(monkeypatch):
     """
     monkeypatch.setenv("DB_BACKEND", "postgres")
     monkeypatch.setenv("POSTGRES_DSN", POSTGRES_DSN)
-    monkeypatch.setenv("AGENT_ID", "integ-pg-agent-1")
-    monkeypatch.setenv("AGENT_TYPE", "test_agent")
+    # Projection publication is a coordinator-only trust-3 operation. These
+    # fixtures exercise that publisher path; claim/complete tests still pass
+    # their ordinary worker identity explicitly at the call site.
+    monkeypatch.setenv("AGENT_ID", "claude-local")
+    monkeypatch.setenv("AGENT_TYPE", "claude_code")
     monkeypatch.setenv("SESSION_ID", "integ-pg-session-1")
     monkeypatch.setenv("LOCK_TTL_MINUTES", "5")
     monkeypatch.setenv("COORDINATOR_PROFILE", "local")
diff --git a/agent-coordinator/tests/integration/postgres/test_autopilot_projection_acceptance_postgres.py b/agent-coordinator/tests/integration/postgres/test_autopilot_projection_acceptance_postgres.py
new file mode 100644
index 00000000..9801f9cf
--- /dev/null
+++ b/agent-coordinator/tests/integration/postgres/test_autopilot_projection_acceptance_postgres.py
@@ -0,0 +1,765 @@
+"""Live PostgreSQL acceptance coverage for Autopilot phase projections."""
+
+from __future__ import annotations
+
+import asyncio
+import json
+
+import asyncpg
+import pytest
+
+from src.event_bus import EventBusService
+from src.event_stream import sse_event_generator
+from src.issue_service import IssueService
+
+from .conftest import POSTGRES_DSN
+
+pytestmark = pytest.mark.integration
+
+_PROJECTION_LABEL = "projection:autopilot-phase"
+
+
+def _key(change_id: str, phase: str, sequence: int) -> dict[str, object]:
+    return {
+        "change_id": change_id,
+        "phase": phase,
+        "transition_sequence": sequence,
+    }
+
+
+async def _wait_until_listening(bus: EventBusService) -> None:
+    for _ in range(100):
+        connection = bus._connection
+        if connection is not None and not connection.is_closed():
+            return
+        await asyncio.sleep(0.02)
+    pytest.fail("PostgreSQL event bus did not become ready within two seconds")
+
+
+async def test_three_generations_replay_cancel_stale_and_exclude_issues_from_claim(
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    """Three live generations converge to one labelled, unclaimable issue row."""
+    issues = IssueService(db=postgres_db)
+    change_id = "live-three-generations"
+    labels = [f"change:{change_id}", _PROJECTION_LABEL]
+
+    first = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase INIT",
+        priority=1,
+        projection_key=_key(change_id, "INIT", 0),
+        projection_labels=labels,
+    )
+    assert first.success is True
+
+    second_submit = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase PLAN",
+        priority=1,
+        projection_key=_key(change_id, "PLAN", 1),
+        projection_labels=labels,
+    )
+    assert second_submit.success is False
+    assert second_submit.reason == "reconciliation_required"
+    second = await pg_work_queue.reconcile_projection(
+        task_type="issue",
+        description="Autopilot phase PLAN",
+        priority=1,
+        projection_key=_key(change_id, "PLAN", 1),
+        projection_labels=labels,
+    )
+    assert first.task_id in second.cancelled_task_ids
+
+    third_submit = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase IMPLEMENT",
+        priority=1,
+        projection_key=_key(change_id, "IMPLEMENT", 2),
+        projection_labels=labels,
+    )
+    assert third_submit.success is False
+    assert third_submit.reason == "reconciliation_required"
+    third = await pg_work_queue.reconcile_projection(
+        task_type="issue",
+        description="Autopilot phase IMPLEMENT",
+        priority=1,
+        projection_key=_key(change_id, "IMPLEMENT", 2),
+        projection_labels=labels,
+    )
+    assert second.task_id in third.cancelled_task_ids
+
+    replay = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase IMPLEMENT",
+        priority=1,
+        projection_key=_key(change_id, "IMPLEMENT", 2),
+        projection_labels=labels,
+    )
+    assert replay.success is True
+    assert replay.created is False
+    assert replay.deduplicated is True
+    assert replay.task_id == third.task_id
+
+    stale = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase PLAN",
+        priority=1,
+        projection_key=_key(change_id, "PLAN", 1),
+        projection_labels=labels,
+    )
+    assert stale.success is False
+    assert stale.reason == "stale_projection"
+
+    labelled = await issues.list_issues(
+        labels=[f"change:{change_id}", _PROJECTION_LABEL],
+        limit=100,
+    )
+    assert [issue.id for issue in labelled] == [third.task_id]
+    rows = await postgres_db.query(
+        "work_queue",
+        f"input_data->>change_id=eq.{change_id}&order=created_at.asc",
+    )
+    assert [row["status"] for row in rows] == ["cancelled", "cancelled", "pending"]
+    assert [row["labels"] for row in rows] == [
+        [],
+        [],
+        labels,
+    ]
+
+    ordinary = await pg_work_queue.submit(
+        task_type="test",
+        description="Only executable row",
+        priority=9,
+    )
+    claimed = await pg_work_queue.claim(
+        agent_id="integ-pg-agent-1",
+        agent_type="test_agent",
+    )
+    assert claimed.success is True
+    assert claimed.task_id == ordinary.task_id
+    assert claimed.task_type == "test"
+
+
+async def test_issue_service_batch_close_is_atomic_across_projection_boundary(
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    issues = IssueService(db=postgres_db)
+    first = await issues.create(title="First ordinary issue")
+    second = await issues.create(title="Second ordinary issue")
+    change_id = "live-atomic-issue-close"
+    labels = [f"change:{change_id}", _PROJECTION_LABEL]
+    projection = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase INIT",
+        priority=1,
+        projection_key=_key(change_id, "INIT", 0),
+        projection_labels=labels,
+    )
+
+    with pytest.raises(PermissionError, match="projection_issue_immutable"):
+        await issues.close(issue_ids=[first.id, projection.task_id, second.id])
+
+    assert (await issues.show(first.id)).status == "pending"
+    assert (await issues.show(second.id)).status == "pending"
+
+    closed = await issues.close(
+        issue_ids=[first.id, second.id],
+        reason="atomic batch complete",
+    )
+    assert [issue.id for issue in closed] == [first.id, second.id]
+    assert [issue.status for issue in closed] == ["completed", "completed"]
+    assert [issue.close_reason for issue in closed] == [
+        "atomic batch complete",
+        "atomic batch complete",
+    ]
+
+
+async def test_priority_one_projection_survives_exact_label_query_window_over_50(
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    """The existing label-only board query retains the projection in its first page."""
+    issues = IssueService(db=postgres_db)
+    change_id = "live-window"
+    label = f"change:{change_id}"
+
+    for index in range(55):
+        await issues.create(
+            title=f"Ordinary issue {index:02d}",
+            priority=2,
+            labels=[label],
+        )
+
+    projection = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase VALIDATE",
+        priority=1,
+        projection_key=_key(change_id, "VALIDATE", 3),
+        projection_labels=[label, _PROJECTION_LABEL],
+    )
+
+    first_page = await issues.list_issues(labels=[label])
+    assert len(first_page) == 50
+    assert first_page[0].id == projection.task_id
+    assert first_page[0].priority == 1
+    assert first_page[0].labels == [label, _PROJECTION_LABEL]
+
+
+async def test_connected_sse_refreshes_after_atomic_projection_reconciliation(
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    """A connected client receives a fresh current-only projection snapshot."""
+    change_id = "live-sse"
+    labels = [f"change:{change_id}", _PROJECTION_LABEL]
+
+    old = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase PLAN",
+        priority=1,
+        projection_key=_key(change_id, "PLAN", 1),
+        projection_labels=labels,
+    )
+
+    bus = EventBusService(dsn=POSTGRES_DSN, channels=("coordinator_task",))
+    await bus.start()
+    await _wait_until_listening(bus)
+    stream = sse_event_generator([change_id], bus)
+    try:
+        initial = await asyncio.wait_for(stream.__anext__(), timeout=5)
+        assert initial["event"] == "snapshot"
+        assert [row["id"] for row in json.loads(initial["data"])["work_queue"]] == [
+            str(old.task_id)
+        ]
+
+        current = await pg_work_queue.reconcile_projection(
+            task_type="issue",
+            description="Autopilot phase IMPLEMENT",
+            priority=1,
+            projection_key=_key(change_id, "IMPLEMENT", 2),
+            projection_labels=labels,
+        )
+
+        refreshed = await asyncio.wait_for(stream.__anext__(), timeout=5)
+        assert refreshed["event"] == "snapshot"
+        assert [row["id"] for row in json.loads(refreshed["data"])["work_queue"]] == [
+            str(current.task_id)
+        ]
+    finally:
+        await stream.aclose()
+        await bus.stop()
+
+
+async def test_connected_sse_refreshes_for_first_canonical_projection_insert(
+    pg_work_queue,
+) -> None:
+    """The first labelled projection insert refreshes an already-connected client."""
+    change_id = "live-first-insert-sse"
+    labels = [f"change:{change_id}", _PROJECTION_LABEL]
+    bus = EventBusService(dsn=POSTGRES_DSN, channels=("coordinator_task",))
+    await bus.start()
+    await _wait_until_listening(bus)
+    stream = sse_event_generator([change_id], bus)
+    try:
+        initial = await asyncio.wait_for(stream.__anext__(), timeout=5)
+        assert json.loads(initial["data"])["work_queue"] == []
+
+        created = await pg_work_queue.submit(
+            task_type="issue",
+            description="Autopilot phase INIT",
+            priority=1,
+            projection_key=_key(change_id, "INIT", 0),
+            projection_labels=labels,
+        )
+        assert created.success is True
+
+        refreshed = await asyncio.wait_for(stream.__anext__(), timeout=1)
+        assert refreshed["event"] == "snapshot"
+        assert [row["id"] for row in json.loads(refreshed["data"])["work_queue"]] == [
+            str(created.task_id)
+        ]
+    finally:
+        await stream.aclose()
+        await bus.stop()
+
+
+async def test_same_generation_submit_replay_clears_noncanonical_owned_labels(
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    change_id = "live-submit-replay-repair"
+    labels = [f"change:{change_id}", _PROJECTION_LABEL]
+    key = _key(change_id, "INIT", 0)
+    canonical = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase INIT",
+        priority=1,
+        projection_key=key,
+        projection_labels=labels,
+    )
+    stale = await postgres_db.insert(
+        "work_queue",
+        {
+            "task_type": "issue",
+            "description": "stale owned projection",
+            "input_data": _key(change_id, "PLAN", 1),
+            "priority": 1,
+            "status": "cancelled",
+            "labels": [],
+        },
+    )
+    await postgres_db.insert(
+        "work_queue_projection_ownership",
+        {"task_id": str(stale["id"])},
+    )
+    await postgres_db.update(
+        "work_queue",
+        match={"id": stale["id"]},
+        data={"labels": labels},
+    )
+
+    replay = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase INIT",
+        priority=1,
+        projection_key=key,
+        projection_labels=labels,
+    )
+
+    assert replay.success is True
+    assert replay.task_id == canonical.task_id
+    rows = await postgres_db.query(
+        "work_queue", f"input_data->>change_id=eq.{change_id}&order=created_at.asc"
+    )
+    labels_by_id = {str(row["id"]): row["labels"] for row in rows}
+    assert labels_by_id[str(canonical.task_id)] == labels
+    assert labels_by_id[str(stale["id"])] == []
+
+
+async def test_database_rejects_unowned_spoofed_projection_issue(
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    change_id = "live-unowned-noncanonical-spoof"
+    labels = [f"change:{change_id}", _PROJECTION_LABEL]
+    canonical = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase INIT",
+        priority=1,
+        projection_key=_key(change_id, "INIT", 0),
+        projection_labels=labels,
+    )
+    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="reserved_projection_label"):
+        await postgres_db.insert(
+            "work_queue",
+            {
+                "task_type": "issue",
+                "description": "ordinary issue spoofing projection metadata",
+                "input_data": _key(change_id, "PLAN", 99),
+                "priority": 5,
+                "labels": labels,
+            },
+        )
+
+    rows = await postgres_db.query(
+        "work_queue", f"input_data->>change_id=eq.{change_id}&order=created_at.asc"
+    )
+    assert [(str(row["id"]), row["status"], row["labels"]) for row in rows] == [
+        (str(canonical.task_id), "pending", labels)
+    ]
+
+
+@pytest.mark.parametrize("mode", ["submit", "reconcile"])
+async def test_unlabelled_projection_cannot_mutate_owned_labelled_namespace(
+    mode,
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    change_id = f"live-owned-mode-isolation-{mode}"
+    labels = [f"change:{change_id}", _PROJECTION_LABEL]
+    canonical_key = _key(change_id, "INIT", 0)
+    canonical = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase INIT",
+        priority=1,
+        projection_key=canonical_key,
+        projection_labels=labels,
+    )
+    request = {
+        "task_type": "issue",
+        "description": "unlabelled projection",
+        "priority": 1,
+        "projection_key": (canonical_key if mode == "submit" else _key(change_id, "PLAN", 1)),
+    }
+
+    if mode == "submit":
+        result = await pg_work_queue.submit(**request)
+    else:
+        result = await pg_work_queue.reconcile_projection(**request)
+
+    assert result.success is False
+    assert result.reason == "projection_mode_mismatch"
+    rows = await postgres_db.query(
+        "work_queue", f"input_data->>change_id=eq.{change_id}&order=created_at.asc"
+    )
+    assert [(str(row["id"]), row["status"], row["labels"]) for row in rows] == [
+        (str(canonical.task_id), "pending", labels)
+    ]
+    heads = await postgres_db.query("work_queue_projection_heads", f"change_id=eq.{change_id}")
+    assert [(row["phase"], row["transition_sequence"]) for row in heads] == [("INIT", 0)]
+
+
+@pytest.mark.parametrize("mode", ["submit", "reconcile"])
+async def test_labelled_projection_cannot_enter_unlabelled_keyed_namespace(
+    mode,
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    change_id = f"live-unlabelled-mode-isolation-{mode}"
+    canonical_key = _key(change_id, "INIT", 0)
+    canonical = await pg_work_queue.submit(
+        task_type="issue",
+        description="legacy unlabelled projection",
+        priority=1,
+        projection_key=canonical_key,
+    )
+    target_key = canonical_key if mode == "submit" else _key(change_id, "PLAN", 1)
+    request = {
+        "task_type": "issue",
+        "description": "Autopilot labelled projection",
+        "priority": 1,
+        "projection_key": target_key,
+        "projection_labels": [f"change:{change_id}", _PROJECTION_LABEL],
+    }
+
+    if mode == "submit":
+        result = await pg_work_queue.submit(**request)
+    else:
+        result = await pg_work_queue.reconcile_projection(**request)
+
+    assert result.success is False
+    assert result.reason == "projection_key_collision"
+    rows = await postgres_db.query(
+        "work_queue", f"input_data->>change_id=eq.{change_id}&order=created_at.asc"
+    )
+    assert [(str(row["id"]), row["status"], row["labels"]) for row in rows] == [
+        (str(canonical.task_id), "pending", [])
+    ]
+    heads = await postgres_db.query("work_queue_projection_heads", f"change_id=eq.{change_id}")
+    assert [(row["phase"], row["transition_sequence"]) for row in heads] == [("INIT", 0)]
+
+
+async def test_submit_collision_with_nonissue_is_fail_closed(
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    change_id = "live-submit-key-collision"
+    key = _key(change_id, "INIT", 0)
+    collision = await postgres_db.insert(
+        "work_queue",
+        {
+            "task_type": "test",
+            "description": "ordinary row owns target key",
+            "input_data": key,
+            "priority": 5,
+            "labels": ["ordinary"],
+        },
+    )
+
+    result = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase INIT",
+        priority=1,
+        projection_key=key,
+        projection_labels=[f"change:{change_id}", _PROJECTION_LABEL],
+    )
+
+    assert result.success is False
+    assert result.reason == "projection_key_collision"
+    rows = await postgres_db.query("work_queue", f"id=eq.{collision['id']}")
+    assert rows[0]["task_type"] == "test"
+    assert rows[0]["status"] == "pending"
+    assert rows[0]["labels"] == ["ordinary"]
+    heads = await postgres_db.query("work_queue_projection_heads", f"change_id=eq.{change_id}")
+    assert heads == []
+
+
+async def test_reconcile_collision_with_nonissue_preserves_head_and_active_row(
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    change_id = "live-reconcile-key-collision"
+    labels = [f"change:{change_id}", _PROJECTION_LABEL]
+    current = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase PLAN",
+        priority=1,
+        projection_key=_key(change_id, "PLAN", 1),
+        projection_labels=labels,
+    )
+    collision = await postgres_db.insert(
+        "work_queue",
+        {
+            "task_type": "test",
+            "description": "ordinary row owns next key",
+            "input_data": _key(change_id, "IMPLEMENT", 2),
+            "priority": 5,
+            "labels": ["ordinary"],
+        },
+    )
+
+    result = await pg_work_queue.reconcile_projection(
+        task_type="issue",
+        description="Autopilot phase IMPLEMENT",
+        priority=1,
+        projection_key=_key(change_id, "IMPLEMENT", 2),
+        projection_labels=labels,
+    )
+
+    assert result.success is False
+    assert result.reason == "projection_key_collision"
+    rows = await postgres_db.query(
+        "work_queue", f"input_data->>change_id=eq.{change_id}&order=created_at.asc"
+    )
+    rows_by_id = {str(row["id"]): row for row in rows}
+    assert rows_by_id[str(current.task_id)]["status"] == "pending"
+    assert rows_by_id[str(current.task_id)]["labels"] == labels
+    collision_row = rows_by_id[str(collision["id"])]
+    assert collision_row["task_type"] == "test"
+    assert collision_row["status"] == "pending"
+    assert collision_row["labels"] == ["ordinary"]
+    heads = await postgres_db.query("work_queue_projection_heads", f"change_id=eq.{change_id}")
+    assert [(row["phase"], row["transition_sequence"]) for row in heads] == [("PLAN", 1)]
+
+
+@pytest.mark.parametrize("mode", ["submit", "reconcile"])
+async def test_owned_projection_cannot_take_over_unowned_issue_key(
+    mode,
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    change_id = f"live-unowned-issue-collision-{mode}"
+    labels = [f"change:{change_id}", _PROJECTION_LABEL]
+    target = _key(change_id, "INIT", 0)
+    current = None
+    if mode == "reconcile":
+        current = await pg_work_queue.submit(
+            task_type="issue",
+            description="Autopilot phase PLAN",
+            priority=1,
+            projection_key=_key(change_id, "PLAN", 1),
+            projection_labels=labels,
+        )
+        target = _key(change_id, "IMPLEMENT", 2)
+
+    collision = await postgres_db.insert(
+        "work_queue",
+        {
+            "task_type": "issue",
+            "description": "ordinary issue owns exact projection tuple",
+            "input_data": {**target, "_projection_owner": "autopilot"},
+            "priority": 5,
+            "labels": [],
+        },
+    )
+    request = {
+        "task_type": "issue",
+        "description": "Autopilot phase target",
+        "priority": 1,
+        "projection_key": target,
+        "projection_labels": labels,
+    }
+    if mode == "submit":
+        result = await pg_work_queue.submit(**request)
+    else:
+        result = await pg_work_queue.reconcile_projection(**request)
+
+    assert result.success is False
+    assert result.reason == "projection_key_collision"
+    collision_id = str(collision["id"])
+    rows = await postgres_db.query("work_queue", f"id=eq.{collision_id}")
+    assert rows[0]["description"] == "ordinary issue owns exact projection tuple"
+    assert rows[0]["status"] == "pending"
+    assert rows[0]["labels"] == []
+    heads = await postgres_db.query("work_queue_projection_heads", f"change_id=eq.{change_id}")
+    if mode == "submit":
+        assert heads == []
+    else:
+        assert current is not None
+        assert [(row["phase"], row["transition_sequence"]) for row in heads] == [("PLAN", 1)]
+        current_rows = await postgres_db.query("work_queue", f"id=eq.{current.task_id}")
+        assert current_rows[0]["status"] == "pending"
+        assert current_rows[0]["labels"] == labels
+
+
+@pytest.mark.parametrize("mode", ["submit", "reconcile"])
+async def test_owned_same_generation_request_reactivates_terminal_canonical_issue(
+    mode,
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    change_id = f"live-reactivate-{mode}"
+    labels = [f"change:{change_id}", _PROJECTION_LABEL]
+    key = _key(change_id, "VALIDATE", 7)
+    canonical = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase VALIDATE",
+        priority=1,
+        projection_key=key,
+        projection_labels=labels,
+    )
+    await postgres_db.update(
+        "work_queue",
+        {"id": str(canonical.task_id)},
+        {
+            "status": "cancelled",
+            "result": {"reason": "prior terminal state"},
+            "error_message": "prior terminal state",
+        },
+    )
+    issues = IssueService(db=postgres_db)
+    assert await issues.list_issues(labels=labels) == []
+
+    request = {
+        "task_type": "issue",
+        "description": "Autopilot phase VALIDATE",
+        "priority": 1,
+        "projection_key": key,
+        "projection_labels": labels,
+    }
+    if mode == "submit":
+        result = await pg_work_queue.submit(**request)
+    else:
+        result = await pg_work_queue.reconcile_projection(**request)
+
+    assert result.success is True
+    visible = await issues.list_issues(labels=labels)
+    assert [(issue.id, issue.status) for issue in visible] == [(canonical.task_id, "pending")]
+    rows = await postgres_db.query("work_queue", f"id=eq.{canonical.task_id}")
+    assert rows[0]["claimed_by"] is None
+    assert rows[0]["claimed_at"] is None
+    assert rows[0]["started_at"] is None
+    assert rows[0]["completed_at"] is None
+    assert rows[0]["result"] is None
+    assert rows[0]["error_message"] is None
+
+
+@pytest.mark.parametrize("mode", ["submit", "reconcile"])
+async def test_owned_same_generation_replay_preserves_nonterminal_status(
+    mode,
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    change_id = f"live-preserve-nonterminal-{mode}"
+    labels = [f"change:{change_id}", _PROJECTION_LABEL]
+    key = _key(change_id, "IMPLEMENT", 5)
+    canonical = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase IMPLEMENT",
+        priority=1,
+        projection_key=key,
+        projection_labels=labels,
+    )
+    await postgres_db.update(
+        "work_queue",
+        {"id": str(canonical.task_id)},
+        {"status": "claimed", "claimed_by": "reviewer-agent"},
+    )
+
+    request = {
+        "task_type": "issue",
+        "description": "Autopilot phase IMPLEMENT replay",
+        "priority": 1,
+        "projection_key": key,
+        "projection_labels": labels,
+    }
+    if mode == "submit":
+        result = await pg_work_queue.submit(**request)
+    else:
+        result = await pg_work_queue.reconcile_projection(**request)
+
+    assert result.success is True
+    assert result.status == "claimed"
+    rows = await postgres_db.query("work_queue", f"id=eq.{canonical.task_id}")
+    assert rows[0]["status"] == "claimed"
+    assert rows[0]["claimed_by"] == "reviewer-agent"
+    assert rows[0]["labels"] == labels
+
+
+async def test_unlabelled_legacy_issue_collision_keeps_pre039_dedupe_semantics(
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    change_id = "live-legacy-unlabelled-collision"
+    key = _key(change_id, "INIT", 0)
+    collision = await postgres_db.insert(
+        "work_queue",
+        {
+            "task_type": "test",
+            "description": "legacy keyed row",
+            "input_data": key,
+            "priority": 5,
+            "labels": ["ordinary"],
+        },
+    )
+
+    result = await pg_work_queue.submit(
+        task_type="issue",
+        description="legacy unlabeled issue request",
+        projection_key=key,
+    )
+
+    assert result.success is True
+    assert result.created is False
+    assert str(result.task_id) == str(collision["id"])
+    rows = await postgres_db.query("work_queue", f"id=eq.{collision['id']}")
+    assert rows[0]["task_type"] == "test"
+    assert rows[0]["labels"] == ["ordinary"]
+
+
+async def test_terminal_reactivation_refreshes_connected_sse(
+    pg_work_queue,
+    postgres_db,
+) -> None:
+    change_id = "live-terminal-reactivation-sse"
+    labels = [f"change:{change_id}", _PROJECTION_LABEL]
+    key = _key(change_id, "VALIDATE", 7)
+    canonical = await pg_work_queue.submit(
+        task_type="issue",
+        description="Autopilot phase VALIDATE",
+        priority=1,
+        projection_key=key,
+        projection_labels=labels,
+    )
+    await postgres_db.update(
+        "work_queue",
+        {"id": str(canonical.task_id)},
+        {"status": "completed"},
+    )
+
+    bus = EventBusService(dsn=POSTGRES_DSN, channels=("coordinator_task",))
+    await bus.start()
+    await _wait_until_listening(bus)
+    stream = sse_event_generator([change_id], bus)
+    try:
+        initial = await asyncio.wait_for(stream.__anext__(), timeout=5)
+        initial_rows = json.loads(initial["data"])["work_queue"]
+        assert initial_rows[0]["status"] == "completed"
+
+        replay = await pg_work_queue.submit(
+            task_type="issue",
+            description="Autopilot phase VALIDATE",
+            priority=1,
+            projection_key=key,
+            projection_labels=labels,
+        )
+        assert replay.status == "pending"
+        refreshed = await asyncio.wait_for(stream.__anext__(), timeout=1)
+        refreshed_rows = json.loads(refreshed["data"])["work_queue"]
+        assert refreshed_rows[0]["status"] == "pending"
+    finally:
+        await stream.aclose()
+        await bus.stop()
diff --git a/agent-coordinator/tests/integration/postgres/test_fresh_database_migration.py b/agent-coordinator/tests/integration/postgres/test_fresh_database_migration.py
index f20d3097..a3d4c347 100644
--- a/agent-coordinator/tests/integration/postgres/test_fresh_database_migration.py
+++ b/agent-coordinator/tests/integration/postgres/test_fresh_database_migration.py
@@ -26,6 +26,7 @@ role permitted to CREATE DATABASE; skipped otherwise.
 from __future__ import annotations
 
 import asyncio
+import json
 import uuid
 
 import asyncpg
@@ -63,6 +64,8 @@ REQUIRED_FUNCTIONS = [
     "coordinator_notify",
     "get_agent_profile",
     "is_domain_allowed",
+    "mutate_issue_if_unowned",
+    "close_issues_if_unowned",
 ]
 
 
@@ -146,6 +149,234 @@ async def migrated_database():
             pass
 
 
+@pytest.fixture
+async def pre039_upgrade_database(tmp_path):
+    """A 038-era database upgraded through 039 with ambiguous labelled rows."""
+    if not _postgres_available:
+        pytest.skip("PostgreSQL not running (start with: docker-compose up -d)")
+
+    name = f"migtest_{uuid.uuid4().hex[:12]}"
+    try:
+        admin = await asyncio.wait_for(_connect(POSTGRES_DSN), timeout=ADMIN_TIMEOUT)
+    except (TimeoutError, OSError) as exc:
+        pytest.skip(f"could not reach PostgreSQL to create a test database: {exc}")
+
+    try:
+        await admin.execute(f'CREATE DATABASE "{name}"')
+    except asyncpg.InsufficientPrivilegeError:
+        pytest.skip("role may not CREATE DATABASE")
+    finally:
+        await admin.close()
+
+    dsn = _admin_dsn_for(name)
+    pre039_dir = tmp_path / "pre039"
+    post039_dir = tmp_path / "post039"
+    pre039_dir.mkdir()
+    post039_dir.mkdir()
+    for sequence, filename, path in discover_migrations():
+        if sequence < 39:
+            (pre039_dir / filename).symlink_to(path)
+        elif sequence == 39:
+            (post039_dir / filename).symlink_to(path)
+
+    try:
+        await asyncio.wait_for(
+            run_migrations(dsn, migrations_dir=pre039_dir), timeout=MIGRATE_TIMEOUT
+        )
+        conn = await _connect(dsn)
+        try:
+            legitimate_raw = await conn.fetchval(
+                "SELECT submit_task('issue', 'Autopilot phase INIT', $1::jsonb, "
+                "1, NULL::uuid[], NULL::timestamptz, NULL::jsonb, $2::text[])",
+                json.dumps(
+                    {
+                        "change_id": "upgrade-legitimate",
+                        "phase": "INIT",
+                        "transition_sequence": 0,
+                    }
+                ),
+                ["change:upgrade-legitimate", "projection:autopilot-phase"],
+            )
+            legitimate = json.loads(legitimate_raw)
+            assert legitimate["success"] is True
+            assert legitimate["created"] is True
+            legitimate_id = uuid.UUID(legitimate["task_id"])
+            spoof_id = await conn.fetchval(
+                "INSERT INTO work_queue "
+                "(task_type, description, input_data, priority, labels) "
+                "VALUES ('issue', 'ordinary spoof', $1::jsonb, 5, $2::text[]) "
+                "RETURNING id",
+                json.dumps(
+                    {
+                        "change_id": "upgrade-spoof",
+                        "phase": "PLAN",
+                        "transition_sequence": 7,
+                    }
+                ),
+                ["change:upgrade-spoof", "projection:autopilot-phase"],
+            )
+        finally:
+            await conn.close()
+
+        await asyncio.wait_for(
+            run_migrations(dsn, migrations_dir=post039_dir), timeout=MIGRATE_TIMEOUT
+        )
+        yield dsn, legitimate_id, spoof_id
+    finally:
+        try:
+            admin = await asyncio.wait_for(_connect(POSTGRES_DSN), timeout=ADMIN_TIMEOUT)
+            try:
+                await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
+            finally:
+                await admin.close()
+        except Exception:
+            pass
+
+
+async def test_039_upgrade_fails_closed_until_owner_registers_verified_row(
+    pre039_upgrade_database,
+) -> None:
+    dsn, legitimate_id, spoof_id = pre039_upgrade_database
+    labels = ["change:upgrade-legitimate", "projection:autopilot-phase"]
+    conn = await _connect(dsn)
+    try:
+        ownership = await conn.fetch(
+            "SELECT task_id FROM work_queue_projection_ownership ORDER BY task_id"
+        )
+        assert ownership == []
+
+        collision_raw = await conn.fetchval(
+            "SELECT submit_task('issue', 'Autopilot phase INIT', $1::jsonb, "
+            "1, NULL::uuid[], NULL::timestamptz, NULL::jsonb, $2::text[])",
+            json.dumps(
+                {
+                    "change_id": "upgrade-legitimate",
+                    "phase": "INIT",
+                    "transition_sequence": 0,
+                }
+            ),
+            labels,
+        )
+        collision = json.loads(collision_raw)
+        assert collision["success"] is False
+        assert collision["reason"] == "projection_key_collision"
+
+        reconcile_raw = await conn.fetchval(
+            "SELECT reconcile_work_projection('upgrade-legitimate', 'PLAN', 1, "
+            "'issue', 'Autopilot phase PLAN', '{}'::jsonb, 1, NULL::jsonb, "
+            "$1::text[])",
+            labels,
+        )
+        reconcile = json.loads(reconcile_raw)
+        assert reconcile["success"] is False
+        assert reconcile["reason"] == "projection_key_collision"
+        assert (
+            await conn.fetchval(
+                "SELECT COUNT(*) FROM work_queue WHERE input_data->>'change_id'="
+                "'upgrade-legitimate'"
+            )
+            == 1
+        )
+        assert await conn.fetchrow(
+            "SELECT phase, transition_sequence FROM work_queue_projection_heads "
+            "WHERE change_id='upgrade-legitimate'"
+        ) == ("INIT", 0)
+
+        await conn.execute(
+            "INSERT INTO work_queue_projection_ownership(task_id) VALUES ($1)",
+            legitimate_id,
+        )
+        replay_raw = await conn.fetchval(
+            "SELECT reconcile_work_projection('upgrade-legitimate', 'PLAN', 1, "
+            "'issue', 'Autopilot phase PLAN', '{}'::jsonb, 1, NULL::jsonb, "
+            "$1::text[])",
+            labels,
+        )
+        replay = json.loads(replay_raw)
+        assert replay["success"] is True
+        assert replay["created"] is True
+        assert str(legitimate_id) in replay["cancelled_task_ids"]
+        legitimate = await conn.fetchrow(
+            "SELECT status, labels FROM work_queue WHERE id=$1", legitimate_id
+        )
+        assert legitimate["status"] == "cancelled"
+        assert legitimate["labels"] == []
+
+        spoof = await conn.fetchrow(
+            "SELECT status, labels, result FROM work_queue WHERE id=$1", spoof_id
+        )
+        assert spoof["status"] == "pending"
+        assert spoof["labels"] == [
+            "change:upgrade-spoof",
+            "projection:autopilot-phase",
+        ]
+        assert spoof["result"] is None
+        assert (
+            await conn.fetchval(
+                "SELECT EXISTS (SELECT 1 FROM work_queue_projection_ownership WHERE task_id=$1)",
+                spoof_id,
+            )
+            is False
+        )
+    finally:
+        await conn.close()
+
+
+async def test_039_unlabelled_reconcile_fails_closed_on_reserved_upgrade_row(
+    pre039_upgrade_database,
+) -> None:
+    dsn, _legitimate_id, spoof_id = pre039_upgrade_database
+    conn = await _connect(dsn)
+    try:
+        result = json.loads(
+            await conn.fetchval(
+                "SELECT reconcile_work_projection('upgrade-spoof','IMPLEMENT',8,"
+                "'issue','legacy caller','{}'::jsonb,1,NULL::jsonb,NULL::text[])"
+            )
+        )
+        assert result["success"] is False
+        assert result["reason"] == "projection_key_collision"
+        assert await conn.fetchrow(
+            "SELECT status,labels FROM work_queue WHERE id=$1", spoof_id
+        ) == (
+            "pending",
+            ["change:upgrade-spoof", "projection:autopilot-phase"],
+        )
+        assert (
+            await conn.fetchval(
+                "SELECT COUNT(*) FROM work_queue_projection_heads WHERE change_id='upgrade-spoof'"
+            )
+            == 0
+        )
+    finally:
+        await conn.close()
+
+
+async def test_039_issue_mutation_fails_closed_on_reserved_upgrade_row(
+    pre039_upgrade_database,
+) -> None:
+    dsn, _legitimate_id, spoof_id = pre039_upgrade_database
+    conn = await _connect(dsn)
+    try:
+        result = json.loads(
+            await conn.fetchval(
+                "SELECT mutate_issue_if_unowned($1, $2::jsonb)",
+                spoof_id,
+                json.dumps({"status": "completed"}),
+            )
+        )
+        assert result["success"] is False
+        assert result["reason"] == "reserved_projection_label"
+        assert await conn.fetchrow(
+            "SELECT status,labels FROM work_queue WHERE id=$1", spoof_id
+        ) == (
+            "pending",
+            ["change:upgrade-spoof", "projection:autopilot-phase"],
+        )
+    finally:
+        await conn.close()
+
+
 async def test_every_migration_applies_to_an_empty_database(migrated_database) -> None:
     """No migration may be skipped, and none may fail.
 
@@ -161,6 +392,148 @@ async def test_every_migration_applies_to_an_empty_database(migrated_database) -
     )
 
 
+async def test_reserved_projection_rows_are_database_owned_and_issue_immutable(
+    migrated_database,
+) -> None:
+    dsn, _applied = migrated_database
+    change_id = "ordinary-issue-isolation"
+    labels = [f"change:{change_id}", "projection:autopilot-phase"]
+    conn = await _connect(dsn)
+    try:
+        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="reserved_projection_label"):
+            await conn.execute(
+                "INSERT INTO work_queue "
+                "(task_type,description,input_data,priority,labels) "
+                "VALUES ('issue','spoof','{}'::jsonb,5,$1::text[])",
+                labels,
+            )
+
+        ordinary_id = await conn.fetchval(
+            "INSERT INTO work_queue "
+            "(task_type,description,input_data,priority,labels) "
+            "VALUES ('issue','ordinary','{}'::jsonb,5,ARRAY[]::text[]) RETURNING id"
+        )
+        reserved_patch = json.loads(
+            await conn.fetchval(
+                "SELECT mutate_issue_if_unowned($1, $2::jsonb)",
+                ordinary_id,
+                json.dumps({"labels": labels}),
+            )
+        )
+        assert reserved_patch == {
+            "success": False,
+            "reason": "reserved_projection_label",
+        }
+
+        projected = json.loads(
+            await conn.fetchval(
+                "SELECT reconcile_work_projection($1,'INIT',0,'issue',"
+                "'Autopilot phase INIT','{}'::jsonb,1,NULL::jsonb,$2::text[])",
+                change_id,
+                labels,
+            )
+        )
+        assert projected["success"] is True
+        projection_id = uuid.UUID(projected["task_id"])
+        assert (
+            await conn.fetchval(
+                "SELECT labels=$2::text[] FROM work_queue WHERE id=$1",
+                projection_id,
+                labels,
+            )
+            is True
+        )
+
+        immutable = json.loads(
+            await conn.fetchval(
+                "SELECT mutate_issue_if_unowned($1, $2::jsonb)",
+                projection_id,
+                json.dumps({"description": "tampered", "status": "completed"}),
+            )
+        )
+        assert immutable == {
+            "success": False,
+            "reason": "projection_issue_immutable",
+        }
+        assert await conn.fetchrow(
+            "SELECT description,status,labels FROM work_queue WHERE id=$1",
+            projection_id,
+        ) == ("Autopilot phase INIT", "pending", labels)
+
+        second_ordinary_id = await conn.fetchval(
+            "INSERT INTO work_queue "
+            "(task_type,description,input_data,priority,labels) "
+            "VALUES ('issue','second ordinary','{}'::jsonb,5,ARRAY[]::text[]) "
+            "RETURNING id"
+        )
+        refused_batch = json.loads(
+            await conn.fetchval(
+                "SELECT close_issues_if_unowned($1::jsonb)",
+                json.dumps(
+                    {
+                        "issue_ids": [
+                            str(ordinary_id),
+                            str(projection_id),
+                            str(second_ordinary_id),
+                        ],
+                        "closed_at": "2026-09-14T14:00:00+00:00",
+                        "reason": None,
+                    }
+                ),
+            )
+        )
+        assert refused_batch == {
+            "success": False,
+            "reason": "projection_issue_immutable",
+        }
+        assert (
+            await conn.fetchval("SELECT status FROM work_queue WHERE id=$1", ordinary_id)
+            == "pending"
+        )
+        assert (
+            await conn.fetchval("SELECT status FROM work_queue WHERE id=$1", second_ordinary_id)
+            == "pending"
+        )
+
+        closed_batch = json.loads(
+            await conn.fetchval(
+                "SELECT close_issues_if_unowned($1::jsonb)",
+                json.dumps(
+                    {
+                        "issue_ids": [str(ordinary_id), str(second_ordinary_id)],
+                        "closed_at": "2026-09-14T14:00:00+00:00",
+                        "reason": "batch complete",
+                    }
+                ),
+            )
+        )
+        assert closed_batch["success"] is True
+        assert [uuid.UUID(row["id"]) for row in closed_batch["issues"]] == [
+            ordinary_id,
+            second_ordinary_id,
+        ]
+
+        advanced = json.loads(
+            await conn.fetchval(
+                "SELECT reconcile_work_projection($1,'PLAN',1,'issue',"
+                "'Autopilot phase PLAN','{}'::jsonb,1,NULL::jsonb,$2::text[])",
+                change_id,
+                labels,
+            )
+        )
+        assert advanced["success"] is True
+        assert (
+            await conn.fetchval(
+                "SELECT COUNT(*) FROM work_queue WHERE task_type='issue' "
+                "AND status='pending' AND labels @> $1::text[]",
+                labels,
+            )
+            == 1
+        )
+    finally:
+        await conn.close()
+
+
 async def test_fresh_database_has_the_objects_the_code_calls(migrated_database) -> None:
     """A migrated database must actually contain what the services dereference.
 
@@ -173,9 +546,7 @@ async def test_fresh_database_has_the_objects_the_code_calls(migrated_database)
     try:
         tables = {
             r["tablename"]
-            for r in await conn.fetch(
-                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
-            )
+            for r in await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
         }
         functions = {
             r["proname"]
@@ -254,9 +625,7 @@ async def test_seeded_database_survives_the_first_run_pass(migrated_database) ->
 
     conn = await _connect(dsn)
     try:
-        body = await conn.fetchval(
-            "SELECT pg_get_functiondef('notify_work_queue_change'::regproc)"
-        )
+        body = await conn.fetchval("SELECT pg_get_functiondef('notify_work_queue_change'::regproc)")
         recorded = await conn.fetchval("SELECT count(*) FROM schema_migrations")
     finally:
         await conn.close()
diff --git a/agent-coordinator/tests/integration/postgres/test_work_queue_postgres.py b/agent-coordinator/tests/integration/postgres/test_work_queue_postgres.py
index d9fba351..378c8628 100644
--- a/agent-coordinator/tests/integration/postgres/test_work_queue_postgres.py
+++ b/agent-coordinator/tests/integration/postgres/test_work_queue_postgres.py
@@ -340,6 +340,62 @@ class TestWorkQueueProjectionMigrationContract:
         assert replay.created is False
 
 
+    @pytest.mark.asyncio
+    async def test_concurrent_generations_leave_only_newest_projection_labelled(
+        self, pg_work_queue, postgres_db
+    ):
+        labels = [
+            "change:concurrent-projection",
+            "projection:autopilot-phase",
+        ]
+        old_key = {
+            "change_id": "concurrent-projection",
+            "phase": "IMPLEMENT",
+            "transition_sequence": 20,
+        }
+        new_key = {
+            "change_id": "concurrent-projection",
+            "phase": "VALIDATE",
+            "transition_sequence": 21,
+        }
+        await pg_work_queue.submit(
+            task_type="issue",
+            description="old generation",
+            projection_key=old_key,
+            projection_labels=labels,
+        )
+
+        await asyncio.gather(
+            pg_work_queue.reconcile_projection(
+                projection_key=old_key,
+                task_type="issue",
+                description="delayed old generation",
+                projection_labels=labels,
+            ),
+            pg_work_queue.reconcile_projection(
+                projection_key=new_key,
+                task_type="issue",
+                description="new generation",
+                projection_labels=labels,
+            ),
+        )
+
+        rows = await postgres_db.query(
+            "work_queue", "task_type=eq.issue&order=created_at.asc&limit=100"
+        )
+        labelled = [row for row in rows if row.get("labels") == labels]
+        assert len(labelled) == 1
+        assert labelled[0]["input_data"]["transition_sequence"] == 21
+        stale = [
+            row
+            for row in rows
+            if row["input_data"]["transition_sequence"] == 20
+        ]
+        assert stale
+        assert all(row["status"] == "cancelled" for row in stale)
+        assert all("projection:autopilot-phase" not in row.get("labels", []) for row in stale)
+
+
 class TestCompleteTaskTerminalCancellation:
     """Migration 036: cancellation by reconciliation must be terminal.
 
diff --git a/agent-coordinator/tests/test_autopilot_projection_visibility.py b/agent-coordinator/tests/test_autopilot_projection_visibility.py
new file mode 100644
index 00000000..ec89f6de
--- /dev/null
+++ b/agent-coordinator/tests/test_autopilot_projection_visibility.py
@@ -0,0 +1,345 @@
+"""Behavioral/static guards for migration 037 and live board refresh."""
+
+from __future__ import annotations
+
+import asyncio
+import json
+from pathlib import Path
+from typing import Any
+
+import pytest
+
+
+def test_migration_excludes_all_issue_rows_and_uses_old_label_fallback() -> None:
+    sql = (
+        Path(__file__).parents[1]
+        / "database/migrations/037_autopilot_phase_projection_visibility.sql"
+    ).read_text()
+    assert "task_type <> 'issue'" in sql
+    assert "DROP FUNCTION IF EXISTS claim_task(TEXT, TEXT, TEXT[])" in sql
+    assert "DROP FUNCTION IF EXISTS claim_task(TEXT, TEXT, TEXT[], TEXT[], INTEGER)" in sql
+    assert "projection:autopilot-phase" in sql
+    assert "NEW.labels" in sql
+    assert "OLD.labels" in sql
+
+
+def test_migration_038_atomically_repairs_owned_projection_labels() -> None:
+    sql = (
+        Path(__file__).parents[1] / "database/migrations/038_atomic_projection_labels.sql"
+    ).read_text()
+    compact = "".join(sql.split())
+    assert "p_projection_labelsTEXT[]DEFAULTNULL" in compact
+    assert "pg_advisory_xact_lock(hashtextextended" in sql
+    assert "projection:autopilot-phase" in sql
+    assert "labels=p_projection_labels" in compact
+    assert "status='cancelled'" in compact
+    assert "COMMIT;" in sql
+
+
+def test_projection_label_events_coalesce_into_one_fresh_snapshot(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    import src.event_stream as event_stream
+    from src.event_bus import CoordinatorEvent
+
+    class FakeBus:
+        task_cb: Any = None
+
+        def on_event(self, channel: str, callback: Any) -> None:
+            if channel == "coordinator_task":
+                self.task_cb = callback
+
+        def off_event(self, channel: str, callback: Any) -> bool:
+            return True
+
+    snapshots = 0
+
+    async def fake_snapshot(ids: list[str]) -> str:
+        nonlocal snapshots
+        snapshots += 1
+        return json.dumps({"work_queue": [], "subscribed_change_ids": ids})
+
+    monkeypatch.setattr(event_stream, "_build_snapshot", fake_snapshot)
+    bus = FakeBus()
+
+    async def drive() -> dict[str, Any]:
+        gen = event_stream.sse_event_generator(["demo"], bus)
+        await gen.__anext__()
+        event = CoordinatorEvent(
+            event_type="projection.labels_changed",
+            channel="coordinator_task",
+            entity_id="row",
+            agent_id="autopilot",
+            urgency="low",
+            summary="projection labels changed",
+            change_id="demo",
+        )
+        await bus.task_cb(event)
+        await bus.task_cb(event)
+        assert snapshots == 1
+        result = await gen.__anext__()
+        await gen.aclose()
+        return result
+
+    event = asyncio.run(drive())
+    assert event["event"] == "snapshot"
+    assert snapshots == 2
+
+
+def test_backpressure_drain_does_not_suppress_later_projection_refresh(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    import src.event_stream as event_stream
+    from src.event_bus import CoordinatorEvent
+
+    class FakeBus:
+        task_cb: Any = None
+
+        def on_event(self, channel: str, callback: Any) -> None:
+            if channel == "coordinator_task":
+                self.task_cb = callback
+
+        def off_event(self, channel: str, callback: Any) -> bool:
+            return True
+
+    snapshots = 0
+
+    async def fake_snapshot(ids: list[str]) -> str:
+        nonlocal snapshots
+        snapshots += 1
+        return json.dumps({"work_queue": [], "subscribed_change_ids": ids})
+
+    monkeypatch.setattr(event_stream, "_build_snapshot", fake_snapshot)
+    monkeypatch.setattr(event_stream, "_BACKPRESSURE_LIMIT", 2)
+    bus = FakeBus()
+
+    async def drive() -> dict[str, Any]:
+        gen = event_stream.sse_event_generator(["demo"], bus)
+        await gen.__anext__()
+        transition = CoordinatorEvent(
+            event_type="work.running",
+            channel="coordinator_task",
+            entity_id="row",
+            agent_id="worker",
+            urgency="low",
+            summary="work running",
+            change_id="demo",
+        )
+        projection = CoordinatorEvent(
+            event_type="projection.labels_changed",
+            channel="coordinator_task",
+            entity_id="projection-row",
+            agent_id="autopilot",
+            urgency="low",
+            summary="projection labels changed",
+            change_id="demo",
+        )
+        for _ in range(3):
+            await bus.task_cb(transition)
+        await bus.task_cb(projection)
+
+        assert (await gen.__anext__())["event"] == "transition"
+        assert (await gen.__anext__())["event"] == "transition"
+        assert (await gen.__anext__())["event"] == "snapshot"
+
+        await bus.task_cb(projection)
+        result = await asyncio.wait_for(gen.__anext__(), timeout=0.1)
+        await gen.aclose()
+        return result
+
+    event = asyncio.run(drive())
+    assert event["event"] == "snapshot"
+    assert snapshots == 3
+
+
+def test_projection_openapi_problem_contract_matches_runtime() -> None:
+    import yaml
+
+    contract_path = (
+        Path(__file__).parents[2] / "openspec/contracts/agent-coordinator/openapi/work-queue.yaml"
+    )
+    document = yaml.safe_load(contract_path.read_text())
+    problem = document["components"]["schemas"]["Problem"]
+    assert problem["required"] == ["type", "title", "status", "detail"]
+    assert problem["properties"]["status"]["type"] == "integer"
+
+    for name in ("Problem401", "Problem403", "Problem409", "Problem422"):
+        content = document["components"]["responses"][name]["content"]
+        assert set(content) == {"application/problem+json"}
+
+    submit = document["paths"]["/work/submit"]["post"]
+    reconcile = document["paths"]["/work/reconcile"]["post"]
+    assert (
+        "agent_requirements"
+        in (submit["requestBody"]["content"]["application/json"]["schema"]["properties"])
+    )
+    for operation in (submit, reconcile):
+        request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
+        assert request_schema["additionalProperties"] is False
+        properties = request_schema["properties"]
+        assert properties["task_type"]["minLength"] == 1
+        assert properties["task_description"]["minLength"] == 1
+        assert properties["priority"] == {
+            "type": "integer",
+            "minimum": 1,
+            "maximum": 10,
+        }
+        projection_labels = properties["projection_labels"]
+        assert projection_labels["minItems"] == 2
+        assert projection_labels["maxItems"] == 2
+        assert projection_labels["prefixItems"] == [
+            {
+                "type": "string",
+                "pattern": r"^change:[a-z0-9][a-z0-9-]{0,127}$",
+                "maxLength": 135,
+            },
+            {"type": "string", "const": "projection:autopilot-phase"},
+        ]
+        assert "MUST equal" in projection_labels["description"]
+        assert projection_labels["items"] is False
+        projection_condition = request_schema["allOf"][0]
+        assert projection_condition["if"] == {"required": ["projection_labels"]}
+        assert projection_condition["then"]["required"] == [
+            "projection_key",
+            "task_type",
+        ]
+        assert projection_condition["then"]["properties"]["task_type"] == {"const": "issue"}
+        assert (
+            operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
+            == "#/components/schemas/ProjectionMutationResult"
+        )
+        assert operation["responses"]["401"]["$ref"] == ("#/components/responses/Problem401")
+    assert (
+        submit["requestBody"]["content"]["application/json"]["schema"]["properties"]["depends_on"][
+            "items"
+        ]["format"]
+        == "uuid"
+    )
+
+
+def test_kanban_label_patch_openapi_declares_projection_forbidden() -> None:
+    import yaml
+
+    contract_path = (
+        Path(__file__).parents[2]
+        / "openspec/contracts/agent-coordinator/openapi/kanban-viz.yaml"
+    )
+    document = yaml.safe_load(contract_path.read_text())
+    responses = document["paths"]["/issues/{issue_id}/labels"]["patch"]["responses"]
+
+    assert "403" in responses
+    assert "projection" in responses["403"]["description"].lower()
+
+
+def test_projection_label_runtime_item_length_matches_openapi() -> None:
+    from pydantic import ValidationError
+
+    from src.coordination_api import WorkReconcileRequest, WorkSubmitRequest
+
+    common = {
+        "task_type": "issue",
+        "task_description": "phase projection",
+        "projection_key": {
+            "change_id": "ri-09",
+            "phase": "IMPLEMENT",
+            "transition_sequence": 9,
+        },
+        "projection_labels": ["x" * 161, "projection:autopilot-phase"],
+    }
+    with pytest.raises(ValidationError):
+        WorkSubmitRequest(**common)
+    with pytest.raises(ValidationError):
+        WorkReconcileRequest(**common)
+
+
+@pytest.mark.parametrize("request_type", ["submit", "reconcile"])
+def test_projection_label_runtime_uses_heterogeneous_prefix_bounds(
+    request_type: str,
+) -> None:
+    from pydantic import ValidationError
+
+    from src.coordination_api import WorkReconcileRequest, WorkSubmitRequest
+
+    request_model = (
+        WorkSubmitRequest if request_type == "submit" else WorkReconcileRequest
+    )
+    change_id = "a" * 128
+    common = {
+        "task_type": "issue",
+        "task_description": "phase projection",
+        "projection_key": {
+            "change_id": change_id,
+            "phase": "IMPLEMENT",
+            "transition_sequence": 9,
+        },
+    }
+    valid = request_model(
+        **common,
+        projection_labels=[
+            f"change:{change_id}",
+            "projection:autopilot-phase",
+        ],
+    )
+    assert tuple(valid.projection_labels or ()) == (
+        f"change:{change_id}",
+        "projection:autopilot-phase",
+    )
+
+    with pytest.raises(ValidationError):
+        request_model(
+            **common,
+            projection_labels=[
+                "change:" + "a" * 129,
+                "projection:autopilot-phase",
+            ],
+        )
+
+    with pytest.raises(ValidationError):
+        request_model(
+            **common,
+            projection_labels=[f"change:{change_id}", "x" * 160],
+        )
+
+
+def test_truth_projection_guide_documents_terminal_reactivation() -> None:
+    guide = (
+        Path(__file__).parents[2] / "docs/guides/work-queue-truth-projection.md"
+    ).read_text()
+    normalized = " ".join(guide.split())
+    assert "reactivated to `pending`" in normalized
+    assert "blocked rows remain blocked" in normalized
+
+
+def test_projection_payload_rejects_missing_canonical_task_id() -> None:
+    from types import SimpleNamespace
+
+    from src.coordination_api import _projection_mutation_payload, _ProjectionProblemError
+
+    result = SimpleNamespace(
+        success=True,
+        task_id=None,
+        created=False,
+        deduplicated=False,
+        status="pending",
+        cancelled_task_ids=[],
+    )
+    with pytest.raises(_ProjectionProblemError) as exc_info:
+        _projection_mutation_payload(result)
+    assert exc_info.value.reason == "canonical_task_id_missing"
+    assert exc_info.value.status == 422
+
+
+def test_projection_key_collision_maps_to_conflict() -> None:
+    from types import SimpleNamespace
+
+    from src.coordination_api import _projection_mutation_payload, _ProjectionProblemError
+
+    result = SimpleNamespace(
+        success=False,
+        failure_category=None,
+        reason="projection_key_collision",
+    )
+    with pytest.raises(_ProjectionProblemError) as exc_info:
+        _projection_mutation_payload(result)
+    assert exc_info.value.reason == "projection_key_collision"
+    assert exc_info.value.status == 409
diff --git a/agent-coordinator/tests/test_cedar_policy_engine.py b/agent-coordinator/tests/test_cedar_policy_engine.py
index 393f1397..3df053d6 100644
--- a/agent-coordinator/tests/test_cedar_policy_engine.py
+++ b/agent-coordinator/tests/test_cedar_policy_engine.py
@@ -130,6 +130,25 @@ class TestCedarAdminActions:
             )
             assert result.allowed is True, f"{action} should be allowed at trust 3"
 
+    @pytest.mark.asyncio
+    async def test_admin_resolves_trust_when_context_omits_it(
+        self, cedar_engine, monkeypatch
+    ):
+        async def _resolve(_agent_id: str, _agent_type: str) -> int:
+            return 3
+
+        monkeypatch.setattr("src.trust_resolution.resolve_trust_level", _resolve)
+
+        result = await cedar_engine.check_operation(
+            agent_id="coordinator-publisher",
+            agent_type="codex",
+            operation="publish_work_projection",
+            resource="change-a",
+            context={"mode": "reconcile", "change_id": "change-a"},
+        )
+
+        assert result.allowed is True
+
 
 class TestCedarSuspendedAgent:
     """Test Cedar forbid policy for suspended agents (trust 0)."""
diff --git a/agent-coordinator/tests/test_coordination_api.py b/agent-coordinator/tests/test_coordination_api.py
index a5b36d27..108d8738 100644
--- a/agent-coordinator/tests/test_coordination_api.py
+++ b/agent-coordinator/tests/test_coordination_api.py
@@ -425,7 +425,8 @@ def test_projection_submit_exposes_additive_result(
     mock_service.submit.return_value = SubmitResult(
         success=True, task_id=task_uuid, created=False, deduplicated=True, status="pending"
     )
-    monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())
+    authorize = AsyncMock()
+    monkeypatch.setattr("src.coordination_api.authorize_operation", authorize)
     import src.work_queue
 
     monkeypatch.setattr(src.work_queue, "_work_queue_service", mock_service)
@@ -451,9 +452,39 @@ def test_projection_submit_exposes_additive_result(
         "status": "pending",
         "cancelled_task_ids": [],
     }
+    assert authorize.await_args.kwargs["operation"] == "publish_work_projection"
+    assert authorize.await_args.kwargs["resource"] == "projection-change"
+    assert authorize.await_args.kwargs["context"]["change_id"] == "projection-change"
 
 
-def test_reconcile_authorizes_submit_work_mode_and_returns_cancellations(
+@pytest.mark.parametrize("path", ["/work/submit", "/work/reconcile"])
+def test_standard_trust_cannot_publish_projection(
+    client: TestClient, monkeypatch: pytest.MonkeyPatch, path: str
+) -> None:
+    mock_service = AsyncMock()
+    import src.work_queue
+
+    monkeypatch.setattr(src.work_queue, "_work_queue_service", mock_service)
+    response = client.post(
+        path,
+        headers=_auth_headers(),
+        json={
+            "task_type": "issue",
+            "task_description": "poison victim projection",
+            "projection_key": {
+                "change_id": "victim-change",
+                "phase": "DONE",
+                "transition_sequence": 2147483647,
+            },
+        },
+    )
+
+    assert response.status_code == 403
+    mock_service.submit.assert_not_awaited()
+    mock_service.reconcile_projection.assert_not_awaited()
+
+
+def test_reconcile_authorizes_projection_publish_and_returns_cancellations(
     client: TestClient, monkeypatch: pytest.MonkeyPatch
 ) -> None:
     from src.work_queue import ReconcileResult
@@ -488,17 +519,20 @@ def test_reconcile_authorizes_submit_work_mode_and_returns_cancellations(
     )
     assert response.status_code == 200
     assert response.json()["cancelled_task_ids"] == [str(UUID(int=2))]
-    assert authorize.await_args.kwargs["operation"] == "submit_work"
+    assert authorize.await_args.kwargs["operation"] == "publish_work_projection"
+    assert authorize.await_args.kwargs["resource"] == "projection-change"
+    assert authorize.await_args.kwargs["context"]["change_id"] == "projection-change"
     assert authorize.await_args.kwargs["context"]["mode"] == "reconcile"
 
 
-def test_stale_projection_returns_409_problem(
-    client: TestClient, monkeypatch: pytest.MonkeyPatch
+@pytest.mark.parametrize("reason", ["stale_projection", "projection_mode_mismatch"])
+def test_projection_conflict_returns_409_problem(
+    client: TestClient, monkeypatch: pytest.MonkeyPatch, reason: str
 ) -> None:
     from src.work_queue import SubmitResult
 
     mock_service = AsyncMock()
-    mock_service.submit.return_value = SubmitResult(success=False, reason="stale_projection")
+    mock_service.submit.return_value = SubmitResult(success=False, reason=reason)
     monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())
     import src.work_queue
 
@@ -518,7 +552,7 @@ def test_stale_projection_returns_409_problem(
     )
     assert response.status_code == 409
     assert response.headers["content-type"].startswith("application/problem+json")
-    assert response.json()["type"].endswith(":stale_projection")
+    assert response.json()["type"].endswith(f":{reason}")
 
 
 # =============================================================================
@@ -1158,3 +1192,51 @@ def test_projection_authentication_returns_401_problem(client: TestClient) -> No
     assert response.status_code == 401
     assert response.headers["content-type"].startswith("application/problem+json")
     assert response.json()["status"] == 401
+
+
+@pytest.mark.parametrize(
+    ("path", "method", "payload", "reason"),
+    [
+        (
+            "/issues/create",
+            "create",
+            {
+                "title": "spoof",
+                "labels": ["change:victim", "projection:autopilot-phase"],
+            },
+            "reserved_projection_label",
+        ),
+        (
+            "/issues/update",
+            "update",
+            {"issue_id": str(UUID(int=91)), "title": "tampered"},
+            "projection_issue_immutable",
+        ),
+        (
+            "/issues/close",
+            "close",
+            {"issue_id": str(UUID(int=91)), "reason": "tampered"},
+            "projection_issue_immutable",
+        ),
+    ],
+)
+def test_ordinary_issue_api_cannot_cross_projection_boundary(
+    client: TestClient,
+    monkeypatch: pytest.MonkeyPatch,
+    path: str,
+    method: str,
+    payload: dict[str, Any],
+    reason: str,
+) -> None:
+    from src.issue_service import ProjectionIssueMutationError
+
+    service = AsyncMock()
+    getattr(service, method).side_effect = ProjectionIssueMutationError(reason)
+    import src.issue_service
+
+    monkeypatch.setattr(src.issue_service, "_issue_service", service)
+
+    response = client.post(path, headers=_auth_headers(), json=payload)
+
+    assert response.status_code == 403
+    assert response.json()["detail"] == reason
diff --git a/agent-coordinator/tests/test_http_proxy.py b/agent-coordinator/tests/test_http_proxy.py
index 4f744aca..35d5195c 100644
--- a/agent-coordinator/tests/test_http_proxy.py
+++ b/agent-coordinator/tests/test_http_proxy.py
@@ -918,18 +918,27 @@ async def test_proxy_submit_and_reconcile_projection_payloads(
     monkeypatch.setattr(http_proxy, "_request", request)
     monkeypatch.setattr(http_proxy, "_agent_identity", lambda: {})
     key = {"change_id": "projection-change", "phase": "IMPLEMENT", "transition_sequence": 6}
+    labels = ["change:projection-change", "projection:autopilot-phase"]
 
     await http_proxy.proxy_submit_work(
-        task_type="implement", description="submit", projection_key=key
+        task_type="issue",
+        description="submit",
+        projection_key=key,
+        projection_labels=labels,
     )
     assert request.await_args_list[0].args[:2] == ("POST", "/work/submit")
     assert request.await_args_list[0].kwargs["json_body"]["projection_key"] == key
+    assert request.await_args_list[0].kwargs["json_body"]["projection_labels"] == labels
 
     await http_proxy.proxy_reconcile_work_projection(
-        projection_key=key, task_type="implement", description="resume"
+        projection_key=key,
+        task_type="issue",
+        description="resume",
+        projection_labels=labels,
     )
     assert request.await_args_list[1].args[:2] == ("POST", "/work/reconcile")
     assert request.await_args_list[1].kwargs["json_body"]["projection_key"] == key
+    assert request.await_args_list[1].kwargs["json_body"]["projection_labels"] == labels
 
 
 @pytest.mark.asyncio
@@ -962,9 +971,13 @@ async def test_projection_proxy_bodies_satisfy_strict_request_models(
     request = AsyncMock(return_value={"success": True})
     monkeypatch.setattr(http_proxy, "_request", request)
     key = {"change_id": "projection-change", "phase": "IMPLEMENT", "transition_sequence": 6}
+    labels = ["change:projection-change", "projection:autopilot-phase"]
 
     await http_proxy.proxy_submit_work(
-        task_type="implement", description="submit", projection_key=key
+        task_type="issue",
+        description="submit",
+        projection_key=key,
+        projection_labels=labels,
     )
     submit_body = request.await_args_list[0].kwargs["json_body"]
     assert "agent_id" not in submit_body
@@ -972,7 +985,10 @@ async def test_projection_proxy_bodies_satisfy_strict_request_models(
     WorkSubmitRequest.model_validate(submit_body)
 
     await http_proxy.proxy_reconcile_work_projection(
-        projection_key=key, task_type="implement", description="resume"
+        projection_key=key,
+        task_type="issue",
+        description="resume",
+        projection_labels=labels,
     )
     reconcile_body = request.await_args_list[1].kwargs["json_body"]
     assert "agent_id" not in reconcile_body
diff --git a/agent-coordinator/tests/test_issue_service.py b/agent-coordinator/tests/test_issue_service.py
index c2200c80..7f214385 100644
--- a/agent-coordinator/tests/test_issue_service.py
+++ b/agent-coordinator/tests/test_issue_service.py
@@ -72,8 +72,11 @@ class TestIssueCreate:
         """Create a basic issue with title and type."""
         issue_id = uuid4()
         mock_db.insert.return_value = _make_issue_row(
-            issue_id=issue_id, title="Fix CORS headers", issue_type="bug",
-            priority=3, labels=["api", "followup"],
+            issue_id=issue_id,
+            title="Fix CORS headers",
+            issue_type="bug",
+            priority=3,
+            labels=["api", "followup"],
         )
 
         issue = await service.create(
@@ -99,11 +102,14 @@ class TestIssueCreate:
         parent_id = uuid4()
         child_id = uuid4()
         mock_db.insert.return_value = _make_issue_row(
-            issue_id=child_id, title="Subtask", parent_id=parent_id,
+            issue_id=child_id,
+            title="Subtask",
+            parent_id=parent_id,
         )
 
         issue = await service.create(
-            title="Subtask", parent_id=parent_id,
+            title="Subtask",
+            parent_id=parent_id,
         )
 
         assert issue.parent_id == parent_id
@@ -116,11 +122,13 @@ class TestIssueCreate:
         dep1 = uuid4()
         dep2 = uuid4()
         mock_db.insert.return_value = _make_issue_row(
-            title="Blocked task", depends_on=[dep1, dep2],
+            title="Blocked task",
+            depends_on=[dep1, dep2],
         )
 
         issue = await service.create(
-            title="Blocked task", depends_on=[dep1, dep2],
+            title="Blocked task",
+            depends_on=[dep1, dep2],
         )
 
         assert len(issue.depends_on) == 2
@@ -151,6 +159,16 @@ class TestIssueCreate:
         with pytest.raises(ValueError, match="Priority must be 1-10"):
             await service.create(title="Bad", priority=0)
 
+    @pytest.mark.asyncio
+    async def test_create_rejects_reserved_projection_label(self, service, mock_db):
+        with pytest.raises(PermissionError, match="reserved_projection_label"):
+            await service.create(
+                title="spoof",
+                labels=["change:victim", "projection:autopilot-phase"],
+            )
+
+        mock_db.insert.assert_not_awaited()
+
 
 # ===========================================================================
 # Issue Listing
@@ -196,14 +214,31 @@ class TestIssueList:
         assert len(issues) == 1
         assert issues[0].title == "Match"
         query = mock_db.query.call_args[0][1]
+        assert "status=in.(pending,claimed,running,completed,failed,blocked)" in query
         assert "labels=cs." in query
         assert "api" in query
         assert "followup" in query
 
     @pytest.mark.asyncio
-    async def test_list_by_labels_does_not_post_filter_after_limit(
+    async def test_explicit_all_status_keeps_cancelled_labelled_issues_queryable(
         self, service, mock_db
     ):
+        mock_db.query.return_value = [
+            _make_issue_row(
+                title="Cancelled projection",
+                status="cancelled",
+                labels=["change:demo"],
+            )
+        ]
+
+        issues = await service.list_issues(status="all", labels=["change:demo"])
+
+        assert [issue.status for issue in issues] == ["cancelled"]
+        query = mock_db.query.call_args[0][1]
+        assert "status=in.(pending,claimed,running,completed,failed,blocked)" not in query
+
+    @pytest.mark.asyncio
+    async def test_list_by_labels_does_not_post_filter_after_limit(self, service, mock_db):
         """#429: LIMIT before label filter hid newly inserted rows.
 
         work_queue already has >= MAX_PAGE_SIZE issue rows. New writes persist
@@ -370,37 +405,63 @@ class TestIssueUpdate:
     async def test_update_labels(self, service, mock_db):
         """Update labels replaces the array."""
         issue_id = uuid4()
-        mock_db.update.return_value = [
-            _make_issue_row(issue_id=issue_id, labels=["api", "urgent"]),
-        ]
+        mock_db.rpc.return_value = {
+            "success": True,
+            "issue": _make_issue_row(issue_id=issue_id, labels=["api", "urgent"]),
+        }
 
         issue = await service.update(issue_id, labels=["api", "urgent"])
 
         assert issue is not None
-        update_data = mock_db.update.call_args[1]["data"]
+        assert mock_db.rpc.await_args.args[0] == "mutate_issue_if_unowned"
+        update_data = mock_db.rpc.await_args.args[1]["p_patch"]
         assert update_data["labels"] == ["api", "urgent"]
 
     @pytest.mark.asyncio
     async def test_update_status_mapping(self, service, mock_db):
         """Update status maps friendly names to DB values."""
         issue_id = uuid4()
-        mock_db.update.return_value = [
-            _make_issue_row(issue_id=issue_id, status="running"),
-        ]
+        mock_db.rpc.return_value = {
+            "success": True,
+            "issue": _make_issue_row(issue_id=issue_id, status="running"),
+        }
 
         await service.update(issue_id, status="in_progress")
 
-        update_data = mock_db.update.call_args[1]["data"]
+        update_data = mock_db.rpc.await_args.args[1]["p_patch"]
         assert update_data["status"] == "running"
 
     @pytest.mark.asyncio
     async def test_update_not_found(self, service, mock_db):
         """Update returns None when issue doesn't exist."""
-        mock_db.update.return_value = []
+        mock_db.rpc.return_value = {"success": False, "reason": "issue_not_found"}
 
         issue = await service.update(uuid4(), title="New title")
         assert issue is None
 
+    @pytest.mark.asyncio
+    async def test_update_rejects_reserved_projection_label(self, service, mock_db):
+        with pytest.raises(PermissionError, match="reserved_projection_label"):
+            await service.update(
+                uuid4(),
+                labels=["change:victim", "projection:autopilot-phase"],
+            )
+
+        mock_db.update.assert_not_awaited()
+        mock_db.rpc.assert_not_awaited()
+
+    @pytest.mark.asyncio
+    async def test_update_rejects_registry_owned_projection(self, service, mock_db):
+        mock_db.rpc.return_value = {
+            "success": False,
+            "reason": "projection_issue_immutable",
+        }
+
+        with pytest.raises(PermissionError, match="projection_issue_immutable"):
+            await service.update(uuid4(), title="tampered")
+
+        mock_db.update.assert_not_awaited()
+
 
 # ===========================================================================
 # Issue Close
@@ -412,34 +473,37 @@ class TestIssueClose:
     async def test_close_with_reason(self, service, mock_db):
         """Close sets status, timestamps, and reason."""
         issue_id = uuid4()
-        mock_db.update.return_value = [
-            _make_issue_row(issue_id=issue_id, status="completed"),
-        ]
+        mock_db.rpc.return_value = {
+            "success": True,
+            "issues": [_make_issue_row(issue_id=issue_id, status="completed")],
+        }
 
         results = await service.close(issue_id=issue_id, reason="Done in PR #42")
 
         assert len(results) == 1
-        update_data = mock_db.update.call_args[1]["data"]
-        assert update_data["status"] == "completed"
-        assert update_data["close_reason"] == "Done in PR #42"
-        assert "closed_at" in update_data
-        # DatabaseClient contract is PostgREST JSON: ISO strings, not
-        # datetime objects. DirectPostgresClient coerces them on bind.
-        assert isinstance(update_data["closed_at"], str)
-        assert isinstance(update_data["completed_at"], str)
-        datetime.fromisoformat(update_data["closed_at"])
-        datetime.fromisoformat(update_data["completed_at"])
+        request = mock_db.rpc.await_args.args[1]["p_request"]
+        assert request["reason"] == "Done in PR #42"
+        assert request["issue_ids"] == [str(issue_id)]
+        assert isinstance(request["closed_at"], str)
+        datetime.fromisoformat(request["closed_at"])
 
     @pytest.mark.asyncio
     async def test_batch_close(self, service, mock_db):
         """Batch close multiple issues."""
         ids = [uuid4(), uuid4(), uuid4()]
-        mock_db.update.return_value = [_make_issue_row(status="completed")]
+        mock_db.rpc.return_value = {
+            "success": True,
+            "issues": [_make_issue_row(issue_id=issue_id, status="completed") for issue_id in ids],
+        }
 
         results = await service.close(issue_ids=ids)
 
-        assert len(results) == 3
-        assert mock_db.update.call_count == 3
+        assert [issue.id for issue in results] == ids
+        mock_db.rpc.assert_awaited_once()
+        assert mock_db.rpc.await_args.args[0] == "close_issues_if_unowned"
+        assert mock_db.rpc.await_args.args[1]["p_request"]["issue_ids"] == [
+            str(issue_id) for issue_id in ids
+        ]
 
     @pytest.mark.asyncio
     async def test_close_no_ids_raises(self, service):
@@ -447,6 +511,18 @@ class TestIssueClose:
         with pytest.raises(ValueError, match="Must provide"):
             await service.close()
 
+    @pytest.mark.asyncio
+    async def test_close_rejects_registry_owned_projection(self, service, mock_db):
+        mock_db.rpc.return_value = {
+            "success": False,
+            "reason": "projection_issue_immutable",
+        }
+
+        with pytest.raises(PermissionError, match="projection_issue_immutable"):
+            await service.close(issue_id=uuid4())
+
+        mock_db.update.assert_not_awaited()
+
 
 # ===========================================================================
 # Issue Comments
@@ -592,8 +668,11 @@ class TestIssueModel:
     def test_from_row(self):
         """Issue.from_row correctly maps work_queue columns."""
         row = _make_issue_row(
-            title="Test", issue_type="bug", priority=3,
-            labels=["api"], assignee="agent-1",
+            title="Test",
+            issue_type="bug",
+            priority=3,
+            labels=["api"],
+            assignee="agent-1",
         )
         issue = Issue.from_row(row)
 
diff --git a/agent-coordinator/tests/test_kanban_viz_endpoints.py b/agent-coordinator/tests/test_kanban_viz_endpoints.py
index 37525d11..47a72285 100644
--- a/agent-coordinator/tests/test_kanban_viz_endpoints.py
+++ b/agent-coordinator/tests/test_kanban_viz_endpoints.py
@@ -487,6 +487,38 @@ def test_patch_issue_labels_adds_and_removes(
     fake_service.update.assert_called_once()
 
 
+@pytest.mark.parametrize(
+    "reason", ["projection_issue_immutable", "reserved_projection_label"]
+)
+def test_patch_issue_labels_maps_projection_refusal_to_forbidden(
+    client: TestClient,
+    monkeypatch: pytest.MonkeyPatch,
+    reason: str,
+) -> None:
+    import uuid
+
+    from src import issue_service as ism
+
+    issue_id = str(uuid.uuid4())
+    fake_issue = MagicMock()
+    fake_issue.labels = ["change:abc"]
+    fake_service = AsyncMock()
+    fake_service.show = AsyncMock(return_value=fake_issue)
+    fake_service.update = AsyncMock(
+        side_effect=ism.ProjectionIssueMutationError(reason)
+    )
+    monkeypatch.setattr(ism, "IssueService", lambda: fake_service)
+
+    response = client.patch(
+        f"/issues/{issue_id}/labels",
+        json={"add": ["projection:autopilot-phase"], "remove": []},
+        headers=_auth_headers(),
+    )
+
+    assert response.status_code == 403
+    assert response.json()["detail"] == reason
+
+
 def test_patch_issue_labels_requires_auth(client: TestClient) -> None:
     """2.7d: PATCH /issues/{id}/labels requires API key → 401 without key."""
     resp = client.patch(
diff --git a/agent-coordinator/tests/test_mcp_work_projection.py b/agent-coordinator/tests/test_mcp_work_projection.py
index dd13ddeb..87f6a82c 100644
--- a/agent-coordinator/tests/test_mcp_work_projection.py
+++ b/agent-coordinator/tests/test_mcp_work_projection.py
@@ -20,18 +20,23 @@ async def test_direct_mcp_submit_exposes_deduplicated_result(monkeypatch):
     monkeypatch.setattr(coordination_mcp, "get_work_queue_service", lambda: service)
 
     result = await coordination_mcp.submit_work(
-        task_type="implement",
+        task_type="issue",
         description="project",
         projection_key={
             "change_id": "projection-change",
             "phase": "IMPLEMENT",
             "transition_sequence": 3,
         },
+        projection_labels=["change:projection-change", "projection:autopilot-phase"],
     )
 
     assert result["task_id"] == str(task_id)
     assert result["created"] is False
     assert result["deduplicated"] is True
+    assert service.submit.await_args.kwargs["projection_labels"] == [
+        "change:projection-change",
+        "projection:autopilot-phase",
+    ]
 
 
 @pytest.mark.asyncio
@@ -55,12 +60,17 @@ async def test_direct_mcp_reconcile_maps_projection_result(monkeypatch):
             "phase": "IMPLEMENT",
             "transition_sequence": 4,
         },
-        task_type="implement",
+        task_type="issue",
         description="resume",
+        projection_labels=["change:projection-change", "projection:autopilot-phase"],
     )
 
     assert result["cancelled_task_ids"] == [str(UUID(int=2))]
     assert result["created"] is True
+    assert service.reconcile_projection.await_args.kwargs["projection_labels"] == [
+        "change:projection-change",
+        "projection:autopilot-phase",
+    ]
 
 
 @pytest.mark.asyncio
@@ -77,8 +87,13 @@ async def test_proxy_mcp_forwards_one_explicit_projection_key(monkeypatch):
     monkeypatch.setattr(coordination_mcp.http_proxy, "proxy_submit_work", proxy)
     key = {"change_id": "projection-change", "phase": "IMPLEMENT", "transition_sequence": 5}
 
+    labels = ["change:projection-change", "projection:autopilot-phase"]
     await coordination_mcp.submit_work(
-        task_type="implement", description="proxy", projection_key=key
+        task_type="issue",
+        description="proxy",
+        projection_key=key,
+        projection_labels=labels,
     )
 
     assert proxy.await_args.kwargs["projection_key"] == key
+    assert proxy.await_args.kwargs["projection_labels"] == labels
diff --git a/agent-coordinator/tests/test_policy_engine.py b/agent-coordinator/tests/test_policy_engine.py
index 156be096..257d61c5 100644
--- a/agent-coordinator/tests/test_policy_engine.py
+++ b/agent-coordinator/tests/test_policy_engine.py
@@ -218,6 +218,7 @@ class TestActionCategories:
         assert "force_push" in ADMIN_ACTIONS
         assert "delete_branch" in ADMIN_ACTIONS
         assert "cleanup_agents" in ADMIN_ACTIONS
+        assert "publish_work_projection" in ADMIN_ACTIONS
 
     def test_allowed_domains(self):
         """Test allowed domains are defined."""
diff --git a/agent-coordinator/tests/test_profile_sync.py b/agent-coordinator/tests/test_profile_sync.py
index 908534da..def6d2da 100644
--- a/agent-coordinator/tests/test_profile_sync.py
+++ b/agent-coordinator/tests/test_profile_sync.py
@@ -315,6 +315,8 @@ class TestDeriveAllowedOperations:
         }
         assert merge_ops.isdisjoint(low)
         assert merge_ops.issubset(high)
+        assert "publish_work_projection" not in low
+        assert "publish_work_projection" in high
 
     def test_output_is_sorted_and_deduplicated(self) -> None:
         # feature_registry and trust>=3 both grant register_feature.
@@ -331,7 +333,7 @@ class TestClaudeCodeLocalRegression:
     """Task 2.5 — the derived grants must reproduce migrations 007/019/022.
 
     ``claude_code_cli`` was seeded by 007, renamed to ``claude_code_local`` by
-    019, and topped up by 022. The union below is what a live deployment's row
+    019, and topped up by 022 and 039. The union below is what a live deployment's row
     holds today; the projection must not silently drop any of it.
     """
 
@@ -360,6 +362,7 @@ class TestClaudeCodeLocalRegression:
         "run_pre_merge_checks",
         "mark_merged",
         "remove_from_merge_queue",
+        "publish_work_projection",
     }
 
     def test_derived_operations_match_migrations(self) -> None:
diff --git a/agent-coordinator/tests/test_trust_resolution_fail_open.py b/agent-coordinator/tests/test_trust_resolution_fail_open.py
index 1fec279d..17ba47b8 100644
--- a/agent-coordinator/tests/test_trust_resolution_fail_open.py
+++ b/agent-coordinator/tests/test_trust_resolution_fail_open.py
@@ -137,11 +137,15 @@ class _FakeGuardrails:
 class _SubmitDB:
     def __init__(self) -> None:
         self.submitted = False
+        self.reconciled = False
 
     async def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
         if function_name == "submit_task":
             self.submitted = True
             return {"success": True, "task_id": "00000000-0000-4000-8000-000000000123"}
+        if function_name == "reconcile_work_projection":
+            self.reconciled = True
+            return {"success": True, "task_id": "00000000-0000-4000-8000-000000000124"}
         return {}
 
     async def query(self, *args: Any, **kwargs: Any) -> list[Any]:
@@ -211,7 +215,7 @@ class TestTrustFailureNeverSkipsGuardrails:
             Path(__file__).resolve().parent.parent / "src" / "work_queue.py"
         ).read_text()
 
-        for phase in ("claim", "complete", "submit"):
+        for phase in ("claim", "complete", "submit", "reconcile"):
             marker = f'"Guardrails check failed during {phase}"'
             assert marker in source, f"guardrail handler for {phase} not found"
             preceding = source[: source.index(marker)]
@@ -221,6 +225,34 @@ class TestTrustFailureNeverSkipsGuardrails:
                 f"TrustResolutionError and skip the scan"
             )
 
+    async def test_reconcile_propagates_instead_of_writing_unscanned(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        from src import guardrails, trust_resolution
+
+        async def _boom(agent_id: str, agent_type: str, *a: Any, **k: Any) -> int:
+            raise TrustResolutionError(agent_id, agent_type, "projection broken")
+
+        monkeypatch.setattr(trust_resolution, "resolve_trust_level", _boom)
+        scanner = _FakeGuardrails()
+        monkeypatch.setattr(guardrails, "get_guardrails_service", lambda: scanner)
+
+        db = _SubmitDB()
+        service = WorkQueueService(db=db)
+        with pytest.raises(TrustResolutionError):
+            await service.reconcile_projection(
+                projection_key={
+                    "change_id": "guarded-change",
+                    "phase": "IMPLEMENT",
+                    "transition_sequence": 3,
+                },
+                task_type="issue",
+                description="rm -rf / --no-preserve-root",
+            )
+
+        assert not scanner.called
+        assert not db.reconciled
+
 
 # ---------------------------------------------------------------------------
 # Follow-up (PR #465 review, P1): trust resolution ran *after* claim_task had
diff --git a/agent-coordinator/tests/test_work_queue.py b/agent-coordinator/tests/test_work_queue.py
index 3767f551..abdd28b7 100644
--- a/agent-coordinator/tests/test_work_queue.py
+++ b/agent-coordinator/tests/test_work_queue.py
@@ -1,5 +1,6 @@
 """Tests for the work queue service."""
 
+import json
 from uuid import UUID
 
 import pytest
@@ -640,7 +641,18 @@ def test_projection_migration_declares_full_head_and_atomic_paths():
 
 
 @pytest.mark.asyncio
-async def test_projection_submit_returns_canonical_deduplicated_result(mock_supabase, db_client):
+async def test_projection_submit_returns_canonical_deduplicated_result(
+    mock_supabase, db_client, monkeypatch
+):
+    class AllowProjectionPolicy:
+        async def check_operation(self, **kwargs):
+            assert kwargs["operation"] == "publish_work_projection"
+            assert kwargs["resource"] == "projection-change"
+            return PolicyDecision.allow()
+
+    monkeypatch.setattr(
+        "src.policy_engine.get_policy_engine", lambda: AllowProjectionPolicy()
+    )
     task_id = UUID(int=7)
     mock_supabase.post("https://test.supabase.co/rest/v1/rpc/submit_task").mock(
         return_value=Response(
@@ -654,17 +666,26 @@ async def test_projection_submit_returns_canonical_deduplicated_result(mock_supa
         )
     )
     result = await WorkQueueService(db_client).submit(
-        task_type="implement",
+        task_type="issue",
         description="project current phase",
         projection_key={
             "change_id": "projection-change",
             "phase": "IMPLEMENT",
             "transition_sequence": 4,
         },
+        projection_labels=[
+            "change:projection-change",
+            "projection:autopilot-phase",
+        ],
     )
     assert result.task_id == task_id
     assert result.created is False
     assert result.deduplicated is True
+    request = mock_supabase.calls.last.request
+    assert json.loads(request.content)["p_projection_labels"] == [
+        "change:projection-change",
+        "projection:autopilot-phase",
+    ]
 
 
 @pytest.mark.asyncio
@@ -713,7 +734,18 @@ async def test_unkeyed_submit_rejects_reserved_projection_identity(db_client):
 
 
 @pytest.mark.asyncio
-async def test_reconcile_returns_sorted_cancelled_ids(mock_supabase, db_client):
+async def test_reconcile_returns_sorted_cancelled_ids(
+    mock_supabase, db_client, monkeypatch
+):
+    class AllowProjectionPolicy:
+        async def check_operation(self, **kwargs):
+            assert kwargs["operation"] == "publish_work_projection"
+            assert kwargs["resource"] == "projection-change"
+            return PolicyDecision.allow()
+
+    monkeypatch.setattr(
+        "src.policy_engine.get_policy_engine", lambda: AllowProjectionPolicy()
+    )
     current = UUID(int=8)
     cancelled = [UUID(int=3), UUID(int=2)]
     mock_supabase.post("https://test.supabase.co/rest/v1/rpc/reconcile_work_projection").mock(
@@ -734,19 +766,30 @@ async def test_reconcile_returns_sorted_cancelled_ids(mock_supabase, db_client):
             "phase": "IMPLEMENT",
             "transition_sequence": 5,
         },
-        task_type="implement",
+        task_type="issue",
         description="resume",
+        projection_labels=[
+            "change:projection-change",
+            "projection:autopilot-phase",
+        ],
     )
     assert result.success is True
+    request = mock_supabase.calls.last.request
+    assert json.loads(request.content)["p_projection_labels"] == [
+        "change:projection-change",
+        "projection:autopilot-phase",
+    ]
     assert result.cancelled_task_ids == sorted(cancelled, key=str)
 
 
 @pytest.mark.asyncio
-async def test_reconcile_enforces_submit_work_policy_with_mode(monkeypatch):
+async def test_reconcile_enforces_projection_publish_policy_with_change(monkeypatch):
     class DenyPolicyEngine:
         async def check_operation(self, **kwargs):
-            assert kwargs["operation"] == "submit_work"
+            assert kwargs["operation"] == "publish_work_projection"
+            assert kwargs["resource"] == "projection-change"
             assert kwargs["context"]["mode"] == "reconcile"
+            assert kwargs["context"]["change_id"] == "projection-change"
             return PolicyDecision.deny("operation_not_permitted")
 
     class FailDB:
diff --git a/docs/architecture-analysis/architecture.diagnostics.json b/docs/architecture-analysis/architecture.diagnostics.json
index b1b246dd..1893581b 100644
--- a/docs/architecture-analysis/architecture.diagnostics.json
+++ b/docs/architecture-analysis/architecture.diagnostics.json
@@ -1,5 +1,5 @@
 {
-  "generated_at": "2026-09-14T05:30:41+00:00",
+  "generated_at": "2026-09-14T14:49:14+00:00",
   "scope": "full",
   "changed_files": [],
   "findings": [
@@ -9,7 +9,7 @@
       "message": "Entrypoint 'acquire_lock' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.acquire_lock",
       "file": "coordination_api.py",
-      "line": 950,
+      "line": 971,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -18,7 +18,7 @@
       "message": "Entrypoint 'release_lock' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.release_lock",
       "file": "coordination_api.py",
-      "line": 987,
+      "line": 1006,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -27,7 +27,7 @@
       "message": "Entrypoint 'check_lock_status' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.check_lock_status",
       "file": "coordination_api.py",
-      "line": 1016,
+      "line": 1033,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -36,7 +36,7 @@
       "message": "Entrypoint 'store_memory' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.store_memory",
       "file": "coordination_api.py",
-      "line": 1042,
+      "line": 1059,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -45,7 +45,7 @@
       "message": "Entrypoint 'query_memories' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.query_memories",
       "file": "coordination_api.py",
-      "line": 1074,
+      "line": 1091,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -54,7 +54,7 @@
       "message": "Entrypoint 'claim_work' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.claim_work",
       "file": "coordination_api.py",
-      "line": 1119,
+      "line": 1134,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -63,7 +63,7 @@
       "message": "Entrypoint 'complete_work' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.complete_work",
       "file": "coordination_api.py",
-      "line": 1153,
+      "line": 1166,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -72,7 +72,7 @@
       "message": "Entrypoint 'submit_work' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.submit_work",
       "file": "coordination_api.py",
-      "line": 1185,
+      "line": 1198,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -81,7 +81,7 @@
       "message": "Entrypoint 'reconcile_work_projection' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.reconcile_work_projection",
       "file": "coordination_api.py",
-      "line": 1220,
+      "line": 1250,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -90,7 +90,7 @@
       "message": "Entrypoint 'get_task_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.get_task_endpoint",
       "file": "coordination_api.py",
-      "line": 1248,
+      "line": 1283,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -99,7 +99,7 @@
       "message": "Entrypoint 'create_issue' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.create_issue",
       "file": "coordination_api.py",
-      "line": 1295,
+      "line": 1330,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -108,7 +108,7 @@
       "message": "Entrypoint 'list_issues' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.list_issues",
       "file": "coordination_api.py",
-      "line": 1329,
+      "line": 1364,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -117,7 +117,7 @@
       "message": "Entrypoint 'blocked_issues_early' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.blocked_issues_early",
       "file": "coordination_api.py",
-      "line": 1356,
+      "line": 1391,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -126,7 +126,7 @@
       "message": "Entrypoint 'show_issue' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.show_issue",
       "file": "coordination_api.py",
-      "line": 1373,
+      "line": 1408,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -135,7 +135,7 @@
       "message": "Entrypoint 'update_issue' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.update_issue",
       "file": "coordination_api.py",
-      "line": 1390,
+      "line": 1425,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -144,7 +144,7 @@
       "message": "Entrypoint 'close_issue' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.close_issue",
       "file": "coordination_api.py",
-      "line": 1422,
+      "line": 1459,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -153,7 +153,7 @@
       "message": "Entrypoint 'comment_issue' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.comment_issue",
       "file": "coordination_api.py",
-      "line": 1454,
+      "line": 1493,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -162,7 +162,7 @@
       "message": "Entrypoint 'check_guardrails' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.check_guardrails",
       "file": "coordination_api.py",
-      "line": 1476,
+      "line": 1515,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -171,7 +171,7 @@
       "message": "Entrypoint 'get_my_profile' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.get_my_profile",
       "file": "coordination_api.py",
-      "line": 1522,
+      "line": 1561,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -180,7 +180,7 @@
       "message": "Entrypoint 'get_agent_dispatch_configs' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.get_agent_dispatch_configs",
       "file": "coordination_api.py",
-      "line": 1552,
+      "line": 1591,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -189,7 +189,7 @@
       "message": "Entrypoint 'query_audit' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.query_audit",
       "file": "coordination_api.py",
-      "line": 1566,
+      "line": 1605,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -198,7 +198,7 @@
       "message": "Entrypoint 'write_handoff' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.write_handoff",
       "file": "coordination_api.py",
-      "line": 1626,
+      "line": 1665,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -207,7 +207,7 @@
       "message": "Entrypoint 'read_handoff' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.read_handoff",
       "file": "coordination_api.py",
-      "line": 1658,
+      "line": 1695,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -216,7 +216,7 @@
       "message": "Entrypoint 'check_policy' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.check_policy",
       "file": "coordination_api.py",
-      "line": 1701,
+      "line": 1736,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -225,7 +225,7 @@
       "message": "Entrypoint 'validate_cedar_policy' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.validate_cedar_policy",
       "file": "coordination_api.py",
-      "line": 1728,
+      "line": 1761,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -234,7 +234,7 @@
       "message": "Entrypoint 'allocate_ports' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.allocate_ports",
       "file": "coordination_api.py",
-      "line": 1759,
+      "line": 1792,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -243,7 +243,7 @@
       "message": "Entrypoint 'release_ports' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.release_ports",
       "file": "coordination_api.py",
-      "line": 1781,
+      "line": 1814,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -252,7 +252,7 @@
       "message": "Entrypoint 'port_status' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.port_status",
       "file": "coordination_api.py",
-      "line": 1790,
+      "line": 1823,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -261,7 +261,7 @@
       "message": "Entrypoint 'list_pending_approvals' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.list_pending_approvals",
       "file": "coordination_api.py",
-      "line": 1830,
+      "line": 1861,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -270,7 +270,7 @@
       "message": "Entrypoint 'decide_approval' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.decide_approval",
       "file": "coordination_api.py",
-      "line": 1841,
+      "line": 1872,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -279,7 +279,7 @@
       "message": "Entrypoint 'list_policy_versions_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.list_policy_versions_endpoint",
       "file": "coordination_api.py",
-      "line": 1868,
+      "line": 1899,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -288,7 +288,7 @@
       "message": "Entrypoint 'rollback_policy_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.rollback_policy_endpoint",
       "file": "coordination_api.py",
-      "line": 1881,
+      "line": 1912,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -297,7 +297,7 @@
       "message": "Entrypoint 'register_feature_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.register_feature_endpoint",
       "file": "coordination_api.py",
-      "line": 1900,
+      "line": 1931,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -306,7 +306,7 @@
       "message": "Entrypoint 'deregister_feature_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.deregister_feature_endpoint",
       "file": "coordination_api.py",
-      "line": 1934,
+      "line": 1963,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -315,7 +315,7 @@
       "message": "Entrypoint 'get_feature_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.get_feature_endpoint",
       "file": "coordination_api.py",
-      "line": 1961,
+      "line": 1990,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -324,7 +324,7 @@
       "message": "Entrypoint 'list_active_features_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.list_active_features_endpoint",
       "file": "coordination_api.py",
-      "line": 1985,
+      "line": 2014,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -333,7 +333,7 @@
       "message": "Entrypoint 'analyze_feature_conflicts_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.analyze_feature_conflicts_endpoint",
       "file": "coordination_api.py",
-      "line": 2015,
+      "line": 2044,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -342,7 +342,7 @@
       "message": "Entrypoint 'enqueue_merge_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.enqueue_merge_endpoint",
       "file": "coordination_api.py",
-      "line": 2039,
+      "line": 2068,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -351,7 +351,7 @@
       "message": "Entrypoint 'get_merge_queue_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.get_merge_queue_endpoint",
       "file": "coordination_api.py",
-      "line": 2072,
+      "line": 2101,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -360,7 +360,7 @@
       "message": "Entrypoint 'get_next_merge_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.get_next_merge_endpoint",
       "file": "coordination_api.py",
-      "line": 2101,
+      "line": 2130,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -369,7 +369,7 @@
       "message": "Entrypoint 'run_pre_merge_checks_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.run_pre_merge_checks_endpoint",
       "file": "coordination_api.py",
-      "line": 2122,
+      "line": 2151,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -378,7 +378,7 @@
       "message": "Entrypoint 'mark_merged_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.mark_merged_endpoint",
       "file": "coordination_api.py",
-      "line": 2147,
+      "line": 2176,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -387,7 +387,7 @@
       "message": "Entrypoint 'remove_from_merge_queue_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.remove_from_merge_queue_endpoint",
       "file": "coordination_api.py",
-      "line": 2166,
+      "line": 2195,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -396,7 +396,7 @@
       "message": "Entrypoint 'compose_train_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.compose_train_endpoint",
       "file": "coordination_api.py",
-      "line": 2189,
+      "line": 2218,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -405,7 +405,7 @@
       "message": "Entrypoint 'eject_from_train_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.eject_from_train_endpoint",
       "file": "coordination_api.py",
-      "line": 2243,
+      "line": 2270,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -414,7 +414,7 @@
       "message": "Entrypoint 'get_train_status_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.get_train_status_endpoint",
       "file": "coordination_api.py",
-      "line": 2292,
+      "line": 2319,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -423,7 +423,7 @@
       "message": "Entrypoint 'report_spec_result_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.report_spec_result_endpoint",
       "file": "coordination_api.py",
-      "line": 2322,
+      "line": 2349,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -432,7 +432,7 @@
       "message": "Entrypoint 'affected_tests_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.affected_tests_endpoint",
       "file": "coordination_api.py",
-      "line": 2361,
+      "line": 2388,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -441,7 +441,7 @@
       "message": "Entrypoint 'merge_train_metrics_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.merge_train_metrics_endpoint",
       "file": "coordination_api.py",
-      "line": 2384,
+      "line": 2411,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -450,7 +450,7 @@
       "message": "Entrypoint 'resolve_archetype_for_phase_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.resolve_archetype_for_phase_endpoint",
       "file": "coordination_api.py",
-      "line": 2420,
+      "line": 2438,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -459,7 +459,7 @@
       "message": "Entrypoint 'report_status' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.report_status",
       "file": "coordination_api.py",
-      "line": 2527,
+      "line": 2546,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -468,7 +468,7 @@
       "message": "Entrypoint 'test_notification' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.test_notification",
       "file": "coordination_api.py",
-      "line": 2620,
+      "line": 2639,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -477,7 +477,7 @@
       "message": "Entrypoint 'notifications_status' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.notifications_status",
       "file": "coordination_api.py",
-      "line": 2657,
+      "line": 2676,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -486,7 +486,7 @@
       "message": "Entrypoint 'discovery_register' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.discovery_register",
       "file": "coordination_api.py",
-      "line": 2674,
+      "line": 2693,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -495,7 +495,7 @@
       "message": "Entrypoint 'discovery_agents' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.discovery_agents",
       "file": "coordination_api.py",
-      "line": 2705,
+      "line": 2722,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -504,7 +504,7 @@
       "message": "Entrypoint 'discovery_heartbeat' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.discovery_heartbeat",
       "file": "coordination_api.py",
-      "line": 2739,
+      "line": 2754,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -513,7 +513,7 @@
       "message": "Entrypoint 'discovery_cleanup' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.discovery_cleanup",
       "file": "coordination_api.py",
-      "line": 2766,
+      "line": 2779,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -522,7 +522,7 @@
       "message": "Entrypoint 'gen_eval_list_scenarios' has no downstream dependencies",
       "node_id": "py:coordination_api.create_coordination_api.gen_eval_list_scenarios",
       "file": "coordination_api.py",
-      "line": 2803,
+      "line": 2816,
       "suggestion": "Add downstream calls or tag this entrypoint as 'pure' if it has no side effects"
     },
     {
@@ -531,7 +531,7 @@
       "message": "Entrypoint 'gen_eval_validate' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.gen_eval_validate",
       "file": "coordination_api.py",
-      "line": 2831,
+      "line": 2844,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -540,7 +540,7 @@
       "message": "Entrypoint 'gen_eval_create' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.gen_eval_create",
       "file": "coordination_api.py",
-      "line": 2855,
+      "line": 2868,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -549,7 +549,7 @@
       "message": "Entrypoint 'gen_eval_run' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.gen_eval_run",
       "file": "coordination_api.py",
-      "line": 2880,
+      "line": 2893,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -558,7 +558,7 @@
       "message": "Entrypoint 'search_issues' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.search_issues",
       "file": "coordination_api.py",
-      "line": 2910,
+      "line": 2923,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -567,7 +567,7 @@
       "message": "Entrypoint 'ready_issues' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.ready_issues",
       "file": "coordination_api.py",
-      "line": 2926,
+      "line": 2939,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -576,7 +576,7 @@
       "message": "Entrypoint 'request_permission_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.request_permission_endpoint",
       "file": "coordination_api.py",
-      "line": 2952,
+      "line": 2965,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -585,7 +585,7 @@
       "message": "Entrypoint 'request_approval_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.request_approval_endpoint",
       "file": "coordination_api.py",
-      "line": 2991,
+      "line": 3002,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -594,7 +594,7 @@
       "message": "Entrypoint 'check_approval_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.check_approval_endpoint",
       "file": "coordination_api.py",
-      "line": 3030,
+      "line": 3037,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -603,7 +603,7 @@
       "message": "Entrypoint 'help_overview' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.help_overview",
       "file": "coordination_api.py",
-      "line": 3089,
+      "line": 3096,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -612,7 +612,7 @@
       "message": "Entrypoint 'help_topic' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.help_topic",
       "file": "coordination_api.py",
-      "line": 3099,
+      "line": 3106,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -621,7 +621,7 @@
       "message": "Entrypoint 'get_sync_points_status' has no downstream dependencies",
       "node_id": "py:coordination_api.create_coordination_api.get_sync_points_status",
       "file": "coordination_api.py",
-      "line": 3126,
+      "line": 3133,
       "suggestion": "Add downstream calls or tag this entrypoint as 'pure' if it has no side effects"
     },
     {
@@ -630,7 +630,7 @@
       "message": "Entrypoint 'get_active_worktrees' has no downstream dependencies",
       "node_id": "py:coordination_api.create_coordination_api.get_active_worktrees",
       "file": "coordination_api.py",
-      "line": 3139,
+      "line": 3146,
       "suggestion": "Add downstream calls or tag this entrypoint as 'pure' if it has no side effects"
     },
     {
@@ -639,7 +639,7 @@
       "message": "Entrypoint 'mint_events_token' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.mint_events_token",
       "file": "coordination_api.py",
-      "line": 3151,
+      "line": 3158,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -648,7 +648,7 @@
       "message": "Entrypoint 'stream_work_events' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.stream_work_events",
       "file": "coordination_api.py",
-      "line": 3184,
+      "line": 3191,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -657,7 +657,7 @@
       "message": "Entrypoint 'patch_issue_labels' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.patch_issue_labels",
       "file": "coordination_api.py",
-      "line": 3235,
+      "line": 3240,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -666,7 +666,7 @@
       "message": "Entrypoint 'force_release_lock' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.force_release_lock",
       "file": "coordination_api.py",
-      "line": 3287,
+      "line": 3295,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -675,7 +675,7 @@
       "message": "Entrypoint 'kick_agent' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.kick_agent",
       "file": "coordination_api.py",
-      "line": 3324,
+      "line": 3332,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -684,7 +684,7 @@
       "message": "Entrypoint 'put_saved_view' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.put_saved_view",
       "file": "coordination_api.py",
-      "line": 3445,
+      "line": 3455,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -693,7 +693,7 @@
       "message": "Entrypoint 'post_kanban_audit' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.post_kanban_audit",
       "file": "coordination_api.py",
-      "line": 3482,
+      "line": 3492,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -702,7 +702,7 @@
       "message": "Entrypoint 'live' has no downstream dependencies",
       "node_id": "py:coordination_api.create_coordination_api.live",
       "file": "coordination_api.py",
-      "line": 3518,
+      "line": 3528,
       "suggestion": "Add downstream calls or tag this entrypoint as 'pure' if it has no side effects"
     },
     {
@@ -711,7 +711,7 @@
       "message": "Entrypoint 'ready' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.ready",
       "file": "coordination_api.py",
-      "line": 3523,
+      "line": 3533,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -720,7 +720,7 @@
       "message": "Entrypoint 'health' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.health",
       "file": "coordination_api.py",
-      "line": 3535,
+      "line": 3545,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -729,7 +729,7 @@
       "message": "Entrypoint 'github_prs' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.github_prs",
       "file": "coordination_api.py",
-      "line": 3546,
+      "line": 3556,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -738,7 +738,7 @@
       "message": "Entrypoint 'openspec_proposals' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.openspec_proposals",
       "file": "coordination_api.py",
-      "line": 3586,
+      "line": 3596,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -747,7 +747,7 @@
       "message": "Entrypoint 'code_search_status_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.code_search_status_endpoint",
       "file": "coordination_api.py",
-      "line": 3632,
+      "line": 3641,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -756,7 +756,7 @@
       "message": "Entrypoint 'search_code_endpoint' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_api.create_coordination_api.search_code_endpoint",
       "file": "coordination_api.py",
-      "line": 3669,
+      "line": 3678,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -765,7 +765,7 @@
       "message": "Entrypoint 'get_current_locks' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_mcp.get_current_locks",
       "file": "coordination_mcp.py",
-      "line": 2614,
+      "line": 2620,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -774,7 +774,7 @@
       "message": "Entrypoint 'get_recent_handoffs' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_mcp.get_recent_handoffs",
       "file": "coordination_mcp.py",
-      "line": 2640,
+      "line": 2646,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -783,7 +783,7 @@
       "message": "Entrypoint 'get_pending_work' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_mcp.get_pending_work",
       "file": "coordination_mcp.py",
-      "line": 2687,
+      "line": 2693,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -792,7 +792,7 @@
       "message": "Entrypoint 'get_recent_memories' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_mcp.get_recent_memories",
       "file": "coordination_mcp.py",
-      "line": 2719,
+      "line": 2725,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -801,7 +801,7 @@
       "message": "Entrypoint 'get_guardrail_patterns' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_mcp.get_guardrail_patterns",
       "file": "coordination_mcp.py",
-      "line": 2748,
+      "line": 2754,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -810,7 +810,7 @@
       "message": "Entrypoint 'get_current_profile' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_mcp.get_current_profile",
       "file": "coordination_mcp.py",
-      "line": 2778,
+      "line": 2784,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -819,7 +819,7 @@
       "message": "Entrypoint 'get_recent_audit' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_mcp.get_recent_audit",
       "file": "coordination_mcp.py",
-      "line": 2814,
+      "line": 2820,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -828,7 +828,7 @@
       "message": "Entrypoint 'get_active_features_resource' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_mcp.get_active_features_resource",
       "file": "coordination_mcp.py",
-      "line": 2843,
+      "line": 2849,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -837,7 +837,7 @@
       "message": "Entrypoint 'get_merge_queue_resource' has downstream dependencies but none touch a DB or produce side effects",
       "node_id": "py:coordination_mcp.get_merge_queue_resource",
       "file": "coordination_mcp.py",
-      "line": 2875,
+      "line": 2881,
       "suggestion": "Verify this is expected, or tag the entrypoint as 'pure'"
     },
     {
@@ -846,7 +846,7 @@
       "message": "Entrypoint 'get_gen_eval_coverage' has no downstream dependencies",
       "node_id": "py:coordination_mcp.get_gen_eval_coverage",
       "file": "coordination_mcp.py",
-      "line": 3081,
+      "line": 3087,
       "suggestion": "Add downstream calls or tag this entrypoint as 'pure' if it has no side effects"
     },
     {
@@ -855,7 +855,7 @@
       "message": "Entrypoint 'get_gen_eval_report' has no downstream dependencies",
       "node_id": "py:coordination_mcp.get_gen_eval_report",
       "file": "coordination_mcp.py",
-      "line": 3113,
+      "line": 3119,
       "suggestion": "Add downstream calls or tag this entrypoint as 'pure' if it has no side effects"
     },
     {
@@ -864,7 +864,7 @@
       "message": "Entrypoint 'coordinate_file_edit' has no downstream dependencies",
       "node_id": "py:coordination_mcp.coordinate_file_edit",
       "file": "coordination_mcp.py",
-      "line": 3160,
+      "line": 3166,
       "suggestion": "Add downstream calls or tag this entrypoint as 'pure' if it has no side effects"
     },
     {
@@ -873,7 +873,7 @@
       "message": "Entrypoint 'start_work_session' has no downstream dependencies",
       "node_id": "py:coordination_mcp.start_work_session",
       "file": "coordination_mcp.py",
-      "line": 3182,
+      "line": 3188,
       "suggestion": "Add downstream calls or tag this entrypoint as 'pure' if it has no side effects"
     },
     {
@@ -882,7 +882,7 @@
       "message": "Backend route 'acquire_lock' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.acquire_lock",
       "file": "coordination_api.py",
-      "line": 950,
+      "line": 971,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -891,7 +891,7 @@
       "message": "Backend route 'release_lock' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.release_lock",
       "file": "coordination_api.py",
-      "line": 987,
+      "line": 1006,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -900,7 +900,7 @@
       "message": "Backend route 'check_lock_status' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.check_lock_status",
       "file": "coordination_api.py",
-      "line": 1016,
+      "line": 1033,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -909,7 +909,7 @@
       "message": "Backend route 'store_memory' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.store_memory",
       "file": "coordination_api.py",
-      "line": 1042,
+      "line": 1059,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -918,7 +918,7 @@
       "message": "Backend route 'query_memories' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.query_memories",
       "file": "coordination_api.py",
-      "line": 1074,
+      "line": 1091,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -927,7 +927,7 @@
       "message": "Backend route 'claim_work' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.claim_work",
       "file": "coordination_api.py",
-      "line": 1119,
+      "line": 1134,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -936,7 +936,7 @@
       "message": "Backend route 'complete_work' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.complete_work",
       "file": "coordination_api.py",
-      "line": 1153,
+      "line": 1166,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -945,7 +945,7 @@
       "message": "Backend route 'submit_work' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.submit_work",
       "file": "coordination_api.py",
-      "line": 1185,
+      "line": 1198,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -954,7 +954,7 @@
       "message": "Backend route 'reconcile_work_projection' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.reconcile_work_projection",
       "file": "coordination_api.py",
-      "line": 1220,
+      "line": 1250,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -963,7 +963,7 @@
       "message": "Backend route 'get_task_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.get_task_endpoint",
       "file": "coordination_api.py",
-      "line": 1248,
+      "line": 1283,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -972,7 +972,7 @@
       "message": "Backend route 'create_issue' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.create_issue",
       "file": "coordination_api.py",
-      "line": 1295,
+      "line": 1330,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -981,7 +981,7 @@
       "message": "Backend route 'list_issues' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.list_issues",
       "file": "coordination_api.py",
-      "line": 1329,
+      "line": 1364,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -990,7 +990,7 @@
       "message": "Backend route 'blocked_issues_early' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.blocked_issues_early",
       "file": "coordination_api.py",
-      "line": 1356,
+      "line": 1391,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -999,7 +999,7 @@
       "message": "Backend route 'show_issue' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.show_issue",
       "file": "coordination_api.py",
-      "line": 1373,
+      "line": 1408,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1008,7 +1008,7 @@
       "message": "Backend route 'update_issue' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.update_issue",
       "file": "coordination_api.py",
-      "line": 1390,
+      "line": 1425,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1017,7 +1017,7 @@
       "message": "Backend route 'close_issue' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.close_issue",
       "file": "coordination_api.py",
-      "line": 1422,
+      "line": 1459,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1026,7 +1026,7 @@
       "message": "Backend route 'comment_issue' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.comment_issue",
       "file": "coordination_api.py",
-      "line": 1454,
+      "line": 1493,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1035,7 +1035,7 @@
       "message": "Backend route 'check_guardrails' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.check_guardrails",
       "file": "coordination_api.py",
-      "line": 1476,
+      "line": 1515,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1044,7 +1044,7 @@
       "message": "Backend route 'get_my_profile' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.get_my_profile",
       "file": "coordination_api.py",
-      "line": 1522,
+      "line": 1561,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1053,7 +1053,7 @@
       "message": "Backend route 'get_agent_dispatch_configs' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.get_agent_dispatch_configs",
       "file": "coordination_api.py",
-      "line": 1552,
+      "line": 1591,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1062,7 +1062,7 @@
       "message": "Backend route 'query_audit' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.query_audit",
       "file": "coordination_api.py",
-      "line": 1566,
+      "line": 1605,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1071,7 +1071,7 @@
       "message": "Backend route 'write_handoff' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.write_handoff",
       "file": "coordination_api.py",
-      "line": 1626,
+      "line": 1665,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1080,7 +1080,7 @@
       "message": "Backend route 'read_handoff' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.read_handoff",
       "file": "coordination_api.py",
-      "line": 1658,
+      "line": 1695,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1089,7 +1089,7 @@
       "message": "Backend route 'check_policy' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.check_policy",
       "file": "coordination_api.py",
-      "line": 1701,
+      "line": 1736,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1098,7 +1098,7 @@
       "message": "Backend route 'validate_cedar_policy' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.validate_cedar_policy",
       "file": "coordination_api.py",
-      "line": 1728,
+      "line": 1761,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1107,7 +1107,7 @@
       "message": "Backend route 'allocate_ports' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.allocate_ports",
       "file": "coordination_api.py",
-      "line": 1759,
+      "line": 1792,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1116,7 +1116,7 @@
       "message": "Backend route 'release_ports' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.release_ports",
       "file": "coordination_api.py",
-      "line": 1781,
+      "line": 1814,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1125,7 +1125,7 @@
       "message": "Backend route 'port_status' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.port_status",
       "file": "coordination_api.py",
-      "line": 1790,
+      "line": 1823,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1134,7 +1134,7 @@
       "message": "Backend route 'list_pending_approvals' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.list_pending_approvals",
       "file": "coordination_api.py",
-      "line": 1830,
+      "line": 1861,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1143,7 +1143,7 @@
       "message": "Backend route 'decide_approval' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.decide_approval",
       "file": "coordination_api.py",
-      "line": 1841,
+      "line": 1872,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1152,7 +1152,7 @@
       "message": "Backend route 'list_policy_versions_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.list_policy_versions_endpoint",
       "file": "coordination_api.py",
-      "line": 1868,
+      "line": 1899,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1161,7 +1161,7 @@
       "message": "Backend route 'rollback_policy_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.rollback_policy_endpoint",
       "file": "coordination_api.py",
-      "line": 1881,
+      "line": 1912,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1170,7 +1170,7 @@
       "message": "Backend route 'register_feature_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.register_feature_endpoint",
       "file": "coordination_api.py",
-      "line": 1900,
+      "line": 1931,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1179,7 +1179,7 @@
       "message": "Backend route 'deregister_feature_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.deregister_feature_endpoint",
       "file": "coordination_api.py",
-      "line": 1934,
+      "line": 1963,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1188,7 +1188,7 @@
       "message": "Backend route 'get_feature_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.get_feature_endpoint",
       "file": "coordination_api.py",
-      "line": 1961,
+      "line": 1990,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1197,7 +1197,7 @@
       "message": "Backend route 'list_active_features_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.list_active_features_endpoint",
       "file": "coordination_api.py",
-      "line": 1985,
+      "line": 2014,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1206,7 +1206,7 @@
       "message": "Backend route 'analyze_feature_conflicts_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.analyze_feature_conflicts_endpoint",
       "file": "coordination_api.py",
-      "line": 2015,
+      "line": 2044,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1215,7 +1215,7 @@
       "message": "Backend route 'enqueue_merge_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.enqueue_merge_endpoint",
       "file": "coordination_api.py",
-      "line": 2039,
+      "line": 2068,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1224,7 +1224,7 @@
       "message": "Backend route 'get_merge_queue_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.get_merge_queue_endpoint",
       "file": "coordination_api.py",
-      "line": 2072,
+      "line": 2101,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1233,7 +1233,7 @@
       "message": "Backend route 'get_next_merge_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.get_next_merge_endpoint",
       "file": "coordination_api.py",
-      "line": 2101,
+      "line": 2130,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1242,7 +1242,7 @@
       "message": "Backend route 'run_pre_merge_checks_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.run_pre_merge_checks_endpoint",
       "file": "coordination_api.py",
-      "line": 2122,
+      "line": 2151,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1251,7 +1251,7 @@
       "message": "Backend route 'mark_merged_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.mark_merged_endpoint",
       "file": "coordination_api.py",
-      "line": 2147,
+      "line": 2176,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1260,7 +1260,7 @@
       "message": "Backend route 'remove_from_merge_queue_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.remove_from_merge_queue_endpoint",
       "file": "coordination_api.py",
-      "line": 2166,
+      "line": 2195,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1269,7 +1269,7 @@
       "message": "Backend route 'compose_train_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.compose_train_endpoint",
       "file": "coordination_api.py",
-      "line": 2189,
+      "line": 2218,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1278,7 +1278,7 @@
       "message": "Backend route 'eject_from_train_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.eject_from_train_endpoint",
       "file": "coordination_api.py",
-      "line": 2243,
+      "line": 2270,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1287,7 +1287,7 @@
       "message": "Backend route 'get_train_status_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.get_train_status_endpoint",
       "file": "coordination_api.py",
-      "line": 2292,
+      "line": 2319,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1296,7 +1296,7 @@
       "message": "Backend route 'report_spec_result_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.report_spec_result_endpoint",
       "file": "coordination_api.py",
-      "line": 2322,
+      "line": 2349,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1305,7 +1305,7 @@
       "message": "Backend route 'affected_tests_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.affected_tests_endpoint",
       "file": "coordination_api.py",
-      "line": 2361,
+      "line": 2388,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1314,7 +1314,7 @@
       "message": "Backend route 'merge_train_metrics_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.merge_train_metrics_endpoint",
       "file": "coordination_api.py",
-      "line": 2384,
+      "line": 2411,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1323,7 +1323,7 @@
       "message": "Backend route 'resolve_archetype_for_phase_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.resolve_archetype_for_phase_endpoint",
       "file": "coordination_api.py",
-      "line": 2420,
+      "line": 2438,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1332,7 +1332,7 @@
       "message": "Backend route 'report_status' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.report_status",
       "file": "coordination_api.py",
-      "line": 2527,
+      "line": 2546,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1341,7 +1341,7 @@
       "message": "Backend route 'test_notification' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.test_notification",
       "file": "coordination_api.py",
-      "line": 2620,
+      "line": 2639,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1350,7 +1350,7 @@
       "message": "Backend route 'notifications_status' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.notifications_status",
       "file": "coordination_api.py",
-      "line": 2657,
+      "line": 2676,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1359,7 +1359,7 @@
       "message": "Backend route 'discovery_register' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.discovery_register",
       "file": "coordination_api.py",
-      "line": 2674,
+      "line": 2693,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1368,7 +1368,7 @@
       "message": "Backend route 'discovery_agents' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.discovery_agents",
       "file": "coordination_api.py",
-      "line": 2705,
+      "line": 2722,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1377,7 +1377,7 @@
       "message": "Backend route 'discovery_heartbeat' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.discovery_heartbeat",
       "file": "coordination_api.py",
-      "line": 2739,
+      "line": 2754,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1386,7 +1386,7 @@
       "message": "Backend route 'discovery_cleanup' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.discovery_cleanup",
       "file": "coordination_api.py",
-      "line": 2766,
+      "line": 2779,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1395,7 +1395,7 @@
       "message": "Backend route 'gen_eval_list_scenarios' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.gen_eval_list_scenarios",
       "file": "coordination_api.py",
-      "line": 2803,
+      "line": 2816,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1404,7 +1404,7 @@
       "message": "Backend route 'gen_eval_validate' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.gen_eval_validate",
       "file": "coordination_api.py",
-      "line": 2831,
+      "line": 2844,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1413,7 +1413,7 @@
       "message": "Backend route 'gen_eval_create' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.gen_eval_create",
       "file": "coordination_api.py",
-      "line": 2855,
+      "line": 2868,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1422,7 +1422,7 @@
       "message": "Backend route 'gen_eval_run' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.gen_eval_run",
       "file": "coordination_api.py",
-      "line": 2880,
+      "line": 2893,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1431,7 +1431,7 @@
       "message": "Backend route 'search_issues' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.search_issues",
       "file": "coordination_api.py",
-      "line": 2910,
+      "line": 2923,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1440,7 +1440,7 @@
       "message": "Backend route 'ready_issues' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.ready_issues",
       "file": "coordination_api.py",
-      "line": 2926,
+      "line": 2939,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1449,7 +1449,7 @@
       "message": "Backend route 'request_permission_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.request_permission_endpoint",
       "file": "coordination_api.py",
-      "line": 2952,
+      "line": 2965,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1458,7 +1458,7 @@
       "message": "Backend route 'request_approval_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.request_approval_endpoint",
       "file": "coordination_api.py",
-      "line": 2991,
+      "line": 3002,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1467,7 +1467,7 @@
       "message": "Backend route 'check_approval_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.check_approval_endpoint",
       "file": "coordination_api.py",
-      "line": 3030,
+      "line": 3037,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1476,7 +1476,7 @@
       "message": "Backend route 'help_overview' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.help_overview",
       "file": "coordination_api.py",
-      "line": 3089,
+      "line": 3096,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1485,7 +1485,7 @@
       "message": "Backend route 'help_topic' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.help_topic",
       "file": "coordination_api.py",
-      "line": 3099,
+      "line": 3106,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1494,7 +1494,7 @@
       "message": "Backend route 'get_sync_points_status' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.get_sync_points_status",
       "file": "coordination_api.py",
-      "line": 3126,
+      "line": 3133,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1503,7 +1503,7 @@
       "message": "Backend route 'get_active_worktrees' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.get_active_worktrees",
       "file": "coordination_api.py",
-      "line": 3139,
+      "line": 3146,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1512,7 +1512,7 @@
       "message": "Backend route 'mint_events_token' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.mint_events_token",
       "file": "coordination_api.py",
-      "line": 3151,
+      "line": 3158,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1521,7 +1521,7 @@
       "message": "Backend route 'stream_work_events' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.stream_work_events",
       "file": "coordination_api.py",
-      "line": 3184,
+      "line": 3191,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1530,7 +1530,7 @@
       "message": "Backend route 'patch_issue_labels' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.patch_issue_labels",
       "file": "coordination_api.py",
-      "line": 3235,
+      "line": 3240,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1539,7 +1539,7 @@
       "message": "Backend route 'force_release_lock' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.force_release_lock",
       "file": "coordination_api.py",
-      "line": 3287,
+      "line": 3295,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1548,7 +1548,7 @@
       "message": "Backend route 'kick_agent' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.kick_agent",
       "file": "coordination_api.py",
-      "line": 3324,
+      "line": 3332,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1557,7 +1557,7 @@
       "message": "Backend route 'put_saved_view' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.put_saved_view",
       "file": "coordination_api.py",
-      "line": 3445,
+      "line": 3455,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1566,7 +1566,7 @@
       "message": "Backend route 'post_kanban_audit' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.post_kanban_audit",
       "file": "coordination_api.py",
-      "line": 3482,
+      "line": 3492,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1575,7 +1575,7 @@
       "message": "Backend route 'live' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.live",
       "file": "coordination_api.py",
-      "line": 3518,
+      "line": 3528,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1584,7 +1584,7 @@
       "message": "Backend route 'ready' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.ready",
       "file": "coordination_api.py",
-      "line": 3523,
+      "line": 3533,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1593,7 +1593,7 @@
       "message": "Backend route 'health' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.health",
       "file": "coordination_api.py",
-      "line": 3535,
+      "line": 3545,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1602,7 +1602,7 @@
       "message": "Backend route 'github_prs' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.github_prs",
       "file": "coordination_api.py",
-      "line": 3546,
+      "line": 3556,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1611,7 +1611,7 @@
       "message": "Backend route 'openspec_proposals' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.openspec_proposals",
       "file": "coordination_api.py",
-      "line": 3586,
+      "line": 3596,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1620,7 +1620,7 @@
       "message": "Backend route 'code_search_status_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.code_search_status_endpoint",
       "file": "coordination_api.py",
-      "line": 3632,
+      "line": 3641,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1629,7 +1629,7 @@
       "message": "Backend route 'search_code_endpoint' has no frontend callers",
       "node_id": "py:coordination_api.create_coordination_api.search_code_endpoint",
       "file": "coordination_api.py",
-      "line": 3669,
+      "line": 3678,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1638,7 +1638,7 @@
       "message": "Backend route 'get_current_locks' has no frontend callers",
       "node_id": "py:coordination_mcp.get_current_locks",
       "file": "coordination_mcp.py",
-      "line": 2614,
+      "line": 2620,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1647,7 +1647,7 @@
       "message": "Backend route 'get_recent_handoffs' has no frontend callers",
       "node_id": "py:coordination_mcp.get_recent_handoffs",
       "file": "coordination_mcp.py",
-      "line": 2640,
+      "line": 2646,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1656,7 +1656,7 @@
       "message": "Backend route 'get_pending_work' has no frontend callers",
       "node_id": "py:coordination_mcp.get_pending_work",
       "file": "coordination_mcp.py",
-      "line": 2687,
+      "line": 2693,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1665,7 +1665,7 @@
       "message": "Backend route 'get_recent_memories' has no frontend callers",
       "node_id": "py:coordination_mcp.get_recent_memories",
       "file": "coordination_mcp.py",
-      "line": 2719,
+      "line": 2725,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1674,7 +1674,7 @@
       "message": "Backend route 'get_guardrail_patterns' has no frontend callers",
       "node_id": "py:coordination_mcp.get_guardrail_patterns",
       "file": "coordination_mcp.py",
-      "line": 2748,
+      "line": 2754,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1683,7 +1683,7 @@
       "message": "Backend route 'get_current_profile' has no frontend callers",
       "node_id": "py:coordination_mcp.get_current_profile",
       "file": "coordination_mcp.py",
-      "line": 2778,
+      "line": 2784,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1692,7 +1692,7 @@
       "message": "Backend route 'get_recent_audit' has no frontend callers",
       "node_id": "py:coordination_mcp.get_recent_audit",
       "file": "coordination_mcp.py",
-      "line": 2814,
+      "line": 2820,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1701,7 +1701,7 @@
       "message": "Backend route 'get_active_features_resource' has no frontend callers",
       "node_id": "py:coordination_mcp.get_active_features_resource",
       "file": "coordination_mcp.py",
-      "line": 2843,
+      "line": 2849,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1710,7 +1710,7 @@
       "message": "Backend route 'get_merge_queue_resource' has no frontend callers",
       "node_id": "py:coordination_mcp.get_merge_queue_resource",
       "file": "coordination_mcp.py",
-      "line": 2875,
+      "line": 2881,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1719,7 +1719,7 @@
       "message": "Backend route 'get_gen_eval_coverage' has no frontend callers",
       "node_id": "py:coordination_mcp.get_gen_eval_coverage",
       "file": "coordination_mcp.py",
-      "line": 3081,
+      "line": 3087,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1728,7 +1728,7 @@
       "message": "Backend route 'get_gen_eval_report' has no frontend callers",
       "node_id": "py:coordination_mcp.get_gen_eval_report",
       "file": "coordination_mcp.py",
-      "line": 3113,
+      "line": 3119,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1737,7 +1737,7 @@
       "message": "Backend route 'coordinate_file_edit' has no frontend callers",
       "node_id": "py:coordination_mcp.coordinate_file_edit",
       "file": "coordination_mcp.py",
-      "line": 3160,
+      "line": 3166,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1746,7 +1746,7 @@
       "message": "Backend route 'start_work_session' has no frontend callers",
       "node_id": "py:coordination_mcp.start_work_session",
       "file": "coordination_mcp.py",
-      "line": 3182,
+      "line": 3188,
       "suggestion": "Add a frontend caller or remove the unused route"
     },
     {
@@ -1971,7 +1971,7 @@
       "message": "Function 'ProfileSyncError' has no corresponding test references",
       "node_id": "py:agents_config.ProfileSyncError",
       "file": "agents_config.py",
-      "line": 1091,
+      "line": 1092,
       "suggestion": "Add tests that reference 'ProfileSyncError' (e.g., test_ProfileSyncError or import it in a test file)"
     },
     {
@@ -1980,7 +1980,7 @@
       "message": "Function 'ProfileSyncResult' has no corresponding test references",
       "node_id": "py:agents_config.ProfileSyncResult",
       "file": "agents_config.py",
-      "line": 1101,
+      "line": 1102,
       "suggestion": "Add tests that reference 'ProfileSyncResult' (e.g., test_ProfileSyncResult or import it in a test file)"
     },
     {
@@ -1989,7 +1989,7 @@
       "message": "Function 'mutations' has no corresponding test references",
       "node_id": "py:agents_config.ProfileSyncResult.mutations",
       "file": "agents_config.py",
-      "line": 1118,
+      "line": 1119,
       "suggestion": "Add tests that reference 'mutations' (e.g., test_mutations or import it in a test file)"
     },
     {
@@ -1998,7 +1998,7 @@
       "message": "Function 'derive_allowed_operations' has no corresponding test references",
       "node_id": "py:agents_config.derive_allowed_operations",
       "file": "agents_config.py",
-      "line": 1130,
+      "line": 1131,
       "suggestion": "Add tests that reference 'derive_allowed_operations' (e.g., test_derive_allowed_operations or import it in a test file)"
     },
     {
@@ -2007,7 +2007,7 @@
       "message": "Function '_is_unique_violation' has no corresponding test references",
       "node_id": "py:agents_config._is_unique_violation",
       "file": "agents_config.py",
-      "line": 1171,
+      "line": 1172,
       "suggestion": "Add tests that reference '_is_unique_violation' (e.g., test__is_unique_violation or import it in a test file)"
     },
     {
@@ -2016,7 +2016,7 @@
       "message": "Function '_registry_sync_timestamp' has no corresponding test references",
       "node_id": "py:agents_config._registry_sync_timestamp",
       "file": "agents_config.py",
-      "line": 1190,
+      "line": 1191,
       "suggestion": "Add tests that reference '_registry_sync_timestamp' (e.g., test__registry_sync_timestamp or import it in a test file)"
     },
     {
@@ -2025,7 +2025,7 @@
       "message": "Function '_desired_profile_row' has no corresponding test references",
       "node_id": "py:agents_config._desired_profile_row",
       "file": "agents_config.py",
-      "line": 1206,
+      "line": 1207,
       "suggestion": "Add tests that reference '_desired_profile_row' (e.g., test__desired_profile_row or import it in a test file)"
     },
     {
@@ -2034,7 +2034,7 @@
       "message": "Function '_profile_drift' has no corresponding test references",
       "node_id": "py:agents_config._profile_drift",
       "file": "agents_config.py",
-      "line": 1219,
+      "line": 1220,
       "suggestion": "Add tests that reference '_profile_drift' (e.g., test__profile_drift or import it in a test file)"
     },
     {
@@ -2043,7 +2043,7 @@
       "message": "Function '_emit_sync_audit' has no corresponding test references",
       "node_id": "py:agents_config._emit_sync_audit",
       "file": "agents_config.py",
-      "line": 1237,
+      "line": 1238,
       "suggestion": "Add tests that reference '_emit_sync_audit' (e.g., test__emit_sync_audit or import it in a test file)"
     },
     {
@@ -2052,7 +2052,7 @@
       "message": "Function '_sync_assignments' has no corresponding test references",
       "node_id": "py:agents_config._sync_assignments",
       "file": "agents_config.py",
-      "line": 1282,
+      "line": 1283,
       "suggestion": "Add tests that reference '_sync_assignments' (e.g., test__sync_assignments or import it in a test file)"
     },
     {
@@ -2061,7 +2061,7 @@
       "message": "Function 'sync_profiles' has no corresponding test references",
       "node_id": "py:agents_config.sync_profiles",
       "file": "agents_config.py",
-      "line": 1468,
+      "line": 1469,
       "suggestion": "Add tests that reference 'sync_profiles' (e.g., test_sync_profiles or import it in a test file)"
     },
     {
@@ -2070,7 +2070,7 @@
       "message": "Function 'get_mcp_env' has no corresponding test references",
       "node_id": "py:agents_config.get_mcp_env",
       "file": "agents_config.py",
-      "line": 1701,
+      "line": 1702,
       "suggestion": "Add tests that reference 'get_mcp_env' (e.g., test_get_mcp_env or import it in a test file)"
     },
     {
@@ -2079,7 +2079,7 @@
       "message": "Function 'get_agents_config' has no corresponding test references",
       "node_id": "py:agents_config.get_agents_config",
       "file": "agents_config.py",
-      "line": 1739,
+      "line": 1740,
       "suggestion": "Add tests that reference 'get_agents_config' (e.g., test_get_agents_config or import it in a test file)"
     },
     {
@@ -2088,7 +2088,7 @@
       "message": "Function 'get_agent_config' has no corresponding test references",
       "node_id": "py:agents_config.get_agent_config",
       "file": "agents_config.py",
-      "line": 1755,
+      "line": 1756,
       "suggestion": "Add tests that reference 'get_agent_config' (e.g., test_get_agent_config or import it in a test file)"
     },
     {
@@ -2097,7 +2097,7 @@
       "message": "Function 'reset_agents_config' has no corresponding test references",
       "node_id": "py:agents_config.reset_agents_config",
       "file": "agents_config.py",
-      "line": 1763,
+      "line": 1764,
       "suggestion": "Add tests that reference 'reset_agents_config' (e.g., test_reset_agents_config or import it in a test file)"
     },
     {
@@ -2106,7 +2106,7 @@
       "message": "Function 'get_dispatch_configs' has no corresponding test references",
       "node_id": "py:agents_config.get_dispatch_configs",
       "file": "agents_config.py",
-      "line": 1773,
+      "line": 1774,
       "suggestion": "Add tests that reference 'get_dispatch_configs' (e.g., test_get_dispatch_configs or import it in a test file)"
     },
     {
@@ -2115,7 +2115,7 @@
       "message": "Function 'get_agent_isolation' has no corresponding test references",
       "node_id": "py:agents_config.get_agent_isolation",
       "file": "agents_config.py",
-      "line": 1841,
+      "line": 1842,
       "suggestion": "Add tests that reference 'get_agent_isolation' (e.g., test_get_agent_isolation or import it in a test file)"
     },
     {
@@ -2124,7 +2124,7 @@
       "message": "Function '_default_archetypes_path' has no corresponding test references",
       "node_id": "py:agents_config._default_archetypes_path",
       "file": "agents_config.py",
-      "line": 1857,
+      "line": 1858,
       "suggestion": "Add tests that reference '_default_archetypes_path' (e.g., test__default_archetypes_path or import it in a test file)"
     },
     {
@@ -2133,7 +2133,7 @@
       "message": "Function '_as_positive_number' has no corresponding test references",
       "node_id": "py:agents_config._as_positive_number",
       "file": "agents_config.py",
-      "line": 1861,
+      "line": 1862,
       "suggestion": "Add tests that reference '_as_positive_number' (e.g., test__as_positive_number or import it in a test file)"
     },
     {
@@ -2142,7 +2142,7 @@
       "message": "Function '_validate_local_roster' has no corresponding test references",
       "node_id": "py:agents_config._validate_local_roster",
       "file": "agents_config.py",
-      "line": 1868,
+      "line": 1869,
       "suggestion": "Add tests that reference '_validate_local_roster' (e.g., test__validate_local_roster or import it in a test file)"
     },
     {
@@ -2151,7 +2151,7 @@
       "message": "Function 'load_archetypes_config' has no corresponding test references",
       "node_id": "py:agents_config.load_archetypes_config",
       "file": "agents_config.py",
-      "line": 1990,
+      "line": 1991,
       "suggestion": "Add tests that reference 'load_archetypes_config' (e.g., test_load_archetypes_config or import it in a test file)"
     },
     {
@@ -2160,7 +2160,7 @@
       "message": "Function 'get_archetype' has no corresponding test references",
       "node_id": "py:agents_config.get_archetype",
       "file": "agents_config.py",
-      "line": 2088,
+      "line": 2089,
       "suggestion": "Add tests that reference 'get_archetype' (e.g., test_get_archetype or import it in a test file)"
     },
     {
@@ -2169,7 +2169,7 @@
       "message": "Function 'get_phase_mapping' has no corresponding test references",
       "node_id": "py:agents_config.get_phase_mapping",
       "file": "agents_config.py",
-      "line": 2102,
+      "line": 2103,
       "suggestion": "Add tests that reference 'get_phase_mapping' (e.g., test_get_phase_mapping or import it in a test file)"
     },
     {
@@ -2178,7 +2178,7 @@
       "message": "Function 'reset_archetypes_config' has no corresponding test references",
       "node_id": "py:agents_config.reset_archetypes_config",
       "file": "agents_config.py",
-      "line": 2114,
+      "line": 2115,
       "suggestion": "Add tests that reference 'reset_archetypes_config' (e.g., test_reset_archetypes_config or import it in a test file)"
     },
     {
@@ -2187,7 +2187,7 @@
       "message": "Function '_served_local_roster' has no corresponding test references",
       "node_id": "py:agents_config._served_local_roster",
       "file": "agents_config.py",
-      "line": 2122,
+      "line": 2123,
       "suggestion": "Add tests that reference '_served_local_roster' (e.g., test__served_local_roster or import it in a test file)"
     },
     {
@@ -2196,7 +2196,7 @@
       "message": "Function '_with_served_local_roster' has no corresponding test references",
       "node_id": "py:agents_config._with_served_local_roster",
       "file": "agents_config.py",
-      "line": 2151,
+      "line": 2152,
       "suggestion": "Add tests that reference '_with_served_local_roster' (e.g., test__with_served_local_roster or import it in a test file)"
     },
     {
@@ -2205,7 +2205,7 @@
       "message": "Function '_normalize_provider_model_map' has no corresponding test references",
       "node_id": "py:agents_config._normalize_provider_model_map",
       "file": "agents_config.py",
-      "line": 2165,
+      "line": 2166,
       "suggestion": "Add tests that reference '_normalize_provider_model_map' (e.g., test__normalize_provider_model_map or import it in a test file)"
     },
     {
@@ -2214,7 +2214,7 @@
       "message": "Function 'get_provider_model_map' has no corresponding test references",
       "node_id": "py:agents_config.get_provider_model_map",
       "file": "agents_config.py",
-      "line": 2195,
+      "line": 2196,
       "suggestion": "Add tests that reference 'get_provider_model_map' (e.g., test_get_provider_model_map or import it in a test file)"
     },
     {
@@ -2223,7 +2223,7 @@
       "message": "Function '_tier_entry_to_spec' has no corresponding test references",
       "node_id": "py:agents_config._tier_entry_to_spec",
       "file": "agents_config.py",
-      "line": 2226,
+      "line": 2227,
       "suggestion": "Add tests that reference '_tier_entry_to_spec' (e.g., test__tier_entry_to_spec or import it in a test file)"
     },
     {
@@ -2232,7 +2232,7 @@
       "message": "Function '_best_defined_tier' has no corresponding test references",
       "node_id": "py:agents_config._best_defined_tier",
       "file": "agents_config.py",
-      "line": 2241,
+      "line": 2242,
       "suggestion": "Add tests that reference '_best_defined_tier' (e.g., test__best_defined_tier or import it in a test file)"
     },
     {
@@ -2241,7 +2241,7 @@
       "message": "Function 'resolve_provider_model_spec' has no corresponding test references",
       "node_id": "py:agents_config.resolve_provider_model_spec",
       "file": "agents_config.py",
-      "line": 2250,
+      "line": 2251,
       "suggestion": "Add tests that reference 'resolve_provider_model_spec' (e.g., test_resolve_provider_model_spec or import it in a test file)"
     },
     {
@@ -2250,7 +2250,7 @@
       "message": "Function 'resolve_provider_model' has no corresponding test references",
       "node_id": "py:agents_config.resolve_provider_model",
       "file": "agents_config.py",
-      "line": 2331,
+      "line": 2332,
       "suggestion": "Add tests that reference 'resolve_provider_model' (e.g., test_resolve_provider_model or import it in a test file)"
     },
     {
@@ -2259,7 +2259,7 @@
       "message": "Function 'compose_prompt' has no corresponding test references",
       "node_id": "py:agents_config.compose_prompt",
       "file": "agents_config.py",
-      "line": 2351,
+      "line": 2352,
       "suggestion": "Add tests that reference 'compose_prompt' (e.g., test_compose_prompt or import it in a test file)"
     },
     {
@@ -2268,7 +2268,7 @@
       "message": "Function '_unique_dir_prefixes' has no corresponding test references",
       "node_id": "py:agents_config._unique_dir_prefixes",
       "file": "agents_config.py",
-      "line": 2367,
+      "line": 2368,
       "suggestion": "Add tests that reference '_unique_dir_prefixes' (e.g., test__unique_dir_prefixes or import it in a test file)"
     },
     {
@@ -2277,7 +2277,7 @@
       "message": "Function 'resolve_model' has no corresponding test references",
       "node_id": "py:agents_config.resolve_model",
       "file": "agents_config.py",
-      "line": 2386,
+      "line": 2387,
       "suggestion": "Add tests that reference 'resolve_model' (e.g., test_resolve_model or import it in a test file)"
     },
     {
@@ -2286,7 +2286,7 @@
       "message": "Function '_resolve_model_spec' has no corresponding test references",
       "node_id": "py:agents_config._resolve_model_spec",
       "file": "agents_config.py",
-      "line": 2425,
+      "line": 2426,
       "suggestion": "Add tests that reference '_resolve_model_spec' (e.g., test__resolve_model_spec or import it in a test file)"
     },
     {
@@ -2295,7 +2295,7 @@
       "message": "Function '_finalize' has no corresponding test references",
       "node_id": "py:agents_config._resolve_model_spec._finalize",
       "file": "agents_config.py",
-      "line": 2434,
+      "line": 2435,
       "suggestion": "Add tests that reference '_finalize' (e.g., test__finalize or import it in a test file)"
     },
     {
@@ -2304,7 +2304,7 @@
       "message": "Function 'resolve_archetype_for_phase' has no corresponding test references",
       "node_id": "py:agents_config.resolve_archetype_for_phase",
       "file": "agents_config.py",
-      "line": 2495,
+      "line": 2496,
       "suggestion": "Add tests that reference 'resolve_archetype_for_phase' (e.g., test_resolve_archetype_for_phase or import it in a test file)"
     },
     {
@@ -4284,7 +4284,7 @@
       "message": "Function '_ProjectionProblemError' has no corresponding test references",
       "node_id": "py:coordination_api._ProjectionProblemError",
       "file": "coordination_api.py",
-      "line": 112,
+      "line": 115,
       "suggestion": "Add tests that reference '_ProjectionProblemError' (e.g., test__ProjectionProblemError or import it in a test file)"
     },
     {
@@ -4293,7 +4293,7 @@
       "message": "Function '__init__' has no corresponding test references",
       "node_id": "py:coordination_api._ProjectionProblemError.__init__",
       "file": "coordination_api.py",
-      "line": 113,
+      "line": 116,
       "suggestion": "Add tests that reference '__init__' (e.g., test___init__ or import it in a test file)"
     },
     {
@@ -4302,7 +4302,7 @@
       "message": "Function '_projection_mutation_payload' has no corresponding test references",
       "node_id": "py:coordination_api._projection_mutation_payload",
       "file": "coordination_api.py",
-      "line": 119,
+      "line": 122,
       "suggestion": "Add tests that reference '_projection_mutation_payload' (e.g., test__projection_mutation_payload or import it in a test file)"
     },
     {
@@ -4311,7 +4311,7 @@
       "message": "Function 'LockAcquireRequest' has no corresponding test references",
       "node_id": "py:coordination_api.LockAcquireRequest",
       "file": "coordination_api.py",
-      "line": 145,
+      "line": 150,
       "suggestion": "Add tests that reference 'LockAcquireRequest' (e.g., test_LockAcquireRequest or import it in a test file)"
     },
     {
@@ -4320,7 +4320,7 @@
       "message": "Function 'LockReleaseRequest' has no corresponding test references",
       "node_id": "py:coordination_api.LockReleaseRequest",
       "file": "coordination_api.py",
-      "line": 154,
+      "line": 159,
       "suggestion": "Add tests that reference 'LockReleaseRequest' (e.g., test_LockReleaseRequest or import it in a test file)"
     },
     {
@@ -4329,7 +4329,7 @@
       "message": "Function 'MemoryStoreRequest' has no corresponding test references",
       "node_id": "py:coordination_api.MemoryStoreRequest",
       "file": "coordination_api.py",
-      "line": 159,
+      "line": 164,
       "suggestion": "Add tests that reference 'MemoryStoreRequest' (e.g., test_MemoryStoreRequest or import it in a test file)"
     },
     {
@@ -4338,7 +4338,7 @@
       "message": "Function 'MemoryQueryRequest' has no corresponding test references",
       "node_id": "py:coordination_api.MemoryQueryRequest",
       "file": "coordination_api.py",
-      "line": 170,
+      "line": 175,
       "suggestion": "Add tests that reference 'MemoryQueryRequest' (e.g., test_MemoryQueryRequest or import it in a test file)"
     },
     {
@@ -4347,7 +4347,7 @@
       "message": "Function 'WorkClaimRequest' has no corresponding test references",
       "node_id": "py:coordination_api.WorkClaimRequest",
       "file": "coordination_api.py",
-      "line": 177,
+      "line": 182,
       "suggestion": "Add tests that reference 'WorkClaimRequest' (e.g., test_WorkClaimRequest or import it in a test file)"
     },
     {
@@ -4356,7 +4356,7 @@
       "message": "Function 'WorkCompleteRequest' has no corresponding test references",
       "node_id": "py:coordination_api.WorkCompleteRequest",
       "file": "coordination_api.py",
-      "line": 183,
+      "line": 188,
       "suggestion": "Add tests that reference 'WorkCompleteRequest' (e.g., test_WorkCompleteRequest or import it in a test file)"
     },
     {
@@ -4365,7 +4365,7 @@
       "message": "Function 'ProjectionKeyRequest' has no corresponding test references",
       "node_id": "py:coordination_api.ProjectionKeyRequest",
       "file": "coordination_api.py",
-      "line": 191,
+      "line": 196,
       "suggestion": "Add tests that reference 'ProjectionKeyRequest' (e.g., test_ProjectionKeyRequest or import it in a test file)"
     },
     {
@@ -4374,7 +4374,7 @@
       "message": "Function 'WorkSubmitRequest' has no corresponding test references",
       "node_id": "py:coordination_api.WorkSubmitRequest",
       "file": "coordination_api.py",
-      "line": 216,
+      "line": 231,
       "suggestion": "Add tests that reference 'WorkSubmitRequest' (e.g., test_WorkSubmitRequest or import it in a test file)"
     },
     {
@@ -4383,7 +4383,7 @@
       "message": "Function 'WorkReconcileRequest' has no corresponding test references",
       "node_id": "py:coordination_api.WorkReconcileRequest",
       "file": "coordination_api.py",
-      "line": 228,
+      "line": 244,
       "suggestion": "Add tests that reference 'WorkReconcileRequest' (e.g., test_WorkReconcileRequest or import it in a test file)"
     },
     {
@@ -4392,7 +4392,7 @@
       "message": "Function 'WorkGetTaskRequest' has no corresponding test references",
       "node_id": "py:coordination_api.WorkGetTaskRequest",
       "file": "coordination_api.py",
-      "line": 239,
+      "line": 256,
       "suggestion": "Add tests that reference 'WorkGetTaskRequest' (e.g., test_WorkGetTaskRequest or import it in a test file)"
     },
     {
@@ -4401,7 +4401,7 @@
       "message": "Function 'IssueCreateRequest' has no corresponding test references",
       "node_id": "py:coordination_api.IssueCreateRequest",
       "file": "coordination_api.py",
-      "line": 243,
+      "line": 260,
       "suggestion": "Add tests that reference 'IssueCreateRequest' (e.g., test_IssueCreateRequest or import it in a test file)"
     },
     {
@@ -4410,7 +4410,7 @@
       "message": "Function 'IssueListRequest' has no corresponding test references",
       "node_id": "py:coordination_api.IssueListRequest",
       "file": "coordination_api.py",
-      "line": 254,
+      "line": 271,
       "suggestion": "Add tests that reference 'IssueListRequest' (e.g., test_IssueListRequest or import it in a test file)"
     },
     {
@@ -4419,7 +4419,7 @@
       "message": "Function 'IssueUpdateRequest' has no corresponding test references",
       "node_id": "py:coordination_api.IssueUpdateRequest",
       "file": "coordination_api.py",
-      "line": 263,
+      "line": 280,
       "suggestion": "Add tests that reference 'IssueUpdateRequest' (e.g., test_IssueUpdateRequest or import it in a test file)"
     },
     {
@@ -4428,7 +4428,7 @@
       "message": "Function 'IssueCloseRequest' has no corresponding test references",
       "node_id": "py:coordination_api.IssueCloseRequest",
       "file": "coordination_api.py",
-      "line": 274,
+      "line": 291,
       "suggestion": "Add tests that reference 'IssueCloseRequest' (e.g., test_IssueCloseRequest or import it in a test file)"
     },
     {
@@ -4437,7 +4437,7 @@
       "message": "Function 'IssueCommentRequest' has no corresponding test references",
       "node_id": "py:coordination_api.IssueCommentRequest",
       "file": "coordination_api.py",
-      "line": 280,
+      "line": 297,
       "suggestion": "Add tests that reference 'IssueCommentRequest' (e.g., test_IssueCommentRequest or import it in a test file)"
     },
     {
@@ -4446,7 +4446,7 @@
       "message": "Function 'GuardrailsCheckRequest' has no corresponding test references",
       "node_id": "py:coordination_api.GuardrailsCheckRequest",
       "file": "coordination_api.py",
-      "line": 285,
+      "line": 302,
       "suggestion": "Add tests that reference 'GuardrailsCheckRequest' (e.g., test_GuardrailsCheckRequest or import it in a test file)"
     },
     {
@@ -4455,7 +4455,7 @@
       "message": "Function 'AuditQueryParams' has no corresponding test references",
       "node_id": "py:coordination_api.AuditQueryParams",
       "file": "coordination_api.py",
-      "line": 290,
+      "line": 307,
       "suggestion": "Add tests that reference 'AuditQueryParams' (e.g., test_AuditQueryParams or import it in a test file)"
     },
     {
@@ -4464,7 +4464,7 @@
       "message": "Function 'HandoffWriteRequest' has no corresponding test references",
       "node_id": "py:coordination_api.HandoffWriteRequest",
       "file": "coordination_api.py",
-      "line": 296,
+      "line": 313,
       "suggestion": "Add tests that reference 'HandoffWriteRequest' (e.g., test_HandoffWriteRequest or import it in a test file)"
     },
     {
@@ -4473,7 +4473,7 @@
       "message": "Function 'HandoffReadRequest' has no corresponding test references",
       "node_id": "py:coordination_api.HandoffReadRequest",
       "file": "coordination_api.py",
-      "line": 309,
+      "line": 326,
       "suggestion": "Add tests that reference 'HandoffReadRequest' (e.g., test_HandoffReadRequest or import it in a test file)"
     },
     {
@@ -4482,7 +4482,7 @@
       "message": "Function 'PolicyCheckRequest' has no corresponding test references",
       "node_id": "py:coordination_api.PolicyCheckRequest",
       "file": "coordination_api.py",
-      "line": 315,
+      "line": 332,
       "suggestion": "Add tests that reference 'PolicyCheckRequest' (e.g., test_PolicyCheckRequest or import it in a test file)"
     },
     {
@@ -4491,7 +4491,7 @@
       "message": "Function 'PolicyValidateRequest' has no corresponding test references",
       "node_id": "py:coordination_api.PolicyValidateRequest",
       "file": "coordination_api.py",
-      "line": 323,
+      "line": 340,
       "suggestion": "Add tests that reference 'PolicyValidateRequest' (e.g., test_PolicyValidateRequest or import it in a test file)"
     },
     {
@@ -4500,7 +4500,7 @@
       "message": "Function 'PortAllocateRequest' has no corresponding test references",
       "node_id": "py:coordination_api.PortAllocateRequest",
       "file": "coordination_api.py",
-      "line": 327,
+      "line": 344,
       "suggestion": "Add tests that reference 'PortAllocateRequest' (e.g., test_PortAllocateRequest or import it in a test file)"
     },
     {
@@ -4509,7 +4509,7 @@
       "message": "Function 'PortReleaseRequest' has no corresponding test references",
       "node_id": "py:coordination_api.PortReleaseRequest",
       "file": "coordination_api.py",
-      "line": 331,
+      "line": 348,
       "suggestion": "Add tests that reference 'PortReleaseRequest' (e.g., test_PortReleaseRequest or import it in a test file)"
     },
     {
@@ -4518,7 +4518,7 @@
       "message": "Function 'ApprovalDecisionRequest' has no corresponding test references",
       "node_id": "py:coordination_api.ApprovalDecisionRequest",
       "file": "coordination_api.py",
-      "line": 335,
+      "line": 352,
       "suggestion": "Add tests that reference 'ApprovalDecisionRequest' (e.g., test_ApprovalDecisionRequest or import it in a test file)"
     },
     {
@@ -4527,7 +4527,7 @@
       "message": "Function 'PolicyRollbackRequest' has no corresponding test references",
       "node_id": "py:coordination_api.PolicyRollbackRequest",
       "file": "coordination_api.py",
-      "line": 341,
+      "line": 358,
       "suggestion": "Add tests that reference 'PolicyRollbackRequest' (e.g., test_PolicyRollbackRequest or import it in a test file)"
     },
     {
@@ -4536,7 +4536,7 @@
       "message": "Function 'FeatureRegisterRequest' has no corresponding test references",
       "node_id": "py:coordination_api.FeatureRegisterRequest",
       "file": "coordination_api.py",
-      "line": 345,
+      "line": 362,
       "suggestion": "Add tests that reference 'FeatureRegisterRequest' (e.g., test_FeatureRegisterRequest or import it in a test file)"
     },
     {
@@ -4545,7 +4545,7 @@
       "message": "Function 'FeatureDeregisterRequest' has no corresponding test references",
       "node_id": "py:coordination_api.FeatureDeregisterRequest",
       "file": "coordination_api.py",
-      "line": 355,
+      "line": 372,
       "suggestion": "Add tests that reference 'FeatureDeregisterRequest' (e.g., test_FeatureDeregisterRequest or import it in a test file)"
     },
     {
@@ -4554,7 +4554,7 @@
       "message": "Function 'FeatureConflictsRequest' has no corresponding test references",
       "node_id": "py:coordination_api.FeatureConflictsRequest",
       "file": "coordination_api.py",
-      "line": 360,
+      "line": 377,
       "suggestion": "Add tests that reference 'FeatureConflictsRequest' (e.g., test_FeatureConflictsRequest or import it in a test file)"
     },
     {
@@ -4563,7 +4563,7 @@
       "message": "Function 'StatusReportRequest' has no corresponding test references",
       "node_id": "py:coordination_api.StatusReportRequest",
       "file": "coordination_api.py",
-      "line": 365,
+      "line": 382,
       "suggestion": "Add tests that reference 'StatusReportRequest' (e.g., test_StatusReportRequest or import it in a test file)"
     },
     {
@@ -4572,7 +4572,7 @@
       "message": "Function 'ResolveForPhaseRequest' has no corresponding test references",
       "node_id": "py:coordination_api.ResolveForPhaseRequest",
       "file": "coordination_api.py",
-      "line": 389,
+      "line": 409,
       "suggestion": "Add tests that reference 'ResolveForPhaseRequest' (e.g., test_ResolveForPhaseRequest or import it in a test file)"
     },
     {
@@ -4581,7 +4581,7 @@
       "message": "Function 'MergeQueueEnqueueRequest' has no corresponding test references",
       "node_id": "py:coordination_api.MergeQueueEnqueueRequest",
       "file": "coordination_api.py",
-      "line": 411,
+      "line": 431,
       "suggestion": "Add tests that reference 'MergeQueueEnqueueRequest' (e.g., test_MergeQueueEnqueueRequest or import it in a test file)"
     },
     {
@@ -4590,7 +4590,7 @@
       "message": "Function 'DiscoveryRegisterRequest' has no corresponding test references",
       "node_id": "py:coordination_api.DiscoveryRegisterRequest",
       "file": "coordination_api.py",
-      "line": 416,
+      "line": 436,
       "suggestion": "Add tests that reference 'DiscoveryRegisterRequest' (e.g., test_DiscoveryRegisterRequest or import it in a test file)"
     },
     {
@@ -4599,7 +4599,7 @@
       "message": "Function 'DiscoveryHeartbeatRequest' has no corresponding test references",
       "node_id": "py:coordination_api.DiscoveryHeartbeatRequest",
       "file": "coordination_api.py",
-      "line": 426,
+      "line": 446,
       "suggestion": "Add tests that reference 'DiscoveryHeartbeatRequest' (e.g., test_DiscoveryHeartbeatRequest or import it in a test file)"
     },
     {
@@ -4608,7 +4608,7 @@
       "message": "Function 'DiscoveryCleanupRequest' has no corresponding test references",
       "node_id": "py:coordination_api.DiscoveryCleanupRequest",
       "file": "coordination_api.py",
-      "line": 432,
+      "line": 452,
       "suggestion": "Add tests that reference 'DiscoveryCleanupRequest' (e.g., test_DiscoveryCleanupRequest or import it in a test file)"
     },
     {
@@ -4617,7 +4617,7 @@
       "message": "Function 'GenEvalValidateRequest' has no corresponding test references",
       "node_id": "py:coordination_api.GenEvalValidateRequest",
       "file": "coordination_api.py",
-      "line": 438,
+      "line": 458,
       "suggestion": "Add tests that reference 'GenEvalValidateRequest' (e.g., test_GenEvalValidateRequest or import it in a test file)"
     },
     {
@@ -4626,7 +4626,7 @@
       "message": "Function 'GenEvalCreateRequest' has no corresponding test references",
       "node_id": "py:coordination_api.GenEvalCreateRequest",
       "file": "coordination_api.py",
-      "line": 442,
+      "line": 462,
       "suggestion": "Add tests that reference 'GenEvalCreateRequest' (e.g., test_GenEvalCreateRequest or import it in a test file)"
     },
     {
@@ -4635,7 +4635,7 @@
       "message": "Function 'GenEvalRunRequest' has no corresponding test references",
       "node_id": "py:coordination_api.GenEvalRunRequest",
       "file": "coordination_api.py",
-      "line": 450,
+      "line": 470,
       "suggestion": "Add tests that reference 'GenEvalRunRequest' (e.g., test_GenEvalRunRequest or import it in a test file)"
     },
     {
@@ -4644,7 +4644,7 @@
       "message": "Function 'IssueSearchRequest' has no corresponding test references",
       "node_id": "py:coordination_api.IssueSearchRequest",
       "file": "coordination_api.py",
-      "line": 456,
+      "line": 476,
       "suggestion": "Add tests that reference 'IssueSearchRequest' (e.g., test_IssueSearchRequest or import it in a test file)"
     },
     {
@@ -4653,7 +4653,7 @@
       "message": "Function 'IssueReadyRequest' has no corresponding test references",
       "node_id": "py:coordination_api.IssueReadyRequest",
       "file": "coordination_api.py",
-      "line": 463,
+      "line": 483,
       "suggestion": "Add tests that reference 'IssueReadyRequest' (e.g., test_IssueReadyRequest or import it in a test file)"
     },
     {
@@ -4662,7 +4662,7 @@
       "message": "Function 'PermissionRequestRequest' has no corresponding test references",
       "node_id": "py:coordination_api.PermissionRequestRequest",
       "file": "coordination_api.py",
-      "line": 470,
+      "line": 490,
       "suggestion": "Add tests that reference 'PermissionRequestRequest' (e.g., test_PermissionRequestRequest or import it in a test file)"
     },
     {
@@ -4671,7 +4671,7 @@
       "message": "Function 'ApprovalSubmitRequest' has no corresponding test references",
       "node_id": "py:coordination_api.ApprovalSubmitRequest",
       "file": "coordination_api.py",
-      "line": 477,
+      "line": 497,
       "suggestion": "Add tests that reference 'ApprovalSubmitRequest' (e.g., test_ApprovalSubmitRequest or import it in a test file)"
     },
     {
@@ -4680,7 +4680,7 @@
       "message": "Function 'MergeTrainEjectRequest' has no corresponding test references",
       "node_id": "py:coordination_api.MergeTrainEjectRequest",
       "file": "coordination_api.py",
-      "line": 486,
+      "line": 506,
       "suggestion": "Add tests that reference 'MergeTrainEjectRequest' (e.g., test_MergeTrainEjectRequest or import it in a test file)"
     },
     {
@@ -4689,7 +4689,7 @@
       "message": "Function 'MergeTrainReportResultRequest' has no corresponding test references",
       "node_id": "py:coordination_api.MergeTrainReportResultRequest",
       "file": "coordination_api.py",
-      "line": 491,
+      "line": 511,
       "suggestion": "Add tests that reference 'MergeTrainReportResultRequest' (e.g., test_MergeTrainReportResultRequest or import it in a test file)"
     },
     {
@@ -4698,7 +4698,7 @@
       "message": "Function 'AffectedTestsRequest' has no corresponding test references",
       "node_id": "py:coordination_api.AffectedTestsRequest",
       "file": "coordination_api.py",
-      "line": 497,
+      "line": 517,
       "suggestion": "Add tests that reference 'AffectedTestsRequest' (e.g., test_AffectedTestsRequest or import it in a test file)"
     },
     {
@@ -4707,7 +4707,7 @@
       "message": "Function 'EventsAuthRequest' has no corresponding test references",
       "node_id": "py:coordination_api.EventsAuthRequest",
       "file": "coordination_api.py",
-      "line": 503,
+      "line": 524,
       "suggestion": "Add tests that reference 'EventsAuthRequest' (e.g., test_EventsAuthRequest or import it in a test file)"
     },
     {
@@ -4716,7 +4716,7 @@
       "message": "Function 'PatchLabelsRequest' has no corresponding test references",
       "node_id": "py:coordination_api.PatchLabelsRequest",
       "file": "coordination_api.py",
-      "line": 508,
+      "line": 529,
       "suggestion": "Add tests that reference 'PatchLabelsRequest' (e.g., test_PatchLabelsRequest or import it in a test file)"
     },
     {
@@ -4725,7 +4725,7 @@
       "message": "Function 'KickAgentRequest' has no corresponding test references",
       "node_id": "py:coordination_api.KickAgentRequest",
       "file": "coordination_api.py",
-      "line": 513,
+      "line": 534,
       "suggestion": "Add tests that reference 'KickAgentRequest' (e.g., test_KickAgentRequest or import it in a test file)"
     },
     {
@@ -4734,7 +4734,7 @@
       "message": "Function 'SavedViewRequest' has no corresponding test references",
       "node_id": "py:coordination_api.SavedViewRequest",
       "file": "coordination_api.py",
-      "line": 527,
+      "line": 548,
       "suggestion": "Add tests that reference 'SavedViewRequest' (e.g., test_SavedViewRequest or import it in a test file)"
     },
     {
@@ -4743,7 +4743,7 @@
       "message": "Function 'KanbanAuditRequest' has no corresponding test references",
       "node_id": "py:coordination_api.KanbanAuditRequest",
       "file": "coordination_api.py",
-      "line": 531,
+      "line": 552,
       "suggestion": "Add tests that reference 'KanbanAuditRequest' (e.g., test_KanbanAuditRequest or import it in a test file)"
     },
     {
@@ -4752,7 +4752,7 @@
       "message": "Function '_extract_api_key' has no corresponding test references",
       "node_id": "py:coordination_api._extract_api_key",
       "file": "coordination_api.py",
-      "line": 541,
+      "line": 562,
       "suggestion": "Add tests that reference '_extract_api_key' (e.g., test__extract_api_key or import it in a test file)"
     },
     {
@@ -4761,7 +4761,7 @@
       "message": "Function '_principal_for_api_key' has no corresponding test references",
       "node_id": "py:coordination_api._principal_for_api_key",
       "file": "coordination_api.py",
-      "line": 558,
+      "line": 579,
       "suggestion": "Add tests that reference '_principal_for_api_key' (e.g., test__principal_for_api_key or import it in a test file)"
     },
     {
@@ -4770,7 +4770,7 @@
       "message": "Function 'verify_api_key' has no corresponding test references",
       "node_id": "py:coordination_api.verify_api_key",
       "file": "coordination_api.py",
-      "line": 571,
+      "line": 592,
       "suggestion": "Add tests that reference 'verify_api_key' (e.g., test_verify_api_key or import it in a test file)"
     },
     {
@@ -4779,7 +4779,7 @@
       "message": "Function 'optional_api_key' has no corresponding test references",
       "node_id": "py:coordination_api.optional_api_key",
       "file": "coordination_api.py",
-      "line": 593,
+      "line": 614,
       "suggestion": "Add tests that reference 'optional_api_key' (e.g., test_optional_api_key or import it in a test file)"
     },
     {
@@ -4788,7 +4788,7 @@
       "message": "Function 'resolve_identity' has no corresponding test references",
       "node_id": "py:coordination_api.resolve_identity",
       "file": "coordination_api.py",
-      "line": 605,
+      "line": 626,
       "suggestion": "Add tests that reference 'resolve_identity' (e.g., test_resolve_identity or import it in a test file)"
     },
     {
@@ -4797,7 +4797,7 @@
       "message": "Function 'authorize_operation' has no corresponding test references",
       "node_id": "py:coordination_api.authorize_operation",
       "file": "coordination_api.py",
-      "line": 635,
+      "line": 652,
       "suggestion": "Add tests that reference 'authorize_operation' (e.g., test_authorize_operation or import it in a test file)"
     },
     {
@@ -4806,7 +4806,7 @@
       "message": "Function 'create_coordination_api' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api",
       "file": "coordination_api.py",
-      "line": 661,
+      "line": 678,
       "suggestion": "Add tests that reference 'create_coordination_api' (e.g., test_create_coordination_api or import it in a test file)"
     },
     {
@@ -4815,7 +4815,7 @@
       "message": "Function 'lifespan' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.lifespan",
       "file": "coordination_api.py",
-      "line": 683,
+      "line": 700,
       "suggestion": "Add tests that reference 'lifespan' (e.g., test_lifespan or import it in a test file)"
     },
     {
@@ -4824,7 +4824,7 @@
       "message": "Function 'code_search_problem_handler' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.code_search_problem_handler",
       "file": "coordination_api.py",
-      "line": 822,
+      "line": 843,
       "suggestion": "Add tests that reference 'code_search_problem_handler' (e.g., test_code_search_problem_handler or import it in a test file)"
     },
     {
@@ -4833,7 +4833,7 @@
       "message": "Function 'projection_problem_handler' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.projection_problem_handler",
       "file": "coordination_api.py",
-      "line": 834,
+      "line": 855,
       "suggestion": "Add tests that reference 'projection_problem_handler' (e.g., test_projection_problem_handler or import it in a test file)"
     },
     {
@@ -4842,7 +4842,7 @@
       "message": "Function 'projection_http_problem_handler' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.projection_http_problem_handler",
       "file": "coordination_api.py",
-      "line": 855,
+      "line": 876,
       "suggestion": "Add tests that reference 'projection_http_problem_handler' (e.g., test_projection_http_problem_handler or import it in a test file)"
     },
     {
@@ -4851,7 +4851,7 @@
       "message": "Function 'request_validation_handler' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.request_validation_handler",
       "file": "coordination_api.py",
-      "line": 873,
+      "line": 894,
       "suggestion": "Add tests that reference 'request_validation_handler' (e.g., test_request_validation_handler or import it in a test file)"
     },
     {
@@ -4860,7 +4860,7 @@
       "message": "Function 'acquire_lock' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.acquire_lock",
       "file": "coordination_api.py",
-      "line": 950,
+      "line": 971,
       "suggestion": "Add tests that reference 'acquire_lock' (e.g., test_acquire_lock or import it in a test file)"
     },
     {
@@ -4869,7 +4869,7 @@
       "message": "Function 'release_lock' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.release_lock",
       "file": "coordination_api.py",
-      "line": 987,
+      "line": 1006,
       "suggestion": "Add tests that reference 'release_lock' (e.g., test_release_lock or import it in a test file)"
     },
     {
@@ -4878,7 +4878,7 @@
       "message": "Function 'check_lock_status' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.check_lock_status",
       "file": "coordination_api.py",
-      "line": 1016,
+      "line": 1033,
       "suggestion": "Add tests that reference 'check_lock_status' (e.g., test_check_lock_status or import it in a test file)"
     },
     {
@@ -4887,7 +4887,7 @@
       "message": "Function 'store_memory' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.store_memory",
       "file": "coordination_api.py",
-      "line": 1042,
+      "line": 1059,
       "suggestion": "Add tests that reference 'store_memory' (e.g., test_store_memory or import it in a test file)"
     },
     {
@@ -4896,7 +4896,7 @@
       "message": "Function 'query_memories' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.query_memories",
       "file": "coordination_api.py",
-      "line": 1074,
+      "line": 1091,
       "suggestion": "Add tests that reference 'query_memories' (e.g., test_query_memories or import it in a test file)"
     },
     {
@@ -4905,7 +4905,7 @@
       "message": "Function 'claim_work' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.claim_work",
       "file": "coordination_api.py",
-      "line": 1119,
+      "line": 1134,
       "suggestion": "Add tests that reference 'claim_work' (e.g., test_claim_work or import it in a test file)"
     },
     {
@@ -4914,7 +4914,7 @@
       "message": "Function 'complete_work' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.complete_work",
       "file": "coordination_api.py",
-      "line": 1153,
+      "line": 1166,
       "suggestion": "Add tests that reference 'complete_work' (e.g., test_complete_work or import it in a test file)"
     },
     {
@@ -4923,7 +4923,7 @@
       "message": "Function 'submit_work' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.submit_work",
       "file": "coordination_api.py",
-      "line": 1185,
+      "line": 1198,
       "suggestion": "Add tests that reference 'submit_work' (e.g., test_submit_work or import it in a test file)"
     },
     {
@@ -4932,7 +4932,7 @@
       "message": "Function 'reconcile_work_projection' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.reconcile_work_projection",
       "file": "coordination_api.py",
-      "line": 1220,
+      "line": 1250,
       "suggestion": "Add tests that reference 'reconcile_work_projection' (e.g., test_reconcile_work_projection or import it in a test file)"
     },
     {
@@ -4941,7 +4941,7 @@
       "message": "Function 'get_task_endpoint' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.get_task_endpoint",
       "file": "coordination_api.py",
-      "line": 1248,
+      "line": 1283,
       "suggestion": "Add tests that reference 'get_task_endpoint' (e.g., test_get_task_endpoint or import it in a test file)"
     },
     {
@@ -4950,7 +4950,7 @@
       "message": "Function 'create_issue' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.create_issue",
       "file": "coordination_api.py",
-      "line": 1295,
+      "line": 1330,
       "suggestion": "Add tests that reference 'create_issue' (e.g., test_create_issue or import it in a test file)"
     },
     {
@@ -4959,7 +4959,7 @@
       "message": "Function 'list_issues' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.list_issues",
       "file": "coordination_api.py",
-      "line": 1329,
+      "line": 1364,
       "suggestion": "Add tests that reference 'list_issues' (e.g., test_list_issues or import it in a test file)"
     },
     {
@@ -4968,7 +4968,7 @@
       "message": "Function 'blocked_issues_early' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.blocked_issues_early",
       "file": "coordination_api.py",
-      "line": 1356,
+      "line": 1391,
       "suggestion": "Add tests that reference 'blocked_issues_early' (e.g., test_blocked_issues_early or import it in a test file)"
     },
     {
@@ -4977,7 +4977,7 @@
       "message": "Function 'show_issue' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.show_issue",
       "file": "coordination_api.py",
-      "line": 1373,
+      "line": 1408,
       "suggestion": "Add tests that reference 'show_issue' (e.g., test_show_issue or import it in a test file)"
     },
     {
@@ -4986,7 +4986,7 @@
       "message": "Function 'update_issue' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.update_issue",
       "file": "coordination_api.py",
-      "line": 1390,
+      "line": 1425,
       "suggestion": "Add tests that reference 'update_issue' (e.g., test_update_issue or import it in a test file)"
     },
     {
@@ -4995,7 +4995,7 @@
       "message": "Function 'close_issue' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.close_issue",
       "file": "coordination_api.py",
-      "line": 1422,
+      "line": 1459,
       "suggestion": "Add tests that reference 'close_issue' (e.g., test_close_issue or import it in a test file)"
     },
     {
@@ -5004,7 +5004,7 @@
       "message": "Function 'comment_issue' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.comment_issue",
       "file": "coordination_api.py",
-      "line": 1454,
+      "line": 1493,
       "suggestion": "Add tests that reference 'comment_issue' (e.g., test_comment_issue or import it in a test file)"
     },
     {
@@ -5013,7 +5013,7 @@
       "message": "Function 'check_guardrails' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.check_guardrails",
       "file": "coordination_api.py",
-      "line": 1476,
+      "line": 1515,
       "suggestion": "Add tests that reference 'check_guardrails' (e.g., test_check_guardrails or import it in a test file)"
     },
     {
@@ -5022,7 +5022,7 @@
       "message": "Function 'get_my_profile' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.get_my_profile",
       "file": "coordination_api.py",
-      "line": 1522,
+      "line": 1561,
       "suggestion": "Add tests that reference 'get_my_profile' (e.g., test_get_my_profile or import it in a test file)"
     },
     {
@@ -5031,7 +5031,7 @@
       "message": "Function 'get_agent_dispatch_configs' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.get_agent_dispatch_configs",
       "file": "coordination_api.py",
-      "line": 1552,
+      "line": 1591,
       "suggestion": "Add tests that reference 'get_agent_dispatch_configs' (e.g., test_get_agent_dispatch_configs or import it in a test file)"
     },
     {
@@ -5040,7 +5040,7 @@
       "message": "Function 'query_audit' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.query_audit",
       "file": "coordination_api.py",
-      "line": 1566,
+      "line": 1605,
       "suggestion": "Add tests that reference 'query_audit' (e.g., test_query_audit or import it in a test file)"
     },
     {
@@ -5049,7 +5049,7 @@
       "message": "Function 'write_handoff' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.write_handoff",
       "file": "coordination_api.py",
-      "line": 1626,
+      "line": 1665,
       "suggestion": "Add tests that reference 'write_handoff' (e.g., test_write_handoff or import it in a test file)"
     },
     {
@@ -5058,7 +5058,7 @@
       "message": "Function 'read_handoff' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.read_handoff",
       "file": "coordination_api.py",
-      "line": 1658,
+      "line": 1695,
       "suggestion": "Add tests that reference 'read_handoff' (e.g., test_read_handoff or import it in a test file)"
     },
     {
@@ -5067,7 +5067,7 @@
       "message": "Function 'check_policy' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.check_policy",
       "file": "coordination_api.py",
-      "line": 1701,
+      "line": 1736,
       "suggestion": "Add tests that reference 'check_policy' (e.g., test_check_policy or import it in a test file)"
     },
     {
@@ -5076,7 +5076,7 @@
       "message": "Function 'validate_cedar_policy' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.validate_cedar_policy",
       "file": "coordination_api.py",
-      "line": 1728,
+      "line": 1761,
       "suggestion": "Add tests that reference 'validate_cedar_policy' (e.g., test_validate_cedar_policy or import it in a test file)"
     },
     {
@@ -5085,7 +5085,7 @@
       "message": "Function 'allocate_ports' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.allocate_ports",
       "file": "coordination_api.py",
-      "line": 1759,
+      "line": 1792,
       "suggestion": "Add tests that reference 'allocate_ports' (e.g., test_allocate_ports or import it in a test file)"
     },
     {
@@ -5094,7 +5094,7 @@
       "message": "Function 'release_ports' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.release_ports",
       "file": "coordination_api.py",
-      "line": 1781,
+      "line": 1814,
       "suggestion": "Add tests that reference 'release_ports' (e.g., test_release_ports or import it in a test file)"
     },
     {
@@ -5103,7 +5103,7 @@
       "message": "Function 'port_status' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.port_status",
       "file": "coordination_api.py",
-      "line": 1790,
+      "line": 1823,
       "suggestion": "Add tests that reference 'port_status' (e.g., test_port_status or import it in a test file)"
     },
     {
@@ -5112,7 +5112,7 @@
       "message": "Function '_approval_to_dict' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api._approval_to_dict",
       "file": "coordination_api.py",
-      "line": 1812,
+      "line": 1843,
       "suggestion": "Add tests that reference '_approval_to_dict' (e.g., test__approval_to_dict or import it in a test file)"
     },
     {
@@ -5121,7 +5121,7 @@
       "message": "Function 'list_pending_approvals' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.list_pending_approvals",
       "file": "coordination_api.py",
-      "line": 1830,
+      "line": 1861,
       "suggestion": "Add tests that reference 'list_pending_approvals' (e.g., test_list_pending_approvals or import it in a test file)"
     },
     {
@@ -5130,7 +5130,7 @@
       "message": "Function 'decide_approval' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.decide_approval",
       "file": "coordination_api.py",
-      "line": 1841,
+      "line": 1872,
       "suggestion": "Add tests that reference 'decide_approval' (e.g., test_decide_approval or import it in a test file)"
     },
     {
@@ -5139,7 +5139,7 @@
       "message": "Function 'list_policy_versions_endpoint' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.list_policy_versions_endpoint",
       "file": "coordination_api.py",
-      "line": 1868,
+      "line": 1899,
       "suggestion": "Add tests that reference 'list_policy_versions_endpoint' (e.g., test_list_policy_versions_endpoint or import it in a test file)"
     },
     {
@@ -5148,7 +5148,7 @@
       "message": "Function 'rollback_policy_endpoint' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.rollback_policy_endpoint",
       "file": "coordination_api.py",
-      "line": 1881,
+      "line": 1912,
       "suggestion": "Add tests that reference 'rollback_policy_endpoint' (e.g., test_rollback_policy_endpoint or import it in a test file)"
     },
     {
@@ -5157,7 +5157,7 @@
       "message": "Function 'register_feature_endpoint' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordination_api.register_feature_endpoint",
       "file": "coordination_api.py",
-      "line": 1900,
+      "line": 1931,
       "suggestion": "Add tests that reference 'register_feature_endpoint' (e.g., test_register_feature_endpoint or import it in a test file)"
     },
     {
@@ -5166,7 +5166,7 @@
       "message": "Function 'deregister_feature_endpoint' has no corresponding test references",
       "node_id": "py:coordination_api.create_coordi

[diff truncated to fit packet budget; use Read/Grep for the remainder]

```

### Spec excerpts
#### specs/roadmap-orchestration/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

#### specs/supervise/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

Hunt only in the attached last-fix diff. Re-verify open ledger items. Do not re-open retired or parked items.

### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 4. Focus on remaining issues.