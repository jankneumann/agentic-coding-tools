"""Tests for the database client factory pattern."""

import json

import pytest

from src.config import reset_config
from src.db import DatabaseClient, SupabaseClient, create_db_client, reset_db

try:
    from src.db_postgres import (
        DirectPostgresClient,
        _coerce_filter_value,
        _encode_jsonb_param,
        _register_jsonb_codecs,
        _serialize_for_asyncpg,
        _validate_identifier,
        _validate_select_clause,
    )

    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False


class TestDatabaseClientProtocol:
    """Tests for the DatabaseClient protocol."""

    def test_supabase_client_implements_protocol(self):
        """SupabaseClient should satisfy the DatabaseClient protocol."""
        client = SupabaseClient()
        assert isinstance(client, DatabaseClient)

    def test_protocol_has_required_methods(self):
        """DatabaseClient protocol should define all required methods."""
        assert hasattr(DatabaseClient, "rpc")
        assert hasattr(DatabaseClient, "query")
        assert hasattr(DatabaseClient, "insert")
        assert hasattr(DatabaseClient, "update")
        assert hasattr(DatabaseClient, "delete")
        assert hasattr(DatabaseClient, "close")


class TestCreateDbClient:
    """Tests for the create_db_client factory function."""

    def test_factory_returns_supabase_by_default(self):
        """Default DB_BACKEND=supabase should return SupabaseClient."""
        client = create_db_client()
        assert isinstance(client, SupabaseClient)

    def test_factory_returns_supabase_explicitly(self, monkeypatch):
        """DB_BACKEND=supabase should return SupabaseClient."""
        monkeypatch.setenv("DB_BACKEND", "supabase")
        reset_config()
        reset_db()
        client = create_db_client()
        assert isinstance(client, SupabaseClient)

    def test_factory_raises_on_unknown_backend(self, monkeypatch):
        """Unknown backend should raise ValueError."""
        monkeypatch.setenv("DB_BACKEND", "unknown")
        reset_config()
        reset_db()
        with pytest.raises(ValueError, match="Unknown database backend"):
            create_db_client()

    def test_factory_raises_import_error_for_postgres_without_asyncpg(self, monkeypatch):
        """DB_BACKEND=postgres without asyncpg installed should raise ImportError."""
        monkeypatch.setenv("DB_BACKEND", "postgres")
        reset_config()
        reset_db()
        # asyncpg may or may not be installed; if not, we should get ImportError
        try:
            client = create_db_client()
            # If asyncpg is installed, client should satisfy protocol
            assert isinstance(client, DatabaseClient)
        except ImportError as e:
            assert "asyncpg" in str(e)


@pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
class TestPostgresFilterParsing:
    """Tests for PostgREST filter parsing in DirectPostgresClient."""

    def test_coerce_filter_value_uuid(self):
        """Test that UUID strings are coerced properly."""
        from uuid import UUID

        val = _coerce_filter_value("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        assert isinstance(val, UUID)

    def test_coerce_filter_value_int(self):
        """Test that integer strings are coerced to int."""
        assert _coerce_filter_value("42") == 42
        assert isinstance(_coerce_filter_value("42"), int)

    def test_coerce_filter_value_bool(self):
        """Test that boolean strings are coerced to bool."""
        assert _coerce_filter_value("true") is True
        assert _coerce_filter_value("false") is False

    def test_coerce_filter_value_string(self):
        """Test that regular strings pass through."""
        assert _coerce_filter_value("hello") == "hello"

    def test_gte_lte_filter_parsing(self):
        """Test that gte/lte filters are recognized in query params.

        Verifies the fix for the Codex review comment about
        AuditService.query() emitting gte/lte operators that were
        silently ignored on DB_BACKEND=postgres.
        """
        import inspect

        from src.db_postgres import DirectPostgresClient

        source = inspect.getsource(DirectPostgresClient.query)
        assert "=gte." in source, "query() should handle gte filters"
        assert "=lte." in source, "query() should handle lte filters"
        assert ">=" in source, "gte should translate to >= operator"
        assert "<=" in source, "lte should translate to <= operator"

    def test_validate_identifier_accepts_safe_names(self):
        assert _validate_identifier("work_queue") == "work_queue"
        result = _validate_identifier("public.work_queue", allow_qualified=True)
        assert result == "public.work_queue"

    def test_validate_identifier_rejects_unsafe_names(self):
        with pytest.raises(ValueError, match="Unsafe identifier"):
            _validate_identifier("work_queue; DROP TABLE users")

        with pytest.raises(ValueError, match="Unsafe identifier"):
            _validate_identifier("public.work_queue;--", allow_qualified=True)

    def test_validate_select_clause_rejects_unsafe_projection(self):
        assert _validate_select_clause("*") == "*"
        assert _validate_select_clause("id, task_type") == "id, task_type"

        with pytest.raises(ValueError, match="Unsafe identifier"):
            _validate_select_clause("id, task_type; DROP TABLE work_queue")

    def test_coerce_filter_value_iso_datetime(self):
        """ISO timestamps in filters must become datetime for asyncpg."""
        from datetime import datetime

        val = _coerce_filter_value("2026-08-19T12:34:56.789123+00:00")
        assert isinstance(val, datetime)
        assert val.tzinfo is not None

    def test_coerce_filter_value_leaves_non_timestamp_strings(self):
        assert _coerce_filter_value("completed") == "completed"
        assert _coerce_filter_value("2026-08-19") == "2026-08-19"


@pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
class TestSerializeForAsyncpg:
    """Services write ISO timestamp strings (PostgREST JSON contract).

    asyncpg rejects those strings for TIMESTAMPTZ columns with
    DataError: invalid input for query argument $N. The postgres
    adapter must coerce them to datetime before binding.
    """

    def test_iso_timestamp_becomes_datetime(self):
        from datetime import datetime

        # datetime.now(UTC).isoformat() — the issue_close payload shape
        raw = "2026-08-19T12:34:56.789123+00:00"
        out = _serialize_for_asyncpg(raw)
        assert isinstance(out, datetime)
        assert out.isoformat() == raw

    def test_zulu_timestamp_becomes_datetime(self):
        from datetime import datetime

        out = _serialize_for_asyncpg("2026-08-19T12:34:56Z")
        assert isinstance(out, datetime)
        assert out.utcoffset() is not None

    def test_plain_strings_pass_through(self):
        assert _serialize_for_asyncpg("completed") == "completed"
        assert _serialize_for_asyncpg("Done in PR #42") == "Done in PR #42"

    def test_dicts_still_json_encoded(self):
        import json

        out = _serialize_for_asyncpg({"body": "hello"})
        assert out == json.dumps({"body": "hello"})

    def test_datetime_objects_pass_through(self):
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        assert _serialize_for_asyncpg(now) is now


@pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
class TestPostgresUpdateTimestampBinding:
    """Prove-it: issue_close's UPDATE binds datetime, not ISO strings.

    Reproduction of DataError: invalid input for query argument $2 —
    $1 is status, $2 is completed_at. Without coercion asyncpg rejects
    the ISO string against TIMESTAMPTZ.
    """

    @pytest.mark.asyncio
    async def test_update_binds_iso_timestamps_as_datetime(self):
        from datetime import datetime
        from uuid import uuid4

        captured: dict = {}

        class FakeConn:
            async def fetch(self, query, *args):
                captured["query"] = query
                captured["args"] = args
                return []

        class FakeAcquire:
            async def __aenter__(self):
                return FakeConn()

            async def __aexit__(self, *exc):
                return None

        class FakePool:
            def acquire(self):
                return FakeAcquire()

        client = DirectPostgresClient()
        client._pool = FakePool()  # type: ignore[assignment]

        issue_id = uuid4()
        await client.update(
            "work_queue",
            match={"id": issue_id},
            data={
                "status": "completed",
                "completed_at": "2026-08-19T12:34:56.789123+00:00",
                "closed_at": "2026-08-19T12:34:56.789123+00:00",
            },
        )

        args = captured["args"]
        # $1 status, $2 completed_at, $3 closed_at, $4 match id
        assert args[0] == "completed"
        assert isinstance(args[1], datetime), (
            "completed_at ($2) must be datetime, not ISO string — "
            f"got {type(args[1]).__name__}"
        )
        assert isinstance(args[2], datetime)
        assert args[3] == issue_id


@pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
class TestEncodeJsonbParam:
    """DirectPostgresClient._encode_jsonb_param — the jsonb codec's encoder.

    Regression coverage for Canonical Validation 6: DirectPostgresClient.query()
    never decoded jsonb columns, so Task.result came back as a raw JSON string
    instead of a dict under DB_BACKEND=postgres. The fix registers a jsonb/json
    type codec on the pool; this encoder is the write side of that codec and
    must not double-encode values _serialize_for_asyncpg (or a caller) already
    turned into JSON text.
    """

    def test_pre_serialized_string_passes_through_unchanged(self):
        """A string already produced by json.dumps() must not be re-encoded.

        _serialize_for_asyncpg() already turns dicts into JSON strings before
        asyncpg sees them; some callers (e.g. work_queue.py's
        agent_requirements) do the same by hand. If the encoder re-encoded an
        already-serialized string, the column would store a quoted JSON
        string instead of the object.
        """
        already_serialized = json.dumps({"reason": "cancelled_by_projection_reconcile"})
        assert _encode_jsonb_param(already_serialized) == already_serialized

    def test_dict_not_pre_serialized_gets_encoded(self):
        out = _encode_jsonb_param({"a": 1})
        assert out == json.dumps({"a": 1})
        assert json.loads(out) == {"a": 1}

    def test_list_not_pre_serialized_gets_encoded(self):
        out = _encode_jsonb_param(["x", "y"])
        assert out == json.dumps(["x", "y"])

    def test_none_encodes_to_json_null(self):
        """Defensive: even if asyncpg ever invoked the encoder for a NULL
        parameter, it must round-trip to Python None, not raise or store the
        literal string 'None'.
        """
        out = _encode_jsonb_param(None)
        assert json.loads(out) is None

    def test_plain_string_that_is_not_json_passes_through(self):
        # e.g. a caller that (incorrectly) binds a bare string to a jsonb
        # column — still must not be double-json-encoded.
        assert _encode_jsonb_param("not json") == "not json"


@pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
class TestRegisterJsonbCodecs:
    """DirectPostgresClient._register_jsonb_codecs — the pool init hook."""

    @pytest.mark.asyncio
    async def test_registers_jsonb_and_json_with_text_codec(self):
        calls: list[dict] = []

        class FakeConn:
            async def set_type_codec(self, typename, *, schema, encoder, decoder, format):
                calls.append(
                    {
                        "typename": typename,
                        "schema": schema,
                        "encoder": encoder,
                        "decoder": decoder,
                        "format": format,
                    }
                )

        await _register_jsonb_codecs(FakeConn())  # type: ignore[arg-type]

        typenames = {call["typename"] for call in calls}
        assert typenames == {"jsonb", "json"}
        for call in calls:
            assert call["schema"] == "pg_catalog"
            assert call["format"] == "text"
            assert call["encoder"] is _encode_jsonb_param
            assert call["decoder"] is json.loads

    @pytest.mark.asyncio
    async def test_registered_codec_round_trips_a_dict(self):
        """Prove the encoder/decoder pair registered here actually round-trips."""
        registered: dict = {}

        class FakeConn:
            async def set_type_codec(self, typename, *, schema, encoder, decoder, format):
                registered[typename] = (encoder, decoder)

        await _register_jsonb_codecs(FakeConn())  # type: ignore[arg-type]

        encoder, decoder = registered["jsonb"]
        payload = {"reason": "cancelled_by_projection_reconcile"}
        # Simulate asyncpg's write path (encoder) followed by its read path
        # from the same wire text (decoder) — this is the exact regression
        # covered by TestCompleteTaskTerminalCancellation in
        # tests/integration/postgres/test_work_queue_postgres.py.
        wire_text = encoder(payload)
        assert decoder(wire_text) == payload


@pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
class TestPoolRegistersJsonbCodecInit:
    """DirectPostgresClient._get_pool() must wire the codec into the pool."""

    @pytest.mark.asyncio
    async def test_get_pool_passes_init_hook_to_create_pool(self, monkeypatch):
        import src.db_postgres as db_postgres_module

        captured_kwargs: dict = {}

        async def fake_create_pool(**kwargs):
            captured_kwargs.update(kwargs)
            return "fake-pool"

        monkeypatch.setattr(db_postgres_module.asyncpg, "create_pool", fake_create_pool)

        client = DirectPostgresClient()
        pool = await client._get_pool()

        assert pool == "fake-pool"
        assert captured_kwargs.get("init") is db_postgres_module._register_jsonb_codecs
