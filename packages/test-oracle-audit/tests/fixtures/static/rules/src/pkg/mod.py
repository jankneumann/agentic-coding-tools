__version__ = "1"
CONST = 1


def add(a, b):
    return a + b


def sub(a, b):
    return a - b


def helper():
    return 1


def _helper(x):
    return 2 * x


def _secret():
    return 1


class Thing:
    def __init__(self):
        self._cache = {}
