import pytest

from mini.text import shout, slugify


def test_slugify_joins_words(words):
    assert slugify(words) == "hello-brave-new-world"


@pytest.mark.parametrize("text", ["a", "b c"])
def test_shout_appends_bang(text):
    assert shout(text).endswith("!")
