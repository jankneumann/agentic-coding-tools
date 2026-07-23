from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

import pytest
from code_search_pkg.identifiers import attempt_chunk_table_name, index_chunk_table_name
from code_search_pkg.schema import CodeChunk, chunk_set_digest, stable_chunk_id


def test_chunk_id_is_path_aware_and_deterministic():
    kwargs = {
        "chunk_ordinal": 0,
        "start_line": 1,
        "end_line": 3,
        "content": "def f():\n    return 1\n",
        "pipeline_fingerprint": "a" * 64,
    }
    first = stable_chunk_id(file_path="src/a.py", **kwargs)

    assert first == stable_chunk_id(file_path="src/a.py", **kwargs)
    assert first != stable_chunk_id(file_path="src/b.py", **kwargs)
    assert len(first) == 64


def test_chunk_id_changes_with_pipeline_contract_or_line_range():
    common = {
        "file_path": "src/a.py",
        "chunk_ordinal": 0,
        "start_line": 1,
        "end_line": 3,
        "content": "x",
    }
    assert stable_chunk_id(**common, pipeline_fingerprint="a" * 64) != stable_chunk_id(
        **common, pipeline_fingerprint="b" * 64
    )
    assert stable_chunk_id(**common, pipeline_fingerprint="a" * 64) != stable_chunk_id(
        **{**common, "end_line": 4}, pipeline_fingerprint="a" * 64
    )
    assert stable_chunk_id(**common, pipeline_fingerprint="a" * 64) != stable_chunk_id(
        **{**common, "chunk_ordinal": 1},
        pipeline_fingerprint="a" * 64,
    )


@pytest.mark.parametrize(
    "path", ["", "/abs.py", "../secret", "src/../secret", r"src\\x.py"]
)
def test_chunk_id_rejects_unsafe_paths(path):
    with pytest.raises(ValueError):
        stable_chunk_id(
            file_path=path,
            chunk_ordinal=0,
            start_line=1,
            end_line=1,
            content="x",
            pipeline_fingerprint="a" * 64,
        )


def test_attempt_and_final_tables_are_disjoint():
    index_id = "11111111-1111-4111-8111-111111111111"
    storage_key = "i_11111111111141118111111111111111"
    assert attempt_chunk_table_name(index_id, 1) != index_chunk_table_name(storage_key)


def test_chunk_set_digest_is_ordered_and_has_canonical_empty_value():
    first = CodeChunk("a", "src/a.py", "python", "one", 1, 1)
    second = CodeChunk("b", "src/a.py", "python", "two", 2, 2)

    assert chunk_set_digest(()) == chunk_set_digest([])
    assert chunk_set_digest([first, second]) == chunk_set_digest([first, second])
    assert chunk_set_digest([first, second]) != chunk_set_digest([second, first])
    assert chunk_set_digest([first]) != chunk_set_digest([second])


def test_heavy_adapter_keeps_memoized_compute_separate_from_attempt_writes():
    source_path = (
        Path(__file__).parents[1] / "src" / "code_search_pkg" / "indexer_pg.py"
    )
    source = source_path.read_text(encoding="utf-8")
    module = ast.parse(source)
    functions = {
        node.name: node
        for node in module.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }

    build = functions["build_file_chunks"]
    write = functions["write_changed_file"]
    assert any(
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "fn"
        and any(
            keyword.arg == "memo"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in decorator.keywords
        )
        for decorator in build.decorator_list
    )
    assert "STORAGE_ATTEMPT" not in ast.unparse(build)
    assert "replace_file" in ast.unparse(write)
    assert "stable_chunk_id" in ast.unparse(write)


def test_heavy_adapter_uses_pinned_v1_app_contexts_without_target_mount():
    source = (
        Path(__file__).parents[1] / "src" / "code_search_pkg" / "indexer_pg.py"
    ).read_text(encoding="utf-8")

    assert "coco.ContextProvider()" in source
    assert "coco.Environment(" in source
    assert "coco.AppConfig(" in source
    assert "coco.App(" in source
    assert "coco.Settings.from_env(config.cocoindex_state_path)" in source
    assert "cocoindex_database" not in source
    assert "localfs.walk_dir(" in source
    assert "coco.mount_each(" in source
    assert "mount_table_target" not in source
    assert "IdGenerator" not in source


@pytest.mark.asyncio
async def test_final_read_rejects_transient_worktree_content_before_chunking(
    tmp_path: Path,
) -> None:
    from code_search_pkg.indexer_pg import (
        ExactSourceMismatchError,
        _read_exact_planned_text,
    )

    source = tmp_path / "app.py"
    planned = b"VALUE = 'planned'\n"
    transient = b"VALUE = 'transient'\n"
    source.write_bytes(planned)
    expected_digest = hashlib.sha256(planned).hexdigest()

    class ReadableFile:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.cached: bytes | None = None

        async def read(self) -> bytes:
            if self.cached is None:
                self.cached = self.path.read_bytes()
            return self.cached

        async def read_text(self, **_kwargs: Any) -> str:
            raise AssertionError("verified bytes must not be read from the file twice")

    source.write_bytes(transient)
    file = ReadableFile(source)
    with pytest.raises(ExactSourceMismatchError, match="planned Git blob"):
        await _read_exact_planned_text(file, expected_digest)  # type: ignore[arg-type]

    source.write_bytes(planned)
    assert file.cached == transient
    planned_file = ReadableFile(source)
    assert (
        await _read_exact_planned_text(planned_file, expected_digest)  # type: ignore[arg-type]
        == planned.decode("utf-8")
    )
