"""A first-run migration failure must stop the boot, not be recorded as success.

``run_migrations`` treated *every* error on a first run (empty
``schema_migrations``) as "this database was seeded by Docker initdb" and wrote
a tracking row saying the migration had been applied. Because later runs skip
anything with a tracking row, one genuinely broken migration became permanent,
invisible schema skew.

That is how it actually failed. ``000_bootstrap.sql`` contained
``GRANT anon TO postgres`` — a hardcoded superuser name. On a database owned by
any other role it aborted with ``role "postgres" does not exist``. Recorded as
applied. The ``auth`` schema and ``supabase_realtime`` publication it should
have created therefore never existed, so 001 aborted at ``ALTER PUBLICATION``,
002 at ``auth.role()``, and 015 at the ``work_queue`` table 001 never got to
create — each recorded as applied in turn.

The result was a coordinator that booted cleanly, logged "33 migrations
applied", and ran against a database missing 16 of its 31 tables and 65 of its
78 functions. The one visible symptom was that every single ``audit_log``
insert failed, because 024's trigger survived and called ``coordinator_notify()``
— a function 015 never created.

Nothing in the suite could catch this: the migration runner was only ever
exercised against fakes or an already-populated database.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.migrations import _is_already_applied_error

MIGRATIONS = Path(__file__).resolve().parent.parent / "database" / "migrations"


class _PgError(Exception):
    """Stand-in for asyncpg errors, which expose ``sqlstate``."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


@pytest.mark.parametrize(
    "sqlstate",
    [
        "42P07",  # duplicate_table
        "42710",  # duplicate_object
        "42723",  # duplicate_function
        "42P06",  # duplicate_schema
        "42701",  # duplicate_column
    ],
)
def test_duplicate_object_errors_are_treated_as_already_applied(sqlstate: str) -> None:
    """The Docker-initdb case this branch exists for must keep working."""
    assert _is_already_applied_error(_PgError(sqlstate)) is True


@pytest.mark.parametrize(
    "sqlstate",
    [
        "42704",  # undefined_object — `role "postgres" does not exist`
        "42P01",  # undefined_table — `relation "work_queue" does not exist`
        "42883",  # undefined_function — `coordinator_notify(...) does not exist`
        "42601",  # syntax_error
        "23505",  # unique_violation
    ],
)
def test_real_failures_are_not_swallowed(sqlstate: str) -> None:
    """These are the errors that were silently recorded as success.

    42704 is the exact SQLSTATE of the bootstrap failure. A migration that
    cannot find something must never be mistaken for one whose objects are
    already there — they are opposite conditions.
    """
    assert _is_already_applied_error(_PgError(sqlstate)) is False


def test_non_database_errors_are_not_swallowed() -> None:
    """An error with no ``sqlstate`` at all is not a duplicate-object error."""
    assert _is_already_applied_error(RuntimeError("boom")) is False


def test_no_migration_hardcodes_the_postgres_superuser_name() -> None:
    """Migrations must not assume the owning role is named ``postgres``.

    ``000_bootstrap.sql`` exists precisely to stand in for objects a managed
    provider creates automatically, so it cannot also depend on that provider's
    conventional role name. Grant to ``CURRENT_USER`` instead.
    """
    offenders: list[str] = []
    pattern = re.compile(r"\bGRANT\s+\w+\s+TO\s+postgres\b", re.I)
    for path in sorted(MIGRATIONS.glob("*.sql")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if line.lstrip().startswith("--"):
                continue
            if pattern.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Migration(s) grant to a hardcoded `postgres` role. On a database owned "
        "by any other role this aborts with `role \"postgres\" does not exist` "
        "and takes every dependent migration down with it:\n  "
        + "\n  ".join(offenders)
    )
