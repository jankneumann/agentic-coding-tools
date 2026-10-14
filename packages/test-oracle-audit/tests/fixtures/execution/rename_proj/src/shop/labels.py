__all__ = ["label", "_exported_one", "_exported_two"]

REGISTRY = {"a": "_by_string", "b": "_also_string"}


def _exported_one():
    return "x"


def _exported_two():
    return "y"


def _by_string():
    return "A"


def _also_string():
    return "B"


def _plain_one():
    return "p1"


def _plain_two():
    return "p2"


def label(kind):
    return globals()[REGISTRY[kind]]()


def plain():
    return _plain_one() + _plain_two()
