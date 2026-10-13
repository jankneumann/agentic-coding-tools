from unittest.mock import patch

from pkg.mod import Thing


def test_combo():
    with patch("os.getcwd"):
        thing = Thing()
        assert thing._cache == {}
