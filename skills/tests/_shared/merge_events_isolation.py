"""Keep merge-metrics tests from writing into the working tree.

``merge_events.emit_event`` takes ``log_path`` as a keyword-only argument
defaulting to the *relative* path ``docs/merge-logs/metrics.jsonl``. The default
is bound at definition time, so it resolves against whatever the current working
directory happens to be — for CI and for anyone running pytest from the repo,
that is a real ``skills/docs/`` tree that no test cleans up.

Several production entry points (``auto_rebase``, ``merge_watcher``,
``post_merge_pipeline``) call ``emit_event`` without a path, and the suites that
exercise them mock the git calls but not the emit. This surfaced when those
suites were first wired into CI.

Patching ``merge_events.emit_event`` would not help: every caller does
``from merge_events import emit_event``, so they hold their own reference to the
function object. Rebinding the default *on that shared function object* is what
reaches all of them at once.

Usage — in a conftest.py beside the tests::

    from merge_events_isolation import isolate_merge_metrics_log  # noqa: F401
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SKILLS_ROOT = Path(__file__).resolve().parents[2]
_MERGE_SCRIPTS = _SKILLS_ROOT / "merge-pull-requests" / "scripts"


@pytest.fixture(autouse=True)
def isolate_merge_metrics_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point emit_event's default log at tmp_path for the duration of a test."""
    if str(_MERGE_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_MERGE_SCRIPTS))

    try:
        import merge_events
    except ImportError:
        # Suite does not exercise the merge-metrics path; nothing to isolate.
        yield None
        return

    defaults = merge_events.emit_event.__kwdefaults__
    if not defaults or "log_path" not in defaults:
        # Signature changed — fail loudly rather than silently stop isolating
        # and let tests start writing to the working tree again.
        raise RuntimeError(
            "merge_events.emit_event no longer has a keyword-only `log_path` "
            "default; update tests/_shared/merge_events_isolation.py."
        )

    target = tmp_path / "merge-logs" / "metrics.jsonl"
    patched = dict(defaults)
    patched["log_path"] = target
    monkeypatch.setattr(merge_events.emit_event, "__kwdefaults__", patched)
    yield target
