-- 046: review queue across hosts.
--
-- A pull-request review is a work_queue row with task_type 'review' plus one
-- review_jobs row that indexes it by (repo, pr, head_sha, round). Any host
-- with vendor CLIs logged in claims the row through the ordinary claim path,
-- runs whichever review lanes it can, and records per-vendor lane results
-- here. Quorum is counted across hosts: distinct vendors with a verified
-- result for the job, regardless of which machine produced them.
--
-- Lane findings live in review_lane_results rather than in work_queue.result
-- because complete_task's guardrail scan runs over str(result), and review
-- findings routinely quote destructive-looking code; parking them in the
-- result would flip legitimate completions to "blocked".
--
-- Lifecycle of review_jobs.status:
--   active      lanes still owed; the current pass is task_id
--   quorum_met  lanes_required distinct verified vendors recorded
--   unreachable max passes spent without quorum (published as partial)
--   superseded  a newer head_sha arrived for the same PR before publication
-- Publication is tracked separately (published_at / review_id) so a failed
-- GitHub post can be retried without re-running lanes.

BEGIN;

CREATE TABLE IF NOT EXISTS review_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo TEXT NOT NULL,
    pr INTEGER NOT NULL CHECK (pr > 0),
    head_sha TEXT NOT NULL CHECK (head_sha ~ '^[0-9a-f]{40}$'),
    base_sha TEXT NOT NULL CHECK (base_sha ~ '^[0-9a-f]{40}$'),
    round INTEGER NOT NULL CHECK (round >= 1),
    lanes_required INTEGER NOT NULL DEFAULT 2 CHECK (lanes_required >= 1),
    risk TEXT NOT NULL DEFAULT 'medium'
        CHECK (risk IN ('low', 'medium', 'high', 'critical')),
    deadline TIMESTAMPTZ,
    submitted_by TEXT NOT NULL,
    task_id UUID REFERENCES work_queue(id),
    passes INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'quorum_met', 'unreachable', 'superseded')),
    published_at TIMESTAMPTZ,
    review_id BIGINT,
    publish_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (repo, pr, head_sha, round)
);

CREATE INDEX IF NOT EXISTS idx_review_jobs_pr ON review_jobs (repo, pr, status);
CREATE INDEX IF NOT EXISTS idx_review_jobs_task ON review_jobs (task_id);

CREATE TABLE IF NOT EXISTS review_lane_results (
    job_id UUID NOT NULL REFERENCES review_jobs(id) ON DELETE CASCADE,
    vendor TEXT NOT NULL CHECK (length(vendor) BETWEEN 1 AND 64),
    host_agent_id TEXT NOT NULL,
    task_id UUID NOT NULL REFERENCES work_queue(id),
    verified BOOLEAN NOT NULL,
    verdict TEXT,
    model TEXT,
    findings JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(findings) = 'array'),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (job_id, vendor)
);


-- Internal: the job as the JSON shape every RPC below returns.
CREATE OR REPLACE FUNCTION review_job_json(p_job review_jobs)
RETURNS JSONB
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
    SELECT jsonb_build_object(
        'job_id', p_job.id,
        'repo', p_job.repo,
        'pr', p_job.pr,
        'head_sha', p_job.head_sha,
        'base_sha', p_job.base_sha,
        'round', p_job.round,
        'lanes_required', p_job.lanes_required,
        'risk', p_job.risk,
        'deadline', p_job.deadline,
        'task_id', p_job.task_id,
        'passes', p_job.passes,
        'status', p_job.status,
        'published_at', p_job.published_at,
        'review_id', p_job.review_id,
        'publish_error', p_job.publish_error,
        'lanes', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'vendor', l.vendor,
                'host_agent_id', l.host_agent_id,
                'task_id', l.task_id,
                'verified', l.verified,
                'verdict', l.verdict,
                'model', l.model,
                'findings', l.findings,
                'error', l.error
            ) ORDER BY l.vendor)
            FROM review_lane_results l
            WHERE l.job_id = p_job.id
        ), '[]'::jsonb)
    );
$$;


