from pkg.shared import one, two


def test_first():
    assert one(1) == 1
    assert two(1) == 2


def test_second():
    assert one(2) == 2
