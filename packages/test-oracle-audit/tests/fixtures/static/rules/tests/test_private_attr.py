import unittest

from pkg.mod import Thing, add


def test_private_assert():
    thing = Thing()
    assert thing._cache == {}


def test_private_in_assert_method():
    thing = Thing()
    case = unittest.TestCase()
    case.assertEqual(thing._cache, {})


def test_private_outside_assert():
    thing = Thing()
    thing._cache = {"a": 1}
    assert add(1, 2) == 3


def test_dunder_attribute():
    assert Thing().__class__ is Thing


class TestSelfPrivate:
    def test_self_private(self):
        self._value = add(1, 2)
        assert self._value == 3
