import pkg.mod as m
from pkg.mod import _helper, add


def test_calls_private_helper():
    assert _helper(2) == 4


def test_private_module_attribute():
    value = m._secret()
    assert value == 1
