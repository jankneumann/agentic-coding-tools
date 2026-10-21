## Review Round 1

The packet is complete; do not explore the repo for missing artifacts.

You have no file-reading tools: this packet is everything you can see. Review only what it contains.

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
OPTIONAL: report which selected files you actually reviewed as a top-level `coverage` object: `{"reviewed": ["path", ...], "skipped": [{"path": "path", "reason": "why"}, ...]}`. Omitting `coverage` is treated as full coverage, never as a penalty.
Output ONLY a JSON object with a top-level `findings` array.

### Diff
```diff
diff --git a/agent-coordinator/agents.yaml b/agent-coordinator/agents.yaml
index 62bf5b50..8922c5fe 100644
--- a/agent-coordinator/agents.yaml
+++ b/agent-coordinator/agents.yaml
@@ -466,3 +466,43 @@ agents:
       model: null
       model_fallbacks: []
       prompt_via_stdin: true
+
+  # First OpenAI-compatible review lane (OpenSpec change openrouter-review-lane,
+  # design D1). Endpoint-only: no `cli` and no `sdk` block, so the review
+  # dispatcher builds only the tier-2.5 OpenAICompatAdapter from
+  # endpoint_kind + base_url. Lane id = `type` = `openrouter`; it must stay
+  # unique because converge() keys checkpointed results by vendor. Its model
+  # tiers live under model_aliases.openrouter in archetypes.yaml.
+  #
+  # No `api_key`: the lane never calls the coordinator under its own identity.
+  # Without a principal the dispatcher falls back to its OPENROUTER_API_KEY
+  # default for endpoint_kind openrouter (works in non-OpenBao/cloud mode).
+  # The schema is additionalProperties:false, so there is no agent-level
+  # api_key_env field.
+  openrouter-review:
+    type: openrouter
+    location: cloud
+    policy_vendor: openrouter
+    # Models are OpenRouter catalog rows. pi-local lists under the same
+    # catalog vendor; _provider_for_catalog_vendor skips endpoint-only agents
+    # so a routed `openrouter` selection still maps to the pi harness.
+    catalog_vendor: openrouter
+    endpoint_kind: openrouter
+    base_url: https://openrouter.ai/api/v1
+    profile: openrouter_review
+    trust_level: 1
+    transport: http
+    isolation: none
+    # No vendor_credentials: the OpenBao topology projection forbids them on a
+    # keyless agent (openbao_credentials.topology, "keyless agent cannot
+    # declare vendor credentials"). The dispatcher consults credential scopes
+    # only for agents with a principal, so the key comes from the
+    # OPENROUTER_API_KEY environment default instead.
+    # `discover` only: being found as an available reviewer at dispatch time.
+    capabilities: [discover]
+    archetypes: [reviewer]
+    description: >-
+      Metered cloud review lane over OpenRouter's OpenAI-compatible chat
+      completions API. Adds a model family that no host CLI serves, so a
+      cloud session with only the Claude CLI can still reach multi-vendor
+      review quorum. Costed under routing.yaml tier metered-api-cloud.
diff --git a/agent-coordinator/archetypes.yaml b/agent-coordinator/archetypes.yaml
index 8d08cfd9..724c45ae 100644
--- a/agent-coordinator/archetypes.yaml
+++ b/agent-coordinator/archetypes.yaml
@@ -66,6 +66,20 @@ model_aliases:
     premium: nvidia/nemotron-3-ultra-550b-a55b
     standard: qwen/qwen3-coder
     economy: qwen/qwen3-coder-flash
+  openrouter:
+    # Endpoint-only review lane `openrouter-review` (agents.yaml; OpenSpec
+    # change openrouter-review-lane, design D1/D2). premium is the review
+    # model; standard/economy are its fallbacks (_derived_tier_fallbacks).
+    # Rule: no `anthropic/` publisher, and preferably a family no host CLI
+    # serves (not openai/codex, google/antigravity, xai/grok).
+    # Catalog: GET https://openrouter.ai/api/v1/models (public, no key),
+    # consulted 2026-10-21. The live fetch was unreachable from the
+    # implementing sandbox (DNS), so these slugs are carried from the pi
+    # roster above, last verified against that catalog on 2026-09-13.
+    # Re-verify before relying on them.
+    premium: nvidia/nemotron-3-ultra-550b-a55b
+    standard: qwen/qwen3-coder
+    economy: qwen/qwen3-coder-flash
   # Always-on local host (see local_host_class above). Entries use the extended
   # form {model, total_params_b, active_params_b, reviewed} so the MoE-first
   # rule is validated, not merely documented; `reviewed` is the operator's
diff --git a/agent-coordinator/database/migrations/046_spend_generation_id_unique.sql b/agent-coordinator/database/migrations/046_spend_generation_id_unique.sql
new file mode 100644
index 00000000..74ba5e5f
--- /dev/null
+++ b/agent-coordinator/database/migrations/046_spend_generation_id_unique.sql
@@ -0,0 +1,100 @@
+-- 046: make POST /routing/spend's generation_id dedupe atomic.
+--
+-- generation_id is the idempotency key of POST /routing/spend. The route used
+-- to look the key up and then insert, so two concurrent posts of one
+-- generation could both miss the lookup and both insert, double-counting the
+-- spend. The dedupe now belongs to the database: a partial unique index on
+-- generation_id, and record_spend_once(), which inserts with
+-- ON CONFLICT DO NOTHING and otherwise returns the row already recorded.
+--
+-- The index is partial (WHERE generation_id IS NOT NULL) because generation_id
+-- is nullable: rows written through LedgerService.record by other callers may
+-- carry no generation and must not collide with each other.
+
+BEGIN;
+
+-- Duplicates may already exist: the race above could produce them. Each one
+-- is the same generation counted twice, so keep the earliest row (lowest id)
+-- and drop the rest; otherwise the unique index below cannot be built.
+DELETE FROM routing_spend_ledger AS later
+USING routing_spend_ledger AS earlier
+WHERE later.generation_id IS NOT NULL
+  AND later.generation_id = earlier.generation_id
+  AND later.id > earlier.id;
+
+CREATE UNIQUE INDEX IF NOT EXISTS uq_spend_ledger_generation_id
+    ON routing_spend_ledger (generation_id)
+    WHERE generation_id IS NOT NULL;
+
+-- Insert one spend row unless its generation_id is already recorded.
+--
+-- Returns {"created": true, "row": <inserted row>} on a fresh insert and
+-- {"created": false, "row": <existing row>} when the generation was already
+-- recorded. Under READ COMMITTED, ON CONFLICT DO NOTHING waits for a
+-- concurrent inserter of the same key to commit, and the follow-up SELECT
+-- runs with a fresh snapshot, so it sees that row. Returns jsonb (not a
+-- composite) so both database clients decode it (see 045).
+CREATE OR REPLACE FUNCTION record_spend_once(p_row JSONB)
+RETURNS JSONB
+LANGUAGE plpgsql
+VOLATILE
+SECURITY INVOKER
+SET search_path = public, pg_temp
+AS $$
+DECLARE
+    v_in routing_spend_ledger;
+    v_row routing_spend_ledger;
+BEGIN
+    v_in := jsonb_populate_record(NULL::routing_spend_ledger, p_row);
+
+    INSERT INTO routing_spend_ledger (
+        occurred_at,
+        decision_id,
+        vendor,
+        model,
+        endpoint_kind,
+        prompt_tokens,
+        completion_tokens,
+        tokens_estimated,
+        actual_usd,
+        counterfactual_usd,
+        exploration,
+        generation_id,
+        work_unit_ref
+    )
+    VALUES (
+        COALESCE(v_in.occurred_at, now()),
+        v_in.decision_id,
+        v_in.vendor,
+        v_in.model,
+        v_in.endpoint_kind,
+        v_in.prompt_tokens,
+        v_in.completion_tokens,
+        COALESCE(v_in.tokens_estimated, FALSE),
+        COALESCE(v_in.actual_usd, 0),
+        COALESCE(v_in.counterfactual_usd, 0),
+        COALESCE(v_in.exploration, FALSE),
+        v_in.generation_id,
+        v_in.work_unit_ref
+    )
+    ON CONFLICT (generation_id) WHERE generation_id IS NOT NULL DO NOTHING
+    RETURNING * INTO v_row;
+
+    IF FOUND THEN
+        RETURN jsonb_build_object('created', TRUE, 'row', to_jsonb(v_row));
+    END IF;
+
+    SELECT * INTO v_row
+    FROM routing_spend_ledger
+    WHERE generation_id = v_in.generation_id
+    ORDER BY id
+    LIMIT 1;
+
+    RETURN jsonb_build_object('created', FALSE, 'row', to_jsonb(v_row));
+END;
+$$;
+
+REVOKE ALL ON FUNCTION record_spend_once(JSONB) FROM PUBLIC;
+GRANT EXECUTE ON FUNCTION record_spend_once(JSONB) TO service_role;
+
+COMMIT;
diff --git a/agent-coordinator/routing.yaml b/agent-coordinator/routing.yaml
index b0c4ace3..822c02db 100644
--- a/agent-coordinator/routing.yaml
+++ b/agent-coordinator/routing.yaml
@@ -15,6 +15,11 @@ cost_policy:
     - id: metered-api
       location: local
       endpoint_kinds: [openrouter]
+    # Cloud OpenRouter lanes (openrouter-review-lane, design D1). Last rung:
+    # it never outranks a subscription tier.
+    - id: metered-api-cloud
+      location: cloud
+      endpoint_kinds: [openrouter]
 
 defaults:
   dispatch_mode: quick
diff --git a/agent-coordinator/src/agents_config.py b/agent-coordinator/src/agents_config.py
index c5a4f9e0..b7b8f350 100644
--- a/agent-coordinator/src/agents_config.py
+++ b/agent-coordinator/src/agents_config.py
@@ -2865,11 +2865,16 @@ def _provider_for_catalog_vendor(catalog_vendor: str) -> str | None:
     agent type, or more than one, lists models under that vendor: a routed
     selection that names no single agent type cannot be dispatched, so the caller
     falls back to static rather than guess.
+
+    Endpoint-only agents (no ``cli``/``sdk``, e.g. the ``openrouter-review``
+    lane) are skipped: they are review lanes, not harnesses a routed task can
+    be dispatched to, so they do not make a catalog vendor ambiguous.
     """
     types = {
         agent.type
         for agent in get_agents_config()
         if (agent.catalog_vendor or agent.type) == catalog_vendor
+        and (agent.cli is not None or agent.sdk is not None)
     }
     return types.pop() if len(types) == 1 else None
 
diff --git a/agent-coordinator/src/model_routing/api.py b/agent-coordinator/src/model_routing/api.py
index 32b02d83..cee933fc 100644
--- a/agent-coordinator/src/model_routing/api.py
+++ b/agent-coordinator/src/model_routing/api.py
@@ -177,7 +177,10 @@ class RoutingProvenanceResponse(BaseModel):
     persisted: bool
     durable_audit: bool
     catalog_key: tuple[str, str, str, str | None] | None
-    cost_tier: Literal["subscription-local", "subscription-cloud", "metered-api"] | None = None
+    cost_tier: (
+        Literal["subscription-local", "subscription-cloud", "metered-api", "metered-api-cloud"]
+        | None
+    ) = None
 
 
 class CandidateResponse(BaseModel):
@@ -278,6 +281,41 @@ class HTTPErrorResponse(BaseModel):
     detail: str
 
 
+class SpendRecordRequest(BaseModel):
+    """One metered review's spend row (openrouter-review-lane, design D4).
+
+    ``generation_id`` is the idempotency key. Unknown fields are rejected so a
+    client can never smuggle a credential or rate field into the ledger.
+    """
+
+    model_config = ConfigDict(extra="forbid")
+
+    vendor: str = Field(min_length=1)
+    model: str = Field(min_length=1)
+    endpoint_kind: EndpointKind
+    generation_id: str = Field(min_length=1)
+    prompt_tokens: int | None = Field(default=None, ge=0)
+    completion_tokens: int | None = Field(default=None, ge=0)
+    actual_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
+    tokens_estimated: bool = False
+    work_unit_ref: str | None = None
+    occurred_at: datetime | None = None
+
+
+class SpendRecordResponse(BaseModel):
+    id: int | str | None = None
+    vendor: str
+    model: str
+    endpoint_kind: str
+    generation_id: str
+    prompt_tokens: int | None = None
+    completion_tokens: int | None = None
+    actual_usd: float = 0.0
+    tokens_estimated: bool = False
+    work_unit_ref: str | None = None
+    occurred_at: datetime | None = None
+
+
 class FeedbackMetrics(BaseModel):
     model_config = ConfigDict(extra="forbid")
 
@@ -325,6 +363,10 @@ class _Ledger(Protocol):
         month: Any = None,
     ) -> dict[str, Any]: ...
 
+    async def record(self, record: Any) -> dict[str, Any]: ...
+
+    async def record_once(self, record: Any) -> tuple[dict[str, Any], bool]: ...
+
 
 class RoutingUnavailableError(RuntimeError):
     """No feasible candidate or backing service is currently available."""
@@ -833,6 +875,16 @@ class RoutingService:
             "estimated_fraction": estimates / entries if entries else 0.0,
         }
 
+    async def record_spend(self, request: SpendRecordRequest) -> tuple[dict[str, Any], bool]:
+        """Write one spend row unless its ``generation_id`` is already recorded.
+
+        Returns ``(row, created)``. The dedupe is atomic: the ledger inserts
+        with ``ON CONFLICT DO NOTHING`` against the unique index on
+        ``generation_id`` (migration 046) and otherwise returns the row already
+        recorded, so concurrent posts of one generation write exactly one row.
+        """
+        return await self.ledger.record_once(request.model_dump(exclude_none=True))
+
     async def post_feedback(self, event: FeedbackEvent) -> dict[str, bool]:
         """Accept feedback without coupling callers to aggregation cadence."""
         from ..audit import get_audit_service
@@ -922,7 +974,7 @@ _SELECT_RESPONSES = {
 
 
 def install_routing_routes(app: FastAPI, auth_dependency: Any) -> None:
-    """Register the five OpenAPI routing paths on the coordinator app."""
+    """Register the six OpenAPI routing paths on the coordinator app."""
 
     @app.post(
         "/routing/select_model",
@@ -983,6 +1035,28 @@ def install_routing_routes(app: FastAPI, auth_dependency: Any) -> None:
             window=window, include_estimates=include_estimates
         )
 
+    @app.post(
+        "/routing/spend",
+        status_code=201,
+        response_model=SpendRecordResponse,
+        dependencies=[Depends(auth_dependency)],
+        responses={
+            **_AUTH_RESPONSES,
+            200: {
+                "model": SpendRecordResponse,
+                "description": "generation_id already recorded; existing row returned",
+            },
+        },
+    )
+    async def spend_endpoint(request: SpendRecordRequest) -> Any:
+        row, created = await get_routing_service().record_spend(request)
+        if created:
+            return row
+        return JSONResponse(
+            status_code=200,
+            content=SpendRecordResponse.model_validate(row).model_dump(mode="json"),
+        )
+
     @app.post(
         "/routing/feedback",
         status_code=202,
diff --git a/agent-coordinator/src/model_routing/ledger.py b/agent-coordinator/src/model_routing/ledger.py
index 806b9a66..1bd64cd2 100644
--- a/agent-coordinator/src/model_routing/ledger.py
+++ b/agent-coordinator/src/model_routing/ledger.py
@@ -49,6 +49,24 @@ class LedgerService:
         return self._db
 
     async def record(self, record: UsageRecord | dict[str, Any]) -> dict[str, Any]:
+        return await self.db.insert("routing_spend_ledger", self._ledger_row(record))
+
+    async def record_once(
+        self, record: UsageRecord | dict[str, Any]
+    ) -> tuple[dict[str, Any], bool]:
+        """Insert ``record`` unless its ``generation_id`` is already recorded.
+
+        Returns ``(row, created)``: the inserted row and ``True``, or the row
+        already holding that ``generation_id`` and ``False``. The check and the
+        insert happen in one statement inside ``record_spend_once``
+        (migration 046), decided by the partial unique index on
+        ``generation_id``, so concurrent callers cannot both insert.
+        """
+        result = await self.db.rpc("record_spend_once", {"p_row": self._ledger_row(record)})
+        return dict(result["row"]), bool(result["created"])
+
+    @staticmethod
+    def _ledger_row(record: UsageRecord | dict[str, Any]) -> dict[str, Any]:
         values = asdict(record) if isinstance(record, UsageRecord) else dict(record)
         prompt_tokens = int(values.get("prompt_tokens") or 0)
         completion_tokens = int(values.get("completion_tokens") or 0)
@@ -83,7 +101,18 @@ class LedgerService:
         row["counterfactual_usd"] = round(float(counterfactual), 6)
         if isinstance(row.get("occurred_at"), datetime):
             row["occurred_at"] = row["occurred_at"].isoformat()
-        return await self.db.insert("routing_spend_ledger", row)
+        return row
+
+    async def find_by_generation_id(self, generation_id: str) -> dict[str, Any] | None:
+        """Return the first ledger row carrying ``generation_id``, or ``None``.
+
+        ``generation_id`` is the idempotency key of ``POST /routing/spend``.
+        """
+        rows = await self.db.query(
+            "routing_spend_ledger",
+            f"generation_id=eq.{encode_filter_value(generation_id)}&order=id.asc&limit=1",
+        )
+        return rows[0] if rows else None
 
     async def usage_summary(
         self,
diff --git a/agent-coordinator/src/model_routing/routing_policy.py b/agent-coordinator/src/model_routing/routing_policy.py
index 3d25324b..902bb7bd 100644
--- a/agent-coordinator/src/model_routing/routing_policy.py
+++ b/agent-coordinator/src/model_routing/routing_policy.py
@@ -95,7 +95,7 @@ class FallbackOrder(_StrictModel):
 
 
 class CostTier(_StrictModel):
-    id: Literal["subscription-local", "subscription-cloud", "metered-api"]
+    id: Literal["subscription-local", "subscription-cloud", "metered-api", "metered-api-cloud"]
     location: Location
     endpoint_kinds: list[Literal["vendor-cli", "vendor-sdk", "openrouter", "local"]] = Field(
         min_length=1
@@ -109,11 +109,16 @@ class CostTier(_StrictModel):
 
 
 class CostPolicy(_StrictModel):
-    tiers: list[CostTier] = Field(min_length=3, max_length=3)
+    tiers: list[CostTier] = Field(min_length=3, max_length=4)
 
     @model_validator(mode="after")
     def validate_ladder(self) -> CostPolicy:
+        # The three-rung ladder is fixed; the optional fourth rung
+        # metered-api-cloud (cloud OpenRouter lanes, openrouter-review-lane D1)
+        # may only be appended last, so it never outranks a subscription tier.
         expected = ["subscription-local", "subscription-cloud", "metered-api"]
+        if len(self.tiers) == 4:
+            expected = [*expected, "metered-api-cloud"]
         if [tier.id for tier in self.tiers] != expected:
             raise ValueError("cost tiers must follow the declared subscription and metered ladder")
         if len(
diff --git a/agent-coordinator/tests/integration/postgres/test_fresh_database_migration.py b/agent-coordinator/tests/integration/postgres/test_fresh_database_migration.py
index 1717f898..634b5dc9 100644
--- a/agent-coordinator/tests/integration/postgres/test_fresh_database_migration.py
+++ b/agent-coordinator/tests/integration/postgres/test_fresh_database_migration.py
@@ -68,6 +68,7 @@ REQUIRED_FUNCTIONS = [
     "is_domain_allowed",
     "upsert_vendor_probe_state",
     "persist_vendor_probe_state",
+    "record_spend_once",
     "record_vendor_rate_limit",
     "compact_vendor_rate_limits",
     "mutate_issue_if_unowned",
@@ -877,3 +878,153 @@ async def test_watchdog_stale_agent_sweep_runs_against_the_migrated_schema(
         assert held == 0
     finally:
         await conn.close()
+
+
+def _spend_row(generation_id: str | None, **overrides: object) -> dict[str, object]:
+    row: dict[str, object] = {
+        "vendor": "openrouter",
+        "model": "review-model",
+        "endpoint_kind": "openrouter",
+        "prompt_tokens": 1200,
+        "completion_tokens": 300,
+        "actual_usd": 0.0042,
+        "counterfactual_usd": 0.0,
+        "tokens_estimated": False,
+        "work_unit_ref": "openrouter-review-lane:VAL_REVIEW:round-2",
+    }
+    if generation_id is not None:
+        row["generation_id"] = generation_id
+    row.update(overrides)
+    return row
+
+
+async def test_046_concurrent_spend_posts_write_one_row(migrated_database) -> None:
+    """Migration 046: concurrent record_spend_once calls for one generation
+    insert exactly one row; every other caller gets that row back."""
+    from src.config import PostgresConfig
+    from src.db_postgres import DirectPostgresClient
+    from src.model_routing.ledger import LedgerService
+
+    dsn, _applied = migrated_database
+    client = DirectPostgresClient(PostgresConfig(dsn=dsn, pool_min=1, pool_max=8))
+    try:
+        ledger = LedgerService(client)
+        results = await asyncio.gather(
+            *(ledger.record_once(_spend_row("gen-race")) for _ in range(8))
+        )
+    finally:
+        await client.close()
+
+    assert sorted(created for _row, created in results) == [False] * 7 + [True]
+    assert len({row["id"] for row, _created in results}) == 1
+    conn = await _connect(dsn)
+    try:
+        count = await conn.fetchval(
+            "SELECT count(*) FROM routing_spend_ledger WHERE generation_id = 'gen-race'"
+        )
+        assert count == 1
+        # A plain insert of the same generation is now refused by the index.
+        with pytest.raises(asyncpg.UniqueViolationError):
+            await conn.execute(
+                "INSERT INTO routing_spend_ledger (vendor, model, endpoint_kind, generation_id) "
+                "VALUES ('openrouter', 'review-model', 'openrouter', 'gen-race')"
+            )
+        # Rows without a generation are outside the partial index.
+        for _ in range(2):
+            await conn.execute(
+                "INSERT INTO routing_spend_ledger (vendor, model, endpoint_kind) "
+                "VALUES ('claude', 'review-model', 'vendor-cli')"
+            )
+    finally:
+        await conn.close()
+
+
+async def test_046_upgrade_keeps_the_earliest_duplicate(tmp_path) -> None:
+    """A pre-046 ledger may already hold duplicates from the old race; the
+    migration keeps the lowest id per generation and then builds the index."""
+    if not _postgres_available:
+        pytest.skip("PostgreSQL not running (start with: docker-compose up -d)")
+
+    name = f"migtest_{uuid.uuid4().hex[:12]}"
+    try:
+        admin = await asyncio.wait_for(_connect(POSTGRES_DSN), timeout=ADMIN_TIMEOUT)
+    except (TimeoutError, OSError) as exc:
+        pytest.skip(f"could not reach PostgreSQL to create a test database: {exc}")
+    try:
+        await admin.execute(f'CREATE DATABASE "{name}"')
+    except asyncpg.InsufficientPrivilegeError:
+        pytest.skip("role may not CREATE DATABASE")
+    finally:
+        await admin.close()
+
+    dsn = _admin_dsn_for(name)
+    pre_dir = tmp_path / "pre046"
+    post_dir = tmp_path / "post046"
+    pre_dir.mkdir()
+    post_dir.mkdir()
+    for sequence, filename, path in discover_migrations():
+        if sequence < 46:
+            (pre_dir / filename).symlink_to(path)
+        elif sequence == 46:
+            (post_dir / filename).symlink_to(path)
+
+    try:
+        try:
+            await asyncio.wait_for(
+                run_migrations(dsn, migrations_dir=pre_dir), timeout=MIGRATE_TIMEOUT
+            )
+        except asyncpg.FeatureNotSupportedError as exc:
+            if "vector" in str(exc):
+                pytest.skip("pgvector extension not installed on this server")
+            raise
+        conn = await _connect(dsn)
+        try:
+            insert = (
+                "INSERT INTO routing_spend_ledger "
+                "(vendor, model, endpoint_kind, generation_id, actual_usd) "
+                "VALUES ('openrouter', 'review-model', 'openrouter', $1, $2) RETURNING id"
+            )
+            first = await conn.fetchval(insert, "gen-dup", 0.01)
+            await conn.fetchval(insert, "gen-dup", 0.02)
+            await conn.fetchval(insert, "gen-dup", 0.03)
+            single = await conn.fetchval(insert, "gen-single", 0.04)
+            await conn.fetchval(insert, None, 0.05)
+            await conn.fetchval(insert, None, 0.06)
+        finally:
+            await conn.close()
+
+        await asyncio.wait_for(
+            run_migrations(dsn, migrations_dir=post_dir), timeout=MIGRATE_TIMEOUT
+        )
+
+        conn = await _connect(dsn)
+        try:
+            kept = await conn.fetch(
+                "SELECT id, generation_id FROM routing_spend_ledger "
+                "WHERE generation_id IS NOT NULL ORDER BY id"
+            )
+            assert [(r["id"], r["generation_id"]) for r in kept] == [
+                (first, "gen-dup"),
+                (single, "gen-single"),
+            ]
+            nulls = await conn.fetchval(
+                "SELECT count(*) FROM routing_spend_ledger WHERE generation_id IS NULL"
+            )
+            assert nulls == 2
+            result = await conn.fetchval(
+                "SELECT record_spend_once($1::jsonb)", json.dumps(_spend_row("gen-dup"))
+            )
+            decoded = json.loads(result)
+            assert decoded["created"] is False
+            assert decoded["row"]["id"] == first
+        finally:
+            await conn.close()
+    finally:
+        try:
+            admin = await asyncio.wait_for(_connect(POSTGRES_DSN), timeout=ADMIN_TIMEOUT)
+            try:
+                await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
+            finally:
+                await admin.close()
+        except Exception:  # noqa: BLE001 - cleanup is advisory
+            pass
diff --git a/agent-coordinator/tests/model_routing/test_agent_endpoints.py b/agent-coordinator/tests/model_routing/test_agent_endpoints.py
index a85cb2d9..ad68fbd1 100644
--- a/agent-coordinator/tests/model_routing/test_agent_endpoints.py
+++ b/agent-coordinator/tests/model_routing/test_agent_endpoints.py
@@ -111,5 +111,7 @@ def test_bundled_registry_declares_lane_identity_and_reporter_capability() -> No
         assert loaded[name].location == raw["location"]
         assert loaded[name].policy_vendor == raw["policy_vendor"]
         assert loaded[name].catalog_vendor == raw["catalog_vendor"]
-        if loaded[name].trust_level < 3 and name != "ocr-local":
+        # Keyless agents (ocr-local, the openrouter-review lane) hold no
+        # coordinator identity, so they cannot call report_vendor_rate_limit.
+        if loaded[name].trust_level < 3 and loaded[name].api_key is not None:
             assert "vendor_limit_reporter" in loaded[name].capabilities, name
diff --git a/agent-coordinator/tests/model_routing/test_ledger.py b/agent-coordinator/tests/model_routing/test_ledger.py
index d78f31e5..164b0c56 100644
--- a/agent-coordinator/tests/model_routing/test_ledger.py
+++ b/agent-coordinator/tests/model_routing/test_ledger.py
@@ -41,6 +41,37 @@ async def test_record_computes_actual_and_metered_counterfactual() -> None:
     assert row["tokens_estimated"] is False
 
 
+@pytest.mark.asyncio
+async def test_record_once_sends_the_computed_row_to_the_atomic_rpc() -> None:
+    db = _db()
+    db.rpc = AsyncMock(
+        side_effect=lambda _fn, params: {"created": False, "row": {"id": 7, **params["p_row"]}}
+    )
+    ledger = LedgerService(db)
+
+    row, created = await ledger.record_once(
+        UsageRecord(
+            vendor="openrouter",
+            model="review-model",
+            endpoint_kind="openrouter",
+            prompt_tokens=1_000_000,
+            actual_prompt_usd_per_mtok=2.0,
+            generation_id="gen-1",
+            occurred_at=datetime(2026, 10, 1, tzinfo=UTC),
+        )
+    )
+
+    db.rpc.assert_awaited_once()
+    function_name, params = db.rpc.await_args.args
+    assert function_name == "record_spend_once"
+    assert params["p_row"]["generation_id"] == "gen-1"
+    assert params["p_row"]["actual_usd"] == pytest.approx(2.0)
+    assert params["p_row"]["occurred_at"] == "2026-10-01T00:00:00+00:00"
+    assert "actual_prompt_usd_per_mtok" not in params["p_row"]
+    db.insert.assert_not_awaited()
+    assert (row["id"], created) == (7, False)
+
+
 @pytest.mark.asyncio
 async def test_usage_summary_can_exclude_estimated_entries() -> None:
     db = _db(
diff --git a/agent-coordinator/tests/model_routing/test_routing_cost_policy.py b/agent-coordinator/tests/model_routing/test_routing_cost_policy.py
index ad3a3c33..191f4ad8 100644
--- a/agent-coordinator/tests/model_routing/test_routing_cost_policy.py
+++ b/agent-coordinator/tests/model_routing/test_routing_cost_policy.py
@@ -104,7 +104,9 @@ def test_cost_policy_schema_and_loader_reject_invalid_ladder(tmp_path) -> None:
     from openspec_paths import change_dir, repo_root_from
 
     schema_path = (
-        change_dir(repo_root_from(__file__, 3), "declare-the-routing-cost-policy-the-router-obeys")
+        # openrouter-review-lane supersedes the archived ladder schema with the
+        # metered-api-cloud tier; archives stay as history.
+        change_dir(repo_root_from(__file__, 3), "openrouter-review-lane")
         / "contracts/config/routing-cost-policy.schema.json"
     )
     schema = json.loads(schema_path.read_text())
diff --git a/agent-coordinator/tests/model_routing/test_routing_policy_config.py b/agent-coordinator/tests/model_routing/test_routing_policy_config.py
index 1274caca..bf741453 100644
--- a/agent-coordinator/tests/model_routing/test_routing_policy_config.py
+++ b/agent-coordinator/tests/model_routing/test_routing_policy_config.py
@@ -12,7 +12,9 @@ from jsonschema import Draft202012Validator, ValidationError
 from openspec_paths import change_dir, repo_root_from
 
 _ROOT = repo_root_from(__file__, 3)
-_CHANGE = change_dir(_ROOT, "implement-the-task-router-vendor-x-location-x-model")
+# openrouter-review-lane supersedes the task-router schema with the
+# metered-api-cloud cost tier; the deployed policy must validate against it.
+_CHANGE = change_dir(_ROOT, "openrouter-review-lane")
 _POLICY = _ROOT / "agent-coordinator/routing.yaml"
 _POLICY_SCHEMA = _CHANGE / "contracts/config/routing.schema.json"
 _ARCHETYPES = _ROOT / "agent-coordinator/archetypes.yaml"
diff --git a/agent-coordinator/tests/model_routing/test_spend_route.py b/agent-coordinator/tests/model_routing/test_spend_route.py
new file mode 100644
index 00000000..c72f4feb
--- /dev/null
+++ b/agent-coordinator/tests/model_routing/test_spend_route.py
@@ -0,0 +1,258 @@
+"""Contract tests for ``POST /routing/spend`` (openrouter-review-lane, task 4.1).
+
+The route writes one ``routing_spend_ledger`` row per metered review through
+``LedgerService.record``; ``generation_id`` is the idempotency key.
+"""
+
+from __future__ import annotations
+
+import asyncio
+from collections.abc import Iterator
+from datetime import UTC, datetime
+from typing import Any
+from unittest.mock import AsyncMock, patch
+from urllib.parse import unquote
+
+import httpx
+import pytest
+from fastapi.testclient import TestClient
+
+from src.config import reset_config
+from src.coordination_api import create_coordination_api
+from src.model_routing.api import RoutingService
+from src.model_routing.ledger import LedgerService
+
+_TEST_KEY = "spend-route-test-key"
+
+
+class UniqueViolationError(Exception):
+    """What the fake raises where PostgreSQL would raise ``23505``."""
+
+
+class _MemoryDb:
+    """In-memory ``routing_spend_ledger`` mirroring migration 046.
+
+    It honours the ``generation_id=eq.`` filter, enforces the partial unique
+    index on ``generation_id`` (a plain ``insert`` of a duplicate raises, as
+    PostgreSQL would), and implements ``record_spend_once`` as one atomic step,
+    like its ``INSERT ... ON CONFLICT DO NOTHING``. ``query`` yields to the
+    event loop so concurrent callers interleave the way they would over a real
+    connection; a lookup-then-insert therefore races here exactly as in prod.
+    """
+
+    def __init__(self) -> None:
+        self.rows: list[dict[str, Any]] = []
+
+    async def query(
+        self, table: str, query_params: str | None = None, select: str = "*"
+    ) -> list[dict[str, Any]]:
+        assert table == "routing_spend_ledger"
+        await asyncio.sleep(0)
+        rows = list(self.rows)
+        for clause in (query_params or "").split("&"):
+            key, _, expr = clause.partition("=")
+            if key == "generation_id" and expr.startswith("eq."):
+                wanted = unquote(expr[3:])
+                rows = [row for row in rows if row.get("generation_id") == wanted]
+        return rows
+
+    def _existing(self, generation_id: Any) -> dict[str, Any] | None:
+        if generation_id is None:
+            return None
+        return next(
+            (row for row in self.rows if row.get("generation_id") == generation_id), None
+        )
+
+    def _append(self, data: dict[str, Any]) -> dict[str, Any]:
+        row = {"id": len(self.rows) + 1, **data}
+        row.setdefault("occurred_at", datetime.now(UTC).isoformat())
+        self.rows.append(row)
+        return row
+
+    async def insert(
+        self, table: str, data: dict[str, Any], return_data: bool = True
+    ) -> dict[str, Any]:
+        assert table == "routing_spend_ledger"
+        await asyncio.sleep(0)
+        if self._existing(data.get("generation_id")) is not None:
+            raise UniqueViolationError(data["generation_id"])
+        return self._append(data)
+
+    async def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
+        assert function_name == "record_spend_once"
+        await asyncio.sleep(0)
+        data = params["p_row"]
+        existing = self._existing(data.get("generation_id"))
+        if existing is not None:
+            return {"created": False, "row": existing}
+        return {"created": True, "row": self._append(data)}
+
+
+@pytest.fixture()
+def memory_db() -> _MemoryDb:
+    return _MemoryDb()
+
+
+@pytest.fixture()
+def client(monkeypatch: pytest.MonkeyPatch, memory_db: _MemoryDb) -> Iterator[TestClient]:
+    reset_config()
+    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
+    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
+    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
+    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
+    monkeypatch.setenv("ROUTING_MONTHLY_CEILING_USD", "10")
+    reset_config()
+    service = RoutingService(catalog=AsyncMock(), ledger=LedgerService(memory_db))
+    with patch("src.model_routing.api.get_routing_service", return_value=service):
+        yield TestClient(create_coordination_api())
+    reset_config()
+
+
+def _headers() -> dict[str, str]:
+    return {"X-API-Key": _TEST_KEY}
+
+
+def _body(**overrides: Any) -> dict[str, Any]:
+    body: dict[str, Any] = {
+        "vendor": "openrouter",
+        "model": "openai/gpt-5",
+        "endpoint_kind": "openrouter",
+        "generation_id": "gen-abc",
+        "prompt_tokens": 1200,
+        "completion_tokens": 300,
+        "actual_usd": 0.0042,
+        "tokens_estimated": False,
+        "work_unit_ref": "openrouter-review-lane:VAL_REVIEW:round-2",
+    }
+    body.update(overrides)
+    return body
+
+
+def test_spend_route_is_registered(client: TestClient) -> None:
+    paths = {
+        (method, route.path)
+        for route in client.app.routes
+        if hasattr(route, "methods")
+        for method in route.methods
+    }
+    assert ("POST", "/routing/spend") in paths
+
+
+def test_insert_returns_201_and_writes_one_row(
+    client: TestClient, memory_db: _MemoryDb
+) -> None:
+    response = client.post("/routing/spend", headers=_headers(), json=_body())
+
+    assert response.status_code == 201
+    payload = response.json()
+    assert payload["generation_id"] == "gen-abc"
+    assert payload["actual_usd"] == pytest.approx(0.0042)
+    assert len(memory_db.rows) == 1
+    row = memory_db.rows[0]
+    assert row["vendor"] == "openrouter"
+    assert row["endpoint_kind"] == "openrouter"
+    assert row["tokens_estimated"] is False
+    assert row["work_unit_ref"] == "openrouter-review-lane:VAL_REVIEW:round-2"
+
+
+def test_duplicate_generation_id_returns_200_without_second_row(
+    client: TestClient, memory_db: _MemoryDb
+) -> None:
+    first = client.post("/routing/spend", headers=_headers(), json=_body())
+    second = client.post("/routing/spend", headers=_headers(), json=_body())
+
+    assert first.status_code == 201
+    assert second.status_code == 200
+    assert second.json()["id"] == first.json()["id"]
+    assert [row["generation_id"] for row in memory_db.rows] == ["gen-abc"]
+
+
+@pytest.mark.asyncio
+async def test_concurrent_duplicate_generation_id_writes_exactly_one_row(
+    client: TestClient, memory_db: _MemoryDb
+) -> None:
+    """Concurrent posts of one generation: one 201, the rest 200, one row.
+
+    A lookup-then-insert lets every racer miss the lookup and insert; the
+    dedupe has to be decided by the database's unique index in one step.
+    """
+    transport = httpx.ASGITransport(app=client.app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
+        responses = await asyncio.gather(
+            *(
+                http.post("/routing/spend", headers=_headers(), json=_body())
+                for _ in range(5)
+            )
+        )
+
+    statuses = sorted(response.status_code for response in responses)
+    assert statuses == [200, 200, 200, 200, 201]
+    assert [row["generation_id"] for row in memory_db.rows] == ["gen-abc"]
+    assert {response.json()["id"] for response in responses} == {memory_db.rows[0]["id"]}
+
+
+@pytest.mark.parametrize(
+    "headers",
+    [{}, {"X-API-Key": "wrong-key"}],
+    ids=["missing", "invalid"],
+)
+def test_unauthenticated_write_is_rejected(
+    client: TestClient, memory_db: _MemoryDb, headers: dict[str, str]
+) -> None:
+    response = client.post("/routing/spend", headers=headers, json=_body())
+
+    assert response.status_code == 401
+    assert memory_db.rows == []
+
+
+@pytest.mark.parametrize(
+    "body",
+    [
+        _body(actual_usd=-1),
+        _body(api_key="sk-should-never-be-accepted"),
+        _body(prompt_tokens=-5),
+        {key: value for key, value in _body().items() if key != "generation_id"},
+    ],
+    ids=["negative-actual-usd", "unknown-field", "negative-tokens", "missing-generation-id"],
+)
+def test_invalid_spend_is_rejected_with_422(
+    client: TestClient, memory_db: _MemoryDb, body: dict[str, Any]
+) -> None:
+    response = client.post("/routing/spend", headers=_headers(), json=body)
+
+    assert response.status_code == 422
+    assert memory_db.rows == []
+
+
+def test_usage_reflects_recorded_review_row(client: TestClient) -> None:
+    before = client.get("/routing/usage?window=month", headers=_headers())
+    assert before.status_code == 200
+    used_before = before.json()["metered_usd_used"]
+
+    posted = client.post("/routing/spend", headers=_headers(), json=_body())
+    assert posted.status_code == 201
+
+    after = client.get("/routing/usage?window=month", headers=_headers())
+    assert after.status_code == 200
+    assert after.json()["metered_usd_used"] == pytest.approx(used_before + 0.0042)
+
+
+@pytest.mark.asyncio
+async def test_find_by_generation_id_returns_row_or_none(memory_db: _MemoryDb) -> None:
+    ledger = LedgerService(memory_db)
+    assert await ledger.find_by_generation_id("gen-x&y") is None
+
+    await ledger.record(
+        {
+            "vendor": "openrouter",
+            "model": "openai/gpt-5",
+            "endpoint_kind": "openrouter",
+            "generation_id": "gen-x&y",
+            "actual_usd": 0.01,
+        }
+    )
+
+    found = await ledger.find_by_generation_id("gen-x&y")
+    assert found is not None
+    assert found["generation_id"] == "gen-x&y"
+    assert await ledger.find_by_generation_id("gen-other") is None
diff --git a/agent-coordinator/tests/openapi_contract_drift_baseline.yaml b/agent-coordinator/tests/openapi_contract_drift_baseline.yaml
index b14276a8..eb13d505 100644
--- a/agent-coordinator/tests/openapi_contract_drift_baseline.yaml
+++ b/agent-coordinator/tests/openapi_contract_drift_baseline.yaml
@@ -30,6 +30,9 @@ uncontracted_routes:
   - route: POST /routing/feedback
     finding: served but not contracted
     reason: Same as GET /routing/catalog — archived change, routing contract never promoted.
+  - route: POST /routing/spend
+    finding: served but not contracted
+    reason: Added by in-flight openrouter-review-lane (task 4.2); the routing contract is still unpromoted (see GET /routing/catalog). Resolves when the routing contract is promoted.
   - route: POST /routing/select_model
     finding: served but not contracted
     reason: Same as GET /routing/catalog; implement-the-task-router-vendor-x-location-x-model also extends it in flight.
diff --git a/agent-coordinator/tests/test_agents_config.py b/agent-coordinator/tests/test_agents_config.py
index b3bc4e64..3079d355 100644
--- a/agent-coordinator/tests/test_agents_config.py
+++ b/agent-coordinator/tests/test_agents_config.py
@@ -814,6 +814,10 @@ CLOUD_ROSTER_PROVIDER_KEYS = frozenset(
     {"claude_code", "codex", "antigravity", "grok", "pi"}
 )
 ROSTER_PROVIDER_KEYS = CLOUD_ROSTER_PROVIDER_KEYS | {"local"}
+# Endpoint-only review-lane providers (openrouter-review-lane D1). They live
+# in archetypes.yaml model_aliases but are not first-class harness providers,
+# so DEFAULT_PROVIDER_MODEL_MAP does not carry them.
+REVIEW_LANE_PROVIDER_KEYS = frozenset({"openrouter"})
 BASE_MODEL_TIERS = frozenset({"premium", "standard", "economy"})
 
 
@@ -1413,7 +1417,9 @@ class TestExistingProvidersAreByteIdentical:
         existing_providers = sorted(
             p for p in raw["model_aliases"] if p != LOCAL_PROVIDER
         )
-        assert set(existing_providers) == set(CLOUD_ROSTER_PROVIDER_KEYS)
+        assert set(existing_providers) == set(
+            CLOUD_ROSTER_PROVIDER_KEYS | REVIEW_LANE_PROVIDER_KEYS
+        )
 
         # "Before": the same config with the local roster + host class removed.
         del raw["model_aliases"][LOCAL_PROVIDER]
@@ -1680,3 +1686,133 @@ def test_bao_mode_ignores_explicit_static_identity_override(
     config = ApiConfig.from_env()
     assert config.api_keys == ["static-key"]  # preserved for cutover preflight
     assert config.api_key_identities == {}
+
+
+# ---------------------------------------------------------------------------
+# openrouter-review lane roster (openrouter-review-lane, task 2.1 / design D1)
+# ---------------------------------------------------------------------------
+
+
+class TestOpenRouterReviewLane:
+    """The endpoint-only OpenRouter reviewer agent in the real agents.yaml."""
+
+    @staticmethod
+    def _lane() -> AgentEntry:
+        entries = load_agents_config()
+        matches = [e for e in entries if e.name == "openrouter-review"]
+        assert len(matches) == 1, "agents.yaml must declare exactly one openrouter-review"
+        return matches[0]
+
+    def test_endpoint_only_reviewer_shape(self) -> None:
+        lane = self._lane()
+        assert lane.type == "openrouter"
+        assert lane.endpoint_kind == "openrouter"
+        assert lane.base_url == "https://openrouter.ai/api/v1"
+        assert lane.cli is None
+        assert lane.sdk is None
+        assert lane.archetypes == ["reviewer"]
+        # Keyless: the OpenBao topology projection rejects a keyless agent
+        # that declares vendor_credentials (no principal can hold them). The
+        # dispatcher reads credential scopes only for agents with a
+        # principal, and falls back to OPENROUTER_API_KEY for this lane.
+        assert lane.vendor_credentials == ()
+        assert lane.location == "cloud"
+        assert lane.transport == "http"
+
+    def test_lane_has_no_coordinator_identity(self) -> None:
+        # D1: no api_key — the lane never calls the coordinator as itself.
+        assert self._lane().api_key is None
+
+    def test_lane_type_is_unique_lane_id(self) -> None:
+        # converge() keys checkpointed results by vendor (= agent type).
+        types = [e.type for e in load_agents_config() if e.endpoint_kind == "openrouter"]
+        assert types.count("openrouter") == 1
+
+    def test_dispatch_configs_emit_lane(self) -> None:
+        from src.agents_config import get_dispatch_configs
+
+        configs = get_dispatch_configs(load_agents_config())["agents"]
+        lane = next(c for c in configs if c["agent_id"] == "openrouter-review")
+        assert lane["type"] == "openrouter"
+        assert lane["endpoint_kind"] == "openrouter"
+        assert lane["base_url"] == "https://openrouter.ai/api/v1"
+        assert lane["cli"] is None
+        assert lane["sdk"] is None
+        assert not lane.get("vendor_credentials")
+        assert lane["principal_id"] is None
+
+
+class TestMeteredCloudCostTier:
+    """routing.yaml must rank a cloud OpenRouter agent (design D1)."""
+
+    def test_cloud_openrouter_has_a_cost_tier(self) -> None:
+        from src.model_routing.routing_policy import load_routing_policy
+
+        policy = load_routing_policy()
+        tier = policy.cost_tier("cloud", "openrouter")
+        assert tier is not None
+        assert tier[1] == "metered-api-cloud"
+
+    def test_cloud_metered_tier_is_last_rung(self) -> None:
+        from src.model_routing.routing_policy import load_routing_policy
+
+        policy = load_routing_policy()
+        tiers = policy.document.cost_policy.tiers
+        cloud = policy.cost_tier("cloud", "openrouter")
+        assert cloud is not None
+        assert cloud[0] == len(tiers) - 1
+
+    def test_local_openrouter_stays_metered_api(self) -> None:
+        from src.model_routing.routing_policy import load_routing_policy
+
+        tier = load_routing_policy().cost_tier("local", "openrouter")
+        assert tier is not None
+        assert tier[1] == "metered-api"
+
+    def test_cloud_metered_tier_cannot_outrank_subscription(self, tmp_path: Path) -> None:
+        import yaml
+
+        from src.model_routing.routing_policy import load_routing_policy
+
+        source = Path(__file__).resolve().parent.parent / "routing.yaml"
+        raw = yaml.safe_load(source.read_text())
+        tiers = raw["cost_policy"]["tiers"]
+        cloud = next(t for t in tiers if t["id"] == "metered-api-cloud")
+        tiers.remove(cloud)
+        tiers.insert(0, cloud)
+        path = tmp_path / "routing.yaml"
+        path.write_text(yaml.safe_dump(raw))
+        with pytest.raises(ValueError, match="cost tiers must follow"):
+            load_routing_policy(path)
+
+    def test_provenance_response_admits_every_cost_tier_id(self) -> None:
+        # Every id the policy can return must survive the API response model.
+        import typing
+
+        from src.model_routing.api import RoutingProvenanceResponse
+        from src.model_routing.routing_policy import load_routing_policy
+
+        annotation = RoutingProvenanceResponse.model_fields["cost_tier"].annotation
+        literal = next(a for a in typing.get_args(annotation) if a is not type(None))
+        allowed = set(typing.get_args(literal))
+        ids = {tier.id for tier in load_routing_policy().document.cost_policy.tiers}
+        assert ids <= allowed
+
+
+class TestCatalogVendorStaysUnambiguous:
+    """The lane shares catalog vendor `openrouter` with pi-local (design D1).
+
+    A routed selection naming catalog vendor `openrouter` must still map to
+    the pi harness: the endpoint-only lane has no CLI/SDK to dispatch a
+    routed task to, so it does not make the vendor ambiguous.
+    """
+
+    def test_openrouter_catalog_vendor_maps_to_pi(self) -> None:
+        from src.agents_config import _provider_for_catalog_vendor
+
+        assert _provider_for_catalog_vendor("openrouter") == "pi"
+
+    def test_pi_catalog_vendor_is_still_openrouter(self) -> None:
+        from src.agents_config import _catalog_vendor_for_provider
+
+        assert _catalog_vendor_for_provider("pi") == "openrouter"
diff --git a/agent-coordinator/tests/test_archetypes_yaml.py b/agent-coordinator/tests/test_archetypes_yaml.py
index c108358f..ffede639 100644
--- a/agent-coordinator/tests/test_archetypes_yaml.py
+++ b/agent-coordinator/tests/test_archetypes_yaml.py
@@ -369,3 +369,27 @@ def test_installed_schema_accepts_every_known_mode() -> None:
         raw = _raw()
         raw["archetypes"]["runner"]["procedure_mode"] = mode
         validate(instance=raw, schema=_installed_schema())
+
+
+# ---------------------------------------------------------------------------
+# openrouter-review-lane task 2.1 — the `openrouter` provider tier map
+# ---------------------------------------------------------------------------
+
+
+@pytest.mark.parametrize("tier", ["premium", "standard", "economy"])
+def test_openrouter_provider_resolves_non_anthropic_slug(
+    tier: str, _load_real_config: None,
+) -> None:
+    spec = resolve_provider_model_spec(tier, provider="openrouter")
+    publisher, sep, model = spec.model.partition("/")
+    assert sep == "/" and publisher and model, (
+        f"openrouter {tier} slug must be <publisher>/<model>, got {spec.model!r}"
+    )
+    assert publisher != "anthropic"
+
+
+def test_openrouter_provider_declares_no_anthropic_model() -> None:
+    entries = _raw()["model_aliases"]["openrouter"]
+    for tier, entry in entries.items():
+        model = entry["model"] if isinstance(entry, dict) else entry
+        assert not model.startswith("anthropic/"), (tier, model)
diff --git a/agent-coordinator/tests/test_migrations.py b/agent-coordinator/tests/test_migrations.py
index 8eeaef90..77ecaf2a 100644
--- a/agent-coordinator/tests/test_migrations.py
+++ b/agent-coordinator/tests/test_migrations.py
@@ -405,3 +405,24 @@ def test_migration_044_persists_retention_and_nullable_selection() -> None:
         in sql
     )
     assert "GRANT EXECUTE ON FUNCTION record_routing_decision_with_audit(JSONB, JSONB)" in sql
+
+
+def test_migration_046_makes_spend_generation_id_dedupe_atomic() -> None:
+    sql = (
+        _COORDINATOR_ROOT / "database/migrations/046_spend_generation_id_unique.sql"
+    ).read_text()
+
+    # Pre-existing duplicates are collapsed to the earliest row first, or the
+    # unique index could not be built on a ledger the old race already hit.
+    dedupe = sql.index("DELETE FROM routing_spend_ledger")
+    index = sql.index("CREATE UNIQUE INDEX IF NOT EXISTS uq_spend_ledger_generation_id")
+    assert dedupe < index
+    assert "later.id > earlier.id" in sql
+    assert "WHERE generation_id IS NOT NULL;" in sql
+    assert "CREATE OR REPLACE FUNCTION record_spend_once(p_row JSONB)" in sql
+    assert "RETURNS JSONB" in sql
+    assert "ON CONFLICT (generation_id) WHERE generation_id IS NOT NULL DO NOTHING" in sql
+    assert "SECURITY INVOKER" in sql
+    assert "SET search_path = public, pg_temp" in sql
+    assert "REVOKE ALL ON FUNCTION record_spend_once(JSONB) FROM PUBLIC" in sql
+    assert "GRANT EXECUTE ON FUNCTION record_spend_once(JSONB) TO service_role" in sql
diff --git a/agent-coordinator/tests/test_vendor_registry.py b/agent-coordinator/tests/test_vendor_registry.py
index 172840ad..07990dbf 100644
--- a/agent-coordinator/tests/test_vendor_registry.py
+++ b/agent-coordinator/tests/test_vendor_registry.py
@@ -436,6 +436,49 @@ async def test_openrouter_lane_projects_despite_publisher_vendor_and_base_url_mi
     ]
 
 
+@pytest.mark.asyncio
+async def test_endpoint_only_review_lane_projects_without_cli_or_sdk() -> None:
+    """openrouter-review-lane task 2.3: the shipped openrouter-review agent has
+    no cli and no sdk block. Its models must still come from the provider map
+    (model_aliases.openrouter) and price against catalog rows, and the lane
+    stays dispatchable over its http transport with no CLI dispatch modes."""
+    from src.agents_config import get_provider_model_map, load_agents_config
+
+    lane_agent = next(a for a in load_agents_config() if a.name == "openrouter-review")
+    assert lane_agent.cli is None and lane_agent.sdk is None
+    provider = get_provider_model_map()["providers"]["openrouter"]
+    slugs = sorted(
+        {value["model"] if isinstance(value, dict) else value for value in provider.values()}
+    )
+    rows = [
+        {
+            "vendor": slug.split("/", 1)[0],
+            "model": slug,
+            "endpoint_kind": "openrouter",
+            "base_url": "https://openrouter.ai/api/v1",
+            "prompt_usd_per_mtok": 1.0,
+            "completion_usd_per_mtok": 2.0,
+            "refreshed_at": NOW.isoformat(),
+            "available": True,
+            "stale": False,
+        }
+        for slug in slugs
+    ]
+    service = VendorRegistryService(
+        _db({"model_catalog": rows}), agents=[lane_agent], now_fn=lambda: NOW
+    )
+
+    lane = (await service.list_vendors(archetype="reviewer", location="cloud"))[0]
+
+    assert lane["agent_id"] == "openrouter-review"
+    assert lane["vendor_type"] == "openrouter"
+    assert lane["dispatchable"] is True
+    assert lane["dispatch_modes"] == []
+    assert lane["cost"]["known"] is True
+    assert lane["cost"]["misses"] == []
+    assert sorted(model["model"] for model in lane["cost"]["models"]) == slugs
+
+
 @pytest.mark.asyncio
 async def test_ambiguous_catalog_model_makes_whole_projection_unknown_and_audits() -> None:
     exact = {
diff --git a/docs/decisions/README.md b/docs/decisions/README.md
index 84d431c3..dd5c7f7a 100644
--- a/docs/decisions/README.md
+++ b/docs/decisions/README.md
@@ -45,6 +45,7 @@ CI verifies the index is fresh by re-running `make decisions` and failing on any
 - [multiplayer-simulation](./multiplayer-simulation.md)
 - [observability](./observability.md)
 - [ownership-map](./ownership-map.md)
+- [parallel-infrastructure](./parallel-infrastructure.md)
 - [project-context-refresh](./project-context-refresh.md)
 - [project-context-refresh-orchestration](./project-context-refresh-orchestration.md)
 - [review-convergence-safety](./review-convergence-safety.md)
diff --git a/docs/decisions/model-routing.md b/docs/decisions/model-routing.md
index c4afd2e7..ac869d5b 100644
--- a/docs/decisions/model-routing.md
+++ b/docs/decisions/model-routing.md
@@ -5,6 +5,17 @@
 
 ---
 
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**Spend: fail-closed budget check at probe time (coordinator ceiling > 0 or key credit limit); record through a new POST /routing/spend; spool and replay when the coordinator is unreachable, with a new degradation code metered_spend_unrecorded** — The existing ceiling is advisory and LedgerService.record has no caller. Cloud workers are known to hit coordinator_projection_forbidden, so the key limit bounds spend while records sit in the spool.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D4)
+
+---
+
 ## 2026-09-24 — 2026-09-27-retain-static-model-until-routing-evidence
 
 ### Phase: Implementation
diff --git a/docs/decisions/parallel-infrastructure.md b/docs/decisions/parallel-infrastructure.md
new file mode 100644
index 00000000..28c3425f
--- /dev/null
+++ b/docs/decisions/parallel-infrastructure.md
@@ -0,0 +1,48 @@
+# Architectural Decisions — parallel-infrastructure
+
+> Reverse-chronological timeline of decisions tagged `architectural: parallel-infrastructure` in session-log Phase Entries.
+> Generated by `make decisions` — do not edit manually.
+
+---
+
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**A lane is an endpoint-only agents.yaml agent (openrouter-review, type openrouter), with its model in an archetypes.yaml provider** — This reuses tier-2.5 discovery and the coordinator's dispatch-configs without a second roster. Lane id = type, because converge keys results by vendor.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D1)
+
+---
+
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**Model-family diversity rule: reject anthropic-publisher lanes and skip duplicate families via vendor_families data** — Quorum is meant to measure independent model opinions. An OpenRouter lane in the claude_code or codex family would inflate it.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D2)
+
+---
+
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**API lanes verify through an authenticated zero-cost probe (GET /key or GET /models) that also checks the spend budget** — The existing Dispatchable Vendor Verification requirement already names this; today every API lane is probe_unsupported.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D3)
+
+---
+
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**Metered lanes fill quorum only (fill_target defaults to default_min_quorum)** — Prevents every host review from paying OpenRouter. The operator can tune it as data.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D5)
diff --git a/docs/decisions/skill-workflow.md b/docs/decisions/skill-workflow.md
index f49c0317..19ffcd22 100644
--- a/docs/decisions/skill-workflow.md
+++ b/docs/decisions/skill-workflow.md
@@ -49,6 +49,28 @@
 
 ---
 
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**agent_lane gains a CompositeOrchestrator (claude_code handshake plus include_lanes HTTP dispatch), and converge maps a mid-run vendor_unavailable/auth_required quorum loss to capability_unavailable** — This is the only path by which a cloud worker reaches quorum 2, and it makes 'exceeding the ceiling parks' true mid-run as well as at the probe.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D6)
+
+---
+
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**Retiring TRUST_POSTURE's cloud section and the policy entry is the last task, gated by an evidence file and a guard test** — The roadmap says the policy is removed once the lane passes in cloud. Live cloud evidence cannot run in CI, so it is an operator-run step with a recorded artifact.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D7)
+
+---
+
 ## 2026-10-09 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Review
diff --git a/openspec/changes/openrouter-review-lane/.review-ledger/ledger.json b/openspec/changes/openrouter-review-lane/.review-ledger/ledger.json
new file mode 100644
index 00000000..828e6045
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/.review-ledger/ledger.json
@@ -0,0 +1,400 @@
+{
+  "schema_version": 1,
+  "change_id": "openrouter-review-lane",
+  "items": [
+    {
+      "id": 1,
+      "status": "retired",
+      "axis": "resilience",
+      "type": "architecture",
+      "criticality": "high",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "fingerprint": "7e6360f7659f9cd1",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D6 makes HTTP lanes refuse any packet with tools_overflow:true, but PLAN_REVIEW packets for real changes in this repo routinely overflow: the round-1 packet for this very change is 320000/320000 chars with tools_overflow:true (branch diff vs origin/main spans ~420 files). In cloud, the OpenRouter lane would therefore return packet_requires_tools on round 1 of most reviews and the run parks capability_unavailable, so Acceptance Outcome 1 (quorum 2 in cloud) holds only for the small fixture used as evidence.",
+      "resolution": "operator adjudication 2026-10-12: verified fixed on disk; reopened by compact token heuristic (no fix_touched_file) - see gen-4 PLAN_REVIEW escalation",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 2,
+      "status": "retired",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "high",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/tasks.md",
+      "fingerprint": "46808a6d10102848",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "OpenAICompatAdapter.dispatch only calls CliVendorAdapter._parse_findings. The CLI ingest path also runs coerce_findings_payload, schema validation, stamp_judgment_ingest, line resolution, placeholder rejection and the empty_findings_too_fast floor. No task brings the HTTP lane onto that pipeline, yet the spec scenario 'Fast empty HTTP review does not count' and Acceptance Outcome 4 (findings conform to the schema and are synthesized like CLI lanes) depend on it. The traceability table maps Tool-less Lane Packet Refusal only to 1.5 and 3.8. Without judgment stamping, OpenRouter findings default to evidence_class=deterministic and count as blocking while CLI-lane findings do not, which skews consensus.",
+      "resolution": "operator adjudication 2026-10-12: verified fixed on disk; reopened by compact token heuristic (no fix_touched_file) - see gen-4 PLAN_REVIEW escalation",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 3,
+      "status": "retired",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "fingerprint": "7bf8fc1d2f272600",
+      "first_seen_round": 1,
+      "last_seen_round": 3,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The mid-run mapping fires when 'every failed lane's error_class is UNAVAILABLE or AUTH'. A verified lane can also produce no ReviewResult at all: it is filtered at dispatch by the family or fill rule, not discovered in the worker environment, or dispatch_and_wait returns [] when job_count == 0. In that case the failed set is empty, the condition is vacuously true, and converge() returns capability_unavailable with missing_lanes == [].",
+      "consensus_status": "unconfirmed",
+      "resolution": "operator adjudication 2026-10-12: resolved by ba681f63 (missing_lanes = verified - succeeded)"
+    },
+    {
+      "id": 4,
+      "status": "retired",
+      "axis": "correctness",
+      "type": "contract_mismatch",
+      "criticality": "medium",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "fingerprint": "bbe851f68eea7841",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The D9 evidence gate and the 'Cloud Single-Vendor Policy Retirement' requirement both require two lanes attributed in consensus-plan.json. The converge()/agent_lane path that autopilot PLAN_REVIEW must use never writes consensus-plan.json; only /parallel-review-plan does. converge() writes .review-cache/round-N/findings-<vendor>-plan.json plus the index, and agent_lane writes result.json without the consensus. As written, the evidence cannot be produced from the mandated path.",
+      "resolution": "operator adjudication 2026-10-12: verified fixed on disk; reopened by compact token heuristic (no fix_touched_file) - see gen-4 PLAN_REVIEW escalation",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 5,
+      "status": "retired",
+      "axis": "compatibility",
+      "type": "compatibility",
+      "criticality": "medium",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "fingerprint": "8a6152404f8d4f7c",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D1 gives openrouter-review location: cloud. In routing.yaml the only tier carrying endpoint_kind openrouter is metered-api with location: local, so RoutingPolicy.cost_tier('cloud', 'openrouter') returns None, and select_model excludes the candidate (model_routing/api.py around lines 577-600). The new agent becomes an inconsistent roster entry for the coordinator router.",
+      "resolution": "operator adjudication 2026-10-12: verified fixed on disk; reopened by compact token heuristic (no fix_touched_file) - see gen-4 PLAN_REVIEW escalation",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 6,
+      "status": "retired",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "medium",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "fingerprint": "a111a5046fcfc79e",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "discover_reviewers makes a single pass over sorted(all_vendors), so the 'roster order' that D5 relies on is not available. The D2 family rule and the D5 fill rule both depend on tier-1/2 selections, which can include vendors that sort after 'openrouter' (e.g. 'pi'). Implemented inside the existing loop, both rules would read an incomplete selection.",
+      "resolution": "operator adjudication 2026-10-12: verified fixed on disk; reopened by compact token heuristic (no fix_touched_file) - see gen-4 PLAN_REVIEW escalation",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 7,
+      "status": "retired",
+      "axis": "resilience",
+      "type": "resilience",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "fingerprint": "3777c42d6a736dfa",
+      "first_seen_round": 1,
+      "last_seen_round": 3,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D4 checks the budget only in the probe, which the supervisor runs once per batch against a $1.00 reservation. A dispatched child can then run up to 3 rounds in each of 3 review phases with packets of roughly 80k tokens, and every concurrently dispatched child sees the same remaining budget. When the coordinator ceiling is the only source (key limit null), nothing stops an overrun, so 'bounded before dispatch' does not hold.",
+      "consensus_status": "unconfirmed",
+      "resolution": "operator adjudication 2026-10-12: resolved by ba681f63, then moved to the dispatch layer (task 3.11)"
+    },
+    {
+      "id": 8,
+      "status": "retired",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "fingerprint": "8a11399a9a35f341",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D1 says the agent has 'no cli and no sdk block, the same shape as ocr-local', but ocr-local declares a cli block (agents.yaml around lines 452-468).",
+      "resolution": "operator adjudication 2026-10-12: verified fixed on disk; reopened by compact token heuristic (no fix_touched_file) - see gen-4 PLAN_REVIEW escalation",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 9,
+      "status": "retired",
+      "axis": "observability",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/tasks.md",
+      "fingerprint": "22e360157aaa6f9b",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "agent_lane.run_converge does not copy ConvergenceResult.missing_lanes into result.json. Task 6.4 expects the worker to park capability_unavailable with missing_lanes, but no task adds that field (or per-lane cost) to result.json.",
+      "resolution": "operator adjudication 2026-10-12: verified fixed on disk; reopened by compact token heuristic (no fix_touched_file) - see gen-4 PLAN_REVIEW escalation",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 10,
+      "status": "retired",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md",
+      "spec_file": "openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md",
+      "fingerprint": "4c7bcb281a057be6",
+      "first_seen_round": 2,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The round-1 fix adds normative behaviour to design D6 and tasks 3.8a/5.6: when the primary packet overflows, HTTP lanes get a separate tool-less packet (for plan reviews, scoped to openspec/changes/<id>/**) with its own sidecar, and they refuse only if that packet also overflows. The 'Tool-less Lane Packet Refusal' requirement still describes refusal of the round's packet only. No requirement or scenario defines the tool-less packet, so the spec no longer matches the design and tasks.",
+      "resolution": "operator adjudication 2026-10-12: verified fixed on disk; reopened by compact token heuristic (no fix_touched_file) - see gen-4 PLAN_REVIEW escalation",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 11,
+      "status": "retired",
+      "axis": "observability",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/specs/skill-workflow/spec.md",
+      "spec_file": "openspec/changes/openrouter-review-lane/specs/skill-workflow/spec.md",
+      "fingerprint": "f0d66f7c84167355",
+      "first_seen_round": 2,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Task 5.6 now has agent_lane persist ConvergenceResult.consensus to reviews/consensus-<review_type>.json, which the retirement evidence depends on. The 'Composite Agent-Lane Review' requirement does not state this. Also, IMPL_REVIEW and VAL_REVIEW share review_type 'implementation', so a VAL_REVIEW run would overwrite the IMPL_REVIEW consensus file.",
+      "resolution": "operator adjudication 2026-10-12: verified fixed on disk; reopened by compact token heuristic (no fix_touched_file) - see gen-4 PLAN_REVIEW escalation",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 12,
+      "status": "retired",
+      "axis": "readability",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/tasks.md",
+      "fingerprint": "92b8158fe22cb772",
+      "first_seen_round": 3,
+      "last_seen_round": 3,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The round-2 spec fix names the consensus file per phase (consensus-plan.json, consensus-impl-review.json, consensus-val-review.json). Task 5.6 and design D9 still say reviews/consensus-<review_type>.json, which gives consensus-implementation.json for both implementation phases, so they collide. The PLAN_REVIEW case, which the retirement evidence depends on, agrees in all three artifacts. Design D9 also cites 'task 5.5' for this write, but the work is in task 5.6.",
+      "resolution": "operator adjudication 2026-10-12: verified fixed on disk; reopened by compact token heuristic (no fix_touched_file) - see gen-4 PLAN_REVIEW escalation",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 13,
+      "status": "addressed",
+      "axis": "architecture",
+      "type": "contract_mismatch",
+      "criticality": "medium",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "fingerprint": "9560d906c79108e4",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D6 and tasks 3.8a/5.6 have converge() build a second, tool-less packet and 'pass both paths to dispatch_and_wait', and have dispatch_and_wait hand the tool-less body and its tools_overflow flag to OpenAI-compatible adapters. That needs a new optional dispatch_and_wait parameter (for both ReviewOrchestrator and the CompositeOrchestrator that converge() calls through _accepts_kwarg) and a new tools_overflow keyword on OpenAICompatAdapter.dispatch. Neither is named anywhere, and the cross-cutting interface contract table lists only include_lanes for dispatch_and_wait. Groups 3 and 5 implement the two sides of this interface in separate packages.",
+      "consensus_status": "unconfirmed",
+      "fix_touched_file": true,
+      "resolution": " | fix commit 3f9651df touched the cited file (verified on disk 2026-10-12)"
+    },
+    {
+      "id": 14,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/tasks.md",
+      "spec_file": "/home/user/agentic-coding-tools/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md",
+      "fingerprint": "760c0f61babee0d4",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The Metered Review Lane Spend Accounting requirement says every review an openrouter lane dispatches is recorded with spend_recorder.record(), and acceptance outcome 3 says every OpenRouter review is recorded against the ceiling. The only task that calls record() is 5.5, inside agent_lane's CompositeOrchestrator. D5 also selects the metered lane on a host with fewer than fill_target non-metered lanes (for example one CLI vendor and OPENROUTER_API_KEY in non-OpenBao mode). That review runs through ReviewOrchestrator.dispatch_and_wait from converge() or /parallel-review-*, never through agent_lane, so its spend is neither recorded nor spooled and no metered_spend_unrecorded degradation is raised.",
+      "consensus_status": "unconfirmed",
+      "fix_touched_file": true,
+      "resolution": " | fix commit 3f9651df touched the cited file (verified on disk 2026-10-12)"
+    },
+    {
+      "id": 15,
+      "status": "addressed",
+      "axis": "observability",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md",
+      "fingerprint": "23f6b8e0d50773bb",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The spec fixes work_unit_ref as '<change_id>:<review_type>:round-<n>'. IMPL_REVIEW and VAL_REVIEW both run with review_type 'implementation', so their rows get the same work_unit_ref and spend cannot be split by phase. This is the collision the round-2 fix already removed for the consensus files. Design D4 allows '<phase|review_type>'.",
+      "consensus_status": "unconfirmed",
+      "fix_touched_file": true,
+      "resolution": " | fix commit 3f9651df touched the cited file (verified on disk 2026-10-12)"
+    },
+    {
+      "id": 16,
+      "status": "addressed",
+      "axis": "architecture",
+      "type": "architecture",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "fingerprint": "50d0804bc4341887",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D4 and task 5.7 put the per-round budget re-check in converge(). converge() is vendor-agnostic: it receives only verified_lanes and an orchestrator, does not know which lanes are metered, has no coordinator-usage client, and has no way to keep one lane out of a dispatch except through orchestrator-specific kwargs. CompositeOrchestrator already knows the metered lanes and builds include_lanes, so the check fits there, or in ReviewOrchestrator.dispatch_and_wait next to the probe code. Keeping it in converge() widens the converge() signature with routing concerns.",
+      "consensus_status": "unconfirmed",
+      "fix_touched_file": true,
+      "resolution": "escalation fix 2026-10-12 (operator-directed): spend_context + dispatch-layer budget re-check (tasks 3.10, 3.11, 5.7; design D4 and interface row)"
+    },
+    {
+      "id": 17,
+      "status": "addressed",
+      "axis": "resilience",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/tasks.md",
+      "spec_file": "/home/user/agentic-coding-tools/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md",
+      "fingerprint": "1a9f013eec745723",
+      "first_seen_round": 2,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The round-1 fix moved spend_recorder.record() into ReviewOrchestrator.dispatch_and_wait, which gets only an optional work_unit_ref and no change id. When the write fails, the spec spools to 'openspec/changes/<change-id>/reviews/spend-spool.jsonl' (spec line 173) and replay runs per change id. A dispatch_and_wait call with work_unit_ref None, such as a one-shot /parallel-review-* run or any caller not yet updated, has no change id, so the failed row has nowhere to go. That metered spend is then neither recorded nor spooled, which is the gap the fix was meant to close.",
+      "consensus_status": "unconfirmed",
+      "fix_touched_file": true,
+      "resolution": "escalation fix 2026-10-12 (operator-directed): spend_context + dispatch-layer budget re-check (tasks 3.10, 3.11, 5.7; design D4 and interface row)"
+    },
+    {
+      "id": 18,
+      "status": "addressed",
+      "axis": "architecture",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "fingerprint": "2ee1c045a3ada4ee",
+      "first_seen_round": 2,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The new 'spend context' row in the interface contract table says dispatch_and_wait adds 'work_unit_ref: str | None' and that a missing value only drops the field from the row. It does not carry the change id that the D4 spool path (openspec/changes/<id>/reviews/spend-spool.jsonl) needs, and it does not say what happens to a metered lane when no context is given.",
+      "consensus_status": "unconfirmed",
+      "fix_touched_file": true,
+      "resolution": "escalation fix 2026-10-12 (operator-directed): spend_context + dispatch-layer budget re-check (tasks 3.10, 3.11, 5.7; design D4 and interface row)"
+    },
+    {
+      "id": 19,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/tasks.md",
+      "spec_file": "/home/user/agentic-coding-tools/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md",
+      "fingerprint": "da65bbb77b41c13f",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Since commit 62590065 a metered lane is refused (spend_context_missing) unless dispatch_and_wait receives a SpendContext, and converge() builds one only when its caller passes the new optional `phase`. The only caller that passes `phase` is agent_lane.py (task 5.6). The host inline converge() call in skills/autopilot/SKILL.md (PLAN_REVIEW fallback, about line 567) and the other host review phases pass no phase, and task 6.4 edits only the cloud review-section text. On a host where D5 selects the metered lane (one non-metered lane), every host converge() round therefore refuses the openrouter lane and ends capability_unavailable. The 'A host-path metered review is recorded' scenario can only pass in a unit test that calls dispatch_and_wait directly. Fix: add a task (or extend 6.4) that makes every host converge() caller in skills/autopilot/SKILL.md pass phase=<PLAN_REVIEW|IMPL_REVIEW|VAL_REVIEW>, or have converge() derive a SpendContext from change_id plus review_type and round when phase is None (accepting the IMPL/VAL collision only for that fallback).",
+      "consensus_status": "unconfirmed",
+      "fix_touched_file": true,
+      "resolution": "PLAN_FIX round 1 (gen 5): fix commit 6c7d08b3 touched the cited file; spec_file edit withheld (absolute allowed_paths scope bug)"
+    },
+    {
+      "id": 20,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/tasks.md",
+      "fingerprint": "f1c36ed5f4930b58",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Task 5.6 bullet 1 still says converge() 'passes work_unit_ref=<change_id>:<phase>:round-<n> to dispatch_and_wait (via _accepts_kwarg)'. After commit 62590065 the design's interface contract table, D4 and task 3.10 define the keyword as `spend_context: SpendContext(change_id, work_unit_ref)`. Groups 3 and 5 implement the two sides of this keyword in separate packages, so an implementer following 5.6 literally would pass a keyword that ReviewOrchestrator.dispatch_and_wait does not accept, and _accepts_kwarg would silently drop it, which leaves every metered dispatch spend_context_missing.",
+      "consensus_status": "unconfirmed",
+      "fix_touched_file": true,
+      "resolution": "PLAN_FIX round 1 (gen 5): fix commit 6c7d08b3 touched the cited file; spec_file edit withheld (absolute allowed_paths scope bug)"
+    },
+    {
+      "id": 21,
+      "status": "addressed",
+      "axis": "resilience",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "spec_file": "/home/user/agentic-coding-tools/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md",
+      "fingerprint": "089d8c3780a945cc",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The D4 per-round budget re-check reads metered_usd_used from GET /routing/usage, which counts only ledger rows. Rows that spooled because POST /routing/spend failed are invisible to it. D4 says 'the key's credit limit bounds spend while rows sit in the spool', but when the key limit is null and the coordinator ceiling is the only source, a worker whose GET succeeds while its POST fails (the partly-forbidden coordinator case D4 itself cites: coordinator_projection_forbidden) keeps passing the re-check while every round's spend spools. The bound then fails exactly in the degraded mode that motivated the spool. The Cost abuse bullet in Security and the Risks row on concurrent overspend do not cover it.",
+      "consensus_status": "unconfirmed",
+      "fix_touched_file": true,
+      "resolution": "PLAN_FIX round 1 (gen 5): fix commit 6c7d08b3 touched the cited file; spec_file edit withheld (absolute allowed_paths scope bug)"
+    }
+  ],
+  "compacted_at": "2026-10-13T00:47:58Z"
+}
diff --git a/openspec/changes/openrouter-review-lane/contracts/README.md b/openspec/changes/openrouter-review-lane/contracts/README.md
new file mode 100644
index 00000000..0db945d5
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/contracts/README.md
@@ -0,0 +1,14 @@
+# Contracts
+
+- `config/routing-cost-policy.schema.json` supersedes the archived
+  `declare-the-routing-cost-policy-the-router-obeys` ladder schema: it adds the
+  `metered-api-cloud` tier (design D1) and allows a fourth rung. The archive is
+  left unchanged as history.
+- `config/routing.schema.json` supersedes the
+  `implement-the-task-router-vendor-x-location-x-model` routing policy schema with
+  the same tier. That change's own contract is left as it was written.
+
+Both are what the deployed `agent-coordinator/routing.yaml` validates against
+(`tests/model_routing/test_routing_cost_policy.py`,
+`tests/model_routing/test_routing_policy_config.py`). When this change archives,
+`change_dir()` resolves the archived path.
diff --git a/openspec/changes/openrouter-review-lane/contracts/config/routing-cost-policy.schema.json b/openspec/changes/openrouter-review-lane/contracts/config/routing-cost-policy.schema.json
new file mode 100644
index 00000000..7218b104
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/contracts/config/routing-cost-policy.schema.json
@@ -0,0 +1,66 @@
+{
+  "$defs": {
+    "CostTier": {
+      "additionalProperties": false,
+      "properties": {
+        "id": {
+          "enum": [
+            "subscription-local",
+            "subscription-cloud",
+            "metered-api",
+            "metered-api-cloud"
+          ],
+          "title": "Id",
+          "type": "string"
+        },
+        "location": {
+          "enum": [
+            "local",
+            "cloud",
+            "unknown"
+          ],
+          "title": "Location",
+          "type": "string"
+        },
+        "endpoint_kinds": {
+          "items": {
+            "enum": [
+              "vendor-cli",
+              "vendor-sdk",
+              "openrouter",
+              "local"
+            ],
+            "type": "string"
+          },
+          "minItems": 1,
+          "title": "Endpoint Kinds",
+          "type": "array"
+        }
+      },
+      "required": [
+        "id",
+        "location",
+        "endpoint_kinds"
+      ],
+      "title": "CostTier",
+      "type": "object"
+    }
+  },
+  "additionalProperties": false,
+  "properties": {
+    "tiers": {
+      "items": {
+        "$ref": "#/$defs/CostTier"
+      },
+      "maxItems": 4,
+      "minItems": 3,
+      "title": "Tiers",
+      "type": "array"
+    }
+  },
+  "required": [
+    "tiers"
+  ],
+  "title": "CostPolicy",
+  "type": "object"
+}
diff --git a/openspec/changes/openrouter-review-lane/contracts/config/routing.schema.json b/openspec/changes/openrouter-review-lane/contracts/config/routing.schema.json
new file mode 100644
index 00000000..8301d400
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/contracts/config/routing.schema.json
@@ -0,0 +1,125 @@
+{
+  "$schema": "https://json-schema.org/draft/2020-12/schema",
+  "$id": "https://agentic-coding-tools.local/contracts/routing-policy-v1.schema.json",
+  "type": "object",
+  "additionalProperties": false,
+  "required": ["schema_version", "policy_version", "defaults", "rules", "fallback"],
+  "properties": {
+    "schema_version": {"const": 1},
+    "policy_version": {"type": "string", "pattern": "^[a-z0-9][a-z0-9.-]{0,63}$"},
+    "defaults": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["dispatch_mode", "phase_dispatch_modes"],
+      "properties": {
+        "dispatch_mode": {"$ref": "#/$defs/dispatchMode"},
+        "phase_dispatch_modes": {
+          "type": "object",
+          "additionalProperties": {"$ref": "#/$defs/dispatchMode"}
+        }
+      }
+    },
+    "rules": {
+      "type": "array",
+      "items": {"$ref": "#/$defs/rule"}
+    },
+    "cost_policy": {"$ref": "#/$defs/costPolicy"},
+    "fallback": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["location_order", "isolation_order", "dispatch_mode_order"],
+      "properties": {
+        "location_order": {
+          "type": "array",
+          "minItems": 1,
+          "uniqueItems": true,
+          "items": {"$ref": "#/$defs/location"}
+        },
+        "isolation_order": {
+          "type": "array",
+          "minItems": 1,
+          "uniqueItems": true,
+          "items": {"$ref": "#/$defs/isolation"}
+        },
+        "dispatch_mode_order": {
+          "type": "array",
+          "minItems": 1,
+          "uniqueItems": true,
+          "items": {"$ref": "#/$defs/dispatchMode"}
+        }
+      }
+    }
+  },
+  "$defs": {
+    "location": {"type": "string", "enum": ["local", "cloud", "unknown"]},
+    "isolation": {"type": "string", "enum": ["none", "worktree", "sandbox"]},
+    "dispatchMode": {"type": "string", "enum": ["review", "alternative", "quick", "sdk"]},
+    "costPolicy": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["tiers"],
+      "properties": {
+        "tiers": {
+          "type": "array",
+          "minItems": 3,
+          "maxItems": 4,
+          "prefixItems": [
+            {"$ref": "#/$defs/localSubscriptionTier"},
+            {"$ref": "#/$defs/cloudSubscriptionTier"},
+            {"$ref": "#/$defs/meteredTier"},
+            {"$ref": "#/$defs/meteredCloudTier"}
+          ]
+        }
+      }
+    },
+    "localSubscriptionTier": {"$ref": "#/$defs/costTier", "properties": {"id": {"const": "subscription-local"}}},
+    "cloudSubscriptionTier": {"$ref": "#/$defs/costTier", "properties": {"id": {"const": "subscription-cloud"}}},
+    "meteredTier": {"$ref": "#/$defs/costTier", "properties": {"id": {"const": "metered-api"}}},
+    "meteredCloudTier": {"$ref": "#/$defs/costTier", "properties": {"id": {"const": "metered-api-cloud"}}},
+    "costTier": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["id", "location", "endpoint_kinds"],
+      "properties": {
+        "id": {"enum": ["subscription-local", "subscription-cloud", "metered-api", "metered-api-cloud"]},
+        "location": {"$ref": "#/$defs/location"},
+        "endpoint_kinds": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"enum": ["vendor-cli", "vendor-sdk", "openrouter", "local"]}}
+      }
+    },
+    "rule": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["id", "when", "constrain"],
+      "properties": {
+        "id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,63}$"},
+        "when": {
+          "type": "object",
+          "additionalProperties": false,
+          "minProperties": 1,
+          "properties": {
+            "phase": {"type": "string"},
+            "archetype": {"type": "string"},
+            "scope": {"type": "string", "enum": ["read-only", "bounded-write", "broad-write"]},
+            "interactivity": {"type": "string", "enum": ["interactive", "headless"]},
+            "secret_need": {"type": "string", "enum": ["none", "brokered", "direct"]},
+            "min_duration_seconds": {"type": "integer", "minimum": 0},
+            "max_duration_seconds": {"type": "integer", "minimum": 0},
+            "min_parallelism": {"type": "integer", "minimum": 1},
+            "max_parallelism": {"type": "integer", "minimum": 1},
+            "repo_shape": {"type": "string", "enum": ["single-package", "monorepo", "unknown"]}
+          }
+        },
+        "constrain": {
+          "type": "object",
+          "additionalProperties": false,
+          "minProperties": 1,
+          "properties": {
+            "location": {"$ref": "#/$defs/location"},
+            "isolation": {"$ref": "#/$defs/isolation"},
+            "dispatch_mode": {"$ref": "#/$defs/dispatchMode"}
+          }
+        }
+      }
+    }
+  }
+}
diff --git a/openspec/changes/openrouter-review-lane/design.md b/openspec/changes/openrouter-review-lane/design.md
index d90c092a..99ee1d60 100644
--- a/openspec/changes/openrouter-review-lane/design.md
+++ b/openspec/changes/openrouter-review-lane/design.md
@@ -1,22 +1,454 @@
-<!-- SCAFFOLD: generated by plan-roadmap from roadmap `multiplayer-collaboration`, item `ri-22`.
-     Preliminary. Refine before implementation. -->
-
 # Design: OpenRouter review lane for cloud workers
 
+> Roadmap `multiplayer-collaboration`, item `ri-22`. Depends on `ri-21` (`dispatch-contract`, completed).
+
 ## Context
 
-Make API-based multi-vendor review available in cloud containers by registering OpenRouter-backed reviewer lanes (non-Anthropic model families) that dispatch over HTTP through the existing OpenAI-compatible adapter, need no vendor CLI, and count toward converge() quorum. Lanes are declared in the dispatch request's execution_profile and review_requirements from ri-21, verified by a dry invocation rather than credential probing, bounded by the existing spend ceiling, and their use retires the temporary cloud single-vendor review policy.
+Cloud containers run on the Claude subscription only. The only review lane a cloud
+worker can dispatch is the agent itself (served through `skills/autopilot/scripts/agent_lane.py`),
+so `converge()` cannot reach `min_quorum=2`. ri-21 made that honest — the review
+parks `capability_unavailable` or runs single-vendor under the temporary
+`cloud-container-single-vendor-2026-10-09` entry of
+`skills/parallel-infrastructure/review_quorum_policy.json`. That entry is backed by
+the "Review quorum in cloud containers (temporary)" section of `TRUST_POSTURE.md`.
 
-## Why this item exists
+Most of the HTTP machinery already exists. What is missing is the wiring that would
+make an OpenRouter lane count toward quorum:
 
-Restores the two-vendor review quorum for cloud workers at metered API cost instead of waiting on the GX10 review lane, and replaces a prompt-level policy exception with a configured, observable lane.
+| Existing piece | Location | Gap this change closes |
+|---|---|---|
+| `OpenAICompatAdapter` (tier 2.5), captures `generation_id` | `skills/parallel-infrastructure/scripts/openai_compat_adapter.py` | No authenticated no-op, no cost or token capture, no refusal of packets that need tools |
+| Tier-2.5 discovery for `endpoint_kind in {openrouter, local}` with `base_url` | `review_dispatcher.py` `from_config_dict` / `discover_reviewers` | No agent declares an OpenRouter `base_url`, so no lane exists. There is no model-family rule and no cost policy for metered lanes |
+| `--check-vendors --json` dry-probe verification (D10) | `review_dispatcher.py` `_probe_mode` | Every SDK or API lane is reported `probe_unsupported` and never verifies |
+| `routing_spend_ledger` + `ROUTING_MONTHLY_CEILING_USD` | `agent-coordinator/src/model_routing/{ledger,api}.py` | Advisory only. No client writes rows (`LedgerService.record` has no caller), and nothing checks the ceiling before dispatch |
+| Honest quorum guard (`verified_lanes`, `capability_unavailable`) | `skills/autopilot/scripts/convergence_loop.py` `converge()` | A lane that loses budget or auth mid-run surfaces as `quorum_lost`, not `capability_unavailable` |
+| Agent-as-lane driver | `skills/autopilot/scripts/agent_lane.py` | Hard-codes `verified_lanes=[claude_code]`, so it cannot add a second lane |
+| Lane ranking for `counting_lanes` | `skills/supervise/scripts/execution.py` `resolve_execution_profile.rank` | Infers the endpoint kind from `reason == probe_unsupported`, which breaks once API lanes verify |
 
-## Depends on
+## Goals / Non-goals
 
-- `ri-21`
+**Goals**
+- In a cloud container, `converge()` reaches quorum 2 with `claude_code` plus at least one
+  verified OpenRouter lane from a non-Anthropic model family.
+- Lane availability comes only from the dry probe. No worker reads environment variables
+  or credentials to discover lanes.
+- Metered spend is recorded for every review and bounded before dispatch. A lane that is
+  over budget is reported unverified, and the review parks `capability_unavailable`.
+- The temporary cloud single-vendor policy is retired after the lane has been shown to
+  work in cloud.
 
-## Open questions
+**Non-goals**
+- Inline or proxy-level budget enforcement, virtual keys, a LiteLLM gateway
+  (`add-coordinator-llm-gateway`).
+- A general usage-accounting store, transcript ingestion, or pricing tables
+  (`add-model-usage-ledger`). This change writes only to the existing `routing_spend_ledger`.
+- Using OpenRouter lanes for `alternative` or `quick` modes. `OpenAICompatAdapter.can_dispatch`
+  stays review-only.
+- Tool use for HTTP lanes. They review the packet text only (see D6).
+- The GX10 review lane, and adaptive model selection for review lanes.
 
-- Which capability do these requirements finally belong to?
-- What are the non-goals for this item?
-- Which decisions here need recording before implementation starts?
+## Decisions
+
+### D1 — A lane is an endpoint-only `agents.yaml` agent, with its model in `archetypes.yaml`
+
+The first lane is a new agent `openrouter-review`:
+
+- `type: openrouter`, `endpoint_kind: openrouter`, `base_url: https://openrouter.ai/api/v1`
+- `location: cloud`, `transport: http`, `trust_level: 1`, `capabilities: [discover]`
+- `archetypes: [reviewer]`, `vendor_credentials: [openrouter]`
+- no `cli` and no `sdk` block: the dispatcher builds only the tier-2.5 `OpenAICompatAdapter` for it
+  (`from_config_dict` already accepts an agent whose only dispatch surface is `endpoint_kind` + `base_url`)
+- no `api_key`. The lane never calls the coordinator under its own identity. Without a principal, key resolution falls back to the dispatcher's existing `OPENROUTER_API_KEY` default for `endpoint_kind: openrouter`, which works in non-OpenBao mode (cloud). On an OpenBao host the lane reports `auth_failed`. That is acceptable: hosts have CLI lanes, and D5 would not select it there. The agent schema has `additionalProperties: false`, so no agent-level `api_key_env` field is added.
+
+Its model comes from a new provider `openrouter` in `agent-coordinator/archetypes.yaml`. The
+`premium` tier is the review model; the `standard` and `economy` tiers are its fallbacks,
+which `_derived_tier_fallbacks` already reads. Lane id = `agent.type` = `openrouter`. This is
+the vendor string in `ReviewResult`, in the checkpoint index, in `execution_profile.lanes`,
+and in ConsensusSynthesizer attribution.
+
+More lanes are added the same way, each with its own `type` and provider key. Lane ids must be
+unique because `converge()` keys checkpointed results by `vendor`.
+
+`location: cloud` needs a matching cost tier. Today the only `routing.yaml` tier carrying
+`endpoint_kind: openrouter` is `metered-api` with `location: local`, so
+`RoutingPolicy.cost_tier("cloud", "openrouter")` returns `None` and `select_model` would exclude
+the agent. Group 2 therefore appends a tier `metered-api-cloud` (`location: cloud`,
+`endpoint_kinds: [openrouter]`) after `metered-api`. It is the last rung, so it never outranks a
+subscription tier, and the supervisor's `_tier_order()` (which reads only `endpoint_kinds`, first
+index wins) is unchanged. A group-2 test asserts `cost_tier("cloud", "openrouter")` is not `None`.
+
+*Alternatives considered*
+- Add `base_url` to `pi-local` and reuse the `pi` provider. Rejected: it couples the pi
+  harness's identity, credential principal and CLI-precedence rules to an HTTP reviewer, and a
+  `location: local` agent would serve a cloud lane.
+- Keep a separate lane file under `skills/parallel-infrastructure/`. Rejected: it would be a
+  second roster, which the principal registry rule forbids, and the coordinator's
+  `/agents/dispatch-configs` would not see it.
+
+### D2 — Model-family diversity rule
+
+A lane counts toward quorum only if it adds a model family:
+
+- The family of an OpenRouter lane is the publisher prefix of its primary model slug
+  (`<publisher>/<model>`).
+- The family of a CLI or SDK vendor comes from a new `vendor_families` map in
+  `review_quorum_policy.json`, for example `claude_code → anthropic`, `codex → openai`,
+  `antigravity → google`, `grok → xai`.
+
+Config load rejects an OpenRouter lane whose primary model or any fallback model has publisher
+`anthropic` (the agent is skipped with a logged reason). `discover_reviewers` skips a tier-2.5
+lane whose family is already contributed by a lane selected at tier 1 or 2, and records the
+reason `duplicate_model_family`. An Anthropic-family lane is reported with the reason
+`anthropic_family`. Both reasons appear in the `unverified` list of `--check-vendors --json`.
+
+A vendor missing from `vendor_families` has unknown family and is never treated as a duplicate.
+
+**Selection is two-pass.** Today `discover_reviewers` makes one pass over `sorted(all_vendors)`,
+so a tier-2.5 lane such as `openrouter` would be decided before tier-1/2 vendors that sort after
+it (for example `pi`). The family rule (D2) and the fill rule (D5) both read the complete
+non-metered selection, so discovery becomes:
+
+1. Pass 1 selects every tier-1 (CLI) and tier-2 (SDK) lane exactly as today.
+2. Pass 2 walks the remaining tier-2.5 candidates in `agents.yaml` roster order (the insertion
+   order of `openai_adapters`, not the sorted vendor order). It applies the Anthropic rule, the
+   duplicate-family rule against the pass-1 set, and then the fill rule (D5).
+
+Tests cover a non-metered vendor that sorts after the metered lane.
+
+*Trade-off accepted:* fallback models may belong to a different family from the primary
+model. The family check uses the primary model only, and `model_used` is recorded so audits
+can see what actually ran. This is preferred over forbidding cross-family fallbacks, which
+would make a single capacity error fatal to the lane.
+
+### D3 — Authenticated dry probe for API lanes
+
+`OpenAICompatAdapter.probe(api_key, transport, timeout=10)` makes one authenticated request
+that costs nothing:
+
+- `openrouter`: `GET {base_url}/key`, which returns the key's `limit`, `usage` and `limit_remaining`
+- `local`: `GET {base_url}/models`
+
+It returns `ProbeResult(ok, reason, budget)`. `reason` is one of `None`, `auth_failed`,
+`probe_timeout`, `endpoint_unreachable`, `spend_ceiling_exceeded`,
+`spend_ceiling_unverifiable`. `budget` holds numeric fields only.
+
+The response body is parsed in memory, and only the numeric budget fields are kept. Nothing
+from the response or the key is printed, logged, or returned.
+
+`_probe_mode` calls this for `dispatch_tier == "openai"` lanes in place of
+`probe_unsupported`. The key is resolved through the existing `ApiKeyResolver` path, which the
+Dispatchable Vendor Verification requirement already allows.
+
+The JSON report gains an additive per-mode `lane_kinds: {lane: endpoint_kind}` map. The supervisor uses it for ranking (D8).
+
+### D4 — Spend: bounded before dispatch, recorded after it
+
+**Bounded.** The probe (D3) also checks the budget. It reads up to two ceiling sources:
+
+1. The coordinator ceiling: `GET /routing/usage?window=month`. It counts when
+   `metered_ceiling_usd > 0` and the coordinator is reachable. Remaining budget is
+   `metered_ceiling_usd − metered_usd_used`.
+2. The OpenRouter key's own credit `limit`, from the probe response. It counts when the limit
+   is not null. Remaining budget is `limit_remaining`.
+
+How the probe decides:
+
+- **Verified:** at least one source is available, and every available source has remaining
+  budget of at least `review_reservation_usd`.
+- **`spend_ceiling_exceeded`:** an available source has less than that left.
+- **`spend_ceiling_unverifiable`:** no source is available (fail closed).
+
+`review_reservation_usd` is a single number in `review_quorum_policy.json` under
+`metered_lanes.review_reservation_usd`. The default is `1.00`. That is roughly one
+full-packet review round on a premium model, and it can be tuned as data.
+
+**Spend context.** Spooling needs a change id (the spool lives under
+`openspec/changes/<id>/reviews/`). So `dispatch_and_wait` takes a `SpendContext(change_id,
+work_unit_ref)` and refuses to dispatch a metered lane without one (`spend_context_missing`,
+`error_class = UNAVAILABLE`). Every metered dispatch therefore has a ledger row or a spool row.
+
+**Re-checked per round.** A probe-time check alone lets later rounds, and concurrently running
+children, spend past the coordinator ceiling. So every time `ReviewOrchestrator.dispatch_and_wait`
+is about to dispatch a metered lane (once per round, on every path, including
+`CompositeOrchestrator`, which calls it), it re-runs the same budget check the probe uses
+(task 3.6) against the current `metered_usd_used`. `GET /routing/usage` counts only ledger rows, so
+for the coordinator source the re-check also counts the `actual_usd` total of the change's
+unreplayed `reviews/spend-spool.jsonl` rows as used (remaining = `metered_ceiling_usd −
+metered_usd_used − spooled_usd`); the budget function takes the spooled total as an input, which
+the probe, having no change context, passes as 0. Without this, a worker whose usage read
+succeeds while its spend write fails (the partly-forbidden coordinator case below) would keep
+passing the re-check while every round's spend spools. The check lives in the dispatch layer, next to
+the probe code and the spend recording (task 3.10), not in `converge()`, which stays
+vendor-agnostic and knows nothing about which lanes are metered. A lane whose remaining budget is now below
+`review_reservation_usd` is not dispatched for that round; it is reported as a failed result with
+`error_class = UNAVAILABLE` (`spend_ceiling_exceeded`), which D7 turns into
+`capability_unavailable`. Concurrent children can still overlap by at most one reservation each
+between a check and the ledger row landing; the key's credit limit remains the hard bound, and
+this residual is listed under Risks.
+
+An unverified lane is left out of `execution_profile.lanes.review`. A dispatched child then
+parks `capability_unavailable` through the existing Honest Review Quorum path. It never drops
+to single-vendor review on its own.
+
+**Recorded.** Each request sets `"usage": {"include": true}`, so OpenRouter returns
+`usage.cost`. The adapter adds `prompt_tokens`, `completion_tokens`, `cost_usd` and
+`cost_source` (`reported`, or `estimated` when the response has no cost) to `ReviewResult`.
+
+A new `skills/parallel-infrastructure/scripts/spend_recorder.py` writes one row per review. The
+caller is `ReviewOrchestrator.dispatch_and_wait`, after each metered result, so every dispatch
+path records (a host `converge()` that selected the lane by D5, `/parallel-review-*`, and
+`agent_lane`'s `CompositeOrchestrator`). It sets `ReviewResult.spend_recorded`:
+
+- It posts to a new authenticated `POST /routing/spend` that calls the existing
+  `LedgerService.record`.
+- The row holds `vendor` = lane id, `model` = `model_used`, `endpoint_kind = openrouter`,
+  `generation_id`, the token counts, `actual_usd`, `tokens_estimated` (true when `cost_source`
+  is `estimated`), and `work_unit_ref = <change_id>:<phase>:round-<n>`.
+
+The same fields always go into the round checkpoint's vendor index, which is durable on the
+branch.
+
+If the coordinator write fails, the record is appended to
+`openspec/changes/<id>/reviews/spend-spool.jsonl`, and the worker records the degradation
+`metered_spend_unrecorded` (a new closed code). `spend_recorder.py replay --change-id <id>`
+posts the spooled rows idempotently, keyed by `generation_id`. The supervisor runs it during
+`apply`.
+
+The key's credit limit bounds spend while rows sit in the spool.
+
+*Alternatives considered*
+- Fail the review when the ledger write fails. Rejected: the coordinator is known to be
+  partly unreachable from cloud workers (`coordinator_projection_forbidden`), and the key
+  limit already bounds spend.
+- Wait for `add-model-usage-ledger`. Rejected: it is a draft with a much larger scope, and the
+  roadmap names the *existing* ceiling.
+
+### D5 — Metered lanes fill quorum, they do not add to it
+
+An agent with `endpoint_kind: openrouter` that is selected at tier 2.5 is a metered lane.
+`discover_reviewers` includes metered lanes only while the non-metered lanes it has selected
+number fewer than `metered_lanes.fill_target`. `fill_target` defaults to the policy file's
+`default_min_quorum`, which is 2. Metered lanes are added in `agents.yaml` roster order, during
+pass 2 of the two-pass selection (D2), until the target is reached.
+
+A host with two CLI lanes therefore pays nothing. A cloud container with only `claude_code`
+gets exactly one metered lane.
+
+This is a property of the roster that `--check-vendors` and `dispatch_and_wait` both apply, so
+the profile and the dispatch always agree.
+
+*Alternative considered:* always dispatch every configured lane (more reviewers). Rejected:
+every host review would start paying OpenRouter. The operator can raise `fill_target`.
+
+### D6 — HTTP lanes refuse packets that need tools
+
+HTTP lanes cannot read files. The `pi --no-tools` incident shows that a reviewer which cannot
+see the artifacts but still returns `{"findings": []}` manufactures false consensus.
+
+When the round's packet metadata has `tools_overflow: true`, `OpenAICompatAdapter.dispatch`
+returns `success=False`, `error_class=UNAVAILABLE`, `error="packet_requires_tools"` and makes
+no HTTP call. The existing Empty Or Blinded Review Is Not Success floor still applies to HTTP
+lanes.
+
+The packet metadata is the sidecar `build_review_packet` writes next to `packet_path`.
+`dispatch_and_wait` already receives `packet_path`. It reads the flag from the sidecar of the
+packet an OpenAI-compatible lane will receive and passes it to
+`OpenAICompatAdapter.dispatch(..., tools_overflow: bool = False)`.
+
+**Refusal must stay rare.** Refusal alone would make the lane useless in practice. Plan-review
+packets on long-lived branches routinely overflow: the round-1 PLAN_REVIEW packet for this change
+was 320000/320000 chars with `tools_overflow: true`, because the diff against `origin/main` spans
+about 420 files. To avoid this, `converge()` builds a second, tool-less packet for HTTP lanes
+whenever the primary packet overflows:
+
+- For `review_type == "plan"`, the tool-less packet's diff is limited to
+  `openspec/changes/<change-id>/**`. It includes the full text of `proposal.md`, `design.md`,
+  `tasks.md` and the spec deltas, all within the same `BUDGET_CHARS`. A plan review judges the plan
+  artifacts, and the unrelated branch diff is not needed for that.
+- For `review_type == "implementation"`, the tool-less packet keeps the existing rule-group
+  selection but drops the excluded and truncated files. Its sidecar lists them as `coverage.skipped`
+  (the blinded-review floor still applies).
+- The tool-less packet gets its own sidecar (`review-packet.toolless.meta.json`). An HTTP lane
+  refuses with `packet_requires_tools` only when this packet *also* has `tools_overflow: true`.
+  The CLI and handshake lanes keep the primary packet.
+- `converge()` passes the tool-less packet as a new optional keyword,
+  `dispatch_and_wait(..., toolless_packet_path: Path | None = None)`, only when the orchestrator
+  accepts it (the existing `_accepts_kwarg` check). Both `ReviewOrchestrator` and
+  `CompositeOrchestrator` accept it, and `CompositeOrchestrator` forwards it to
+  `ReviewOrchestrator`. When it is `None`, OpenAI-compatible lanes get the primary packet as today.
+
+A scenario covers a plan review whose full branch diff overflows: the HTTP lane receives a
+tool-less packet that fits, and it is dispatched. The D9 evidence run must use a change whose
+primary packet overflows, so that a small fixture cannot hide the problem.
+
+### D7 — Composite orchestrator in `agent_lane.py`, and honest mid-run loss
+
+`agent_lane.run_converge` gains `--verified-lanes` (repeatable). A dispatched child copies
+the values from its launch marker's `execution_profile.lanes.review`. A standalone run copies
+them from the `--check-vendors --json` output, which is the only allowed probe.
+
+It builds a `CompositeOrchestrator`. Each round it:
+
+- dispatches the `claude_code` handshake lane (unchanged), and
+- runs `ReviewOrchestrator.dispatch_and_wait(..., include_lanes=<verified lanes other than claude_code>)`
+  concurrently,
+
+and returns the combined `ReviewResult` list, with the checkpoint callback forwarded.
+`include_lanes` is a new optional filter on `dispatch_and_wait`; `None` keeps today's
+behaviour.
+
+The quorum policy is resolved with `verified_review_lanes = len(verified_lanes)` instead of the
+literal `1`.
+
+`claude_code` is always a verified lane inside `agent_lane`, because the running agent
+serves it. That is the premise of the module today. A `--verified-lanes claude_code` value
+is deduplicated.
+
+In `converge()`, `missing_lanes` is defined as the round's verified lanes minus the lanes that
+returned a successful result. When a round has fewer successful results than `min_quorum`,
+`missing_lanes` is non-empty, and every lane in `missing_lanes` has a recorded failure whose
+`error_class` is `UNAVAILABLE` or `AUTH` (budget exhausted, HTTP 402, key revoked, or
+`packet_requires_tools`), it returns `reason="capability_unavailable"` with those lanes. A
+verified lane that produced no result at all (no success and no recorded failure) is not a
+capability loss, so the condition is never vacuously true: that round stays `quorum_lost`, as
+does any other quorum loss.
+
+The autopilot SKILL already maps `capability_unavailable` to `runner.py park --kind
+capability_unavailable`.
+
+### D8 — Supervisor ranking uses `lane_kinds`
+
+`resolve_execution_profile.rank` reads the lane's endpoint kind from the report's
+`lane_kinds`. It falls back to the old `probe_unsupported` inference only when `lane_kinds` is
+absent, so older reports still rank. `openrouter` sorts by its position in the
+`cost_policy.tiers` ladder in `routing.yaml`.
+
+`ExecutionProfile` in `dispatch-request.schema.json` does not change: lanes stay plain lane-id strings.
+
+### D9 — Retiring the temporary policy needs evidence and is the last task
+
+The operator runs `/autopilot` on a fixture change in a cloud container whose environment has
+`OPENROUTER_API_KEY` as a secret and allows egress to `openrouter.ai`. The run is accepted
+only if the evidence file `openspec/changes/openrouter-review-lane/evidence/cloud-quorum-run.md`
+shows all of the following:
+
+- `PLAN_REVIEW` with `min_quorum=2`
+- two attributed lanes in `reviews/consensus-plan.json`. `converge()` itself never writes this
+  file (only `/parallel-review-plan` does), so `agent_lane.py` persists `ConvergenceResult.consensus`
+  to a per-phase file after each run (task 5.6): `consensus-plan.json`, `consensus-impl-review.json`
+  or `consensus-val-review.json`, so the two implementation phases do not collide. It sits alongside `quorum_received`
+  and the per-lane index already in `.review-cache/round-N/`
+- a `routing_spend_ledger` row, or a spool row, carrying the `generation_id`
+
+Only then does the final task:
+
+- delete the `cloud-container-single-vendor-2026-10-09` entry,
+- delete the `TRUST_POSTURE.md` section, and
+- update the `single_vendor_review` references in `skills/autopilot/SKILL.md`.
+
+The mechanism for per-environment exceptions (`policies[]` with a `sunset`) stays. Any future
+exception is data, never prose.
+
+Editing the prose of `TRUST_POSTURE.md` is checked against `posture_digest`, which covers the
+front-matter dispositions. If the digest also covers the body, the resulting gate
+re-evaluation is expected and is recorded in the session log.
+
+## Implementation notes (as built)
+
+These record where the build departs from, or sharpens, the decisions above. None of them
+changes behaviour beyond what the code and tests already pin.
+
+- **D1: no `vendor_credentials` on `openrouter-review`.** The OpenBao topology projection
+  rejects a keyless agent (no `api_key`, no principal) that declares vendor credentials, and the
+  dispatcher reads `vendor_credentials` only for agents that have a `principal_id`. Declaring
+  `[openrouter]` would therefore break the projection without changing key resolution. The
+  entry omits it, and the key resolves through the dispatcher's `OPENROUTER_API_KEY` default for
+  `endpoint_kind: openrouter`. There is no agent-level `api_key_env`. Coordinator-brokered
+  credentials (ri-23) replace this delivery later; nothing here anticipates that.
+- **D5: SDK lanes do not count toward `fill_target`.** An importable SDK package cannot be
+  verified by a dry probe (`probe_unsupported`). Counting it let the `claude-remote` and
+  `codex-remote` SDK lanes meet `fill_target` on the real roster, so the metered lane was always
+  skipped as `fill_target_met`. Only probe-verified lanes now fill quorum.
+- **Spend is recorded on empty findings.** A lane that returns a schema-valid result with no
+  findings still consumed tokens and was billed. Skipping the ledger row would undercount the
+  budget rule (D4), so the row is written whenever the call returned a cost, whatever the
+  findings count. This is intended.
+- **`phase_archetype` is null for IMPLEMENT.** Groups 1–6 were dispatched as direct parallel
+  worktree agents rather than through `build-dispatch`, so no archetype was resolved and the
+  loop state records `phase_archetype: null` for that phase. This is a record of how the run was
+  driven, not a defect in the routing code.
+- **Schemas and spec deltas are carried in this change.** The `metered-api-cloud` tier is added
+  in `contracts/config/routing-cost-policy.schema.json` and `contracts/config/routing.schema.json`
+  of this change, which supersede the archived routing-cost-policy copy and the task-router
+  change's copy (see `contracts/README.md`); those originals are untouched. The opening of the
+  provider-model-map key set to `openrouter` is a MODIFIED requirement in
+  `specs/configuration/spec.md`.
+- **Generation-id dedupe is atomic.** Migration 046 adds a partial unique index on
+  `routing_spend_ledger (generation_id) WHERE generation_id IS NOT NULL` and the RPC
+  `record_spend_once`, which inserts with `ON CONFLICT … DO NOTHING` and otherwise returns the
+  existing row. `POST /routing/spend` calls it through `ledger.record_once`, so concurrent
+  duplicates write exactly one row (201 for the writer, 200 for the rest).
+- **Follow-up: task-router resolver ineligibility.** `model_routing/resolver.py` excludes
+  `openrouter-review` as `lane:dispatch-mode-ineligible`, because the agent has no dispatch modes.
+  The review dispatcher, not the task router, selects review lanes, so this change does not
+  alter it. Making endpoint-only agents eligible to the resolver is left as a follow-up.
+
+## Cross-cutting interface contracts
+
+| Contract | Change | Compatibility |
+|---|---|---|
+| `ReviewResult` | adds `prompt_tokens`, `completion_tokens`, `cost_usd`, `cost_source`, `spend_recorded` (all optional, default `None`) | additive, existing callers unaffected |
+| `--check-vendors --json` | adds `modes.<mode>.lane_kinds`; API lanes may now be `verified` or carry the new reasons | additive; consumers ignore unknown keys |
+| `review_quorum_policy.json` | adds `vendor_families` and `metered_lanes.{fill_target, review_reservation_usd}` | additive; `resolve_quorum_policy` ignores them |
+| `dispatch_and_wait` (`ReviewOrchestrator`, `CompositeOrchestrator`) | adds optional `include_lanes` and `toolless_packet_path: Path \| None = None` (D6) | defaults keep behaviour; `converge()` passes `toolless_packet_path` only when `_accepts_kwarg` reports it |
+| `OpenAICompatAdapter.dispatch` | adds keyword `tools_overflow: bool = False` (D6) | default keeps behaviour |
+| `dispatch_and_wait` / `converge()` spend context | `dispatch_and_wait` adds optional `spend_context: SpendContext \| None = None`, a frozen dataclass `{change_id: str, work_unit_ref: str}`; `converge()` adds optional `phase: str \| None = None` and passes `SpendContext(change_id, "<change_id>:<phase>:round-<n>")` when `phase` is set; `/parallel-review-*` passes `SpendContext(change_id, "<change_id>:<review_type>:oneshot")` (D4) | non-metered lanes ignore it, so defaults keep behaviour; a metered lane with no `spend_context` is not dispatched and returns a failed result with `error_class = UNAVAILABLE`, reason `spend_context_missing`, so its spend can never go unrecorded and unspooled |
+| `dispatch-result.schema.json` `Degradation.code` | adds enum value `metered_spend_unrecorded` | additive enum; writers older than this change never emit it |
+| Coordinator HTTP | adds `POST /routing/spend` (X-API-Key auth, Pydantic `extra="forbid"`, `actual_usd >= 0`, `generation_id` idempotency) | new route |
+
+## Security
+
+- **Credentials:** the OpenRouter key is read only through `ApiKeyResolver`. In cloud that
+  means the `OPENROUTER_API_KEY` environment secret in non-OpenBao mode; on hosts it means
+  OpenBao `vendor_credentials: [openrouter]`. The probe and dispatch never log headers or
+  response bodies. A sentinel test (the existing Dispatchable Vendor Verification scenario,
+  extended to `OPENROUTER_API_KEY`) checks this.
+- **Data egress:** packets, which hold diffs and spec excerpts, are sent to a third party
+  (OpenRouter and the upstream provider). This is acceptable for this repository, which is
+  public on GitHub. For any other repository it is opt-in, because the lane exists only if an
+  agent with `endpoint_kind: openrouter` and `base_url` is configured.
+- **New endpoint:** `POST /routing/spend` requires `X-API-Key`. Its input is validated, and it
+  accepts only the fields of the ledger row.
+- **Cost abuse:** the ceiling check before dispatch, plus the key's own credit limit, plus
+  `fill_target`.
+
+## Risks
+
+| Risk | Mitigation |
+|---|---|
+| The cloud environment's egress policy blocks `openrouter.ai` | The probe reports `endpoint_unreachable`, the review parks honestly, and the setup doc names the allowlist entry |
+| TLS through the agent proxy fails with stdlib `urllib` | The transport uses the default SSL context, which honours `SSL_CERT_FILE`; the cloud setup doc points it at the proxy CA bundle |
+| OpenRouter changes the `/key` or `usage.cost` shapes | The transport is injectable and tests pin the parsed fields. The probe fails closed (`spend_ceiling_unverifiable`) on an unexpected shape |
+| The model slug in the `openrouter` provider is retired | `_derived_tier_fallbacks` provides fallbacks; a slug error is classified and the next model is tried |
+| `claude --version` fails inside the container, so the profile omits `claude_code` and the fill rule tries to select a second metered lane | The roster has one metered lane, so at most one is selected. `agent_lane` still counts `claude_code` (D7) |
+| The supervisor runs `--check-vendors` in a different environment class than the worker, for example a host supervisor with a cloud worker | This is inherited from ri-21 (the profile is resolved by the supervisor). The worker parks honestly if the profile lists lanes it cannot dispatch, through the mid-run mapping in D7. Correcting the supervisor's environment is out of scope |
+| Spool rows are never replayed | `metered_spend_unrecorded` is a visible degradation on the dispatch result, and `apply` runs replay |
+
+- **Concurrent overspend under the coordinator ceiling alone.** The per-round re-check (D4)
+  narrows it to at most one `review_reservation_usd` per concurrently running child; a key
+  credit limit removes it.
+- **Spooled spend in other workers.** The re-check counts only the current change's spool.
+  Rows spooled by other workers stay invisible to the coordinator ceiling until `apply` replays
+  them. A key credit limit bounds this; the cloud setup doc (task 7.1) recommends one.
+
+## Open questions (for the operator, recorded as decisions with defaults)
+
+1. **Ceiling when the coordinator ceiling is unset.** The default fails closed and requires
+   either `ROUTING_MONTHLY_CEILING_USD > 0` or an OpenRouter key with a credit limit (D4).
+   The alternative is to treat an unset ceiling as unlimited.
+2. **Fill vs. supplement.** The default dispatches metered lanes only to fill quorum (D5).
+   The alternative is to always dispatch them.
+3. **Initial review model** for the `openrouter` provider `premium` tier. It must be a
+   non-Anthropic publisher, and preferably a family not already served by a host CLI
+   (codex → openai, antigravity → google, grok → xai). It is chosen at implementation from
+   the live OpenRouter catalog and recorded in `archetypes.yaml` with its source URL.
diff --git a/openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g1.json b/openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g1.json
new file mode 100644
index 00000000..ee131ad9
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g1.json
@@ -0,0 +1,35 @@
+{
+  "attempt": 1,
+  "branch": "openspec/openrouter-review-lane",
+  "change_id": "openrouter-review-lane",
+  "degradations": [
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "project-state submit returned forbidden",
+      "phase": "INIT"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate proposal_approval decision posture_block",
+      "phase": "PLAN"
+    }
+  ],
+  "dispatch_id": "batch-d8913c4d8e973cd7940e2d09:ri-22:attempt-1",
+  "evidence": {
+    "commit": "c631f23f64fcf6af4c3e6e15d70f2d5fe7ff7a0c",
+    "loop_state_digest": "66379bb4cc4760e8e530cb7dcc925348ce5a1dff2b605c3bf27597322b0434ea",
+    "loop_state_path": "openspec/changes/openrouter-review-lane/loop-state.json"
+  },
+  "host_id": "machine-dc39bf1e25efdf45",
+  "lease_generation": 1,
+  "outcome": "parked",
+  "parked": {
+    "deadline": null,
+    "gate": "proposal_approval",
+    "kind": "pending_gate",
+    "reason": "Approve this OpenSpec proposal and begin implementation?",
+    "resume_hint": "answer gate proposal_approval through the resume request's gate_answer"
+  },
+  "schema_version": 2,
+  "worktree_ref": "openrouter-review-lane"
+}
diff --git a/openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g2.json b/openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g2.json
new file mode 100644
index 00000000..d61c4960
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g2.json
@@ -0,0 +1,39 @@
+{
+  "attempt": 1,
+  "branch": "openspec/openrouter-review-lane",
+  "change_id": "openrouter-review-lane",
+  "degradations": [
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "project-state submit returned forbidden",
+      "phase": "INIT"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate proposal_approval decision posture_block",
+      "phase": "PLAN"
+    }
+  ],
+  "dispatch_id": "batch-d8913c4d8e973cd7940e2d09:ri-22:attempt-1",
+  "evidence": {
+    "commit": "d6c49b1eaace9ff5f232c0c477f516a3966cbcaa",
+    "loop_state_digest": "4e58211e36b7abf52f53a5ff200d4cfa55a75af35570fcf137f83a3558bfe458",
+    "loop_state_path": "openspec/changes/openrouter-review-lane/loop-state.json"
+  },
+  "host_id": "machine-dc39bf1e25efdf45",
+  "lease_generation": 2,
+  "outcome": "parked",
+  "parked": {
+    "classifier_reason": "Applying a supervisor-relayed gate approval (cross-session message, no launch marker) was classified as an auto-mode bypass",
+    "command": "runner.py gate-answer openrouter-review-lane --gate proposal_approval --decision approved --approval-ref gate-decision:2b09fbd1-b6b9-49e7-8bda-b724b22f17d6",
+    "deadline": null,
+    "gate": null,
+    "kind": "permission_blocked",
+    "reason": "permission denied for Bash under rule auto mode classifier: [Auto-Mode Bypass]",
+    "resume_hint": null,
+    "rule": "auto mode classifier: [Auto-Mode Bypass]",
+    "tool": "Bash"
+  },
+  "schema_version": 2,
+  "worktree_ref": "openrouter-review-lane"
+}
diff --git a/openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g3.json b/openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g3.json
new file mode 100644
index 00000000..c6014a4e
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g3.json
@@ -0,0 +1,50 @@
+{
+  "attempt": 1,
+  "branch": "openspec/openrouter-review-lane",
+  "change_id": "openrouter-review-lane",
+  "degradations": [
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "project-state submit returned forbidden",
+      "phase": "INIT"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate proposal_approval decision posture_block",
+      "phase": "PLAN"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate proposal_approval decision auto (gen 3)",
+      "phase": "PLAN"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "vendor=claude_code; cloud policy cloud-container-single-vendor-2026-10-09 min_quorum 1",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate escalate_resume decision posture_block",
+      "phase": "ESCALATE"
+    }
+  ],
+  "dispatch_id": "batch-d8913c4d8e973cd7940e2d09:ri-22:attempt-1",
+  "evidence": {
+    "commit": "c72e91158b0ac8685f444a2b31393ad1a7754a13",
+    "loop_state_digest": "f209ef7c01c21cc7d7a79bdbe08aa7196cc338faf23bd9a5fced21eda744d60b",
+    "loop_state_path": "openspec/changes/openrouter-review-lane/loop-state.json"
+  },
+  "host_id": "machine-dc39bf1e25efdf45",
+  "lease_generation": 3,
+  "outcome": "parked",
+  "parked": {
+    "deadline": null,
+    "gate": "escalate_resume",
+    "kind": "pending_gate",
+    "reason": "Has this escalation been resolved? Resume the loop?",
+    "resume_hint": "answer gate escalate_resume through the resume request's gate_answer"
+  },
+  "schema_version": 2,
+  "worktree_ref": "openrouter-review-lane"
+}
diff --git a/openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g6.json b/openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g6.json
new file mode 100644
index 00000000..4e9ae71b
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g6.json
@@ -0,0 +1,74 @@
+{
+  "attempt": 1,
+  "branch": "openspec/openrouter-review-lane",
+  "change_id": "openrouter-review-lane",
+  "degradations": [
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "project-state submit returned forbidden",
+      "phase": "INIT"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate proposal_approval decision posture_block",
+      "phase": "PLAN"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate proposal_approval decision auto (gen 3)",
+      "phase": "PLAN"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "vendor=claude_code; cloud policy cloud-container-single-vendor-2026-10-09 min_quorum 1",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate escalate_resume decision posture_block",
+      "phase": "ESCALATE"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "gen 4 re-entry: vendor=claude_code; cloud policy cloud-container-single-vendor-2026-10-09 min_quorum 1",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "gen 4: audit sink reported failure for gate escalate_resume decision posture_block",
+      "phase": "ESCALATE"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "re-entry after ledger adjudication: vendor=claude_code; cloud policy min_quorum 1",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate escalate_resume decision posture_block (2026-10-13)",
+      "phase": "ESCALATE"
+    }
+  ],
+  "dispatch_id": "batch-d8913c4d8e973cd7940e2d09:ri-22:attempt-1",
+  "evidence": {
+    "commit": "f6f819bd96fed5823e35791dc88f5b8e9584b423",
+    "loop_state_digest": "6a5c86d32c967ab8c28dd9674b14b539e8427ac859ba721c33e12612a79ffae1",
+    "loop_state_path": "openspec/changes/openrouter-review-lane/loop-state.json"
+  },
+  "host_id": "machine-dc39bf1e25efdf45",
+  "lease_generation": 6,
+  "outcome": "parked",
+  "parked": {
+    "deadline": null,
+    "gate": null,
+    "kind": "capability_unavailable",
+    "missing_lanes": [
+      "openrouter"
+    ],
+    "phase": "PLAN_REVIEW",
+    "reason": "check-vendors verifies only claude_code; no OpenRouter HTTP review lane exists yet (openrouter-review agent, adapter probe and CompositeOrchestrator are this change's unimplemented tasks 1-6). OPENROUTER_API_KEY present and openrouter.ai allow-listed, but no dispatcher path consumes them. Quorum 2 requested by supervisor; refusing to review below it.",
+    "resume_hint": null
+  },
+  "schema_version": 2,
+  "worktree_ref": "openrouter-review-lane"
+}
diff --git a/openspec/changes/openrouter-review-lane/loop-state.json b/openspec/changes/openrouter-review-lane/loop-state.json
new file mode 100644
index 00000000..291cf5bb
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/loop-state.json
@@ -0,0 +1,332 @@
+{
+  "schema_version": 6,
+  "change_id": "openrouter-review-lane",
+  "current_phase": "IMPL_REVIEW",
+  "iteration": 0,
+  "total_iterations": 13,
+  "max_phase_iterations": 3,
+  "findings_trend": [],
+  "blocking_findings": [],
+  "vendor_availability": {},
+  "packages_status": {},
+  "package_authors": {},
+  "implementation_strategy": {},
+  "memory_ids": [],
+  "handoff_ids": [
+    "local:gatekeeper-openrouter-review-lane-20261010T1050Z",
+    "746039a0-a579-4a6e-83a7-662068674762",
+    "local:plan-review-openrouter-review-lane-20261011T1419Z",
+    "local:plan-review-openrouter-review-lane-20261012T0247Z",
+    "local:plan-review-openrouter-review-lane-20261013T0048Z",
+    "local:implement-openrouter-review-lane-20261021T1611Z",
+    "local:impl-iterate-openrouter-review-lane-20261021T1650Z"
+  ],
+  "phase_history": [
+    {
+      "at": "2026-10-10T10:51:34.903189+00:00",
+      "outcome": "proceed_with_review",
+      "phase": "GATEKEEPER"
+    },
+    {
+      "at": "2026-10-11T14:08:18.140652+00:00",
+      "outcome": "complete",
+      "phase": "PLAN_ITERATE"
+    },
+    {
+      "at": "2026-10-11T14:20:20.952004+00:00",
+      "outcome": "max_iter",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "at": "2026-10-12T02:48:17.763162+00:00",
+      "outcome": "max_iter",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "at": "2026-10-13T00:52:14.849282+00:00",
+      "outcome": "max_iter",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "at": "2026-10-21T14:35:56.595019+00:00",
+      "outcome": "operator_accept",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "at": "2026-10-21T16:11:23.888216+00:00",
+      "outcome": "complete",
+      "phase": "IMPLEMENT"
+    },
+    {
+      "at": "2026-10-21T16:27:12.638292+00:00",
+      "outcome": "complete",
+      "phase": "IMPL_ITERATE"
+    }
+  ],
+  "last_handoff_id": "local:impl-iterate-openrouter-review-lane-20261021T1650Z",
+  "started_at": "2026-10-10T10:48:36.099038+00:00",
+  "phase_started_at": "2026-10-21T16:27:12.857478+00:00",
+  "previous_phase": "PLAN_REVIEW",
+  "escalation_reason": "PLAN_REVIEW transitioned to ESCALATE via outcome 'max_iter'",
+  "val_review_enabled": true,
+  "cli_review_enabled": true,
+  "error": null,
+  "phase_archetype": null,
+  "force": false,
+  "gate_signals": {},
+  "gate_verdict": "proceed_with_review",
+  "gate_decisions": [
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "proposal_approval",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "PLAN",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'proposal_approval' parked: trust posture disposition is block (unscoped fallback: auto requires a launch marker carrying a roadmap_approval_ref)",
+      "recorded_at": "2026-10-10T10:51:43.189455+00:00",
+      "resolution": "posture_block",
+      "scope": "unscoped",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "auto",
+      "default_action": null,
+      "disposition": "auto",
+      "gate": "proposal_approval",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "PLAN",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'proposal_approval' auto-approved by trust posture",
+      "recorded_at": "2026-10-10T13:35:48.613149+00:00",
+      "resolution": "auto",
+      "scope": "roadmap_approval",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": null,
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "PLAN",
+      "posture_present": false,
+      "provenance": {
+        "approval_ref": "gate-decision:a0408bee-2afc-4b03-8a84-b6daaf11326d",
+        "source": "human"
+      },
+      "reason": "gate 'escalate_resume' approved by the operator",
+      "recorded_at": "2026-10-11T13:50:04.379017+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-11T14:20:29.178053+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": null,
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "approval_ref": "gate-decision:4eec73f8-9f8f-46a5-935c-7358a8dcd984",
+        "source": "human"
+      },
+      "reason": "gate 'escalate_resume' approved by the operator",
+      "recorded_at": "2026-10-12T02:39:42.726118+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-12T02:48:21.393995+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator approved in worker session 2026-10-13 (no ref); fixes in 62590065",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "approval_ref": null,
+        "source": "human"
+      },
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator approved in worker session 2026-10-13 (no ref); fixes in 62590065",
+      "recorded_at": "2026-10-13T00:41:40.423464+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-13T00:52:18.981212+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": null,
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "approval_ref": "gate-decision:666c85e5-7ab8-4df2-b225-ed944cadbad7",
+        "source": "human"
+      },
+      "reason": "gate 'escalate_resume' approved by the operator",
+      "recorded_at": "2026-10-15T11:13:56.724300+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": null,
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "PLAN_REVIEW",
+      "posture_present": false,
+      "provenance": {
+        "approval_ref": "gate-decision:ad5b460d-fdc9-4f7a-a15d-3be473dbcb29",
+        "source": "human"
+      },
+      "reason": "gate 'escalate_resume' approved by the operator",
+      "recorded_at": "2026-10-21T14:35:56.594832+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    }
+  ],
+  "pending_gate": null,
+  "goal_gate": null,
+  "park": null,
+  "degradations": [
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "project-state submit returned forbidden",
+      "phase": "INIT"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate proposal_approval decision posture_block",
+      "phase": "PLAN"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate proposal_approval decision auto (gen 3)",
+      "phase": "PLAN"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "vendor=claude_code; cloud policy cloud-container-single-vendor-2026-10-09 min_quorum 1",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate escalate_resume decision posture_block",
+      "phase": "ESCALATE"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "gen 4 re-entry: vendor=claude_code; cloud policy cloud-container-single-vendor-2026-10-09 min_quorum 1",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "gen 4: audit sink reported failure for gate escalate_resume decision posture_block",
+      "phase": "ESCALATE"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "re-entry after ledger adjudication: vendor=claude_code; cloud policy min_quorum 1",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink reported failure for gate escalate_resume decision posture_block (2026-10-13)",
+      "phase": "ESCALATE"
+    },
+    {
+      "code": "single_vendor_review",
+      "phase": "IMPL_REVIEW",
+      "detail": "vendor=claude_code"
+    }
+  ]
+}
diff --git a/openspec/changes/openrouter-review-lane/plan-findings.md b/openspec/changes/openrouter-review-lane/plan-findings.md
new file mode 100644
index 00000000..feb3f239
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/plan-findings.md
@@ -0,0 +1,57 @@
+# Plan Findings: openrouter-review-lane
+
+Produced by `/iterate-on-plan` (autopilot PLAN_ITERATE, architect archetype), 2026-10-11.
+Threshold: medium. Baseline: `openspec validate --strict` passed, but the change was still
+the plan-roadmap scaffold.
+
+The analysis ran inline. This harness exposes no sub-agent (`Task`/`Agent`) tool, so the
+parallel Explore analysts were not dispatched (recorded as a `skill-procedure-deviation`
+decision in `session-log.md`).
+
+## Iteration 1 — scaffold to plan
+
+| # | Type | Criticality | Description | Resolution |
+|---|------|-------------|-------------|------------|
+| 1 | completeness | critical | `proposal.md` had no Why, What Changes, or Impact sections | Rewrote `proposal.md` with all three, plus Non-goals |
+| 2 | consistency | critical | The spec delta sat under the placeholder capability `multiplayer-collaboration` (the guide capability), and the touched capabilities had no deltas | Removed the placeholder. Added deltas for `parallel-infrastructure`, `skill-workflow`, `supervise`, `model-routing` |
+| 3 | testability | critical | Every scenario was "WHEN implemented THEN <outcome restated>", so none could be verified | Rewrote as concrete WHEN/THEN with injected transports, fixture values, and exact reasons and codes |
+| 4 | feasibility | critical | `tasks.md` was a generic five-item checklist that traced to no requirement | Seven task groups with Files, Depends, TDD ordering, and a traceability table |
+| 5 | consistency | high | The new behaviour duplicated existing requirements (Dispatchable Vendor Verification, OpenAI-Compatible Dispatcher Discovery, Honest Review Quorum, Execution Profile) instead of modifying them | Converted to MODIFIED deltas carrying the full requirement text |
+| 6 | feasibility | high | The plan assumed an enforced spend ceiling. In fact `ROUTING_MONTHLY_CEILING_USD` is advisory and `LedgerService.record` has no caller | D4: budget checked during the probe (coordinator ceiling or key limit), a new `POST /routing/spend`, and a spool with replay |
+| 7 | feasibility | high | API lanes are always `probe_unsupported`, so an OpenRouter lane could never verify | D3: authenticated zero-cost probe (`GET /key`, `GET /models`) |
+| 8 | feasibility | high | `agent_lane.py` hard-codes a single lane, so cloud `converge()` cannot reach quorum 2 | D7: `CompositeOrchestrator` with `--verified-lanes` |
+| 9 | correctness | high | Lane identity: `converge()` keys results by `vendor`. Two lanes sharing one id would collide, and an Anthropic-family OpenRouter model would fake diversity | D1 lane id = `type`; D2 family rule (reject `anthropic`, skip duplicate families) |
+| 10 | security | high | An HTTP lane cannot read files. An overflowing packet would give a blinded "no findings" vote (the `pi --no-tools` precedent) | D6: refuse with `packet_requires_tools`; the blinded-review floor applies |
+| 11 | performance | medium | Adding a metered lane to the shared roster would make every host review pay OpenRouter | D5: metered lanes fill quorum only (`fill_target`) |
+| 12 | consistency | medium | Supervisor `rank()` infers the endpoint kind from `probe_unsupported`, which is wrong once API lanes verify | D8: additive `lane_kinds` in the report, with a fallback |
+| 13 | completeness | medium | A mid-run budget or auth loss returned `quorum_lost`, which contradicts "parks with capability_unavailable" | Honest Review Quorum MODIFIED: mapping for `vendor_unavailable` and `auth_required` |
+| 14 | scope | medium | Overlap with the draft changes `add-coordinator-llm-gateway` and `add-model-usage-ledger` | Explicit non-goals. Writes only the existing `routing_spend_ledger` |
+| 15 | completeness | medium | Retiring the policy had no evidence gate, so TRUST_POSTURE could be edited before the lane worked | D9 plus a guard test that requires `evidence/cloud-quorum-run.md` |
+| 16 | consistency | medium | D1 initially gave the agent an `api_key_env` field, which the agent schema rejects (`additionalProperties: false`) | Removed it; the dispatcher's `OPENROUTER_API_KEY` default for `openrouter` covers it |
+
+## Iteration 2 — self-review of the rewritten plan
+
+| # | Type | Criticality | Description | Resolution |
+|---|------|-------------|-------------|------------|
+| 1 | clarity | medium | `local` API lanes had no verification rule once budget conditions were added | Spec: a `local` lane verifies on probe success alone |
+| 2 | assumptions | medium | `review_reservation_usd` had no default | D4: default `1.00`, kept as data |
+| 3 | completeness | medium | `claude_code` verification inside `agent_lane` was left implicit, and the failure mode of a missing `claude` binary was not covered | D7: the running agent is always verified; risk row added |
+| 4 | assumptions | medium | Supervisor and worker environment classes can differ (inherited from ri-21) | Risk row added; out of scope with the reason stated |
+
+## Iteration 3 — settle check
+
+No finding at or above medium remains. Residual findings below the threshold:
+
+| # | Type | Criticality | Description | Disposition |
+|---|------|-------------|-------------|-------------|
+| 1 | parallelizability | low | No `work-packages.yaml`. Dependencies and write scopes are in `tasks.md` only | Generate it at `/implement-feature` if the coordinated tier is selected |
+| 2 | security | low | Any agent holding a coordinator API key can post spend rows, which could exhaust the ceiling and deny the lane | Accepted. The route is authenticated and audited, and the harm is denial of a metered lane only |
+| 3 | assumptions | low | Three operator choices carry defaults rather than confirmed answers (design "Open questions"). An interactive AskUserQuestion is not available to a phase sub-agent | Surfaced in the handoff for the operator. Every default fails closed or saves cost |
+| 4 | performance | low | The probe adds up to two HTTP calls (≤ 10 s each) per `--check-vendors` run | Accepted. It runs once per batch, and API lanes probe only for mode `review` |
+
+## Parallelizability
+
+Independent: 3 groups (1, 2, 4) | Sequential chains: 1 (→3→{5,6}→7) | Max parallel width: 3.
+File overlap: `review_dispatcher.py` (groups 1 and 3, ordered by dependency; group 1 owns only
+the `ReviewResult` fields), `review_quorum_policy.json` (groups 3 and 7, ordered),
+`skills/autopilot/SKILL.md` (groups 6 and 7, ordered). No two independent groups share a file.
diff --git a/openspec/changes/openrouter-review-lane/proposal.md b/openspec/changes/openrouter-review-lane/proposal.md
index d5a8f8fe..219d1ff4 100644
--- a/openspec/changes/openrouter-review-lane/proposal.md
+++ b/openspec/changes/openrouter-review-lane/proposal.md
@@ -7,20 +7,137 @@
 
 ## Summary
 
