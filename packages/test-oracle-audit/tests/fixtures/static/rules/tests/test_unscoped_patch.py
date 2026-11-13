import os
from unittest.mock import patch

from pkg.mod import add


def test_patch_stdlib():
    with patch("os.path.exists") as exists:
        exists.return_value = True
        assert add(1, 2) == 3


def test_patch_builtin(monkeypatch):
    monkeypatch.setattr("builtins.open", lambda *a, **k: None)
    assert add(1, 2) == 3


def test_patch_uncovered_module():
    with patch("pkg.other.fetch", return_value=1):
        assert add(1, 2) == 3


def test_patch_object_stdlib():
    with patch.object(os, "getcwd", return_value="/"):
        assert add(1, 2) == 3


@patch("os.getcwd")
def test_patch_decorator(getcwd):
    assert add(1, 2) == 3


def test_patch_in_scope():
    with patch("pkg.mod.helper", return_value=1):
        assert add(1, 2) == 3


def test_monkeypatch_in_scope(monkeypatch):
    monkeypatch.setattr("pkg.mod.CONST", 3)
    assert add(1, 2) == 3
