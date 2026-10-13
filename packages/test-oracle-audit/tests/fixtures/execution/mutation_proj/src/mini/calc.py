"""Pure arithmetic helpers; every function is small and side-effect free."""


def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def sign(n):
    if n > 0:
        return 1
    if n < 0:
        return -1
    return 0


def percent(part, whole):
    if whole == 0:
        return 0.0
    return part * 100 / whole


def bucket(n):
    if n < 10:
        return 0
    if n < 100:
        return 1
    return 2


def is_adult(age):
    return age >= 18