-Make API-based multi-vendor review available in cloud containers by registering OpenRouter-backed reviewer lanes (non-Anthropic model families) that dispatch over HTTP through the existing OpenAI-compatible adapter, need no vendor CLI, and count toward converge() quorum. Lanes are declared in the dispatch request's execution_profile and review_requirements from ri-21, verified by a dry invocation rather than credential probing, bounded by the existing spend ceiling, and their use retires the temporary cloud single-vendor review policy.
+Make API-based multi-vendor review available in cloud containers. Register OpenRouter-backed
+reviewer lanes from non-Anthropic model families that:
+
+- dispatch over HTTP through the existing OpenAI-compatible adapter,
+- need no vendor CLI, and
+- count toward `converge()` quorum.
+
+Lanes are declared in the dispatch request's `execution_profile` and `review_requirements`
+from ri-21. Each lane is verified by a dry invocation, not by probing credentials, and is
+bounded by the existing spend ceiling. Once the lanes are in use, the temporary cloud
+single-vendor review policy is retired.
 
 ## Dependencies
 
-- `ri-21`
+- `ri-21` (`dispatch-contract`, completed): execution_profile, review_requirements, the quorum
+  policy data file, honest-quorum parking, and the closed degradation codes.
+
+## Why
+
+Cloud workers run on the Claude subscription only. Their only review lane is the agent itself,
+so review either parks `capability_unavailable` or runs single-vendor under the temporary
+policy in `TRUST_POSTURE.md` (operator decision 2026-10-09).
+
+The repository already has most of an HTTP lane:
+
+- `OpenAICompatAdapter` (tier 2.5 of the review dispatcher)
+- an OpenRouter generation id on `ReviewResult`
+- `routing_spend_ledger` with a monthly ceiling
+- the `--check-vendors` dry-probe contract, which already names "the adapter's own
+  authenticated no-op" for API lanes
+
+None of this is wired:
+
+- No agent declares an OpenRouter `base_url`.
+- API lanes are always reported `probe_unsupported`.
+- Nothing writes ledger rows or checks the ceiling.
+- `agent_lane.py` hard-codes a single lane.
+
+Wiring these pieces restores the two-vendor quorum for cloud workers at metered cost, without
+waiting for the GX10 review lane. It also replaces a policy exception written in prose with a
+configured lane that can be observed.
+
+## What Changes
+
+**Lane roster** (`agent-coordinator/agents.yaml`, `agent-coordinator/archetypes.yaml`)
+- Add the endpoint-only agent `openrouter-review` (`type: openrouter`,
+  `endpoint_kind: openrouter`, `base_url`, reviewer-only).
+- Add a provider `openrouter` whose tier map supplies the review model and its fallbacks
+  (design D1).
+
+**Dispatcher** (`skills/parallel-infrastructure/scripts/{openai_compat_adapter,review_dispatcher}.py`, `review_quorum_policy.json`)
+- An authenticated, zero-cost dry probe for API lanes (`GET /key` for OpenRouter,
+  `GET /models` for local endpoints). It replaces `probe_unsupported` and also checks the
+  spend budget (D3, D4).
+- Per-mode `lane_kinds` in `--check-vendors --json`.
+- A model-family diversity rule: no Anthropic-family lanes, and no lane whose family is
+  already counted (D2).
+- Metered lanes fill quorum rather than supplement it (D5).
+- Cost and token capture on `ReviewResult`.
+- Refusal of packets that need tools (D6).
+- An `include_lanes` filter on `dispatch_and_wait`.
+
+**Spend** (new `skills/parallel-infrastructure/scripts/spend_recorder.py`, `agent-coordinator/src/model_routing/api.py`)
+- A new authenticated `POST /routing/spend` that writes `routing_spend_ledger` rows.
+- When the coordinator cannot be reached, records go to a local spool with a replay command,
+  and the new degradation code `metered_spend_unrecorded` is recorded (D4).
+
+**Convergence** (`skills/autopilot/scripts/{agent_lane,convergence_loop}.py`)
+- `agent_lane.py` composes the `claude_code` handshake lane with the verified HTTP lanes (D7).
+- `converge()` reports a mid-run loss of lane capability as `capability_unavailable`, not
+  `quorum_lost` (D7).
+
+**Supervisor** (`skills/supervise/scripts/execution.py`, `openspec/schemas/dispatch-result.schema.json`)
+- `counting_lanes` is ranked from `lane_kinds` (D8).
+- The degradation enum gains the new code.
+
+**Retirement, gated on cloud evidence** (`TRUST_POSTURE.md`, `review_quorum_policy.json`, `skills/autopilot/SKILL.md`, docs)
+- Delete the temporary cloud section and the policy entry.
+- Document the cloud setup: the environment secret and the egress allowlist (D9).
 
 ## Acceptance Outcomes
 
