"""A scoped run must not overwrite the committed full-scope diagnostics.

``docs/architecture-analysis/architecture.diagnostics.json`` is tracked, and
architecture provenance records its content digest. Two skills write it:
``refresh-architecture`` runs the validator unscoped, while ``validate-feature``
runs it scoped to the changed files. Both used the same default destination, so
whichever ran last decided what got committed -- and a scoped report replacing a
full one is invisible in review, because the file still parses and still looks
like diagnostics. It only shows up as a very large deletion in the diff.

The default destination now follows the scope. An explicit ``--output`` still
wins, so callers keep control, but pointing one at the canonical path from a
scoped run warns.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_flows import (  # noqa: E402
    CANONICAL_OUTPUT,
    SCOPED_OUTPUT,
    build_parser,
    resolve_output_path,
)


class TestDefaultDestination:
    def test_full_run_writes_the_canonical_artifact(self) -> None:
        assert resolve_output_path(None, None) == CANONICAL_OUTPUT

    def test_scoped_run_does_not_write_the_canonical_artifact(self) -> None:
        resolved = resolve_output_path(None, ["a.py", "b.py"])
        assert resolved == SCOPED_OUTPUT
        assert resolved != CANONICAL_OUTPUT

    def test_empty_scope_is_still_a_scoped_run(self) -> None:
        """A diff that matched nothing scopes to zero files -- which is still a
        scoped report, and emphatically not a full one."""
        assert resolve_output_path(None, []) == SCOPED_OUTPUT

    def test_the_two_defaults_are_distinct_paths(self) -> None:
        assert CANONICAL_OUTPUT != SCOPED_OUTPUT


class TestExplicitOutput:
    def test_explicit_output_wins_for_a_full_run(self, tmp_path: Path) -> None:
        target = tmp_path / "elsewhere.json"
        assert resolve_output_path(target, None) == target

    def test_explicit_output_wins_for_a_scoped_run(self, tmp_path: Path) -> None:
        target = tmp_path / "scoped-elsewhere.json"
        assert resolve_output_path(target, ["a.py"]) == target

    def test_scoped_run_at_the_canonical_path_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("WARNING"):
            resolved = resolve_output_path(CANONICAL_OUTPUT, ["a.py"])
        assert resolved == CANONICAL_OUTPUT, "an explicit path is still honored"
        assert "full-scope artifact" in caplog.text

    def test_full_run_at_the_canonical_path_is_silent(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("WARNING"):
            resolve_output_path(CANONICAL_OUTPUT, None)
        assert caplog.text == "", "a full run writing the full artifact is normal"


class TestParserDefault:
    def test_output_default_is_deferred_to_resolution(self) -> None:
        """--output must not carry a hardcoded default, or every scoped run
        would look explicit and land back on the canonical path."""
        args = build_parser().parse_args([])
        assert args.output is None
