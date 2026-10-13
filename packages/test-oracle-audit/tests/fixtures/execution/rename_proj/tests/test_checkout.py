from shop.labels import label
from shop.pricing import price_with_tax


def test_price_and_label_public_only():
    assert price_with_tax(10) == 12.0
    assert label("a") == "A"
