from pkg.mod import add, sub


def test_add_returns_sum():
    assert add(2, 3) == 5


def test_sub_returns_difference():
    result = sub(5, 3)
    assert result == 2
    assert sub(0, 1) == -1
