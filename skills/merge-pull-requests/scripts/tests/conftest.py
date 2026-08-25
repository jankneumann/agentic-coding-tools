"""Keep this suite from writing into the repository it is testing.

``merge_events.DEFAULT_LOG_PATH`` is the relative path
``docs/merge-logs/metrics.jsonl``. It resolves against the CWD, and CI runs
this suite with ``skills/`` as the working directory, so every test that
exercised a production path calling ``emit_event()`` without an explicit
``log_path`` appended real rows to the tracked
``skills/docs/merge-logs/metrics.jsonl``. Three files did:
``test_auto_rebase.py``, ``test_auto_rollback.py`` and
``test_merge_watcher.py`` -- none of them obviously about metrics, which is
precisely why patching them one by one would not hold. The next test to call
into ``auto_rebase`` would reopen it.

The redirect below is autouse and directory-wide, so it covers tests that do
not know they emit events at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The suite imports skill scripts by flat module name.
_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture(autouse=True)
def _redirect_default_merge_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Point the default merge-event log at tmp_path for every test.

    Tests that pass an explicit ``log_path`` are unaffected; this only catches
    the implicit default. Returned so a test can assert against it if it ever
    needs to.
    """
    import merge_events

    redirected = tmp_path / "default-merge-log" / "metrics.jsonl"
    monkeypatch.setattr(merge_events, "DEFAULT_LOG_PATH", redirected)
    return redirected
