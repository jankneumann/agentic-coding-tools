from shop.catalog import slug


def test_slug_public_only():
    assert slug("Red Shoes") == "red-shoes"


def test_reexported_private_name_is_stable():
    from shop import _slugify

    assert _slugify("A B") == "a-b"
