from pkg import mirror_attr


def test_alpha():
    assert mirror_attr.alpha(1) == 2


def test_beta():
    assert mirror_attr.beta(1) == 3