-- Internal: enqueue one claimable pass of a job.
CREATE OR REPLACE FUNCTION review_enqueue_pass(
    p_job review_jobs,
    p_exclude_vendors TEXT[]
)
RETURNS UUID
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_task_id UUID;
BEGIN
    -- input_data deliberately carries none of change_id / phase /
    -- transition_sequence: those mark a row as an autopilot projection.
    INSERT INTO work_queue(task_type, description, input_data, priority, deadline)
    VALUES (
        'review',
        format('Review %s#%s at %s (round %s, pass %s)',
               p_job.repo, p_job.pr, left(p_job.head_sha, 12),
               p_job.round, p_job.passes),
        jsonb_build_object(
            'review_job_id', p_job.id,
            'repo', p_job.repo,
            'pr', p_job.pr,
            'head_sha', p_job.head_sha,
            'base_sha', p_job.base_sha,
            'round', p_job.round,
            'lanes_required', p_job.lanes_required,
            'risk', p_job.risk,
            'pass', p_job.passes,
            'exclude_vendors', to_jsonb(COALESCE(p_exclude_vendors, ARRAY[]::TEXT[])),
            'submitted_by', p_job.submitted_by
        ),
        CASE p_job.risk WHEN 'critical' THEN 2 WHEN 'high' THEN 3 ELSE 5 END,
        p_job.deadline
    )
    RETURNING id INTO v_task_id;
    RETURN v_task_id;
END;
$$;


