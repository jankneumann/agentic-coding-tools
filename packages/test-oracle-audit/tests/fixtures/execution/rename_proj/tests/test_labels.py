from shop.labels import label, plain


def test_label_public_only():
    assert label("a") == "A"
    assert label("b") == "B"
    assert plain() == "p1p2"


def test_all_listed_private_name_is_stable():
    from shop.labels import _exported_one

    assert _exported_one() == "x"