-- In a cloud container with an OpenRouter credential provisioned as an environment secret, converge() reaches min_quorum=2 for PLAN_REVIEW using claude_code plus at least one OpenRouter lane from a different model family, verified end to end on a fixture change.
-- Lane availability is established by a dry invocation of the lane for the requested mode and reported in execution_profile; no worker reads environment variables or credentials to discover it, and --check-vendors no longer reports a lane that cannot dispatch.
-- Every OpenRouter review records model, generation id and cost against the existing monthly spend ceiling; exceeding the ceiling parks with capability_unavailable instead of silently dropping to single-vendor review.
-- OpenRouter findings conform to review-findings.schema.json and are synthesized by ConsensusSynthesizer like CLI lanes, with vendor attribution preserved in the ledger.
-- The "Review quorum in cloud containers (temporary)" section of TRUST_POSTURE.md is removed once the lane passes in cloud, restoring quorum 2 everywhere, and review_requirements expresses any remaining per-environment exception as data with a sunset.
+- In a cloud container with an OpenRouter credential provisioned as an environment secret,
+  `converge()` reaches `min_quorum=2` for PLAN_REVIEW using `claude_code` plus at least one
+  OpenRouter lane from a different model family, verified end to end on a fixture change.
+- Lane availability is established by a dry invocation of the lane for the requested mode and
+  reported in `execution_profile`. No worker reads environment variables or credentials to
+  discover it, and `--check-vendors` no longer reports a lane that cannot dispatch.
+- Every OpenRouter review records model, generation id and cost against the existing monthly
+  spend ceiling. Exceeding the ceiling parks with `capability_unavailable` instead of silently
+  dropping to single-vendor review.
+- OpenRouter findings conform to `review-findings.schema.json` and are synthesized by
+  ConsensusSynthesizer like CLI lanes, with vendor attribution preserved in the ledger.
+- The "Review quorum in cloud containers (temporary)" section of `TRUST_POSTURE.md` is removed
+  once the lane passes in cloud, restoring quorum 2 everywhere, and `review_requirements`
+  expresses any remaining per-environment exception as data with a sunset.
+
+## Non-goals
+
+- Inline or proxy budget enforcement and virtual keys (`add-coordinator-llm-gateway`).
+- A general usage-accounting store or pricing tables (`add-model-usage-ledger`).
+- OpenRouter lanes for the `alternative` or `quick` dispatch modes, and tool use by HTTP lanes.
+- The GX10 review lane, and adaptive model selection for review lanes.
+
+## Impact
+
+**Affected specs**
+
+| Capability | Delta |
+|---|---|
+| `parallel-infrastructure` | MODIFIED: OpenAI-Compatible Dispatcher Discovery; Dispatchable Vendor Verification. ADDED: Metered Review Lane Spend Accounting; Tool-less Lane Packet Refusal |
+| `skill-workflow` | MODIFIED: Honest Review Quorum. ADDED: Composite Agent-Lane Review; Cloud Single-Vendor Policy Retirement |
+| `supervise` | MODIFIED: Execution Profile and Review Requirements |
+| `model-routing` | ADDED: Review Spend Recording Route |
+
+**Affected code**
+- `skills/parallel-infrastructure/scripts/{openai_compat_adapter,review_dispatcher}.py` and new `spend_recorder.py`; `skills/parallel-infrastructure/review_quorum_policy.json`
+- `skills/autopilot/scripts/{agent_lane,convergence_loop}.py`, `skills/autopilot/SKILL.md`
+- `skills/supervise/scripts/execution.py`
+- `agent-coordinator/{agents.yaml,archetypes.yaml}` and `agent-coordinator/src/model_routing/api.py`
+- `openspec/schemas/dispatch-result.schema.json` (additive enum value)
+- `TRUST_POSTURE.md` (section removal, last task), `docs/guides/` cloud setup notes
+
+**Operational**
+- Requires the cloud environment secret `OPENROUTER_API_KEY`, egress to `openrouter.ai`, and
+  either `ROUTING_MONTHLY_CEILING_USD > 0` on the coordinator or a credit limit on the
+  OpenRouter key.
+- Review packets are sent to OpenRouter.
 
 ## Rationale
 
