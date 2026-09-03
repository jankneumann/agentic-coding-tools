"""The audit payload must match the audit_log table (issue #455).

``AuditService.log_operation`` built a payload containing ``delegated_from``,
a column ``audit_log`` did not have. Every audit insert therefore failed on the
PostgreSQL backend and the coordinator recorded **no audit trail at all** — for
every operation, not just one feature.

Nothing caught it, and nothing could have, because three layers each hid it:

* ``_insert_audit_entry`` caught the exception and returned it as a value;
* the fire-and-forget path discarded that value without reading it;
* ``log_operation`` returned ``AuditResult(success=True)`` regardless.

The existing tests mock the Supabase HTTP transport by URL prefix, so nothing
in the suite ever had PostgreSQL parse the statement.

So this test asserts the *contract between the code and the schema* without
needing a database: it reads the columns the migrations create for
``audit_log`` and asserts every key the service writes is one of them.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "database" / "migrations"

#: Keys ``AuditService.log_operation`` puts in its insert payload.
#: Kept as a literal list so a reviewer sees the payload shape here; the test
#: below proves the list matches the source rather than trusting it.
AUDIT_PAYLOAD_KEYS = {
    "agent_id",
    "agent_type",
    "operation",
    "parameters",
    "result",
    "duration_ms",
    "success",
    "error_message",
    "delegated_from",
}


def _audit_log_columns() -> set[str]:
    """Columns ``audit_log`` has after every migration is applied."""
    columns: set[str] = set()
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = path.read_text()

        create = re.search(
            r"CREATE TABLE IF NOT EXISTS audit_log\s*\((.*?)\n\);",
            sql,
            re.S | re.I,
        )
        if create:
            for line in create.group(1).splitlines():
                line = line.strip()
                if not line or line.startswith("--"):
                    continue
                name = line.split()[0].strip(",")
                if name.upper() not in {
                    "PRIMARY",
                    "UNIQUE",
                    "CHECK",
                    "FOREIGN",
                    "CONSTRAINT",
                }:
                    columns.add(name)

        for alter in re.finditer(
            r"ALTER TABLE audit_log\s+ADD COLUMN(?: IF NOT EXISTS)?\s+(\w+)",
            sql,
            re.I,
        ):
            columns.add(alter.group(1))

    return columns


def _payload_keys_in_source() -> set[str]:
    """The keys the service actually builds, parsed from src/audit.py."""
    source = (Path(__file__).resolve().parent.parent / "src" / "audit.py").read_text()
    block = re.search(r"data\s*=\s*\{(.*?)\n\s*\}", source, re.S)
    assert block, "could not locate the audit payload literal in src/audit.py"
    return set(re.findall(r'"(\w+)":', block.group(1)))


def test_every_audit_payload_key_is_a_real_column() -> None:
    """The whole audit trail dies if one key has no column behind it."""
    columns = _audit_log_columns()
    assert columns, "failed to parse audit_log columns from the migrations"

    missing = sorted(AUDIT_PAYLOAD_KEYS - columns)
    assert not missing, (
        f"AuditService writes column(s) audit_log does not have: {missing}. "
        f"Every audit insert will fail and the trail will be silently empty. "
        f"Add them in a migration (see 035_audit_log_delegated_from.sql)."
    )


def test_declared_payload_matches_the_source() -> None:
    """Keep this file honest: the literal above must match src/audit.py.

    Without this, someone adding a key to the payload would leave the column
    check asserting a stale list and the guard would quietly stop guarding.
    """
    assert _payload_keys_in_source() == AUDIT_PAYLOAD_KEYS


def test_delegated_from_is_on_audit_log_not_only_agent_sessions() -> None:
    """Regression: migration 013 added the column to the wrong table.

    013 added ``delegated_from`` to ``agent_sessions``. The audit payload needed
    it on ``audit_log``, and nothing noticed for the life of the table.
    """
    assert "delegated_from" in _audit_log_columns()
