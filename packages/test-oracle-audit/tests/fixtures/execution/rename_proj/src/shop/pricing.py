_FLOOR = 0.0


def _round_cents(amount):
    return round(amount, 2)


def _tax_rate():
    return 0.2


def price_with_tax(net):
    return max(_FLOOR, _round_cents(net * (1 + _tax_rate())))
