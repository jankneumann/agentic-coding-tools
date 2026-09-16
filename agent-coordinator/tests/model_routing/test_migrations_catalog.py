"""Contract tests for the additive model-routing migration."""

from __future__ import annotations

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "database" / "migrations"


def test_model_routing_migration_is_additive_and_idempotent() -> None:
    migration = MIGRATIONS / "040_model_routing.sql"
    sql = migration.read_text()

    for table in (
        "model_catalog",
        "model_posteriors",
        "routing_decisions",
        "routing_spend_ledger",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql

    normalized = sql.upper()
    assert "ALTER TABLE" not in normalized
    assert "DROP TABLE" not in normalized
    assert normalized.count("CREATE INDEX IF NOT EXISTS") >= 2


def test_model_routing_migration_matches_endpoint_kind_contract() -> None:
    sql = (MIGRATIONS / "040_model_routing.sql").read_text()

    for kind in ("vendor-cli", "vendor-sdk", "openrouter", "local"):
        assert f"'{kind}'" in sql
    assert "UNIQUE (vendor, model, endpoint_kind)" in sql


def test_deleting_catalog_entry_cascades_to_its_posteriors() -> None:
    sql = (MIGRATIONS / "040_model_routing.sql").read_text()

    assert "REFERENCES model_catalog(id) ON DELETE CASCADE" in sql
