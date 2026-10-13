import unittest
import warnings

import pytest
from pkg.mod import add


def test_no_assert():
    add(1, 2)


def test_with_assert():
    assert add(1, 2) == 3


def test_with_raises():
    with pytest.raises(TypeError):
        add(None, 1)


def test_with_warns():
    with pytest.warns(UserWarning):
        warnings.warn("careful", UserWarning)
        add(1, 2)


def test_with_deprecated_call():
    with pytest.deprecated_call():
        warnings.warn("old", DeprecationWarning)
        add(1, 2)


def test_with_assert_method():
    case = unittest.TestCase()
    case.assertEqual(add(1, 2), 3)
