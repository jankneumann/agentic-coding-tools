"""Unit tests for slug validation and table naming (design D2). No DB/embedder needed."""
from __future__ import annotations

import pytest

from code_search_pkg.identifiers import chunk_table_name, slugify, validate_slug


@pytest.mark.parametrize("slug", ["a", "agentic_coding_tools", "repo1", "x_9_y"])
def test_validate_slug_accepts_legal(slug):
    assert validate_slug(slug) == slug


@pytest.mark.parametrize(
    "bad",
    ["", "1repo", "_repo", "Repo", "has space", "semi;colon", "a" * 52, "dash-name"],
)
def test_validate_slug_rejects_illegal(bad):
    with pytest.raises(ValueError):
        validate_slug(bad)


def test_chunk_table_name_is_prefixed_and_safe():
    assert chunk_table_name("agentic_coding_tools") == "code_chunks__agentic_coding_tools"


def test_chunk_table_name_rejects_injection():
    # A slug that could carry SQL must never reach the table name.
    with pytest.raises(ValueError):
        chunk_table_name("x; DROP TABLE code_chunks__x;--")


@pytest.mark.parametrize(
    "name,expected",
    [
        ("agentic-coding-tools", "agentic_coding_tools"),
        ("My.Repo", "my_repo"),
        ("2024-service", "service"),          # leading digits trimmed
        ("__weird__name__", "weird_name"),    # underscore runs collapse; ends stripped
    ],
)
def test_slugify(name, expected):
    assert slugify(name) == expected


def test_slugify_rejects_unsluggable():
    with pytest.raises(ValueError):
        slugify("123")  # nothing left after trimming leading digits
