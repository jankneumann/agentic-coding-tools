"""Arithmetic helpers."""


def _normalize(value):
    return int(value)


def add(a, b):
    """Return the sum of two numbers."""
    return _normalize(a) + _normalize(b)


def clamp(value, low, high):
    """Limit ``value`` to the closed interval [low, high]."""
    if value < low:
        return low
    if value > high:
        return high
    return value
