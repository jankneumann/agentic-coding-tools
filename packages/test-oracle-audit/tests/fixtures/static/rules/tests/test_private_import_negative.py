from pkg.mod import __version__, add
from tests.helpers import _build


def test_public_only():
    assert add(1, 2) == 3


def test_test_helper_private_name():
    built = _build()
    assert built == 1


def test_dunder_import():
    assert __version__ == "1"
