from mini.calc import bucket, clamp, is_adult, percent, sign


def test_arithmetic_strong():
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(11, 0, 10) == 10
    assert clamp(0, 0, 10) == 0
    assert clamp(10, 0, 10) == 10
    assert sign(3) == 1
    assert sign(-3) == -1
    assert sign(0) == 0
    assert percent(1, 4) == 25.0
    assert percent(1, 0) == 0.0
    assert bucket(5) == 0
    assert bucket(10) == 1
    assert bucket(50) == 1
    assert bucket(100) == 2
    assert bucket(500) == 2


def test_arithmetic_not_none_only():
    assert clamp(5, 0, 10) is not None
    assert sign(3) is not None
    assert percent(1, 4) is not None
    assert bucket(5) is not None


def test_is_adult_boundary():
    assert is_adult(18) is True
    assert is_adult(17) is False
