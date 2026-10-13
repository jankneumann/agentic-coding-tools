"""Text helpers."""


def slugify(text):
    """Lowercase ``text`` and join its words with dashes."""
    return "-".join(text.lower().split())


def shout(text):
    """Return ``text`` upper-cased with an exclamation mark."""
    return text.upper() + "!"
