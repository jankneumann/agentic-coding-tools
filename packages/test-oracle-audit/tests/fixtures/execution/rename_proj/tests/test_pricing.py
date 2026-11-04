from shop import pricing
from shop.pricing import price_with_tax


def test_price_public_only():
    assert price_with_tax(100) == 120.0


def test_imports_private_helper():
    from shop.pricing import _round_cents

    assert _round_cents(1.234) == 1.23


def test_patches_private_rate(monkeypatch):
    monkeypatch.setattr(pricing, "_tax_rate", lambda: 0.5)
    assert price_with_tax(100) == 150.0
