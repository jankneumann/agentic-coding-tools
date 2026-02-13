"""Tests for the database client factory pattern."""

import pytest

from src.config import reset_config
from src.db import DatabaseClient, SupabaseClient, create_db_client, reset_db


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
