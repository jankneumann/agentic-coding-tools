"""Tiny calculator module used as the code under test."""


def _normalise(value):
    return int(value)


def add(a, b):
    """Return the sum of two integers."""
    return _normalise(a) + _normalise(b)


def scale(values, factor):
    """Multiply every value by ``factor`` and return the new list."""
    return [_normalise(v) * factor for v in values]
