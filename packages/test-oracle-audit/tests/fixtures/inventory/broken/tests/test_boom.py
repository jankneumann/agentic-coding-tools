raise RuntimeError("this module cannot be imported")


def test_never_collected():
    assert True
