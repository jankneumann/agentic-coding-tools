"""Consistent JSON I/O for architecture graphs and intermediate analysis files."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load_graph(path: Path, *, quiet: bool = False) -> dict[str, Any]:
    """Load an architecture JSON file, returning its parsed contents.

    Returns an empty dict (and prints a warning) when the file is missing and
    *quiet* is ``False``.  Raises on malformed JSON.
    """
    if not path.exists():
        if not quiet:
            print(f"[warn] file not found: {path}", file=sys.stderr)
        return {}
    with open(path) as f:
        return json.load(f)


def save_json(
    path: Path,
    data: Any,
    *,
    ensure_ascii: bool = False,
    indent: int = 2,
) -> Path:
    """Write *data* as pretty-printed JSON, creating parent directories.

    Returns the resolved output path.
    """
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
        f.write("\n")
    return path
