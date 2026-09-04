"""Tests for the database client factory pattern."""

import tomllib
from pathlib import Path

import pytest

from src.config import reset_config
from src.db import DatabaseClient, SupabaseClient, create_db_client, reset_db

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

try:
    from src.db_postgres import (
        DirectPostgresClient,
        _coerce_filter_value,
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


class TestAsyncpgIsABaseDependency:
    """DB_BACKEND defaults to "postgres" (#456), so asyncpg must be installed
    by a plain, extra-free install — not gated behind the optional
    ``postgres`` extra.

    Before this fix, ``asyncpg`` lived only in ``[project.optional-
    dependencies].postgres``. A base install (``pip install
    agent-coordinator`` / ``uv sync`` with no extras) then hit the dynamic
    import in ``create_db_client()`` and raised ``ImportError`` for the
    *default* configuration — the package could not start out of the box.
    See the P1 review finding on PR #464.
    """

    def test_asyncpg_is_a_base_dependency_in_pyproject(self) -> None:
        data = tomllib.loads(PYPROJECT.read_text())
        base_deps = data["project"]["dependencies"]
        assert any(dep.split(">=")[0].split("==")[0].strip() == "asyncpg" for dep in base_deps), (
            "asyncpg must be a base dependency (not only in an optional extra) "
            "because DB_BACKEND defaults to 'postgres'."
        )

    def test_asyncpg_is_importable_without_the_postgres_extra(self) -> None:
        """This is the actual failure mode: the dynamic import in
        create_db_client()/db_postgres.py must succeed on whatever
        environment this test suite runs in, without requiring an extra.
        """
        import importlib

        importlib.import_module("asyncpg")


class TestCreateDbClient:
    """Tests for the create_db_client factory function."""

    @pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
    def test_factory_returns_postgres_by_default(self, monkeypatch):
        """With DB_BACKEND unset the factory must pick PostgreSQL.

        This asserted ``supabase`` until the default was flipped (#456). It also
        read the *ambient* ``DB_BACKEND`` instead of clearing it, so it silently
        tested whatever the developer's shell happened to export rather than the
        default — clearing the variable is what makes this a default test at all.
        """
        from src.db_postgres import DirectPostgresClient

        monkeypatch.delenv("DB_BACKEND", raising=False)
        reset_config()
        reset_db()
        client = create_db_client()
        assert isinstance(client, DirectPostgresClient)

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

    def test_cs_filter_parsing(self):
        """Array-contains (cs) must translate to @> so label filters work.

        Silently ignoring cs was how list_issues post-filtered after LIMIT
        and hid newly inserted issues (#429).
        """
        import inspect

        from src.db_postgres import DirectPostgresClient

        source = inspect.getsource(DirectPostgresClient.query)
        assert "=cs." in source, "query() should handle cs (contains) filters"
        assert "@>" in source, "cs should translate to PostgreSQL @>"

    def test_parse_postgrest_array_literal(self):
        from src.db_postgres import _parse_postgrest_array_literal

        assert _parse_postgrest_array_literal("{api,followup}") == ["api", "followup"]
        assert _parse_postgrest_array_literal('{"change:__probe__"}') == [
            "change:__probe__"
        ]
        assert _parse_postgrest_array_literal('{"task:1.1","change:foo"}') == [
            "task:1.1",
            "change:foo",
        ]

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
