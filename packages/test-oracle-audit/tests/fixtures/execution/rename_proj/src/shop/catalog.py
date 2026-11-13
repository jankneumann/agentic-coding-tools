_SEP = "-"


def _slugify(name):
    return name.lower().replace(" ", _SEP)


def slug(name):
    return _slugify(name)
