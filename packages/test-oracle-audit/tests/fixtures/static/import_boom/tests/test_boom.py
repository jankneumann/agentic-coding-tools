raise RuntimeError("test module imported at analysis time")

from pkg.calc import add


def test_unchecked():
    add(1, 2)


def test_checked():
    assert add(1, 2) == 3
