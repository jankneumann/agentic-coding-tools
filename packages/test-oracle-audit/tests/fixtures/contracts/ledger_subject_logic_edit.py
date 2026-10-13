"""Fixture module whose test functions get labelled (never collected: fixtures/ is excluded)."""


def test_y():
    result = compute(2, 3)
    assert result == 6


class TestGroup:
    def test_method(self):
        values = [compute(1, 1), compute(2, 2)]
        assert values == [2, 5]


def compute(a, b):
    return a + b
