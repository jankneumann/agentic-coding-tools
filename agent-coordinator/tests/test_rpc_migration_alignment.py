"""Guard against drift between runtime RPC calls and migration function names."""

from __future__ import annotations

import re
from pathlib import Path

RPC_CALL_RE = re.compile(r'\.rpc\(\s*"([a-zA-Z_][a-zA-Z0-9_]*)"')
MIGRATION_FUNC_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\(",
    re.IGNORECASE,
)


def _extract_called_rpcs(path: Path) -> set[str]:
    return set(RPC_CALL_RE.findall(path.read_text()))


def _extract_migration_functions(migrations_dir: Path) -> set[str]:
    functions: set[str] = set()
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        for match in MIGRATION_FUNC_RE.findall(sql_file.read_text()):
            # We only call unqualified names from app code.
            functions.add(match.split(".")[-1])
    return functions


def test_coordination_api_rpc_calls_match_migrations() -> None:
    """RPCs in the HTTP runtime path must exist in canonical migrations."""
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    migrations_dir = repo_root / "supabase" / "migrations"

    runtime_service_files = [
        src_dir / "locks.py",
        src_dir / "work_queue.py",
        src_dir / "memory.py",
        src_dir / "handoffs.py",
        src_dir / "profiles.py",
    ]

    called_rpcs: set[str] = set()
    for file_path in runtime_service_files:
        called_rpcs.update(_extract_called_rpcs(file_path))

    migration_functions = _extract_migration_functions(migrations_dir)
    missing = called_rpcs - migration_functions

    assert not missing, (
        "Runtime RPC function(s) are not defined in canonical migrations: "
        f"{sorted(missing)}"
    )