-Restores the two-vendor review quorum for cloud workers at metered API cost instead of waiting on the GX10 review lane, and replaces a prompt-level policy exception with a configured, observable lane.
+Restores the two-vendor review quorum for cloud workers at metered API cost instead of waiting
+on the GX10 review lane, and replaces a prompt-level policy exception with a configured,
+observable lane.
diff --git a/openspec/changes/openrouter-review-lane/session-log.md b/openspec/changes/openrouter-review-lane/session-log.md
new file mode 100644
index 00000000..a32fab41
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/session-log.md
@@ -0,0 +1,64 @@
+# Session Log: openrouter-review-lane
+
+> Decision rationale, trade-offs, and alternatives recorded at each workflow phase.
+> Auto-generated by workflow skills. Sanitized before commit.
+
+## Phase: Plan Iteration 1 (2026-10-11)
+
+**Agent**: claude_code (autopilot PLAN_ITERATE, architect) | **Session**: N/A
+
+### Decisions
+1. **A lane is an endpoint-only agents.yaml agent (openrouter-review, type openrouter), with its model in an archetypes.yaml provider** `architectural: parallel-infrastructure` — This reuses tier-2.5 discovery and the coordinator's dispatch-configs without a second roster. Lane id = type, because converge keys results by vendor.
+2. **Model-family diversity rule: reject anthropic-publisher lanes and skip duplicate families via vendor_families data** `architectural: parallel-infrastructure` — Quorum is meant to measure independent model opinions. An OpenRouter lane in the claude_code or codex family would inflate it.
+3. **API lanes verify through an authenticated zero-cost probe (GET /key or GET /models) that also checks the spend budget** `architectural: parallel-infrastructure` — The existing Dispatchable Vendor Verification requirement already names this; today every API lane is probe_unsupported.
+4. **Spend: fail-closed budget check at probe time (coordinator ceiling > 0 or key credit limit); record through a new POST /routing/spend; spool and replay when the coordinator is unreachable, with a new degradation code metered_spend_unrecorded** `architectural: model-routing` — The existing ceiling is advisory and LedgerService.record has no caller. Cloud workers are known to hit coordinator_projection_forbidden, so the key limit bounds spend while records sit in the spool.
+5. **Metered lanes fill quorum only (fill_target defaults to default_min_quorum)** `architectural: parallel-infrastructure` — Prevents every host review from paying OpenRouter. The operator can tune it as data.
+6. **agent_lane gains a CompositeOrchestrator (claude_code handshake plus include_lanes HTTP dispatch), and converge maps a mid-run vendor_unavailable/auth_required quorum loss to capability_unavailable** `architectural: skill-workflow` — This is the only path by which a cloud worker reaches quorum 2, and it makes 'exceeding the ceiling parks' true mid-run as well as at the probe.
+7. **Retiring TRUST_POSTURE's cloud section and the policy entry is the last task, gated by an evidence file and a guard test** `architectural: skill-workflow` — The roadmap says the policy is removed once the lane passes in cloud. Live cloud evidence cannot run in CI, so it is an operator-run step with a recorded artifact.
+8. **Ran the analysis inline instead of dispatching parallel Explore analyst sub-agents** `architectural: skill-procedure-deviation` — The PLAN_ITERATE sub-agent harness exposes no Task/Agent tool; this is a genuine unavailability of the adapter, not avoidance. Reported per AGENTS.md.
+9. **Surfaced the assumption findings as documented defaults plus handoff open questions instead of AskUserQuestion** `architectural: skill-procedure-deviation` — A phase sub-agent cannot run an interactive prompt. Each default fails closed or saves cost, and the operator can override it as data.
+
+### Alternatives Considered
+- Add base_url to pi-local and reuse the pi provider: rejected because Couples the pi harness identity, the CLI-precedence rules, and a location: local agent to a cloud HTTP lane
+- Fail the review whenever the ledger write fails: rejected because Cloud coordinator access is partly forbidden; the key credit limit already bounds spend
+- Wait for add-model-usage-ledger or add-coordinator-llm-gateway to provide accounting and enforcement: rejected because Both are drafts with much larger scope; the roadmap names the existing ceiling
+- Always dispatch every configured lane: rejected because Adds metered cost to every host review for marginal benefit
+
+### Trade-offs
+- Accepted The family check uses the primary model only over forbidding cross-family fallbacks because A capacity error would otherwise be fatal to the lane; model_used is recorded for audit
+- Accepted Fail closed when no ceiling source exists over treating an unset ceiling as unlimited because A metered lane must never spend without a bound
+
+### Open Questions
+- [ ] Operator: confirm the fail-closed ceiling default (coordinator ROUTING_MONTHLY_CEILING_USD > 0, or an OpenRouter key credit limit).
+- [ ] Operator: confirm that metered lanes fill quorum only, rather than always being dispatched.
+- [ ] Operator/implementer: choose the openrouter provider premium review model (non-Anthropic, ideally a family no host CLI serves).
+
+### Completed Work
+- proposal.md: Why, What Changes, Impact, Non-goals
+- design.md: D1-D9, interface-contract table, security, risks, open questions
+- specs: parallel-infrastructure (2 MODIFIED, 2 ADDED), skill-workflow (1 MODIFIED, 2 ADDED), supervise (1 MODIFIED), model-routing (1 ADDED); placeholder multiplayer-collaboration delta removed
+- tasks.md: 7 groups, 33 tasks with Files/Depends/Specs and a traceability table
+
+### Context
+Turned the plan-roadmap scaffold into a full plan. Addressed 16 findings (5 critical, 6 high, 5 medium): rewrote the proposal, wrote design decisions D1-D9 grounded in the existing adapter, dispatcher, ledger, converge and agent_lane code, replaced the placeholder multiplayer-collaboration delta with MODIFIED/ADDED deltas in four real capabilities, and wrote seven dependency-annotated task groups.
+
+---
+
+## Phase: Plan Iteration 2 (2026-10-11)
+
+**Agent**: claude_code (autopilot PLAN_ITERATE, architect) | **Session**: N/A
+
+### Decisions
+1. **Generate one commit for the whole iterate run instead of one commit per iteration** `architectural: skill-procedure-deviation` — The edits for iterations 1 and 2 were interleaved in a single editing pass over the scaffold. Separate commits would be artificial. Both iterations are recorded in plan-findings.md and here.
+2. **Skip the iterate-on-plan step 10 vendor review** `architectural: skill-procedure-deviation` — VENDOR_REVIEW is off: no --vendor-review flag, and the coordinator is not available to this sub-agent. Autopilot's next phase, PLAN_REVIEW, runs the multi-vendor review, so a dispatch here would duplicate it.
+3. **Defer work-packages.yaml generation to /implement-feature** `architectural: skill-procedure-deviation` — tasks.md already carries write scopes and dependencies; work-packages.yaml is only needed if the coordinated tier is selected.
+
+### Completed Work
+- Spec: a local API lane verifies on probe success alone
+- D4: review_reservation_usd defaults to 1.00
+- D7: claude_code is always verified inside agent_lane; risk rows added
+- plan-findings.md written with all iterations and the parallelizability summary
+
+### Context
+Self-review of the rewritten plan found 4 medium findings: the local lane verification rule, the reservation default, claude_code verification inside agent_lane, and a supervisor/worker environment mismatch risk. All were fixed. A settle check found nothing at or above medium; 4 low findings remain in plan-findings.md.
+
diff --git a/openspec/changes/openrouter-review-lane/specs/configuration/spec.md b/openspec/changes/openrouter-review-lane/specs/configuration/spec.md
new file mode 100644
index 00000000..1a1a0496
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/specs/configuration/spec.md
@@ -0,0 +1,37 @@
+## MODIFIED Requirements
+
+### Requirement: Provider Model Mapping Configuration
+
+Provider dispatch configuration SHALL define model mappings for Claude Code, Codex, antigravity, grok, and pi so logical archetypes can resolve to provider-specific model IDs.
+
+The model mapping SHALL conform to `openspec/schemas/provider-model-map.schema.json` (schema_version 2). The provider key set SHALL be closed to the five roster keys, all five required, plus two optional keys: `local` and `openrouter`. `openrouter` holds the model aliases of the endpoint-only `openrouter-review` lane, and is not a roster vendor.
+
+The `pi` provider SHALL resolve to OpenRouter model slugs, and its default model SHALL be `qwen/qwen3-coder`, selected so the roster reaches models outside the subscription harnesses.
+
+#### Scenario: Provider map includes all first-class providers
+
+- **WHEN** the default provider model map is loaded
+- **THEN** it SHALL include entries for `claude_code`, `codex`, `antigravity`, `grok`, and `pi`
+- **AND** each entry SHALL define `premium`, `standard`, and `economy` model IDs
+- **AND** it SHALL NOT include an entry for `gemini`
+
+#### Scenario: Optional provider keys are allowed but not required
+
+- **WHEN** a provider model map carries an `openrouter` entry or a `local` entry
+- **THEN** it SHALL validate, provided the entry defines `premium`, `standard`, and `economy`
+- **AND** a map without either entry SHALL also validate
+- **AND** a map with any other provider key SHALL fail validation
+
+#### Scenario: pi maps to OpenRouter slugs
+
+- **WHEN** the `pi` provider entry is loaded
+- **THEN** every tier value SHALL be an OpenRouter model slug in `<publisher>/<model>` form
+- **AND** the `standard` tier SHALL be `qwen/qwen3-coder`
+
+#### Scenario: Non-Claude provider rejects unmapped Claude alias
+
+- **GIVEN** provider `codex`
+- **AND** an archetype resolves to legacy alias `opus`
+- **WHEN** no Codex mapping exists for that alias or tier
+- **THEN** dispatch resolution SHALL fail with a structured configuration error before invoking Codex
+- **AND** the error SHALL identify the missing provider model mapping
diff --git a/openspec/changes/openrouter-review-lane/specs/model-routing/spec.md b/openspec/changes/openrouter-review-lane/specs/model-routing/spec.md
new file mode 100644
index 00000000..d3af4759
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/specs/model-routing/spec.md
@@ -0,0 +1,32 @@
+## ADDED Requirements
+
+### Requirement: Review Spend Recording Route
+
+The coordinator SHALL expose `POST /routing/spend`, which requires the `X-API-Key` header.
+
+The request body SHALL be validated with unknown fields forbidden. It accepts:
+- required: `vendor`, `model`, `endpoint_kind`, `generation_id`;
+- optional: `prompt_tokens`, `completion_tokens` (non-negative integers), `actual_usd` (a
+  non-negative number), `tokens_estimated`, `work_unit_ref`, `occurred_at`.
+
+A valid request SHALL write one `routing_spend_ledger` row through `LedgerService.record`.
+`generation_id` SHALL be the idempotency key: a second request with a `generation_id` already
+in the ledger SHALL return the existing row with HTTP 200 and SHALL NOT insert another row.
+`GET /routing/usage` SHALL include recorded review rows in `metered_usd_used`.
+
+#### Scenario: A review spend row is recorded
+- **WHEN** an authenticated client posts `{vendor: "openrouter", model: "<publisher>/<model>", endpoint_kind: "openrouter", generation_id: "gen-abc", actual_usd: 0.0042, tokens_estimated: false}`
+- **THEN** the response SHALL be HTTP 201, and the next `GET /routing/usage?window=month` SHALL
+  report `metered_usd_used` increased by 0.0042
+
+#### Scenario: Duplicate generation id is not double-counted
+- **WHEN** the same body is posted twice
+- **THEN** the second response SHALL be HTTP 200 and the ledger SHALL contain one `gen-abc` row
+
+#### Scenario: Unauthenticated write is rejected
+- **WHEN** the request has no `X-API-Key` header, or an invalid one
+- **THEN** the response SHALL be HTTP 401 and no row SHALL be written
+
+#### Scenario: Invalid spend is rejected
+- **WHEN** the body has `actual_usd: -1`, or an unknown field `api_key`
+- **THEN** the response SHALL be HTTP 422 and no row SHALL be written
diff --git a/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md b/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md
new file mode 100644
index 00000000..1a4c118b
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md
@@ -0,0 +1,262 @@
+## MODIFIED Requirements
+
+### Requirement: OpenAI-Compatible Dispatcher Discovery
+
+The review dispatcher SHALL construct an OpenAI-compatible adapter for configured `local` or
+`openrouter` endpoints with a `base_url` after CLI and SDK discovery. A usable CLI SHALL retain
+precedence over the endpoint adapter for the same agent.
+
+The lane id of an endpoint lane SHALL be its agent `type`. Its model family SHALL be the
+publisher prefix of its primary model slug (`<publisher>/<model>`). The family of a CLI or SDK
+vendor SHALL be read from `vendor_families` in `review_quorum_policy.json`.
+
+The dispatcher SHALL skip, and SHALL NOT count toward quorum, an `openrouter` lane in either
+of these cases:
+- its primary model or any fallback model has publisher `anthropic`;
+- its family equals the family of a lane already selected at tier 1 or tier 2. The skip
+  reason SHALL be `duplicate_model_family`.
+
+An agent with `endpoint_kind: openrouter` selected at tier 2.5 is a metered lane. Metered lanes
+SHALL be selected only while the non-metered selected lanes number fewer than
+`metered_lanes.fill_target`. That value defaults to the policy file's `default_min_quorum`.
+Metered lanes are added in roster order until the target is reached. `--check-vendors` and
+`dispatch_and_wait` SHALL apply the same selection.
+
+`dispatch_and_wait` SHALL accept an optional `include_lanes` set. When it is given, only those
+lanes SHALL be dispatched. When it is `None`, behaviour SHALL be unchanged.
+
+#### Scenario: Endpoint-only agent is discoverable
+
+- **WHEN** dispatch configuration contains a local/OpenRouter endpoint with no CLI or SDK block
+- **THEN** review discovery SHALL return an OpenAI-compatible reviewer for that endpoint
+
+#### Scenario: CLI retains precedence
+
+- **WHEN** an agent has both a usable CLI and an OpenAI-compatible endpoint
+- **THEN** review discovery SHALL select the CLI tier first
+
+#### Scenario: Anthropic-family OpenRouter lane is rejected
+
+- **WHEN** an `openrouter` agent resolves the primary model `anthropic/<any>` or lists an
+  `anthropic/` fallback
+- **THEN** discovery SHALL NOT return that lane, and `--check-vendors --json` SHALL list it
+  under `unverified` with reason `anthropic_family`
+
+#### Scenario: Duplicate family is skipped
+
+- **WHEN** `codex` is selected at tier 1, `vendor_families.codex` is `openai`, and an
+  `openrouter` lane's primary model is `openai/<model>`
+- **THEN** that lane SHALL be listed `unverified` with reason `duplicate_model_family` and SHALL
+  NOT be dispatched
+
+#### Scenario: Metered lane fills quorum only
+
+- **WHEN** `fill_target` is 2, and two non-metered lanes and one verified `openrouter` lane are
+  available
+- **THEN** discovery SHALL return the two non-metered lanes only, and no HTTP request SHALL be
+  sent to the OpenRouter endpoint during dispatch
+
+#### Scenario: Metered lane fills a cloud roster
+
+- **WHEN** `fill_target` is 2, `claude_code` is the only non-metered lane, and one `openrouter`
+  lane verifies
+- **THEN** discovery SHALL return `claude_code` and the `openrouter` lane
+
+#### Scenario: include_lanes restricts dispatch
+
+- **WHEN** `dispatch_and_wait` is called with `include_lanes={"openrouter"}` and `claude_code` and
+  `openrouter` are both available
+- **THEN** exactly one review SHALL be dispatched, to `openrouter`
+
+### Requirement: Dispatchable Vendor Verification
+
+`review_dispatcher.py --check-vendors` SHALL count a vendor lane as available for a mode only
+after a dry invocation for that mode succeeds. The dry invocation is the adapter's declared
+no-op, run with a 10-second timeout:
+- for a CLI lane, `<cli> --version`;
+- for an `openrouter` API lane, one authenticated `GET {base_url}/key`;
+- for a `local` API lane, one authenticated `GET {base_url}/models`.
+
+An SDK lane with no authenticated no-op SHALL remain `unverified` with reason
+`probe_unsupported`.
+
+Credentials MAY be read only inside the adapter's existing credential path. The probe SHALL
+NOT print, log, or return any environment value, credential, or response body. From an API
+probe response it SHALL keep only the numeric budget fields (`limit`, `usage`,
+`limit_remaining`).
+
+An `openrouter` lane SHALL verify only if:
+- the authenticated probe succeeds;
+- at least one spend ceiling source is available: the coordinator monthly ceiling when it is
+  greater than 0 and the coordinator is reachable, or the key's non-null `limit`; and
+- every available source has remaining budget of at least
+  `metered_lanes.review_reservation_usd`.
+
+A `local` API lane SHALL verify when its probe succeeds; no budget rule applies to it.
+An `openrouter` lane that fails any of these conditions SHALL be `unverified` with one of these reasons: `auth_failed`,
+`probe_timeout`, `endpoint_unreachable`, `spend_ceiling_exceeded`, or
+`spend_ceiling_unverifiable`.
+
+With `--json` it SHALL print
+`{"modes": {<mode>: {"verified": [...], "unverified": [{"vendor", "reason"}], "lane_kinds": {<lane>: <endpoint_kind>}}}, "probe_command": "<argv>"}`.
+It SHALL keep its existing exit codes: 0 at quorum, 2 below quorum or on probe failure. When
+the roster cannot be resolved it SHALL print `{"error": "<reason>", "modes": {}}` and exit 2.
+
+#### Scenario: A listed vendor without its CLI is unverified
+- **WHEN** `agents.yaml` lists `codex` for mode `review` and no `codex` executable is on `PATH`
+- **THEN** `--check-vendors --json` SHALL list `codex` under `unverified` with reason
+  `cli_not_found`, and SHALL NOT count it toward `--min-vendors`
+
+#### Scenario: A hanging dry invocation is unverified
+- **WHEN** a lane's dry invocation does not exit within 10 seconds
+- **THEN** the lane SHALL be `unverified` with reason `probe_timeout`
+
+#### Scenario: The probe never discloses credentials
+- **WHEN** the test sets `ANTHROPIC_API_KEY=sk-test-SENTINEL-1234567890`,
+  `OPENAI_API_KEY=sk-test-SENTINEL-0987654321` and
+  `OPENROUTER_API_KEY=sk-or-test-SENTINEL-5555555555`, configures an `openrouter` lane with an
+  injected transport that echoes the request headers in its response body, and runs
+  `--check-vendors --json`
+- **THEN** no sentinel value SHALL appear in stdout, stderr, log records, or the JSON, and no
+  `env` or `printenv` subprocess SHALL have been spawned
+
+#### Scenario: An OpenRouter lane verifies by its authenticated no-op
+- **WHEN** the injected transport answers `GET /key` with HTTP 200 and `limit: 20.0`,
+  `limit_remaining: 15.0`, the coordinator is unreachable, and `review_reservation_usd` is 1.0
+- **THEN** the lane SHALL be listed under `verified` for mode `review`, `lane_kinds` SHALL map
+  it to `openrouter`, and no chat-completions request SHALL have been sent
+
+#### Scenario: A rejected key is unverified
+- **WHEN** the injected transport answers `GET /key` with HTTP 401
+- **THEN** the lane SHALL be `unverified` with reason `auth_failed`
+
+#### Scenario: An exhausted ceiling is unverified
+- **WHEN** the coordinator reports `metered_ceiling_usd: 50.0` and `metered_usd_used: 49.5`, and
+  `review_reservation_usd` is 1.0
+- **THEN** the lane SHALL be `unverified` with reason `spend_ceiling_exceeded`, even if the key's
+  `limit_remaining` is larger
+
+#### Scenario: No ceiling source fails closed
+- **WHEN** the coordinator is unreachable or reports `metered_ceiling_usd: 0`, and the key
+  reports `limit: null`
+- **THEN** the lane SHALL be `unverified` with reason `spend_ceiling_unverifiable`
+
+#### Scenario: An unexpected probe response shape fails closed
+- **WHEN** `GET /key` returns HTTP 200 with a body that has no `data` object
+- **THEN** the lane SHALL be `unverified` with reason `spend_ceiling_unverifiable` unless the
+  coordinator ceiling source alone verifies it
+
+## ADDED Requirements
+
+### Requirement: Metered Review Lane Spend Accounting
+
+Every review that an `openrouter` lane dispatches SHALL request inline usage accounting
+(`"usage": {"include": true}`). On the resulting `ReviewResult` it SHALL set:
+- `generation_id`, `model_used`, `prompt_tokens`, `completion_tokens`;
+- `cost_usd`, taken from the response's `usage.cost`;
+- `cost_source`: `reported` when `usage.cost` is present, `estimated` when it is absent.
+
+`converge()` SHALL write these fields into the round checkpoint's vendor index.
+
+After each review that sent a request, `ReviewOrchestrator.dispatch_and_wait` SHALL call
+`spend_recorder.record()`, which SHALL send one row to `POST /routing/spend` with:
+`vendor` (the lane id), `model`, `endpoint_kind: openrouter`, `generation_id`, token counts,
+`actual_usd`, `tokens_estimated` (true when `cost_source` is `estimated`), and
+`work_unit_ref` (`<change_id>:<phase>:round-<n>`, for example
+`openrouter-review-lane:VAL_REVIEW:round-2`; the phase, not the review type, so IMPL_REVIEW and
+VAL_REVIEW rows stay distinct; `converge()` supplies it in the `spend_context` it passes to
+`dispatch_and_wait` when its caller gives the phase). The call SHALL happen on every dispatch path, including a host
+`converge()` or `/parallel-review-*` run that selected the metered lane, not only inside
+`agent_lane.py`. The result SHALL carry `spend_recorded` (the recorder's `recorded` value).
+
+If the write fails, the record SHALL be appended to
+`openspec/changes/<change-id>/reviews/spend-spool.jsonl`, and the caller SHALL record the
+degradation `metered_spend_unrecorded` with phase and lane. The change id SHALL come from the
+`spend_context` (`change_id`, `work_unit_ref`) passed to `dispatch_and_wait`. A metered lane
+dispatched without a `spend_context` SHALL NOT make an HTTP request; it SHALL return a failed
+result with `error_class` `vendor_unavailable` and reason `spend_context_missing`.
+
+#### Scenario: A metered lane without spend context is not dispatched
+- **WHEN** `dispatch_and_wait` is called with no `spend_context` and the selection includes the
+  `openrouter` lane
+- **THEN** no HTTP request SHALL be made for that lane, and its result SHALL have `error_class`
+  `vendor_unavailable` and reason `spend_context_missing`
+
+`spend_recorder.py replay --change-id <id>` SHALL post the spooled rows. Replay SHALL skip a
+`generation_id` the ledger already holds, and SHALL remove each row it delivers.
+
+Each time `dispatch_and_wait` is about to dispatch a metered lane (once per review round, on
+every dispatch path), the remaining budget SHALL be re-checked with the same rule the probe
+uses. A lane below `review_reservation_usd` SHALL NOT be dispatched
+for that round and SHALL be reported as a failed result with `error_class` `vendor_unavailable`
+and reason `spend_ceiling_exceeded`.
+
+#### Scenario: A later round finds the ceiling exhausted
+- **WHEN** the coordinator ceiling had budget at probe time, and before round 2 its remaining
+  budget is below `review_reservation_usd`
+- **THEN** round 2 SHALL NOT dispatch the `openrouter` lane, and SHALL record it as
+  `vendor_unavailable` with reason `spend_ceiling_exceeded`
+
+#### Scenario: A review is recorded against the ledger
+- **WHEN** an `openrouter` review returns `id: gen-abc`, `usage: {prompt_tokens: 1200, completion_tokens: 300, cost: 0.0042}`, and the coordinator accepts the write
+- **THEN** the ledger SHALL contain one row with `generation_id: gen-abc`, `actual_usd: 0.0042`,
+  and `tokens_estimated: false`, and the round checkpoint index entry for the lane SHALL carry
+  the same generation id, model and cost
+
+#### Scenario: A host-path metered review is recorded
+- **WHEN** a host with one non-metered lane runs `converge()` with `ReviewOrchestrator`, the fill
+  rule selects the `openrouter` lane, and its review returns `id: gen-host`
+- **THEN** `spend_recorder.record()` SHALL have been called once for `gen-host`, and the result's
+  `spend_recorded` SHALL be true when the coordinator accepts the write
+
+#### Scenario: Missing cost is labelled estimated
+- **WHEN** the response has token usage but no `usage.cost`
+- **THEN** `cost_source` SHALL be `estimated` and the ledger row SHALL have
+  `tokens_estimated: true`
+
+#### Scenario: Coordinator unavailable spools the record
+- **WHEN** `POST /routing/spend` fails with a connection error or HTTP 403
+- **THEN** the review result SHALL be unchanged, one line SHALL be appended to
+  `reviews/spend-spool.jsonl`, and a `metered_spend_unrecorded` degradation SHALL be recorded
+
+#### Scenario: Replay is idempotent
+- **WHEN** `replay` runs twice over a spool holding `gen-abc`, and the first run succeeds
+- **THEN** the ledger SHALL hold exactly one `gen-abc` row and the spool SHALL be empty
+
+### Requirement: Tool-less Lane Packet Refusal
+
+When a round's primary review packet has `tools_overflow: true`, `converge()` SHALL also build a
+tool-less packet for OpenAI-compatible lanes, within the same `BUDGET_CHARS`, with its own sidecar
+`review-packet.toolless.meta.json`:
+- for `review_type == "plan"`, its diff SHALL be limited to `openspec/changes/<change-id>/**`,
+  and it SHALL carry the full text of `proposal.md`, `design.md`, `tasks.md` and the spec deltas;
+- for `review_type == "implementation"`, it SHALL keep the rule-group selection, drop the excluded
+  and truncated files, and list them in the sidecar as `coverage.skipped`.
+
+`dispatch_and_wait` SHALL give OpenAI-compatible lanes the tool-less packet when one exists, and
+the primary packet otherwise. CLI lanes and the `claude_code` handshake lane SHALL keep the
+primary packet.
+
+An OpenAI-compatible lane SHALL NOT review a packet it received whose sidecar has
+`tools_overflow: true`. That means the tool-less packet when one was built, otherwise the primary
+packet. Its dispatch SHALL return `success=False`, `error_class=vendor_unavailable` and
+`error="packet_requires_tools"` without sending a request.
+The Empty Or Blinded Review Is Not Success rule SHALL apply to OpenAI-compatible lanes as it
+does to CLI lanes.
+
+#### Scenario: Overflowing branch diff still reaches the HTTP lane
+- **WHEN** a plan review's primary packet has `tools_overflow: true` because the branch diff
+  exceeds `BUDGET_CHARS`, but the change's own artifacts fit, and an `openrouter` lane is selected
+- **THEN** a tool-less packet with `tools_overflow: false` SHALL be written. The `openrouter` lane
+  SHALL be dispatched with that packet's body, and the CLI and handshake lanes SHALL receive the
+  primary packet
+
+#### Scenario: Overflowing packet is refused
+- **WHEN** the packet an `openrouter` lane would receive (the tool-less packet, or the primary
+  packet when no tool-less packet was built) has `tools_overflow: true`
+- **THEN** the lane's result SHALL be `success=False` with `error="packet_requires_tools"`, and the
+  injected transport SHALL record zero requests
+
+#### Scenario: Fast empty HTTP review does not count
+- **WHEN** an `openrouter` lane returns `{"findings": []}` in under the configured floor
+- **THEN** `success` SHALL be false, and the lane SHALL NOT count toward quorum
diff --git a/openspec/changes/openrouter-review-lane/specs/skill-workflow/spec.md b/openspec/changes/openrouter-review-lane/specs/skill-workflow/spec.md
new file mode 100644
index 00000000..16f61ea2
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/specs/skill-workflow/spec.md
@@ -0,0 +1,144 @@
+## MODIFIED Requirements
+
+### Requirement: Honest Review Quorum
+
+When the launch marker of a dispatched child carries `review_requirements`, a review phase
+whose verified lanes from `execution_profile` are fewer than
+`review_requirements.min_quorum[phase]` SHALL record
+`park(kind=capability_unavailable, phase, missing_lanes)` and stop. It SHALL NOT run the review
+with a lower quorum.
+
+A standalone run (no launch marker) SHALL keep disabling CLI review below quorum. It SHALL
+record a `review_skipped` degradation, or a `single_vendor_review` degradation when exactly one
+lane reviewed.
+
+During `converge()`, a round can end with fewer successful results than `min_quorum`.
+`missing_lanes` SHALL be the round's verified lanes minus the lanes that returned a successful
+result. When `missing_lanes` is non-empty and every lane in it has a recorded failure whose
+`error_class` is `vendor_unavailable` or `auth_required`, `converge()` SHALL return
+`reason="capability_unavailable"` with `missing_lanes` naming those lanes. A verified lane with
+no result at all SHALL NOT satisfy this condition. This
+covers an exhausted budget, HTTP 402, a revoked key, or `packet_requires_tools`. Any other
+quorum loss SHALL remain `reason="quorum_lost"`.
+
+
+#### Scenario: A lane that returns nothing is not a capability loss
+- **WHEN** a PLAN_REVIEW round has verified lanes `claude_code` and `openrouter`, `claude_code`
+  succeeds, and `openrouter` returns neither a result nor a recorded failure
+- **THEN** `converge()` SHALL return `reason="quorum_lost"`, not `capability_unavailable`
+
+#### Scenario: Dispatched child below quorum parks
+- **WHEN** `review_requirements.min_quorum.PLAN_REVIEW` is 2 and only `claude_code` is verified
+- **THEN** the loop SHALL have `park.kind == capability_unavailable` with `missing_lanes` naming
+  the counting lanes not verified, no review dispatch SHALL have run, and `emit-result` SHALL
+  return `parked/capability_unavailable`
+
+#### Scenario: A single-lane review under a quorum-1 policy is recorded
+- **WHEN** a dispatched child's `review_requirements.min_quorum.PLAN_REVIEW` is 1 by policy
+  data, and exactly one review lane dispatches because the others failed to dispatch
+- **THEN** the review SHALL run, and `degradations` SHALL contain a `single_vendor_review` entry
+  for `PLAN_REVIEW` whose detail names the vendor
+- **AND** the child SHALL NOT have read environment variables or credentials to decide that only
+  one lane exists
+
+#### Scenario: GATEKEEPER review scheduling on the host-driven path
+- **WHEN** `runner.py transition --outcome proceed_with_review` is applied in `GATEKEEPER`
+- **THEN** `val_review_enabled` SHALL be True and `gate_verdict` SHALL be `proceed_with_review`
+
+#### Scenario: Standalone run below quorum records a degradation
+- **WHEN** no launch marker exists and `--check-vendors` reports one vendor
+- **THEN** `cli_review_enabled` SHALL be False and `degradations` SHALL contain one
+  `review_skipped` entry for `PLAN_REVIEW`
+
+#### Scenario: Budget exhausted mid-run parks instead of losing quorum
+- **WHEN** `min_quorum` is 2, round 1 succeeds with `claude_code` and `openrouter`, and in round 2
+  `openrouter` fails with HTTP 402 (`error_class=vendor_unavailable`)
+- **THEN** `converge()` SHALL return `reason="capability_unavailable"` with
+  `missing_lanes == ["openrouter"]`, and SHALL NOT return `quorum_lost`
+
+#### Scenario: A malformed review still loses quorum
+- **WHEN** `min_quorum` is 2 and a round's `openrouter` result fails with
+  `error_class=unknown` ("Review output was not valid review-findings JSON")
+- **THEN** `converge()` SHALL return `reason="quorum_lost"`
+
+## ADDED Requirements
+
+### Requirement: Composite Agent-Lane Review
+
+`agent_lane.py converge` SHALL accept `--verified-lanes` (repeatable). A dispatched child SHALL
+take the values from its launch marker's `execution_profile.lanes.review`. A standalone run
+SHALL take them from the `--check-vendors --json` output and SHALL NOT read environment
+variables or credentials.
+
+It SHALL resolve the quorum policy with `verified_review_lanes` equal to the number of
+verified lanes, and SHALL pass those lanes to `converge()` as `verified_lanes`.
+
+Each round SHALL:
+- dispatch the `claude_code` handshake lane;
+- in parallel, dispatch `ReviewOrchestrator.dispatch_and_wait(include_lanes=<verified lanes except claude_code>)`;
+- return both results to `converge()`.
+
+Every lane's findings SHALL be written to the round checkpoint under its own lane id, and
+ConsensusSynthesizer SHALL attribute consensus findings to those lane ids.
+
+After each run, `agent_lane.py` SHALL write `ConvergenceResult.consensus` (including
+`quorum_received`) under `openspec/changes/<change-id>/reviews/`, with one file per phase:
+- `consensus-plan.json` for `PLAN_REVIEW`;
+- `consensus-impl-review.json` for `IMPL_REVIEW`;
+- `consensus-val-review.json` for `VAL_REVIEW`.
+
+The two implementation phases share `review_type: implementation`, so the file is named by phase
+and neither run overwrites the other. `converge()` itself SHALL NOT be required to write these
+files.
+
+The review body written for `VAL_REVIEW` SHALL list every lane that reviewed. It SHALL name a
+`single_vendor_review` degradation only when exactly one lane reviewed.
+
+#### Scenario: Cloud plan review reaches quorum two
+- **WHEN** `agent_lane.py converge --phase PLAN_REVIEW --verified-lanes claude_code --verified-lanes openrouter`
+  runs against a fixture change, with an injected OpenRouter transport that returns
+  schema-valid findings and an agent handshake that writes schema-valid findings
+- **THEN** `converge()` SHALL be called with `min_quorum=2`, the round checkpoint SHALL contain
+  findings files for both `claude_code` and `openrouter`, `consensus` SHALL report
+  `quorum_received: 2`, and `reviews/consensus-plan.json` SHALL contain the same consensus
+
+#### Scenario: Findings carry vendor attribution
+- **WHEN** both lanes report a finding at the same file and line range
+- **THEN** the consensus finding SHALL list both `claude_code` and `openrouter` in its vendor
+  attribution, and the review ledger entry SHALL preserve both lane ids
+
+#### Scenario: Only the agent lane verified
+- **WHEN** `--verified-lanes claude_code` is the only lane and no active policy lowers the quorum
+- **THEN** `converge()` SHALL return `capability_unavailable` with `missing_lanes` naming the
+  counting lanes not verified, and no handshake file SHALL be written
+
+### Requirement: Cloud Single-Vendor Policy Retirement
+
+The temporary cloud single-vendor policy SHALL be retired only after an evidence file
+`openspec/changes/openrouter-review-lane/evidence/cloud-quorum-run.md` records a cloud-container
+autopilot run on a fixture change. The run must show:
+- `PLAN_REVIEW` with `min_quorum=2`;
+- a `consensus-plan.json` attributing findings or confirmations to `claude_code` and to an
+  `openrouter` lane;
+- a ledger or spool row carrying that review's `generation_id`.
+
+Retirement SHALL:
+- delete the `cloud-container-single-vendor-2026-10-09` entry from
+  `review_quorum_policy.json`, keeping the `policies` array and its `sunset` field as the
+  mechanism for future exceptions;
+- delete the "Review quorum in cloud containers (temporary)" section of `TRUST_POSTURE.md`;
+- update `skills/autopilot/SKILL.md` so that no instruction tells a cloud worker to accept
+  single-vendor review.
+
+#### Scenario: Retirement restores quorum two in cloud
+- **WHEN** the policy entry has been deleted and `resolve_quorum_policy(environment="cloud_container", verified_review_lanes=1)` is called
+- **THEN** `min_quorum` SHALL be 2 for each review phase and `policy_id` SHALL be null
+
+#### Scenario: Retirement is blocked without evidence
+- **WHEN** a guard test finds `review_quorum_policy.json` without the cloud entry but no
+  `evidence/cloud-quorum-run.md` in this change, or an evidence file missing a `generation_id`
+- **THEN** the test SHALL fail
+
+#### Scenario: No prose exception remains
+- **WHEN** a guard test scans `TRUST_POSTURE.md` after retirement
+- **THEN** it SHALL find no section titled "Review quorum in cloud containers"
diff --git a/openspec/changes/openrouter-review-lane/specs/supervise/spec.md b/openspec/changes/openrouter-review-lane/specs/supervise/spec.md
new file mode 100644
index 00000000..bae00088
--- /dev/null
+++ b/openspec/changes/openrouter-review-lane/specs/supervise/spec.md
@@ -0,0 +1,79 @@
+## MODIFIED Requirements
+
+### Requirement: Execution Profile and Review Requirements
+
+Before launching a batch, the supervisor SHALL resolve two values by invoking
+`review_dispatcher.py --check-vendors --json`, and SHALL place both in every request:
+
+- **`execution_profile`**: verified lanes per mode (`review`, `alternative`, `quick`);
+  `location`; isolation mode; and `probe_command`, the only probe a worker may run.
+- **`review_requirements`**: `min_quorum` per review phase, and `counting_lanes`.
+  - `min_quorum` defaults to 2 and can be overridden by the router context
+    `review_min_quorum`.
+  - `counting_lanes` are ordered by the `cost_policy.tiers` ladder of
+    `agent-coordinator/routing.yaml`. Each lane's endpoint kind is read from the report's
+    `lane_kinds`. The kind is inferred from the `probe_unsupported` reason only when
+    `lane_kinds` is absent.
+
+The worker protocol in `skills/autopilot/SKILL.md` SHALL forbid reading environment variables
+or credentials to discover capabilities. `ExecutionAdapter.apply` SHALL persist the result's
+`degradations` on the checkpoint attempt and SHALL return them in its summary. When the result
+carries a `metered_spend_unrecorded` degradation, `apply` SHALL run
+`spend_recorder.py replay --change-id <id>` once, and SHALL report the replay outcome in its
+summary without failing the apply.
+
+#### Scenario: Request carries a resolved profile
+- **WHEN** `prepare` returns a batch
+- **THEN** every request SHALL validate against `dispatch-request.schema.json` with non-empty
+  `execution_profile.lanes.review`, `execution_profile.probe_command`, and
+  `review_requirements.min_quorum` keyed by review phase
+
+#### Scenario: Profile resolution failure blocks launch
+- **WHEN** `--check-vendors --json` prints output that does not parse as JSON, or JSON carrying
+  an `error` field
+- **THEN** `prepare` SHALL raise without writing any attempt, and the error SHALL name the probe
+  failure
+
+#### Scenario: Below-quorum availability still launches with an honest profile
+- **WHEN** `--check-vendors --json` exits 2 (below quorum) with valid JSON and no `error` field
+- **THEN** `prepare` SHALL succeed, and each request's `execution_profile.lanes.review` SHALL
+  list only the verified lanes, so the child parks `capability_unavailable` at its first review
+  phase
+
+#### Scenario: The per-environment quorum is resolved from data
+- **WHEN** the quorum policy data declares an active `cloud_container` entry with `min_quorum` 1
+  that applies below 2 verified review lanes, and `prepare` runs in a cloud container where one
+  review lane verifies
+- **THEN** every request's `review_requirements.min_quorum` SHALL be 1 for each review phase,
+  and `review_requirements.quorum_policy` SHALL name the environment, the policy entry, and its
+  sunset condition
+- **AND** on a host, or in a container where two or more review lanes verify, `min_quorum` SHALL
+  stay 2
+
+#### Scenario: A verified OpenRouter lane is ranked as metered
+- **WHEN** the report's `review.verified` is `["claude_code", "openrouter"]` with
+  `lane_kinds: {"claude_code": "vendor-cli", "openrouter": "openrouter"}`, and the routing ladder is
+  `[vendor-cli, vendor-sdk, openrouter]`
+- **THEN** `counting_lanes` SHALL be `["claude_code", "openrouter"]`, and `min_quorum` SHALL be 2
+  for each review phase
+
+#### Scenario: A report without lane_kinds still ranks
+- **WHEN** the report has no `lane_kinds` key
+- **THEN** ranking SHALL use the previous `probe_unsupported` inference and `prepare` SHALL succeed
+
+#### Scenario: Degradations reach the checkpoint
+- **WHEN** a success result carries
+  `degradations: [{code: single_vendor_review, phase: PLAN_REVIEW, detail: "codex not dispatchable"}]`
+- **THEN** after `apply` the checkpoint attempt's outcome metadata and the `apply` return value
+  SHALL both contain that entry unchanged
+
+#### Scenario: Unrecorded spend is replayed on apply
+- **WHEN** a result carries a `metered_spend_unrecorded` degradation and the coordinator accepts
+  the replay
+- **THEN** `apply` SHALL return a summary with the replayed row count, and the degradation SHALL
+  remain on the checkpoint attempt
+
+#### Scenario: Worker protocol forbids env probing
+- **WHEN** a guard test scans `skills/autopilot/SKILL.md` and `skills/supervise/SKILL.md`
+- **THEN** neither SHALL contain an instruction to run `env`, `printenv`, or to read API key
+  variables for vendor discovery
diff --git a/openspec/changes/openrouter-review-lane/tasks.md b/openspec/changes/openrouter-review-lane/tasks.md
index 200faab7..142b9dce 100644
--- a/openspec/changes/openrouter-review-lane/tasks.md
+++ b/openspec/changes/openrouter-review-lane/tasks.md
@@ -1,19 +1,342 @@
 # Tasks: OpenRouter review lane for cloud workers
 
-> Change ID: `openrouter-review-lane`
+> Change ID: `openrouter-review-lane`. Design decisions are referenced as D1–D9 (`design.md`).
+> Tests come first within each group (TDD). Each numbered task is sized for a single commit.
+> Each group lists **Files** (write scope) and **Depends** (blocking groups). Groups whose
+> write scopes do not overlap can run in parallel.
 
-## Status
+## Dependency graph
 
-- [ ] Planning
-- [ ] Implementation
-- [ ] Testing
-- [ ] Review
-- [ ] Done
+```
+1 (adapter) ────────────────┐
+2 (roster) ─────────────────┼─> 3 (dispatcher discovery/probe/spend call) ──┬─> 5 (convergence) ──┬─> 7 (cloud E2E + retirement)
+4 (spend route + recorder) ─┘                                               └─> 6 (supervisor)  ──┘
+```
 
-## Tasks
+Groups 1, 2 and 4 are independent, so up to 3 can run in parallel. Group 3 needs all three
+(4 for the `spend_recorder.record()` call in task 3.10). Groups 5 and 6 run in parallel after
+group 3. Group 7 runs last. Sequential chain length is 4.
 
-- [ ] Define detailed requirements
-- [ ] Implement core functionality
-- [ ] Write tests
-- [ ] Update documentation
-- [ ] Review and merge
+## 1. OpenAI-compatible adapter: probe, cost capture, packet refusal
+
+**Files:** `skills/parallel-infrastructure/scripts/openai_compat_adapter.py`,
+`skills/parallel-infrastructure/scripts/review_dispatcher.py` (only the `ReviewResult`
+dataclass fields and the shared ingest helper extracted in 1.7),
+`skills/tests/parallel-infrastructure/test_openai_compat_adapter.py`
+**Depends:** none
+**Specs:** parallel-infrastructure "Dispatchable Vendor Verification" (probe part),
+"Metered Review Lane Spend Accounting" (capture part), "Tool-less Lane Packet Refusal"
+(including "Fast empty HTTP review does not count"); acceptance outcome 4
+
+- [x] 1.1 Write the failing tests, all using an injected transport:
+  - `probe()` for `openrouter` sends `GET {base_url}/key`, and for `local` sends `GET /models`.
+  - 200 → `ok` with numeric budget fields.
+  - 401 → `auth_failed`; timeout → `probe_timeout`; connection error → `endpoint_unreachable`.
+  - A body with no `data` → budget `None`.
+  - Sentinel test: a transport that echoes the headers leaks nothing into the result, the
+    logs, or the exception text.
+- [x] 1.2 Implement `ProbeResult` and `OpenAICompatAdapter.probe(api_key, transport, timeout=10)`.
+  Add a GET-capable transport alongside the existing POST transport, using the default SSL
+  context (so `SSL_CERT_FILE` is honoured). Cite the OpenRouter docs URLs for `/key` in a
+  comment (source-driven-development).
+- [x] 1.3 Write the failing tests for cost capture:
+  - The request body includes `usage: {include: true}`.
+  - The response fields `usage.prompt_tokens`, `usage.completion_tokens` and `usage.cost` map
+    to the new `ReviewResult` fields.
+  - Without a cost, `cost_source == "estimated"`.
+- [x] 1.4 Add the optional `ReviewResult` fields `prompt_tokens`, `completion_tokens`,
+  `cost_usd`, `cost_source` and `spend_recorded` (set by task 3.10), all defaulting to `None`,
+  and implement the capture in `dispatch()`.
+- [x] 1.5 Write a failing test: `dispatch(..., tools_overflow=True)` returns
+  `packet_requires_tools` / `vendor_unavailable` with zero transport calls. Then implement the
+  `tools_overflow` keyword (default False).
+- [x] 1.6 Write failing tests: HTTP findings go through the same ingest pipeline as CLI findings.
+  Today `OpenAICompatAdapter.dispatch` only calls `CliVendorAdapter._parse_findings`. The tests,
+  each using an injected transport, cover:
+  - a fast `{"findings": []}` (under `empty_findings_min_seconds()`) → `success=False`,
+    `error="empty_findings_too_fast"`;
+  - a schema-invalid payload → `success=False`, `error_class=unknown`;
+  - a placeholder-only payload → `success=False`, `error="non_substantive_placeholder"`;
+  - a valid payload → findings coerced (`coerce_findings_payload`), stamped
+    `evidence_class: judgment` (`stamp_judgment_ingest`), and line-resolved against the packet diff,
+    exactly as on the CLI path.
+- [x] 1.7 Factor the CLI ingest steps (coerce → validate → judgment stamp → line resolve →
+  placeholder check → empty-findings floor) out of `CliVendorAdapter` into a shared helper in
+  `review_dispatcher.py`. Call it from both adapters. CLI behaviour must not change: the existing
+  `test_fast_empty_findings_are_unsuccessful` and the related ingest tests stay green.
+
+## 2. Lane roster
+
+**Files:** `agent-coordinator/agents.yaml`, `agent-coordinator/archetypes.yaml`,
+`agent-coordinator/routing.yaml` (append the `metered-api-cloud` tier only),
+`agent-coordinator/tests/test_agents_config.py`, `agent-coordinator/tests/test_archetypes_yaml.py`
+(add tests only)
+**Depends:** none
+**Specs:** parallel-infrastructure "OpenAI-Compatible Dispatcher Discovery"
+
+- [x] 2.1 Write failing tests:
+  - `openrouter-review` loads with `endpoint_kind: openrouter`, a `base_url`, no `cli`/`sdk`,
+    `archetypes: [reviewer]`, and `vendor_credentials: [openrouter]`.
+  - `get_dispatch_configs()` emits it.
+  - The `openrouter` provider resolves `premium`, `standard` and `economy` slugs, none with
+    publisher `anthropic`.
+  - `RoutingPolicy.cost_tier("cloud", "openrouter")` is not `None` (design D1), and
+    `cost_tier("local", "openrouter")` still returns `metered-api`.
+- [x] 2.2 Add the agent entry (design D1), the `openrouter` provider tier map, and the
+  `metered-api-cloud` tier (`location: cloud`, `endpoint_kinds: [openrouter]`), appended last to
+  `routing.yaml` `cost_policy.tiers`. Choose the
+  premium slug from the live OpenRouter model catalog: it must be non-Anthropic and preferably
+  a family not served by a host CLI. Record the catalog URL and the date in a YAML comment.
+- [x] 2.3 Run the registry projection tests (`test_registry_projection.py`,
+  `test_vendor_registry.py`, profile sync) and fix any projection assumption that every agent
+  carries a CLI or SDK block.
+
+## 3. Dispatcher discovery, probe wiring, family and fill rules
+
+**Files:** `skills/parallel-infrastructure/scripts/review_dispatcher.py` (excluding the
+`ReviewResult` dataclass, which group 1 owns), `skills/parallel-infrastructure/review_quorum_policy.json`
+(add `vendor_families` and `metered_lanes` only; do not touch `policies`),
+`skills/parallel-infrastructure/scripts/review_packet.py` (the tool-less packet builder only),
+`skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py`,
+`skills/parallel-infrastructure/scripts/tests/test_review_packet.py`,
+`skills/parallel-infrastructure/tests/test_check_vendors_api_lane.py` (new)
+**Depends:** 1, 2 (the roster is needed only for the integration test in 3.9; tests 3.1–3.8 use inline config dicts), 4 (the `spend_recorder.record()` interface, task 3.10)
+**Specs:** parallel-infrastructure "OpenAI-Compatible Dispatcher Discovery" (MODIFIED),
+"Dispatchable Vendor Verification" (MODIFIED), "Tool-less Lane Packet Refusal"
+
+- [x] 3.1 Write failing tests for the family rule:
+  - An `anthropic/` primary or fallback → `unverified` with reason `anthropic_family`.
+  - `codex` at tier 1 plus an `openai/` OpenRouter lane → `duplicate_model_family`.
+  - A vendor missing from `vendor_families` is never a duplicate.
+  - Two-pass order (design D2): a non-metered vendor that sorts after `openrouter` (for example
+    `pi`, mapped to `openai`) still makes an `openai/` OpenRouter lane a `duplicate_model_family`.
+- [x] 3.2 Add `vendor_families` and `metered_lanes {fill_target, review_reservation_usd}` to
+  `review_quorum_policy.json`, plus a loader. Implement the family rule in
+  `from_config_dict` / `discover_reviewers` (design D2).
+- [x] 3.3 Write failing tests for the fill rule. With `fill_target` 2:
+  - two non-metered lanes → no metered lane is selected;
+  - one non-metered lane → exactly one metered lane is selected.
+  
+  Also test that `dispatch_and_wait(include_lanes=...)` restricts dispatch.
+- [x] 3.4 Implement the two-pass selection (design D2): pass 1 for tier 1/2, pass 2 for tier-2.5
+  candidates in `agents.yaml` roster order. Then implement the metered fill selection (design D5)
+  and the `include_lanes` filter. Add a fill-rule test where the non-metered lane sorts after the
+  metered one.
+- [x] 3.5 Write failing tests for `_probe_mode` on API lanes, using an injected probe and an
+  injected coordinator-usage function:
+  - verified when the key limit leaves enough budget;
+  - `spend_ceiling_exceeded` when the coordinator has too little budget left;
+  - `spend_ceiling_unverifiable` when there is no ceiling source;
+  - `auth_failed` passes through;
+  - `lane_kinds` is present for every lane;
+  - no chat-completions call is made.
+- [x] 3.6 Implement the API-lane probe in `_probe_mode`. Resolve the key via `ApiKeyResolver`,
+  fetch coordinator usage through an injectable `GET /routing/usage` client (which fails soft
+  to "source unavailable"), apply the budget rule (design D4) through a reusable function that
+  `dispatch_and_wait` also calls per round (task 3.11), and emit `lane_kinds`. Keep
+  `probe_unsupported` for SDK lanes.
+- [x] 3.7 Extend the existing credential-sentinel test to cover `OPENROUTER_API_KEY` and an
+  OpenRouter lane with an echoing transport.
+- [x] 3.8 Write a failing test, then implement: `dispatch_and_wait` reads `tools_overflow` from
+  the packet sidecar next to `packet_path` and passes it to OpenAI-compatible adapters.
+- [x] 3.8a Write failing tests, then implement in `review_packet.py`: a `build_toolless_packet`
+  (design D6) and its `review-packet.toolless.meta.json` sidecar. Tests:
+  - For `review_type="plan"`, a branch whose full diff overflows `BUDGET_CHARS` yields a tool-less
+    packet with `tools_overflow: false` that contains the full `proposal.md`, `design.md`,
+    `tasks.md` and spec deltas.
+  - For `implementation`, the dropped files appear in `coverage.skipped`.
+  - `dispatch_and_wait` passes the tool-less body and flag to OpenAI-compatible adapters, and the
+    primary body to CLI lanes.
+- [x] 3.9 Integration test: with the repository's `agents.yaml`, an injected transport and no
+  `pi`/`codex` binaries on `PATH`, `--check-vendors --json` lists `openrouter` as verified and
+  maps it to `openrouter` in `lane_kinds`.
+- [x] 3.10 Write failing tests, then implement: `ReviewOrchestrator.dispatch_and_wait` calls
+  `spend_recorder.record()` once after every OpenAI-compatible result with `endpoint_kind:
+  openrouter` that made an HTTP request, and sets `ReviewResult.spend_recorded` to its
+  `recorded` value. The row's `change_id` (for the spool path) and `work_unit_ref` come from a
+  new optional `dispatch_and_wait` keyword `spend_context: SpendContext | None` (design D4); a
+  metered lane with no `spend_context` is not dispatched and returns `vendor_unavailable`
+  (`spend_context_missing`). This covers every dispatch path: `converge()` with `ReviewOrchestrator` on a
+  host where the fill rule (D5) selected the metered lane, the `/parallel-review-*` one-shot
+  dispatch, and `CompositeOrchestrator` (which calls `dispatch_and_wait`). Tests: a host-path
+  dispatch with an injected transport and an injected recorder records one row; a refused
+  (`packet_requires_tools`) or budget-skipped lane records nothing; a recorder returning
+  `recorded=False` yields `spend_recorded=False`; a metered lane with no `spend_context` makes no
+  HTTP request and returns `spend_context_missing`; `/parallel-review-*` passes a one-shot
+  `SpendContext`.
+- [x] 3.11 Write failing tests, then implement the per-round budget re-check (design D4) in
+  `ReviewOrchestrator.dispatch_and_wait`: before dispatching a metered lane it re-runs the
+  probe's budget function (task 3.6); a lane below `review_reservation_usd` is not dispatched
+  and is returned `vendor_unavailable` (`spend_ceiling_exceeded`). For the coordinator source it
+  counts the change's unreplayed spool total as used (design D4). Tests: budget available at probe,
+  exhausted before the second dispatch → that dispatch skips the lane, records no spend; key limit
+  null, coordinator remaining 1.5, spool total 1.0, reservation 1.0 → the lane is skipped.
+
+## 4. Spend recording route and client
+
+**Files:** `agent-coordinator/src/model_routing/api.py`, `agent-coordinator/src/model_routing/ledger.py`
+(an idempotent lookup only), `agent-coordinator/tests/model_routing/test_spend_route.py` (new),
+`skills/parallel-infrastructure/scripts/spend_recorder.py` (new),
+`skills/tests/parallel-infrastructure/test_spend_recorder.py` (new)
+**Depends:** none (the interface is the request body in the model-routing spec)
+**Specs:** model-routing "Review Spend Recording Route"; parallel-infrastructure "Metered
+Review Lane Spend Accounting" (record, spool and replay part)
+
+- [x] 4.1 Write failing route tests: 201 on insert, 200 on a duplicate `generation_id`, 401
+  without a key, 422 on a negative `actual_usd` or an unknown field, and `GET /routing/usage`
+  reflects the row.
+- [x] 4.2 Implement the `SpendRecordRequest` Pydantic model (`extra="forbid"`), the
+  `POST /routing/spend` route, and `LedgerService.find_by_generation_id`. No database
+  migration is needed because `generation_id` already exists.
+- [x] 4.3 Write failing client tests:
+  - `record()` posts the row.
+  - On a connection error or 403 it appends to `reviews/spend-spool.jsonl` and returns
+    `recorded=False`.
+  - `replay --change-id` is idempotent and empties the spool.
+  - No API key value appears in the spool.
+- [x] 4.4 Implement `spend_recorder.py`: `record()`, `replay()`, and a CLI. It authenticates
+  with the existing coordination-bridge credentials (`COORDINATION_API_URL`/`COORDINATION_API_KEY`,
+  read only inside the bridge's credential path).
+
+## 5. Convergence: composite agent lane and honest mid-run loss
+
+**Files:** `skills/autopilot/scripts/agent_lane.py`, `skills/autopilot/scripts/convergence_loop.py`,
+`skills/autopilot/scripts/runner.py` (only to add `metered_spend_unrecorded` to
+`record-degradation` choices), `openspec/schemas/dispatch-result.schema.json` (only the enum
+value), `skills/tests/autopilot/test_agent_lane.py`, `skills/tests/autopilot/test_convergence_loop_capability.py` (new)
+**Depends:** 3, 4
+**Specs:** skill-workflow "Honest Review Quorum" (MODIFIED), "Composite Agent-Lane Review";
+parallel-infrastructure "Metered Review Lane Spend Accounting" (checkpoint part)
+
+- [x] 5.1 Write failing tests: in round 2 the OpenRouter lane fails `vendor_unavailable` →
+  `capability_unavailable` with `missing_lanes == ["openrouter"]`; an `unknown` failure →
+  `quorum_lost`; a verified lane with no result and no recorded failure → `quorum_lost`
+  (`missing_lanes` = verified − succeeded, never vacuous).
+- [x] 5.2 Implement the mid-run capability mapping in `converge()` (design D7). Write
+  `generation_id`, `prompt_tokens`, `completion_tokens`, `cost_usd` and `cost_source` into the
+  round checkpoint's vendor index.
+- [x] 5.3 Add `metered_spend_unrecorded` to the `Degradation.code` enum in
+  `dispatch-result.schema.json` and to the `runner.py record-degradation` choices. Update the
+  schema fixture test.
+- [x] 5.4 Write failing tests for the `CompositeOrchestrator`:
+  - Run against a fixture change with an injected transport and a scripted handshake.
+  - `converge()` receives `min_quorum=2`, the checkpoint holds both lane files, and
+    `quorum_received == 2`.
+  - Consensus findings attribute both lane ids.
+  - `--verified-lanes claude_code` alone → `capability_unavailable` with no handshake files.
+- [x] 5.5 Implement `--verified-lanes`, `CompositeOrchestrator` (the handshake lane plus
+  `ReviewOrchestrator.dispatch_and_wait(include_lanes=...)` run concurrently, with the result
+  callback forwarded), and quorum-policy resolution from the verified count. For each
+  metered result whose `spend_recorded` is `False` (recorded by the dispatcher, task 3.10),
+  record the `metered_spend_unrecorded` degradation through the result payload. `agent_lane`
+  does not call `spend_recorder.record()` itself. Update `_review_body` to list the lanes.
+- [x] 5.6 Write failing tests, then implement:
+  - `converge()` accepts an optional `phase` and, when it is set, passes
+    `spend_context=SpendContext(change_id, "<change_id>:<phase>:round-<n>")` to `dispatch_and_wait`
+    (via `_accepts_kwarg`; the keyword and dataclass are the ones task 3.10 adds);
+    `agent_lane.py` passes its `--phase`.
+  - `converge()` builds the tool-less packet (task 3.8a) when the primary packet overflows, and
+    passes the tool-less packet as `dispatch_and_wait(..., toolless_packet_path=...)` (design D6).
+  - `agent_lane.py` `result.json` carries `missing_lanes` (from `ConvergenceResult.missing_lanes`),
+    `lanes` (the lane ids that returned a successful result), `quorum_received`, a per-lane
+    `{model_used, generation_id, cost_usd, cost_source}` map, and `degradations` (including
+    `metered_spend_unrecorded`). Task 6.4's park and degradation rules read these fields.
+  - After each run, `agent_lane.py` writes `ConvergenceResult.consensus` (with `quorum_received`)
+    to `openspec/changes/<id>/reviews/`, using one file per phase so the two implementation phases
+    do not collide: `consensus-plan.json` (PLAN_REVIEW), `consensus-impl-review.json`
+    (IMPL_REVIEW), `consensus-val-review.json` (VAL_REVIEW). This matches the skill-workflow
+    "Composite Agent-Lane Review" requirement. The D9 evidence and task 7.2 cite
+    `consensus-plan.json`. `converge()` itself never writes these files.
+- [x] 5.7 Write a failing test, then make it pass: with the dispatcher's budget re-check (task
+  3.11) injected to fail before round 2, `converge()` through `CompositeOrchestrator` ends
+  `capability_unavailable` with `missing_lanes == ["openrouter"]` (design D7). `converge()`
+  itself gains no budget logic.
+
+## 6. Supervisor ranking, apply-time replay, and worker protocol
+
+**Files:** `skills/supervise/scripts/execution.py`, `skills/tests/supervise/test_execution_profile.py`,
+`skills/autopilot/SKILL.md` (the review-section protocol text and the host-path `converge(...)`
+examples only)
+**Depends:** 3 (the `lane_kinds` shape), 4 (the replay CLI)
+**Specs:** supervise "Execution Profile and Review Requirements" (MODIFIED)
+
+- [x] 6.1 Write failing tests: `lane_kinds` ranks `openrouter` after `vendor-cli`; a missing
+  `lane_kinds` falls back to the old inference.
+- [x] 6.2 Implement the `rank()` change in `resolve_execution_profile` (design D8).
+- [x] 6.3 Write failing tests, then implement: `ExecutionAdapter.apply` runs
+  `spend_recorder.py replay` once when a `metered_spend_unrecorded` degradation is present,
+  reports the replayed count, and never fails the apply on a replay error.
+- [x] 6.4 Update the autopilot `SKILL.md` review section with these rules:
+  - In cloud, run `agent_lane.py converge --verified-lanes <each lane from execution_profile.lanes.review>`.
+  - A `capability_unavailable` result maps to `runner.py park --kind capability_unavailable`.
+  - Record the degradation `metered_spend_unrecorded` when the result reports it.
+  - Every host-path `converge(...)` example (the PLAN_REVIEW inline fallback and the IMPL_REVIEW
+    and VAL_REVIEW equivalents) passes `phase="<PLAN_REVIEW|IMPL_REVIEW|VAL_REVIEW>"`. Without it
+    `converge()` sends no `spend_context`, and a metered lane that D5 selects on a host is refused
+    with `spend_context_missing` (task 3.10). Extend the SKILL guard test to assert that each host
+    `converge(` example names `phase=`.
+  
+  Keep the env-probing guard test green.
+
+## 7. Cloud end-to-end evidence and retirement of the temporary policy
+
+**Files:** `openspec/changes/openrouter-review-lane/evidence/cloud-quorum-run.md` (new),
+`skills/parallel-infrastructure/review_quorum_policy.json` (`policies` entry),
+`TRUST_POSTURE.md`, `skills/autopilot/SKILL.md` (single-vendor references),
+`docs/guides/` (cloud setup note), `skills/tests/parallel-infrastructure/test_quorum_policy_retirement.py` (new)
+**Depends:** 1–6 merged on the feature branch
+**Specs:** skill-workflow "Cloud Single-Vendor Policy Retirement"; acceptance outcome 1
+
+- [ ] 7.1 Document the cloud setup in the guide that covers cloud environments: the
+  `OPENROUTER_API_KEY` environment secret, the egress allowlist entry `openrouter.ai`,
+  `SSL_CERT_FILE` for the agent proxy CA, and the ceiling sources (a coordinator
+  `ROUTING_MONTHLY_CEILING_USD > 0`, or an OpenRouter key with a credit limit).
+- [ ] 7.2 This step is run by the operator in a provisioned cloud container. Run `/autopilot`
+  on a fixture change through PLAN_REVIEW. Write `evidence/cloud-quorum-run.md` with:
+  - the `--check-vendors --json` report (verified lanes, `lane_kinds`, no secrets);
+  - `min_quorum` from `review_requirements`;
+  - the `consensus-plan.json` lane attribution;
+  - the ledger or spool `generation_id`, model and cost.
+- [ ] 7.3 Write the guard test `test_quorum_policy_retirement.py`:
+  - It fails if the cloud policy entry is absent while the evidence file is missing or has no
+    `generation_id`.
+  - It asserts that `TRUST_POSTURE.md` has no "Review quorum in cloud containers" section.
+  - It asserts that `resolve_quorum_policy(cloud_container, 1)` returns quorum 2.
+- [ ] 7.4 Delete the `cloud-container-single-vendor-2026-10-09` entry and the `TRUST_POSTURE.md`
+  section. Remove the cloud single-vendor guidance from `skills/autopilot/SKILL.md`. Check
+  whether `posture_digest` changes, and record the result in the session log.
+- [ ] 7.5 Run `skills/install.sh` to sync the runtime copies, the full `skills/` and
+  `agent-coordinator` test sweeps (`pytest -m "not e2e and not integration"`), `ruff`,
+  `mypy --strict` on the touched coordinator modules, and `openspec validate openrouter-review-lane --strict`.
+
+## 8. Implementation iteration
+
+- [x] 8.1 Carry the `metered-api-cloud` tier in this change's `contracts/config/` schemas and
+  revert the archived routing-cost-policy schema and the task-router change's `routing.schema.json`.
+- [x] 8.2 Add the `configuration` spec delta that admits an optional `openrouter` key in the
+  provider model map, with a schema test.
+- [x] 8.3 Make the `generation_id` dedupe in `POST /routing/spend` atomic (unique constraint plus
+  `ON CONFLICT DO NOTHING`) and add a concurrent-duplicate test.
+- [x] 8.4 Suppress the misleading "Cross-vendor review NOT CHECKED" stderr inside the composite lane.
+- [x] 8.5 Find and fix the shared-state leak behind the order-dependent
+  `test_relayed_gate_answer` stale-ref test.
+- [x] 8.6 Record the as-built notes in `design.md` (D1 credentials, D5 fill rule, spend on empty
+  findings, null `phase_archetype`).
+- [ ] 8.7 Follow-up, out of scope here: make endpoint-only agents eligible to the task-router
+  resolver, which today excludes `openrouter-review` as `lane:dispatch-mode-ineligible`.
+
+## Traceability
+
+| Requirement | Tasks |
+|---|---|
+| parallel-infrastructure: OpenAI-Compatible Dispatcher Discovery | 2.1–2.3, 3.1–3.4, 3.9 |
+| parallel-infrastructure: Dispatchable Vendor Verification | 1.1–1.2, 3.5–3.7, 3.9 |
+| parallel-infrastructure: Metered Review Lane Spend Accounting | 1.3–1.4, 3.10–3.11, 4.3–4.4, 5.2, 5.5–5.7, 6.4 |
+| parallel-infrastructure: Tool-less Lane Packet Refusal | 1.5–1.7, 3.8, 3.8a, 5.6 |
+| skill-workflow: Honest Review Quorum | 5.1–5.3 |
+| skill-workflow: Composite Agent-Lane Review | 5.4–5.6, 6.4 |
+| skill-workflow: Cloud Single-Vendor Policy Retirement | 5.6, 7.1–7.4 |
+| supervise: Execution Profile and Review Requirements | 6.1–6.3 |
+| configuration: Provider Model Mapping Configuration | 8.2 |
+| model-routing: Review Spend Recording Route | 4.1–4.2, 8.3 |
+| Acceptance outcome 4 (schema-conformant HTTP findings, synthesized like CLI lanes) | 1.6–1.7 |
diff --git a/openspec/schemas/dispatch-result.schema.json b/openspec/schemas/dispatch-result.schema.json
index e7168bc2..9035488c 100644
--- a/openspec/schemas/dispatch-result.schema.json
+++ b/openspec/schemas/dispatch-result.schema.json
@@ -239,7 +239,8 @@
             "coordinator_projection_forbidden",
             "audit_sink_failed",
             "phase_fallback_inline",
-            "handoff_local_fallback"
+            "handoff_local_fallback",
+            "metered_spend_unrecorded"
           ]
         },
         "phase": {"type": "string", "minLength": 1, "maxLength": 64},
