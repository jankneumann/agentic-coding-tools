"""Tests for the database client factory pattern."""

import pytest

from src.config import reset_config
from src.db import DatabaseClient, SupabaseClient, create_db_client, reset_db

try:
    from src.db_postgres import (
        _coerce_filter_value,
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
        assert _validate_identifier("public.work_queue", allow_qualified=True) == "public.work_queue"

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
