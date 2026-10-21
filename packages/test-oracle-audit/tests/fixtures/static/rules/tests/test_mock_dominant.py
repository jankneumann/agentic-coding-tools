from unittest.mock import Mock

from pkg.mod import add


def test_mock_heavy():
    callback = Mock()
    callback(add(1, 2))
    callback.assert_called_once_with(3)
    assert callback.call_count == 1
    assert callback.call_args[0][0] == 3
    assert add(1, 1) == 2


def test_mock_called_attribute_only():
    callback = Mock()
    callback()
    assert callback.called


def test_mock_not_called_only():
    callback = Mock()
    callback.assert_not_called()


def test_mock_tie():
    callback = Mock()
    callback(1)
    callback.assert_called_once()
    assert add(1, 2) == 3


def test_mock_minority():
    callback = Mock()
    callback(1)
    callback.assert_called_once()
    assert add(1, 2) == 3
    assert add(2, 2) == 4