diff --git a/openspec/schemas/provider-model-map.schema.json b/openspec/schemas/provider-model-map.schema.json
index a65e2429..c88b3fb1 100644
--- a/openspec/schemas/provider-model-map.schema.json
+++ b/openspec/schemas/provider-model-map.schema.json
@@ -73,7 +73,8 @@
           "antigravity",
           "grok",
           "pi",
-          "local"
+          "local",
+          "openrouter"
         ]
       },
       "additionalProperties": {
diff --git a/skills/autopilot/SKILL.md b/skills/autopilot/SKILL.md
index 40b695c5..ce0ccb83 100644
--- a/skills/autopilot/SKILL.md
+++ b/skills/autopilot/SKILL.md
@@ -130,10 +130,16 @@ carries no token.
   `loop-state.json`, emit the result, and stop. The command is stored redacted.
 - **Probing.** Run only `execution_profile.probe_command`. Never read environment
   variables or credentials to discover capabilities.
+- **Review in cloud.** Run each review phase through `agent_lane.py converge
+  --phase <phase>` with one `--verified-lanes <lane>` per entry of the marker's
+  `execution_profile.lanes.review` and one `--counting-lanes <lane>` per entry of
+  `review_requirements.counting_lanes` (see *Cloud review lanes* under Detect CLI mode).
+  A `capability_unavailable` result maps to `runner.py park --kind capability_unavailable`
+  with its `missing_lanes`; record `metered_spend_unrecorded` when the result reports it.
 - **Degradations.** Record every degraded path with `runner.py record-degradation`
   (closed codes only: `single_vendor_review`, `review_skipped`,
   `coordinator_projection_forbidden`, `audit_sink_failed`, `phase_fallback_inline`,
-  `handoff_local_fallback`).
+  `handoff_local_fallback`, `metered_spend_unrecorded`).
 - **Result.** When the loop is terminal or parked, commit `loop-state.json`, then
   `runner.py emit-result <change-id> --dispatch-id <id> --generation <N> --attempt <A>`
   (exit 5: not terminal or parked; exit 2: loop state uncommitted). Commit the file it
