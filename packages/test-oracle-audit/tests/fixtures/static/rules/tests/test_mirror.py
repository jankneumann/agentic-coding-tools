from pkg.mirror import alpha, beta


def test_alpha():
    assert alpha(1) == 2


def test_beta():
    assert beta(1) == 3
