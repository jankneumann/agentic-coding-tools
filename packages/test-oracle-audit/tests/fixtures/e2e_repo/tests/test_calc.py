from mini.calc import _normalize, add, clamp


def test_add_sums_integers():
    assert add(2, 3) == 5


def test_clamp_limits_value():
    assert clamp(15, 0, 10) == 10
    assert clamp(-4, 0, 10) == 0
    assert clamp(7, 0, 10) == 7


def test_add_runs_without_checking():
    add(1, 1)


def test_normalize_truncates():
    assert _normalize(3.9) == 3