@@ -217,6 +223,39 @@ python3 "<skill-base-dir>/scripts/runner.py" record-degradation <change-id> \
   --code single_vendor_review --phase <phase> --detail "vendor=<the one lane>"
 ```
 
+*Cloud review lanes (dispatched child in a cloud container).* The running agent
+serves the `claude_code` lane; any other verified lane (for example `openrouter`)
+is dispatched beside it by the composite agent lane. Pass every lane in the
+marker's `execution_profile.lanes.review`, one `--verified-lanes` per lane, and every
+lane in `review_requirements.counting_lanes`, one `--counting-lanes` per lane — so a
+counting lane that did not verify shows up in `missing_lanes`. Never add a lane the
+marker does not list, and never probe for one:
+
+```bash
+python3 "<skill-base-dir>/scripts/agent_lane.py" converge \
+  --change-id <change-id> --phase <PLAN_REVIEW|IMPL_REVIEW|VAL_REVIEW> \
+  --proto-dir <protocol dir> --base-ref origin/<pr-base> --model <model id> \
+  --verified-lanes <lane> [--verified-lanes <lane> ...] \
+  --counting-lanes <lane> [--counting-lanes <lane> ...]
+```
+
+Then read the protocol directory's `result.json`:
+
+- A `capability_unavailable` result maps to `runner.py park --kind capability_unavailable`:
+  park with `--phase <phase>` and one `--missing-lane` per entry of the result's
+  `missing_lanes`, commit `loop-state.json`, emit the result, and stop. This covers a
+  lane that verified at launch and lost budget or auth mid-run. Any other
+  non-converged reason (`quorum_lost`, `max_rounds`, `stalled`) follows the phase's
+  normal not-converged path.
+- When the result's `degradations` include `metered_spend_unrecorded` (a metered
+  lane's spend was spooled because the coordinator write failed), record it, once per
+  entry, before emitting the result. The supervisor replays the spool during `apply`.
+
+```bash
+python3 "<skill-base-dir>/scripts/runner.py" record-degradation <change-id> \
+  --code metered_spend_unrecorded --phase <phase> --detail "<the result entry's detail>"
+```
+
 *Standalone run (no marker).* Keep today's probe, and record the degradation when
 review is disabled below quorum:
 
@@ -576,6 +615,7 @@ from convergence_loop import converge
 result = converge(
     change_id=change_id,
     review_type="plan",
+    phase="PLAN_REVIEW",  # required: names the spend_context for metered lanes
     artifacts_dir=change_dir,
     worktree_path=worktree_path,
     agents_yaml_path=agents_yaml_path,
@@ -587,6 +627,11 @@ result = converge(
 )
 ```
 
+Every host-path `converge(...)` call passes `phase=` (here `"PLAN_REVIEW"`; the
+IMPL_REVIEW and VAL_REVIEW fallbacks below pass theirs). Without it `converge()`
+sends no `spend_context`, and a metered lane selected on a host is refused with
+`spend_context_missing`.
+
 Then run `apply-outcome` to record `phase_archetype = null`.
 
 **If converged**: Report findings summary, transition to IMPLEMENT.
@@ -807,7 +852,27 @@ the dispatched agent executes `converge()` as the whole review phase.
 **Fallback**: If `archetype: null` OR the dispatch adapter is unavailable, run the
 inline path — invoke the convergence loop with `fix_mode="targeted"`
 and a `post_fix_validator` callback for scoped pytest/mypy/openspec
-checks. Then run `apply-outcome` to record `phase_archetype = null`.
+checks:
+
+```python
+from convergence_loop import converge
+result = converge(
+    change_id=change_id,
+    review_type="implementation",
+    phase="IMPL_REVIEW",  # required: names the spend_context for metered lanes
+    artifacts_dir=change_dir,
+    worktree_path=worktree_path,
+    agents_yaml_path=agents_yaml_path,
+    max_rounds=3,
+    min_quorum=2,
+    fix_mode="targeted",
+    fix_callback=apply_impl_fixes_targeted,
+    post_fix_validator=run_scoped_checks,
+    memory_callback=write_memory,
+)
+```
+
+Then run `apply-outcome` to record `phase_archetype = null`.
 
 For **targeted implementation fixes** (IMPL_FIX sub-step, NOT a
 sub-agent dispatch): Look up the lead vendor from `package_authors`, use
@@ -880,8 +945,26 @@ as the whole VAL_REVIEW phase.
 
 **Fallback**: If `archetype: null` OR the dispatch adapter is unavailable, run the
 inline path — invoke the convergence loop with `review_type="implementation"`
-and `fix_mode="targeted"`, scoped to the validation evidence. Then run
-`apply-outcome` to record `phase_archetype = null`.
+and `fix_mode="targeted"`, scoped to the validation evidence:
+
+```python
+from convergence_loop import converge
+result = converge(
+    change_id=change_id,
+    review_type="implementation",
+    phase="VAL_REVIEW",  # required: names the spend_context for metered lanes
+    artifacts_dir=change_dir,
+    worktree_path=worktree_path,
+    agents_yaml_path=agents_yaml_path,
+    max_rounds=3,
+    min_quorum=2,
+    fix_mode="targeted",
+    fix_callback=apply_val_fixes_targeted,
+    memory_callback=write_memory,
+)
+```
+
+Then run `apply-outcome` to record `phase_archetype = null`.
 
 ### 8. SUBMIT_PR Phase
 
diff --git a/skills/autopilot/scripts/agent_lane.py b/skills/autopilot/scripts/agent_lane.py
index d3cf0ffe..f4ac9bd5 100644
--- a/skills/autopilot/scripts/agent_lane.py
+++ b/skills/autopilot/scripts/agent_lane.py
@@ -30,6 +30,7 @@ import json
 import logging
 import re
 import sys
+import threading
 import time
 from datetime import datetime, timezone
 from pathlib import Path
@@ -164,8 +165,106 @@ class AgentLaneOrchestrator:
         return [result]
 
 
+class CompositeOrchestrator:
+    """The handshake lane plus the dispatcher's other verified lanes (design D7).
+
+    Each round runs ``ReviewOrchestrator.dispatch_and_wait(include_lanes=...)``
+    in a thread while the handshake lane is served in this one, then returns
+    both result lists. The checkpoint callback is forwarded with the round's
+    full expected count. The review orchestrator is built on the first round
+    that has a lane for it, so a run ``converge()`` refuses below quorum
+    never builds one.
+    """
+
+    def __init__(
+        self,
+        agent_lane: AgentLaneOrchestrator,
+        *,
+        include_lanes: list[str] | tuple[str, ...] = (),
+        review_factory: Callable[[], Any] | None = None,
+    ) -> None:
+        self.agent_lane = agent_lane
+        self.include_lanes = list(include_lanes)
+        self._review_factory = review_factory
+        self._review: Any = None
+        self.results_by_round: list[list[Any]] = []
+
+    @property
+    def round(self) -> int:
+        return self.agent_lane.round
+
+    @property
+    def adapters(self) -> dict[str, Any]:
+        return getattr(self._review, "adapters", None) or {}
+
+    def _review_orchestrator(self) -> Any:
+        if self._review is None and self.include_lanes:
+            if self._review_factory is None:
+                raise RuntimeError(f"no review orchestrator for lanes {self.include_lanes}")
+            self._review = self._review_factory()
+        return self._review
+
+    def dispatch_and_wait(
+        self,
+        review_type: str,
+        dispatch_mode: str,
+        prompt: str,
+        cwd: Path,
+        timeout_seconds: float | None = None,
+        packet_path: Path | None = None,
+        result_callback: Callable[[Any, int], None] | None = None,
+        *,
+        toolless_packet_path: Path | None = None,
+        spend_context: Any = None,
+    ) -> list[Any]:
+        review = self._review_orchestrator()
+        expected = 1 + (len(self.include_lanes) if review is not None else 0)
+
+        def forward(result: Any, _count: int) -> None:
+            if result_callback is not None:
+                result_callback(result, expected)
+
+        review_results: list[Any] = []
+        review_errors: list[BaseException] = []
+
+        def run_review() -> None:
+            try:
+                review_results.extend(review.dispatch_and_wait(
+                    review_type, dispatch_mode, prompt, cwd,
+                    timeout_seconds=timeout_seconds,
+                    packet_path=packet_path,
+                    result_callback=forward,
+                    include_lanes=self.include_lanes,
+                    toolless_packet_path=toolless_packet_path,
+                    spend_context=spend_context,
+                    # the handshake lane reviews this round too, so the
+                    # dispatcher's subset is not a single-vendor review
+                    caller_vendors=(LANE,),
+                ))
+            except BaseException as exc:  # noqa: BLE001 - re-raised in the caller's thread
+                review_errors.append(exc)
+
+        thread = None
+        if review is not None:
+            thread = threading.Thread(target=run_review, name="composite-review", daemon=True)
+            thread.start()
+        try:
+            agent_results = self.agent_lane.dispatch_and_wait(
+                review_type, dispatch_mode, prompt, cwd,
+                timeout_seconds=timeout_seconds, packet_path=packet_path, result_callback=forward,
+            )
+        finally:
+            if thread is not None:
+                thread.join()
+        if review_errors:
+            raise review_errors[0]
+        results = [*agent_results, *review_results]
+        self.results_by_round.append(results)
+        return results
+
+
 def make_fix_callback(
-    handshake: Handshake, orchestrator: AgentLaneOrchestrator, *, fix_phase: str
+    handshake: Handshake, orchestrator: Any, *, fix_phase: str
 ) -> Callable[[list[dict[str, Any]], Path], None]:
     def fix_callback(payloads: list[dict[str, Any]], worktree_path: Path) -> None:
         n = orchestrator.round