-- Producer entry point. Idempotent on (repo, pr, head_sha, round); with
-- p_round NULL an existing job for the same head is returned instead of a new
-- round. A different head supersedes every unpublished job for the PR.
CREATE OR REPLACE FUNCTION submit_review_job(
    p_repo TEXT,
    p_pr INTEGER,
    p_head_sha TEXT,
    p_base_sha TEXT,
    p_submitted_by TEXT,
    p_round INTEGER DEFAULT NULL,
    p_lanes_required INTEGER DEFAULT 2,
    p_risk TEXT DEFAULT 'medium',
    p_deadline TIMESTAMPTZ DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_job review_jobs;
    v_round INTEGER;
    v_superseded UUID[];
BEGIN
    IF p_round IS NOT NULL AND p_round < 1 THEN
        RETURN jsonb_build_object('success', FALSE, 'reason', 'invalid_round');
    END IF;

    -- Serialize per PR so concurrent pushes cannot both win the supersede.
    PERFORM pg_advisory_xact_lock(
        hashtextextended('review_job:' || p_repo || '#' || p_pr::TEXT, 0)
    );

    SELECT * INTO v_job FROM review_jobs
    WHERE repo = p_repo AND pr = p_pr AND head_sha = p_head_sha
      AND (p_round IS NULL OR round = p_round)
    ORDER BY round DESC
    LIMIT 1;

    IF FOUND THEN
        RETURN jsonb_build_object(
            'success', TRUE,
            'created', FALSE,
            'deduplicated', TRUE,
            'superseded_task_ids', '[]'::jsonb,
            'job', review_job_json(v_job)
        );
    END IF;

    WITH stale AS (
        UPDATE review_jobs
        SET status = 'superseded', updated_at = NOW()
        WHERE repo = p_repo AND pr = p_pr AND head_sha <> p_head_sha
          AND status <> 'superseded' AND published_at IS NULL
        RETURNING task_id
    ), cancelled AS (
        UPDATE work_queue
        SET status = 'cancelled', closed_at = NOW(),
            close_reason = 'superseded_by_new_head'
        WHERE id IN (SELECT task_id FROM stale)
          AND status IN ('pending', 'claimed', 'running')
        RETURNING id
    )
    SELECT COALESCE(array_agg(id), ARRAY[]::UUID[]) INTO v_superseded FROM cancelled;

    v_round := COALESCE(
        p_round,
        (SELECT MAX(round) FROM review_jobs WHERE repo = p_repo AND pr = p_pr),
        0
    );
    IF p_round IS NULL THEN
        v_round := v_round + 1;
    END IF;

    INSERT INTO review_jobs(
        repo, pr, head_sha, base_sha, round, lanes_required, risk,
        deadline, submitted_by
    )
    VALUES (
        p_repo, p_pr, p_head_sha, p_base_sha, v_round, p_lanes_required,
        p_risk, p_deadline, p_submitted_by
    )
    RETURNING * INTO v_job;

    UPDATE review_jobs SET task_id = review_enqueue_pass(v_job, NULL)
    WHERE id = v_job.id
    RETURNING * INTO v_job;

    RETURN jsonb_build_object(
        'success', TRUE,
        'created', TRUE,
        'deduplicated', FALSE,
        'superseded_task_ids', to_jsonb(v_superseded),
        'job', review_job_json(v_job)
    );
END;
$$;


-- Worker entry point. p_lanes is a JSON array of
--   {vendor, verified, verdict?, model?, findings?, error?}
-- recorded against the job whose current pass is p_task_id. The caller must
-- be the agent that claimed that pass. A verified row is never replaced by an
-- unverified one. When quorum is still short and passes remain, a residual
-- pass is enqueued that excludes the vendors already verified.
CREATE OR REPLACE FUNCTION record_review_lanes(
    p_task_id UUID,
    p_agent_id TEXT,
    p_lanes JSONB,
    p_max_passes INTEGER DEFAULT 3
)
RETURNS JSONB
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_task work_queue;
    v_job review_jobs;
    v_verified TEXT[];
    v_residual UUID;
BEGIN
    IF jsonb_typeof(p_lanes) IS DISTINCT FROM 'array' THEN
        RETURN jsonb_build_object('success', FALSE, 'reason', 'invalid_lanes');
    END IF;

    SELECT * INTO v_task FROM work_queue WHERE id = p_task_id;
    IF NOT FOUND OR v_task.task_type <> 'review' THEN
        RETURN jsonb_build_object('success', FALSE, 'reason', 'task_not_found');
    END IF;
    IF v_task.claimed_by IS DISTINCT FROM p_agent_id THEN
        RETURN jsonb_build_object('success', FALSE, 'reason', 'not_claimant');
    END IF;

    SELECT * INTO v_job FROM review_jobs
    WHERE id = (v_task.input_data->>'review_job_id')::UUID
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', FALSE, 'reason', 'job_not_found');
    END IF;
    IF v_job.status = 'superseded' THEN
        RETURN jsonb_build_object(
            'success', FALSE, 'reason', 'superseded', 'job', review_job_json(v_job)
        );
    END IF;
    IF v_job.task_id IS DISTINCT FROM p_task_id THEN
        RETURN jsonb_build_object(
            'success', FALSE, 'reason', 'stale_pass', 'job', review_job_json(v_job)
        );
    END IF;

    INSERT INTO review_lane_results(
        job_id, vendor, host_agent_id, task_id, verified, verdict, model,
        findings, error
    )
    SELECT
        v_job.id,
        lane->>'vendor',
        p_agent_id,
        p_task_id,
        COALESCE((lane->>'verified')::BOOLEAN, FALSE),
        lane->>'verdict',
        lane->>'model',
        COALESCE(lane->'findings', '[]'::jsonb),
        lane->>'error'
    FROM jsonb_array_elements(p_lanes) AS lane
    ON CONFLICT (job_id, vendor) DO UPDATE
    SET host_agent_id = EXCLUDED.host_agent_id,
        task_id = EXCLUDED.task_id,
        verified = EXCLUDED.verified,
        verdict = EXCLUDED.verdict,
        model = EXCLUDED.model,
        findings = EXCLUDED.findings,
        error = EXCLUDED.error,
        created_at = NOW()
    WHERE NOT review_lane_results.verified OR EXCLUDED.verified;

    SELECT COALESCE(array_agg(vendor ORDER BY vendor), ARRAY[]::TEXT[])
    INTO v_verified
    FROM review_lane_results WHERE job_id = v_job.id AND verified;

    IF v_job.status = 'active' THEN
        IF cardinality(v_verified) >= v_job.lanes_required THEN
            UPDATE review_jobs SET status = 'quorum_met', updated_at = NOW()
            WHERE id = v_job.id RETURNING * INTO v_job;
        ELSIF v_job.passes >= p_max_passes THEN
            UPDATE review_jobs SET status = 'unreachable', updated_at = NOW()
            WHERE id = v_job.id RETURNING * INTO v_job;
        ELSE
            UPDATE review_jobs SET passes = passes + 1, updated_at = NOW()
            WHERE id = v_job.id RETURNING * INTO v_job;
            v_residual := review_enqueue_pass(v_job, v_verified);
            UPDATE review_jobs SET task_id = v_residual
            WHERE id = v_job.id RETURNING * INTO v_job;
        END IF;
    END IF;

    RETURN jsonb_build_object(
        'success', TRUE,
        'verified_vendors', to_jsonb(v_verified),
        'residual_task_id', v_residual,
        'publish_ready', v_job.status IN ('quorum_met', 'unreachable')
                         AND v_job.published_at IS NULL,
        'job', review_job_json(v_job)
    );
END;
$$;


-- Read model for converge() and for workers checking for supersession.
-- Returns the requested round, or the latest round for the head when
-- p_round is NULL.
CREATE OR REPLACE FUNCTION get_review_round(
    p_repo TEXT,
    p_pr INTEGER,
    p_head_sha TEXT,
    p_round INTEGER DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_job review_jobs;
BEGIN
    SELECT * INTO v_job FROM review_jobs
    WHERE repo = p_repo AND pr = p_pr AND head_sha = p_head_sha
      AND (p_round IS NULL OR round = p_round)
    ORDER BY round DESC
    LIMIT 1;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('found', FALSE);
    END IF;
    RETURN jsonb_build_object('found', TRUE, 'job', review_job_json(v_job));
END;
$$;


-- Publication claim: exactly one caller gets claimed=true per job until it
-- reports failure, which releases the claim for a retry.
CREATE OR REPLACE FUNCTION claim_review_publication(p_job_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_job review_jobs;
BEGIN
    UPDATE review_jobs
    SET published_at = NOW(), publish_error = NULL, updated_at = NOW()
    WHERE id = p_job_id AND published_at IS NULL
      AND status IN ('quorum_met', 'unreachable')
    RETURNING * INTO v_job;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('claimed', FALSE);
    END IF;
    RETURN jsonb_build_object('claimed', TRUE, 'job', review_job_json(v_job));
END;
$$;


CREATE OR REPLACE FUNCTION finish_review_publication(
    p_job_id UUID,
    p_review_id BIGINT DEFAULT NULL,
    p_error TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF p_error IS NULL THEN
        UPDATE review_jobs
        SET review_id = p_review_id, updated_at = NOW()
        WHERE id = p_job_id AND published_at IS NOT NULL;
    ELSE
        UPDATE review_jobs
        SET published_at = NULL, publish_error = left(p_error, 500),
            updated_at = NOW()
        WHERE id = p_job_id;
    END IF;
    RETURN jsonb_build_object('success', FOUND);
END;
$$;


REVOKE ALL ON FUNCTION review_job_json(review_jobs) FROM PUBLIC;
REVOKE ALL ON FUNCTION review_enqueue_pass(review_jobs, TEXT[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION submit_review_job(
    TEXT, INTEGER, TEXT, TEXT, TEXT, INTEGER, INTEGER, TEXT, TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION record_review_lanes(UUID, TEXT, JSONB, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION get_review_round(TEXT, INTEGER, TEXT, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION claim_review_publication(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION finish_review_publication(UUID, BIGINT, TEXT) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION review_job_json(review_jobs) TO service_role;
GRANT EXECUTE ON FUNCTION review_enqueue_pass(review_jobs, TEXT[]) TO service_role;
GRANT EXECUTE ON FUNCTION submit_review_job(
    TEXT, INTEGER, TEXT, TEXT, TEXT, INTEGER, INTEGER, TEXT, TIMESTAMPTZ
) TO service_role;
GRANT EXECUTE ON FUNCTION record_review_lanes(UUID, TEXT, JSONB, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION get_review_round(TEXT, INTEGER, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION claim_review_publication(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION finish_review_publication(UUID, BIGINT, TEXT) TO service_role;

COMMIT;
