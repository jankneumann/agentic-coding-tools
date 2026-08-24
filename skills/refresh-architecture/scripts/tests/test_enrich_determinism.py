"""Determinism guard for treesitter_enrichment.json (follow-up to issue #362).

The enrichment pass is a committed architecture producer, so one revision must
yield one set of bytes. It did not: occurrence lists came out of
``QueryCursor.captures()`` in an order that varied between runs, so
``context_managers`` and ``type_hints`` entries swapped places and every refresh
rewrote a 1.1 MB artifact.

This defect is deliberately guarded differently from the ones in
``test_report_determinism.py``. Those were Python set-iteration order, catchable
by rendering under several pinned ``PYTHONHASHSEED`` values. This one is *not*:
two runs under a single pinned seed still disagree, because the instability is
internal to the tree-sitter query engine. The only guard that catches it is
running the producer twice under identical conditions and comparing bytes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from enrich_with_treesitter import TREESITTER_AVAILABLE  # noqa: E402

pytestmark = pytest.mark.skipif(
    not TREESITTER_AVAILABLE,
    reason="tree-sitter not installed",
)

QUERIES_DIR = SCRIPTS_DIR / "treesitter_queries"

#: Source with many same-line and same-file occurrences — annotated parameters
#: and context managers are the two categories that were observed churning.
_SOURCE = '''
"""Module docstring."""
from contextlib import suppress


def alpha(first: int, second: str, third: float) -> bool:
    # TODO: an inline marker
    with suppress(ValueError):
        return bool(first)


def beta(alpha_arg: dict, beta_arg: list, gamma_arg: set) -> None:
    with suppress(KeyError):
        pass
    try:
        pass
    except Exception:
        pass


class Gamma:
    def method(self, one: int, two: int, three: int) -> tuple:
        with suppress(TypeError):
            return (one, two, three)
'''

_RUNNER = """
import json
import sys
from pathlib import Path

sys.path.insert(0, {scripts!r})
from enrich_with_treesitter import TreeSitterEnricher

enricher = TreeSitterEnricher(queries_dir=Path({queries!r}))
enricher.enrich_python(Path(sys.argv[1]))
Path(sys.argv[2]).write_text(json.dumps(enricher.build_output(), indent=2))
"""


@pytest.fixture
def src_tree(tmp_path: Path) -> Path:
    """A source tree wide enough to expose ordering churn."""
    src = tmp_path / "src"
    src.mkdir()
    # Several modules so the instability has room to reorder across files too.
    for name in ("delta", "echo", "foxtrot", "golf"):
        (src / f"{name}.py").write_text(_SOURCE, encoding="utf-8")
    return src


def _run(src: Path, out: Path) -> str:
    """Run the enrichment in a fresh interpreter; return the artifact text.

    ``SOURCE_DATE_EPOCH`` is pinned exactly as ``run_architecture.py --staged``
    pins it. Without it ``generated_at`` correctly falls back to the wall clock,
    which would make this guard fail for a reason that is by design and mask the
    ordering defect it exists to catch.
    """
    env = dict(os.environ)
    env["SOURCE_DATE_EPOCH"] = "1700000000"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _RUNNER.format(scripts=str(SCRIPTS_DIR), queries=str(QUERIES_DIR)),
            str(src),
            str(out),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"enrichment failed:\n{result.stderr}"
    return out.read_text(encoding="utf-8")


def test_enrichment_is_byte_identical_across_runs(src_tree: Path, tmp_path: Path) -> None:
    """Repeated runs over one tree must agree exactly.

    Several runs, not two: the capture order is not stably wrong, so a single
    comparison can agree by luck.
    """
    outputs = [_run(src_tree, tmp_path / f"enrich-{i}.json") for i in range(5)]

    first = json.loads(outputs[0])
    assert first["python_patterns"]["type_hints"]["count"] > 0, (
        "fixture produced no type hints — the guard would be vacuous"
    )

    for index, text in enumerate(outputs[1:], start=1):
        assert text == outputs[0], (
            f"run {index} differs from run 0 — treesitter_enrichment.json is "
            f"not reproducible, so every refresh rewrites it"
        )


def test_occurrence_items_are_sorted_by_file_then_line(src_tree: Path, tmp_path: Path) -> None:
    """The imposed order is (file, line), which is also what a reader expects."""
    output = json.loads(_run(src_tree, tmp_path / "sorted.json"))

    for category, payload in output["python_patterns"].items():
        keys = [(i.get("file", ""), i.get("line") or 0) for i in payload["items"]]
        assert keys == sorted(keys), f"{category} items are not ordered by (file, line)"
