"""Regression checks for Cedar policy seed alignment."""

from __future__ import annotations

from pathlib import Path


def test_cedar_write_policy_seed_includes_check_guardrails() -> None:
    migrations_dir = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
    migration_text = (
        migrations_dir / "011_update_cedar_write_policy_check_guardrails.sql"
    ).read_text()
    assert 'Action::"check_guardrails"' in migration_text
