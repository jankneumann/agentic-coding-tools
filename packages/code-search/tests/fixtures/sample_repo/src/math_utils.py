"""Small deterministic functions used by semantic-index E2E tests."""


def add(left: int, right: int) -> int:
    """Return the sum of two integers."""

    return left + right


def fibonacci(limit: int) -> list[int]:
    """Return Fibonacci values smaller than ``limit``."""

    values = [0, 1]
    while values[-1] + values[-2] < limit:
        values.append(values[-1] + values[-2])
    return values