@@ -195,11 +294,13 @@ def write_validation_review_section(report_path: Path, *, status: str, body: str
 
 
 def _review_body(result: dict[str, Any], *, min_quorum: int, policy: dict[str, Any]) -> str:
+    lanes = result.get("lanes") or [LANE]
+    listed = ", ".join(f"`{lane}`" for lane in lanes)
     lines = [
         f"- Result: converged in {result['rounds']} round(s) via `agent_lane.py converge`.",
-        f"- Lanes: `{LANE}` only (min_quorum={min_quorum}).",
+        f"- Lanes: {listed}{' only' if len(lanes) == 1 else ''} (min_quorum={min_quorum}).",
     ]
-    if policy.get("policy_id"):
+    if len(lanes) == 1 and policy.get("policy_id"):
         lines.append(
             f"- Degradation: `single_vendor_review` under quorum policy `{policy['policy_id']}`."
         )
@@ -208,6 +309,72 @@ def _review_body(result: dict[str, Any], *, min_quorum: int, policy: dict[str, A
     return "\n".join(lines)
 
 
+#: review phase -> the per-phase consensus file under ``<change>/reviews/``
+CONSENSUS_FILES: dict[str, str] = {
+    "PLAN_REVIEW": "consensus-plan.json",
+    "IMPL_REVIEW": "consensus-impl-review.json",
+    "VAL_REVIEW": "consensus-val-review.json",
+}
+
+
+def _resolve_lanes(
+    verified_lanes: list[str] | None, counting_lanes: list[str] | None
+) -> tuple[list[str], list[str]]:
+    """``claude_code`` first (the running agent serves it), then the rest, deduplicated."""
+    verified = list(dict.fromkeys([LANE, *(verified_lanes or [])]))
+    counting = list(dict.fromkeys(counting_lanes)) if counting_lanes else list(verified)
+    return verified, counting
+
+
+def _lane_of(result: Any, verified: list[str]) -> str:
+    for lane in verified:
+        if lane in (getattr(result, "vendor", None), getattr(result, "agent_id", None)):
+            return lane
+    return str(getattr(result, "vendor", None) or getattr(result, "agent_id", None))
+
+
+def _lane_report(
+    results_by_round: list[list[Any]], verified: list[str], *, phase: str
+) -> dict[str, Any]:
+    """The ``lanes`` / ``lane_results`` / ``degradations`` fields of ``result.json``.
+
+    ``lane_results`` holds each lane's most recent result. A metered result
+    whose spend the dispatcher could not record (``spend_recorded is False``)
+    becomes one ``metered_spend_unrecorded`` degradation per lane and round.
+    """
+    succeeded: set[str] = set()
+    lane_results: dict[str, dict[str, Any]] = {}
+    degradations: list[dict[str, Any]] = []
+    for n, results in enumerate(results_by_round, start=1):
+        for result in results:
+            lane = _lane_of(result, verified)
+            if getattr(result, "success", False):
+                succeeded.add(lane)
+            lane_results[lane] = {
+                "success": bool(getattr(result, "success", False)),
+                "model_used": getattr(result, "model_used", None),
+                "generation_id": getattr(result, "generation_id", None),
+                "cost_usd": getattr(result, "cost_usd", None),
+                "cost_source": getattr(result, "cost_source", None),
+            }
+            if getattr(result, "spend_recorded", None) is False:
+                degradations.append({
+                    "code": "metered_spend_unrecorded",
+                    "phase": phase,
+                    "detail": f"{lane} round {n} spend not recorded",
+                })
+    ordered = [lane for lane in verified if lane in succeeded]
+    ordered += sorted(succeeded - set(ordered))
+    return {"lanes": ordered, "lane_results": lane_results, "degradations": degradations}
+
+
+def _quorum_received(consensus: dict[str, Any] | None, results_by_round: list[list[Any]]) -> int:
+    if consensus and consensus.get("quorum_received") is not None:
+        return int(consensus["quorum_received"])
+    last = results_by_round[-1] if results_by_round else []
+    return sum(1 for result in last if getattr(result, "success", False))
+
+
 def run_converge(
     *,
     change_id: str,
@@ -223,7 +390,17 @@ def run_converge(
     poll_seconds: float = POLL_SECONDS,
     converge_fn: Callable[..., Any] | None = None,
     policy_fn: Callable[..., dict[str, Any]] | None = None,
+    verified_lanes: list[str] | None = None,
+    counting_lanes: list[str] | None = None,
+    review_orchestrator_factory: Callable[[], Any] | None = None,
 ) -> dict[str, Any]:
+    """Run one review phase through ``converge()`` and record ``result.json``.
+
+    ``verified_lanes`` are the review lanes the launch marker (or a
+    ``--check-vendors --json`` probe) verified; ``claude_code`` is always one.
+    The others are dispatched by a ``ReviewOrchestrator`` alongside the
+    handshake lane. ``counting_lanes`` default to the verified lanes.
+    """
     if phase not in PHASES:
         raise ValueError(f"phase must be one of {sorted(PHASES)}")
     review_type, fix_phase = PHASES[phase]
@@ -246,10 +423,25 @@ def run_converge(
         filename=str(handshake.dir / "converge.log"), level=logging.INFO,
         format="%(asctime)s %(name)s %(levelname)s %(message)s",
     )
-    policy = policy_fn(environment=environment, verified_review_lanes=1)
+    verified, counting = _resolve_lanes(verified_lanes, counting_lanes)
+    others = [lane for lane in verified if lane != LANE]
+    if review_orchestrator_factory is None:
+        def review_orchestrator_factory() -> Any:
+            from review_dispatcher import _orchestrator_for_dispatch
+
+            return _orchestrator_for_dispatch(None, worktree)
+
+    policy = policy_fn(environment=environment, verified_review_lanes=len(verified))
     min_quorum = int(policy["min_quorum"][phase])
-    orchestrator = AgentLaneOrchestrator(handshake, model=model)
-    handshake.event("converge_started", phase=phase, min_quorum=min_quorum, policy=policy)
+    orchestrator = CompositeOrchestrator(
+        AgentLaneOrchestrator(handshake, model=model),
+        include_lanes=others,
+        review_factory=review_orchestrator_factory,
+    )
+    handshake.event(
+        "converge_started", phase=phase, min_quorum=min_quorum, policy=policy,
+        verified_lanes=verified, counting_lanes=counting,
+    )
     try:
         res = converge_fn(
             change_id=change_id,
@@ -259,9 +451,10 @@ def run_converge(
             max_rounds=max_rounds,
             min_quorum=min_quorum,
             fix_mode=fix_mode,
-            verified_lanes=[LANE],
-            counting_lanes=[LANE],
+            verified_lanes=verified,
+            counting_lanes=counting,
             base_ref=base_ref,
+            phase=phase,
             fix_callback=make_fix_callback(handshake, orchestrator, fix_phase=fix_phase),
             memory_callback=lambda text: handshake.event("memory", text=text),
             orchestrator=orchestrator,
@@ -278,9 +471,21 @@ def run_converge(
             "validation_errors": res.validation_errors,
             "checkpoint_dir": str(res.checkpoint_dir) if res.checkpoint_dir else None,
             "summary": (res.consensus or {}).get("summary"),
+            "missing_lanes": getattr(res, "missing_lanes", None),
+            "quorum_received": _quorum_received(res.consensus, orchestrator.results_by_round),
+            **_lane_report(orchestrator.results_by_round, verified, phase=phase),
         }
+        if res.consensus is not None:
+            consensus_path = change_dir / "reviews" / CONSENSUS_FILES[phase]
+            consensus_path.parent.mkdir(parents=True, exist_ok=True)
+            consensus_path.write_text(json.dumps(res.consensus, indent=2, default=str), encoding="utf-8")
+            out["consensus_path"] = str(consensus_path)
     except Exception as exc:  # noqa: BLE001 - recorded for the agent, not swallowed silently
         out = {"phase": phase, "converged": False, "error": f"{type(exc).__name__}: {exc}"}
+        # Spend already sent but not recorded is still reported on a failed run.
+        degradations = _lane_report(orchestrator.results_by_round, verified, phase=phase)["degradations"]
+        if degradations:
+            out["degradations"] = degradations
 
     if phase == "VAL_REVIEW" and out.get("converged"):
         write_validation_review_section(
@@ -310,6 +515,16 @@ def _build_parser() -> argparse.ArgumentParser:
     cv.add_argument("--max-rounds", type=int, default=3)
     cv.add_argument("--fix-mode", default="targeted", choices=["inline", "targeted"])
     cv.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
+    cv.add_argument(
+        "--verified-lanes", action="append", default=None, metavar="LANE",
+        help="A verified review lane (repeatable): the launch marker's execution_profile.lanes.review, "
+        "or the --check-vendors --json verified list. claude_code is always included.",
+    )
+    cv.add_argument(
+        "--counting-lanes", action="append", default=None, metavar="LANE",
+        help="A lane that counts toward quorum (repeatable): the launch marker's "
+        "review_requirements.counting_lanes. Defaults to the verified lanes.",
+    )
     return parser
 
 
@@ -326,8 +541,12 @@ def main(argv: list[str] | None = None) -> int:
         max_rounds=args.max_rounds,
         fix_mode=args.fix_mode,
         timeout_seconds=args.timeout_seconds,
+        verified_lanes=args.verified_lanes,
+        counting_lanes=args.counting_lanes,
     )
-    print(json.dumps({k: out.get(k) for k in ("phase", "converged", "rounds", "reason", "error")}))
+    print(json.dumps(
+        {k: out.get(k) for k in ("phase", "converged", "rounds", "reason", "missing_lanes", "error")}
+    ))
     return 0 if out.get("converged") else 1
 
 
diff --git a/skills/autopilot/scripts/convergence_loop.py b/skills/autopilot/scripts/convergence_loop.py
index c61fba25..3bf55a3e 100644
--- a/skills/autopilot/scripts/convergence_loop.py
+++ b/skills/autopilot/scripts/convergence_loop.py
@@ -51,8 +51,10 @@ from consensus_synthesizer import (  # noqa: E402
     VendorResult,
 )
 from review_dispatcher import (  # noqa: E402
+    ErrorClass,
     ReviewOrchestrator,
     ReviewResult,
+    SpendContext,
     _orchestrator_for_dispatch,
 )
 from review_ledger import (  # noqa: E402
@@ -70,7 +72,11 @@ from review_ledger import (  # noqa: E402
     scoped_fix_payload,
     mark_addressed,
 )
-from review_packet import build_review_packet  # noqa: E402
+from review_packet import (  # noqa: E402
+    TOOLLESS_REVIEW_TYPES,
+    build_review_packet,
+    build_toolless_packet,
+)
 import fact_check as fact_check_module  # noqa: E402
 
 from convergence_disposition import (  # noqa: E402
@@ -121,9 +127,12 @@ class ConvergenceResult:
     escalate_findings: list[dict[str, Any]] | None = None
     validation_errors: list[str] | None = None
     checkpoint_dir: Path | None = None
-    # dispatch-contract D10: with reason="capability_unavailable", the counting
-    # lanes that were not verified. The caller records the park through
-    # `runner.py park`; this loop never writes loop state.
+    # dispatch-contract D10: with reason="capability_unavailable" before any
+    # dispatch, the counting lanes that were not verified. After a dispatched
+    # round falls below quorum (design D7), the verified lanes that returned no
+    # successful result, for both "capability_unavailable" and "quorum_lost".
+    # The caller records the park through `runner.py park`; this loop never
+    # writes loop state.
     missing_lanes: list[str] | None = None
 
 
@@ -351,6 +360,68 @@ def _accepts_kwarg(func: Callable[..., Any], name: str) -> bool:
     )
 
 
+def _vendor_index_entry(
+    result: ReviewResult, review_type: str, findings_array: list[Any],
+) -> dict[str, Any]:
+    """One checkpoint vendor-index entry, with the lane's generation and cost.
+
+    The metered fields are ``None`` for a lane that is not metered, so the
+    index reads the same for every lane.
+    """
+    return {
+        "name": result.vendor,
+        "findings_path": f"findings-{result.vendor}-{review_type}.json",
+        "finding_count": len(findings_array),
+        "unanchored_findings": result.unanchored_findings,
+        "model_used": result.model_used,
+        "generation_id": result.generation_id,
+        "prompt_tokens": result.prompt_tokens,
+        "completion_tokens": result.completion_tokens,
+        "cost_usd": result.cost_usd,
+        "cost_source": result.cost_source,
+    }
+
+
+# A lane that failed with one of these classes can no longer review in this
+# environment (design D7); any other shortfall is a lost quorum.
+_CAPABILITY_ERROR_CLASSES = frozenset({ErrorClass.UNAVAILABLE, ErrorClass.AUTH})
+
+
+def _lane_matches(lane: str, result: ReviewResult) -> bool:
+    return lane == result.vendor or lane == result.agent_id
+
+
+def _classify_quorum_shortfall(
+    results: list[ReviewResult], verified_lanes: list[str] | None,
+) -> tuple[str, list[str] | None]:
+    """Map a below-quorum round to ``(reason, missing_lanes)`` (design D7).
+
+    ``missing_lanes`` is the verified lanes that returned no successful
+    result. The round is ``capability_unavailable`` only when that set is
+    non-empty and every lane in it has a recorded ``vendor_unavailable`` or
+    ``auth_required`` failure. A lane that returned nothing, or failed for
+    any other reason, keeps it ``quorum_lost``. Without ``verified_lanes``
+    the legacy ``quorum_lost`` shape (no ``missing_lanes``) is kept.
+    """
+    if verified_lanes is None:
+        return "quorum_lost", None
+    verified = sorted(set(verified_lanes))
+    missing = [
+        lane for lane in verified
+        if not any(r.success and _lane_matches(lane, r) for r in results)
+    ]
+    capability_lost = bool(missing) and all(
+        any(
+            not r.success
+            and r.error_class in _CAPABILITY_ERROR_CLASSES
+            and _lane_matches(lane, r)
+            for r in results
+        )
+        for lane in missing
+    )
+    return ("capability_unavailable" if capability_lost else "quorum_lost"), missing
+
+
 def _write_review_checkpoint(
     checkpoint_dir: Path,
     results: list[ReviewResult],
@@ -392,12 +463,9 @@ def _write_review_checkpoint(
                 findings=findings_array,
                 reviewer_vendor=result.vendor,
             )
-            vendors_index.append({
-                "name": result.vendor,
-                "findings_path": f"findings-{result.vendor}-{review_type}.json",
-                "finding_count": len(findings_array),
-                "unanchored_findings": result.unanchored_findings,
-            })
+            vendors_index.append(
+                _vendor_index_entry(result, review_type, findings_array)
+            )
     cf_write_manifest(
         checkpoint_dir,
         review_type=review_type,
@@ -469,12 +537,7 @@ def _augment_manifest_with_fact_check(
         })
         if result.success and result.findings:
             findings_array = result.findings.get("findings", [])
-            entry = {
-                "name": result.vendor,
-                "findings_path": f"findings-{result.vendor}-{review_type}.json",
-                "finding_count": len(findings_array),
-                "unanchored_findings": result.unanchored_findings,
-            }
+            entry = _vendor_index_entry(result, review_type, findings_array)
             entry.update(fact_check_info.get(result.vendor, {}))
             vendors_index.append(entry)
     cf_write_manifest(
@@ -726,6 +789,7 @@ def converge(
     verified_lanes: list[str] | None = None,
     counting_lanes: list[str] | None = None,
     base_ref: str | None = None,
+    phase: str | None = None,
 ) -> ConvergenceResult:
     """Run the review-fix convergence loop.
 
@@ -770,6 +834,14 @@ def converge(
         base_ref: Ref the review packet diffs against. ``None`` (default)
             keeps the packet builder's ``DEFAULT_BASE_REF``; a stacked branch
             passes its PR base (e.g. ``origin/openspec/<parent>``).
+        phase: The autopilot review phase (e.g. ``PLAN_REVIEW``). When set,
+            each round passes ``spend_context=SpendContext(change_id,
+            "<change_id>:<phase>:round-<n>")`` to an orchestrator that accepts
+            it, so metered lanes can attribute their spend (design D4).
+
+    A primary packet whose meta reports ``tools_overflow`` also gets a
+    tool-less companion packet, passed as ``toolless_packet_path`` to an
+    orchestrator that accepts it (design D6).
 
     Returns:
         ConvergenceResult with convergence status and details.
@@ -821,16 +893,17 @@ def converge(
 
         # 2a. Pack the review input, then dispatch.
         checkpoint_dir = artifacts_dir / ".review-cache" / f"round-{round_num}"
-        packet_path, _packet_meta = build_review_packet(
-            change_id=change_id,
-            round_num=round_num,
-            artifacts_dir=artifacts_dir,
-            worktree_path=worktree_path,
-            output_dir=checkpoint_dir,
-            last_fix_diff=last_fix_diff if round_num > 1 else None,
-            ledger=ledger,
+        packet_inputs: dict[str, Any] = {
+            "change_id": change_id,
+            "round_num": round_num,
+            "artifacts_dir": artifacts_dir,
+            "worktree_path": worktree_path,
+            "output_dir": checkpoint_dir,
+            "last_fix_diff": last_fix_diff if round_num > 1 else None,
+            "ledger": ledger,
             **({"base_ref": base_ref} if base_ref is not None else {}),
-        )
+        }
+        packet_path, packet_meta = build_review_packet(**packet_inputs)
         prompt = packet_path.read_text(encoding="utf-8")
         dispatch_kwargs: dict[str, Any] = {
             "review_type": review_type,
@@ -841,6 +914,21 @@ def converge(
         }
         if _accepts_kwarg(orchestrator.dispatch_and_wait, "packet_path"):
             dispatch_kwargs["packet_path"] = packet_path
+        if (
+            (packet_meta or {}).get("tools_overflow")
+            and review_type in TOOLLESS_REVIEW_TYPES
+            and _accepts_kwarg(orchestrator.dispatch_and_wait, "toolless_packet_path")
+        ):
+            toolless_path, _toolless_meta = build_toolless_packet(
+                review_type=review_type, **packet_inputs,
+            )
+            dispatch_kwargs["toolless_packet_path"] = toolless_path
+        if phase is not None and _accepts_kwarg(
+            orchestrator.dispatch_and_wait, "spend_context"
+        ):
+            dispatch_kwargs["spend_context"] = SpendContext(
+                change_id, f"{change_id}:{phase}:round-{round_num}",
+            )
         checkpointed: dict[str, ReviewResult] = {}
         checkpoint_lock = threading.Lock()
 
@@ -900,16 +988,18 @@ def converge(
         # 2b. Check quorum
         successful = [r for r in results if r.success]
         if len(successful) < min_quorum:
+            reason, missing = _classify_quorum_shortfall(results, verified_lanes)
             logger.warning(
-                "Quorum lost: %d/%d (need %d)",
-                len(successful), len(results), min_quorum,
+                "Quorum shortfall (%s): %d/%d (need %d); missing %s",
+                reason, len(successful), len(results), min_quorum, missing,
             )
             return ConvergenceResult(
                 converged=False,
                 rounds=round_num,
-                reason="quorum_lost",
+                reason=reason,
                 validation_errors=all_validation_errors or None,
                 checkpoint_dir=latest_checkpoint_dir,
+                missing_lanes=missing,
             )
 
         # 2b.5. Diff-grounded fact-check, after the durable raw checkpoint
diff --git a/skills/parallel-infrastructure/review_quorum_policy.json b/skills/parallel-infrastructure/review_quorum_policy.json
index 5446e53c..8924f940 100644
--- a/skills/parallel-infrastructure/review_quorum_policy.json
+++ b/skills/parallel-infrastructure/review_quorum_policy.json
@@ -2,6 +2,17 @@
   "schema_version": 1,
   "description": "Review quorum per execution environment, as data (dispatch-contract D10). The supervisor copies the resolved entry into every request's review_requirements; a worker never lowers a quorum itself. A single-lane review is detected only by lanes failing to dispatch, never by reading environment variables or credentials, and records the degradation single_vendor_review (phase, vendor).",
   "default_min_quorum": 2,
+  "vendor_families": {
+    "claude_code": "anthropic",
+    "codex": "openai",
+    "antigravity": "google",
+    "grok": "xai"
+  },
+  "metered_lanes": {
+    "description": "Design D5 (openrouter-review-lane): a metered (OpenRouter) review lane is added only while fewer than fill_target non-metered lanes are selected. Each round reserves review_reservation_usd against the remaining spend ceiling before dispatch.",
+    "fill_target": 2,
+    "review_reservation_usd": 1.0
+  },
   "policies": [
     {
       "id": "cloud-container-single-vendor-2026-10-09",
diff --git a/skills/parallel-infrastructure/scripts/openai_compat_adapter.py b/skills/parallel-infrastructure/scripts/openai_compat_adapter.py
index 0388e6e2..0b96a531 100644
--- a/skills/parallel-infrastructure/scripts/openai_compat_adapter.py
+++ b/skills/parallel-infrastructure/scripts/openai_compat_adapter.py
@@ -20,9 +20,12 @@ classification so it drops into the same dispatch chain.
 from __future__ import annotations
 
 import json
+import socket
+import ssl
 import time
 import urllib.error
 import urllib.request
+from dataclasses import dataclass
 from pathlib import Path
 from typing import Any, Callable
 
@@ -30,7 +33,11 @@ from review_dispatcher import (  # type: ignore[import-untyped]
     CliVendorAdapter,
     ErrorClass,
     ReviewResult,
+    _coverage_quorum_threshold,
+    _extract_diff_from_prompt,
+    _extract_selected_files_from_prompt,
     classify_error,
+    ingest_findings_output,
 )
 
 # transport(url, headers, body, timeout) -> parsed JSON response dict
@@ -50,6 +57,92 @@ def _default_transport(
         return json.loads(resp.read().decode("utf-8"))
 
 
+# get_transport(url, headers, timeout) -> (http_status, parsed JSON body or None).
+# Raises on timeout / connection failure; an HTTP error status is *returned*, not
+# raised, so the probe can classify it without ever touching the response text.
+GetTransport = Callable[[str, "dict[str, str]", int], "tuple[int, dict[str, Any] | None]"]
+
+
+def _default_get_transport(
+    url: str, headers: dict[str, str], timeout: int
+) -> tuple[int, dict[str, Any] | None]:
+    """Real GET transport (stdlib urllib). Never exercised in unit tests.
+
+    Uses the default SSL context, which honours ``SSL_CERT_FILE`` /
+    ``SSL_CERT_DIR`` (needed behind the cloud egress proxy's CA bundle).
+    """
+    req = urllib.request.Request(url, headers=headers, method="GET")
+    context = ssl.create_default_context()
+    try:
+        with urllib.request.urlopen(  # noqa: S310 (trusted base_url)
+            req, timeout=timeout, context=context
+        ) as resp:
+            status = resp.status
+            raw = resp.read()
+    except urllib.error.HTTPError as exc:
+        # Discard the error body unread: it may echo request details.
+        exc.close()
+        return exc.code, None
+    try:
+        body = json.loads(raw.decode("utf-8"))
+    except (UnicodeDecodeError, json.JSONDecodeError):
+        return status, None
+    return status, body if isinstance(body, dict) else None
+
+
+# Probe reasons (design D3). The spend_ceiling_* reasons are applied by the
+# dispatcher's budget check on top of a successful probe (group 3), not here.
+PROBE_AUTH_FAILED = "auth_failed"
+PROBE_TIMEOUT = "probe_timeout"
+PROBE_ENDPOINT_UNREACHABLE = "endpoint_unreachable"
+
+_BUDGET_FIELDS = ("limit", "usage", "limit_remaining")
+
+# Dispatch refusal for a packet whose sidecar has tools_overflow: true (D6).
+PACKET_REQUIRES_TOOLS = "packet_requires_tools"
+
+
+@dataclass(frozen=True)
+class ProbeResult:
+    """Outcome of an authenticated no-op probe (design D3).
+
+    ``budget`` holds only the numeric OpenRouter key fields ``limit``,
+    ``usage`` and ``limit_remaining`` (each a float, or None when absent or
+    non-numeric). It is None for local endpoints and for an OpenRouter body
+    with no ``data`` object. Nothing else from the response is retained.
+    """
+
+    ok: bool
+    reason: str | None = None
+    budget: dict[str, float | None] | None = None
+
+
+def _numeric(value: Any) -> float | None:
+    if isinstance(value, bool) or not isinstance(value, (int, float)):
+        return None
+    return float(value)
+
+
+def _extract_budget(body: dict[str, Any] | None) -> dict[str, float | None] | None:
+    data = body.get("data") if isinstance(body, dict) else None
+    if not isinstance(data, dict):
+        return None
+    return {name: _numeric(data.get(name)) for name in _BUDGET_FIELDS}
+
+
+def _int_or_none(value: Any) -> int | None:
+    if isinstance(value, bool) or not isinstance(value, int):
+        return None
+    return value
+
+
+def _is_timeout(exc: BaseException) -> bool:
+    if isinstance(exc, (TimeoutError, socket.timeout)):
+        return True
+    reason = getattr(exc, "reason", None)
+    return isinstance(reason, (TimeoutError, socket.timeout))
+
+
 class OpenAICompatAdapter:
     """Dispatch to an OpenAI-compatible endpoint (OpenRouter or local)."""
 
@@ -89,15 +182,61 @@ class OpenAICompatAdapter:
         return headers
 
     def build_request(self, prompt: str, model: str) -> dict[str, Any]:
-        return {
+        body: dict[str, Any] = {
             "model": model,
             "messages": [{"role": "user", "content": prompt}],
             "temperature": 0,
         }
+        if self.endpoint_kind == "openrouter":
+            # Inline usage accounting: the response then carries usage.cost (D4).
+            # https://openrouter.ai/docs/use-cases/usage-accounting
+            body["usage"] = {"include": True}
+        return body
 
     def _endpoint_url(self) -> str:
         return f"{self.base_url}/chat/completions"
 
+    def _probe_url(self) -> str:
+        # OpenRouter: GET /api/v1/key returns the calling key's credit
+        # ``limit``, ``usage`` and ``limit_remaining`` under ``data`` and costs
+        # nothing. Docs: https://openrouter.ai/docs/api-reference/limits
+        # (not re-fetched on 2026-10-21: openrouter.ai unreachable from the build sandbox).
+        # Local (Ollama/vLLM): GET /v1/models is the cheapest authenticated no-op.
+        if self.endpoint_kind == "openrouter":
+            return f"{self.base_url}/key"
+        return f"{self.base_url}/models"
+
+    def probe(
+        self,
+        api_key: str | None,
+        transport: GetTransport | None = None,
+        timeout: int = 10,
+    ) -> ProbeResult:
+        """Authenticated, zero-cost dry probe of the endpoint (design D3).
+
+        Sends exactly one GET (``/key`` for OpenRouter, ``/models`` for local
+        endpoints) and never a chat completion. The response is parsed in
+        memory and only the numeric budget fields are kept; no header, key,
+        response body or exception text is logged, printed, or returned.
+        """
+        if self.endpoint_kind == "openrouter" and not api_key:
+            return ProbeResult(ok=False, reason=PROBE_AUTH_FAILED)
+
+        send = transport or _default_get_transport
+        headers = self.build_headers(api_key)
+        try:
+            status, body = send(self._probe_url(), headers, timeout)
+        except Exception as exc:  # noqa: BLE001 — classified, text discarded
+            reason = PROBE_TIMEOUT if _is_timeout(exc) else PROBE_ENDPOINT_UNREACHABLE
+            return ProbeResult(ok=False, reason=reason)
+
+        if status in (401, 403):
+            return ProbeResult(ok=False, reason=PROBE_AUTH_FAILED)
+        if not 200 <= status < 300:
+            return ProbeResult(ok=False, reason=PROBE_ENDPOINT_UNREACHABLE)
+        budget = _extract_budget(body) if self.endpoint_kind == "openrouter" else None
+        return ProbeResult(ok=True, reason=None, budget=budget)
+
     def dispatch(
         self,
         mode: str,
@@ -106,13 +245,27 @@ class OpenAICompatAdapter:
         timeout_seconds: int = 300,
         api_key: str | None = None,
         transport: Transport | None = None,
+        *,
+        tools_overflow: bool = False,
     ) -> ReviewResult:
         """Dispatch via the OpenAI-compatible API with model fallback.
 
         Captures the generation id (``response["id"]``) for spend reconciliation.
         On a capacity/rate-limit error the next fallback model is tried; other
         errors return immediately.
+
+        ``tools_overflow`` is the ``tools_overflow`` flag from the sidecar of
+        the packet this lane receives. HTTP lanes cannot read files, so a
+        packet that needs tools is refused before any request is sent (D6):
+        reviewing it blind would manufacture false consensus.
         """
+        if tools_overflow:
+            return ReviewResult(
+                vendor=self.vendor, success=False,
+                error=PACKET_REQUIRES_TOOLS,
+                error_class=ErrorClass.UNAVAILABLE,
+                agent_id=self.agent_id,
+            )
         # OpenRouter (metered) requires a key; local endpoints may not.
         if self.endpoint_kind == "openrouter" and not api_key:
             return ReviewResult(
@@ -144,39 +297,11 @@ class OpenAICompatAdapter:
                     elapsed_seconds=time.monotonic() - start,
                 )
 
-            content = _extract_content(resp)
-            if not content:
-                return ReviewResult(
-                    vendor=self.vendor, success=False,
-                    error="Empty response content", error_class=ErrorClass.UNKNOWN,
-                    model_used=model, models_attempted=models_attempted,
-                    elapsed_seconds=time.monotonic() - start,
-                    generation_id=resp.get("id"),
-                )
-            # Parse the model output into the dispatcher's review-findings shape
-            # ({"findings": [...]}) using the same extractor the CLI/SDK adapters use.
-            # A non-empty response that is NOT valid review-findings JSON is a failure,
-            # not a silent success with zero findings.
-            findings = CliVendorAdapter._parse_findings(content)
-            if findings is None:
-                return ReviewResult(
-                    vendor=self.vendor, success=False,
-                    error="Review output was not valid review-findings JSON",
-                    error_class=ErrorClass.UNKNOWN,
-                    model_used=model, models_attempted=models_attempted,
-                    elapsed_seconds=time.monotonic() - start,
-                    generation_id=resp.get("id"),
-                )
-            return ReviewResult(
-                vendor=self.vendor,
-                success=True,
-                findings=findings,
-                model_used=model,
-                models_attempted=models_attempted,
-                elapsed_seconds=time.monotonic() - start,
-                error=None,
-                generation_id=resp.get("id"),
+            result = self._result_from_response(
+                resp, model, models_attempted, time.monotonic() - start,
+                prompt=prompt, cwd=cwd,
             )
+            return self._with_usage(result, resp)
 
         return ReviewResult(
             vendor=self.vendor, success=False,
@@ -185,6 +310,82 @@ class OpenAICompatAdapter:
             elapsed_seconds=time.monotonic() - start,
         )
 
+    def _result_from_response(
+        self,
+        resp: dict[str, Any],
+        model: str,
+        models_attempted: list[str],
+        elapsed: float,
+        *,
+        prompt: str = "",
+        cwd: Path | None = None,
+    ) -> ReviewResult:
+        """Turn one chat-completions response into a ReviewResult.
+
+        The message content goes through the same ingest pipeline as CLI
+        stdout (``ingest_findings_output``): coerce, validate, judgment
+        stamp, line resolve against the packet diff, placeholder check and
+        the empty-findings floor. An HTTP lane is held to the CLI contract.
+        """
+        content = _extract_content(resp)
+        if not content:
+            return ReviewResult(
+                vendor=self.vendor, success=False,
+                error="Empty response content", error_class=ErrorClass.UNKNOWN,
+                model_used=model, models_attempted=models_attempted,
+                elapsed_seconds=elapsed, generation_id=resp.get("id"),
+            )
+        # Parse the model output into the dispatcher's review-findings shape
+        # ({"findings": [...]}) using the same extractor the CLI/SDK adapters use.
+        # A non-empty response that is NOT valid review-findings JSON is a failure,
+        # not a silent success with zero findings.
+        if CliVendorAdapter._parse_findings(content) is None:
+            return ReviewResult(
+                vendor=self.vendor, success=False,
+                error="Review output was not valid review-findings JSON",
+                error_class=ErrorClass.UNKNOWN,
+                model_used=model, models_attempted=models_attempted,
+                elapsed_seconds=elapsed, generation_id=resp.get("id"),
+            )
+        result = ingest_findings_output(
+            self.vendor,
+            content,
+            "",
+            elapsed=elapsed,
+            model_name=model,
+            models_attempted=models_attempted,
+            packet_diff=_extract_diff_from_prompt(prompt),
+            selected_files=_extract_selected_files_from_prompt(prompt),
+            coverage_quorum_threshold=(
+                _coverage_quorum_threshold(cwd) if cwd is not None else 0.8
+            ),
+        )
+        result.generation_id = resp.get("id")
+        result.agent_id = self.agent_id
+        # The CLI path leaves error_class unset for a schema-invalid payload
+        # (it then falls through vendor fallback as an unclassified error).
+        # An HTTP response that parsed but failed ingest is a model-output
+        # failure, so classify it explicitly.
+        if not result.success and result.error_class is None:
+            result.error_class = ErrorClass.UNKNOWN
+        return result
+
+    def _with_usage(self, result: ReviewResult, resp: dict[str, Any]) -> ReviewResult:
+        """Copy the response's token counts and cost onto *result* (D4).
+
+        Applied to every result built from a response, successful or not, so
+        a billed-but-rejected review still reports its spend. cost_source is
+        set only for metered (OpenRouter) lanes.
+        """
+        usage = resp.get("usage")
+        usage = usage if isinstance(usage, dict) else {}
+        result.prompt_tokens = _int_or_none(usage.get("prompt_tokens"))
+        result.completion_tokens = _int_or_none(usage.get("completion_tokens"))
+        result.cost_usd = _numeric(usage.get("cost"))
+        if self.endpoint_kind == "openrouter":
+            result.cost_source = "reported" if result.cost_usd is not None else "estimated"
+        return result
+
 
 def _extract_content(resp: dict[str, Any]) -> str | None:
     """Pull assistant text from an OpenAI-compatible chat response."""
diff --git a/skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-result.schema.json b/skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-result.schema.json
index e7168bc2..9035488c 100644
--- a/skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-result.schema.json
+++ b/skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-result.schema.json
@@ -239,7 +239,8 @@
             "coordinator_projection_forbidden",
             "audit_sink_failed",
             "phase_fallback_inline",
-            "handoff_local_fallback"
+            "handoff_local_fallback",
+            "metered_spend_unrecorded"
           ]
         },
         "phase": {"type": "string", "minLength": 1, "maxLength": 64},
diff --git a/skills/tests/autopilot/test_relayed_gate_answer.py b/skills/tests/autopilot/test_relayed_gate_answer.py
index b350c87f..f19ae57a 100644
--- a/skills/tests/autopilot/test_relayed_gate_answer.py
+++ b/skills/tests/autopilot/test_relayed_gate_answer.py
@@ -160,7 +160,11 @@ def _origin_with_only_rm(worker: Path) -> None:
     _git(worker, "add", "-A")
     _git(worker, "commit", "-q", "-m", "second roadmap")
     _git(worker, "update-ref", "refs/remotes/origin/openspec/roadmap-gone", "HEAD")
-    bare = worker.parent / "origin.git"
+    # ``worker.parent`` is the session-wide pytest basetemp: a fixed name there
+    # is shared with every other test that builds an origin, and a re-init keeps
+    # the previous test's branch, so the push below is a non-fast-forward.
+    bare = worker.parent / f"{worker.name}-origin.git"
+    assert not bare.exists(), f"{bare} belongs to another test"
     _git(worker.parent, "init", "-q", "--bare", str(bare))
     _git(worker, "remote", "add", "origin", str(bare))
     _git(worker, "push", "-q", "origin", "refs/remotes/origin/openspec/roadmap-rm:refs/heads/openspec/roadmap-rm")
diff --git a/skills/tests/vendor-neutral-autopilot/test_contracts.py b/skills/tests/vendor-neutral-autopilot/test_contracts.py
index 464f3583..96b7a377 100644
--- a/skills/tests/vendor-neutral-autopilot/test_contracts.py
+++ b/skills/tests/vendor-neutral-autopilot/test_contracts.py
@@ -118,6 +118,21 @@ def test_provider_model_map_schema_rejects_unknown_provider_name() -> None:
     assert list(Draft202012Validator(_schema()).iter_errors(instance))
 
 
+def test_provider_model_map_schema_admits_optional_openrouter_entry() -> None:
+    # openrouter-review-lane: `openrouter` is an optional, non-roster key holding
+    # the endpoint-only review lane's aliases; the roster stays required.
+    providers = _roster_providers(drop_frontier=True)
+    instance = {
+        "schema_version": 2,
+        "tiers": ["premium", "standard", "economy"],
+        "providers": {**providers, "openrouter": dict(providers["pi"])},
+    }
+    Draft202012Validator(_schema()).validate(instance)
+
+    del instance["providers"]["codex"]
+    assert list(Draft202012Validator(_schema()).iter_errors(instance))
+
+
 # ---------------------------------------------------------------------------
 # `local` provider delta (OpenSpec change add-local-model-provider-tier)
 # ---------------------------------------------------------------------------

```

### Rule groups

#### Group 1 (default: `agent-coordinator/agents.yaml`)
Applies to:
- agent-coordinator/agents.yaml

Verify a new or changed CLI/SDK block's flags match what that vendor's CLI actually accepts (cross-check against any comment citing a verified version). Check that trust_level, capabilities, and archetypes are consistent with what the agent is actually granted.

#### Group 2 (default: `agent-coordinator/archetypes.yaml`)
Applies to:
- agent-coordinator/archetypes.yaml

Verify model/tier changes are cited to an operator decision or empirical finding, not asserted alone. Check that a tier change does not silently widen or narrow which archetypes route to it.

#### Group 3 (default: `(default)`)
Applies to:
- agent-coordinator/database/migrations/046_spend_generation_id_unique.sql
- agent-coordinator/routing.yaml
- agent-coordinator/tests/openapi_contract_drift_baseline.yaml
- docs/decisions/README.md
- docs/decisions/model-routing.md
- docs/decisions/parallel-infrastructure.md
- docs/decisions/skill-workflow.md
- openspec/changes/openrouter-review-lane/.review-ledger/ledger.json
- openspec/changes/openrouter-review-lane/contracts/README.md
- openspec/changes/openrouter-review-lane/contracts/config/routing-cost-policy.schema.json
- openspec/changes/openrouter-review-lane/contracts/config/routing.schema.json
- openspec/changes/openrouter-review-lane/design.md
- openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g1.json
- openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g2.json
- openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g3.json
- openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g6.json
- openspec/changes/openrouter-review-lane/loop-state.json
- openspec/changes/openrouter-review-lane/plan-findings.md
- openspec/changes/openrouter-review-lane/proposal.md
- openspec/changes/openrouter-review-lane/session-log.md
- openspec/changes/openrouter-review-lane/tasks.md
- skills/parallel-infrastructure/review_quorum_policy.json
- skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-result.schema.json

Review for correctness, security, and adherence to this repository's conventions.

#### Group 4 (default: `**/*.py`)
Applies to:
- agent-coordinator/src/agents_config.py
- agent-coordinator/src/model_routing/api.py
- agent-coordinator/src/model_routing/ledger.py
- agent-coordinator/src/model_routing/routing_policy.py
- agent-coordinator/tests/integration/postgres/test_fresh_database_migration.py
- agent-coordinator/tests/model_routing/test_agent_endpoints.py
- agent-coordinator/tests/model_routing/test_ledger.py
- agent-coordinator/tests/model_routing/test_routing_cost_policy.py
- agent-coordinator/tests/model_routing/test_routing_policy_config.py
- agent-coordinator/tests/model_routing/test_spend_route.py
- agent-coordinator/tests/test_agents_config.py
- agent-coordinator/tests/test_archetypes_yaml.py
- agent-coordinator/tests/test_migrations.py
- agent-coordinator/tests/test_vendor_registry.py

Check for unhandled exceptions, resource leaks (files/sockets/locks not in a context manager), and mutable default arguments. Flag a docstring claim ("never raises", "pure function") the code does not actually satisfy.

#### Group 5 (default: `openspec/changes/*/specs/**/spec.md`)
Applies to:
- openspec/changes/openrouter-review-lane/specs/configuration/spec.md
- openspec/changes/openrouter-review-lane/specs/model-routing/spec.md
- openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md
- openspec/changes/openrouter-review-lane/specs/skill-workflow/spec.md
- openspec/changes/openrouter-review-lane/specs/supervise/spec.md

Verify every SHALL/MUST has at least one Scenario with WHEN/THEN. Check that a MODIFIED requirement's unchanged scenarios were preserved, not silently dropped.

#### Group 6 (default: `openspec/schemas/*.schema.json`)
Applies to:
- openspec/schemas/dispatch-result.schema.json
- openspec/schemas/provider-model-map.schema.json

Verify the schema is valid Draft 2020-12, that required fields were not silently dropped, and that any mirrored copy (install_assets, sentinel-injected) is checked for the same change.

#### Group 7 (default: `skills/*/SKILL.md`)
Applies to:
- skills/autopilot/SKILL.md

Check that the workflow steps match what the referenced scripts actually accept (flags, return shapes). Verify examples are runnable as written. Flag instructions that silently assume coordinator, tier, or environment state without stating the fallback.

#### Group 8 (default: `skills/*/scripts/*.py`)
Applies to:
- skills/autopilot/scripts/agent_lane.py
- skills/autopilot/scripts/convergence_loop.py
- skills/parallel-infrastructure/scripts/openai_compat_adapter.py

Check for unhandled exceptions on the failure paths this module is meant to guard (network, subprocess, file I/O). Verify a function documented as "never raises" actually catches every exception class it claims to. Flag silent behavior changes to existing callers.

#### Group 9 (default: `skills/tests/**`)
Applies to:
- skills/tests/autopilot/test_relayed_gate_answer.py
- skills/tests/vendor-neutral-autopilot/test_contracts.py

Same standard as scripts/tests/: verify the test would fail if the behavior it targets were broken. Check that fixture paths use openspec_paths.change_dir rather than a literal openspec/changes/<id>/ path where the guide requires it.

### Not included in this packet
These changed files were left out; do not report findings about them.
- openspec/changes/openrouter-review-lane/.review-cache/round-1/fact-check-claude_code.json
- openspec/changes/openrouter-review-lane/.review-cache/round-1/findings-claude_code-plan.json
- openspec/changes/openrouter-review-lane/.review-cache/round-1/raw-claude_code-plan.meta.json
- openspec/changes/openrouter-review-lane/.review-cache/round-1/raw-claude_code-plan.txt
- openspec/changes/openrouter-review-lane/.review-cache/round-1/review-manifest.json
- openspec/changes/openrouter-review-lane/.review-cache/round-1/review-packet.md
- openspec/changes/openrouter-review-lane/.review-cache/round-1/review-packet.meta.json
- openspec/changes/openrouter-review-lane/.review-cache/round-2/fact-check-claude_code.json
- openspec/changes/openrouter-review-lane/.review-cache/round-2/findings-claude_code-plan.json
- openspec/changes/openrouter-review-lane/.review-cache/round-2/raw-claude_code-plan.meta.json
- openspec/changes/openrouter-review-lane/.review-cache/round-2/raw-claude_code-plan.txt
- openspec/changes/openrouter-review-lane/.review-cache/round-2/review-manifest.json
- openspec/changes/openrouter-review-lane/.review-cache/round-2/review-packet.md
- openspec/changes/openrouter-review-lane/.review-cache/round-2/review-packet.meta.json
- openspec/changes/openrouter-review-lane/.review-cache/round-3/fact-check-claude_code.json
- openspec/changes/openrouter-review-lane/.review-cache/round-3/findings-claude_code-plan.json
- openspec/changes/openrouter-review-lane/.review-cache/round-3/raw-claude_code-plan.meta.json
- openspec/changes/openrouter-review-lane/.review-cache/round-3/raw-claude_code-plan.txt
- openspec/changes/openrouter-review-lane/.review-cache/round-3/review-manifest.json
- openspec/changes/openrouter-review-lane/.review-cache/round-3/review-packet.md
- openspec/changes/openrouter-review-lane/.review-cache/round-3/review-packet.meta.json
- openspec/changes/openrouter-review-lane/specs/multiplayer-collaboration/spec.md
- skills/parallel-infrastructure/scripts/review_dispatcher.py
- skills/parallel-infrastructure/scripts/review_packet.py
- skills/parallel-infrastructure/scripts/spend_recorder.py
- skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py
- skills/parallel-infrastructure/scripts/tests/test_review_packet.py
- skills/parallel-infrastructure/tests/test_check_vendors_api_lane.py
- skills/supervise/scripts/execution.py
- skills/tests/autopilot/test_agent_lane.py
- skills/tests/autopilot/test_convergence_loop_capability.py
- skills/tests/autopilot/test_emit_result.py
- skills/tests/parallel-infrastructure/test_openai_compat_adapter.py
- skills/tests/parallel-infrastructure/test_spend_recorder.py
- skills/tests/supervise/test_execution_profile.py

### Spec excerpts
#### specs/configuration/spec.md
## MODIFIED Requirements

### Requirement: Provider Model Mapping Configuration

Provider dispatch configuration SHALL define model mappings for Claude Code, Codex, antigravity, grok, and pi so logical archetypes can resolve to provider-specific model IDs.

The model mapping SHALL conform to `openspec/schemas/provider-model-map.schema.json` (schema_version 2). The provider key set SHALL be closed to the five roster keys, all five required, plus two optional keys: `local` and `openrouter`. `openrouter` holds the model aliases of the endpoint-only `openrouter-review` lane, and is not a roster vendor.

The `pi` provider SHALL resolve to OpenRouter model slugs, and its default model SHALL be `qwen/qwen3-coder`, selected so the roster reaches models outside the subscription harnesses.

#### Scenario: Provider map includes all first-class providers

- **WHEN** the default provider model map is loaded
- **THEN** it SHALL include entries for `claude_code`, `codex`, `antigravity`, `grok`, and `pi`
- **AND** each entry SHALL define `premium`, `standard`, and `economy` model IDs
- **AND** it SHALL NOT include an entry for `gemini`

#### Scenario: Optional provider keys are allowed but not required

- **WHEN** a provider model map carries an `openrouter` entry or a `local` entry
- **THEN** it SHALL validate, provided the entry defines `premium`, `standard`, and `economy`
- **AND** a map without either entry SHALL also validate
- **AND** a map with any other provider key SHALL fail validation

#### Scenario: pi maps to OpenRouter slugs

- **WHEN** the `pi` provider entry is loaded
- **THEN** every tier value SHALL be an OpenRouter model slug in `<publisher>/<model>` form
- **AND** the `standard` tier SHALL be `qwen/qwen3-coder`

#### Scenario: Non-Claude provider rejects unmapped Claude alias

- **GIVEN** provider `codex`
- **AND** an archetype resolves to legacy alias `opus`
- **WHEN** no Codex mapping exists for that alias or tier
- **THEN** dispatch resolution SHALL fail with a structured configuration error before invoking Codex
- **AND** the error SHALL identify the missing provider model mapping


#### specs/model-routing/spec.md
## ADDED Requirements

### Requirement: Review Spend Recording Route

The coordinator SHALL expose `POST /routing/spend`, which requires the `X-API-Key` header.

The request body SHALL be validated with unknown fields forbidden. It accepts:
- required: `vendor`, `model`, `endpoint_kind`, `generation_id`;
- optional: `prompt_tokens`, `completion_tokens` (non-negative integers), `actual_usd` (a
  non-negative number), `tokens_estimated`, `work_unit_ref`, `occurred_at`.

A valid request SHALL write one `routing_spend_ledger` row through `LedgerService.record`.
`generation_id` SHALL be the idempotency key: a second request with a `generation_id` already
in the ledger SHALL return the existing row with HTTP 200 and SHALL NOT insert another row.
`GET /routing/usage` SHALL include recorded review rows in `metered_usd_used`.

#### Scenario: A review spend row is recorded
- **WHEN** an authenticated client posts `{vendor: "openrouter", model: "<publisher>/<model>", endpoint_kind: "openrouter", generation_id: "gen-abc", actual_usd: 0.0042, tokens_estimated: false}`
- **THEN** the response SHALL be HTTP 201, and the next `GET /routing/usage?window=month` SHALL
  report `metered_usd_used` increased by 0.0042

#### Scenario: Duplicate generation id is not double-counted
- **WHEN** the same body is posted twice
- **THEN** the second response SHALL be HTTP 200 and the ledger SHALL contain one `gen-abc` row

#### Scenario: Unauthenticated write is rejected
- **WHEN** the request has no `X-API-Key` header, or an invalid one
- **THEN** the response SHALL be HTTP 401 and no row SHALL be written

#### Scenario: Invalid spend is rejected
- **WHEN** the body has `actual_usd: -1`, or an unknown field `api_key`
- **THEN** the response SHALL be HTTP 422 and no row SHALL be written


#### specs/parallel-infrastructure/spec.md
## MODIFIED Requirements

### Requirement: OpenAI-Compatible Dispatcher Discovery

The review dispatcher SHALL construct an OpenAI-compatible adapter for configured `local` or
`openrouter` endpoints with a `base_url` after CLI and SDK discovery. A usable CLI SHALL retain
precedence over the endpoint adapter for the same agent.

The lane id of an endpoint lane SHALL be its agent `type`. Its model family SHALL be the
publisher prefix of its primary model slug (`<publisher>/<model>`). The family of a CLI or SDK
vendor SHALL be read from `vendor_families` in `review_quorum_policy.json`.

The dispatcher SHALL skip, and SHALL NOT count toward quorum, an `openrouter` lane in either
of these cases:
- its primary model or any fallback model has publisher `anthropic`;
- its family equals the family of a lane already selected at tier 1 or tier 2. The skip
  reason SHALL be `duplicate_model_family`.

An agent with `endpoint_kind: openrouter` selected at tier 2.5 is a metered lane. Metered lanes
SHALL be selected only while the non-metered selected lanes number fewer than
`metered_lanes.fill_target`. That value defaults to the policy file's `default_min_quorum`.
Metered lanes are added in roster order until the target is reached. `--check-vendors` and
`dispatch_and_wait` SHALL apply the same selection.

`dispatch_and_wait` SHALL accept an optional `include_lanes` set. When it is given, only those
lanes SHALL be dispatched. When it is `None`, behaviour SHALL be unchanged.

#### Scenario: Endpoint-only agent is discoverable

- **WHEN** dispatch configuration contains a local/OpenRouter endpoint with no CLI or SDK block
- **THEN** review discovery SHALL return an OpenAI-compatible reviewer for that endpoint

#### Scenario: CLI retains precedence

- **WHEN** an agent has both a usable CLI and an OpenAI-compatible endpoint
- **THEN** review discovery SHALL select the CLI tier first

#### Scenario: Anthropic-family OpenRouter lane is rejected

- **WHEN** an `openrouter` agent resolves the primary model `anthropic/<any>` or lists an
  `anthropic/` fallback
- **THEN** discovery SHALL NOT return that lane, and `--check-vendors --json` SHALL list it
  under `unverified` with reason `anthropic_family`

#### Scenario: Duplicate family is skipped

- **WHEN** `codex` is selected at tier 1, `vendor_families.codex` is `openai`, and an
  `openrouter` lane's primary model is `openai/<model>`
- **THEN** that lane SHALL be listed `unverified` with reason `duplicate_model_family` and SHALL
  NOT be dispatched

#### Scenario: Metered lane fills quorum only

- **WHEN** `fill_target` is 2, and two non-metered lanes and one verified `openrouter` lane are
  available
- **THEN** discovery SHALL return the two non-metered lanes only, and no HTTP request SHALL be
  sent to the OpenRouter endpoint during dispatch

#### Scenario: Metered lane fills a cloud roster

- **WHEN** `fill_target` is 2, `claude_code` is the only non-metered lane, and one `openrouter`
  lane verifies
- **THEN** discovery SHALL return `claude_code` and the `openrouter` lane

#### Scenario: include_lanes restricts dispatch

- **WHEN** `dispatch_and_wait` is called with `include_lanes={"openrouter"}` and `claude_code` and
  `openrouter` are both available
- **THEN** exactly one review SHALL be dispatched, to `openrouter`

### Requirement: Dispatchable Vendor Verification

`review_dispatcher.py --check-vendors` SHALL count a vendor lane as available for a mode only
after a dry invocation for that mode succeeds. The dry invocation is the adapter's declared
no-op, run with a 10-second timeout:
- for a CLI lane, `<cli> --version`;
- for an `openrouter` API lane, one authenticated `GET {base_url}/key`;
- for a `local` API lane, one authenticated `GET {base_url}/models`.

An SDK lane with no authenticated no-op SHALL remain `unverified` with reason
`probe_unsupported`.

Credentials MAY be read only inside the adapter's existing credential path. The probe SHALL
NOT print, log, or return any environment value, credential, or response body. From an API
probe response it SHALL keep only the numeric budget fields (`limit`, `usage`,
`limit_remaining`).

An `openrouter` lane SHALL verify only if:
- the authenticated probe succeeds;
- at least one spend ceiling source is available: the coordinator monthly ceiling when it is
  greater than 0 and the coordinator is reachable, or the key's non-null `limit`; and
- every available source has remaining budget of at least
  `metered_lanes.review_reservation_usd`.

A `local` API lane SHALL verify when its probe succeeds; no budget rule applies to it.
An `openrouter` lane that fails any of these conditions SHALL be `unverified` with one of these reasons: `auth_failed`,
`probe_timeout`, `endpoint_unreachable`, `spend_ceiling_exceeded`, or
`spend_ceiling_unverifiable`.

With `--json` it SHALL print
`{"modes": {<mode>: {"verified": [...], "unverified": [{"vendor", "reason"}], "lane_kinds": {<lane>: <endpoint_kind>}}}, "probe_command": "<argv>"}`.
It SHALL keep its existing exit codes: 0 at quorum, 2 below quorum or on probe failure. When
the roster cannot be resolved it SHALL print `{"error": "<reason>", "modes": {}}` and exit 2.

#### Scenario: A listed vendor without its CLI is unverified
- **WHEN** `agents.yaml` lists `codex` for mode `review` and no `codex` executable is on `PATH`
- **THEN** `--check-vendors --json` SHALL list `codex` under `unverified` with reason
  `cli_not_found`, and SHALL NOT count it toward `--min-vendors`

#### Scenario: A hanging dry invocation is unverified
- **WHEN** a lane's dry invocation does not exit within 10 seconds
- **THEN** the lane SHALL be `unverified` with reason `probe_timeout`

#### Scenario: The probe never discloses credentials
- **WHEN** the test sets `ANTHROPIC_API_KEY=sk-test-SENTINEL-1234567890`,
  `OPENAI_API_KEY=sk-test-SENTINEL-0987654321` and
  `OPENROUTER_API_KEY=sk-or-test-SENTINEL-5555555555`, configures an `openrouter` lane with an
  injected transport that echoes the request headers in its response body, and runs
  `--check-vendors --json`
- **THEN** no sentinel value SHALL appear in stdout, stderr, log records, or the JSON, and no
  `env` or `printenv` subprocess SHALL have been spawned

#### Scenario: An OpenRouter lane verifies by its authenticated no-op
- **WHEN** the injected transport answers `GET /key` with HTTP 200 and `limit: 20.0`,
  `limit_remaining: 15.0`, the coordinator is unreachable, and `review_reservation_usd` is 1.0
- **THEN** the lane SHALL be listed under `verified` for mode `review`, `lane_kinds` SHALL map
  it to `openrouter`, and no chat-completions request SHALL have been sent

#### Scenario: A rejected key is unverified
- **WHEN** the injected transport answers `GET /key` with HTTP 401
- **THEN** the lane SHALL be `unverified` with reason `auth_failed`

#### Scenario: An exhausted ceiling is unverified
- **WHEN** the coordinator reports `metered_ceiling_usd: 50.0` and `metered_usd_used: 49.5`, and
  `review_reservation_usd` is 1.0
- **THEN** the lane SHALL be `unverified` with reason `spend_ceiling_exceeded`, even if the key's
  `limit_remaining` is larger

#### Scenario: No ceiling source fails closed
- **WHEN** the coordinator is unreachable or reports `metered_ceiling_usd: 0`, and the key
  reports `limit: null`
- **THEN** the lane SHALL be `unverified` with reason `spend_ceiling_unverifiable`

#### Scenario: An unexpected probe response shape fails closed
- **WHEN** `GET /key` returns HTTP 200 with a body that has no `data` object
- **THEN** the lane SHALL be `unverified` with reason `spend_ceiling_unverifiable` unless the
  coordinator ceiling source alone verifies it

## ADDED Requirements

### Requirement: Metered Review Lane Spend Accounting

Every review that an `openrouter` lane dispatches SHALL request inline usage accounting
(`"usage": {"include": true}`). On the resulting `ReviewResult` it SHALL set:
- `generation_id`, `model_used`, `prompt_tokens`, `completion_tokens`;
- `cost_usd`, taken from the response's `usage.cost`;
- `cost_source`: `reported` when `usage.cost` is present, `estimated` when it is absent.

`converge()` SHALL write these fields into the round checkpoint's vendor index.

After each review that sent a request, `ReviewOrchestrator.dispatch_and_wait` SHALL call
`spend_recorder.record()`, which SHALL send one row to `POST /routing/spend` with:
`vendor` (the lane id), `model`, `endpoint_kind: openrouter`, `generation_id`, token counts,
`actual_usd`, `tokens_estimated` (true when `cost_source` is `estimated`), and
`work_unit_ref` (`<change_id>:<phase>:round-<n>`, for example
`openrouter-review-lane:VAL_REVIEW:round-2`; the phase, not the review type, so IMPL_REVIEW and
VAL_REVIEW rows stay distinct; `converge()` supplies it in the `spend_context` it passes to
`dispatch_and_wait` when its caller gives the phase). The call SHALL happen on every dispatch path, including a host
`converge()` or `/parallel-review-*` run that selected the metered lane, not only inside
`agent_lane.py`. The result SHALL carry `spend_recorded` (the recorder's `recorded` value).

If the write fails, the record SHALL be appended to
`openspec/changes/<change-id>/reviews/spend-spool.jsonl`, and the caller SHALL record the
degradation `metered_spend_unrecorded` with phase and lane. The change id SHALL come from the
`spend_context` (`change_id`, `work_unit_ref`) passed to `dispatch_and_wait`. A metered lane
dispatched without a `spend_context` SHALL NOT make an HTTP request; it SHALL return a failed
result with `error_class` `vendor_unavailable` and reason `spend_context_missing`.

#### Scenario: A metered lane without spend context is not dispatched
- **WHEN** `dispatch_and_wait` is called with no `spend_context` and the selection includes the
  `openrouter` lane
- **THEN** no HTTP request SHALL be made for that lane, and its result SHALL have `error_class`
  `vendor_unavailable` and reason `spend_context_missing`

`spend_recorder.py replay --change-id <id>` SHALL post the spooled rows. Replay SHALL skip a
`generation_id` the ledger already holds, and SHALL remove each row it delivers.

Each time `dispatch_and_wait` is about to dispatch a metered lane (once per review round, on
every dispatch path), the remaining budget SHALL be re-checked with the same rule the probe
uses. A lane below `review_reservation_usd` SHALL NOT be dispatched
for that round and SHALL be reported as a failed result with `error_class` `vendor_unavailable`
and reason `spend_ceiling_exceeded`.

#### Scenario: A later round finds the ceiling exhausted
- **WHEN** the coordinator ceiling had budget at probe time, and before round 2 its remaining
  budget is below `review_reservation_usd`
- **THEN** round 2 SHALL NOT dispatch the `openrouter` lane, and SHALL record it as
  `vendor_unavailable` with reason `spend_ceiling_exceeded`

#### Scenario: A review is recorded against the ledger
- **WHEN** an `openrouter` review returns `id: gen-abc`, `usage: {prompt_tokens: 1200, completion_tokens: 300, cost: 0.0042}`, and the coordinator accepts the write
- **THEN** the ledger SHALL contain one row with `generation_id: gen-abc`, `actual_usd: 0.0042`,
  and `tokens_estimated: false`, and the round checkpoint index entry for the lane SHALL carry
  the same generation id, model and cost

#### Scenario: A host-path metered review is recorded
- **WHEN** a host with one non-metered lane runs `converge()` with `ReviewOrchestrator`, the fill
  rule selects the `openrouter` lane, and its review returns `id: gen-host`
- **THEN** `spend_recorder.record()` SHALL have been called once for `gen-host`, and the result's
  `spend_recorded` SHALL be true when the coordinator accepts the write

#### Scenario: Missing cost is labelled estimated
- **WHEN** the response has token usage but no `usage.cost`
- **THEN** `cost_source` SHALL be `estimated` and the ledger row SHALL have
  `tokens_estimated: true`

#### Scenario: Coordinator unavailable spools the record
- **WHEN** `POST /routing/spend` fails

[spec excerpt truncated]


#### specs/skill-workflow/spec.md
## MODIFIED Requirements

### Requirement: Honest Review Quorum

When the launch marker of a dispatched child carries `review_requirements`, a review phase
whose verified lanes from `execution_profile` are fewer than
`review_requirements.min_quorum[phase]` SHALL record
`park(kind=capability_unavailable, phase, missing_lanes)` and stop. It SHALL NOT run the review
with a lower quorum.

A standalone run (no launch marker) SHALL keep disabling CLI review below quorum. It SHALL
record a `review_skipped` degradation, or a `single_vendor_review` degradation when exactly one
lane reviewed.

During `converge()`, a round can end with fewer successful results than `min_quorum`.
`missing_lanes` SHALL be the round's verified lanes minus the lanes that returned a successful
result. When `missing_lanes` is non-empty and every lane in it has a recorded failure whose
`error_class` is `vendor_unavailable` or `auth_required`, `converge()` SHALL return
`reason="capability_unavailable"` with `missing_lanes` naming those lanes. A verified lane with
no result at all SHALL NOT satisfy this condition. This
covers an exhausted budget, HTTP 402, a revoked key, or `packet_requires_tools`. Any other
quorum loss SHALL remain `reason="quorum_lost"`.


#### Scenario: A lane that returns nothing is not a capability loss
- **WHEN** a PLAN_REVIEW round has verified lanes `claude_code` and `openrouter`, `claude_code`
  succeeds, and `openrouter` returns neither a result nor a recorded failure
- **THEN** `converge()` SHALL return `reason="quorum_lost"`, not `capability_unavailable`

#### Scenario: Dispatched child below quorum parks
- **WHEN** `review_requirements.min_quorum.PLAN_REVIEW` is 2 and only `claude_code` is verified
- **THEN** the loop SHALL have `park.kind == capability_unavailable` with `missing_lanes` naming
  the counting lanes not verified, no review dispatch SHALL have run, and `emit-result` SHALL
  return `parked/capability_unavailable`

#### Scenario: A single-lane review under a quorum-1 policy is recorded
- **WHEN** a dispatched child's `review_requirements.min_quorum.PLAN_REVIEW` is 1 by policy
  data, and exactly one review lane dispatches because the others failed to dispatch
- **THEN** the review SHALL run, and `degradations` SHALL contain a `single_vendor_review` entry
  for `PLAN_REVIEW` whose detail names the vendor
- **AND** the child SHALL NOT have read environment variables or credentials to decide that only
  one lane exists

#### Scenario: GATEKEEPER review scheduling on the host-driven path
- **WHEN** `runner.py transition --outcome proceed_with_review` is applied in `GATEKEEPER`
- **THEN** `val_review_enabled` SHALL be True and `gate_verdict` SHALL be `proceed_with_review`

#### Scenario: Standalone run below quorum records a degradation
- **WHEN** no launch marker exists and `--check-vendors` reports one vendor
- **THEN** `cli_review_enabled` SHALL be False and `degradations` SHALL contain one
  `review_skipped` entry for `PLAN_REVIEW`

#### Scenario: Budget exhausted mid-run parks instead of losing quorum
- **WHEN** `min_quorum` is 2, round 1 succeeds with `claude_code` and `openrouter`, and in round 2
  `openrouter` fails with HTTP 402 (`error_class=vendor_unavailable`)
- **THEN** `converge()` SHALL return `reason="capability_unavailable"` with
  `missing_lanes == ["openrouter"]`, and SHALL NOT return `quorum_lost`

#### Scenario: A malformed review still loses quorum
- **WHEN** `min_quorum` is 2 and a round's `openrouter` result fails with
  `error_class=unknown` ("Review output was not valid review-findings JSON")
- **THEN** `converge()` SHALL return `reason="quorum_lost"`

## ADDED Requirements

### Requirement: Composite Agent-Lane Review

`agent_lane.py converge` SHALL accept `--verified-lanes` (repeatable). A dispatched child SHALL
take the values from its launch marker's `execution_profile.lanes.review`. A standalone run
SHALL take them from the `--check-vendors --json` output and SHALL NOT read environment
variables or credentials.

It SHALL resolve the quorum policy with `verified_review_lanes` equal to the number of
verified lanes, and SHALL pass those lanes to `converge()` as `verified_lanes`.

Each round SHALL:
- dispatch the `claude_code` handshake lane;
- in parallel, dispatch `ReviewOrchestrator.dispatch_and_wait(include_lanes=<verified lanes except claude_code>)`;
- return both results to `converge()`.

Every lane's findings SHALL be written to the round checkpoint under its own lane id, and
ConsensusSynthesizer SHALL attribute consensus findings to those lane ids.

After each run, `agent_lane.py` SHALL write `ConvergenceResult.consensus` (including
`quorum_received`) under `openspec/changes/<change-id>/reviews/`, with one file per phase:
- `consensus-plan.json` for `PLAN_REVIEW`;
- `consensus-impl-review.json` for `IMPL_REVIEW`;
- `consensus-val-review.json` for `VAL_REVIEW`.

The two implementation phases share `review_type: implementation`, so the file is named by phase
and neither run overwrites the other. `converge()` itself SHALL NOT be required to write these
files.

The review body written for `VAL_REVIEW` SHALL list every lane that reviewed. It SHALL name a
`single_vendor_review` degradation only when exactly one lane reviewed.

#### Scenario: Cloud plan review reaches quorum two
- **WHEN** `agent_lane.py converge --phase PLAN_REVIEW --verified-lanes claude_code --verified-lanes openrouter`
  runs against a fixture change, with an injected OpenRouter transport that returns
  schema-valid findings and an agent handshake that writes schema-valid findings
- **THEN** `converge()` SHALL be called with `min_quorum=2`, the round checkpoint SHALL contain
  findings files for both `claude_code` and `openrouter`, `consensus` SHALL report
  `quorum_received: 2`, and `reviews/consensus-plan.json` SHALL contain the same consensus

#### Scenario: Findings carry vendor attribution
- **WHEN** both lanes report a finding at the same file and line range
- **THEN** the consensus finding SHALL list both `claude_code` and `openrouter` in its vendor
  attribution, and the review ledger entry SHALL preserve both lane ids

#### Scenario: Only the agent lane verified
- **WHEN** `--verified-lanes claude_code` is the only lane and no active policy lowers the quorum
- **THEN** `converge()` SHALL return `capability_unavailable` with `missing_lanes` naming the
  counting lanes not verified, and no handshake file SHALL be written

### Requirement: Cloud Single-Vendor Policy Retirement

The temporary cloud single-vendor policy SHALL be retired only after an evidence file
`openspec/changes/openrouter-review-lane/evidence/cloud-quorum-run.md` records a cloud-container
autopilot run on a fixture change. The run must show:
- `PLAN_REVIEW` with `min_quorum=2`;
- a `consensus-plan.json` attributing findings or confirmations to `claude_code` and to an
  `openrouter` lane;
- a ledger or spool row carrying that review's `generation_id`.

Retirement SHALL:
- delete the `cloud-container-single-vendor-2026-10-09` entry from
  `review_quorum_policy.json`, keeping the `policies` array and its `sunset` field as the
  mechanism for future exceptions;
- delete the "Review quorum in cloud containers (temporary)" section of `TRUST_POSTURE.md`;
- update `skills/autopilot/SKILL.md` so that no instruction tells a cloud worker to accept
  single-vendor review.

#### Scenario: Retirement restores quorum two in cloud
- **WHEN** the policy entry has been deleted and `resolve_quorum_policy(environment="cloud_container", verified_review_lanes=1)` is called
- **THEN** `min_quorum` SHALL be 2 for each review phase and `policy_id` SHALL be null

#### Scenario: Retirement is blocked without evidence
- **WHEN** a guard test finds `review_quorum_policy.json` without the cloud entry but no
  `evidence/cloud-quorum-run.md` in this change, or an evidence file missing a `generation_id`
- **THEN** the test SHALL fail

#### Scenario: No prose exception remains
- **WHEN** a guard test scans `TRUST_POSTURE.md` after retirement
- **THEN** it SHALL find no section titled "Review quorum in cloud containers"


#### specs/supervise/spec.md
## MODIFIED Requirements

### Requirement: Execution Profile and Review Requirements

Before launching a batch, the supervisor SHALL resolve two values by invoking
`review_dispatcher.py --check-vendors --json`, and SHALL place both in every request:

- **`execution_profile`**: verified lanes per mode (`review`, `alternative`, `quick`);
  `location`; isolation mode; and `probe_command`, the only probe a worker may run.
- **`review_requirements`**: `min_quorum` per review phase, and `counting_lanes`.
  - `min_quorum` defaults to 2 and can be overridden by the router context
    `review_min_quorum`.
  - `counting_lanes` are ordered by the `cost_policy.tiers` ladder of
    `agent-coordinator/routing.yaml`. Each lane's endpoint kind is read from the report's
    `lane_kinds`. The kind is inferred from the `probe_unsupported` reason only when
    `lane_kinds` is absent.

The worker protocol in `skills/autopilot/SKILL.md` SHALL forbid reading environment variables
or credentials to discover capabilities. `ExecutionAdapter.apply` SHALL persist the result's
`degradations` on the checkpoint attempt and SHALL return them in its summary. When the result
carries a `metered_spend_unrecorded` degradation, `apply` SHALL run
`spend_recorder.py replay --change-id <id>` once, and SHALL report the replay outcome in its
summary without failing the apply.

#### Scenario: Request carries a resolved profile
- **WHEN** `prepare` returns a batch
- **THEN** every request SHALL validate against `dispatch-request.schema.json` with non-empty
  `execution_profile.lanes.review`, `execution_profile.probe_command`, and
  `review_requirements.min_quorum` keyed by review phase

#### Scenario: Profile resolution failure blocks launch
- **WHEN** `--check-vendors --json` prints output that does not parse as JSON, or JSON carrying
  an `error` field
- **THEN** `prepare` SHALL raise without writing any attempt, and the error SHALL name the probe
  failure

#### Scenario: Below-quorum availability still launches with an honest profile
- **WHEN** `--check-vendors --json` exits 2 (below quorum) with valid JSON and no `error` field
- **THEN** `prepare` SHALL succeed, and each request's `execution_profile.lanes.review` SHALL
  list only the verified lanes, so the child parks `capability_unavailable` at its first review
  phase

#### Scenario: The per-environment quorum is resolved from data
- **WHEN** the quorum policy data declares an active `cloud_container` entry with `min_quorum` 1
  that applies below 2 verified review lanes, and `prepare` runs in a cloud container where one
  review lane verifies
- **THEN** every request's `review_requirements.min_quorum` SHALL be 1 for each review phase,
  and `review_requirements.quorum_policy` SHALL name the environment, the policy entry, and its
  sunset condition
- **AND** on a host, or in a container where two or more review lanes verify, `min_quorum` SHALL
  stay 2

#### Scenario: A verified OpenRouter lane is ranked as metered
- **WHEN** the report's `review.verified` is `["claude_code", "openrouter"]` with
  `lane_kinds: {"claude_code": "vendor-cli", "openrouter": "openrouter"}`, and the routing ladder is
  `[vendor-cli, vendor-sdk, openrouter]`
- **THEN** `counting_lanes` SHALL be `["claude_code", "openrouter"]`, and `min_quorum` SHALL be 2
  for each review phase

#### Scenario: A report without lane_kinds still ranks
- **WHEN** the report has no `lane_kinds` key
- **THEN** ranking SHALL use the previous `probe_unsupported` inference and `prepare` SHALL succeed

#### Scenario: Degradations reach the checkpoint
- **WHEN** a success result carries
  `degradations: [{code: single_vendor_review, phase: PLAN_REVIEW, detail: "codex not dispatchable"}]`
- **THEN** after `apply` the checkpoint attempt's outcome metadata and the `apply` return value
  SHALL both contain that entry unchanged

#### Scenario: Unrecorded spend is replayed on apply
- **WHEN** a result carries a `metered_spend_unrecorded` degradation and the coordinator accepts
  the replay
- **THEN** `apply` SHALL return a summary with the replayed row count, and the degradation SHALL
  remain on the checkpoint attempt

#### Scenario: Worker protocol forbids env probing
- **WHEN** a guard test scans `skills/autopilot/SKILL.md` and `skills/supervise/SKILL.md`
- **THEN** neither SHALL contain an instruction to run `env`, `printenv`, or to read API key
  variables for vendor discovery


### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 1. Focus on remaining issues.