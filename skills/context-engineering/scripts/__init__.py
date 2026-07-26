"""Executable helpers behind the ``context-engineering`` skill.

The modules here are imported flat (``import semantic_context``) after their
directory is put on ``sys.path``, matching every other skill in this tree. The
package marker exists so the directory is a well-formed Python package for
tooling that walks it, not so callers reach these modules by a dotted path.
"""
