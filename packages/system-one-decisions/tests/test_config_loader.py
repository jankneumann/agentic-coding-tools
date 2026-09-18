"""Tests for the threshold config loader.

Spec: specs/system-one-decisions/spec.md
  "Threshold defaults resolve from a package-owned data file, never a literal"
"""

from __future__ import annotations

import pytest


def test_defaults_load_from_the_packaged_config() -> None:
    from system_one_decisions._config import DEFAULT_ACT_FLOOR, DEFAULT_APPROVE_FLOOR

    assert DEFAULT_ACT_FLOOR == 0.6
    assert DEFAULT_APPROVE_FLOOR == 0.9


def test_load_thresholds_returns_the_same_values_as_the_module_constants() -> None:
    from system_one_decisions import _config

    loaded = _config.load_thresholds()
    assert loaded["defaults"]["act_floor"] == _config.DEFAULT_ACT_FLOOR
    assert loaded["defaults"]["approve_floor"] == _config.DEFAULT_APPROVE_FLOOR


def test_missing_config_file_raises_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A packaging mistake (file not shipped) should fail loud, not silently
    fall back to a hardcoded value -- that would defeat the whole point of
    moving thresholds out of the source code."""
    from system_one_decisions import _config

    class _MissingResource:
        def __truediv__(self, _name: str) -> _MissingResource:
            return self

        def read_text(self, *_args: object, **_kwargs: object) -> str:
            raise FileNotFoundError("thresholds.json not packaged")

    monkeypatch.setattr(_config, "_resource_root", lambda: _MissingResource())
    _config.load_thresholds.cache_clear()
    try:
        with pytest.raises(FileNotFoundError):
            _config.load_thresholds()
    finally:
        _config.load_thresholds.cache_clear()
