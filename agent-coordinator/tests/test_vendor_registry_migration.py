"""Contract checks for the additive vendor-registry migration."""

from pathlib import Path

MIGRATION = Path(__file__).parents[1] / "database/migrations/041_vendor_registry.sql"


def test_vendor_registry_migration_declares_state_tables_and_atomic_rpcs() -> None:
    sql = MIGRATION.read_text()

    for table in ("vendor_probe_state", "vendor_rate_limits"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    for function in (
        "upsert_vendor_probe_state",
        "record_vendor_rate_limit",
        "compact_vendor_rate_limits",
    ):
        assert f"CREATE OR REPLACE FUNCTION {function}" in sql
