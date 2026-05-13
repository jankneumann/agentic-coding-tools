"""Per-skill conftest stub.

Exists so pytest treats this directory as a distinct rootpath, which avoids
basename collisions when multiple skill test directories all expose a
``test_skill_md.py`` module (the hyphenated parent directory names cannot
be used as Python package names, so without this stub pytest falls back to
bare-module imports and trips on the duplicate basename).
"""
